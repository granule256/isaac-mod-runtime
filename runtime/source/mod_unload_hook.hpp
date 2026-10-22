#pragma once
#include "ports/hook_port.hpp"
namespace isaac::runtime {
Status InstallModUnloadPointerHook(const HookTarget&) noexcept;
}
