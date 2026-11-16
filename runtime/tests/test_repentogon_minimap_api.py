"""REPENTOGON's Minimap reads the current engine map and returns Lua Vectors."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = PREFIX + r'''
#include "interfaces/lua/repentogon_minimap_api.hpp"
#include "runtime_constants.hpp"
#include <vector>

constexpr std::uintptr_t kMinimap = 0x24ee70;
static std::vector<unsigned char> moduleBytes, game;
static std::uintptr_t currentGame;
static unsigned sizeCalls;

template<class T> static void Put(std::vector<unsigned char>& memory,
                                  std::size_t offset, T value) {
    std::memcpy(memory.data() + offset, &value, sizeof(value));
}

static RepentogonMinimapVector DisplayedSize(void* minimap) {
    assert(minimap == game.data() + kMinimap);
    ++sizeCalls;
    return {39.25f, 51.5f};
}

static int ChangeMap(lua_State*) {
    Put(game, kMinimap, 1);
    Put(game, kMinimap + 0x794, 5.5f);
    Put(game, kMinimap + 0x798, -4.f);
    return 0;
}

static int ClearGame(lua_State*) {
    currentGame = 0;
    return 0;
}

static void InstallTestBindings(lua_State* state) noexcept {
    lua_pushcfunction(state, ChangeMap);
    lua_setglobal(state, "_changeMap");
    lua_pushcfunction(state, ClearGame);
    lua_setglobal(state, "_clearGame");
}

int main() {
    moduleBytes.resize(kGameOwnerGlobalSlotOffset + sizeof(std::uintptr_t));
    game.resize(kMinimap + 0xb40);
    currentGame = reinterpret_cast<std::uintptr_t>(game.data());
    const auto ownerSlot = reinterpret_cast<std::uintptr_t>(&currentGame);
    Put(moduleBytes, kGameOwnerGlobalSlotOffset, ownerSlot);
    Put(game, kMinimap, 2);
    Put(game, kMinimap + 0x794, -1.25f);
    Put(game, kMinimap + 0x798, 3.75f);
    const unsigned char guard[] = {
        0xff,0xc3,0x00,0xd1,0xe8,0x0b,0x00,0xfd,
        0xf3,0x17,0x00,0xf9,0xfd,0xfb,0x01,0xa9};
    std::memcpy(moduleBytes.data() + 0x41a9cc, guard, sizeof(guard));
    const auto base = reinterpret_cast<std::uintptr_t>(moduleBytes.data());
    LuaRuntime::SetEngineModuleBase(base);
    LuaRuntime::SetGameBindings(base + kGameOwnerGlobalSlotOffset, 0);
    LuaRuntime::ObserveGameThread();
    Files files(true);
    SetSessionSaveFilePort(&files);
    const repentogon::NativePort port{Ready, Ready};
    repentogon::SetNativePort(&port);
    SetRepentogonMinimapNativeTestBinding(&DisplayedSize);
    LuaRuntime::SetRuntimeExtensionInstaller(InstallTestBindings);

    const char* script = R"lua(
assert(type(Minimap) == 'table')
assert(Minimap.GetState() == 2)
local size = Minimap.GetDisplayedSize()
assert(size.X == 39.25 and size.Y == 51.5)
local shake = Minimap.GetShakeOffset()
assert(shake == Vector(-1.25, 3.75))
_changeMap()
assert(Minimap.GetState() == 1 and Minimap.GetShakeOffset() == Vector(5.5, -4))
assert(shake == Vector(-1.25, 3.75))
_clearGame()
assert(not pcall(Minimap.GetState))
assert(not pcall(Minimap.GetShakeOffset))
assert(not pcall(Minimap.GetDisplayedSize))
)lua";
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@minimap.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        char error[1024]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    assert(sizeCalls == 1);
    assert(LuaRuntime::ShutdownForModReload());
    LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
    SetRepentogonMinimapNativeTestBinding(nullptr);
    repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonMinimapApiTests(unittest.TestCase):
    def test_reads_native_map_state_size_and_shake(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-minimap-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
