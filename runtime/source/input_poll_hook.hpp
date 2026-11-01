#pragma once

#include "ports/hook_port.hpp"

namespace isaac::runtime {
using NativeInputPollFn = void (*)(void*);
Status InstallNativeInputPollHook(const HookTarget&) noexcept;
} // namespace isaac::runtime
