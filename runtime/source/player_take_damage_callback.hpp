#pragma once

#include <cstdint>

namespace isaac::runtime {
class CallbackDispatcher;
}

namespace isaac::runtime::player_take_damage {

// REPENTOGON ModCallbacks.MC_PRE_PLAYER_TAKE_DMG.
inline constexpr std::uint32_t kPrePlayerTakeDamageCallbackId = 1008;

// The upstream wrapper short-circuits on the first non-nil result and cancels
// only when that result is literal boolean false. A failed protected callback
// invocation behaves like nil and lets the original TakeDamage run.
[[nodiscard]] bool DispatchPrePlayerTakeDamage(
    CallbackDispatcher& dispatcher, std::int32_t playerVariant) noexcept;

}  // namespace isaac::runtime::player_take_damage

namespace LuaRuntime {

// Runs at Entity_Player::TakeDamage entry, before native invincibility,
// shield/Holy Mantle and callback 11. Returns true only for a literal false
// callback result, which suppresses the original method.
[[nodiscard]] bool DispatchPrePlayerTakeDamage(
    std::uintptr_t player, float damage, std::uint64_t damageFlags,
    std::uintptr_t sourceRef, std::int32_t damageCountdown) noexcept;

}  // namespace LuaRuntime
