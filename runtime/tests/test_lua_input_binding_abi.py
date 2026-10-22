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

## ★★ 2026-10-06（批次 381）再改：边沿 = "引擎帧上采样 + 纯读"

边沿**不再由"调用方什么时候问"决定**（口径与两张真机脸见 `docs/会话交接-20261006-一-*.md`
第 4 节）：每帧在"帧号自增之后、派发回调之前"由采样器写一次边沿表，`IsActionTriggered` /
`IsActionPressed` 退化成**纯读**。这条测试随之变成三层：

1. **调用约定**（本文件的原始职责）：仍由 `GetActionValue` 钉住 —— 动作号落**第 2 个参数**、
   手柄号落**第 3 个参数**（第 1 个是被跳板覆盖的占位）。
2. **端到端边沿**：宿主没有引擎，测试**直接驱动边沿表本体**（`isaac::runtime::g_ActionEdge`，
   与采样器写的是同一张表）模拟"每帧的按住位图"，仍保留"按住 → 松开 → 再按住"三段。
3. **两条 API 不再现查引擎**：`IsActionTriggered` 纯读；`IsActionPressed` 走 A2
   （采样有记录就答同一次采样的值）⇒ 断言"引擎的按住绑定一次都没被调用"。

★ 边沿**语义**（同帧一致 / 下一帧 false / 走两格回归 / 十字键闸门回归 / 首帧不算边沿 / 聚合 /
帧号跳变不误报）的逐条判据在 `runtime/tests/test_input_action_edge.py`（纯逻辑宿主用例）。
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
    #include "domain/console/console_panel_state.hpp"

    #include "application/callback/callback_dispatcher.hpp"   // `ManagedFrameClock`
    #include "input_edge.hpp"                                  // `InputFrameEdges`（批次 381）
    #include "lua_runtime.hpp"

    //: ★ 批次 381（2026-10-06）：输入的边沿改成"**每帧帧上采样 + 判定纯读**"之后，
    //: `Input.IsActionTriggered` 不再自己现查引擎 —— 边沿由采样器写进 `g_ActionEdge`。
    //: 宿主没有引擎（`EngineModuleBase()==0` ⇒ 采样器读不到设备表、全答 false），
    //: 所以本用例**直接驱动边沿表本体**（与采样器写的是同一张表）来保留
    //: "按住 → 松开 → 再按住"这一层端到端覆盖。
    namespace isaac::runtime { extern LuaRuntime::InputFrameEdges g_ActionEdge; }

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
        -- ★ 批次 230：这一条用 PC 的 20（ACTION_MENULEFT）当样本 —— 它在 Switch 引擎里是 17，
        --   于是本用例同时钉住"调用约定"与"动作号翻译"（口径见 input_action_map.hpp）。
        results[4] = Input.GetActionValue(20, 1)
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
        // ★ 批次 381：输入边沿改成按**引擎帧**判 —— 采样器在"帧号自增之后、派发之前"写边沿表，
        //   判定（`IsActionTriggered` / `IsActionPressed`）只是**纯读**"这一格在本帧的记录"。
        //   宿主夹具没有派发循环 ⇒ 每次脚本执行前**手动推进一帧**，再把这帧的"按住位图"
        //   写进边沿表（= 采样器在真机上做的同一件事）。
        const auto advance_frame = [&]() -> std::uint32_t {
            isaac::runtime::ManagedFrameClock::MarkPostUpdateDispatch();
            return static_cast<std::uint32_t>(isaac::runtime::ManagedFrameClock::Count());
        };
        //: `mask` 的第 i 位 = 本帧动作 i 被按住；`controller` 1 = 脚本里传的 controllerId（透传）。
        const auto sample_actions = [&](std::uint32_t frame, unsigned mask) {
            bool pressed[LuaRuntime::InputFrameEdges::kSlots] = {};
            for (unsigned i = 0; i < LuaRuntime::InputFrameEdges::kSlots; ++i) {
                pressed[i] = ((mask >> i) & 1u) != 0u;
            }
            isaac::runtime::g_ActionEdge.SampleRow(1u, frame, pressed, nullptr);
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
        // ★ 批次 381：本帧的"按住位图"先写进边沿表（= 采样器在真机上做的同一件事），
        //   然后脚本里的 `IsActionTriggered` 只从这张表里**纯读**。
        std::uint32_t frame = advance_frame();
        g_heldActions = (1u << 13) | (1u << 15);
        sample_actions(frame, (1u << 13) | (1u << 15));
        run_script();
        Check(captured_flag(1) == 0, "首次观察（按住）不算边沿");
        Check(captured_flag(3) == 1, "IsActionPressed 读同一次采样 ⇒ 15 按住 = true");
        // ★ 调用约定现在由仍**现查引擎**的 `GetActionValue` 钉住（见第 3 次那两条断言）。
        //   两条边沿/按住 API 现在都**不再直接现查引擎**（`IsActionTriggered` 纯读、
        //   `IsActionPressed` 走 A2 读同一次采样）⇒ 引擎的"按住"绑定这里**一次都没被调用**，
        //   而引擎那条 Triggered 跳板同样从不被调用（真机上它永远是假）。
        Check(g_pressedHistoryCount == 0,
              "A2：采样有记录时 IsActionPressed 不调引擎（与边沿同源）");
        Check(g_lastPressed.action == 0xFFFFFFFFu,
              "A2：IsActionPressed 没有落到引擎的按住绑定上");
        Check(g_lastTriggered.action == 0xFFFFFFFFu,
              "引擎那条\"刚按下\"跳板不该再被调用（真机上它永远是假）");

        // ---- 第 2 次：松开（不报边沿）--------------------------------------------
        frame = advance_frame();
        g_heldActions = 0;
        sample_actions(frame, 0u);
        run_script();
        Check(captured_flag(1) == 0, "松开不报边沿");
        Check(captured_flag(2) == 0, "松开（另一个动作）不报边沿");
        Check(captured_flag(3) == 0, "IsActionPressed 读同一次采样 ⇒ 15 松开 = false");
        Check(captured_flag(4) == 1, "GetActionValue 的 0.5 在 Lua 里是真值");

        // ---- 第 3 次：再按住 ⇒ **这次才是真正的上升沿** ---------------------------
        frame = advance_frame();
        g_heldActions = (1u << 13) | (1u << 15);
        sample_actions(frame, (1u << 13) | (1u << 15));
        run_script();
        Check(captured_flag(1) == 1,
              "★ 端到端上升沿：帧上采样出的边沿，纯读答 true（松开 → 再按住）");
        Check(captured_flag(2) == 0, "没被按住的另一个动作仍为 false");
        Check(captured_flag(3) == 1, "IsActionPressed 按住时为 true");
        Check(captured_flag(4) == 1, "GetActionValue 的 0.5 在 Lua 里是真值");
        Check(g_lastValue.action == 17 && g_lastValue.controller == 1,
              "GetActionValue 应当把 (动作=20 → 引擎内部 17, 手柄=1) 放进 x1/x2");
        // 数值透传：`captured[4]` 必须**是** 0.5（不是"真值"）。
        lua_getglobal(state, "captured");
        lua_rawgeti(state, -1, 4);
        Check(lua_tonumber(state, -1) == 0.5, "GetActionValue 的 float 必须透传");
        lua_pop(state, 2);

        std::printf("RECORDED triggered=(%u,%u) pressed=(%u,%u) value=(%u,%u)\n",
                    g_lastTriggered.action, g_lastTriggered.controller,
                    g_lastPressed.action, g_lastPressed.controller,
                    g_lastValue.action, g_lastValue.controller);

        // 真正调用Lua处理器：控制台捕获按住/边沿/模拟量，放开后同帧原采样仍可读取。
        isaac::runtime::console::g_ConsoleInputCaptured.store(1);
        run_script();
        Check(captured_flag(1)==0 && captured_flag(3)==0,"console captures pressed and triggered");
        lua_getglobal(state,"captured");lua_rawgeti(state,-1,4);
        Check(lua_tonumber(state,-1)==0,"console captures analog value");lua_pop(state,2);
        isaac::runtime::console::g_ConsoleInputCaptured.store(0);
        run_script();Check(captured_flag(3)==1,"normal input restored after console");
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
