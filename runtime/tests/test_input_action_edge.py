"""`Input.IsActionTriggered` 的上升沿判定（批次 107）。

## 这个测试解决什么问题

真机读数（2026-09-20）的形状：**同一条控制器、同一个动作**，引擎的"按住"查询（`IsActionPressed`）
为真、而引擎的"刚按下"查询（`IsActionTriggered`）**一次都没为真** —— 于是 EID 的
"库存概况"导航（`eid_holdmapdesc.lua:671` 起，用 `Input.IsActionTriggered` 读四个方向）
按下去没反应。反汇编显示两个引擎函数结构完全相同，只差虚函数槽（`vtable+0x48` 按住 / `+0x50` 刚按下）。

本批把这个 API 换成**我们自己的上升沿**（原语是已验证可用的 `IsActionPressed`）。
上升沿逻辑最容易出的错不是"崩"，而是**静默多报/少报一次** —— 那会让模组"按一下跳两格"或
"按了不动"，而且不报错。所以这里把每条分支逐条钉住。

## 两半断言

1. **行为（宿主真跑）**：`ActionEdgeTracker` 是纯逻辑 ⇒ 直接跑它的每条分支。
2. **接线可见性（文本）**：只保证"那条路还在"——用的是 `IsActionPressed` 的入口、走了上升沿表、
   会话重置会清空、偏离台账里那条写全了"偏离后果 + 判据"。**这一半不验行为。**
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
LUA_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"

HARNESS = r'''
#include "input_edge.hpp"

#include <cstdint>
#include <cstdio>

using LuaRuntime::ActionEdgeTracker;

namespace {

int failures = 0;

void Check(bool condition, const char* label) {
    if (!condition) {
        std::printf("FAIL %s\n", label);
        ++failures;
    }
}

// 真机上的那两个值：动作 4 = `ACTION_SHOOTLEFT`，控制器 33 = 玩家自己的 `ControllerIndex`。
constexpr std::uint32_t kAction = 4;
constexpr std::uint32_t kController = 33;
//: 松手去抖窗口（帧）—— 真松手要隔开这么多帧才算"新的一次按下"。
constexpr std::uint32_t kWindow = ActionEdgeTracker::kReleaseFrames;

}  // namespace

int main() {
    ActionEdgeTracker tracker{};

    // ① **第一次观察**不算边沿：模组第一次问到时若键正被按着，不该凭空多一次"刚按下"。
    Check(!tracker.Observe(kAction, kController, true, 1), "首帧（按住）不算边沿");
    // ② **同一帧内**问多少次都是同一个答案。
    Check(!tracker.Observe(kAction, kController, true, 1), "同一帧内再问，答案不变");
    Check(!tracker.Observe(kAction, kController, true, 2), "连续按住跨帧不报");

    // ③ ★★ 真机上那个现象（批次 109 的读数：动作 7 在**按住**期间被报了 170 次边沿）：
    //    引擎的"按住"查询在按着的时候会**闪断**（某些帧读到"没按住"）。
    //    去抖窗口（6 帧）之内无论闪断几次，都**不许**再报边沿 ⇒ 用户不会看到"长按不停翻页"。
    tracker.Reset();
    static_cast<void>(tracker.Observe(kAction, kController, true, 30));   // 首次观察
    for (std::uint32_t frame = 31; frame <= 60; ++frame) {
        const bool down = (frame % 2) == 1;   // 隔帧闪断
        Check(!tracker.Observe(kAction, kController, down, frame),
              "闪断：按住期间不许再报边沿");
    }
    Check(tracker.PeakReleaseRun(kAction, kController) == 1,
          "闪断：最长闪断记成 1 帧（诊断用，用来判去抖窗口够不够）");

    // ④ **真松手**（连续超过窗口帧都读到"没按住"）之后再按 ⇒ 这才是新的一次边沿。
    for (std::uint32_t frame = 61; frame <= 60 + kWindow + 1; ++frame) {
        static_cast<void>(tracker.Observe(kAction, kController, false, frame));
    }
    Check(tracker.Observe(kAction, kController, true, 60 + kWindow + 2),
          "真松手之后再按 = 新的一次边沿");
    Check(tracker.Observe(kAction, kController, true, 60 + kWindow + 2),
          "同一帧内再问仍是 true（PC 语义）");
    Check(tracker.Observe(kAction, kController, false, 60 + kWindow + 2),
          "同一帧内读到抬起也不撤销（帧内定一次）");
    Check(!tracker.Observe(kAction, kController, true, 60 + kWindow + 3),
          "下一帧（仍按住）不再报");

    // ⑤ 连点：每次"松手 + 超过窗口"之后再按都能报到。
    for (std::uint32_t frame = 80; frame <= 80 + kWindow; ++frame) {
        static_cast<void>(tracker.Observe(kAction, kController, false, frame));
    }
    Check(tracker.Observe(kAction, kController, true, 80 + kWindow + 1), "连点：第二次按下");
    for (std::uint32_t frame = 100; frame <= 100 + kWindow; ++frame) {
        static_cast<void>(tracker.Observe(kAction, kController, false, frame));
    }
    Check(tracker.Observe(kAction, kController, true, 100 + kWindow + 1), "连点：第三次按下");

    // ⑥ 分槽：控制器号与动作号都只看低 5 位（真机是 33 ⇒ 与 1 同一个槽）。
    tracker.Reset();
    Check(!tracker.Observe(kAction, 1, true, 200), "槽：控制器 1 首帧不算边沿");
    Check(!tracker.Observe(kAction, kController, true, 201), "槽：33 与 1 是同一个槽");
    Check(!tracker.Observe(kAction, 2, true, 202), "槽：控制器 2 是另一个槽（首帧）");
    Check(!tracker.Observe(kAction + 32, kController, true, 203),
          "槽：动作号 36 与 4 是同一个槽（仍按住）");

    // ⑦ 会话重置之后：记录清空 ⇒ 下一次按住又算"首帧"（不报边沿），此后照常。
    tracker.Reset();
    Check(!tracker.Observe(kAction, kController, true, 300), "重置后第一次按住不算边沿");
    for (std::uint32_t frame = 301; frame <= 300 + kWindow + 1; ++frame) {
        static_cast<void>(tracker.Observe(kAction, kController, false, frame));
    }
    Check(tracker.Observe(kAction, kController, true, 300 + kWindow + 2),
          "重置后仍能报出新的边沿");

    if (failures != 0) {
        std::printf("INPUT_ACTION_EDGE_CHECKS_FAILED %d\n", failures);
        return 1;
    }
    std::printf("INPUT_ACTION_EDGE_CHECKS_PASSED\n");
    return 0;
}
'''


def host_compiler() -> str | None:
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


class ActionEdgeBehaviourTests(unittest.TestCase):
    def test_edge_semantics_on_host(self):
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-input-edge-") as directory:
            workdir = Path(directory)
            source = workdir / "harness.cpp"
            source.write_text(HARNESS.lstrip(), encoding="utf-8")
            binary = workdir / "harness"
            build = subprocess.run(
                [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE),
                 str(source), "-o", str(binary)],
                text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("INPUT_ACTION_EDGE_CHECKS_PASSED", run.stdout)


class ActionEdgeWiringTests(unittest.TestCase):
    """接线可见性（文本）。**不验行为** —— 这一半只保证"那条路还在"，见文件头的口径说明。"""

    @classmethod
    def setUpClass(cls):
        cls.input_api = (LUA_DIR / "input_api.cpp").read_text(encoding="utf-8")
        cls.input_header = (LUA_DIR / "input_api.hpp").read_text(encoding="utf-8")
        cls.isaac_api = (LUA_DIR / "isaac_api.cpp").read_text(encoding="utf-8")
        cls.deviation = (LUA_DIR / "api_deviation.cpp").read_text(encoding="utf-8")

    def test_triggered_uses_the_pressed_primitive_plus_our_edge(self):
        """必须拿 `IsActionPressed` 当原语（引擎那条"刚按下"在真机上永远是假）。

        这一条是整批的**要害**：如果哪天有人"顺手改回"引擎的 Triggered 入口，
        症状就是"导航键又没反应"，而且不报错 —— 所以钉住"用的是 Pressed 那一个 thunk"。
        """
        handler = self.input_api[
            self.input_api.index("int InputIsActionTriggered(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("InputIsActionPressedThunk()", handler)
        self.assertNotIn("InputIsActionTriggeredThunk()", handler)
        self.assertIn("g_ActionEdge.Observe(", handler)

    def test_edge_state_is_session_scoped(self):
        """上升沿表是会话级状态：新会话必须清空（否则上一次会话"按住过"的记录会凭空报一次边沿）。"""
        self.assertIn("void ResetInputEdgeState() noexcept {", self.input_api)
        self.assertIn("void ResetInputEdgeState() noexcept;", self.input_header)
        self.assertIn("ResetInputEdgeState();", self.isaac_api)

    def test_the_deviation_is_registered(self):
        """换成我们自己的语义必须进偏离台账（本项目对"交回的不是引擎值"的硬要求）。"""
        self.assertIn("{0x09010004,", self.deviation)
        entry = self.deviation[self.deviation.index("{0x09010004,"):]
        entry = entry[:entry.index("},")]
        self.assertIn("偏离后果：", entry)
        self.assertIn("判据：runtime/tests/test_input_action_edge.py", entry)


if __name__ == "__main__":
    unittest.main()
