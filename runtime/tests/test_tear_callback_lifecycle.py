"""Only real native tear Init publishes INIT, before AddEntity and fire."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import test_lua_entity_query as fixture
from . import test_support


MAIN = r'''
#include "interfaces/lua/entity_lifetime.hpp"
#include "native_room_events.hpp"
static GameLocationKey location{84, 0, 1, 0};
GameRoomObservation ReadGameLocationKey(uintptr_t, GameLocationKey* key) {
    *key = location;
    return GameRoomObservation::Success;
}
int main(int argc, char** argv) {
    if (argc != 2) return 90;
    static_cast<void>(kScriptTemplate);
    static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);
    CreateBlocks(); FillEntities(); PublishLists(); PublishGame();
    PublishEntityList(g_RoomBytes, true);
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
    LuaRuntime::SetGameBindings(g_EngineBase + kGameOwnerGlobalSlotOffset, 0x2222);
    const std::string mode = argv[1];
    std::string script = R"lua(
local m = RegisterMod('tear lifecycle', 1)
initCount, fireCount, promoted = 0, 0, 0
m:AddCallback(ModCallbacks.MC_POST_TEAR_INIT, function(_, t)
    assert(not t:GetData().initialized, 'duplicate INIT in one lifetime')
    t:GetData().initialized = true
    initCount = initCount + 1
end, 0)
m:AddCallback(ModCallbacks.MC_POST_TEAR_INIT, function()
    error('wrong variant filter')
end, 999)
)lua";
    if (mode == "filtered_nonmatching") {
        script.replace(script.find("end, 0)"), std::strlen("end, 0)"), "end, 998)");
    }
    if (mode != "init_only") script += R"lua(
m:AddCallback(ModCallbacks.MC_POST_FIRE_TEAR, function(_, t)
    fireCount = fireCount + 1
    if t:GetData().initialized then promoted = promoted + 1 end
end)
)lua";
    if (LuaRuntime::InitializeFromBuffer(script.data(), script.size(), "@tear-lifecycle.lua") !=
        LuaRuntime::LuaInitResult::Success) return 1;
    const auto tear = AddressOf(g_Entities[kTearNear]);
    // Native Init happens before publication in the room live table.
    WriteAt<std::uint32_t>(g_RoomBytes,
        kRoomEntityListOffset + kEntityListLiveCountOffset, 0);
    if (mode != "fire_only") LuaRuntime::DispatchNativeTearInit(tear);
    PublishEntityList(g_RoomBytes, true);
    if (mode == "scan_first") LuaRuntime::DispatchPostUpdate();
    LuaRuntime::DispatchPostFireTear(tear);
    const double expectedInit = mode == "filtered_nonmatching" || mode == "fire_only" ? 0 : 1;
    if (!ExpectNumber("initCount", expectedInit) ||
        !ExpectNumber("fireCount", mode == "init_only" ? 0 : 1) ||
        !ExpectNumber("promoted", mode == "init_only" || mode == "filtered_nonmatching" || mode == "fire_only" ? 0 : 1)) return 2;
    LuaRuntime::DispatchPostUpdate();
    if (!ExpectNumber("initCount", expectedInit)) return 3;
    if (mode == "reuse" || mode == "room" || mode == "repeat_init") {
        // D2 retires the old identity even when allocator address/seed/frame all repeat.
        if (mode == "repeat_init") isaac::runtime::ReinitializeEntityLifetime(tear);
        else isaac::runtime::RetireEntityLifetime(tear);
        if (mode == "room") {
            ++location.roomIndex;
            isaac::runtime::NoteNativeRoomLoaded();
        }
        LuaRuntime::DispatchNativeTearInit(tear);
        LuaRuntime::DispatchPostFireTear(tear);
        LuaRuntime::DispatchPostUpdate();
        if (!ExpectNumber("initCount", 2) || !ExpectNumber("promoted", 2)) return 4;
    }
    if (mode == "surviving_room") {
        ++location.roomIndex;
        isaac::runtime::NoteNativeRoomLoaded();
        LuaRuntime::DispatchPostUpdate();
        if (!ExpectNumber("initCount", 1)) return 5;
    }
    if (LuaRuntime::TakeCallbackError()) {
        LuaRuntime::LuaErrorHistoryEntryView errors[16]{};
        const auto count = LuaRuntime::CopyLuaErrorHistory(errors, 16);
        for (std::size_t i = 0; i < count; ++i) std::puts(errors[i].text);
        return 6;
    }
    return 0;
}
'''


class TearCallbackLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="isaac-tear-lifecycle-")
        flags = tuple(flag for flag in test_support.HARNESS_COMPILE_FLAGS
                      if not flag.startswith("-DEXL_DIAGNOSTIC_STAGE="))
        with patch.object(test_support, "HARNESS_COMPILE_FLAGS", flags):
            cls.binary = test_support.build_lua_harness(
                source_root=fixture.SOURCE, workdir=Path(cls.temp.name),
                harness_source=fixture.HARNESS.split("int main(", 1)[0] + MAIN)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_native_init_only_and_scan_never_synthesizes_init(self):
        for mode in ("native", "scan_first", "init_only", "reuse", "room", "surviving_room", "repeat_init", "fire_only"):
            with self.subTest(mode=mode):
                result = subprocess.run([str(self.binary), mode], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nonmatching_init_filter_does_not_suppress_fire(self):
        result = subprocess.run([str(self.binary), "filtered_nonmatching"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
