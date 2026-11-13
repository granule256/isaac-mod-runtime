#pragma once

// Compatibility bridge for menu-only mods that poll PC keyboard identities while
// the native CHARACTER menu is active. The current native game/input port does
// not register a keyboard backend, so these reads otherwise return false. This
// is a statement about the current input port, not a hardware impossibility.
//
// Scope is deliberately narrow:
//   * Manager render scene 1 (main menu), never gameplay scene 2.
//   * MenuManager active menu 5 (MainMenuType.CHARACTER).
//   * PC controllerId 0 (keyboard) only.
//   * Left/right stick clicks and D-pad left/right only.
//
// input_api.cpp queries the existing "any real controller" aggregate sample for
// the mapped button; this header owns only the pure identity mapping.

#include <cstdint>

namespace isaac::runtime::character_menu_keyboard_bridge {

inline constexpr std::uintptr_t kMenuManagerGlobalSlotOffset = 0xAAD1B0;
inline constexpr std::uintptr_t kMenuManagerActiveMenuOffset = 0x38;
inline constexpr std::uint32_t kManagerMenuScene = 1;
inline constexpr std::int32_t kCharacterMenu = 5;

inline constexpr std::int64_t kPcKeyboardControllerId = 0;

// PC keyboard enum values used by the author mod.
inline constexpr std::int64_t kKeyLeft = 263;
inline constexpr std::int64_t kKeyRight = 262;
inline constexpr std::int64_t kKeyLeftControl = 341;
inline constexpr std::int64_t kKeyRightControl = 345;
inline constexpr std::int64_t kKeyU = 85;

// PC Controller values 0..15 are shared with the native device numbering.
// Values here are confirmed by the generated Controller enum and the input
// compatibility evidence, not inferred from GLFW keyboard constants.
inline constexpr std::uint32_t kButtonDpadLeft = 0;
inline constexpr std::uint32_t kButtonDpadRight = 1;
inline constexpr std::uint32_t kButtonLeftStick = 10;
inline constexpr std::uint32_t kButtonRightStick = 13;

struct KeyboardMapping {
    bool mapped{};
    std::uint32_t controller_button{};
};

[[nodiscard]] constexpr bool IsCharacterMenuContext(
    std::uint32_t manager_scene, std::int32_t active_menu) noexcept {
    return manager_scene == kManagerMenuScene && active_menu == kCharacterMenu;
}

[[nodiscard]] constexpr KeyboardMapping MapKeyboardIdentity(
    std::int64_t keyboard, std::int64_t controller_id) noexcept {
    if (controller_id != kPcKeyboardControllerId) return {};
    switch (keyboard) {
        case kKeyLeft:
            return {true, kButtonDpadLeft};
        case kKeyRight:
            return {true, kButtonDpadRight};
        case kKeyLeftControl:
        case kKeyRightControl:
            return {true, kButtonLeftStick};
        case kKeyU:
            return {true, kButtonRightStick};
        default:
            return {};
    }
}

}  // namespace isaac::runtime::character_menu_keyboard_bridge
