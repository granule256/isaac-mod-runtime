#pragma once

#include <cstddef>
#include <cstdint>
#include <map>
#include <set>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace isaac::runtime::custom_cache {

// Parent integration contract:
// - Port::evaluate is the 1224 additive dispatcher (lowercase tag, player,
//   current value); callback registration/filtering/order stay in the parent.
// - QueueTags is used by Lua and deferred item events. Immediate updates from
//   native collectible events evaluate the supplied tags directly.
// - EvaluateItems is called before native Entity_Player::EvaluateItems; apply
//   the returned cacheFlags before running native code.
// - Port::maximumsChanged makes a changed cap available to native readers
//   before the next callback runs.

inline constexpr std::uint32_t kEvaluateCustomCacheCallback = 1224;
inline constexpr std::uint32_t kCacheAll = 0xFFFF;
inline constexpr std::uint32_t kCacheDamage = 1;
inline constexpr std::uint32_t kCacheFireDelay = 2;
inline constexpr std::uint32_t kCacheShotSpeed = 4;
inline constexpr std::uint32_t kCacheRange = 8;
inline constexpr std::uint32_t kCacheSpeed = 16;
inline constexpr std::uint32_t kCacheStats =
    kCacheDamage | kCacheFireDelay | kCacheShotSpeed | kCacheRange | kCacheSpeed;

struct Maximums {
    std::int32_t maxCoins{99};
    std::int32_t maxKeys{99};
    std::int32_t maxBombs{99};
    bool coinsConfigured{};
    bool keysConfigured{};
    bool bombsConfigured{};
};

struct Port {
    void* user{};

    // Return true only when at least one 1224 listener supplied a numeric
    // replacement. The parent owns listener order and callback error policy.
    bool (*evaluate)(
        void* user, std::uintptr_t player, std::string_view tag,
        double value, double* replacement) noexcept{};

    // Supplies engine-sensitive defaults such as Deep Pockets' 999 max coins.
    double (*defaultValue)(
        void* user, std::uintptr_t player, std::string_view tag) noexcept{};

    void (*invalidateFamiliarMultipliers)(
        void* user, std::uintptr_t player) noexcept{};
    void (*healthTypeEnforced)(void* user, std::uintptr_t player) noexcept{};
    void (*maximumsChanged)(
        void* user, std::uintptr_t primaryPlayer, std::string_view tag,
        const Maximums& maximums) noexcept{};
};

struct Evaluation {
    std::string tag;
    std::uintptr_t player{};
    double previous{};
    double value{};
    bool changed{};
};

struct EvaluationBatch {
    std::vector<Evaluation> evaluations;
    std::uint32_t cacheFlags{};
    bool requiresEvaluateItems{};
    bool shouldEvaluateCache{};
};

enum class ItemKind : std::uint8_t {
    Collectible,
    Trinket,
    Null,
};

class Store final {
public:
    Store();

    void Reset();
    void ResetPlayers() noexcept;

    bool RegisterTag(std::string_view tag);
    std::size_t RegisterTags(std::string_view spaceSeparated);
    std::size_t RegisterItemTags(
        ItemKind kind, std::int32_t id, std::string_view spaceSeparated);
    bool RemoveItemTags(ItemKind kind, std::int32_t id);
    const std::set<std::string>& ItemTags(ItemKind kind, std::int32_t id) const;

    const std::set<std::string>& KnownTags() const noexcept { return knownTags_; }

    void QueueTags(std::uintptr_t player, std::span<const std::string_view> tags);

    // The native item path evaluates only these tags on immediate events.
    EvaluationBatch AddCustomCacheTag(
        std::span<const std::string_view> tags, bool immediate,
        std::uintptr_t player, std::uintptr_t primaryPlayer,
        const Port& port);

    // Matches the REPENTOGON pre-EvaluateItems phase: CACHE_ALL enqueues every
    // known XML tag, then the copied pending set is evaluated and cleared.
    EvaluationBatch EvaluateItems(
        std::uintptr_t player, std::uint32_t cacheFlags,
        std::uintptr_t primaryPlayer, const Port& port);
    EvaluationBatch TriggerItemTags(
        std::uintptr_t player, ItemKind kind, std::int32_t id,
        bool immediate, std::uintptr_t primaryPlayer, const Port& port);

    double GetCustomCacheValue(
        std::uintptr_t player, std::string_view tag, const Port& port) const;
    std::int32_t GetConsumableMaximum(
        std::uintptr_t player, std::string_view tag, const Port& port) const;

    bool HasPending(std::uintptr_t player) const;
    bool HasWork(std::uintptr_t player) const;
    bool ShouldEvaluateCache(std::uintptr_t player) const;
    Maximums GetMaximums() const noexcept { return maximums_; }

private:
    struct PlayerState {
        std::set<std::string> pending;
        std::map<std::string, double, std::less<>> results;
        std::uint32_t cacheFlags{};
        bool requiresEvaluateItems{};
        bool shouldEvaluateCache{};
        std::uint64_t deferredEpoch{};
    };

    Evaluation EvaluateOne(
        std::uintptr_t player, std::uintptr_t primaryPlayer,
        std::string_view tag, const Port& port, EvaluationBatch* batch);

    double DefaultValue(
        std::uintptr_t player, std::string_view tag, const Port& port) const;

    static bool IsGlobalMaximum(std::string_view tag) noexcept;

    std::set<std::string> knownTags_;
    const std::set<std::string> emptyItemTags_;
    std::map<std::uintptr_t, PlayerState> players_;
    struct ItemKey {
        ItemKind kind{ItemKind::Collectible};
        std::int32_t id{};
        friend bool operator<(const ItemKey& left, const ItemKey& right) noexcept {
            if (left.kind != right.kind) return left.kind < right.kind;
            return left.id < right.id;
        }
    };
    std::map<ItemKey, std::set<std::string>> itemTags_;
    Maximums maximums_{};
};

[[nodiscard]] std::string NormalizeTag(std::string_view tag);
[[nodiscard]] std::int32_t ClampMaximum(double value) noexcept;

}  // namespace isaac::runtime::custom_cache
