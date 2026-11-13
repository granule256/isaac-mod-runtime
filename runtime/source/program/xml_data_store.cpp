#include "program/xml_data_store.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>
#include <string_view>
#include <unordered_map>

namespace isaac::runtime::xml_data {
namespace {

constexpr std::size_t kMaximumXmlBytes = 16U * 1024U * 1024U;

char LowerAscii(char value) noexcept {
    return value >= 'A' && value <= 'Z' ? static_cast<char>(value + ('a' - 'A')) : value;
}

std::string LowerAscii(std::string value) {
    for (char& character : value) {
        character = LowerAscii(character);
    }
    return value;
}

bool StartsWith(const char* data, std::size_t length, std::size_t position,
                const char* token) noexcept {
    if (data == nullptr || token == nullptr) return false;
    const std::size_t tokenLength = std::strlen(token);
    return position <= length && tokenLength <= length - position &&
           std::memcmp(data + position, token, tokenLength) == 0;
}

bool IsWhitespace(char value) noexcept {
    return value == ' ' || value == '\t' || value == '\r' || value == '\n';
}

int ParseInteger(const std::string& value) noexcept {
    if (value.empty()) return 0;
    char* end = nullptr;
    const long parsed = std::strtol(value.c_str(), &end, 0);
    return end != value.c_str() ? static_cast<int>(parsed) : 0;
}

std::string IntegerString(int value) {
    return std::to_string(value);
}

void SetAttribute(XmlRecord* record, const char* name, std::string value) {
    if (record == nullptr || name == nullptr) return;
    for (XmlAttribute& attribute : record->attributes) {
        if (attribute.name == name) {
            attribute.value = std::move(value);
            return;
        }
    }
    record->attributes.push_back(XmlAttribute{name, std::move(value)});
}

const XmlAttribute* FindAttribute(const XmlRecord& record, const char* name) noexcept {
    return record.FindAttribute(name);
}

void MergeMissingAttributes(std::vector<XmlAttribute>* destination,
                            const std::vector<XmlAttribute>& source) {
    if (destination == nullptr) return;
    for (const XmlAttribute& attribute : source) {
        bool present = false;
        for (const XmlAttribute& existing : *destination) {
            if (existing.name == attribute.name) {
                present = true;
                break;
            }
        }
        if (!present) destination->push_back(attribute);
    }
}

void AppendUtf8(std::string* output, std::uint32_t codepoint) {
    if (output == nullptr || codepoint > 0x10FFFFU ||
        (codepoint >= 0xD800U && codepoint <= 0xDFFFU)) {
        return;
    }
    if (codepoint <= 0x7FU) {
        output->push_back(static_cast<char>(codepoint));
    } else if (codepoint <= 0x7FFU) {
        output->push_back(static_cast<char>(0xC0U | (codepoint >> 6U)));
        output->push_back(static_cast<char>(0x80U | (codepoint & 0x3FU)));
    } else if (codepoint <= 0xFFFFU) {
        output->push_back(static_cast<char>(0xE0U | (codepoint >> 12U)));
        output->push_back(static_cast<char>(0x80U | ((codepoint >> 6U) & 0x3FU)));
        output->push_back(static_cast<char>(0x80U | (codepoint & 0x3FU)));
    } else {
        output->push_back(static_cast<char>(0xF0U | (codepoint >> 18U)));
        output->push_back(static_cast<char>(0x80U | ((codepoint >> 12U) & 0x3FU)));
        output->push_back(static_cast<char>(0x80U | ((codepoint >> 6U) & 0x3FU)));
        output->push_back(static_cast<char>(0x80U | (codepoint & 0x3FU)));
    }
}

bool DecodeValue(std::string_view raw, std::string* decoded) {
    if (decoded == nullptr) return false;
    decoded->clear();
    decoded->reserve(raw.size());
    for (std::size_t index = 0; index < raw.size();) {
        if (raw[index] != '&') {
            decoded->push_back(raw[index++]);
            continue;
        }
        const std::size_t end = raw.find(';', index + 1);
        if (end == std::string_view::npos) return false;
        const std::string_view entity = raw.substr(index + 1, end - index - 1);
        if (entity == "amp") {
            decoded->push_back('&');
        } else if (entity == "lt") {
            decoded->push_back('<');
        } else if (entity == "gt") {
            decoded->push_back('>');
        } else if (entity == "quot") {
            decoded->push_back('"');
        } else if (entity == "apos") {
            decoded->push_back('\'');
        } else if (!entity.empty() && entity.front() == '#') {
            std::uint32_t value = 0;
            bool valid = false;
            std::size_t cursor = 1;
            int radix = 10;
            if (cursor < entity.size() && (entity[cursor] == 'x' || entity[cursor] == 'X')) {
                radix = 16;
                ++cursor;
            }
            if (cursor >= entity.size()) return false;
            for (; cursor < entity.size(); ++cursor) {
                const char character = entity[cursor];
                int digit = -1;
                if (character >= '0' && character <= '9') digit = character - '0';
                if (radix == 16 && character >= 'a' && character <= 'f') digit = character - 'a' + 10;
                if (radix == 16 && character >= 'A' && character <= 'F') digit = character - 'A' + 10;
                if (digit < 0 || digit >= radix) return false;
                if (value > (0x10FFFFU - static_cast<std::uint32_t>(digit)) /
                                static_cast<std::uint32_t>(radix)) {
                    return false;
                }
                value = value * static_cast<std::uint32_t>(radix) +
                        static_cast<std::uint32_t>(digit);
                valid = true;
            }
            if (!valid) return false;
            AppendUtf8(decoded, value);
        } else {
            return false;  // Do not accept external or HTML-only entities.
        }
        index = end + 1;
    }
    return true;
}

struct Tag {
    std::string name;
    std::vector<XmlAttribute> attributes;
    bool selfClosing{};
};

struct ParsedDocument {
    std::string root;
    std::vector<XmlAttribute> rootAttributes;
    std::vector<XmlRecord> records;
};

class Parser {
public:
    Parser(const char* data, std::size_t length) : data_(data), length_(length) {}

    bool Parse(ParsedDocument* output) {
        if (data_ == nullptr || output == nullptr || length_ == 0 ||
            length_ > kMaximumXmlBytes) {
            return false;
        }
        SkipBom();
        SkipWhitespace();
        SkipTopLevelMisc();
        Tag root;
        if (!ParseStartTag(&root)) return false;
        output->root = root.name;
        output->rootAttributes = std::move(root.attributes);
        if (root.selfClosing) {
            SkipWhitespace();
            SkipTopLevelMisc();
            return position_ == length_;
        }

        std::vector<std::string> stack;
        stack.push_back(root.name);
        std::size_t currentRecord = std::numeric_limits<std::size_t>::max();
        bool rootClosed = false;
        while (position_ < length_) {
            while (position_ < length_ && data_[position_] != '<') ++position_;
            if (position_ >= length_) break;

            if (StartsWith(data_, length_, position_, "<!--")) {
                if (!SkipComment()) return false;
                continue;
            }
            if (StartsWith(data_, length_, position_, "<?")) {
                if (!SkipProcessingInstruction()) return false;
                continue;
            }
            if (StartsWith(data_, length_, position_, "<![CDATA[")) {
                if (!SkipCdata()) return false;
                continue;
            }
            if (StartsWith(data_, length_, position_, "<!")) {
                return false;  // DOCTYPE, ENTITY and other declarations are not accepted.
            }
            if (StartsWith(data_, length_, position_, "</")) {
                std::string endName;
                if (!ParseEndTag(&endName) || stack.empty() || stack.back() != endName) {
                    return false;
                }
                stack.pop_back();
                if (stack.empty()) {
                    rootClosed = true;
                    break;
                }
                continue;
            }

            Tag tag;
            if (!ParseStartTag(&tag)) return false;
            const std::size_t parentDepth = stack.size();
            if (parentDepth == 1) {
                XmlRecord record;
                record.attributes = std::move(tag.attributes);
                output->records.push_back(std::move(record));
                currentRecord = output->records.size() - 1;
            } else if (parentDepth == 2 &&
                       currentRecord != std::numeric_limits<std::size_t>::max()) {
                XmlRecord& record = output->records[currentRecord];
                const std::string tagName = LowerAscii(tag.name);
                XmlChildGroup* group = nullptr;
                for (XmlChildGroup& candidate : record.children) {
                    if (candidate.tag == tagName) {
                        group = &candidate;
                        break;
                    }
                }
                if (group == nullptr) {
                    record.children.push_back(XmlChildGroup{tagName, {}});
                    group = &record.children.back();
                }
                group->entries.push_back(XmlChild{std::move(tag.attributes)});
            }
            if (!tag.selfClosing) stack.push_back(std::move(tag.name));
        }

        if (!rootClosed) return false;
        SkipWhitespace();
        SkipTopLevelMisc();
        return position_ == length_;
    }

private:
    void SkipBom() noexcept {
        if (length_ >= 3 && static_cast<unsigned char>(data_[0]) == 0xEF &&
            static_cast<unsigned char>(data_[1]) == 0xBB &&
            static_cast<unsigned char>(data_[2]) == 0xBF) {
            position_ = 3;
        }
    }

    void SkipWhitespace() noexcept {
        while (position_ < length_ && IsWhitespace(data_[position_])) ++position_;
    }

    bool SkipComment() {
        const std::size_t start = position_ + 4;
        const std::size_t end = Find("-->", start);
        if (end == std::string::npos) return false;
        position_ = end + 3;
        return true;
    }

    bool SkipProcessingInstruction() {
        const std::size_t end = Find("?>", position_ + 2);
        if (end == std::string::npos) return false;
        position_ = end + 2;
        return true;
    }

    bool SkipCdata() {
        const std::size_t end = Find("]]>", position_ + 9);
        if (end == std::string::npos) return false;
        position_ = end + 3;
        return true;
    }

    void SkipTopLevelMisc() {
        while (position_ < length_) {
            SkipWhitespace();
            if (position_ >= length_) return;
            if (StartsWith(data_, length_, position_, "<!--")) {
                if (!SkipComment()) {
                    position_ = length_;
                    return;
                }
                continue;
            }
            if (StartsWith(data_, length_, position_, "<?")) {
                if (!SkipProcessingInstruction()) {
                    position_ = length_;
                    return;
                }
                continue;
            }
            return;
        }
    }

    std::size_t Find(const char* needle, std::size_t start) const noexcept {
        if (needle == nullptr || start > length_) return std::string::npos;
        const std::size_t needleLength = std::strlen(needle);
        if (needleLength > length_ - start) return std::string::npos;
        for (std::size_t i = start; i + needleLength <= length_; ++i) {
            if (std::memcmp(data_ + i, needle, needleLength) == 0) return i;
        }
        return std::string::npos;
    }

    bool ParseName(std::string* name) {
        if (name == nullptr || position_ >= length_) return false;
        const std::size_t begin = position_;
        while (position_ < length_) {
            const char value = data_[position_];
            if (IsWhitespace(value) || value == '>' || value == '/' || value == '=' ||
                value == '<') {
                break;
            }
            ++position_;
        }
        if (position_ == begin) return false;
        name->assign(data_ + begin, position_ - begin);
        return true;
    }

    bool ParseStartTag(Tag* tag) {
        if (tag == nullptr || position_ >= length_ || data_[position_] != '<') return false;
        ++position_;
        if (position_ >= length_ || data_[position_] == '/' || data_[position_] == '!' ||
            data_[position_] == '?') {
            return false;
        }
        if (!ParseName(&tag->name)) return false;
        for (;;) {
            SkipWhitespace();
            if (position_ >= length_) return false;
            if (data_[position_] == '>') {
                ++position_;
                return true;
            }
            if (data_[position_] == '/') {
                if (position_ + 1 >= length_ || data_[position_ + 1] != '>') return false;
                position_ += 2;
                tag->selfClosing = true;
                return true;
            }
            std::string name;
            if (!ParseName(&name)) return false;
            SkipWhitespace();
            if (position_ >= length_ || data_[position_] != '=') return false;
            ++position_;
            SkipWhitespace();
            if (position_ >= length_ || (data_[position_] != '\'' && data_[position_] != '"')) {
                return false;
            }
            const char quote = data_[position_++];
            const std::size_t valueBegin = position_;
            while (position_ < length_ && data_[position_] != quote) {
                if (data_[position_] == '<') return false;
                ++position_;
            }
            if (position_ >= length_) return false;
            const std::string_view raw(data_ + valueBegin, position_ - valueBegin);
            ++position_;  // closing quote
            std::string decoded;
            if (!DecodeValue(raw, &decoded)) return false;
            const std::string lowerName = LowerAscii(std::move(name));
            bool replaced = false;
            for (XmlAttribute& attribute : tag->attributes) {
                if (attribute.name == lowerName) {
                    attribute.value = std::move(decoded);
                    replaced = true;
                    break;
                }
            }
            if (!replaced) {
                tag->attributes.push_back(XmlAttribute{lowerName, std::move(decoded)});
            }
        }
    }

    bool ParseEndTag(std::string* name) {
        if (name == nullptr || position_ + 2 > length_ || data_[position_] != '<' ||
            data_[position_ + 1] != '/') {
            return false;
        }
        position_ += 2;
        if (!ParseName(name)) return false;
        SkipWhitespace();
        if (position_ >= length_ || data_[position_] != '>') return false;
        ++position_;
        return true;
    }

    const char* data_{};
    std::size_t length_{};
    std::size_t position_{};
};

struct EntityKey {
    int type{};
    int variant{};
    int subtype{};

    friend bool operator==(const EntityKey& left, const EntityKey& right) noexcept {
        return left.type == right.type && left.variant == right.variant &&
               left.subtype == right.subtype;
    }
};

struct EntityKeyHash {
    std::size_t operator()(const EntityKey& key) const noexcept {
        std::size_t value = static_cast<std::size_t>(static_cast<std::uint32_t>(key.type));
        value = value * 0x9E3779B1U + static_cast<std::size_t>(key.variant);
        value = value * 0x85EBCA77U + static_cast<std::size_t>(key.subtype);
        return value;
    }
};

struct CategoryState {
    std::vector<XmlRecord> records;
    std::unordered_map<int, std::size_t> byId;
    std::unordered_map<EntityKey, std::size_t, EntityKeyHash> byTuple;
    std::vector<std::size_t> order;
    int maxId{};
    std::unordered_map<std::string, int> byName;
};

struct Store {
    CategoryState categories[4];
};

Store* g_store = nullptr;
XmlDataStoreStats g_stats{};

int CategoryIndex(XmlNodeType type) noexcept {
    switch (type) {
        case XmlNodeType::Entity:
            return 0;
        case XmlNodeType::Challenge:
            return 1;
        case XmlNodeType::Backdrop:
            return 2;
        case XmlNodeType::GiantBook:
            return 3;
        default:
            return -1;
    }
}

XmlNodeType NodeTypeFor(XmlDataFileKind kind) noexcept {
    switch (kind) {
        case XmlDataFileKind::Entities:
            return XmlNodeType::Entity;
        case XmlDataFileKind::Challenges:
            return XmlNodeType::Challenge;
        case XmlDataFileKind::Backdrops:
            return XmlNodeType::Backdrop;
        case XmlDataFileKind::GiantBooks:
            return XmlNodeType::GiantBook;
    }
    return XmlNodeType::Mod;
}

const char* ExpectedRoot(XmlNodeType type) noexcept {
    switch (type) {
        case XmlNodeType::Entity:
            return "entities";
        case XmlNodeType::Challenge:
            return "challenges";
        case XmlNodeType::Backdrop:
            return "backdrops";
        case XmlNodeType::GiantBook:
            return "giantbook";
        default:
            return nullptr;
    }
}

void ApplySource(XmlRecord* record, const char* sourceId) {
    if (record == nullptr) return;
    const char* id = sourceId != nullptr && sourceId[0] != '\0' ? sourceId : "BaseGame";
    SetAttribute(record, "sourceid", id);
}

void TranslateEntityName(XmlRecord* record, const XmlNameTranslator& translator) {
    if (record == nullptr || translator.translate == nullptr) return;
    const XmlAttribute* name = FindAttribute(*record, "name");
    if (name == nullptr || name->value.empty() || name->value.front() != '#') return;
    char translated[4096]{};
    std::size_t length = 0;
    if (!translator.translate(translator.context, "Entities", name->value.c_str() + 1,
                              translated, sizeof(translated), &length) ||
        length == 0 || length >= sizeof(translated)) {
        return;
    }
    translated[length] = '\0';
    SetAttribute(record, "untranslatedname", name->value);
    SetAttribute(record, "name", std::string(translated, length));
}

void ProcessBackdropName(XmlRecord* record) {
    if (record == nullptr || FindAttribute(*record, "name") != nullptr) return;
    const XmlAttribute* gfx = FindAttribute(*record, "gfx");
    std::string name;
    if (gfx != nullptr) {
        name = gfx->value;
        if (name.size() >= 4) {
            name.resize(name.size() - 4);
        } else {
            name.clear();
        }
        const std::size_t underscore = name.find('_');
        if (underscore > 0 && underscore < 4) {
            name.erase(0, underscore + 1);
        }
    }
    SetAttribute(record, "name", std::move(name));
}

void AddOrReplaceById(CategoryState* category, XmlRecord record) {
    auto found = category->byId.find(record.id);
    if (found != category->byId.end()) {
        category->records[found->second] = std::move(record);
        return;
    }
    const std::size_t index = category->records.size();
    category->records.push_back(std::move(record));
    category->byId.emplace(category->records.back().id, index);
    category->order.push_back(index);
}

int AddChallengeOrBackdrop(CategoryState* category, XmlRecord record, bool isContent,
                            XmlNodeType type) {
    const XmlAttribute* explicitId = FindAttribute(record, "id");
    int id = 0;
    if (type == XmlNodeType::Backdrop) {
        if (explicitId != nullptr) {
            id = ParseInteger(explicitId->value);
        } else {
            id = ++category->maxId;
            SetAttribute(&record, "id", IntegerString(id));
        }
        category->maxId = std::max(category->maxId, id);
    } else if (!isContent && explicitId != nullptr) {
        id = ParseInteger(explicitId->value);
        category->maxId = std::max(category->maxId, id);
    } else {
        if (explicitId != nullptr) {
            SetAttribute(&record, "relativeid", explicitId->value);
        }
        id = ++category->maxId;
        SetAttribute(&record, "id", IntegerString(id));
    }
    record.id = id;
    AddOrReplaceById(category, std::move(record));
    return id;
}

bool IsEntityCollisionCluster(int type) noexcept {
    return type < 10 || type >= 1000;
}

void AddEntity(CategoryState* category, XmlRecord record, bool isContent) {
    const XmlAttribute* id = FindAttribute(record, "id");
    int type = id != nullptr ? ParseInteger(id->value) : 0;
    const XmlAttribute* variantAttribute = FindAttribute(record, "variant");
    const XmlAttribute* subtypeAttribute = FindAttribute(record, "subtype");
    int variant = variantAttribute != nullptr ? ParseInteger(variantAttribute->value) : 0;
    const int subtype = subtypeAttribute != nullptr ? ParseInteger(subtypeAttribute->value) : 0;

    EntityKey key{type, variant, subtype};
    if (variantAttribute == nullptr && IsEntityCollisionCluster(type)) {
        while (category->byTuple.find(key) != category->byTuple.end()) {
            key.variant += 1;
        }
        variant = key.variant;
    }
    if (isContent && category->byTuple.find(key) != category->byTuple.end()) {
        if (IsEntityCollisionCluster(type)) {
            do {
                key.variant += 1;
                variant = key.variant;
            } while (category->byTuple.find(key) != category->byTuple.end());
        } else {
            do {
                key.type += 1;
                type = key.type;
            } while (category->byTuple.find(key) != category->byTuple.end());
        }
    }

    SetAttribute(&record, "id", IntegerString(type));
    SetAttribute(&record, "type", IntegerString(type));
    SetAttribute(&record, "variant", IntegerString(variant));
    record.id = type;

    auto found = category->byTuple.find(key);
    if (found != category->byTuple.end()) {
        category->records[found->second] = std::move(record);
        return;
    }
    const std::size_t index = category->records.size();
    category->records.push_back(std::move(record));
    category->byTuple.emplace(key, index);
    category->order.push_back(index);
}

bool AddRecord(XmlDataFileKind kind, XmlRecord record, bool isContent,
               const char* sourceId, const XmlNameTranslator& translator) {
    const XmlNodeType type = NodeTypeFor(kind);
    if (type == XmlNodeType::Entity) {
        ApplySource(&record, sourceId);
        TranslateEntityName(&record, translator);
        AddEntity(&g_store->categories[CategoryIndex(type)], std::move(record), isContent);
    } else if (type == XmlNodeType::Challenge || type == XmlNodeType::Backdrop ||
               type == XmlNodeType::GiantBook) {
        ApplySource(&record, sourceId);
        if (type == XmlNodeType::Backdrop) ProcessBackdropName(&record);
        if (type == XmlNodeType::GiantBook && !FindAttribute(record, "name")) {
            const auto* gfx = FindAttribute(record, "gfx");
            if (gfx) {
                auto name = gfx->value;
                const auto separator = name.find_last_of("/\\");
                if (separator != std::string::npos) name.erase(0, separator + 1);
                const auto extension = name.find_last_of('.');
                if (extension != std::string::npos) name.resize(extension);
                SetAttribute(&record, "name", std::move(name));
            }
        }
        auto& category = g_store->categories[CategoryIndex(type)];
        const int id = AddChallengeOrBackdrop(&category, std::move(record), isContent, type);
        if (type == XmlNodeType::GiantBook) {
            const auto* name = category.records[category.byId.find(id)->second].FindAttribute("name");
            if (name) category.byName[name->value] = id;
        }
    } else {
        return false;
    }
    return true;
}

void RefreshStats() {
    if (g_store == nullptr) {
        g_stats.entities = 0;
        g_stats.challenges = 0;
        g_stats.backdrops = 0;
        return;
    }
    g_stats.entities = static_cast<std::uint32_t>(g_store->categories[0].records.size());
    g_stats.challenges = static_cast<std::uint32_t>(g_store->categories[1].records.size());
    g_stats.backdrops = static_cast<std::uint32_t>(g_store->categories[2].records.size());
}

}  // namespace

void ResetXmlDataStore() noexcept {
    delete g_store;
    g_store = nullptr;
    g_stats = {};
}

bool IngestXmlDataFile(XmlDataFileKind kind, const char* source_id, bool is_content,
                       const char* xml, std::size_t length,
                       const XmlNameTranslator& translator) noexcept {
    const XmlNodeType type = NodeTypeFor(kind);
    const char* rootName = ExpectedRoot(type);
    if (rootName == nullptr || xml == nullptr || length == 0 || length > kMaximumXmlBytes) {
        ++g_stats.rejected_files;
        return false;
    }

    ParsedDocument document;
    Parser parser(xml, length);
    if (!parser.Parse(&document) || document.root != rootName) {
        ++g_stats.rejected_files;
        return false;
    }

    if (g_store == nullptr) {
        g_store = new (std::nothrow) Store{};
        if (g_store == nullptr) {
            ++g_stats.rejected_files;
            return false;
        }
    }

    for (XmlRecord& record : document.records) {
        if (type == XmlNodeType::Entity || type == XmlNodeType::Backdrop ||
            type == XmlNodeType::GiantBook) {
            MergeMissingAttributes(&record.attributes, document.rootAttributes);
        }
        if (!AddRecord(kind, std::move(record), is_content, source_id, translator)) {
            ++g_stats.rejected_files;
            return false;
        }
    }
    ++g_stats.files;
    RefreshStats();
    return true;
}

const XmlRecord* FindEntityByTypeVarSub(int type, int variant, int subtype,
                                        bool strict) noexcept {
    if (g_store == nullptr) return nullptr;
    const CategoryState& category = g_store->categories[0];
    auto find = [&category](int t, int v, int s) -> const XmlRecord* {
        const auto found = category.byTuple.find(EntityKey{t, v, s});
        return found == category.byTuple.end() ? nullptr : &category.records[found->second];
    };
    if (const XmlRecord* exact = find(type, variant, subtype)) return exact;
    if (strict) return nullptr;
    if (const XmlRecord* variantOnly = find(type, variant, 0)) return variantOnly;
    return find(type, 0, 0);
}

const XmlRecord* FindEntryById(XmlNodeType type, int id) noexcept {
    if (g_store == nullptr) return nullptr;
    if (type == XmlNodeType::Entity) return FindEntityByTypeVarSub(id, 0, 0, false);
    const int index = CategoryIndex(type);
    if (index < 0) return nullptr;
    const CategoryState& category = g_store->categories[index];
    const auto found = category.byId.find(id);
    return found == category.byId.end() ? nullptr : &category.records[found->second];
}

const XmlRecord* FindGiantBookByName(const char* name) noexcept {
    if (!g_store || !name) return nullptr;
    const auto& category = g_store->categories[3];
    const auto found = category.byName.find(name);
    return found == category.byName.end() ? nullptr :
        FindEntryById(XmlNodeType::GiantBook, found->second);
}

const XmlRecord* FindEntryByOrder(XmlNodeType type, int order) noexcept {
    if (g_store == nullptr || order <= 0) return nullptr;
    const int index = CategoryIndex(type);
    if (index < 0) return nullptr;
    const CategoryState& category = g_store->categories[index];
    const std::size_t position = static_cast<std::size_t>(order - 1);
    return position < category.order.size() ? &category.records[category.order[position]]
                                            : nullptr;
}

std::size_t CountEntries(XmlNodeType type) noexcept {
    if (g_store == nullptr) return 0;
    const int index = CategoryIndex(type);
    if (index < 0) return 0;
    const CategoryState& category = g_store->categories[index];
    return type == XmlNodeType::Entity ? category.records.size() : category.byId.size();
}

const XmlDataStoreStats& Statistics() noexcept {
    return g_stats;
}

}  // namespace isaac::runtime::xml_data
