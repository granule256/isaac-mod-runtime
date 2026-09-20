"""门禁：`ItemConfig` 布局表（`tools/layout_tables/item.json` ↔ `runtime/source/item_layout.hpp`）。

## 为什么要有它

这张表登记的是 `ItemConfig` 的**容器边界**（六个 `std::vector<Item*>` 的 begin/end）。它的语义锚点
来自引擎自己的访问器，形状固定得几乎像签名：

    ldp x8, x9, [x0, #offset]     ; 取 begin(+offset) 与 end(+offset+8)
    sub x9, x9, x8
    lsr x9, x9, #3                ; ÷8 ⇒ 元素是 8 字节指针
    cmp w9, w1
    ldr x0, [x8, w1, uxtw #3]     ; 索引 × 8 取元素

所以本表的行**都可以**标 `confirmed`（有 `semantic` 证据），不像 room 表那样需要豁免名单。

## 它钉住什么

1. **证据可复现**：`--verify` 重新反汇编每条证据（缺 NRO 则跳过，与其它预算/符号门禁同口径）；
2. **生成物不过期**：`--check` 头文件必须与表一致；
3. **口径合法**：confidence 取值、每行必须有语义与证据、`confirmed` 必须有 `semantic`/`device` 锚点；
4. **★ 与手写常量不许漂移**（本表独有）：同一批偏移在 `runtime_constants.hpp` 里还有**手写**的一份
   （`kItemConfigCollectibleBeginOffset` …），"整体迁"之前两边必须逐条相同 —— 否则将来把使用点从
   手写切到生成的头时，会静默换掉偏移。这条把"同名常量必须同值"钉死。

## 一处诚实的局限（写进表头，也在这里留痕）

`End` 行的偏移值**无法**用"指令里出现立即数"的方式核对：`ldp` 一条指令读相邻两个 8 字节，
第二个偏移隐含在指令里。机器核对的是"它是与 begin 相邻的第二个指针"与"元素 8 字节"（`lsr #3`）。
"""

import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "build_layout_table.py"
TABLE = ROOT / "tools" / "layout_tables" / "item.json"
HEADER = ROOT / "runtime" / "source" / "item_layout.hpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
NRO = ROOT / (
    "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    "/Program #0/1/.nro/Repentance.nro"
)
CONFIDENCES = {"confirmed", "candidate", "structural"}
CONST_RE = re.compile(
    r"^inline constexpr (?:std::)?uintptr_t (k[A-Za-z0-9]+Offset) = (0x[0-9A-Fa-f]+);", re.M)


def run_tool(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), "--table", str(TABLE), *arguments],
        text=True, capture_output=True, cwd=ROOT,
    )


class ItemLayoutTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = json.loads(TABLE.read_text(encoding="utf-8"))

    def test_evidence_reproduces_against_the_fixed_nro(self):
        """每条证据都要能重新反汇编核对 —— 这是"布局表可复核"的全部意义。"""
        if not NRO.is_file():
            self.skipTest(f"缺少用户提供的固定 NRO：{NRO}")
        result = run_tool("--verify")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("通过", result.stdout)

    def test_generated_header_matches_the_table(self):
        """头文件必须与表一致（改表不改生成物 ⇒ 实现里读旧偏移）。"""
        result = run_tool("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_row_declares_a_known_confidence(self):
        for row in self.table["rows"]:
            with self.subTest(row=row["name"]):
                self.assertIn(row["confidence"], CONFIDENCES)
                self.assertTrue(row["evidence"], "每行都必须带证据")
                self.assertTrue(row["semantic"], "每行都必须写清语义")
                self.assertEqual(8, row["width"], "本表登记的都是 8 字节指针")

    def test_confirmed_rows_carry_a_name_justifying_anchor(self):
        """`confirmed` 必须有一条**能证明名字**的证据（取值/形状锚点），不能只有访问证据。"""
        for row in self.table["rows"]:
            if row["confidence"] != "confirmed":
                continue
            with self.subTest(row=row["name"]):
                kinds = {entry.get("kind", "access") for entry in row["evidence"]}
                self.assertTrue(kinds & {"semantic", "device"},
                                f"{row['name']} 只有访问证据（{sorted(kinds)}），不能标 confirmed")

    def test_begin_and_end_come_in_pairs(self):
        """六个向量必须成套登记：有 Begin 的行就必须有同前缀的 End（反之亦然）。

        本表登记的是"一对边界指针"；只登记一端会让"这对指针是向量边界"这个论证缺一半。
        """
        names = {row["name"] for row in self.table["rows"]}
        begins = {name for name in names if name.endswith("Begin")}
        self.assertTrue(begins, "一张都没有 Begin 行？")
        for begin in sorted(begins):
            with self.subTest(row=begin):
                self.assertIn(begin[: -len("Begin")] + "End", names, f"{begin} 缺少配对的 End")
        for row in self.table["rows"]:
            if row["name"].endswith("End"):
                with self.subTest(row=row["name"]):
                    self.assertIn(row["name"][: -len("End")] + "Begin", names)

    def test_generated_constants_agree_with_the_handwritten_ones(self):
        """★ 本表独有：同名常量在生成的头与手写常量表里**必须同值**。

        `runtime_constants.hpp` 里有一份手写的同批偏移（本表的行就是从那里来的）。
        "整体迁"把使用点切到生成的头之前，两边必须逐条相同 —— 否则迁移会静默换掉偏移。
        （只比两边都有的名字：本表还登记了手写表里没有的 `PlayerFormBegin`。）
        """
        generated = dict(CONST_RE.findall(HEADER.read_text(encoding="utf-8")))
        handwritten = dict(CONST_RE.findall(CONSTANTS.read_text(encoding="utf-8")))
        shared = sorted(set(generated) & set(handwritten))
        self.assertGreaterEqual(len(shared), 11,
                                f"两边同名常量太少了（{len(shared)} 条），是不是有人改了命名？")
        for name in shared:
            with self.subTest(constant=name):
                self.assertEqual(
                    int(handwritten[name], 16), int(generated[name], 16),
                    f"{name} 在 runtime_constants.hpp 里是 {handwritten[name]}、"
                    f"在 item_layout.hpp 里是 {generated[name]} —— 两处必须一致",
                )

    def test_only_confirmed_rows_are_offered_to_the_api(self):
        """生成的"可用字段"清单必须只含 `confirmed` 行。"""
        header = HEADER.read_text(encoding="utf-8")
        match = re.search(r"// 当前可用：(.*)", header)
        self.assertIsNotNone(match, "生成的头部缺少『当前可用』清单")
        listed = {item.strip() for item in match.group(1).split("、") if item.strip()}
        expected = {row["name"] for row in self.table["rows"] if row["confidence"] == "confirmed"}
        self.assertEqual(listed, expected)

    def test_build_id_is_the_fixed_target(self):
        """表锁定在固定版本上：换版本必须整体重做，不能沿用旧偏移。"""
        self.assertEqual(self.table["build_id"], "91C73FDD575061318D68886316AFEAC72388B2AB")
