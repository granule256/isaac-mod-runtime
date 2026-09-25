"""门禁：**局内单向闩锁**（2026-09-25 批次 117）—— 语义里最容易写错的那几条，一秒分清。

## 这一批是什么

用户要的语义（2026-09-24 原话的意思）：**一局之内**，只要出现过「还没打过妈腿（成就 #4 未解锁）
且**开着模组**」，那么**即使之后把模组关掉，这一局也一直禁成就**。
★ 这比 PC 严（PC 是开局那一刻问一次、之后不动），用户在两个方案里明确选了「局内单向」。

形状 = 一颗**单向**闩锁：只有「条件成立过」能把它抬起来，只有「局边界」能把它放下去。

## 为什么值得单独钉住

这条语义里**最容易写错的一条**是「把模组关掉之后它又变回去」—— 而那种错在真机上看起来
和「判据根本没生效」**一模一样**（都是成就照样弹），只能靠纯逻辑一秒分清楚，
不值得为它跑一轮真机（真机一轮要退游戏、开 FTP、上卡、重启主机）。

所以这里分两半：
  1. **纯算术**在宿主上跑（编译 `mod_menu_native.hpp`，只调 `RunLatchNextState`）；
  2. **结构性判据**钉住「只有谁能改这颗闩锁」与「清零点挂在哪两处」—— 因为「多出第三处改它」
     正是那种「看代码看不出来、真机上偶尔发作」的错。

## 判据清单

1. 单向性：置位过之后，条件**不再成立**也必须仍然是 1（「关掉模组不解除」）；
2. 未置位 + 条件不成立 ⇒ 0（「全程没开过模组」那一局不锁）；
3. 条件成立 ⇒ 置位（「中途开启模组」从那一刻起锁）；
4. 真值表穷举：只有「已置位」或「条件成立」这两种情况是 1，其余是 0；
5. 只能有两处改这颗闩锁：置位只在 `ObserveRunLatch`、清零只在 `NoteNewRun` / `NoteRunLatchArmed`；
6. 判据本身必须**短接在闩锁上**（`AchievementsShouldBeBlockedFor` 里先问 `RunLatchLatched()`）；
7. 置位判据**只认正向证据**（读不到成就那一段时不许置位 —— 不许 fail-closed）；
8. 0→1 那一下必须**主动写一次**只读位（走引擎自己的 `SetReadOnly`，不直接写那个偏移）；
9. 清零点必须挂在 `GameExit` 与 `GameStart` **两处**，且 `GameExit` 那一路带了「挂点缺席则
   停用闩锁」的降级（`GameStart` 是 `Game::Start` 返回之后才回调的，单独用它会让上一局的闩锁渗进新局）。

## 批次 118 补的两条（117 上卡后的第一次真机读数暴露的）

10. **只在一局里观察**：117 的读数里人还在主菜单、闩锁却已经置位（`[45]=1 / [46]=1`，而
    `[35]` 引擎一次没调过 `SetReadOnly` ⇒ 还没进过任何一局）⇒ 「开机时开着模组、进局前把模组
    关掉」那一局会被误锁，而用户在开工单里的裁定①明确要求"不锁"。判据 = 观察必须吃「在一局里吗」，
    且那一格只能由 `NoteNewRun` 按**来源**维护（入局/出局的映射只留一处）。
11. **边沿写位必须当场读回并记账**（`[52]`/`[53]`）：那次读数里"闩锁置位过、只读位却是 0"，
    而当时没有任何格子能分清"没写进去"与"写了又被清掉"，只能推断 —— 现在把它变成事实。

## 批次 119 补的三条（用户 2026-09-25 裁定"继续同一份存档算同一局"）

12. **出局 ⇒ 把闩锁留成"留存"**：用户能改开关的唯一时机就是退出到主菜单（模组页在一局里
    打不开）⇒ 出局就清掉的话，"中途开启后又关掉仍锁"这条**永远观察不到**；
13. **继续 ⇒ 把留存接回来，并补写一次锁**：引擎那次开局写位发生在 `Game::StartFromSavedState`
    **体内**，而我们把留存接回来是在它**返回之后** ⇒ 必须由下一帧的观察点补写；
14. **开新局 ⇒ 连留存一起清**：否则"关掉模组后开新局"会被误锁（正是用户最早报的形状），
    而用户选的裁定①要求"进局前关掉模组 ⇒ 这一局不锁"。
"""

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
CPP = SOURCE / "mod_menu_native.cpp"
HPP = SOURCE / "mod_menu_native.hpp"
HOOK_MANAGER = SOURCE / "hook_manager.cpp"

HARNESS = r'''
#include "mod_menu_native.hpp"

#include <cstdio>

using isaac::runtime::modmenu::RunLatchNextState;

namespace {
int failures = 0;
void Check(bool condition, const char* label) {
    if (!condition) { std::printf("FAIL %s\n", label); ++failures; }
}
}  // namespace

int main() {
    // (1) 单向性 —— 这一条就是用户要的那句「中途关掉也仍然禁」：置位过之后条件消失也不许下去。
    Check(RunLatchNextState(false, true) == true, "已置位 + 条件不再成立 => 仍然是 1（单向，不解除）");
    // (2) 没置位、条件也不成立 => 不锁（「全程没开过模组」那一局照给成就）。
    Check(RunLatchNextState(false, false) == false, "未置位 + 条件不成立 => 0");
    // (3) 条件成立 => 置位（「中途开启模组」从那一刻起锁）。
    Check(RunLatchNextState(true, false) == true, "未置位 + 条件成立 => 置位");
    // (4) 已置位 + 条件仍成立 => 保持（幂等：每帧都会走这一格）。
    Check(RunLatchNextState(true, true) == true, "已置位 + 条件仍成立 => 保持 1");
    // (5) 真值表穷举：只有「已置位 或 条件成立」才是 1（防顺手写成 && 或取反这类错）。
    for (int cond = 0; cond <= 1; ++cond) {
        for (int latched = 0; latched <= 1; ++latched) {
            const bool expected = (cond != 0) || (latched != 0);
            if (RunLatchNextState(cond != 0, latched != 0) != expected) {
                std::printf("FAIL 真值表（条件=%d 已置位=%d）\n", cond, latched);
                ++failures;
            }
        }
    }
    if (failures != 0) { std::printf("ACHIEVEMENT_RUN_LATCH_CHECKS_FAILED %d\n", failures); return 1; }
    std::printf("ACHIEVEMENT_RUN_LATCH_CHECKS_PASSED\n");
    return 0;
}
'''


def function_body(text: str, signature: str) -> str:
    """取一个函数的函数体（从签名起、到下一个顶格的 `}` 为止）。"""
    assert signature in text, f"没找到 {signature}"
    return text.split(signature, 1)[1].split("\n}\n", 1)[0]


def code_only(text: str) -> str:
    """去掉行注释之后的代码（判据只看代码，注释里必须能自由解释「为什么不用某个写法」）。"""
    return re.sub(r"//[^\n]*", "", text)


class AchievementRunLatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = CPP.read_text(encoding="utf-8")
        cls.hpp = HPP.read_text(encoding="utf-8")
        cls.hook = HOOK_MANAGER.read_text(encoding="utf-8")

    # ---- 1) 纯算术：单向性（在宿主上编一份夹具跑）--------------------------------

    def test_latch_arithmetic_on_host(self):
        compiler = next((shutil.which(c) for c in ("c++", "clang++", "g++")
                         if shutil.which(c)), None)
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-achievement-run-latch-") as directory:
            workdir = Path(directory)
            source = workdir / "harness.cpp"
            source.write_text(HARNESS.lstrip(), encoding="utf-8")
            binary = workdir / "harness"
            build = subprocess.run(
                [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE),
                 str(source), "-o", str(binary)],
                text=True, capture_output=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("ACHIEVEMENT_RUN_LATCH_CHECKS_PASSED", run.stdout)

    # ---- 2) 只有两处能改这颗闩锁 -------------------------------------------------

    def test_only_two_places_may_change_the_latch(self):
        """★ 这条是整个语义的**全部机制**：多出第三处改它 = 「关掉模组之后仍然禁」就会偶尔失效。

        （那种错的真机现象 = 成就照样弹，与「判据没生效」分不开，所以必须在这里钉死。）
        """
        code = code_only(self.cpp)
        # ① 「把闩锁抬起来」只许出现在 `ObserveRunLatch` 里，且只有两种抬法：
        #    正常观察的 `= next`、以及"接回留存"的 `= true`（批次 119）。
        observe = function_body(code, "bool ObserveRunLatch")
        self.assertEqual(len(re.findall(r"g_RunLatchLatched\s*=\s*next;", code)), 1,
                         "「按条件置位」只能出现在 `ObserveRunLatch` 里")
        self.assertEqual(len(re.findall(r"g_RunLatchLatched\s*=\s*true;", code)), 1,
                         "「接回留存」那一处置位也只能出现在 `ObserveRunLatch` 里")
        self.assertIn("g_RunLatchLatched = next;", observe, "置位要在 `ObserveRunLatch` 里")
        self.assertIn("g_RunLatchLatched = true;", observe, "接回留存也在 `ObserveRunLatch` 里")
        # ② 「把闩锁放下」只许出现在 `NoteNewRun`（局边界）与 `NoteRunLatchArmed`（停用）里：
        #    直接数**全文**的赋值条数与这两个函数体里的条数是否相等 —— 比"数字对不对"更结实，
        #    别处多一处就会让「关掉模组之后仍然是 1」偶尔失效。
        #    ★ 注意：**变量定义那一行**（`bool g_RunLatchLatched = false;`）长得也像赋值 ——
        #      它只是初始化，不是「放下」，所以先把定义行摘掉再数。
        definition = r"bool\s+g_RunLatchLatched\s*=\s*false;"
        self.assertEqual(len(re.findall(definition, code)), 1,
                         "闩锁的初值只能有一处（匿名命名空间里的那一行定义）")
        clears = re.findall(r"g_RunLatchLatched\s*=\s*false;", re.sub(definition, "", code))
        in_boundary = re.findall(r"g_RunLatchLatched\s*=\s*false;",
                                 function_body(code, "void NoteNewRun"))
        in_disarm = re.findall(r"g_RunLatchLatched\s*=\s*false;",
                               function_body(code, "void NoteRunLatchArmed"))
        self.assertEqual(len(clears), len(in_boundary) + len(in_disarm),
                         "「把闩锁放下」只许出现在 `NoteNewRun`（局边界）与 `NoteRunLatchArmed`（停用）里；"
                         "别处多出来的那一处会把用户的「关掉也不解除」破坏掉")
        self.assertGreaterEqual(len(in_boundary), 1, "`NoteNewRun` 里必须有放下闩锁的那一步")
        new_run = function_body(code, "void NoteNewRun")
        self.assertIn("g_RunLatchLatched = false;", new_run, "清零要在 `NoteNewRun` 里")

    # ---- 3) 判据必须短接在闩锁上 -------------------------------------------------

    def test_the_judgement_short_circuits_on_the_latch(self):
        body = function_body(code_only(self.cpp), "bool AchievementsShouldBeBlockedFor")
        self.assertIn("RunLatchLatched()", body,
                      "判据必须先问闩锁 —— 否则「中途开过模组、之后关掉」这一局会被放行")
        self.assertLess(body.index("RunLatchLatched()"),
                        body.index("ModMenuEnabledCount() == 0"),
                        "闩锁那一问必须排在「没有模组在用时一律放行」**之前**"
                        "（排后面就等于闩锁永远轮不到）")

    # ---- 4) 置位只认正向证据（不许 fail-closed）---------------------------------

    def test_the_latch_is_set_only_on_positive_evidence(self):
        body = function_body(code_only(self.cpp), "void UpdateAchievementDisallow")
        call = re.search(r"ObserveRunLatch\(([^;]*?)\)\)", body)
        self.assertIsNotNone(call, "每帧要观察一次闩锁（「中途开启模组」只有这里看得到）")
        condition = call.group(1)
        self.assertIn("enabled != 0", condition, "条件里要有「真实模组处于启用状态」")
        self.assertIn("achievementBitsOk", condition,
                      "条件里要有「成就那一段确实读到了」—— 读不到时不许置位（不许 fail-closed）")
        self.assertIn("!wombUnlocked", condition, "条件里要有「成就 #4 未解锁」")
        # 反向：不许把「读不到」当成「没打过妈腿」（那正是 fail-closed 的形状）。
        self.assertNotRegex(condition, r"!\s*achievementBitsOk",
                            "不许出现「读不到也算成立」的写法 —— 那正是 fail-closed 的形状"
                            "（批次 098 已按用户裁定撤掉，不许回来）")

    # ---- 5) 0→1 那一下必须主动写一次只读位 ---------------------------------------

    def test_the_edge_actively_writes_the_readonly_bit_through_the_engine(self):
        body = function_body(code_only(self.cpp), "void UpdateAchievementDisallow")
        self.assertRegex(body, r"if\s*\(ObserveRunLatch\(",
                         "置位那一下要单独判出来（那是「中途开启模组」真正生效的唯一时机）")
        self.assertIn("WriteAchievementReadOnly(", body,
                      "0→1 那一帧必须**主动**把只读位写下去："
                      "引擎那次写只发生在开局路径上，不会再来第二次")
        writer = function_body(code_only(self.cpp), "void WriteAchievementReadOnly")
        self.assertIn("HookId::PersistentGameDataSetReadOnly", writer,
                      "要写就走**引擎自己的** `SetReadOnly`（全镜像唯一写那一位的地方）")
        self.assertNotIn("kPersistentReadOnlyOffset,", writer,
                         "不许自己直接写那个偏移（会绕开引擎的记账，另有门禁也钉着这一条）")
        self.assertIn("original == nullptr", writer,
                      "拿不到回退入口 ⇒ 什么都不做（宁可不禁，也不误禁）")

    # ---- 6) 清零点：两处，且 `GameExit` 那一路带降级 -----------------------------

    def test_both_reset_points_are_wired(self):
        exit_body = function_body(self.hook, 'extern "C" void EntryRelayGameExitCallback')
        # ★ 认**限定名**（`isaac::runtime::modmenu::NoteNewRun(...RunBoundaryKind::GameExit)`）：
        #   这里判的是「那一路通知了没有」，不是「名字怎么写的」。
        self.assertRegex(exit_body, r"NoteNewRun\([\w:]*RunBoundaryKind::GameExit\)",
                         "`GameExit` 必须通知一条局边界 —— 它在退出流程一开始触发，"
                         "**严格早于**下一局的任何写位（它在闩锁上的作用 = 把闩锁留成「留存」）")
        self.assertIn("gameExitCalls", exit_body,
                      "那一路还要记进状态面 [49]（它是「这条清零点确实会触发」的证据）")
        start_body = function_body(self.hook, "void ObserveGameStart")
        self.assertIn("NoteNewRun(", start_body,
                      "`GameStart` 也要通知局边界（开新局 / 继续，两者处置不同）")
        self.assertIn("RunBoundaryKind::NewRun", start_body, "新局那一支要写清种类")
        self.assertIn("RunBoundaryKind::LoadSave", start_body, "继续那一支也要写清种类")

    def test_the_latch_degrades_when_the_gameexit_hook_is_missing(self):
        """★ 清零点只挂 `GameStart` 时会把上一局的闩锁渗进新局 ⇒ 必须靠 `GameExit`；
        而 `GameExit` 是可选挂点（`required = false`）⇒ 它缺席时**宁可退回实时判据**。"""
        install = function_body(code_only(self.cpp), "void ModMenuNativeInstall")
        self.assertRegex(install, r"NoteRunLatchArmed\(\s*isaac::runtime::Original<[^>]*>"
                                  r"\(HookId::GameExit\)\s*!=\s*nullptr\s*\)",
                         "安装时要按「`GameExit` 挂点装上了没有」决定闩锁是否启用")
        observe = function_body(code_only(self.cpp), "bool ObserveRunLatch")
        self.assertIn("if (!g_RunLatchArmed)", observe,
                      "闩锁停用时必须直接不置位（= 完全退回批次 107 的实时判据）")
        self.assertIn("runLatchArmed", self.hpp,
                      "状态面要有「闩锁可用否」那一格（不然现场分不出「没置位」与「停用了」）")
        self.assertIn("runLatchArmed", self.cpp, "安装时要把那一格写下来")

    # ---- 7) 只在一局里观察（批次 118：117 的第一次真机读数暴露的缺陷）----------------

    def test_the_latch_is_only_observed_inside_a_run(self):
        """★★ 117 上卡后的第一次读数：人还在**主菜单**，闩锁却已经被置位（`[45]=1 / [46]=1`，
        而 `[35]` 引擎一次没调过 `SetReadOnly`、`[47]/[49]` 都没动过 ⇒ 还没进过任何一局）。

        后果正是用户在开工单里的**裁定①**被违反：开机时开着模组、进局前把模组关掉，
        那一局本应**不锁**，却会被这颗在菜单上立起来的闩锁误锁。

        ⇒ 判据：观察必须吃「在一局里吗」这一格；而这一格只能由 `NoteNewRun` 按**来源**维护
        （入局/出局的映射只许留一处 —— 放在调用点就会变成"三处各自记得"）。
        """
        observe = function_body(code_only(self.cpp), "bool ObserveRunLatch")
        self.assertIn("g_RunLatchInRun", observe,
                      "观察必须吃「在一局里吗」这道闸门（否则菜单上就会置位）")
        self.assertLess(observe.index("if (!g_RunLatchInRun)"),
                        observe.index("g_RunLatchLatched = next;"),
                        "那道闸门必须排在**置位之前**（排后面等于没有）")
        new_run = function_body(code_only(self.cpp), "void NoteNewRun")
        self.assertIn("g_RunLatchInRun =", new_run,
                      "「在一局里吗」由 `NoteNewRun` 按来源维护（入局/出局映射只留一处）")
        self.assertIn("RunBoundaryKind::GameExit", new_run,
                      "出局那一支（`GameExit`）必须是把它放回 0 的那一支")
        self.assertIn("runInProgress", self.hpp,
                      "状态面要有「在一局里吗」那一格（否则现场分不出"
                      "「不在局里所以没置位」与「在局里但条件不成立」）")

    # ---- 8) 边沿写位必须带记账（批次 118）------------------------------------------

    def test_the_edge_write_records_whether_it_actually_landed(self):
        """★ 117 那次读数里「闩锁置位过 1 次、可只读位读出来还是 0」，当时**没有任何格子**
        能分清"没写进去"与"写进去了又被清掉" —— 只能靠推断。判据：写完之后**当场读回**并记账。"""
        writer = function_body(code_only(self.cpp), "void WriteAchievementReadOnly")
        self.assertIn("++g_ModMenuState.runLatchEdgeWrites", writer, "试过几次要记账（[52]）")
        self.assertIn("runLatchEdgeWriteResult", writer, "结果要记账（[53]）")
        self.assertIn("AddressOf(persistentGameData)", writer,
                      "读回要先算出那个字节的地址（写法理由见实现处的注释）")
        self.assertIn("ReadAt(", writer, "写完要**当场读回**，把「有没有生效」变成事实而不是推断")
        # 三种结果的常量都要在、且取值与 `.hpp`/读数工具那份口径一致（静默改号会让读数说谎）。
        for name, value in (("kEdgeWriteVerified", 1), ("kEdgeWriteNoOriginal", 2),
                            ("kEdgeWriteNotVisible", 3)):
            self.assertRegex(self.cpp, rf"{name}\s*=\s*{value};",
                             f"{name} 必须是 {value}（读数工具按这个数解释；改号等于让读数说谎）")
        # 拿不到回退入口那一条必须仍然"什么都不写"（降级方向：宁可不禁，也不误禁）。
        no_original = writer.split("original == nullptr", 1)[1].split("}", 1)[0]
        self.assertNotIn("original(", no_original, "拿不到回退入口时不许硬调")
        self.assertIn("kEdgeWriteNoOriginal", no_original, "那一支要记下「没写」这个事实")

    # ---- 9) 「继续同一份存档算同一局」（批次 119，用户 2026-09-25 裁定）-------------

    def test_continue_keeps_the_taint_and_a_new_run_clears_it(self):
        """★★ 用户裁定：**继续同一份存档算同一局**。

        为什么非要这样：用户能改开关的唯一时机就是「退出到主菜单」（模组页在一局里打不开），
        而若「退出即清零」，「中途开启后又关掉仍锁」这条**永远观察不到**。
        ★ 它与裁定①（进局前关掉模组 ⇒ 这一局不锁）并不矛盾：那一条说的是**开新局**，
        而开新局必须连「留存」一起清掉。

        所以三条判据缺一不可：
          (1) 出局 ⇒ 把闩锁**留成留存**（不许清成「这份存档是干净的」）；
          (2) 继续 ⇒ 把留存接回来，而且**必须补写一次锁**（引擎那次开局写位发生在我们接回来之前）；
          (3) 开新局 ⇒ **连留存一起清**（否则「关掉模组后开新局」会被误锁 = 用户最早报的形状）。
        """
        new_run = function_body(code_only(self.cpp), "void NoteNewRun")
        # (1) 出局：闩锁转成留存
        self.assertIn("g_RunLatchCarriedOver = g_RunLatchLatched;", new_run,
                      "出局时要把闩锁**留存**下来（直接清掉的话，用户那条语义就永远看不到）")
        # (2) 继续：留存 ⇒ 待接回
        self.assertIn("g_RunLatchResumePending = g_RunLatchCarriedOver;", new_run,
                      "继续同一份存档要把留存接回来")
        # (3) 开新局：连留存一起清
        self.assertIn("RunBoundaryKind::NewRun", new_run, "开新局那一支必须存在")
        new_run_branch = new_run.split("RunBoundaryKind::NewRun", 1)[1].split("break;", 1)[0]
        self.assertIn("g_RunLatchCarriedOver = false;", new_run_branch,
                      "开新局必须连**留存**一起清（裁定①：进局前关掉模组 ⇒ 这一局不锁）")
        self.assertIn("g_RunLatchResumePending = false;", new_run_branch, "待接回也要一并清掉")
        # 接回来必须补写一次锁：观察点要为这一幕返回一次 true
        observe = function_body(code_only(self.cpp), "bool ObserveRunLatch")
        self.assertIn("if (g_RunLatchResumePending)", observe, "观察点要认出「待接回」这一幕")
        resume = observe.split("if (g_RunLatchResumePending)", 1)[1]
        self.assertIn("g_RunLatchLatched = true;", resume.split("return true;", 1)[0],
                      "接回来就是把闩锁抬成 1")
        self.assertIn("g_RunLatchResumePending = false;", resume.split("return true;", 1)[0],
                      "接回只做一次（消费掉，别每帧都当成新边沿）")
        self.assertIn("return true;", resume,
                      "★ 必须返回 true ⇒ 调用方**补写一次锁**（引擎那次写在我们接回来之前，"
                      "不补写就等于这一局没锁上）")
        for field in ("runLatchCarriedOver", "runLatchResumes"):
            self.assertIn(field, self.hpp, f"状态面要有 {field} 那一格（现场要看得出接回没接回）")
            self.assertIn(field, code_only(self.cpp), f"{field} 要被真的写下去")


if __name__ == "__main__":
    unittest.main()