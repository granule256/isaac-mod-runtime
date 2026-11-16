#pragma once

#include "program/xml_data_store.hpp"

#include <array>
#include <cerrno>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>

namespace isaac::runtime::custom_item_pool {

// Native ItemPool::PoolItem (24 bytes on the pinned Switch build).
struct NativePoolItem {
    std::int32_t itemId;
    float initialWeight;
    float weight;
    float decreaseBy;
    float removeOn;
    std::uint8_t isSpecial;
    std::uint8_t isUnlocked;
    std::uint16_t reserved;
};

// The prefix of ItemPool::Pool consumed by ItemPool::pick_collectible.
// The native picker reads only totalWeight, begin and end; capacity is kept
// so the object remains a truthful container view for diagnostics.
struct NativePool {
    float totalWeight;
    std::uint32_t reserved0;
    NativePoolItem* begin;
    NativePoolItem* end;
    NativePoolItem* capacity;
    std::array<std::uint8_t, 16> rng1;
    std::array<std::uint8_t, 16> rng2;
    std::uint32_t bibleUpgrade;
    std::uint32_t reserved1;
};

// The native instruction before Pool is `smaddl x23, poolId, 0x48, itemPool`;
// the following pre-indexed load reads totalWeight at x23+8 and advances x23
// to Pool. Keeping this prefix makes the substitute pointer ABI-identical.
struct NativePoolEntry {
    std::uint64_t prefix;
    NativePool pool;
};

static_assert(sizeof(NativePoolItem) == 0x18);
static_assert(offsetof(NativePoolItem, itemId) == 0x00);
static_assert(offsetof(NativePoolItem, initialWeight) == 0x04);
static_assert(offsetof(NativePoolItem, weight) == 0x08);
static_assert(offsetof(NativePoolItem, decreaseBy) == 0x0C);
static_assert(offsetof(NativePoolItem, removeOn) == 0x10);
static_assert(offsetof(NativePoolItem, isSpecial) == 0x14);
static_assert(offsetof(NativePoolItem, isUnlocked) == 0x15);
static_assert(sizeof(NativePool) == 0x48);
static_assert(offsetof(NativePool, totalWeight) == 0x00);
static_assert(offsetof(NativePool, begin) == 0x08);
static_assert(offsetof(NativePool, end) == 0x10);
static_assert(offsetof(NativePool, capacity) == 0x18);
static_assert(offsetof(NativePool, rng1) == 0x20);
static_assert(offsetof(NativePool, rng2) == 0x30);
static_assert(offsetof(NativePool, bibleUpgrade) == 0x40);
static_assert(sizeof(NativePoolEntry) == 0x50);
static_assert(offsetof(NativePoolEntry, pool) == 0x08);

struct Bindings {
    void* context{};
    std::int32_t (*resolveName)(void* context, const char* name,
                                std::size_t length){};
    bool (*inspectId)(void* context, std::int32_t id, bool* isSpecial){};
};

// Loads the custom pool from XMLData on first use and returns the exact Pool
// entry expected by native GetCollectible. The native outer pipeline remains
// responsible for RNG, pick, discounts, fallback and decrease/removeOn.
[[nodiscard]] NativePoolEntry* AcquireNativePool(
    void* itemPool, std::uint32_t poolId, const Bindings& bindings) noexcept;

// Must be called after XMLData reset/reingest. Per-pool weight edits are
// intentionally discarded at that boundary because the XML source changed.
void ResetState() noexcept;

#if !defined(__SWITCH__)
// Host integration seam. Production always builds the bindings from the
// current engine and runtime name tables in remaining_api.cpp.
void SetHostBindingsForTests(const Bindings& bindings) noexcept;
[[nodiscard]] const Bindings* HostBindingsForTests() noexcept;
#endif

namespace detail {

constexpr std::uint32_t kMaxPools = 64;
constexpr std::uint32_t kMaxItems = 4096;
constexpr std::uint32_t kMaxItemsPerPool = 1024;

struct PoolState {
    std::uint32_t id;
    std::uint32_t firstItem;
    std::uint32_t itemCount;
    NativePoolEntry entry;
};

inline PoolState g_pools[kMaxPools]{};
inline std::uint32_t g_poolCount = 0;
inline NativePoolItem g_items[kMaxItems]{};
inline std::uint32_t g_itemCount = 0;
inline void* g_ownerItemPool = nullptr;

#if !defined(__SWITCH__)
inline Bindings g_hostBindings{};
inline bool g_hasHostBindings = false;
#endif

inline bool ParseInt(const char* text, std::int32_t* value) noexcept {
    if (text == nullptr || value == nullptr || text[0] == '\0') {
        return false;
    }
    char* end = nullptr;
    errno = 0;
    const long parsed = std::strtol(text, &end, 10);
    if (errno == ERANGE || end == text || *end != '\0' ||
        parsed < std::numeric_limits<std::int32_t>::min() ||
        parsed > std::numeric_limits<std::int32_t>::max()) {
        return false;
    }
    *value = static_cast<std::int32_t>(parsed);
    return true;
}

inline bool ParseFloat(const char* text, float* value) noexcept {
    if (text == nullptr || value == nullptr || text[0] == '\0') {
        return false;
    }
    char* end = nullptr;
    errno = 0;
    const float parsed = std::strtof(text, &end);
    if (errno == ERANGE || end == text || *end != '\0' || !std::isfinite(parsed)) {
        return false;
    }
    *value = parsed;
    return true;
}

inline const char* AttributeValue(const xml_data::XmlChild& item,
                                  const char* name) noexcept {
    if (name == nullptr) {
        return nullptr;
    }
    for (const auto& attribute : item.attributes) {
        if (attribute.name == name) {
            return attribute.value.c_str();
        }
    }
    return nullptr;
}

inline PoolState* FindPool(std::uint32_t poolId) noexcept {
    for (std::uint32_t index = 0; index < g_poolCount; ++index) {
        if (g_pools[index].id == poolId) {
            return &g_pools[index];
        }
    }
    return nullptr;
}

inline bool ResolveItemId(const xml_data::XmlChild& child,
                          const Bindings& bindings, std::int32_t* itemId,
                          bool* isSpecial) noexcept {
    if (itemId == nullptr || isSpecial == nullptr ||
        bindings.inspectId == nullptr) {
        return false;
    }

    const char* idText = AttributeValue(child, "id");
    if (idText != nullptr) {
        std::int32_t parsed = 0;
        if (!ParseInt(idText, &parsed) || parsed < 0) {
            return false;
        }
        *itemId = parsed;
        return bindings.inspectId(bindings.context, parsed, isSpecial);
    }

    const char* name = AttributeValue(child, "name");
    if (name == nullptr || name[0] == '\0' || bindings.resolveName == nullptr) {
        return false;
    }
    const std::int32_t resolved =
        bindings.resolveName(bindings.context, name, std::strlen(name));
    if (resolved < 0) {
        return false;
    }
    *itemId = resolved;
    return bindings.inspectId(bindings.context, resolved, isSpecial);
}

inline bool LoadPool(const xml_data::XmlRecord& record,
                     const Bindings& bindings, PoolState** state) noexcept {
    if (state == nullptr || record.id < xml_data::kFirstCustomItemPoolId ||
        g_poolCount >= kMaxPools || g_itemCount >= kMaxItems) {
        return false;
    }
    const auto* items = record.FindChildren("item");
    const std::uint32_t available = kMaxItems - g_itemCount;
    const std::uint32_t count =
        items == nullptr ? 0 : static_cast<std::uint32_t>(items->entries.size());
    if (count > available || count > kMaxItemsPerPool) {
        return false;
    }

    const std::uint32_t first = g_itemCount;
    std::uint32_t loaded = 0;
    float totalWeight = 0.0F;
    if (items != nullptr) {
        for (const xml_data::XmlChild& child : items->entries) {
            std::int32_t itemId = 0;
            bool isSpecial = false;
            if (!ResolveItemId(child, bindings, &itemId, &isSpecial)) {
                continue;
            }

            float weight = 1.0F;
            float decreaseBy = 0.5F;
            float removeOn = 0.1F;
            const char* weightText = AttributeValue(child, "weight");
            const char* decreaseText = AttributeValue(child, "decreaseby");
            const char* removeText = AttributeValue(child, "removeon");
            if (weightText != nullptr) {
                static_cast<void>(ParseFloat(weightText, &weight));
            }
            if (decreaseText != nullptr) {
                static_cast<void>(ParseFloat(decreaseText, &decreaseBy));
            }
            if (removeText != nullptr) {
                static_cast<void>(ParseFloat(removeText, &removeOn));
            }
            if (!std::isfinite(weight) || !std::isfinite(decreaseBy) ||
                !std::isfinite(removeOn) || weight < 0.0F) {
                continue;
            }

            NativePoolItem& destination = g_items[first + loaded];
            destination = NativePoolItem{};
            destination.itemId = itemId;
            destination.initialWeight = weight;
            destination.weight = weight;
            destination.decreaseBy = decreaseBy;
            destination.removeOn = removeOn;
            destination.isSpecial = isSpecial ? 1U : 0U;
            totalWeight += weight;
            ++loaded;
        }
    }

    PoolState& added = g_pools[g_poolCount];
    added = PoolState{};
    added.id = record.id;
    added.firstItem = first;
    added.itemCount = loaded;
    NativePool& pool = added.entry.pool;
    pool.totalWeight = totalWeight;
    pool.begin = loaded == 0 ? nullptr : &g_items[first];
    pool.end = loaded == 0 ? nullptr : &g_items[first + loaded];
    pool.capacity = pool.end;
    ++g_poolCount;
    g_itemCount += loaded;
    *state = &added;
    return true;
}

inline bool EnsurePoolLoaded(std::uint32_t poolId, const Bindings& bindings,
                             PoolState** state) noexcept {
    if (state == nullptr) {
        return false;
    }
    if (PoolState* existing = FindPool(poolId)) {
        *state = existing;
        return true;
    }
    const auto* record = xml_data::FindEntryById(
        xml_data::XmlNodeType::ItemPool, static_cast<int>(poolId));
    if (record == nullptr || record->id != static_cast<int>(poolId) ||
        record->id < xml_data::kFirstCustomItemPoolId) {
        return false;
    }
    return LoadPool(*record, bindings, state);
}

}  // namespace detail

inline NativePoolEntry* AcquireNativePool(
    void* itemPool, std::uint32_t poolId, const Bindings& bindings) noexcept {
    if (itemPool == nullptr || bindings.inspectId == nullptr ||
        poolId < static_cast<std::uint32_t>(
                     xml_data::kFirstCustomItemPoolId)) {
        return nullptr;
    }
    if (detail::g_ownerItemPool != nullptr &&
        detail::g_ownerItemPool != itemPool) {
        ResetState();
    }
    detail::g_ownerItemPool = itemPool;

    detail::PoolState* pool = nullptr;
    if (!detail::EnsurePoolLoaded(poolId, bindings, &pool)) {
        return nullptr;
    }
    return &pool->entry;
}

inline void ResetState() noexcept {
    detail::g_poolCount = 0;
    detail::g_itemCount = 0;
    detail::g_ownerItemPool = nullptr;
}

#if !defined(__SWITCH__)
inline void SetHostBindingsForTests(const Bindings& bindings) noexcept {
    detail::g_hostBindings = bindings;
    detail::g_hasHostBindings = true;
}

inline const Bindings* HostBindingsForTests() noexcept {
    return detail::g_hasHostBindings ? &detail::g_hostBindings : nullptr;
}
#endif

}  // namespace isaac::runtime::custom_item_pool
