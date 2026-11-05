"""The reserved restart chord is one logical action, without a menu-toggle edge."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_input_slot_collision import HARNESS, SOURCE
from .test_support import build_lua_harness

CASES = r'''
    luaL_requiref(state, "_G", luaopen_base, 1); lua_pop(state, 1);
    const auto valueQuery = +[](void*, std::uint32_t, std::uint32_t, void*) -> float {return 0.25f;};
    LuaRuntime::SetInputBindings(reinterpret_cast<std::uintptr_t>(&FakeActionPressed), 0,
                                reinterpret_cast<std::uintptr_t>(valueQuery));
    auto sample = [&](unsigned buttons) {
        g_heldBy33 = buttons; g_heldBy1 = 0; advance_frame();
    };
    auto expect = [&](const char* script) {
        if (luaL_dostring(state, script) != LUA_OK) {
            std::printf("RESTART_INPUT_FAILED: %s\n", lua_tostring(state, -1));
            ++failures; lua_pop(state, 1);
        }
    };
    constexpr unsigned chord = (1u<<8)|(1u<<11)|(1u<<10)|(1u<<13);
    sample(0);
    sample(chord|(1u<<4));
    expect("assert(Input.IsActionPressed(18,1), 'restart chord must expose ACTION_RESTART');"
           "assert(Input.IsActionTriggered(18,1), 'restart action needs its own edge');"
           "assert(Input.GetActionValue(18,1)==1);"
           "assert(not Input.IsButtonTriggered(13,1), 'restart must not toggle a menu');"
           "assert(Input.IsButtonPressed(13,1), 'raw held state must remain readable');"
           "assert(Input.IsButtonTriggered(4,1), 'unrelated button edge must survive')");
    sample(chord);
    expect("assert(Input.IsActionPressed(18,1));assert(not Input.IsActionTriggered(18,1))");
    sample(1u<<13);
    expect("assert(not Input.IsActionPressed(18,1));assert(Input.GetActionValue(18,1)==0);"
           "assert(not Input.IsButtonTriggered(13,1), 'partial release must not invent an edge')");
    sample(0);sample(1u<<13);
    expect("assert(Input.IsButtonTriggered(13,1), 'standalone right stick still toggles a menu');"
           "assert(not Input.IsActionPressed(18,1))");
    sample(0);sample(chord & ~(1u<<13));sample(chord);
    expect("assert(Input.IsActionTriggered(18,1));assert(not Input.IsButtonTriggered(13,1))");
    sample(0);
    g_heldBy33 = chord & ~(1u<<13);g_heldBy1 = 1u<<13;advance_frame();
    expect("assert(Input.IsActionPressed(18,4294967295), 'native any-device chord must match');"
           "assert(not Input.IsActionPressed(18,1), 'no single physical device holds the chord');"
           "assert(not Input.IsButtonTriggered(13,1), 'global restart consumes component edges')");
'''


class NativeRestartInputTests(unittest.TestCase):
    def test_real_sampler_and_lua_queries(self):
        with tempfile.TemporaryDirectory(prefix='isaac-restart-input-') as temporary:
            binary = build_lua_harness(
                source_root=SOURCE, workdir=Path(temporary),
                harness_source=HARNESS.replace('#include <lauxlib.h>', '#include <lauxlib.h>\n#include <lualib.h>')
                                      .replace('    lua_close(state);', CASES+'\n    lua_close(state);'))
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
