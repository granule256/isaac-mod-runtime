"""Isaac.CreateTimer keeps its Lua callback alive and reports callback errors."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / "source"
DRIVER = PREFIX + r'''
#include "interfaces/lua/repentogon_timer_api.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>

static std::vector<unsigned char> module;
static std::vector<unsigned char> effect;
static void (*timerCallback)(void*);
static int createCalls;

static void* CreateTimer(void (*callback)(void*), std::uint32_t delay,
                         std::int32_t times, bool persistent) {
    assert(callback != nullptr);
    assert(delay == 5 || delay == 1);
    assert(times == 2 || times == 0);
    assert(!persistent || times == 0);
    ++createCalls;
    timerCallback = callback;
    return effect.data();
}

static int Fire(lua_State*) {
    assert(timerCallback != nullptr);
    timerCallback(effect.data());
    return 0;
}

static void Extensions(lua_State* state) noexcept {
    lua_pushcfunction(state, Fire);
    lua_setglobal(state, "_fire");
}

int main() {
    module.assign(kEntityEffectVtableOffset + 16, 0);
    effect.assign(0x2000, 0);
    const auto base = reinterpret_cast<std::uintptr_t>(module.data());
    const auto vtable = base + kEntityEffectVtableOffset;
    std::memcpy(effect.data(), &vtable, sizeof(vtable));
    const std::uint32_t type = kEntityTypeEffect;
    std::memcpy(effect.data() + kEntityTypeOffset, &type, sizeof(type));

    Files files(true);
    SetSessionSaveFilePort(&files);
    LuaRuntime::SetEngineModuleBase(base);
    LuaRuntime::ObserveGameThread();
    const isaac::runtime::repentogon::NativePort port{Ready, Ready};
    isaac::runtime::repentogon::SetNativePort(&port);
    isaac::runtime::SetRepentogonTimerNativeTestBindings({&CreateTimer});
    LuaRuntime::SetRuntimeExtensionInstaller(Extensions);

    const char* script = R"lua(
timerCalls = 0
local effect = Isaac.CreateTimer(function(entity)
  assert(entity.Type == 1000)
  timerCalls = timerCalls + 1
end, 5, 2, false)
assert(effect.Type == 1000)
_fire()
assert(timerCalls == 1)
_fire()
assert(timerCalls == 2)

local second = Isaac.CreateTimer(function()
  error('timer boom')
end, 1)
assert(second.Type == 1000)
_fire()

assert(not pcall(function() Isaac.CreateTimer(1, 1) end))
)lua";
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                         "@timer-api.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    assert(createCalls == 2);
    assert(LuaRuntime::TakeCallbackError());
    assert(LuaRuntime::ShutdownForModReload());
    LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
    isaac::runtime::SetRepentogonTimerNativeTestBindings({});
    isaac::runtime::repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonTimerApiTests(unittest.TestCase):
    def test_lua_timer_callback_and_error(self):
        with tempfile.TemporaryDirectory(prefix="repentogon-timer-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
