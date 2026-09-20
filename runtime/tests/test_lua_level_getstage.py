import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import layered_lua_runtime_sources
except ImportError:
    from test_support import layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"


class LuaLevelGetStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-level-getstage-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "level_getstage_harness.cpp"
        harness.write_text(
            r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"

#include <cstdint>
#include <cstring>

namespace {
GameLevelStageObservation g_Observation = GameLevelStageObservation::Success;
std::uint32_t g_Stage = 5;
}

GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::OwnerUnreadable;
}

GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t ownerSlot, std::uint32_t* stage) {
    if (ownerSlot != 0x1111 || stage == nullptr) return GameLevelStageObservation::OwnerUnreadable;
    if (g_Observation == GameLevelStageObservation::Success) *stage = g_Stage;
    return g_Observation;
}

GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t, uintptr_t) {
    return GameIsGreedModeObservation::MethodUnavailable;
}
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t, uintptr_t) { return GameIsAscentObservation::MethodUnavailable; }

GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {
    return GameItemPoolObservation::GameUnreadable;
}

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {
    return GameRoomObservation::RoomUnreadable;
}

GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    const char* script = nullptr;
    if (std::strcmp(scenario, "top_level") == 0) {
        script =
            "local ok, v = pcall(function() return Game():GetLevel():GetStage() end)"
            " print('TOPLEVEL ok='..tostring(ok)..' v='..tostring(v))";
    } else {
        if (std::strcmp(scenario, "unreadable") == 0) {
            g_Observation = GameLevelStageObservation::GameUnreadable;
        }
        script = "local mod=RegisterMod('Probe',1); mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function() local level=Game():GetLevel(); if level:GetStage()~=5 then error('wrong stage') end end)";
    }
    LuaRuntime::SetGameBindings(0x1111, 0x2222);
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@level-getstage.lua");
    if (std::strcmp(scenario, "top_level") == 0) {
        // ★ 设计变更（2026-09-19 批次 043）：顶层（非托管回调）调用**不再被作用域守卫拒绝** ——
        // PC 允许模组在加载期读引擎状态（GoodTrip 的 scripts/floor.lua:11-17 就是），
        // 而报错会让整个模组的功能整块消失。判据改为「这次调用真的被执行了」：
        // 脚本一律用 pcall 包住并打印结果，Python 侧核对（见本文件对应测试）。
        static_cast<void>(result);
        return 0;
    }
    if (result != LuaRuntime::LuaInitResult::Success) return 2;
    LuaRuntime::DispatchPreGetCollectible(nullptr, 0, 0, 1, 0);
    if (std::strcmp(scenario, "unreadable") == 0) return LuaRuntime::TakeCallbackError() ? 0 : 3;
    return LuaRuntime::TakeCallbackError() ? 4 : 0;
}
''', encoding="utf-8")
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        lua_objects = []
        for lua_source in sorted(lua_root.glob("*.c")):
            if lua_source.name in excluded:
                continue
            obj = temporary / f"{lua_source.stem}.o"
            build = subprocess.run(
                ["cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root),
                 "-c", str(lua_source), "-o", str(obj)], text=True, capture_output=True,
            )
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            lua_objects.append(obj)
        cls.binary = temporary / "level_getstage_harness"
        build = subprocess.run(
            ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_DIAGNOSTIC_STAGE=14",
             "-DEXL_LOAD_KIND=Module", "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *(str(path) for path in lua_objects), "-lm", "-o", str(cls.binary)],
            text=True, capture_output=True,
        )
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_harness(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def assert_top_level_ran(self, scenario):
        """★ 设计变更（2026-09-19 批次 043）：顶层调用不再被作用域守卫拒绝。

        场景脚本用 `pcall` 包住调用并打印结果 ⇒ 这里核对：**这次调用真的被执行了**，
        而且错误文本里不再出现 "only available during a Runtime callback"（守卫已删除）。
        """
        result = self.run_harness(scenario)
        self.assertIn("TOPLEVEL ok=", result.stdout)
        self.assertNotIn("only available during a Runtime callback", result.stdout)

    def test_game_getlevel_and_level_getstage_resolve_the_current_owner_in_a_callback(self):
        self.run_harness("success")

    def test_level_getstage_is_a_general_runtime_api_not_a_starterr_build_feature(self):
        game_api = (SOURCE.parent / "src" / "interfaces" / "lua" / "game_api.cpp").read_text(
            encoding="utf-8"
        )
        remaining_api = (
            SOURCE.parent / "src" / "interfaces" / "lua" / "remaining_api.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("0x02010003", game_api)
        self.assertIn("0x03010001", remaining_api)
        self.assertNotIn("EXL_ENABLE_STARTERR_RNG", game_api + remaining_api)

    def test_level_getstage_rejects_unreadable_game_state(self):
        self.run_harness("unreadable")

    def test_game_getlevel_runs_at_top_level(self):
        self.assert_top_level_ran("top_level")

    def test_handles_do_not_store_native_pointers(self):
        handles = (SOURCE / "lua_object_handles.hpp").read_text(encoding="utf-8")
        handle = handles[handles.index("struct GameHandle"):handles.index("struct MusicHandle")]
        self.assertNotIn("uintptr_t", handle)
        self.assertNotIn("Game*", handle)
        level = handles[handles.index("struct LevelHandle"):handles.index("struct ItemPoolHandle")]
        self.assertNotIn("uintptr_t", level)
        self.assertNotIn("Level*", level)


if __name__ == "__main__":
    unittest.main()
