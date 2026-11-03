#pragma once

#include "relay/internal_hook.hpp"

namespace isaac::runtime {

struct PlayerDamageNativeBindings {
    bool (*tryEndAstralProjection)(void*){};
    // true cancels damage, matching DispatchEntityTakeDamage.
    bool (*dispatch)(std::uintptr_t, float, std::uint64_t, std::uintptr_t,
                     std::int32_t, std::int32_t){};
};

// The NS player function does not preserve its countdown argument. Keep it on
// the entry wrapper's stack until the matching native call returns.
class PlayerDamageCallScope {
public:
    PlayerDamageCallScope(std::uintptr_t player, std::uintptr_t source,
                          std::int32_t countdown) noexcept;
    ~PlayerDamageCallScope() noexcept;
    PlayerDamageCallScope(const PlayerDamageCallScope&) = delete;
    PlayerDamageCallScope& operator=(const PlayerDamageCallScope&) = delete;
    PlayerDamageCallScope(PlayerDamageCallScope&&) = delete;
    PlayerDamageCallScope& operator=(PlayerDamageCallScope&&) = delete;

private:
    PlayerDamageCallScope* previous_;
    std::uintptr_t player_, source_;
    std::int32_t countdown_;
    friend std::uint32_t PlayerDamageInternalCallback(relay::InternalHookContext&,
                                                     const void*) noexcept;
};

// 0 resumes the original Astral Projection test; 1 takes the false epilogue.
std::uint32_t PlayerDamageInternalCallback(relay::InternalHookContext&,
                                           const void*) noexcept;

} // namespace isaac::runtime
