"""门禁：`ItemConfig_Item` 布局表（`tools/layout_tables/item_config_item.json`）。

## 为什么单开这张表

`tools/layout_tables/item.json` 登记的是 `ItemConfig` 的**容器边界**（六个 `std::vector<Item*>` 的
begin/end），它自己的门禁把"每行宽度必须是 8"钉死了；而本表登记的是**元素内部**的字段
（目前只有一行：null 服装的 anm2 路径，24 字节 libc++ `std::string`，`+0x88`）⇒ 塞进那张表会当场判红，
也会把"容器边界"与"元素字段"两种语义混在一起。

**消费者**：`tools/api_definition_of_done.json` 里 `Isaac:GetCostumeIdByPath` 的
`provenance.field`（`engine_field` 要求布局表里有 `confirmed` 的那一行）。

## 它钉住什么

1. **证据可复现**：`--verify` 重新反汇编每条证据（缺 NRO 则跳过，与其它布局表门禁同口径）；
2. **口径合法**：confidence 取值、每行必须有语义与证据、`confirmed` 必须有**机器核对过**的一类证据；
3. **与手写常量不许漂移**：同一批偏移在 `runtime_constants.hpp` 里还有手写的一份
   （`kItemConfigItemNullCostumePathOffset`），"整体迁"之前两边必须逐条相同 —— 否则迁移会静默换掉偏移；
4. **与台账不许漂移**：`api_definition_of_done.json` 里任何 `provenance.field` 以 `ItemConfig_Item.`
   开头的条目，都必须在本表里有一行 `confirmed`（否则台账在引用一个布局表里不存在/不可信的字段）；
5. **版本锁定**：`build_id` 必须是仓库里那一个固定镜像。

## 一处诚实的局限（写进表头，也在这里留痕）

本表**没有生成的头文件**（`item_config_item_layout.hpp` 不存在），所以这里**不跑 `--check`**：
本表的消费者是台账，不是 C++ 代码。将来要把实现切到生成常量时，再补"生成头 + `--check`"那一半
（与 `item_layout.hpp` 同一套做法），别半途生成 —— 表头的 `note` 里也写明这一条。

另：`confirmed` 一般要求一条"能证明**名字**"的语义证据（`item.json` 那条门禁就是这么要求 `semantic`/`device`
的）。本表把判据定成"至少一条 `access`/`device` 类、机器核对过的证据"，理由是这一行的名字锚点不是单条
立即数，而是**两个不同函数在同一个偏移上把它当服装路径用**（写入侧 `LoadCostumes` 的
`add x0,x19,#0x88` 与读取侧 `AddCostume` 的 `ldrb w8,[x23,#0x88]!` + SSO 判定）—— 这两条都在 `access`
类里逐条复核过。判据写在这里，不许悄悄放宽。
"""

import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "build_layout_table.py"
TABLE = ROOT / "tools" / "layout_tables" / "item_config_item.json"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
LEDGER = ROOT / "tools" / "api_definition_of_done.json"
NRO = ROOT / (
    "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    "/Program #0/1/.nro/Repentance.nro"
)
CONFIDENCES = {"confirmed", "candidate", "structural"}
MACHINE_CHECKED_KINDS = {"access", "device"}
CONST_RE = re.compile(
    r"^inline constexpr (?:std::)?uintptr_t (k[A-Za-z0-9]+Offset) = (0x[0-9A-Fa-f]+);", re.M)

#: 行名 → 手写常量名。**显式列出**而不是按名字拼：本表的行名（`NullCostumePath`）与手写常量名
#: （`kItemConfigItemNullCostumePathOffset`，中间多一个 `Item`）口径不同，靠拼名字会静默漏对账。
HANDWRITTEN = {"NullCostumePath": "kItemConfigItemNullCostumePathOffset"}


def run_tool(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), "--table", str(TABLE), *arguments],
        text=True, capture_output=True, cwd=ROOT,
    )


class ItemConfigItemLayoutTableTests(unittest.TestCase):
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

    def test_every_row_declares_a_known_confidence(self):
        self.assertTrue(self.table["rows"], "表是空的？")
        for row in self.table["rows"]:
            with self.subTest(row=row["name"]):
                self.assertIn(row["confidence"], CONFIDENCES)
                self.assertTrue(row["evidence"], "每行都必须带证据")
                self.assertTrue(row["semantic"], "每行都必须写清语义")
                self.assertGreater(row["width"], 0, "宽度必须写明")

    def test_confirmed_rows_carry_machine_checked_evidence(self):
        """`confirmed` 必须至少有一条**机器核对过**的证据（`access` / `device`）。

        本表把判据定成这一类（而不是 `item.json` 那条"必须有 `semantic`/`device`"），因为这一行的
        名字锚点是"两个不同函数在同一偏移上把它当服装路径用"—— 两条都在 `access` 类里逐条复核。
        """
        for row in self.table["rows"]:
            if row["confidence"] != "confirmed":
                continue
            with self.subTest(row=row["name"]):
                kinds = {entry.get("kind", "access") for entry in row["evidence"]}
                self.assertTrue(kinds & MACHINE_CHECKED_KINDS,
                                f"{row['name']} 没有机器可核对的证据（{sorted(kinds)}）")

    def test_offsets_agree_with_the_handwritten_constants(self):
        """★ 同一偏移的手写常量与表里那一行必须同值（迁移前两边不许漂移）。"""
        handwritten = dict(CONST_RE.findall(CONSTANTS.read_text(encoding="utf-8")))
        rows = {row["name"]: row for row in self.table["rows"]}
        self.assertEqual(sorted(HANDWRITTEN), sorted(rows),
                         "本表的行与这份对账映射对不上（加行时要一起改这里）")
        for name, constant in HANDWRITTEN.items():
            with self.subTest(row=name, constant=constant):
                self.assertIn(constant, handwritten,
                              f"{constant} 不在 runtime_constants.hpp 里（表与实现脱节了）")
                self.assertEqual(int(handwritten[constant], 16), rows[name]["offset"],
                                 f"{name}：表里是 {rows[name]['offset']}、"
                                 f"{constant} 是 {handwritten[constant]} —— 两处必须一致")

    def test_ledger_fields_from_this_struct_exist_here(self):
        """★ 台账不许引用本表里没有（或不是 `confirmed`）的字段。"""
        confirmed = {row["name"] for row in self.table["rows"]
                     if row["confidence"] == "confirmed"}
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
        referenced = set()
        for key, row in ledger["rows"].items():
            field = (row.get("provenance") or {}).get("field")
            if isinstance(field, str) and field.startswith(f"{self.table['struct']}."):
                name = field.split(".", 1)[1]
                referenced.add((key, name))
                with self.subTest(api=key, field=field):
                    self.assertIn(name, confirmed,
                                  f"{key} 的真值来源引用了 {field}，"
                                  f"但本表没有 `confirmed` 的那一行")
        self.assertTrue(referenced, "台账里没有一条引用本表？那这张表多半已经没人用了")

    def test_build_id_is_the_fixed_target(self):
        """表锁定在固定版本上：换版本必须整体重做，不能沿用旧偏移。"""
        self.assertEqual(self.table["build_id"], "91C73FDD575061318D68886316AFEAC72388B2AB")

    def test_no_generated_header_yet(self):
        """★ 本表**目前没有生成的头文件**（消费者是台账）—— 半途生成会让"哪份是真值"变模糊。"""
        header = ROOT / "runtime" / "source" / "item_config_item_layout.hpp"
        self.assertFalse(header.is_file(),
                         "出现了 item_config_item_layout.hpp：要么补齐生成 + `--check` 那一半"
                         "（照 item_layout.hpp 的做法），要么删掉它 —— 不许半途生成")


if __name__ == "__main__":
    unittest.main()