"""RoomConfig lookup uses the native RoomConfig receiver and existing RoomConfig views."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_world_api import BEHAVIOR, SOURCE

EXTRA = r'''
static std::vector<unsigned char> g_RoomSet0;
static std::vector<unsigned char> g_RoomSet1;
static unsigned getRoomCalls;
static unsigned modeMinusOneCalls;
static unsigned modeMinusTwoCalls;
static unsigned modeCoercedCalls;

static void* GetRoom(void* receiver, std::uint32_t stage, std::uint32_t type,
                     std::uint32_t variant, std::int32_t mode) {
    ++getRoomCalls;
    assert(receiver == g_GameBytes.data() +
                           isaac::runtime::mod_rooms::kGameRoomConfigOffset);
    if (mode == -1) ++modeMinusOneCalls;
    if (mode == -2) ++modeMinusTwoCalls;
    if (mode == 2) ++modeCoercedCalls;
    if (stage == 0 && type == 1 && variant == 0) {
        return g_RoomSet0.data();
    }
    if (stage == 0 && type == 2 && variant == UINT32_MAX) {
        return g_RoomSet0.data() + 0x80;
    }
    if (stage == 36 && type == 29 && variant == 77 && mode == 1) {
        return g_RoomSet1.data();
    }
    return nullptr;
}

static int CorruptGuard(lua_State*) {
    g_ModuleBytes[0x49340c] ^= 1;
    return 0;
}

static int RestoreGuard(lua_State*) {
    g_ModuleBytes[0x49340c] ^= 1;
    return 0;
}

static void PublishRoomConfigFixtures() {
    const auto& roomConfigLayout =
        isaac::runtime::api500_world::kLayouts[6];
    std::memcpy(g_ModuleBytes.data() + roomConfigLayout.offset,
                roomConfigLayout.bytes.data(), roomConfigLayout.bytes.size());
    g_RoomSet0.assign(2 * 0x80, 0);
    g_RoomSet1.assign(0x80, 0);
    constexpr std::size_t set0 = 0x21b78 + 0x68;
    constexpr std::size_t set1 = 0x21b78 + 36 * 0x100 + 1 * 0x48 + 0x68;
    WriteAt<std::uintptr_t>(g_GameBytes, set0 + 0x18, AddressOf(g_RoomSet0));
    WriteAt<std::uint32_t>(g_GameBytes, set0 + 0x20, 2);
    WriteAt<std::uintptr_t>(g_GameBytes, set1 + 0x18, AddressOf(g_RoomSet1));
    WriteAt<std::uint32_t>(g_GameBytes, set1 + 0x20, 1);
    WriteAt<std::uint32_t>(g_RoomSet0, 0x00, 0);
    WriteAt<std::uint32_t>(g_RoomSet0, 0x04, 0);
    WriteAt<std::int32_t>(g_RoomSet0, 0x08, 1);
    WriteAt<std::uint32_t>(g_RoomSet0, 0x0c, 0);
    WriteAt<std::uint32_t>(g_RoomSet0, 0x40, 0x34);
    WriteAt<std::int32_t>(g_RoomSet0, 0x5c, 3);
    WriteAt<std::uint32_t>(g_RoomSet0, 0x80, 0);
    WriteAt<std::uint32_t>(g_RoomSet0, 0x84, 0);
    WriteAt<std::int32_t>(g_RoomSet0, 0x88, 2);
    WriteAt<std::uint32_t>(g_RoomSet0, 0x8c, UINT32_MAX);
    WriteAt<std::uint32_t>(g_RoomSet0, 0xc0, 0x78);
    WriteAt<std::int32_t>(g_RoomSet0, 0xdc, 4);
    WriteAt<std::uint32_t>(g_RoomSet1, 0x00, 36);
    WriteAt<std::uint32_t>(g_RoomSet1, 0x04, 1);
    WriteAt<std::int32_t>(g_RoomSet1, 0x08, 29);
    WriteAt<std::uint32_t>(g_RoomSet1, 0x0c, 77);
    WriteAt<std::uint32_t>(g_RoomSet1, 0x40, 0xbc);
    WriteAt<std::int32_t>(g_RoomSet1, 0x5c, 5);
}

static void InstallRoomConfig(lua_State* state) {
    isaac::runtime::RegisterRepentogonRoomConfigApi(state);
    lua_getglobal(state, "RoomConfig");
    lua_pushcfunction(
        state,
        isaac::runtime::RepentogonRoomConfigGetRoomByStageTypeAndVariant);
    lua_setfield(state, -2, "GetRoomByStageTypeAndVariant");
    lua_pop(state, 1);
    lua_pushcfunction(state, CorruptGuard);
    lua_setglobal(state, "_corruptRoomConfigGuard");
    lua_pushcfunction(state, RestoreGuard);
    lua_setglobal(state, "_restoreRoomConfigGuard");
}
'''

ROOM_SCRIPT = r'''
_corruptRoomConfigGuard()
local ok, err = pcall(function()
    return RoomConfig.GetRoomByStageTypeAndVariant(0, 1, 0)
end)
assert(not ok and string.find(err, "guard"))
_restoreRoomConfigGuard()

local config = RoomConfig.GetRoomByStageTypeAndVariant(0, 1, 0)
assert(config and config.Type == 1 and config.Variant == 0)
assert(type(config.Mode) == "number" and config.Mode == 0)
assert(config.Shape == 3 and config.Doors == 0x34)
assert(RoomConfig.GetRoomByStageTypeAndVariant(0, 2, -1).Variant == 0xffffffff)
assert(RoomConfig.GetRoomByStageTypeAndVariant(0, 1, 0, 2).Type == 1)
assert(RoomConfig.GetRoomByStageTypeAndVariant(0, 1, 0, -2).Type == 1)
assert(RoomConfig.GetRoomByStageTypeAndVariant(0, 1, 0, 2, true).Type == 1)
local stage36 = RoomConfig.GetRoomByStageTypeAndVariant(36, 29, 77, 1)
assert(stage36 and stage36.Type == 29 and stage36.Variant == 77)
assert(type(stage36.Mode) == "number" and stage36.Mode == 1)
assert(stage36.Shape == 5 and stage36.Doors == 0xbc)
assert(RoomConfig.GetRoomByStageTypeAndVariant(1, 1, 0) == nil)

assert(not pcall(function()
    RoomConfig.GetRoomByStageTypeAndVariant(0, 1)
end))
assert(not pcall(function()
    RoomConfig.GetRoomByStageTypeAndVariant(-1, 1, 0)
end))
assert(not pcall(function()
    RoomConfig.GetRoomByStageTypeAndVariant(37, 1, 0)
end))
assert(not pcall(function()
    RoomConfig.GetRoomByStageTypeAndVariant(0, 0, 0)
end))
assert(not pcall(function()
    RoomConfig.GetRoomByStageTypeAndVariant(0, 30, 0)
end))
'''


class RepentogonRoomConfigApiTests(unittest.TestCase):
    def test_receiver_validation_and_existing_room_config_view(self):
        driver = (
            '#include "interfaces/lua/repentogon_room_config_api.hpp"\n'
            '#include "interfaces/lua/api500_world.guards.hpp"\n'
            '#include "mod_room_guards.hpp"\n' + BEHAVIOR
        )
        driver = driver.replace(
            "namespace {",
            "static int CorruptGuard(lua_State*);\n"
            "static int RestoreGuard(lua_State*);\n"
            "static void InstallRoomConfig(lua_State*);\n"
            "\nnamespace {",
            1,
        )
        driver = driver.replace(
            "g_GameBytes.assign(kLevelCurrentRoomDimensionOffset + sizeof(std::uint32_t), 0);",
            "g_GameBytes.assign(0x25000, 0);",
        )
        driver = driver.replace("int main() {", EXTRA + "\nint main() {")
        driver = driver.replace(
            "    PublishNativeState();",
            r'''
    PublishNativeState();
    PublishRoomConfigFixtures();
    const unsigned char getRoomGuard[] = {
        0xfd, 0x7b, 0xbc, 0xa9, 0xf7, 0x0b, 0x00, 0xf9,
        0xfd, 0x03, 0x00, 0x91, 0xf6, 0x57, 0x02, 0xa9,
    };
    std::memcpy(g_ModuleBytes.data() + 0x49340c, getRoomGuard,
                sizeof(getRoomGuard));
    isaac::runtime::SetRepentogonRoomConfigNativeTestBindings({GetRoom});
''',
        )
        driver = driver.replace(
            "    LuaRuntime::SetRuntimeExtensionInstaller(InstallTestBindings);",
            "    LuaRuntime::SetRuntimeExtensionInstaller(InstallTestBindings);\n"
            "    isaac::runtime::RegisterRepentogonRoomConfigApi(nullptr);",
        )
        driver = driver.replace(
            "    lua_setglobal(state, \"wrongType\");\n}",
            "    lua_setglobal(state, \"wrongType\");\n    InstallRoomConfig(state);\n}",
        )
        driver = driver.replace(
            "_installRoomMethods(room)\n",
            "_installRoomMethods(room)\n" + ROOM_SCRIPT,
        )
        driver = driver.replace(
            "    assert(LuaRuntime::ShutdownForModReload());",
            "    assert(getRoomCalls == 7);\n"
            "    assert(modeMinusOneCalls == 5 && modeMinusTwoCalls == 1 &&\n"
            "           modeCoercedCalls == 0);\n"
            "    assert(LuaRuntime::ShutdownForModReload());",
        )
        with tempfile.TemporaryDirectory(prefix="room-config-") as folder:
            extra = SOURCE.parent / "src/interfaces/lua/repentogon_room_config_api.cpp"
            added = (
                ()
                if extra in test_support.layered_lua_runtime_sources(SOURCE)
                else (extra,)
            )
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=driver,
                extra_sources=added,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
