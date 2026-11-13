#pragma once

// Source-backed records for the REPENTOGON XMLData facade.
//
// This is deliberately a data-only layer: it parses the XML files that the
// runtime already receives, applies the XMLData ID/order rules, and exposes
// indexed record views. It does not touch the engine or the Lua state.

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace isaac::runtime::xml_data {

// Values are the public XMLNode enum values from the pinned REPENTOGON
// snapshot. The store currently populates Entity, Challenge, Backdrop and GiantBook.
enum class XmlNodeType : int {
    Mod = 0,
    Entity = 1,
    Player = 2,
    Item = 3,
    Trinket = 4,
    Pill = 5,
    Card = 6,
    Music = 7,
    Sound = 8,
    Challenge = 9,
    ItemPool = 10,
    Nightmare = 11,
    Costume = 12,
    NullCostume = 13,
    Wisp = 14,
    WispColor = 15,
    Curse = 16,
    Locust = 17,
    LocustColor = 18,
    BombCostume = 19,
    CraftingRecipe = 20,
    BossPool = 21,
    BossPortrait = 22,
    Cutscene = 23,
    Stage = 24,
    Backdrop = 25,
    Achievement = 26,
    GiantBook = 27,
    BossRushWave = 28,
    PlayerForm = 29,
    NullItem = 30,
    BossColor = 31,
    FxLayer = 32,
    FxParam = 33,
    FxRay = 34,
    Baby = 35,
};

// The XML roots currently ingested. The numeric values intentionally equal
// XmlNodeType values so the loading call can be explicit at its boundary.
enum class XmlDataFileKind : std::uint8_t {
    Entities = 1,
    Challenges = 9,
    Backdrops = 25,
    GiantBooks = 27,
};

struct XmlAttribute {
    std::string name;
    std::string value;
};

struct XmlChild {
    std::vector<XmlAttribute> attributes;
};

struct XmlChildGroup {
    std::string tag;
    std::vector<XmlChild> entries;
};

struct XmlRecord {
    int id{};
    std::vector<XmlAttribute> attributes;
    std::vector<XmlChildGroup> children;

    [[nodiscard]] const XmlAttribute* FindAttribute(const char* name) const noexcept {
        if (name == nullptr) return nullptr;
        for (auto it = attributes.rbegin(); it != attributes.rend(); ++it) {
            if (it->name == name) return &*it;
        }
        return nullptr;
    }

    [[nodiscard]] const XmlChildGroup* FindChildren(const char* tag) const noexcept {
        if (tag == nullptr) return nullptr;
        for (const auto& child : children) {
            if (child.tag == tag) return &child;
        }
        return nullptr;
    }
};

// Optional game-side translation hook. `category` is the StringTable category
// ("Entities" for entity names). Returning false leaves the raw value in place.
struct XmlNameTranslator {
    void* context{};
    bool (*translate)(void* context, const char* category, const char* key, char* output,
                      std::size_t capacity, std::size_t* length) noexcept{};
};

struct XmlDataStoreStats {
    std::uint32_t files{};
    std::uint32_t rejected_files{};
    std::uint32_t entities{};
    std::uint32_t challenges{};
    std::uint32_t backdrops{};
};

// Drops all records. The store is allocated lazily after this call.
void ResetXmlDataStore() noexcept;

// Parses one complete XML document and commits it only after the whole
// document is structurally valid. `is_content` selects the XMLData ID/order
// rules; `source_id` is written into every record as `sourceid`.
[[nodiscard]] bool IngestXmlDataFile(XmlDataFileKind kind, const char* source_id,
                                    bool is_content, const char* xml, std::size_t length,
                                    const XmlNameTranslator& translator = {}) noexcept;

[[nodiscard]] const XmlRecord* FindEntityByTypeVarSub(int type, int variant, int subtype,
                                                      bool strict) noexcept;
[[nodiscard]] const XmlRecord* FindEntryById(XmlNodeType type, int id) noexcept;
[[nodiscard]] const XmlRecord* FindGiantBookByName(const char* name) noexcept;
[[nodiscard]] const XmlRecord* FindEntryByOrder(XmlNodeType type, int order) noexcept;
[[nodiscard]] std::size_t CountEntries(XmlNodeType type) noexcept;
[[nodiscard]] const XmlDataStoreStats& Statistics() noexcept;

}  // namespace isaac::runtime::xml_data
