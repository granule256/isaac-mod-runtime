"""门禁：`Font:DrawString*` 的**绘制计数必须覆盖全部四个变体**。

## 为什么要有它

2026-09-18 的事故：读数工具会打印"画字：`DrawString*` 调用 N 次"，而当时那几个计数点写在
`DrawStringVariant` 的**未缩放分支**（`else`）里 ⇒ `Font:DrawStringScaled` /
`DrawStringScaledUTF8` **一次都不记**。而 EID、q4-items、自带菜单、我们自己的
`Isaac.RenderScaledText` **全都走缩放变体** —— 于是真机上读数恒为 `0`，
这句"0"被当成过"屏幕上一个字都没画"的证据（当天差点把一个**探针自身只在第一帧画一次**的毛病
误判成运行时缺陷；`docs/问题与解决记录.md` 续五十八）。

**规则**：计数（次数/字节/alpha/缩放）与 API 序列位必须在**四条变体共用的路径**上；
变体之间只允许"序列位不同"。谁把计数挪回某个分支里，这条门禁就红。

（与项目其它源码门禁同一形态：不做 C++ 解析，只做受控的文本提取。）
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FONT_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "font_api.cpp"

#: 四个变体的 API 序列位（`api_sequence_probe.hpp` 的位表）。
SEQUENCE_BASES = ("32U + (scaled ? 1U : 0U) + (unicode ? 2U : 0U)",)


class FontDrawInstrumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = FONT_API.read_text(encoding="utf-8")
        start = cls.text.index("int DrawStringVariant(")
        cls.body = cls.text[start:cls.text.index("\n}\n", start)]

    def test_counters_live_before_the_variant_branch(self) -> None:
        """计数必须在 `if (scaled)` **之前** —— 那才是四条变体共用的位置。"""
        branch = self.body.index("if (scaled) {")
        before = self.body[:branch]
        for needle in ("g_FontDrawCalls.fetch_add", "g_FontDrawBytes.fetch_add",
                       "RecordApiSequenceDraw", "g_FontDrawAlpha.store"):
            with self.subTest(counter=needle):
                self.assertIn(needle, before,
                              f"{needle} 必须在 `if (scaled)` 之前（否则缩放变体不被计数）")

    def test_scale_is_recorded_for_the_scaled_variants(self) -> None:
        before = self.body[:self.body.index("if (scaled) {")]
        self.assertIn("g_FontDrawScaleX.store", before)
        self.assertIn("lua_isnumber(state, 5)", before)

    def test_sequence_bit_distinguishes_all_four_variants(self) -> None:
        for needle in SEQUENCE_BASES:
            with self.subTest(needle=needle):
                self.assertIn(needle, self.body)

    def test_the_reader_tool_says_the_counter_covers_all_variants(self) -> None:
        """读数工具的措辞必须与实现同口径（它曾断言"未缩放变体"，现在不该再那样限制）。"""
        reader = (ROOT / "tools" / "read_device_state_via_gdb.py").read_text(encoding="utf-8")
        self.assertNotIn("**未缩放**变体（`Font:DrawString` / `DrawStringUTF8`）调用", reader)
        self.assertIn("四条变体", reader)


if __name__ == "__main__":
    unittest.main()
