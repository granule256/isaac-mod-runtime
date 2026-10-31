#pragma once
#include <cstdint>

namespace isaac::runtime {
// Only the verified HUD call consumes the compatibility layer's effective lock.
// Native callers for room rewards, statistics and gameplay keep their result.
constexpr bool HudAchievementStatus(bool nativeStatus, std::uintptr_t caller,
                                    std::uintptr_t hudReturn, bool readOnly) noexcept {
    return nativeStatus || (hudReturn != 0 && caller == hudReturn && readOnly);
}
}
