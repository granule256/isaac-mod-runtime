#pragma once

#include <algorithm>
#include <cstdint>
#include <limits>
#include <unordered_map>

namespace isaac::runtime::innate_collectibles {

// REPENTOGON 1.0.12e keeps innate copies outside the real inventory. MGO
// restores its persistent copies in MC_POST_GAME_STARTED on a continued run.
inline std::unordered_map<std::uintptr_t,
                          std::unordered_map<std::int32_t, std::int32_t>> g_Items;

inline std::int32_t Count(std::uintptr_t player, std::int32_t item) noexcept {
    if (g_Items.empty()) return 0;
    const auto owner = g_Items.find(player);
    if (owner == g_Items.end()) return 0;
    const auto found = owner->second.find(item);
    return found == owner->second.end() ? 0 : found->second;
}

inline void Change(std::uintptr_t player, std::int32_t item, std::int32_t amount) {
    const auto next = std::clamp<std::int64_t>(
        static_cast<std::int64_t>(Count(player, item)) + amount, 0,
        std::numeric_limits<std::int32_t>::max());
    if (next > 0) {
        g_Items[player][item] = static_cast<std::int32_t>(next);
    } else if (const auto owner = g_Items.find(player); owner != g_Items.end()) {
        owner->second.erase(item);
        if (owner->second.empty()) g_Items.erase(owner);
    }
}

inline std::int32_t EffectiveCount(std::uintptr_t player, std::int32_t item,
                                   std::int32_t native, bool ignore) noexcept {
    if (ignore) return native;
    const auto value = static_cast<std::int64_t>(native) + Count(player, item);
    return static_cast<std::int32_t>(std::min<std::int64_t>(
        value, std::numeric_limits<std::int32_t>::max()));
}

inline bool EffectiveHas(std::uintptr_t player, std::int32_t item,
                         bool native, bool ignore) noexcept {
    return native || (!ignore && Count(player, item) > 0);
}

inline void ResetPlayer(std::uintptr_t player) noexcept {
    if (!g_Items.empty()) g_Items.erase(player);
}
inline void Reset() noexcept { g_Items.clear(); }

}  // namespace isaac::runtime::innate_collectibles
