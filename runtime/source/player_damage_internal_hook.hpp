#pragma once

#include "damage_context.hpp"
#include "relay/internal_hook.hpp"

namespace isaac::runtime {

using PlayerDamageValues = damage::Values;

struct PlayerDamageNativeBindings {
    bool (*tryEndAstralProjection)(void*){};
    // true cancels damage, matching DispatchEntityTakeDamage.
    bool (*dispatch)(std::uintptr_t, float, std::uint64_t, std::uintptr_t,
                     std::int32_t, std::int32_t){};
    // Preferred pre-dispatch entry once the runtime can apply table returns.
    bool (*dispatchPreValues)(PlayerDamageValues&){};
    // Called only after the original Player TakeDamage reports success.
    void (*dispatchPostValues)(const PlayerDamageValues&){};
};

// The NS player function does not preserve its countdown argument. Keep the
// accepted native values on the entry wrapper's stack until post dispatch.
using PlayerDamageCallScope = damage::CallScope;

// 0 resumes the original Astral Projection test; 1 takes the false epilogue.
std::uint32_t PlayerDamageInternalCallback(relay::InternalHookContext&,
                                           const void*) noexcept;

// Call after the original Player TakeDamage invocation. `succeeded` is the
// native return value; false discards the scope without posting.
void DispatchPlayerDamagePost(bool succeeded,
                              const PlayerDamageNativeBindings& bindings) noexcept;

} // namespace isaac::runtime
