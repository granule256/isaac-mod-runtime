#pragma once

#include <array>
#include <cstdint>

namespace isaac::runtime {

inline constexpr std::uint32_t kLuaRestartAction = 18;
// Game::ProcessInput reads these four buttons for the platform restart command.
inline constexpr std::array<std::uint32_t, 4> kNativeRestartButtons{8, 11, 10, 13};

inline bool NativeRestartChordHeld(const bool* buttons) noexcept {
    for (const auto button : kNativeRestartButtons)
        if (!buttons[button]) return false;
    return true;
}

inline bool NativeRestartChordButton(std::uint32_t button) noexcept {
    for (const auto component : kNativeRestartButtons)
        if (component == button) return true;
    return false;
}

} // namespace isaac::runtime
