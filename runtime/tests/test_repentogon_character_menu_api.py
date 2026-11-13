"""Fancy Menu CharacterMenu and MenuManager prerequisites use live native state."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

PUBLIC_ROOT = Path(__file__).resolve().parents[2]
SOURCE = PUBLIC_ROOT / "runtime" / "source"
API_SOURCE = (
    PUBLIC_ROOT
    / "runtime"
    / "src"
    / "interfaces"
    / "lua"
    / "repentogon_character_menu_api.cpp"
)
COLOR_MODIFIER_SOURCE = (
    PUBLIC_ROOT
    / "runtime"
    / "src"
    / "interfaces"
    / "lua"
    / "repentogon_color_modifier_api.cpp"
)

DRIVER = PREFIX + r'''
#include "interfaces/lua/repentogon_character_menu_api.hpp"
#include "interfaces/lua/repentogon_color_modifier_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "runtime_constants.hpp"

#include <cstring>
#include <vector>

namespace {
constexpr std::uintptr_t kMenuManagerSlot = 0xAAD1B0;
constexpr std::uintptr_t kMenuCharacter = 0x1A2658;
constexpr std::uintptr_t kCharacterStatus = 0x38;
constexpr std::uintptr_t kCharacterUnlocked = 0x3D;
constexpr std::uintptr_t kCharacterDifficulty = 0x40;
constexpr std::uintptr_t kCharacterSelectedId = 0x48;
constexpr std::uintptr_t kCharacterShownPage = 0x1138;
constexpr std::uintptr_t kCharacterPageSwapWidget = 0x1140;
constexpr std::uintptr_t kCharacterCompletionWidget = 0x5D8;
constexpr std::uintptr_t kCharacterModMap = 0x1400;
constexpr std::uintptr_t kVanillaPlayerTable = 0xA38840;
constexpr std::uintptr_t kVanillaPageStride = 0x240;
constexpr std::uintptr_t kVanillaEntryStride = 0x20;
constexpr std::uintptr_t kVanillaPlayerType = 0x08;

template <class T>
void Put(std::vector<unsigned char>& bytes, std::uintptr_t offset, T value) {
    assert(offset + sizeof(value) <= bytes.size());
    std::memcpy(bytes.data() + offset, &value, sizeof(value));
}

std::uintptr_t Address(const void* value) {
    return reinterpret_cast<std::uintptr_t>(value);
}

void Bind(lua_State* state, const char* table, const char* name,
          lua_CFunction function) {
    lua_getglobal(state, table);
    assert(lua_istable(state, -1));
    lua_pushcfunction(state, function);
    lua_setfield(state, -2, name);
    lua_pop(state, 1);
}

}  // namespace

static std::vector<unsigned char> moduleBytes;
static std::vector<unsigned char> menuSlot;
static std::vector<unsigned char> menuManager;
static std::vector<unsigned char> modMap;
static unsigned selectedPlayerTypeCalls;
static unsigned colorModifierCalls;
static float lastColor[6];
static bool lastLerp;
static float lastRate;

static int SelectedPlayerType(const void* menu, int selection) {
    ++selectedPlayerTypeCalls;
    assert(Address(menu) == Address(menuManager.data()) + kMenuCharacter);
    assert(selection >= 0);
    return selection == 9 ? 38 : selection;
}

static void SetColorModifier(void* menu, const void* value, bool lerp,
                             float rate) {
    ++colorModifierCalls;
    assert(Address(menu) == Address(menuManager.data()));
    const auto* modifier =
        static_cast<const isaac::runtime::RepentogonColorModifierValue*>(value);
    lastColor[0] = modifier->r;
    lastColor[1] = modifier->g;
    lastColor[2] = modifier->b;
    lastColor[3] = modifier->a;
    lastColor[4] = modifier->brightness;
    lastColor[5] = modifier->contrast;
    lastLerp = lerp;
    lastRate = rate;
}

static int InputAllowed(lua_State* state) {
    const auto action =
        static_cast<std::uint32_t>(luaL_checkinteger(state, 1));
    lua_pushboolean(
        state,
        isaac::runtime::RepentogonMenuManagerInputMaskAllows(action));
    return 1;
}

static int ClearInputMask(lua_State* state) {
    static_cast<void>(state);
    isaac::runtime::ClearRepentogonMenuInputMask();
    return 0;
}

static int BeginMaskScope(lua_State* state) {
    static_cast<void>(state);
    isaac::runtime::BeginRepentogonMainMenuRenderInputMaskScope();
    return 0;
}

static int EndMaskScope(lua_State* state) {
    static_cast<void>(state);
    isaac::runtime::EndRepentogonMainMenuRenderInputMaskScope();
    return 0;
}

static void Extensions(lua_State* state) noexcept {
    assert(isaac::runtime::RegisterRepentogonColorModifierApi(state) == 0);
    assert(isaac::runtime::RegisterRepentogonCharacterMenuApi(state) == 0);

    Bind(state, "CharacterMenu", "GetActiveStatus",
         isaac::runtime::RepentogonCharacterMenuGetActiveStatus);
    Bind(state, "CharacterMenu", "GetDifficulty",
         isaac::runtime::RepentogonCharacterMenuGetDifficulty);
    Bind(state, "CharacterMenu", "GetIsCharacterUnlocked",
         isaac::runtime::RepentogonCharacterMenuGetIsCharacterUnlocked);
    Bind(state, "CharacterMenu", "GetPageSwapWidgetSprite",
         isaac::runtime::RepentogonCharacterMenuGetPageSwapWidgetSprite);
    Bind(state, "CharacterMenu", "GetSelectedCharacterID",
         isaac::runtime::RepentogonCharacterMenuGetSelectedCharacterID);
    Bind(state, "CharacterMenu", "GetSelectedCharacterMenu",
         isaac::runtime::RepentogonCharacterMenuGetSelectedCharacterMenu);
    Bind(state, "CharacterMenu", "GetSelectedCharacterPlayerType",
         isaac::runtime::RepentogonCharacterMenuGetSelectedCharacterPlayerType);
    Bind(state, "CharacterMenu", "GetPlayerTypeFromCharacterMenuID",
         isaac::runtime::RepentogonCharacterMenuGetPlayerTypeFromCharacterMenuID);
    Bind(state, "MenuManager", "SetInputMask",
         isaac::runtime::RepentogonMenuManagerSetInputMask);
    Bind(state, "MenuManager", "SetColorModifier",
         isaac::runtime::RepentogonMenuManagerSetColorModifier);
    lua_pushcfunction(state, InputAllowed);
    lua_setglobal(state, "_inputAllowed");
    lua_pushcfunction(state, ClearInputMask);
    lua_setglobal(state, "_clearInputMask");
    lua_pushcfunction(state, BeginMaskScope);
    lua_setglobal(state, "_beginMaskScope");
    lua_pushcfunction(state, EndMaskScope);
    lua_setglobal(state, "_endMaskScope");
}

int main() {
    moduleBytes.assign(kMenuManagerSlot + sizeof(std::uintptr_t), 0);
    menuSlot.assign(sizeof(std::uintptr_t), 0);
    menuManager.assign(0x1B0000, 0);
    modMap.assign(2 * sizeof(std::uint64_t), 0);

    Put<std::uintptr_t>(menuSlot, 0, Address(menuManager.data()));
    Put<std::uintptr_t>(moduleBytes, kMenuManagerSlot,
                        Address(menuSlot.data()));

    const auto character = Address(menuManager.data()) + kMenuCharacter;
    Put<std::int32_t>(menuManager, kMenuCharacter + kCharacterStatus, 3);
    Put<std::uint8_t>(menuManager, kMenuCharacter + kCharacterUnlocked, 1);
    Put<std::int32_t>(menuManager, kMenuCharacter + kCharacterDifficulty, 2);
    Put<std::int32_t>(menuManager, kMenuCharacter + kCharacterSelectedId, 9);
    Put<std::int32_t>(menuManager, kMenuCharacter + kCharacterShownPage, 1);
    Put<std::uintptr_t>(menuManager, kMenuCharacter + kCharacterModMap,
                        Address(modMap.data()));
    Put<std::uintptr_t>(menuManager, kMenuCharacter + kCharacterModMap + 0x08,
                        Address(modMap.data()) + modMap.size());
    Put<std::uintptr_t>(menuManager, kMenuCharacter + kCharacterModMap + 0x10,
                        Address(modMap.data()) + modMap.size());
    Put<std::uint64_t>(modMap, 0, 50 | (std::uint64_t{51} << 32));
    Put<std::uint64_t>(modMap, sizeof(std::uint64_t), 52 | (std::uint64_t{53} << 32));

    Put<std::int32_t>(moduleBytes,
                      kVanillaPlayerTable + kVanillaPageStride +
                          kVanillaEntryStride * 9 + kVanillaPlayerType,
                      38);
    Put<std::int32_t>(moduleBytes,
                      kVanillaPlayerTable + kVanillaEntryStride * 9 +
                          kVanillaPlayerType,
                      9);

    LuaRuntime::SetEngineModuleBase(Address(moduleBytes.data()));
    LuaRuntime::ObserveGameThread();
    const isaac::runtime::repentogon::NativePort port{
        Ready, Ready,
        isaac::runtime::RepentogonCharacterMenuSpriteAlive};
    isaac::runtime::repentogon::SetNativePort(&port);
    isaac::runtime::SetRepentogonCharacterMenuNativeTestBindings(
        {SelectedPlayerType, SetColorModifier});
    LuaRuntime::SetRuntimeExtensionInstaller(Extensions);

    constexpr const char* script = R"lua(
local modifier = ColorModifier(0.25, 0.5, 0.75, 0.125, 1.5, 2.5)
assert(type(modifier) == 'userdata')
MenuManager.SetColorModifier(modifier, false, 0.2)

assert(CharacterMenu.GetActiveStatus() == 3)
assert(CharacterMenu.GetDifficulty() == 2)
assert(CharacterMenu.GetIsCharacterUnlocked() == true)
assert(CharacterMenu.GetSelectedCharacterID() == 9)
assert(CharacterMenu.GetSelectedCharacterMenu() == 1)
assert(CharacterMenu.GetSelectedCharacterPlayerType() == 38)
assert(CharacterMenu.GetPlayerTypeFromCharacterMenuID(9, false) == 9)
assert(CharacterMenu.GetPlayerTypeFromCharacterMenuID(9, true) == 38)
assert(CharacterMenu.GetPlayerTypeFromCharacterMenuID(18, false) == 50)
assert(CharacterMenu.GetPlayerTypeFromCharacterMenuID(18, true) == 51)
assert(CharacterMenu.GetPlayerTypeFromCharacterMenuID(19, false) == 52)
assert(CharacterMenu.GetPlayerTypeFromCharacterMenuID(19, true) == 53)
assert(CharacterMenu.GetPlayerTypeFromCharacterMenuID(20, false) == nil)
assert(CharacterMenu.GetPlayerTypeFromCharacterMenuID(-1, false) == nil)
assert(type(CharacterMenu.GetPageSwapWidgetSprite()) == 'userdata')

MenuManager.SetInputMask(0)
assert(not _inputAllowed(20))
assert(not _inputAllowed(31))
_beginMaskScope()
assert(_inputAllowed(20))
_endMaskScope()
assert(not _inputAllowed(20))
MenuManager.SetInputMask(1048576)
assert(_inputAllowed(20))
assert(not _inputAllowed(21))
_beginMaskScope()
assert(_inputAllowed(21))
_endMaskScope()
assert(not _inputAllowed(21))
_clearInputMask()
assert(_inputAllowed(31))
)lua";

    const auto result = LuaRuntime::InitializeFromBuffer(
        script, std::strlen(script), "@repentogon-character-menu.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }

    assert(selectedPlayerTypeCalls == 1);
    assert(colorModifierCalls == 1);
    assert(lastColor[0] == 0.25F && lastColor[1] == 0.5F &&
           lastColor[2] == 0.75F && lastColor[3] == 0.125F &&
           lastColor[4] == 1.5F && lastColor[5] == 2.5F);
    assert(!lastLerp && lastRate == 0.2F);
    Put<std::int32_t>(menuManager, 0x38, 0x108);
    constexpr const char* transitionMask = R"lua(
MenuManager.SetInputMask(0)
_beginMaskScope()
_endMaskScope()
assert(_inputAllowed(20))
)lua";
    if (LuaRuntime::InitializeFromBuffer(
            transitionMask, std::strlen(transitionMask),
            "@repentogon-character-menu-transition-mask.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        return 4;
    }
    Put<std::int32_t>(menuManager, 0x38, 8);
    isaac::runtime::ClearRepentogonMenuInputMask();
    assert(isaac::runtime::RepentogonCharacterMenuSpriteAlive(
        character + kCharacterPageSwapWidget));
    assert(isaac::runtime::RepentogonCharacterMenuSpriteAlive(
        character + kCharacterCompletionWidget + 0x08));
    assert(!isaac::runtime::RepentogonCharacterMenuSpriteAlive(
        character + kCharacterPageSwapWidget + 8));

    Put<std::int32_t>(menuManager, kMenuCharacter + kCharacterUnlocked, 0);
    constexpr const char* locked = R"lua(
assert(CharacterMenu.GetIsCharacterUnlocked() == false)
)lua";
    if (LuaRuntime::InitializeFromBuffer(locked, std::strlen(locked),
            "@repentogon-character-menu-locked.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        return 2;
    }

    Put<std::uintptr_t>(menuSlot, 0, 0);
    constexpr const char* inactive = R"lua(
assert(not pcall(function() CharacterMenu.GetActiveStatus() end))
assert(not pcall(function() CharacterMenu.GetPageSwapWidgetSprite() end))
)lua";
    if (LuaRuntime::InitializeFromBuffer(inactive, std::strlen(inactive),
            "@repentogon-character-menu-inactive.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        return 3;
    }

    assert(LuaRuntime::ShutdownForModReload());
    LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
    isaac::runtime::SetRepentogonCharacterMenuNativeTestBindings({});
    isaac::runtime::repentogon::SetNativePort(nullptr);
}
'''


class RepentogonCharacterMenuApiTests(unittest.TestCase):
    def test_native_branch_compiles_with_null_host_address(self) -> None:
        with tempfile.TemporaryDirectory(
                prefix="repentogon-character-menu-compile-") as folder:
            compatibility = Path(folder) / "compatibility"
            compatibility.mkdir()
            (compatibility / "stdfloat").write_text(
                "#pragma once\n"
                "namespace std { using float16_t = float; "
                "using float128_t = long double; }\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "c++", "-std=c++23", "-D__SWITCH__",
                    "-DEXL_LAYERED_RUNTIME=1", "-DEXL_DIAGNOSTIC_STAGE=14",
                    "-DEXL_LOAD_KIND=Module", "-DEXL_LOAD_KIND_ENUM=2",
                    "-DEXL_PROGRAM_ID=0", "-fsyntax-only",
                    f"-I{compatibility}", f"-I{PUBLIC_ROOT / 'runtime' / 'src'}",
                    f"-I{SOURCE}",
                    f"-I{SOURCE / 'third_party' / 'lua-5.3.3' / 'src'}",
                    str(API_SOURCE),
                ],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_live_character_menu_surface(self) -> None:
        with tempfile.TemporaryDirectory(prefix="repentogon-character-menu-") as folder:
            layered = test_support.layered_lua_runtime_sources(SOURCE)
            extra_sources = tuple(
                source for source in (API_SOURCE, COLOR_MODIFIER_SOURCE)
                if source not in layered
            )
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
                extra_sources=extra_sources,
            )
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
