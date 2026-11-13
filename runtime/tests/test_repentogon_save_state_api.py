"""Room save-state vectors use the pinned descriptor and element layouts."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / "source"
DRIVER = PREFIX + r'''
#include "interfaces/lua/repentogon_save_state_api.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>

using namespace isaac::runtime;

static std::vector<unsigned char> module;
static std::vector<unsigned char> descriptor;
static std::vector<unsigned char> game;
static std::vector<unsigned char> gridElements;
static std::vector<unsigned char> entityElements;
static std::vector<unsigned char> decoElements;
static std::uintptr_t entityBeginAddress;
static unsigned clearCalls;

static std::uintptr_t Address(const std::vector<unsigned char>& bytes) {
    return reinterpret_cast<std::uintptr_t>(bytes.data());
}

static int CorruptAssignGuard(lua_State*) {
    module[0x360fdc] ^= 1;
    return 0;
}

static int RestoreAssignGuard(lua_State*) {
    module[0x360fdc] ^= 1;
    return 0;
}

template <class T>
static void Put(std::vector<unsigned char>& bytes, std::size_t offset, T value) {
    assert(offset + sizeof(value) <= bytes.size());
    std::memcpy(bytes.data() + offset, &value, sizeof(value));
}

static void Extensions(lua_State* state) noexcept {
    RegisterRepentogonSaveStateViews(state);
    auto* handle = static_cast<LuaRuntime::RoomDescriptorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RoomDescriptorHandle)));
    *handle = {descriptor.data(), game.data(), LuaRuntime::EngineModuleBase()};
    luaL_getmetatable(state, LuaRuntime::kRoomDescriptorMetatable);
    lua_setmetatable(state, -2);
    lua_setglobal(state, "desc");
    lua_pushcfunction(state, CorruptAssignGuard);
    lua_setglobal(state, "_corruptAssignGuard");
    lua_pushcfunction(state, RestoreAssignGuard);
    lua_setglobal(state, "_restoreAssignGuard");
}

static void HostAssign(void* vector, const void* first, const void* last) {
    assert(vector != nullptr);
    assert(first == last);
    if (clearCalls == 0) {
        assert(first == reinterpret_cast<const void*>(entityBeginAddress));
    } else {
        assert(first == nullptr);
    }
    std::memset(vector, 0, 0x18);
    ++clearCalls;
}

int main() {
    module.assign(0x361000, 0);
    descriptor.assign(0x100, 0);
    game.assign(0x100, 0);
    gridElements.assign(2 * 0x20, 0);
    entityElements.assign(2 * 0x78, 0);
    decoElements.assign(0x78, 0);

    const auto gridBegin = Address(gridElements);
    Put(descriptor, 0x78, gridBegin);
    Put(descriptor, 0x80, gridBegin + gridElements.size());
    Put(descriptor, 0x88, gridBegin + gridElements.size());
    Put(gridElements, 0x00, std::int32_t{4});
    Put(gridElements, 0x04, std::int32_t{7});
    Put(gridElements, 0x0c, std::int32_t{9});
    Put(gridElements, 0x10, std::int32_t{2});
    Put(gridElements, 0x14, std::int32_t{11});
    gridElements[0x18] = 1;

    const auto entityBegin = Address(entityElements);
    entityBeginAddress = entityBegin;
    Put(descriptor, 0x90, entityBegin);
    Put(descriptor, 0x98, entityBegin + entityElements.size());
    Put(descriptor, 0xa0, entityBegin + entityElements.size());
    Put(entityElements, 0x00, std::uint32_t{20});
    Put(entityElements, 0x04, std::uint32_t{3});
    Put(entityElements, 0x08, std::uint32_t{8});
    Put(entityElements, 0x14, std::int32_t{42});

    const auto decoBegin = Address(decoElements);
    Put(descriptor, 0xc0, decoBegin);
    Put(descriptor, 0xc8, decoBegin + decoElements.size());
    Put(descriptor, 0xd0, decoBegin + decoElements.size());
    Put(decoElements, 0x00, std::uint32_t{100});

    LuaRuntime::SetEngineModuleBase(Address(module));
    LuaRuntime::ObserveGameThread();
    const unsigned char assignGuard[] = {
        0xfd, 0x7b, 0xba, 0xa9, 0xfc, 0x6f, 0x01, 0xa9,
        0xfd, 0x03, 0x00, 0x91, 0xfa, 0x67, 0x02, 0xa9,
    };
    std::memcpy(module.data() + 0x360fdc, assignGuard, sizeof(assignGuard));
    SetRepentogonSaveStateNativeTestBindings({HostAssign});
    Files files(true);
    SetSessionSaveFilePort(&files);
    const repentogon::NativePort port{Ready, Ready};
    repentogon::SetNativePort(&port);
    LuaRuntime::SetRuntimeExtensionInstaller(Extensions);

    const char* script = R"lua(
local entities = desc:GetEntitiesSaveState()
assert(#entities == 2)
local entity = entities:Get(0)
local deco = desc:GetDecoSaveState()
_corruptAssignGuard()
local guardOk, guardErr = pcall(function() deco:Clear() end)
assert(not guardOk and string.find(guardErr, 'guard'))
_restoreAssignGuard()
assert(#deco == 1 and deco:Get(0):GetType() == 100)
assert(entity:GetType() == 20)
assert(entity:GetVariant() == 3)
assert(entity:GetSubType() == 8)
assert(entity:GetI3() == 42)
assert(select('#', entities:Clear()) == 0)
assert(#entities == 0)
local stale, staleErr = pcall(function() return entity:GetType() end)
assert(not stale and string.find(staleErr, 'no longer available'))
assert(not pcall(function() entities:Get(0) end))
assert(select('#', entities:Clear()) == 0 and #entities == 0)
local grid = desc:GetGridEntitiesSaveState()
assert(#grid == 2)
assert(type(grid.Clear) == 'function')
local gridDesc = grid:Get(0)
assert(gridDesc.Initialized and gridDesc.SpawnCount == 9 and gridDesc.State == 2)
assert(gridDesc.Type == 4 and gridDesc.Variant == 7 and gridDesc.VarData == 11)
assert(select('#', grid:Clear()) == 0)
assert(#grid == 2)
assert(gridDesc.Initialized and gridDesc.SpawnCount == 9 and gridDesc.State == 2)
assert(gridDesc.Type == 0 and gridDesc.Variant == 7 and gridDesc.VarData == 11)
gridDesc.Initialized = false
gridDesc.SpawnCount = 0
gridDesc.State = 0
gridDesc.Type = 0
gridDesc.Variant = 0
gridDesc.VarData = 0
assert(not gridDesc.Initialized and gridDesc.SpawnCount == 0 and gridDesc.State == 0)
assert(gridDesc.Type == 0 and gridDesc.Variant == 0 and gridDesc.VarData == 0)
assert(not pcall(function() entities:Get(2) end))
assert(not pcall(function() grid:Get(2) end))
)lua";
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                         "@save-state-api.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    assert(LuaRuntime::ShutdownForModReload());
    assert(clearCalls == 2);
    LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
    repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonSaveStateApiTests(unittest.TestCase):
    def test_descriptor_vectors_and_element_fields(self):
        with tempfile.TemporaryDirectory(prefix="repentogon-save-state-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
