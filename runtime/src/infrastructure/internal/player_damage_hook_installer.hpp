#pragma once

#include "ports/hook_port.hpp"

namespace isaac::runtime {
bool TryInstallPlayerDamageBoundary(const HookTarget&) noexcept;
struct PlayerDamageBoundaryInstallState {
    std::uintptr_t base{};
    std::uint32_t installed{}, failure{};
};
extern "C" PlayerDamageBoundaryInstallState g_PlayerDamageBoundaryInstallState;
} // namespace isaac::runtime
