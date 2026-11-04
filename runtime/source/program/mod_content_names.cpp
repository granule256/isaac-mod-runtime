// 批次 404（2026-10-07）：`Isaac.Get*ByName` 名字表一族里"收藏品 / 饰品 / 卡牌"三条的
// 运行时追加层 —— 实现。语义、id 规则、逐族证据、顺序约束、幂等与坏文件的处置**全部**写在
// 同名 `.hpp` 的文件头，这里只写实现细节。
//
// ★ 为什么不用 `std::map` / 动态分配：本模块 `-nostartfiles`，函数里带动态初始化的 `static`
//   会在 `__cxa_guard_*` 上自旋（黑屏有声不崩，见门禁 `test_no_static_guard_init.py`）。
//   这里一切状态都是**文件作用域的 POD**（零/常量初始化 ⇒ 无静态守卫），不拥有堆。
// ★ 为什么不用 `<string>`：追加层只在启动喂入时写几十条，线性扫足够；存储用"名字池 + 定长条目"
//   （与 `isaac_name_tables` / `mod_player_names` 同一形状），于是它**不拥有堆**，
//   也就不可能因为分配失败半途丢一条名字（那会让后面的 id 整体错位）。

#include "program/mod_content_names.hpp"

#include <cstring>

namespace isaac::runtime {
namespace {

//: 容量。都取到"远超任何真实模组"的量（取小了的后果是**静默**的，宁可多留）。
constexpr std::uint32_t kMaxNameBytes = 16384;
constexpr std::uint32_t kMaxEntries = 1024;         //: 全部族共享的条目表
constexpr std::uint32_t kMaxEntriesPerFile = 512;   //: 一份 xml 最多解析这么多条
constexpr std::uint32_t kMaxModKeys = 96;           //: = 引擎模组上限 32 的三倍
constexpr std::size_t kMaxModKeyLength = 128;

struct Entry {
    std::uint32_t nameOffset;  //: 在名字池里的字节下标
    std::int32_t id;
    ModContentNameFamily family;
};

// 全部状态（文件作用域 POD）：零初始化或常量初始化 ⇒ 不会有 `__cxa_guard_*`。
char g_NamePool[kMaxNameBytes] = {};
std::uint32_t g_NameUsed = 0;
Entry g_Entries[kMaxEntries] = {};
std::uint32_t g_EntryCount = 0;
char g_ModKeys[kMaxModKeys][kMaxModKeyLength] = {};
std::uint8_t g_ModKeyFiles[kMaxModKeys] = {};
std::uint32_t g_ModKeyCount = 0;

//: 每族下一个 id。基准 = 本体该类条数（逐族取证见 `.hpp` 表头）。
//: ★ 每条**识别到的**条目（无论有没有名字、无论有没有存下）都 +1 —— 与引擎"往向量里
//:   追加一格"同语义；漏推进会让后面的条目整体错位（静默错）。
std::int32_t g_NextId[static_cast<std::size_t>(ModContentNameFamily::Count)] = {
    kModContentNameIdBase[0], kModContentNameIdBase[1], kModContentNameIdBase[2],
};
ModContentNameStats g_Stats = {};

//: 一条识别规则：标签名 → 归哪一族。
struct TagRule {
    const char* tag;
    std::uint32_t tagLength;
    ModContentNameFamily family;
};

//: `items.xml` 的识别规则：`<passive>/<active>/<familiar>` 归收藏品、`<trinket>` 归饰品。
//: 其余标签（`<null>` 等）**不识别、不占 id**（引擎把它们放进**另一条**向量）。
constexpr TagRule kItemsRules[] = {
    {"passive", 7, ModContentNameFamily::Collectible},
    {"active", 6, ModContentNameFamily::Collectible},
    {"familiar", 8, ModContentNameFamily::Collectible},
    {"trinket", 7, ModContentNameFamily::Trinket},
};
//: `pocketitems.xml` 的识别规则：`<card>` 与 `<rune>` **同一条处理路**（都进卡牌向量）；
//: `<pilleffect>` 走另一条路（药丸向量）⇒ 不识别、不占卡牌 id。
constexpr TagRule kPocketRules[] = {
    {"card", 4, ModContentNameFamily::Card},
    {"rune", 4, ModContentNameFamily::Card},
};

const TagRule* RulesFor(ModContentFileKind file, std::uint32_t* count) noexcept {
    if (file == ModContentFileKind::Items) {
        *count = static_cast<std::uint32_t>(sizeof(kItemsRules) / sizeof(kItemsRules[0]));
        return kItemsRules;
    }
    *count = static_cast<std::uint32_t>(sizeof(kPocketRules) / sizeof(kPocketRules[0]));
    return kPocketRules;
}

const char* RootNameFor(ModContentFileKind file, std::size_t* length) noexcept {
    if (file == ModContentFileKind::Items) {
        *length = 5;  // "items"
        return "items";
    }
    *length = 11;  // "pocketitems"
    return "pocketitems";
}

bool IsSpace(char c) noexcept {
    return c == ' ' || c == '\t' || c == '\r' || c == '\n';
}

bool IsTagNameChar(char c) noexcept {
    return c != ' ' && c != '\t' && c != '\r' && c != '\n' && c != '/' && c != '>' && c != '=';
}

//: 从 `<`（下标 `start`）起找该标签的 `>`（跳过引号内的 `>`）。找到返回 true 并给 `*tagEnd`。
bool FindTagEnd(const char* xml, std::size_t start, std::size_t length,
                std::size_t* tagEnd) noexcept {
    char quote = '\0';
    for (std::size_t i = start + 1; i < length; ++i) {
        const char c = xml[i];
        if (quote != '\0') {
            if (c == quote) {
                quote = '\0';
            }
            continue;
        }
        if (c == '"' || c == '\'') {
            quote = c;
            continue;
        }
        if (c == '>') {
            *tagEnd = i;
            return true;
        }
    }
    return false;
}

//: 从标签内容里取一个属性的值（去引号）。`nameStart` = 标签名首字符（`<` 的后一格）。
bool ExtractAttribute(const char* xml, std::size_t nameStart, std::size_t tagEnd,
                      const char* attribute, std::size_t attributeLength, const char** value,
                      std::size_t* valueLength) noexcept {
    std::size_t i = nameStart;
    while (i < tagEnd && IsTagNameChar(xml[i])) {  // 跳过标签名
        ++i;
    }
    while (i < tagEnd) {
        while (i < tagEnd && (IsSpace(xml[i]) || xml[i] == '/')) {
            ++i;
        }
        if (i >= tagEnd) {
            break;
        }
        const std::size_t nameBegin = i;
        while (i < tagEnd && IsTagNameChar(xml[i])) {
            ++i;
        }
        const std::size_t nameLength = i - nameBegin;
        while (i < tagEnd && IsSpace(xml[i])) {
            ++i;
        }
        if (i >= tagEnd || xml[i] != '=') {
            continue;
        }
        ++i;
        while (i < tagEnd && IsSpace(xml[i])) {
            ++i;
        }
        if (i >= tagEnd) {
            break;
        }
        const char quote = xml[i];
        const bool quoted = quote == '"' || quote == '\'';
        if (quoted) {
            ++i;
        }
        const std::size_t valueBegin = i;
        while (i < tagEnd && (quoted ? xml[i] != quote : !IsSpace(xml[i]))) {
            ++i;
        }
        const std::size_t length = i - valueBegin;
        if (nameLength == attributeLength &&
            std::memcmp(xml + nameBegin, attribute, attributeLength) == 0) {
            *value = xml + valueBegin;
            *valueLength = length;
            return true;
        }
        if (quoted && i < tagEnd) {
            ++i;
        }
    }
    return false;
}

//: 把一个属性值解析成整数（只认 `[+-]?[0-9]+`）。失败返回 false。
bool ParseIntAttribute(const char* text, std::size_t length, std::int32_t* out) noexcept {
    if (length == 0) {
        return false;
    }
    std::size_t i = 0;
    bool negative = false;
    if (text[0] == '-') {
        negative = true;
        i = 1;
    } else if (text[0] == '+') {
        i = 1;
    }
    if (i >= length) {
        return false;
    }
    long value = 0;
    for (; i < length; ++i) {
        if (text[i] < '0' || text[i] > '9') {
            return false;
        }
        value = value * 10 + (text[i] - '0');
        if (value > 2000000000L) {
            return false;
        }
    }
    *out = negative ? -static_cast<std::int32_t>(value) : static_cast<std::int32_t>(value);
    return true;
}

//: 扫下一个标签：`*nameStart/*nameLength` = 标签名（`<` 之后那一段），`*tagEnd` = 它的 `>`。
//: 返回 false = 没有更多标签；`*truncated` = true 表示遇到一个没有闭合 `>` 的标签（坏文件）。
bool NextTag(const char* xml, std::size_t length, std::size_t* cursor, std::size_t* nameStart,
             std::size_t* nameLength, std::size_t* tagEnd, bool* truncated) noexcept {
    while (*cursor < length) {
        while (*cursor < length && xml[*cursor] != '<') {
            ++*cursor;
        }
        if (*cursor >= length) {
            return false;
        }
        const std::size_t tag = *cursor;
        // 注释是原始文本；其中的撇号、引号和假标签都不能按属性语法解释。
        if (length - tag >= 4 && std::memcmp(xml + tag, "<!--", 4) == 0) {
            std::size_t end = tag + 4;
            while (length - end >= 3 && std::memcmp(xml + end, "-->", 3) != 0) {
                ++end;
            }
            if (length - end < 3) {
                *truncated = true;
                *cursor = length;
                return false;
            }
            *cursor = end + 3;
            continue;
        }
        if (tag + 1 < length &&
            (xml[tag + 1] == '!' || xml[tag + 1] == '?' || xml[tag + 1] == '/')) {
            // 其它声明 / 闭合标签：整段跳过。
            std::size_t end = 0;
            if (!FindTagEnd(xml, tag, length, &end)) {
                *truncated = true;
                *cursor = length;
                return false;
            }
            *cursor = end + 1;
            continue;
        }
        std::size_t i = tag + 1;
        const std::size_t begin = i;
        while (i < length && IsTagNameChar(xml[i])) {
            ++i;
        }
        std::size_t end = 0;
        if (!FindTagEnd(xml, tag, length, &end)) {
            *truncated = true;
            *cursor = length;
            return false;
        }
        *nameStart = begin;
        *nameLength = i - begin;
        *tagEnd = end;
        *cursor = end + 1;
        return true;
    }
    return false;
}

bool TagMatches(const char* xml, std::size_t nameStart, std::size_t nameLength,
                const TagRule& rule) noexcept {
    return nameLength == rule.tagLength &&
           std::memcmp(xml + nameStart, rule.tag, rule.tagLength) == 0;
}

//: 共用解析：找 `file` 的根标签，然后按 `rules` 把每条识别到的标签写进 `out`（**含无名条目**，
//: `name == nullptr` 表示无名）。卡牌那条"显式负 id 跳过"由 `skipNegativeId` 打开。
//: 返回识别到的总数（**不受 capacity 限制**；超出 capacity 记在 `*overflow` 里，由调用方处置）。
std::uint32_t ParseTaggedFile(const char* xml, std::size_t length, ModContentFileKind file,
                              ModContentName* out, std::uint32_t capacity, bool skipNegativeId,
                              bool* malformed, std::uint32_t* skipped, std::uint32_t* overflow) noexcept {
    if (malformed != nullptr) {
        *malformed = false;
    }
    if (skipped != nullptr) {
        *skipped = 0;
    }
    if (overflow != nullptr) {
        *overflow = 0;
    }
    if (xml == nullptr || length == 0) {
        if (malformed != nullptr) {
            *malformed = true;
        }
        return 0;
    }

    std::uint32_t ruleCount = 0;
    const TagRule* rules = RulesFor(file, &ruleCount);
    std::size_t rootLength = 0;
    const char* root = RootNameFor(file, &rootLength);

    // UTF-8 BOM（模组把文件存成"带 BOM"很常见）—— 不跳过的话根标签会被判缺失。
    std::size_t cursor = 0;
    if (length >= 3 && static_cast<unsigned char>(xml[0]) == 0xEF &&
        static_cast<unsigned char>(xml[1]) == 0xBB && static_cast<unsigned char>(xml[2]) == 0xBF) {
        cursor = 3;
    }

    // ① 找根标签（必须是本文件的根，否则判坏 —— 防止把别的文件喂错）。
    std::size_t nameStart = 0;
    std::size_t nameLength = 0;
    std::size_t tagEnd = 0;
    bool truncated = false;
    bool rootFound = false;
    while (NextTag(xml, length, &cursor, &nameStart, &nameLength, &tagEnd, &truncated)) {
        if (nameLength == rootLength && std::memcmp(xml + nameStart, root, rootLength) == 0) {
            rootFound = true;
            break;
        }
        if (tagEnd + 1 > length) {
            break;
        }
    }
    if (truncated || !rootFound) {
        if (malformed != nullptr) {
            *malformed = true;  // 不是本文件的形状 / 根标签截断
        }
        return 0;
    }

    // ② 根之下的所有识别标签。
    std::uint32_t stored = 0;
    std::uint32_t skipCount = 0;
    std::uint32_t over = 0;
    while (NextTag(xml, length, &cursor, &nameStart, &nameLength, &tagEnd, &truncated)) {
        if (truncated) {
            if (malformed != nullptr) {
                *malformed = true;  // 标签截断
            }
            return 0;
        }
        const TagRule* matched = nullptr;
        for (std::uint32_t ruleIndex = 0; ruleIndex < ruleCount; ++ruleIndex) {
            if (TagMatches(xml, nameStart, nameLength, rules[ruleIndex])) {
                matched = &rules[ruleIndex];
                break;
            }
        }
        if (matched == nullptr) {
            continue;  // 不认识的标签：不占 id
        }
        // 卡牌：显式负 id ⇒ 引擎**整条跳过**（`0x3BEE08 tbnz w25,#0x1f`）。
        if (skipNegativeId) {
            const char* idText = nullptr;
            std::size_t idLength = 0;
            std::int32_t idValue = 0;
            if (ExtractAttribute(xml, nameStart, tagEnd, "id", 2, &idText, &idLength) &&
                ParseIntAttribute(idText, idLength, &idValue) && idValue < 0) {
                ++skipCount;
                continue;
            }
        }
        const char* value = nullptr;
        std::size_t valueLength = 0;
        // GetCardIdByName takes the HUD name; older cards without hud retain their name.
        const bool hasHud = matched->family == ModContentNameFamily::Card &&
            ExtractAttribute(xml, nameStart, tagEnd, "hud", 3, &value, &valueLength) &&
            valueLength > 0;
        if (!hasHud) {
            (void)ExtractAttribute(xml, nameStart, tagEnd, "name", 4, &value, &valueLength);
        }
        if (value != nullptr && valueLength > 0) {
            // 有名条目。
            if (out != nullptr && stored < capacity) {
                out[stored].family = matched->family;
                out[stored].name = value;
                out[stored].length = valueLength;
            } else {
                ++over;
            }
            ++stored;
        } else {
            // 无名条目：仍占一个 id（引擎照样 append），但不进表。
            if (out != nullptr && stored < capacity) {
                out[stored].family = matched->family;
                out[stored].name = nullptr;
                out[stored].length = 0;
            } else {
                ++over;
            }
            ++stored;
        }
    }
    // ★ `NextTag` 在"最后一个标签没闭合 `>`"时会**返回 false**（于是上面的 `while` 直接退出，
    //   循环体里那次 `truncated` 检查根本没机会跑）。必须在这里补一次，否则截断文件会被当成
    //   "零条目的好文件"静默混进来（不抛错、也不计入 malformed）。
    if (truncated) {
        if (malformed != nullptr) {
            *malformed = true;
        }
        return 0;
    }

    if (skipped != nullptr) {
        *skipped += skipCount;
    }
    if (overflow != nullptr) {
        *overflow += over;
    }
    return stored;
}

//: 把一条名字存进池与条目表；存不下返回 false（并计一次溢出）。
bool StoreName(ModContentNameFamily family, const char* name, std::size_t length,
               std::int32_t id) noexcept {
    if (g_EntryCount >= kMaxEntries || g_NameUsed + length + 1 > kMaxNameBytes) {
        ++g_Stats.capacityOverflow;
        return false;
    }
    const std::uint32_t offset = g_NameUsed;
    std::memcpy(g_NamePool + offset, name, length);
    g_NamePool[offset + length] = '\0';
    g_NameUsed += static_cast<std::uint32_t>(length) + 1;
    g_Entries[g_EntryCount].nameOffset = offset;
    g_Entries[g_EntryCount].id = id;
    g_Entries[g_EntryCount].family = family;
    ++g_EntryCount;
    return true;
}

std::uint32_t Ingest(ModContentFileKind file, const char* modKey, const char* xml,
                     std::size_t length) noexcept {
    // 幂等键不能为空 —— 没有键就无法保证"同名模组喂两次不追加两次"，宁可不加。
    if (modKey == nullptr || modKey[0] == '\0') {
        ++g_Stats.malformedFiles;
        return 0;
    }
    // ★ 幂等：同一个 `(modKey, 文件别)` 只接受第一次调用（键表满也不能破例 —— 那时宁可不加）。
    const auto fileIndex = static_cast<std::uint8_t>(file);
    for (std::uint32_t i = 0; i < g_ModKeyCount; ++i) {
        if (g_ModKeyFiles[i] == fileIndex && std::strcmp(g_ModKeys[i], modKey) == 0) {
            ++g_Stats.duplicateFiles;
            return 0;
        }
    }
    if (g_ModKeyCount >= kMaxModKeys) {
        ++g_Stats.capacityOverflow;
        return 0;
    }
    const std::size_t keyLength = std::strlen(modKey);
    if (keyLength + 1 > kMaxModKeyLength) {
        ++g_Stats.capacityOverflow;
        return 0;
    }
    std::memcpy(g_ModKeys[g_ModKeyCount], modKey, keyLength + 1);
    g_ModKeyFiles[g_ModKeyCount] = fileIndex;
    ++g_ModKeyCount;
    ++g_Stats.fedFiles;

    ModContentName names[kMaxEntriesPerFile];
    bool malformed = false;
    std::uint32_t skipCount = 0;
    std::uint32_t overflow = 0;
    const bool skipNegativeId = file == ModContentFileKind::PocketItems;
    const std::uint32_t count =
        ParseTaggedFile(xml, length, file, names, kMaxEntriesPerFile, skipNegativeId, &malformed,
                        &skipCount, &overflow);
    g_Stats.skippedEntries += skipCount;
    if (malformed) {
        ++g_Stats.malformedFiles;
        return 0;  // 坏文件 ⇒ 跳过该模组（不追加、不打乱别的条目的位置）
    }
    if (overflow > 0) {
        // ★ 一份 xml 里识别到 > `kMaxEntriesPerFile` 条：分类信息已经装不下 ⇒ **整份跳过**
        //   （宁可漏加也不"半途消费一部分 id" —— 后者会让后面的条目整体错位、静默错）。
        g_Stats.capacityOverflow += overflow;
        ++g_Stats.malformedFiles;
        return 0;
    }

    std::uint32_t appended = 0;
    for (std::uint32_t index = 0; index < count; ++index) {
        const auto familyIndex = static_cast<std::size_t>(names[index].family);
        const std::int32_t id = g_NextId[familyIndex];
        ++g_NextId[familyIndex];  // ★ 无论存没存，都占一个 id（与引擎"往向量里追加一格"一致）
        ++g_Stats.consumedIds;
        if (names[index].name == nullptr) {
            ++g_Stats.unnamedEntries;  // 占 id 但不进表
            continue;
        }
        if (StoreName(names[index].family, names[index].name, names[index].length, id)) {
            ++appended;
        }
    }
    g_Stats.stored += appended;
    return appended;
}

} // namespace

std::uint32_t ParseModItemsXml(const char* xml, std::size_t length, ModContentName* out,
                               std::uint32_t capacity, bool* malformed,
                               std::uint32_t* skipped) noexcept {
    std::uint32_t overflow = 0;
    return ParseTaggedFile(xml, length, ModContentFileKind::Items, out, capacity, false, malformed,
                           skipped, &overflow);
}

std::uint32_t ParseModPocketItemsXml(const char* xml, std::size_t length, ModContentName* out,
                                     std::uint32_t capacity, bool* malformed,
                                     std::uint32_t* skipped) noexcept {
    std::uint32_t overflow = 0;
    return ParseTaggedFile(xml, length, ModContentFileKind::PocketItems, out, capacity, true,
                           malformed, skipped, &overflow);
}

std::uint32_t IngestModContentXml(ModContentFileKind file, const char* modKey, const char* xml,
                                  std::size_t length) noexcept {
    return Ingest(file, modKey, xml, length);
}

std::int32_t LookupModContentName(ModContentNameFamily family, const char* name,
                                  std::size_t length) noexcept {
    if (name == nullptr || length == 0) {
        return -1;
    }
    for (std::uint32_t i = 0; i < g_EntryCount; ++i) {
        if (g_Entries[i].family != family) {
            continue;
        }
        const char* const candidate = g_NamePool + g_Entries[i].nameOffset;
        if (std::strlen(candidate) == length && std::memcmp(candidate, name, length) == 0) {
            return g_Entries[i].id;
        }
    }
    return -1;  // 未命中：与静态表同口径（契约这几条找不到都是 -1）
}

const ModContentNameStats& ModContentNameStatistics() noexcept {
    return g_Stats;
}

void NoteModContentNameReadFailure() noexcept {
    ++g_Stats.readFailures;
}

void ClearModContentNames() noexcept {
    std::memset(g_NamePool, 0, sizeof(g_NamePool));
    g_NameUsed = 0;
    std::memset(g_Entries, 0, sizeof(g_Entries));
    g_EntryCount = 0;
    std::memset(g_ModKeys, 0, sizeof(g_ModKeys));
    std::memset(g_ModKeyFiles, 0, sizeof(g_ModKeyFiles));
    g_ModKeyCount = 0;
    for (std::size_t i = 0; i < static_cast<std::size_t>(ModContentNameFamily::Count); ++i) {
        g_NextId[i] = kModContentNameIdBase[i];
    }
    g_Stats = {};
}

void ResetModContentNamesForTests() noexcept { ClearModContentNames(); }

} // namespace isaac::runtime
