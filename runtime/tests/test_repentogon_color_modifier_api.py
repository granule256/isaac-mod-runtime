"""ColorModifier is a typed 24-byte native value, not an opaque placeholder."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

RUNTIME = Path(__file__).resolve().parents[1]
SOURCE = RUNTIME / "source"
COLOR_MODIFIER_API = (
    RUNTIME / "src/interfaces/lua/repentogon_color_modifier_api.cpp"
)

DRIVER = r'''
#include "interfaces/lua/repentogon_color_modifier_api.hpp"

extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}

#include <cassert>
#include <cstdio>
#include <cstring>

using namespace isaac::runtime;

static_assert(sizeof(RepentogonColorModifierValue) == 0x18);
static_assert(offsetof(RepentogonColorModifierValue, r) == 0x00);
static_assert(offsetof(RepentogonColorModifierValue, g) == 0x04);
static_assert(offsetof(RepentogonColorModifierValue, b) == 0x08);
static_assert(offsetof(RepentogonColorModifierValue, a) == 0x0c);
static_assert(offsetof(RepentogonColorModifierValue, brightness) == 0x10);
static_assert(offsetof(RepentogonColorModifierValue, contrast) == 0x14);

static int Address(lua_State* state) {
    auto* value = RequireRepentogonColorModifierArgument(state, 1);
    lua_pushlightuserdata(state, value);
    return 1;
}

static void OpenLibraries(lua_State* state) {
    luaL_requiref(state, "_G", luaopen_base, 1);
    lua_pop(state, 1);
    luaL_requiref(state, LUA_TABLIBNAME, luaopen_table, 1);
    lua_pop(state, 1);
}

int main() {
    auto* state = luaL_newstate();
    assert(state);
    OpenLibraries(state);
    assert(RegisterRepentogonColorModifierApi(state) == 0);
    assert(RegisterRepentogonColorModifierApi(state) == 0);

    lua_pushcfunction(state, Address);
    lua_setglobal(state, "_address");

    const char* script = R"lua(
assert(type(ColorModifier) == 'table')
local value = ColorModifier(1, 0.25, -2, 0.5, 3, 4)
assert(value.R == 1 and value.G == 0.25 and value.B == -2 and value.A == 0.5)
assert(value.Brightness == 3 and value.Contrast == 4)
assert(_address(value) == _address(value))

value.R = 0.75
value.G = 0.5
value.B = 0.125
value.A = 0.625
value.Brightness = -1
value.Contrast = 2
assert(value.R == 0.75 and value.G == 0.5 and value.B == 0.125 and value.A == 0.625)
assert(value.Brightness == -1 and value.Contrast == 2)

local defaults = ColorModifier()
assert(defaults.R == 1 and defaults.G == 1 and defaults.B == 1 and defaults.A == 0)
assert(defaults.Brightness == 0 and defaults.Contrast == 1)
assert(not pcall(function() ColorModifier('bad') end))
assert(ColorModifier(1, 1, 1, 0)._address == nil)
)lua";

    if (luaL_loadbuffer(state, script, std::strlen(script),
                        "@color-modifier.lua") != LUA_OK ||
        lua_pcall(state, 0, 0, 0) != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        return 1;
    }

    lua_close(state);
}
'''

NATIVE_DRIVER = PREFIX + r'''
#include "game_observer.hpp"
#include "interfaces/lua/repentogon_color_modifier_api.hpp"
#include "runtime_constants.hpp"
#include <array>
#include <vector>

static std::vector<unsigned char> module, game, room;
static std::uintptr_t gamePointer;
static unsigned computes, sets;

GameRoomObservation ReadCurrentGameRoom(std::uintptr_t ownerSlot, void** current) {
    assert(ownerSlot == reinterpret_cast<std::uintptr_t>(module.data()) + kGameOwnerGlobalSlotOffset);
    *current = room.data();
    return GameRoomObservation::Success;
}

template<class T> static void Put(std::vector<unsigned char>& bytes, std::size_t offset, T value) {
    assert(offset + sizeof(T) <= bytes.size());
    std::memcpy(bytes.data() + offset, &value, sizeof(T));
}

static RepentogonColorModifierValue Compute(const void* object) {
    assert(object == room.data());
    ++computes;
    return {2, 3, 4, 5, 6, 7};
}

static void Set(void* object, const RepentogonColorModifierValue& color, bool lerp, float rate) {
    assert(object == game.data());
    assert(color.contrast == color.r + 5);
    if (sets == 0) assert(color.r == 1 && lerp && rate == 0.015f);
    if (sets == 1) assert(color.r == 2 && lerp && rate == 1.f);
    if (sets == 2) assert(color.r == 8 && !lerp && rate == 0.25f);
    if (sets == 3) assert(color.r == 2 && lerp && rate == 0.015f);
    ++sets;
}

int main() {
    module.resize(kGameOwnerGlobalSlotOffset + sizeof(std::uintptr_t));
    game.resize(0x350000);
    room.resize(0x4000);
    gamePointer = reinterpret_cast<std::uintptr_t>(game.data());
    const auto base = reinterpret_cast<std::uintptr_t>(module.data());
    Put(module, kGameOwnerGlobalSlotOffset, reinterpret_cast<std::uintptr_t>(&gamePointer));
    Put(room, 0x1f30, RepentogonColorModifierValue{8, 9, 10, 11, 12, 13});
    const std::array<unsigned char, 16> setGuard{
        0x2d,0x08,0x40,0xf9,0x89,0xd0,0x8b,0x52,0x89,0x06,0xa0,0x72,0x2b,0x30,0x40,0xa9};
    const std::array<unsigned char, 16> computeGuard{
        0xef,0x3b,0xb9,0x6d,0xed,0x33,0x01,0x6d,0xf5,0x2b,0x00,0xf9,0xeb,0x2b,0x02,0x6d};
    Put(module, 0x35ca3c, setGuard);
    Put(module, 0x48a5ec, computeGuard);
    LuaRuntime::SetEngineModuleBase(base);
    LuaRuntime::SetGameBindings(base + kGameOwnerGlobalSlotOffset, 0);
    LuaRuntime::ObserveGameThread();
    Files files(true);
    SetSessionSaveFilePort(&files);
    const repentogon::NativePort port{Ready, Ready};
    repentogon::SetNativePort(&port);
    SetRepentogonColorModifierNativeTestBindings({Set, Compute});

    const char* script = R"lua(
local game = Game()
local room = game:GetRoom()
game:SetColorModifier(ColorModifier(1,2,3,4,5,6))
room:UpdateColorModifier(true, true, 1)
room:UpdateColorModifier(false, false, 0.25)
room:UpdateColorModifier()
assert(not pcall(game.SetColorModifier, game, {}))
assert(not pcall(game.SetColorModifier, game, ColorModifier(), 'x'))
)lua";
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@color-native.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        char error[1024]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    assert(sets == 4 && computes == 2);
    assert(LuaRuntime::ShutdownForModReload());
    SetRepentogonColorModifierNativeTestBindings({});
    repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonColorModifierApiTests(unittest.TestCase):
    def test_constructor_properties_and_typed_native_accessor(self):
        with tempfile.TemporaryDirectory(prefix="color-modifier-") as folder:
            extra_sources = (
                ()
                if COLOR_MODIFIER_API
                in test_support.layered_lua_runtime_sources(SOURCE)
                else (COLOR_MODIFIER_API,)
            )
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
                extra_sources=extra_sources,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_game_and_room_submit_native_color_with_correct_abi_and_defaults(self):
        with tempfile.TemporaryDirectory(prefix="color-modifier-native-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=NATIVE_DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
