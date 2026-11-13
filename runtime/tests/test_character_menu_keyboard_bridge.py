"""Focused tests for the CHARACTER-menu keyboard compatibility bridge."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
SRC = ROOT / "runtime" / "src"


HARNESS = r'''
#include "application/callback/callback_dispatcher.hpp"
#include "interfaces/lua/input_api.hpp"
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"
#include "pc_ns_input_device_map.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

extern "C" {
#include <lauxlib.h>
}

namespace {

constexpr std::uintptr_t kMenuManagerSlot = 0xAAD1B0;
constexpr std::uintptr_t kMenuManagerState = 0x38;
constexpr std::uint32_t kMenuScene = 1;
constexpr std::int32_t kCharacterMenu = 5;

constexpr int kLeftControl = 341;
constexpr int kRightControl = 345;
constexpr int kKeyLeft = 263;
constexpr int kKeyRight = 262;
constexpr int kKeyU = 85;
constexpr int kKeySpace = 32;

std::vector<std::uint8_t> g_Module;
std::uintptr_t g_ManagerSlot{};
std::uintptr_t g_MenuSlot{};
std::array<std::uint8_t, 0x80> g_GameManager{};
std::array<std::uint8_t, 0x80> g_InputManager{};
std::array<std::uint8_t, 0x80> g_Menu{};
std::array<std::uint8_t, 0x40> g_TouchDevice{};
std::array<std::uint8_t, 0x40> g_PadDevice{};
std::array<std::uintptr_t, 2> g_DeviceTable{};
std::uint32_t g_Held{};
int g_Failures{};

void Check(bool condition, const char* label) {
    if (condition) return;
    std::printf("FAIL %s\n", label);
    ++g_Failures;
}

void StoreU32(void* base, std::uintptr_t offset, std::uint32_t value) {
    std::memcpy(static_cast<std::uint8_t*>(base) + offset, &value, sizeof(value));
}

void StoreWord(void* base, std::uintptr_t offset, std::uintptr_t value) {
    std::memcpy(static_cast<std::uint8_t*>(base) + offset, &value, sizeof(value));
}

bool FakeButtonPressed(void*, std::uint32_t button, std::uint32_t, void*) {
    return button < 32 && ((g_Held >> button) & 1U) != 0;
}

bool FakeActionPressed(void*, std::uint32_t, std::uint32_t, void*) {
    return false;
}

struct LuaInput {
    lua_State* state{};

    bool Query(const char* name, int key, int controller) const {
        lua_getglobal(state, "Input");
        lua_getfield(state, -1, name);
        lua_pushinteger(state, key);
        lua_pushinteger(state, controller);
        lua_pushboolean(state, 1);
        if (lua_pcall(state, 3, 1, 0) != LUA_OK) {
            std::printf("FAIL lua %s: %s\n", name, lua_tostring(state, -1));
            lua_pop(state, 2);
            ++g_Failures;
            return false;
        }
        const bool result = lua_toboolean(state, -1) != 0;
        lua_pop(state, 2);
        return result;
    }

    bool Pressed(int key, int controller = 0) const {
        return Query("IsButtonPressed", key, controller);
    }

    bool Triggered(int key, int controller = 0) const {
        return Query("IsButtonTriggered", key, controller);
    }
};

void AdvanceFrame() {
    g_ManagerSlot = 0;
    isaac::runtime::NativeFrameClock::MarkNativeFrame();
    g_ManagerSlot = reinterpret_cast<std::uintptr_t>(g_GameManager.data());
}

void SetContext(std::uint32_t scene, std::int32_t menu) {
    StoreU32(g_GameManager.data(), kManagerRenderSceneOffset, scene);
    StoreU32(g_Menu.data(), kMenuManagerState, static_cast<std::uint32_t>(menu));
}

}  // namespace

int main() {
    g_Module.assign(static_cast<std::size_t>(kMenuManagerSlot) + sizeof(std::uintptr_t), 0);
    g_ManagerSlot = 0;
    g_MenuSlot = reinterpret_cast<std::uintptr_t>(g_Menu.data());
    StoreWord(g_Module.data(), kGameManagerGlobalSlotOffset,
              reinterpret_cast<std::uintptr_t>(&g_ManagerSlot));
    StoreWord(g_Module.data(), kMenuManagerSlot,
              reinterpret_cast<std::uintptr_t>(&g_MenuSlot));
    StoreU32(g_TouchDevice.data(), kKageInputDeviceIdOffset,
             isaac::runtime::kNsTouchscreenDeviceId);
    StoreU32(g_PadDevice.data(), kKageInputDeviceIdOffset, 33U);
    g_DeviceTable[0] = reinterpret_cast<std::uintptr_t>(g_TouchDevice.data());
    g_DeviceTable[1] = reinterpret_cast<std::uintptr_t>(g_PadDevice.data());
    const auto begin = reinterpret_cast<std::uintptr_t>(g_DeviceTable.data());
    StoreWord(g_InputManager.data(), kKageInputDeviceVectorBeginOffset, begin);
    StoreWord(g_InputManager.data(), kKageInputDeviceVectorEndOffset,
              begin + 2 * sizeof(std::uintptr_t));
    // `TryReadSingleton` reads module+slot to get the slot, then slot to get the object.
    StoreWord(g_Module.data(), kGameManagerGlobalSlotOffset,
              reinterpret_cast<std::uintptr_t>(&g_ManagerSlot));
    StoreWord(g_Module.data(), kMenuManagerSlot,
              reinterpret_cast<std::uintptr_t>(&g_MenuSlot));
    StoreWord(g_Module.data(), kKageInputManagerSlotOffset,
              reinterpret_cast<std::uintptr_t>(g_InputManager.data()));
    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(g_Module.data()));
    LuaRuntime::SetInputButtonBindings(
        reinterpret_cast<std::uintptr_t>(&FakeButtonPressed), 0);
    LuaRuntime::SetInputBindings(
        reinterpret_cast<std::uintptr_t>(&FakeActionPressed), 0, 0);
    isaac::runtime::ResetInputEdgeState();

    lua_State* state = luaL_newstate();
    if (state == nullptr) return 2;
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachInputMethods(state));
    lua_setglobal(state, "Input");
    const LuaInput input{state};

    SetContext(kMenuScene, kCharacterMenu);

    // Establish a not-held history before the first edge.
    g_Held = 0;
    AdvanceFrame();
    Check(!input.Pressed(kLeftControl), "ctrl starts not held");

    // Left-stick click -> both PC Ctrl identities.
    g_Held = 1U << 10;
    AdvanceFrame();
    Check(input.Pressed(kLeftControl), "left stick click maps to left control");
    Check(input.Triggered(kLeftControl), "left stick click maps to left control edge");
    Check(input.Pressed(kRightControl), "left stick click maps to right control");
    Check(input.Triggered(kRightControl), "left stick click maps to right control edge");
    Check(!input.Pressed(kKeyU), "left stick click does not map to U");
    AdvanceFrame();
    Check(input.Pressed(kLeftControl), "ctrl stays held from live button state");
    Check(!input.Triggered(kLeftControl), "held ctrl has no second edge");

    // Right-stick click -> KEY_U (large-view toggle).
    g_Held = 0;
    AdvanceFrame();
    g_Held = 1U << 13;
    AdvanceFrame();
    Check(input.Pressed(kKeyU), "right stick click maps to KEY_U");
    Check(input.Triggered(kKeyU), "right stick click maps to KEY_U edge");
    Check(!input.Pressed(kLeftControl), "right stick does not map to ctrl");
    g_Held = 0;
    AdvanceFrame();
    Check(!input.Pressed(kKeyU), "releasing the stick clears the bridged held state");

    // D-pad left/right -> keyboard arrow identities.
    g_Held = 1U << 0;
    AdvanceFrame();
    Check(input.Pressed(kKeyLeft), "dpad left maps to KEY_LEFT");
    Check(input.Triggered(kKeyLeft), "dpad left maps to KEY_LEFT edge");
    Check(!input.Pressed(kKeyRight), "dpad left not KEY_RIGHT");
    g_Held = 1U << 1;
    AdvanceFrame();
    Check(input.Pressed(kKeyRight), "dpad right maps to KEY_RIGHT");
    Check(input.Triggered(kKeyRight), "dpad right maps to KEY_RIGHT edge");

    // Unsupported keyboard key and non-keyboard controller identity stay false.
    Check(!input.Pressed(kKeySpace), "unsupported keyboard key stays false");
    Check(!input.Triggered(kKeySpace), "unsupported keyboard edge stays false");
    Check(!input.Pressed(kLeftControl, 1), "controller identity 1 is not bridged");

    // Scene and menu guards.
    SetContext(2, kCharacterMenu);
    Check(!input.Pressed(kLeftControl), "gameplay scene is not bridged");
    SetContext(kMenuScene, 4);
    Check(!input.Pressed(kLeftControl), "non-character main menu is not bridged");
    SetContext(kMenuScene, kCharacterMenu);
    Check(input.Pressed(kKeyRight), "character menu scene 1 is bridged");
    g_MenuSlot = 0;
    Check(!input.Pressed(kKeyRight), "missing MenuManager slot is not bridged");

    g_MenuSlot = reinterpret_cast<std::uintptr_t>(g_Menu.data());
    SetContext(kMenuScene, kCharacterMenu);
    lua_close(state);
    isaac::runtime::ResetInputEdgeState();

    if (g_Failures != 0) {
        std::printf("CHARACTER_MENU_KEYBOARD_BRIDGE_FAILED %d\n", g_Failures);
        return 1;
    }
    std::printf("CHARACTER_MENU_KEYBOARD_BRIDGE_PASSED\n");
    return 0;
}
'''

HEADER_DRIVER = r'''
#include "interfaces/lua/character_menu_keyboard_bridge.hpp"

#include <cassert>

using namespace isaac::runtime::character_menu_keyboard_bridge;

int main() {
    assert(IsCharacterMenuContext(1, 5));
    assert(!IsCharacterMenuContext(2, 5));
    assert(!IsCharacterMenuContext(1, 4));

    assert(MapKeyboardIdentity(kKeyLeft, 0).controller_button == kButtonDpadLeft);
    assert(MapKeyboardIdentity(kKeyRight, 0).controller_button == kButtonDpadRight);
    assert(MapKeyboardIdentity(kKeyLeftControl, 0).controller_button == kButtonLeftStick);
    assert(MapKeyboardIdentity(kKeyRightControl, 0).controller_button == kButtonLeftStick);
    assert(MapKeyboardIdentity(kKeyU, 0).controller_button == kButtonRightStick);

    assert(!MapKeyboardIdentity(kKeyLeft, 1).mapped);
    assert(!MapKeyboardIdentity(32, 0).mapped);
}
'''


class CharacterMenuKeyboardBridgeTests(unittest.TestCase):
    def test_header_mapping_is_pure_and_scope_limited(self):
        with tempfile.TemporaryDirectory(prefix="character-keyboard-header-") as folder:
            work = Path(folder)
            source = work / "driver.cpp"
            binary = work / "driver"
            source.write_text(HEADER_DRIVER, encoding="utf-8")
            result = subprocess.run(
                [
                    "c++",
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(SRC),
                    str(source),
                    "-o",
                    str(binary),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(
                [str(binary)], text=True, capture_output=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bridge_is_scope_limited_and_uses_live_input(self):
        with tempfile.TemporaryDirectory(prefix="character-keyboard-bridge-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=HARNESS,
            )
            result = subprocess.run(
                [str(binary)], text=True, capture_output=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CHARACTER_MENU_KEYBOARD_BRIDGE_PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()
