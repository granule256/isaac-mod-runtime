#include "infrastructure/internal/player_damage_hook_installer.hpp"
#include "player_damage_internal_hook.hpp"
#include "player_damage_boundary_layout.hpp"
#include "lua_runtime.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"

namespace isaac::runtime {
extern "C" { PlayerDamageBoundaryInstallState g_PlayerDamageBoundaryInstallState{}; }

bool TryInstallPlayerDamageBoundary(const HookTarget& target) noexcept {
    namespace layout = player_damage_boundary;
    auto& state = g_PlayerDamageBoundaryInstallState;
    if (state.base != 0)
        return state.base == target.base && state.installed == 1 && state.failure == 0;
    if (target.base == 0 || target.buildId != layout::kBuildId ||
        target.codeSize < layout::kVeneer + 16 || target.base > UINTPTR_MAX - target.codeSize ||
        !engine_memory::EngineMemoryReadable(target.base + 0x40, layout::kBuildId.size()) ||
        !engine_memory::EngineMemoryReadable(target.base + layout::kFunction, layout::kLength) ||
        !engine_memory::EngineMemoryReadable(target.base + layout::kAstralPlt, layout::kAstralPltGuard.size()) ||
        !engine_memory::EngineMemoryReadable(target.base + layout::kVeneer, 16) ||
        !layout::ImageMatches(static_cast<const std::uint8_t*>(engine_memory::AsObject(target.base)),
                              target.codeSize)) {
        state.failure = static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);
        return false;
    }
    // Verify the whole original function before its entry relay is installed.
    // This immutable native binding is published before the source BL changes.
    static PlayerDamageNativeBindings native{};
    native.tryEndAstralProjection = engine_call::AsFunction<bool (*)(void*)>(target.base + layout::kAstralPlt);
    native.dispatch = LuaRuntime::DispatchEntityTakeDamage;
    relay::InternalHookBinding binding{};
    binding.callback = PlayerDamageInternalCallback;
    binding.user = &native;
    binding.resumes[0] = target.base + layout::kAllow;
    binding.resumes[1] = target.base + layout::kCancel;
    binding.resumeCount = 2;
    binding.scratch = relay::InternalScratchPolicy::ProvedDeadX16;
    state.base = target.base;
    const auto failure = relay::TryInstallInternalHook(binding,
        {target.base + layout::kSource, layout::kOriginal}, target.base + layout::kVeneer);
    state.failure = static_cast<std::uint32_t>(failure);
    if (failure != relay::InternalHookFailure::None) return false;
    state.installed = 1;
    return true;
}

} // namespace isaac::runtime
