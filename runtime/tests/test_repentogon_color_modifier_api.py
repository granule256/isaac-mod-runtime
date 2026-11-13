"""ColorModifier is a typed 24-byte native value, not an opaque placeholder."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support

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


if __name__ == "__main__":
    unittest.main()
