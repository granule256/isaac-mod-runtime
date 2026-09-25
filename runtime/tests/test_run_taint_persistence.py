"""门禁：**存档分区里那个「污染过」标记**（2026-09-25 批次 120，用户裁定「比 PC 严」）。

## 这一批是什么

117~119 的闩锁只在**内存**里（出局时转成「留存」、下一次「继续」接回来），**重启游戏/主机就没了**。
用户 2026-09-25 明确要跨重启：**这一份存档只要在妈腿未解锁时用过模组，之后关掉模组、甚至重启，
都继续禁成就，直到开新局**。

★★ 先钉住它**不是 PC 的原样**（用户已确认要「比 PC 严」）：PC 的 `ModManager::AchievementsLocked()`
（`0x250CB8`，098 逐条反汇编）是**开局那一刻的实时查询**，不持久化任何「污染」标记。
这一批加的是**我们自己的**语义 ⇒ 文档与台账里必须写明「比 PC 严」，不能写成「PC 语义」。

## 判据清单

1. **纯算术**（宿主上跑）：`Serialize` → `Parse` 往返一致；`tainted=0` / `tainted=1` 都认；
2. **容忍未知行**（将来加字段不会让老版本读不懂）：头一行不认识也照样能读出标记；
3. **fail-open**：空内容、乱码、`tainted=yes`、`tainted=2`、没有 `tainted=` 行 ⇒ 一律**当成干净**
   （后果是「可能少禁一次成就」，不是「把不该禁的档禁掉」—— 与项目一贯的「宁可不禁也不误禁」同方向）；
4. **不写半截**：缓冲区放不下 ⇒ `Serialize` 返回 0（调用方按「写不了」处理）；
5. **I/O 只走那一条缝**：必须 `SessionSaveFilePort()`，且拿不到端口 / 读失败 ⇒ 记一次失败（状态面 `[57]`）
   并**不置位**（fail-open）；
6. **I/O 的时机**：只允许在**每帧那条游戏线程路径**上做（`RunTaintFileTick` 由
   `UpdateAchievementDisallow` 调）—— **不许**在 `NoteNewRun` 里做（它跑在引擎的开局序列里）；
7. **谁挂待办**：开新局 ⇒ 挂「写 0」；继续同一份存档 ⇒ 挂「读」；读到污染 ⇒ 挂「待接回」；
8. **置位那一帧落盘**：把标记写成 1（已经是 1 就不重复写，省一次存档提交）。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "runtime" / "src"
SOURCE = ROOT / "runtime" / "source"
MARKER = SRC / "domain" / "runtime" / "run_taint_marker.hpp"
CPP = SOURCE / "mod_menu_native.cpp"
HPP = SOURCE / "mod_menu_native.hpp"

HARNESS = r'''
#include "domain/runtime/run_taint_marker.hpp"

#include <cstdio>
#include <string>

using isaac::runtime::ParseRunTaint;
using isaac::runtime::SerializeRunTaint;
using isaac::runtime::kRunTaintMaximumBytes;

namespace {
int failures = 0;
void Check(bool condition, const char* label) {
    if (!condition) { std::printf("FAIL %s\n", label); ++failures; }
}
//: 序列化一份再解析回来（走的是与真机完全相同的那两个函数）。
bool RoundTrip(bool tainted) {
    char out[kRunTaintMaximumBytes]{};
    const std::size_t length = SerializeRunTaint(tainted, out, sizeof(out));
    if (length == 0) { return false; }
    return ParseRunTaint(std::string_view(out, length)) == tainted;
}
}  // namespace

int main() {
    // (1) 往返一致（两个方向都要测：只测一边会让"永远返回 true"的写法蒙过去）。
    Check(RoundTrip(true), "序列化 1 再解析回来仍然是 1");
    Check(RoundTrip(false), "序列化 0 再解析回来仍然是 0");
    // (2) 容忍未知行 / 头一行不认识也能读懂（将来加字段不会让老版本失效）。
    Check(ParseRunTaint("tainted=1\n") == true, "只有标记行也认");
    Check(ParseRunTaint("isaac-runtime-run-taint 9\nwhatever=1\ntainted=1\n") == true,
          "未知行 + 未来版本号 ==> 仍然读出标记");
    // (3) fail-open：这里每一条都必须当成**干净**。
    Check(ParseRunTaint("") == false, "空内容 ==> 干净");
    Check(ParseRunTaint("tainted=0\n") == false, "显式 0 ==> 干净");
    Check(ParseRunTaint("tainted=2\n") == false, "看不懂的值 ==> 当干净（不是污染）");
    Check(ParseRunTaint("tainted=yes\n") == false, "看不懂的值 ==> 当干净");
    Check(ParseRunTaint("tainted\n") == false, "没有等号 ==> 当干净");
    Check(ParseRunTaint("garbage\xff\xfe\n") == false, "乱码 ==> 当干净");
    Check(ParseRunTaint("other=1\n") == false, "没有标记行 ==> 当干净");
    // (4) 不写半截：放不下必须返回 0。
    char tiny[4]{};
    Check(SerializeRunTaint(true, tiny, sizeof(tiny)) == 0, "缓冲区放不下 ==> 返回 0");
    Check(SerializeRunTaint(true, nullptr, 64) == 0, "空指针 ==> 返回 0");
    if (failures != 0) { std::printf("RUN_TAINT_MARKER_CHECKS_FAILED %d\n", failures); return 1; }
    std::printf("RUN_TAINT_MARKER_CHECKS_PASSED\n");
    return 0;
}
'''


def function_body(text: str, signature: str) -> str:
    """取一个函数的函数体（从签名起、到下一个顶格的 `}` 为止）。"""
    assert signature in text, f"没找到 {signature}"
    return text.split(signature, 1)[1].split("\n}\n", 1)[0]


class RunTaintPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = CPP.read_text(encoding="utf-8")
        cls.hpp = HPP.read_text(encoding="utf-8")
        cls.marker = MARKER.read_text(encoding="utf-8")

    # ---- 1) 纯算术（在宿主上编一份夹具跑）----------------------------------------

    def test_the_marker_arithmetic_on_host(self):
        compiler = next((shutil.which(c) for c in ("c++", "clang++", "g++")
                         if shutil.which(c)), None)
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-run-taint-") as directory:
            workdir = Path(directory)
            source = workdir / "harness.cpp"
            source.write_text(HARNESS.lstrip(), encoding="utf-8")
            binary = workdir / "harness"
            build = subprocess.run(
                [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(SRC),
                 str(source), "-o", str(binary)],
                text=True, capture_output=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("RUN_TAINT_MARKER_CHECKS_PASSED", run.stdout)

    # ---- 2) 与 PC 的关系必须写清楚 -----------------------------------------------

    def test_it_is_documented_as_stricter_than_pc(self):
        """★ 这一批加的是**我们自己的**语义，不是 PC 的原样 —— 文档里不许写成「PC 语义」。

        为什么值得钉：用户 2026-09-25 的理由是「不然怎么做到还原 PC 语义」，而我们 098 的取证
        （逐条反汇编 `ModManager::AchievementsLocked()`）表明 PC 恰恰**不持久化**这个标记。
        ⇒ 万一将来有人照着「PC 语义」去对账，会以为这里做错了。
        """
        for text in (self.marker, self.hpp):
            self.assertIn("比 PC 严", text, "文件头/字段注释要写明「比 PC 严」")
            self.assertIn("AchievementsLocked", text, "要给出 PC 那条规则的出处（098 反汇编）")

    # ---- 3) I/O 只走那一条缝，且失败方向是 fail-open ------------------------------

    def test_the_io_goes_through_the_session_port_and_fails_open(self):
        read_body = function_body(self.cpp, "void ReadRunTaintFile")
        write_body = function_body(self.cpp, "void WriteRunTaintFile")
        for body in (read_body, write_body):
            self.assertIn("SessionSaveFilePort()", body,
                          "存档分区的读写只许走那一条缝（不许自己找文件/自己拼路径）")
            self.assertIn("storage == nullptr", body,
                          "端口拿不到时要有明确分支，并按能力不可用如实记账（不许静默）")
            self.assertIn("taintFileFailures", body, "失败要记进状态面 [57]")
        # 文件不存在 = 干净（不是错误）。
        self.assertIn("StatusCode::NotFound", read_body, "文件不存在要按「干净」处理")
        # fail-open：读失败那条分支**不许**去置位/去挂待接回。
        fail_branch = read_body.split("!status.ok()", 1)[1].split("}", 1)[0]
        self.assertNotIn("g_RunLatchResumePending", fail_branch,
                         "读失败 ⇒ 不许当污染（fail-open：宁可不禁也不误禁）")
        self.assertIn("isaac::runtime::SerializeRunTaint(", write_body,
                      "写之前要序列化（走那个纯函数，别在这里拼字符串）")
        self.assertIn("length == 0", write_body, "序列化放不下 ⇒ 按「写不了」处理，不写半截")

    # ---- 4) I/O 的时机：只在每帧那条游戏线程路径上 -------------------------------

    def test_the_io_happens_in_the_per_frame_path_not_in_the_boundary_callback(self):
        """★★ 这条是这一批最容易踩的坑：`NoteNewRun` 跑在**引擎的开局序列**里（中继回调），
        在那里做文件 I/O 风险高（本项目有过「在开局路径上写卡 ⇒ 装载崩溃」的经历）。
        ⇒ 它只许**挂待办**，真正读写只能在每帧的 `UpdateAchievementDisallow` 里。"""
        boundary = function_body(self.cpp, "void NoteNewRun")
        self.assertIn("g_TaintFileReadPending = true;", boundary, "继续 ⇒ 挂「读」的待办")
        self.assertIn("g_TaintFileWritePending = true;", boundary, "开新局 ⇒ 挂「写」的待办")
        for forbidden in ("ReadRunTaintFile(", "WriteRunTaintFile(", "storage->"):
            self.assertNotIn(forbidden, boundary, f"`NoteNewRun` 里不许做 I/O（{forbidden}）")
        update = function_body(self.cpp, "void UpdateAchievementDisallow")
        self.assertIn("RunTaintFileTick();", update, "每帧更新里必须做一次那条待办")
        tick = function_body(self.cpp, "void RunTaintFileTick")
        self.assertIn("ReadRunTaintFile();", tick, "tick 里做读")
        self.assertIn("WriteRunTaintFile(", tick, "tick 里做写")
        # tick 必须在早退之前（与 098 那次同一个理由：一局里读不到菜单管理器）。
        self.assertLess(update.index("RunTaintFileTick();"),
                        update.index("ReadSingleton(module, kManagerSlotOffset"),
                        "tick 要排在「读不到菜单管理器就 return」那道早退**之前**")

    # ---- 5) 谁挂待办、谁落盘 -----------------------------------------------------

    def test_who_schedules_the_io_and_what_gets_written(self):
        # 读到污染 ⇒ 挂「待接回」（这就是跨重启那条路的入口）。
        read_body = function_body(self.cpp, "void ReadRunTaintFile")
        self.assertIn("kTaintFileTainted", read_body, "读到污染要能认出来")
        self.assertIn("g_RunLatchResumePending = true;", read_body,
                      "读到污染 ⇒ 挂「待接回」（下一次观察点会补写一次锁）")
        # 置位那一帧落盘（已经是污染就不重复写）。
        update = function_body(self.cpp, "void UpdateAchievementDisallow")
        self.assertIn("WriteRunTaintFile(true)", update, "闩锁置位那一帧要把标记写成 1")
        self.assertRegex(update, r"g_TaintFileState != kTaintFileTainted",
                         "已经是「污染过」时不许重复写（省一次存档提交）")
        # 状态面要有那两格。
        for field in ("taintFileState", "taintFileFailures"):
            self.assertIn(field, self.hpp, f"状态面要有 {field} 那一格")
            self.assertIn(field, self.cpp, f"{field} 要被真的写下去")


if __name__ == "__main__":
    unittest.main()