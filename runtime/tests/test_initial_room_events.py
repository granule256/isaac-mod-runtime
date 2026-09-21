"""开局起始房间必须收到一次 `MC_POST_NEW_LEVEL` + `MC_POST_NEW_ROOM`（2026-09-22）。

## 这个测试解决什么问题（真机症状）

用户报："**每次游戏重启，第一次进局正好在献祭房，EID 的房间信息就不显示**；之后就正常。"
设备读数直接印证（保留件 `dist/gdb-read-20260922-*`）：那一局

```
15 MC_POST_GAME_STARTED   1     ← 事件送到了
18 MC_POST_NEW_LEVEL      0     ← 一次都没发
19 MC_POST_NEW_ROOM       0     ← 一次都没发（EID 的房间信息就在这条里算）
```

而 `71 MC_PRE_ROOM_ENTITY_SPAWN = 1` —— 房间里的实体事件是发过的，唯独"进入房间"这一条没有。
原因是我们自己的判定：旧代码"**第一次读到身份时不判变化**"（怕把开局那间房当成第二间房），
于是开局房间永远收不到这两条；只有等到玩家推门换房，`NEW_ROOM` 才第一次发出 ⇒ 症状与现象完全吻合。

PC 的语义是：开局时 `POST_GAME_STARTED` → `POST_NEW_LEVEL` → `POST_NEW_ROOM` **都发**。

## 两半断言

1. **行为（宿主真跑）**：`DecideFrameRoomEvents()` 是纯函数，逐条验三个口径 ——
   开局补派一次、读不到身份时既不判也不消费、中途加载时不拿残值当身份。
2. **接线可见性（文本）**：开局派发成功后置标志、判定结果驱动派发、`lua_runtime.cpp` 引用这个头。
   **这一半不验行为**，只保证"那条路还在"（真机行为见目标里的验收条件：读数里 18/19 要从 0 变 1）。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

HARNESS = r'''
#include "frame_event_decision.hpp"

#include <cstdio>
#include <cstdint>

using isaac::runtime::DecideFrameRoomEvents;
using isaac::runtime::FrameRoomDecision;

namespace {

int failures = 0;

void Check(bool condition, const char* label) {
    if (!condition) {
        std::printf("FAIL %s\n", label);
        ++failures;
    }
}

}  // namespace

int main() {
    // 口径 1：开局那一帧读到了身份 ⇒ NEW_LEVEL + NEW_ROOM 都要发，且标志可以清。
    {
        const FrameRoomDecision d = DecideFrameRoomEvents(
            /*haveLocation=*/true, /*roomKnown=*/false, /*levelKnown=*/false,
            /*sameStage=*/false, /*sameRoom=*/false, /*initialRoomPending=*/1);
        Check(d.newLevel, "开局应当补派 NEW_LEVEL");
        Check(d.newRoom, "开局应当补派 NEW_ROOM");
        Check(d.initialRoomConsumed, "开局那次补派应当顺手把标志清掉");
    }
    // 口径 1b：开局补派**不依赖**"上一次身份"是否存在（旧代码就是在这里漏的）。
    {
        const FrameRoomDecision d = DecideFrameRoomEvents(true, false, false, true, true, 1);
        Check(d.newLevel && d.newRoom && d.initialRoomConsumed,
              "即使同层同房，开局那次也必须发（标志是唯一的依据）");
    }
    // 口径 2：这一帧读不到身份 ⇒ 什么都不派，**也不消费**标志（下一帧重试）。
    {
        const FrameRoomDecision d = DecideFrameRoomEvents(false, false, false, false, false, 1);
        Check(!d.newLevel && !d.newRoom, "读不到身份时不许派发");
        Check(!d.initialRoomConsumed, "读不到身份时不许把开局那次补派吞掉");
    }
    // 口径 3：中途加载（没有开局标志、第一次读到身份）⇒ 不判变化。
    {
        const FrameRoomDecision d = DecideFrameRoomEvents(true, false, false, false, false, 0);
        Check(!d.newLevel && !d.newRoom, "第一次读到身份、又不是开局 ⇒ 不判变化");
    }
    // 正常换房：同层、不同房 ⇒ 只发 NEW_ROOM。
    {
        const FrameRoomDecision d = DecideFrameRoomEvents(true, true, true, true, false, 0);
        Check(d.newRoom && !d.newLevel, "换房间只发 NEW_ROOM");
    }
    // 正常换层：层变了、房间也不同 ⇒ 两条都发（顺序由调用方按结构体字段顺序保证）。
    {
        const FrameRoomDecision d = DecideFrameRoomEvents(true, true, true, false, false, 0);
        Check(d.newLevel && d.newRoom, "换层时两条都要发");
    }
    // 稳定帧：同层同房 ⇒ 什么都不发（否则就成了"每帧一次"）。
    {
        const FrameRoomDecision d = DecideFrameRoomEvents(true, true, true, true, true, 0);
        Check(!d.newLevel && !d.newRoom, "稳定帧不许派发");
    }
    // 标志消费后不再重复：下一帧 pending 已经是 0。
    {
        const FrameRoomDecision d = DecideFrameRoomEvents(true, true, true, true, true, 0);
        Check(!d.newLevel && !d.newRoom && !d.initialRoomConsumed, "补派只发生一次");
    }

    if (failures != 0) {
        std::printf("INITIAL_ROOM_CHECKS_FAILED %d\n", failures);
        return 1;
    }
    std::printf("INITIAL_ROOM_CHECKS_PASSED\n");
    return 0;
}
'''


def host_compiler() -> str | None:
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


class FrameRoomDecisionBehaviourTests(unittest.TestCase):
    def test_decision_semantics_on_host(self):
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-initial-room-") as directory:
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
            self.assertIn("INITIAL_ROOM_CHECKS_PASSED", run.stdout)


class InitialRoomWiringTests(unittest.TestCase):
    """接线可见性（文本）。**不验行为** —— 只保证"那条路还在"。"""

    @classmethod
    def setUpClass(cls):
        cls.runtime = (SOURCE / "lua_runtime.cpp").read_text(encoding="utf-8")

    def test_game_start_arms_the_initial_room(self):
        """开局派发成功之后必须挂上"起始房间待补派"的标志。"""
        self.assertIn("#include \"frame_event_decision.hpp\"", self.runtime)
        index = self.runtime.index("if (DispatchPostGameStarted(pending == kGameStartedFromSave))")
        window = self.runtime[index:index + 1200]
        self.assertIn("g_FrameEventState.initialRoomPending = 1;", window,
                      "开局派发成功后必须武装起始房间补派")

    def test_decision_drives_the_two_dispatches(self):
        """判定结果必须真的驱动那两条派发（`enteredNewLevel` / `enteredNewRoom`）。"""
        index = self.runtime.index("isaac::runtime::DecideFrameRoomEvents(")
        window = self.runtime[index:index + 1600]
        self.assertIn("enteredNewLevel = decision.newLevel;", window)
        self.assertIn("enteredNewRoom = true;", window)
        self.assertIn("g_FrameEventState.initialRoomPending = 0;", window,
                      "补派之后必须清掉标志（否则会每帧发一次）")

    def test_dispatch_order_is_level_before_room(self):
        """派发顺序照 PC：`NEW_LEVEL` 在 `NEW_ROOM` 之前。"""
        level = self.runtime.index("kCallbackPostNewLevel,\n                                              isaac::runtime::ThreadAffinity::Any")
        room = self.runtime.index("kCallbackPostNewRoom,\n                                              isaac::runtime::ThreadAffinity::Any")
        self.assertLess(level, room, "NEW_LEVEL 必须先于 NEW_ROOM 派发")


if __name__ == "__main__":
    unittest.main()
