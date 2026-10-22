"""`g_InputActionAsked*` 探针必须可读 —— 批次 217（2026-09-30）。

## 为什么需要这一组

用户报「菜单只有方向上能选、下没反应」+「按一次触发很多次」。查这两个问题需要回答一句话：

> **用户按下的那一刻，菜单到底问没问那个动作，我们答的是真还是假？**

而原来那几张掩码（`g_InputActionQueriedMask` / `g_InputActionTriggeredMaskOther` /
`g_InputActionPressedMaskOther`）是**粘性**的 —— 一旦置位**永不清**，真机上早饱和成 `0x0fffffff`
（问过全部 28 个动作）⇒ 看它们**什么都得不出来**。

所以批次 217 记了"每个动作最后一次被问到时"的四项现场：**帧号 / 哪条 API / controller / 答案**。
带帧号才能说"刚才那几帧"（读数工具按"比最新一次提问早 ≤180 帧"筛）。

判据三条（读数工具会原样打印）：
① 问了且我们答 true ⇒ 问题在**模组自己的导航逻辑**；
② 问了但我们答 false ⇒ 查**我们的查询链**（手柄号 / 设备 / 引擎判定）；
③ **压根没被问** ⇒ 模组没走到那一步，别去查输入。

## 这条门禁钉什么

1. 四个探针符号在读数工具的 `SYM_ELF_NAMES` 里（不然真机读不到）；
2. 读数工具**真的把它们打印出来**（只进读取列表、漏了打印 = 等于没测）；
3. ★ 定义必须写在**匿名命名空间之外**（内部链接会让 ELF 里查不到 —— 批次 214 刚踩过第 5 次）；
4. kind 的三个取值在读数工具里有名字（0/1/2 → `IsActionTriggered`/`IsActionPressed`/`GetActionValue`）。
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
READER = ROOT / "tools" / "read_device_state_via_gdb.py"
IMPLEMENTATION = ROOT / "runtime" / "src" / "interfaces" / "lua" / "input_api.cpp"

SYMBOLS = ("g_InputActionAskedFrame", "g_InputActionAskedKind",
           "g_InputActionAskedController", "g_InputActionAskedAnswer",
           # 批次 218：**按键侧**同一套（判"菜单走按键分支还是动作分支"）。
           "g_InputButtonAskedFrame", "g_InputButtonAskedKind",
           "g_InputButtonAskedController", "g_InputButtonAskedAnswer",
           # 批次 218：按键侧与动作侧的边沿计数**分开**（以前共用一格 ⇒ 按下标分不清是哪一个）。
           "g_InputButtonEdgeCounts",
           # 批次 219：**"最后一次真的被激活"的帧号** —— 217/218 那两族记的是"最后一次被问时答什么"，
           # 而 MCM 每帧都问 ⇒ 永远读到"此刻的输入状态"；要判"推下时激活了哪个动作号"必须靠帧号。
           "g_InputActionHeldFrame", "g_InputButtonTriggeredFrame")
READ_KEYS = ("input_action_asked_frame", "input_action_asked_kind",
             "input_action_asked_controller", "input_action_asked_answer",
             "input_button_asked_frame", "input_button_asked_kind",
             "input_button_asked_controller", "input_button_asked_answer",
             "input_button_edge_counts",
             "input_action_held_frame", "input_button_triggered_frame")


class InputActionAskedProbeTests(unittest.TestCase):
    def test_implementation_defines_them_outside_the_anonymous_namespace(self):
        source = IMPLEMENTATION.read_text(encoding="utf-8")
        anonymous = source.index("\nnamespace {\n")
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                declaration = (f"std::atomic<std::uint32_t> {symbol}[32];"
                               if symbol != "g_InputButtonEdgeCounts"
                               else f"std::atomic<std::uint32_t> {symbol}[32];")
                self.assertIn(declaration, source, f"实现里必须有 {symbol}")
                # ★ 匿名命名空间里 = 内部链接 ⇒ ELF 符号表查不到 ⇒ 读数工具永远读不到（批次 214 真事故）。
                self.assertLess(source.index(declaration), anonymous,
                                f"{symbol} 必须定义在匿名命名空间**之外**")

    def test_reader_knows_and_prints_the_symbols(self):
        reader = READER.read_text(encoding="utf-8")
        for symbol in SYMBOLS:
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, reader, f"读数工具必须认得 {symbol}")
        for key in READ_KEYS:
            with self.subTest(key=key):
                printed = any(marker in reader for marker in (
                    f"'{key}' in values", f"first_u32(values, '{key}')",
                    f"first_u32(values, '{key}', index)", f"first_u32(values, '{key}', i)"))
                self.assertTrue(printed, f"读数工具必须打印 {key}")

    def test_action_and_button_edge_counts_are_separate_arrays(self):
        """按键号与动作号是**两套命名空间**：共用一个计数数组 ⇒ 按下标分不清是哪一个。"""
        source = IMPLEMENTATION.read_text(encoding="utf-8")
        self.assertIn("std::atomic<std::uint32_t> g_InputEdgeCounts[32];", source,
                      "动作侧仍记在 `g_InputEdgeCounts`")
        self.assertIn("std::atomic<std::uint32_t> g_InputButtonEdgeCounts[32];", source,
                      "按键侧必须有自己的计数数组")
        # 按键那条路径（`InputIsButtonTriggered`）不许再往动作侧那格写。
        handler = source[source.index("int InputIsButtonTriggered(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        # 注释里会**提到**旧数组名（解释"为什么改"），比对前先把注释去掉。
        code_only = re.sub(r"//[^\n]*", "", handler)
        self.assertIn("g_InputButtonEdgeCounts", code_only)
        self.assertNotIn("g_InputEdgeCounts", code_only,
                         "按键那条不许再往 `g_InputEdgeCounts` 累加")

    def test_the_three_kinds_are_named_and_the_verdict_is_printed(self):
        reader = READER.read_text(encoding="utf-8")
        for name in ("IsActionTriggered", "IsActionPressed", "GetActionValue"):
            self.assertIn(f"'{name}'", reader, f"kind 名字 {name} 要在读数工具里")
        # 判据文字必须在（读数的人不该自己去推三条分支）
        self.assertIn("压根没被问", reader, "三态判据要印在读数里")


if __name__ == "__main__":
    unittest.main()
