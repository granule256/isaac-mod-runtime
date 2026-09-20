"""`Input.IsActionTriggered/IsActionPressed/GetActionValue` 的**调用约定**测试。

## 为什么需要它（真机 bug，2026-09-16）

模组开关菜单"按了没反应"。真机读数排除了脚本、字体、绑定之外的所有可能：0~27 号动作 ×
controller 0/1 全问一遍、玩家按遍所有键，**回答"是"的一个都没有**。

真因在这三个绑定**不是函数本体而是游戏自己的入口跳板**，逐字节读出来是：

    adrp x0, <g_Manager> ; ldr x0, [x0, #0x768]   → x0 = Manager 单例
    mov  x3, xzr                                  → x3 = 0（尾随实体参数清零）
    b    <真函数>

真函数签名是 `(Manager*, u32 action, u32 controller, void* entity)`，跳板只补 x0 与 x3，
**动作号在 x1、手柄序号在 x2**。照 PC 的形态 `query(action, controller)` 调用，会把动作号塞进
x0（被覆盖）、手柄序号塞进 x1（被当成动作号）⇒ 引擎永远答"没按下"。

这条测试用**假的跳板**（记录它收到了什么）驱动真实的 handler，钉住"动作号必须落到第 2 个参数、
手柄序号落到第 3 个参数"。它不依赖真机、不依赖游戏。

## 2026-09-20（批次 107）追加：`IsActionTriggered` 改成"问按住、自己算边沿"

真机上引擎那条"刚按下"**从来没答过 true**（同一条控制器、同一个动作，`IsActionPressed` 通、
`IsActionTriggered` 永远假）⇒ EID 的"库存概况"导航按下去没反应。本批把它换成
"问引擎的**按住** + Runtime 自己算上升沿"，所以这条测试追加了三段：**按住（不算边沿）→ 松开 →
再按住（报一次边沿）**，并断言引擎那条 Triggered 跳板**一次都不再被调用**。
"""

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
SRC = ROOT / "runtime" / "src"

DRIVER = textwrap.dedent(
    r"""
    #include "interfaces/lua/input_api.hpp"

    #include "lua_runtime.hpp"

    extern "C" {
    #include <lauxlib.h>
    #include <lualib.h>
    }
    
    #include <chrono>
    #include <cstdio>
    #include <cstring>
    #include <thread>

    // 假跳板：记录它收到的 (x0 占位, x1, x2)，并按脚本给的答案回答。
    namespace {
    int failures = 0;
    void Check(bool condition, const char* what) {
        if (!condition) { std::printf("FAILED_CHECK %s\n", what); ++failures; }
    }

    struct Call { void* self; unsigned action; unsigned controller; };
    Call g_lastTriggered{nullptr, 0xFFFFFFFFu, 0xFFFFFFFFu};
    Call g_lastPressed{nullptr, 0xFFFFFFFFu, 0xFFFFFFFFu};
    Call g_lastValue{nullptr, 0xFFFFFFFFu, 0xFFFFFFFFu};
    bool g_triggeredAnswer = false;
    float g_valueAnswer = 0.0f;
    //: 哪些动作"此刻被按住"（按动作号取位）。测试在几次脚本执行之间改它，模拟"按住/松开"。
    unsigned g_heldActions = 0;

    bool FakeTriggered(void* self, unsigned action, unsigned controller) {
        g_lastTriggered = {self, action, controller};
        return g_triggeredAnswer;
    }
    //: "按住"那条绑定的**调用序列**（前几次的动作号）—— `IsActionTriggered` 也走它，
    //: 所以序列里应当能看到"先 13（来自 IsActionTriggered）、再 15（来自 IsActionPressed）"。
    unsigned g_pressedHistory[8] = {};
    unsigned g_pressedHistoryCount = 0;

    bool FakePressed(void* self, unsigned action, unsigned controller) {
        g_lastPressed = {self, action, controller};
        if (g_pressedHistoryCount < 8) {
            g_pressedHistory[g_pressedHistoryCount++] = action;
        }
        return ((g_heldActions >> (action & 31u)) & 1u) != 0;
    }
    float FakeValue(void* self, unsigned action, unsigned controller) {
        g_lastValue = {self, action, controller};
        return g_valueAnswer;
    }

    // 脚本跑三次，用来验**端到端的上升沿**：按住 → 松开 → 再按住。
    // ★ 2026-09-20（批次 107）：`IsActionTriggered` 不再问引擎那条"刚按下"（真机上它永远是假），
    // 而是问引擎的"按住"（`g_heldActions` 决定）、再由 Runtime 自己算边沿。
    const char* kScript = R"LUA(
        local results = {}
        results[1] = Input.IsActionTriggered(13, 1)          -- 动作 13、手柄 1
        results[2] = Input.IsActionTriggered(14, 0)          -- 动作 14、手柄 0
        results[3] = Input.IsActionPressed(15, 1)
        results[4] = Input.GetActionValue(16, 1)
        captured = results
    )LUA";
    } // namespace

    int main() {
        // 注意参数顺序：`SetInputBindings(isActionPressed, isActionTriggered, getActionValue)`
        // —— **第一个是"按住"、第二个才是"刚按下"**（第一次写这个用例时把两者传反了，
        // 于是记录出来的动作号正好互换；这类顺序错误只有"检查收到什么"才抓得住）。
        LuaRuntime::SetInputBindings(reinterpret_cast<uintptr_t>(&FakePressed),
                                     reinterpret_cast<uintptr_t>(&FakeTriggered),
                                     reinterpret_cast<uintptr_t>(&FakeValue));
        lua_State* state = luaL_newstate();
        if (state == nullptr) { std::printf("FAILED_CHECK luaL_newstate\n"); return 1; }
        // 不需要 `luaL_openlibs`：本用例只调我们自己的 handler（harness 也不编 `linit.c`）。
        // 与运行时准备阶段同路：建 `Input` 表并挂上 handler（`lua_runtime.cpp` 里
        // `RegisterNeutralInputApi` 做的就是这两句）。
        lua_newtable(state);
        static_cast<void>(isaac::runtime::AttachInputMethods(state));
        lua_setglobal(state, "Input");

        g_valueAnswer = 0.5f;
        const auto run_script = [&]() {
            if (luaL_dostring(state, kScript) != LUA_OK) {
                std::printf("FAILED_CHECK script error: %s\n", lua_tostring(state, -1));
                failures += 1;
            }
        };
        //: 读 `captured[index]`（脚本每次执行都会覆盖它）。
        const auto captured_flag = [&](int index) {
            lua_getglobal(state, "captured");
            if (!lua_istable(state, -1)) { lua_pop(state, 1); return -1; }
            lua_rawgeti(state, -1, index);
            const int value = lua_toboolean(state, -1);
            lua_pop(state, 2);
            return value;
        };

        // ---- 第 1 次：动作 13 与 15 被按住（13 是首次观察 ⇒ **不算边沿**）------------
        g_heldActions = (1u << 13) | (1u << 15);
        run_script();
        Check(captured_flag(1) == 0, "首次观察（按住）不算边沿");
        // ★ 约定：动作号落在第 2 个参数、手柄序号落在第 3 个（第 1 个是被跳板覆盖的占位）。
        //   而且**"刚按下"这条 API 现在问的是"按住"那个绑定** ⇒ 序列里先 13（IsActionTriggered）
        //   再 15（IsActionPressed），而引擎那条 Triggered 跳板**一次都不该被调用**（真机上它永远是假）。
        // 脚本里的三次动作查询**全部**走"按住"那条绑定，按脚本顺序 = 13、14、15。
        Check(g_pressedHistoryCount >= 3 && g_pressedHistory[0] == 13 &&
                  g_pressedHistory[1] == 14 && g_pressedHistory[2] == 15,
              "IsActionTriggered/IsActionPressed 都应当把动作号交给**按住**那条绑定");
        Check(g_lastTriggered.action == 0xFFFFFFFFu,
              "引擎那条\"刚按下\"跳板不该再被调用（真机上它永远是假）");

        // ---- 第 2 次：松开（不报边沿）--------------------------------------------
        // ⚠️ 批次 109/110 起边沿是**按帧**判、并且"松手"要连续超过去抖窗口（6 帧）才算真松手
        // ⇒ 三次脚本执行之间必须睡够（把窗口跨过去）。宿主上没有引擎，帧号走"毫秒 / 4"兜底
        // ⇒ 睡 40 毫秒 ≈ 10 帧 > 窗口（真机上用的是引擎自己的帧计数，每帧必进）。
        std::this_thread::sleep_for(std::chrono::milliseconds(40));
        g_heldActions = 0;
        run_script();
        Check(captured_flag(1) == 0, "松开不报边沿");
        Check(captured_flag(2) == 0, "松开（另一个动作）不报边沿");
        Check(captured_flag(3) == 0, "IsActionPressed 松开时为 false");
        Check(captured_flag(4) == 1, "GetActionValue 的 0.5 在 Lua 里是真值");

        // ---- 第 3 次：再按住 ⇒ **这次才是真正的上升沿** ---------------------------
        std::this_thread::sleep_for(std::chrono::milliseconds(40));
        g_heldActions = (1u << 13) | (1u << 15);
        run_script();
        Check(captured_flag(1) == 1, "松开后再按住 = 上升沿，必须为 true");
        Check(captured_flag(2) == 0, "没被按住的另一个动作仍为 false");
        Check(captured_flag(3) == 1, "IsActionPressed 按住时为 true");
        Check(captured_flag(4) == 1, "GetActionValue 的 0.5 在 Lua 里是真值");
        Check(g_lastValue.action == 16 && g_lastValue.controller == 1,
              "GetActionValue 应当把 (动作=16, 手柄=1) 放进 x1/x2");
        // 数值透传：`captured[4]` 必须**是** 0.5（不是"真值"）。
        lua_getglobal(state, "captured");
        lua_rawgeti(state, -1, 4);
        Check(lua_tonumber(state, -1) == 0.5, "GetActionValue 的 float 必须透传");
        lua_pop(state, 2);

        std::printf("RECORDED triggered=(%u,%u) pressed=(%u,%u) value=(%u,%u)\n",
                    g_lastTriggered.action, g_lastTriggered.controller,
                    g_lastPressed.action, g_lastPressed.controller,
                    g_lastValue.action, g_lastValue.controller);

        lua_close(state);
        if (failures == 0) { std::printf("INPUT_ABI_CHECKS_PASSED\n"); }
        return failures == 0 ? 0 : 1;
    }
    """
)


class InputBindingAbiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-input-abi-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name),
            harness_source=DRIVER,
        )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_input_binding_calling_convention(self):
        result = subprocess.run([str(self.binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("INPUT_ABI_CHECKS_PASSED", result.stdout)
        self.assertNotIn("FAILED_CHECK", result.stdout)


if __name__ == "__main__":
    unittest.main()
