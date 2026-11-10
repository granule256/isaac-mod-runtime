#pragma once
#include "ports/hook_port.hpp"
namespace isaac::runtime {
bool TryInstallSpeedCacheBoundary(const HookTarget&) noexcept;
struct SpeedCacheBoundaryInstallState {
 std::uintptr_t base{};
 std::uint32_t installed{},failure{};
};
extern "C" SpeedCacheBoundaryInstallState g_SpeedCacheBoundaryInstallState;
}
