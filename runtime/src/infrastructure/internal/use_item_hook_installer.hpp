#pragma once
#include "ports/hook_port.hpp"
namespace isaac::runtime {
bool TryInstallUseItemNativeBoundaries(const HookTarget&) noexcept;
struct UseItemBoundaryInstallState {std::uintptr_t base{};std::uint32_t installed{},failure{};};
extern "C" UseItemBoundaryInstallState g_UseItemBoundaryInstallState;
}
