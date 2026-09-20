"""`Level:GetStartingRoomIndex()` 的派生记账（批次 106）。

## 这个测试解决什么问题

EID 的 `features/eid_holdmapdesc.lua:35` 每条回调都在问
`GetStartingRoomIndex() ~= GetCurrentRoomIndex()`（"玩家是不是在起始房间"），
而 Switch 的引擎里**没有**这个符号/字段（取证过程见 `runtime/source/level_start_room.hpp` 顶部：
符号表、Ghidra 类型库、镜像字符串、`RoomDescriptor` 的 24 个标志、`RoomConfig::Room` 的字段、
`Level/Game` 的 0x215xx 全镜像扫描 —— 都查过，都没有）。以前的实现里它**整条不存在** ⇒
模组每次调用都 `attempt to call a nil value` ⇒ 那条回调被打断。

本批给的取值是**派生**的（本层第一次被看到的房间索引）。派生值最容易出的错不是"崩"，
而是**静默答错**（例如把"每一帧都把当前房间当成起始房间"写成"只在换层时记"）——
那会让 EID 的 `hideInOverview` 行为完全不同，而且不报错。所以这里把跟踪语义逐条钉住。

## 两半断言（各自的口径）

1. **行为（宿主真跑）**：`LevelStartRoomTracker` 是纯逻辑，宿主上直接跑它的每一条分支 ——
   第一次记、同层不改、换层改、`stageType` 变了也算换层、重置后可重记。
2. **接线可见性（文本）**：只保证"那条路还在"——记账调用在"换层 / 第一次读到身份"那个分支里、
   会话重置时会清空、取值前先做一次懒观察、id 0x03010011 在处理器与目录里都登记了。
   **这一半不验行为**：真机行为（"引擎真值 == 我们记的值"）见
   `docs/待真机验收-20260920-回调面.md` 与 `api_deviation.cpp` 的 0x03010011。
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
#include "level_start_room.hpp"

#include <cstdint>
#include <cstdio>

using LuaRuntime::LevelStartRoomTracker;

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
    // 编译期自证：哨兵值必须是 -1（模组那边会拿它当整数比较）。
    static_assert(LevelStartRoomTracker::kUnknownRoomIndex == 0xFFFFFFFFu,
                  "哨兵值必须是 -1：模组的比较会把 -1 判成'不是起始房间'");

    LevelStartRoomTracker tracker{};
    Check(tracker.Value() == LevelStartRoomTracker::kUnknownRoomIndex, "初始是还不知道");

    // 第一次观察 = 本层的起始房间。
    tracker.Observe(1, 0, 37);
    Check(tracker.Value() == 37, "第一次观察记下来");

    // 同一层里换房间：**不许**改（这正是"起始"两个字的含义）。
    tracker.Observe(1, 0, 42);
    tracker.Observe(1, 0, 8);
    Check(tracker.Value() == 37, "同一层内换房间不修改记录");

    // 换层（stage 变）：改成新层第一次看到的房间。
    tracker.Observe(2, 0, 5);
    Check(tracker.Value() == 5, "换层重新记");
    tracker.Observe(2, 0, 6);
    Check(tracker.Value() == 5, "新层内换房间也不改");

    // stage 相同、stageType 不同（交替层/镜像那类）= 也是新层。
    tracker.Observe(2, 1, 9);
    Check(tracker.Value() == 9, "stageType 变了也算新层");

    // 重置（新 Lua 会话）之后必须重新起底：即使层号与重置前相同。
    tracker.Reset();
    Check(tracker.Value() == LevelStartRoomTracker::kUnknownRoomIndex, "重置后回到还不知道");
    tracker.Observe(2, 1, 11);
    Check(tracker.Value() == 11, "重置后同样的层号也要重新记");

    if (failures != 0) {
        std::printf("LEVEL_START_ROOM_CHECKS_FAILED %d\n", failures);
        return 1;
    }
    std::printf("LEVEL_START_ROOM_CHECKS_PASSED\n");
    return 0;
}
'''


def host_compiler() -> str | None:
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


class LevelStartRoomTrackerBehaviourTests(unittest.TestCase):
    def test_tracker_semantics_on_host(self):
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-level-start-room-") as directory:
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
            self.assertIn("LEVEL_START_ROOM_CHECKS_PASSED", run.stdout)


class LevelStartRoomWiringTests(unittest.TestCase):
    """接线可见性（文本）。**不验行为** —— 这一半只保证"那条路还在"，见文件头的口径说明。"""

    @classmethod
    def setUpClass(cls):
        cls.runtime = (SOURCE / "lua_runtime.cpp").read_text(encoding="utf-8")
        cls.state = (SOURCE / "lua_runtime_state.hpp").read_text(encoding="utf-8")
        cls.remaining = (LUA_DIR / "remaining_api.cpp").read_text(encoding="utf-8")
        cls.catalog = (LUA_DIR / "api_catalog.cpp").read_text(encoding="utf-8")
        cls.deviation = (LUA_DIR / "api_deviation.cpp").read_text(encoding="utf-8")

    def test_bookkeeping_rides_on_the_level_change_branch(self):
        """记账必须挂在"换层 **或** 第一次读到身份"那个分支上。

        只挂换层 ⇒ 运行时在层中途加载时永远没有记录（答"还不知道"）；
        只挂第一次 ⇒ 换层之后再也不会更新（一层用到底）。
        """
        self.assertIn("if (enteredNewLevel || g_FrameEventState.levelKnown == 0) {", self.runtime)
        self.assertIn("g_LevelStartRoom.Observe(location.stage, location.stageType, location.roomIndex);",
                      self.runtime)

    def test_new_session_clears_the_record(self):
        """新 Lua 会话必须清空：否则上一局的记录会被当成这一局的起始房间。"""
        self.assertIn("ResetLevelStartRoomTracker();", self.runtime)
        self.assertIn("void ResetLevelStartRoomTracker() noexcept {", self.runtime)

    def test_the_api_observes_lazily_before_reading(self):
        """取值前先懒观察 —— 否则"没有模组登记帧事件族"的会话里这个 API 永远答"还不知道"
        （`DispatchFrameEvents` 开头有一条"没人听就整段跳过"的早退）。"""
        # 从**定义**处切（不能从前面那行前置声明处切 —— 那样会在下一个函数结尾就截断）。
        handler = self.remaining[
            self.remaining.index("int LevelGetStartingRoomIndex(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        observe = handler.index("LuaRuntime::NoteCurrentLocationForStartRoom();")
        value = handler.index("LuaRuntime::StartingRoomIndexForCurrentLevel()")
        self.assertLess(observe, value, "必须先观察再取值")
        self.assertIn("void NoteCurrentLocationForStartRoom() noexcept {", self.runtime)
        # 懒观察本身读不到引擎内存时**什么都不做**（宁可继续答"还不知道"，也不编一个房间号）。
        self.assertIn("if (ReadGameLocationKey(GameOwnerSlot(), &location) != "
                      "GameRoomObservation::Success) {", self.runtime)

    def test_the_id_is_registered_in_both_places(self):
        """处理器表与目录行必须同时登记 id 0x03010011（少一处就是"Lua 侧调不到"或"目录漏账"）。"""
        self.assertIn("{0x03010011, &LevelGetStartingRoomIndex},", self.remaining)
        self.assertIn('MakeId(ApiDomain::Level, 1, 0x0011)', self.catalog)
        self.assertIn('"GetStartingRoomIndex"', self.catalog)

    def test_the_deviation_is_registered(self):
        """派生值必须进偏离台账（这是本项目对"没取证就用近似"的硬要求）。"""
        self.assertIn("{0x03010011,", self.deviation)
        entry = self.deviation[self.deviation.index("{0x03010011,"):]
        entry = entry[:entry.index("},")]
        self.assertIn("偏离后果：", entry)
        self.assertIn("判据：runtime/tests/test_level_start_room.py", entry)
        self.assertIn("取证后的替换方式", entry)


if __name__ == "__main__":
    unittest.main()
