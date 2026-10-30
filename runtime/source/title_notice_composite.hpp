#pragma once
#include <cstdint>

namespace isaac::runtime::notice {
// Final MenuManager foreground ANM2::Render returns here, before either branch
// of the render-target option. Keep every other sprite caller untouched.
inline constexpr std::uintptr_t kMenuForegroundReturnOffset = 0x3FEB5C;
template<class Draw>
void CompositeAfterForeground(std::uintptr_t caller, std::uintptr_t expected, Draw draw) noexcept {
    if (expected != 0 && caller == expected) draw();
}
}
