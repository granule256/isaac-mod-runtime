#pragma once

#include "ports/hook_port.hpp"

namespace isaac::runtime {
Status InstallNativeRestartInputHook(const HookTarget& target) noexcept;
} // namespace isaac::runtime
