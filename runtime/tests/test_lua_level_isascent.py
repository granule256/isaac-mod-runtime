import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

#: 本文件特有的那部分 harness：只覆盖 `Level:IsAscent` 的观测函数（行为由场景决定），
#: 其余观测函数与文件读取走 `test_support` 里的共享弱默认桩。
HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"

#include <cstdint>
#include <cstring>

namespace {
GameIsAscentObservation g_Observation = GameIsAscentObservation::AscentFalse;
}

// 覆盖共享默认桩（强符号优先）：`Level:IsAscent` 的行为由场景决定。
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t ownerSlot, uintptr_t method) {
    return ownerSlot == 0x1111 && method == 0x4444 ? g_Observation : GameIsAscentObservation::MethodUnavailable;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    if (std::strcmp(scenario, "unreadable") == 0) g_Observation = GameIsAscentObservation::GameUnreadable;
    if (std::strcmp(scenario, "true") == 0) g_Observation = GameIsAscentObservation::AscentTrue;
    const char* script = std::strcmp(scenario, "top_level") == 0 ?
        "local ok, v = pcall(function() return Game():GetLevel():IsAscent() end)"
        " print('TOPLEVEL ok='..tostring(ok)..' v='..tostring(v))" :
        (std::strcmp(scenario, "true") == 0 ?
         "local mod=RegisterMod('Probe',1); mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function() if Game():GetLevel():IsAscent()~=true then error('wrong ascent state') end end)" :
         "local mod=RegisterMod('Probe',1); mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function() if Game():GetLevel():IsAscent()~=false then error('wrong ascent state') end end)");
    LuaRuntime::SetGameBindings(0x1111, 0x2222);
    LuaRuntime::SetLevelIsAscentBinding(0x4444);
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@isascent.lua");
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
    // 批次 250：`unreadable` 不再"必须报错"—— 读不到时给**回退值 false**（脚本断言的正是
    // `IsAscent() == false`），所以两个场景一律只看"回调有没有**意外**抛错"。
    return LuaRuntime::TakeCallbackError() ? 4 : 0;
}
'''


class LuaLevelIsAscentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-isascent-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

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

    def test_level_isascent_is_a_general_runtime_api(self):
        self.run_harness("false")
        self.run_harness("true")

    def test_level_isascent_runs_at_top_level_and_falls_back_when_state_is_unreadable(self):
        """批次 250：`unreadable` 场景的口径从"必须抛错"改成"**回调不抛错**"。

        原断言 `run_harness("unreadable")` 期望 harness 退出码 3（= 回调抛了错）；
        现在 `Level:IsAscent()` 读不到时给回退值 `false`，与脚本里写的期望值一致
        ⇒ 回调正常走完（harness 只在"意外抛错"时给非 0）。
        理由见 `native_state_fallback.hpp`：抛错会摘掉整条模组回调，代价远大于一个值不对。
        """
        self.assert_top_level_ran("top_level")
        self.run_harness("unreadable")

    def test_isascent_registration_has_no_mod_specific_build_gate(self):
        api = (
            SOURCE.parent / "src" / "interfaces" / "lua" / "remaining_api.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("0x03010002", api)
        self.assertNotIn("INSTANT_RESTART", api)


if __name__ == "__main__":
    unittest.main()
