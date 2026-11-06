#pragma once
#include "ports/hook_port.hpp"

namespace isaac::runtime {
Status InstallModItemPoolPointerHook(const HookTarget&) noexcept;
}
