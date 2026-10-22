#pragma once
#include <cstdint>
namespace isaac::runtime {
bool InstallShaderScreenHook(std::uintptr_t base) noexcept;
}
