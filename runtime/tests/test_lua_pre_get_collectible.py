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


class PreGetCollectibleDeclarationTests(unittest.TestCase):
    def test_runtime_declares_the_pre_get_collectible_callback_boundary(self):
        header = (SOURCE / "lua_runtime.hpp").read_text(encoding="utf-8")
        self.assertIn("std::uint64_t DispatchPreGetCollectible(", header)


class LuaPreGetCollectibleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-pre-get-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "lua_pre_get_harness.cpp"
        harness.write_text(
            r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"

#include <cstdint>
#include <cstring>

GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::OwnerUnreadable;
}

GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t*) {
    return GameLevelStageObservation::GameUnreadable;
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

namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&, const char*, u8*, std::size_t, std::size_t*) {
    return TextReadResult::InvalidArgument;
}
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    const char* script = nullptr;
    if (std::strcmp(scenario, "nil") == 0) {
        script = "local mod=RegisterMod('Probe',1); "
                 "mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function(self) if self~=mod then error('update self') end RuntimeTest.MarkPostUpdate() end); "
                 "mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function(self,pool,decrease,seed) "
                 "if self~=mod or pool~=3 or decrease~=false or seed~=9 then error('pre args') end return nil end)";
    } else if (std::strcmp(scenario, "override") == 0) {
        script = "local mod=RegisterMod('Probe',1); "
                 "mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function(self,pool,decrease,seed) "
                 "if self~=mod or pool~=1 or decrease~=true or seed~=2 then error('override args') end return 733 end)";
    } else if (std::strcmp(scenario, "multi_later_returns") == 0) {
        // 同一 id 登记两条：第一条不返回、第二条返回 733 ⇒ 第二条的值生效。
        // ★ 这一条钉住批次 103 的改动：从前只取登记表第 0 条 ⇒ 第二条**永远不会被调用**。
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { first = 0, second = 0 } "
            "mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE, function() "
            "  _probe.first = _probe.first + 1 end) "
            "mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE, function() "
            "  _probe.second = _probe.second + 1 return 733 end)";
    } else if (std::strcmp(scenario, "multi_first_stops") == 0) {
        // 完整PC bootstrap：首个非nil生效，第二条不得再调用。
        script =
            "local mod = RegisterMod('Probe', 1) "
            "_probe = { first = 0, second = 0 } "
            "mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE, function() "
            "  _probe.first = _probe.first + 1 return 733 end) "
            "mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE, function() "
            "  _probe.second = _probe.second + 1 return 999 end)";
    } else if (std::strcmp(scenario, "bad_return") == 0) {
        script = "local mod=RegisterMod('Probe',1); "
                 "mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function(self) if self~=mod then error('update self') end RuntimeTest.MarkPostUpdate() end); "
                 "mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function() return true end)";
    } else {
        script = "local mod=RegisterMod('Probe',1); "
                 "mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function() return 0x100000000 end)";
    }
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@pre_get.lua") !=
        LuaRuntime::LuaInitResult::Success) return 1;
    if (std::strcmp(scenario, "nil") == 0) {
        const auto result = LuaRuntime::DispatchPreGetCollectible(nullptr, 3, 9, 1, 0);
        LuaRuntime::DispatchPostUpdate();
        return result == 0 && LuaRuntime::PostUpdateCount() == 1 && !LuaRuntime::TakeCallbackError() ? 0 : 2;
    }
    if (std::strcmp(scenario, "override") == 0) {
        // 打包口径（批次 103 起有两位）：bit 32 = 有替换值、bit 33 = **返回过非 nil**
        // ⇒ 回了一个整数时两位都置上：`(1<<33) | (1<<32) | 733`。
        return LuaRuntime::DispatchPreGetCollectible(nullptr, 1, 2, 0, 0) == 0x3000002DDULL &&
                       !LuaRuntime::TakeCallbackError()
                   ? 0
                   : 3;
    }
    if (std::strcmp(scenario, "multi_later_returns") == 0) {
        const auto multi = LuaRuntime::DispatchPreGetCollectible(nullptr, 1, 2, 0, 0);
        double first = 0, second = 0;
        // ⚠️ `ReadLuaTableNumber` **成功返回 0**（1/2/3 = 三种读不到的原因），
        // 别写成 `!ReadLuaTableNumber(...)` —— 那是"成功就报错"（本用例第一版正是这么写的）。
        if (LuaRuntime::ReadLuaTableNumber("_probe", "first", &first) != 0 || first != 1) return 7;
        if (LuaRuntime::ReadLuaTableNumber("_probe", "second", &second) != 0 || second != 1) return 8;
        if (multi != 0x3000002DDULL) return 9;
        return LuaRuntime::TakeCallbackError() ? 10 : 0;
    }
    if (std::strcmp(scenario, "multi_first_stops") == 0) {
        const auto multi = LuaRuntime::DispatchPreGetCollectible(nullptr, 1, 2, 0, 0);
        double first = 0, second = 0;
        // ⚠️ `ReadLuaTableNumber` **成功返回 0**（1/2/3 = 三种读不到的原因），
        // 别写成 `!ReadLuaTableNumber(...)` —— 那是"成功就报错"（本用例第一版正是这么写的）。
        if (LuaRuntime::ReadLuaTableNumber("_probe", "first", &first) != 0 || first != 1) return 7;
        if (LuaRuntime::ReadLuaTableNumber("_probe", "second", &second) != 0 || second != 0) return 8;
        // 完整PC bootstrap首733生效，第二条999未执行。
        if (multi != 0x3000002DDULL) return 9;
        return LuaRuntime::TakeCallbackError() ? 10 : 0;
    }
    // 完整PC消费者只取整数低32位：0x100000000变成零哨兵，保留原生成且不报错。
    // 类型转换错误没有正常返回值；下一次派发仍保留登记。
    const auto result = LuaRuntime::DispatchPreGetCollectible(nullptr, 1, 2, 1, 0);
    const bool conversionError = std::strcmp(scenario, "bad_return") == 0;
    if (result != 0 || LuaRuntime::TakeCallbackError() != conversionError) return 4;
    if (std::strcmp(scenario, "bad_return") == 0) {
        const auto second = LuaRuntime::DispatchPreGetCollectible(nullptr, 1, 2, 1, 0);
        if (second != 0 || !LuaRuntime::TakeCallbackError()) return 6;
    }
    LuaRuntime::DispatchPostUpdate();
    return std::strcmp(scenario, "bad_return") != 0 ||
                   (LuaRuntime::PostUpdateCount() == 1 && !LuaRuntime::TakeCallbackError())
               ? 0
               : 5;
}
'''.lstrip()
        )
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        lua_objects = []
        for lua_source in sorted(lua_root.glob("*.c")):
            if lua_source.name in excluded:
                continue
            output = temporary / (lua_source.stem + ".o")
            result = subprocess.run(
                ["cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root), "-c",
                 str(lua_source), "-o", str(output)],
                text=True, capture_output=True,
            )
            if result.returncode != 0:
                raise AssertionError(result.stdout + result.stderr)
            lua_objects.append(output)
        cls.harness = temporary / "lua_pre_get_harness"
        result = subprocess.run(
            ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *(str(path) for path in lua_objects), "-lm", "-o", str(cls.harness)],
            text=True, capture_output=True,
        )
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_harness(self, scenario):
        result = subprocess.run([str(self.harness), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nil_preserves_original_result_and_all_callbacks_receive_their_mod(self):
        self.run_harness("nil")

    def test_integer_result_is_an_explicit_collectible_override(self):
        self.run_harness("override")

    def test_nil_continues_and_first_integer_stops_remaining_registrations(self):
        """批次 103：这一条以前是**手工取第 0 条登记**（`g_CallbackRegistry.At(id, 0)`），
        第一条nil时第二条必须执行；第一条非nil时第二条必须停止。
        完整PC原main.lua已证明两种情况，不能把“支持多条登记”写成“无条件全部执行”。"""
        self.run_harness("multi_later_returns")
        self.run_harness("multi_first_stops")

    def test_invalid_non_nil_result_is_recorded_without_unregistering_the_callback(self):
        self.run_harness("bad_return")

    def test_integer_with_zero_low_word_preserves_original_without_an_error(self):
        self.run_harness("out_of_range")

    def test_runtime_pre_get_reentry_guard_is_not_thread_local(self):
        # This guard used to be `thread_local`, and that cost a hardware crash. In an
        # injected module, reading a `thread_local` on the game's MainThread calls
        # `__aarch64_read_tp()`, which is `mrs x0, tpidrro_el0 ; ldr x0, [x0, #504]` --
        # 0 for this module -- and the very next instruction dereferences that null.
        # Crash report `01789099948`: Result 0x4A8 (Data Abort), fault address 0x0,
        # PC = runtime+0x440c, reached from `Entity_Pickup::Init` through the
        # PreGetCollectible relay, i.e. as soon as a room spawns a pickup. It was the
        # only TLS access in the whole module.
        runtime = (SOURCE / "lua_runtime.cpp").read_text(encoding="utf-8")

        self.assertIn("bool g_InPreGetCollectibleDispatch = false;", runtime)
        self.assertNotIn("thread_local bool g_InPreGetCollectibleDispatch", runtime)
        self.assertIn("DispatchPreGetCollectible", runtime)


if __name__ == "__main__":
    unittest.main()
