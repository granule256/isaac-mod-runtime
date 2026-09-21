"""按键查询候选顺序（标题画面自绘入口要用）—— 顺序错的表现是"按键没反应"，不报错、不崩。

口径见 `action_input_poll.hpp`：自学习值 → 玩家自己的 `ControllerIndex` → `0xFFFFFFFF`（引擎菜单用的
"任意手柄"）→ 0..3、32..35 兜底；重复只留第一次。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

HARNESS = r'''
#include "action_input_poll.hpp"

#include <cstdio>
#include <cstring>

using isaac::runtime::ActionControllerCandidates;
using isaac::runtime::BuildActionControllerCandidates;
using isaac::runtime::PollActionPressed;
using isaac::runtime::kAnyController;

namespace {
int failures = 0;
void Check(bool condition, const char* label) {
    if (!condition) { std::printf("FAIL %s\n", label); ++failures; }
}
// 假查询：只有 answerFor 那个 controller 答"是"，并记录问过哪些值。
struct QueryState { std::uint32_t answerFor; std::uint32_t asked[16]; int askedCount; };
bool FakeQuery(void* ctx, std::uint32_t, std::uint32_t controller, void*) {
    auto* state = static_cast<QueryState*>(ctx);
    if (state->askedCount < 16) { state->asked[state->askedCount] = controller; }
    ++state->askedCount;
    return controller == state->answerFor;
}
}  // namespace

int main() {
    // 主菜单场景：没有玩家、还没学到值 ⇒ 第一个候选必须是"任意手柄"。
    {
        const ActionControllerCandidates c = BuildActionControllerCandidates(0, false, 0, false);
        Check(c.count >= 3, "候选表不该为空");
        Check(c.values[0] == kAnyController, "没有玩家也没有学习值时，先问 0xFFFFFFFF");
    }
    // 学到了：自学习值必须排第一（学到就不再靠猜）。
    {
        const ActionControllerCandidates c = BuildActionControllerCandidates(33, true, 0, false);
        Check(c.values[0] == 33, "自学习值必须排第一");
        Check(c.values[1] == kAnyController, "其后是任意手柄");
    }
    // 有玩家：玩家值排在任意手柄之前。
    {
        const ActionControllerCandidates c = BuildActionControllerCandidates(0, false, 7, true);
        Check(c.values[0] == 7, "有玩家时玩家值优先");
        Check(c.values[1] == kAnyController, "其后是任意手柄");
    }
    // 去重：玩家值恰好是 0xFFFFFFFF 时不许出现两次。
    {
        const ActionControllerCandidates c = BuildActionControllerCandidates(0, false, kAnyController, true);
        Check(c.values[0] == kAnyController, "玩家值就是任意手柄");
        int hits = 0;
        for (std::uint32_t i = 0; i < c.count; ++i) { if (c.values[i] == kAnyController) { ++hits; } }
        Check(hits == 1, "同一个值只许出现一次");
    }
    // 兜底值都在表里（0..3、32..35），且总量不超过上限。
    {
        const ActionControllerCandidates c = BuildActionControllerCandidates(0, false, 0, false);
        for (std::uint32_t v = 0; v <= 3; ++v) {
            bool found = false;
            for (std::uint32_t i = 0; i < c.count; ++i) { if (c.values[i] == v) { found = true; } }
            Check(found, "0..3 必须在候选里");
        }
        for (std::uint32_t v = 32; v <= 35; ++v) {
            bool found = false;
            for (std::uint32_t i = 0; i < c.count; ++i) { if (c.values[i] == v) { found = true; } }
            Check(found, "32..35 必须在候选里");
        }
        Check(c.count <= isaac::runtime::kActionControllerCapacity, "总量不许超过上限");
    }
    // 轮询：谁答"是"就返回谁、并把它记成自学习值。
    {
        const ActionControllerCandidates c = BuildActionControllerCandidates(0, false, 0, false);
        QueryState state{0, {0}, 0};   // controller 0 答"是"
        std::uint32_t learned = 0xDEADBEEF;
        const bool pressed = PollActionPressed(&FakeQuery, &state, 13, c, &learned);
        Check(pressed, "有控制器答是 ⇒ 应当返回 true");
        Check(learned == 0, "答是的那个值要被记下来");
        Check(state.askedCount >= 1, "应当至少问一次");
    }
    // 没人答"是" ⇒ false，且不改动自学习值。
    {
        const ActionControllerCandidates c = BuildActionControllerCandidates(0, false, 0, false);
        QueryState state{0x99, {0}, 0};
        std::uint32_t learned = 5;
        Check(!PollActionPressed(&FakeQuery, &state, 13, c, &learned), "没人答是 ⇒ false");
        Check(learned == 5, "没答是就不许改自学习值");
        Check(static_cast<std::uint32_t>(state.askedCount) == c.count, "每个候选都要问一遍");
    }

    if (failures != 0) { std::printf("ACTION_INPUT_POLL_CHECKS_FAILED %d\n", failures); return 1; }
    std::printf("ACTION_INPUT_POLL_CHECKS_PASSED\n");
    return 0;
}
'''


class ActionInputPollTests(unittest.TestCase):
    def test_candidate_order_on_host(self):
        compiler = next((shutil.which(c) for c in ("c++", "clang++", "g++")
                         if shutil.which(c)), None)
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-action-input-") as directory:
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
            self.assertIn("ACTION_INPUT_POLL_CHECKS_PASSED", run.stdout)


if __name__ == "__main__":
    unittest.main()
