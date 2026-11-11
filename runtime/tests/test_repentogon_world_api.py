"""Repentogon Level dimension and GridEntity trapdoor downcast consumers."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_repentogon_in_game import PREFIX

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness


SOURCE = Path(__file__).resolve().parent.parent / "source"

DEFAULT_VM_CHECK = PREFIX + r'''
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"

#include <cstdio>
#include <cstring>

extern "C" {
#include "lauxlib.h"
}

void InspectDefaultSurface(lua_State* state) noexcept {
    luaL_getmetatable(state, LuaRuntime::kLevelMetatable);
    lua_getfield(state, -1, "GetDimension");
    lua_pushboolean(state, lua_isfunction(state, -1));
    lua_setglobal(state, "defaultLevelDimension");
    lua_pop(state, 2);

    luaL_getmetatable(state, LuaRuntime::kGridEntityMetatable);
    lua_getfield(state, -1, "__methods");
    lua_getfield(state, -1, "ToTrapDoor");
    lua_pushboolean(state, lua_isfunction(state, -1));
    lua_setglobal(state, "defaultGridTrapDoor");
    lua_pop(state, 3);

    luaL_getmetatable(state, LuaRuntime::kRoomMetatable);
    lua_getfield(state, -1, "__index");
    lua_getfield(state, -1, "GetGreedWaveTimer");
    lua_pushboolean(state, lua_isfunction(state, -1));
    lua_setglobal(state, "defaultRoomGreedTimer");
    lua_pop(state, 3);
}

int main() {
    Files files(true);SetSessionSaveFilePort(&files);LuaRuntime::ObserveGameThread();
    const isaac::runtime::repentogon::NativePort port{Ready,Ready};
    isaac::runtime::repentogon::SetNativePort(&port);
    constexpr const char* script = R"lua(
local missing = {}
if not defaultLevelDimension then missing[#missing + 1] = 'Level.GetDimension' end
if not defaultGridTrapDoor then missing[#missing + 1] = 'GridEntity.ToTrapDoor' end
if not defaultRoomGreedTimer then missing[#missing + 1] = 'Room.GetGreedWaveTimer' end
assert(#missing == 0, 'missing APIs: ' .. table.concat(missing, ', '))
)lua";
    LuaRuntime::SetRuntimeExtensionInstaller(InspectDefaultSurface);
    const auto result = LuaRuntime::InitializeFromBuffer(
        script, std::strlen(script), "@repentogon-world-default-vm.lua");
    if (result == LuaRuntime::LuaInitResult::Success) return 0;
    char error[2048]{};
    static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
    std::fprintf(stderr, "%s\n", error);
    return 1;
}
'''

BEHAVIOR = r'''
#include "interfaces/lua/repentogon_world_api.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
#include "game_observer.hpp"

#include <cstdint>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>

extern "C" {
#include "lauxlib.h"
}

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_TrapDoorBytes;
std::vector<unsigned char> g_RockBytes;
std::vector<unsigned char> g_WrongTypeBytes;

constexpr std::uintptr_t kTrapDoorVtable = 0xA38120;
constexpr std::uint32_t kTrapDoorType = 17;
constexpr std::uint32_t kRockType = 2;
constexpr std::uintptr_t kGreedTimerOffset = 0x7910;

template <typename T>
void WriteAt(std::vector<unsigned char>& bytes, std::size_t offset, T value) {
    std::memcpy(bytes.data() + offset, &value, sizeof(value));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& bytes) {
    return reinterpret_cast<std::uintptr_t>(bytes.data());
}

void PublishNativeState() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uintptr_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uintptr_t), 0);
    g_GameBytes.assign(kLevelCurrentRoomDimensionOffset + sizeof(std::uint32_t), 0);
    g_RoomBytes.assign(0x8000, 0);
    g_TrapDoorBytes.assign(0x40, 0);
    g_RockBytes.assign(0x40, 0);
    g_WrongTypeBytes.assign(0x40, 0);

    WriteAt<std::uintptr_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset,
                            AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uintptr_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
    WriteAt<std::uint32_t>(g_GameBytes, kLevelCurrentRoomDimensionOffset, 1);
    WriteAt<std::uintptr_t>(g_GameBytes, 0x21550,
                            AddressOf(g_RoomBytes));
    WriteAt<std::int32_t>(g_RoomBytes, kGreedTimerOffset, 240);
    const unsigned char greedGuard[]={0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf6,0x57,0x02,0xa9};
    std::memcpy(g_ModuleBytes.data()+0x46bd50,greedGuard,sizeof(greedGuard));

    const auto base = AddressOf(g_ModuleBytes);
    WriteAt<std::uintptr_t>(g_TrapDoorBytes, 0,
                            base + kTrapDoorVtable);
    WriteAt<std::uint32_t>(g_TrapDoorBytes, kGridEntityTypeOffset,
                           kTrapDoorType);
    WriteAt<std::uintptr_t>(g_RockBytes, 0,
                            base + kGridEntity_RockVtableOffset);
    WriteAt<std::uint32_t>(g_RockBytes, kGridEntityTypeOffset, kRockType);
    WriteAt<std::uintptr_t>(g_WrongTypeBytes, 0,
                            base + kTrapDoorVtable);
    WriteAt<std::uint32_t>(g_WrongTypeBytes, kGridEntityTypeOffset, 16);

    LuaRuntime::SetEngineModuleBase(base);
    LuaRuntime::SetGameBindings(base + kGameOwnerGlobalSlotOffset, 0);
}

void InstallTestBindings(lua_State* state) noexcept {
    luaL_getmetatable(state, LuaRuntime::kLevelMetatable);
    lua_pushcfunction(state, isaac::runtime::RepentogonLevelGetDimension);
    lua_setfield(state, -2, "GetDimension");
    lua_pop(state, 1);

    luaL_getmetatable(state, LuaRuntime::kGridEntityMetatable);
    lua_getfield(state, -1, "__methods");
    lua_pushcfunction(state, isaac::runtime::RepentogonGridToTrapDoor);
    lua_setfield(state, -2, "ToTrapDoor");
    lua_pop(state, 2);

    lua_pushcfunction(state, [](lua_State* lua) -> int {
        luaL_checkudata(lua, 1, LuaRuntime::kRoomMetatable);
        lua_getmetatable(lua, 1);
        lua_getfield(lua, -1, "__index");
        lua_pushcfunction(lua, isaac::runtime::RepentogonRoomGetGreedWaveTimer);
        lua_setfield(lua, -2, "GetGreedWaveTimer");
        lua_pushcfunction(lua, isaac::runtime::RepentogonRoomSetGreedWaveTimer);
        lua_setfield(lua, -2, "SetGreedWaveTimer");
        lua_pop(lua, 2);
        return 0;
    });
    lua_setglobal(state, "_installRoomMethods");

    isaac::runtime::PushGridEntityHandle(state, AddressOf(g_TrapDoorBytes));
    lua_setglobal(state, "trapdoor");
    isaac::runtime::PushGridEntityHandle(state, AddressOf(g_RockBytes));
    lua_setglobal(state, "rock");
    isaac::runtime::PushGridEntityHandle(state, AddressOf(g_WrongTypeBytes));
    lua_setglobal(state, "wrongType");
}

} // namespace

GameRoomObservation ReadCurrentGameRoom(std::uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomUnreadable;
    *room = g_RoomBytes.data();
    return g_RoomBytes.empty() ? GameRoomObservation::RoomUnreadable
                               : GameRoomObservation::Success;
}

int main() {
    PublishNativeState();
    LuaRuntime::ObserveGameThread();
    LuaRuntime::SetRuntimeExtensionInstaller(InstallTestBindings);

    constexpr const char* script = R"lua(
savedLevel = Game():GetLevel()
assert(savedLevel:GetDimension() == 1)
assert(not pcall(function() return savedLevel:GetDimension(1) end))
if type(_installRoomMethods)~='function' then error('room installer missing') end
local room=Game():GetRoom();if room==nil then error('room nil') end
_installRoomMethods(room)
assert(room:GetGreedWaveTimer()==240)
room:SetGreedWaveTimer(17)
assert(room:GetGreedWaveTimer()==17)
assert(not pcall(function() room:GetGreedWaveTimer(1) end))
assert(not pcall(function() room:SetGreedWaveTimer({}) end))

local trap = trapdoor:ToTrapDoor()
assert(trap ~= nil and trap:GetType() == 17)
assert(rock:ToTrapDoor() == nil)
assert(wrongType:ToTrapDoor() == nil)
assert(not pcall(function() return trapdoor:ToTrapDoor(1) end))
assert(not pcall(function() return trapdoor.ToTrapDoor({}) end))
)lua";
    auto result = LuaRuntime::InitializeFromBuffer(
        script, std::strlen(script), "@repentogon-world-behavior.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }

    // A live handle whose backing object disappeared must degrade to nil, not cast.
    WriteAt<std::uintptr_t>(g_TrapDoorBytes, 0, 0);
    WriteAt<std::uintptr_t>(g_OwnerSlotBytes, 0, 0);
    constexpr const char* expired = R"lua(
assert(trapdoor:ToTrapDoor() == nil)
assert(not pcall(function() return savedLevel:GetDimension() end))
)lua";
    result = LuaRuntime::InitializeFromBuffer(
        expired, std::strlen(expired), "@repentogon-world-expired.lua");
    if (result == LuaRuntime::LuaInitResult::Success) return 0;
    char error[2048]{};
    static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
    std::fprintf(stderr, "%s\n", error);
    return 2;
}
'''


class RepentogonWorldApiDefaultVmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="repentogon-world-api-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "default-vm",
            harness_source=DEFAULT_VM_CHECK,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_default_vm_exposes_both_owners(self) -> None:
        result = subprocess.run(
            [str(self.binary)],
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class RepentogonWorldApiBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="repentogon-world-api-behavior-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "behavior",
            harness_source=BEHAVIOR,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_dimension_and_exact_trapdoor_downcast(self) -> None:
        result = subprocess.run(
            [str(self.binary)],
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
