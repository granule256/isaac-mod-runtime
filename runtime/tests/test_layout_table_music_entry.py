"""门禁：`Music::Entry` 布局表（`tools/layout_tables/music_entry.json`）。

## 为什么单开这张表

`runtime_constants.hpp` 里既有的音乐常量只登记**容器边界**（`Music + 0x3D8/+0x3E0` 与步长 `0x70`），
元素的**内部字段**从来没登记过。批次 148 的 `Isaac:GetMusicIdByName` 要读元素起点那段名字串，
按项目纪律（批次 047 起）：**字段在布局表里 ≠ 字段对外可用**，而"对外可用"要求那一行是 `confirmed`
⇒ 必须有这一张表。与 `item_config_item.json` 同一条处置：它登记的是**元素字段**，
塞进"容器边界"那种表会把两种语义混在一起。

**消费者**：`tools/api_definition_of_done.json` 里 `Isaac:GetMusicIdByName` 的 `provenance.field`。

## 它钉住什么

1. **证据可复现**：`--verify` 重新反汇编每条证据引的那条指令（缺 NRO 则跳过，与其它布局表门禁同口径）；
2. **口径合法**：confidence 取值、每行必须有语义与证据、宽度必须写明；
3. **与手写常量不许漂移**：同一偏移在 `runtime_constants.hpp` 里还有手写的一份
   （`kMusicEntryNameStringOffset`）—— "整体迁"之前两边必须逐条相同；
4. **与台账不许漂移**：`api_definition_of_done.json` 里任何 `provenance.field` 以 `Music.Entry.`
   开头的条目，都必须在本表里有一行 `confirmed`；
5. **版本锁定**：`build_id` 必须是仓库里那一个固定镜像。

## 一处诚实的局限（写进表头，也在这里留痕）

这一行的名字锚点**不是**某条立即数指令里的 `#0x0`，而是「`Music::Play` 与
`Music::StreamSet::Load` 两条读路径都不碰 `条目+0x00..+0x1F`」这个**排除法**结论
⇒ 两条证据各指一条**能反汇编复核**的指令（`umaddl`（编号=下标、元素连续）与
`ldrb w8,[x1,#0x20]!`（第一条字段访问就跳到 +0x20）），推断写在 `semantic` 里。
判据定成"至少一条 `access` 类、机器核对过的证据"（与 `item_config_item.json` 那条一致），
**不许悄悄放宽**。

★ 另：本表**没有生成的头文件**（`music_entry_layout.hpp` 不存在），所以这里**不跑 `--check`**：
本表的消费者是台账，不是 C++ 代码（与 `item_config_item.json` 同一条）。
"""

import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "build_layout_table.py"
TABLE = ROOT / "tools" / "layout_tables" / "music_entry.json"
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

#: 行名 → 手写常量名。**显式列出**而不是按名字拼：本表的行名（`Name`）与手写常量名
#: （`kMusicEntryNameStringOffset`，中间多一个 `String`）口径不同，靠拼名字会静默漏对账。
#: ★ 2026-09-27（批次 149c）：加了 `Id` 行（偏移 0）—— 真机把第一版"名字在 +0x00"的
#: 排除法推断否掉了（读数里"最后一条的名字"读出 `0x78` = 120 = 它的下标），
#: 写侧属性分派证明 `+0x00` 是 `id`、`+0x08` 才是 `name`。两行都要与手写常量对账。
HANDWRITTEN = {"Id": "kMusicEntryIdOffset", "Name": "kMusicEntryNameStringOffset"}


def run_tool(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), "--table", str(TABLE), *arguments],
        text=True, capture_output=True, cwd=ROOT,
    )


class MusicEntryLayoutTableTests(unittest.TestCase):
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
        """`confirmed` 必须至少有一条**机器核对过**的证据（`access` / `device`）—— 理由见文件头。"""
        for row in self.table["rows"]:
            if row["confidence"] != "confirmed":
                continue
            with self.subTest(row=row["name"]):
                kinds = {entry.get("kind", "access") for entry in row["evidence"]}
                self.assertTrue(kinds & MACHINE_CHECKED_KINDS,
                                f"{row['name']} 没有机器可核对的证据（{sorted(kinds)}）")

    def test_the_two_read_paths_are_both_cited(self):
        """★ 这一行的推断是**排除法**（两条读路径都不碰 `+0x00..+0x1F`）⇒ 两条都必须真被引到。

        只引一条（例如只引 `umaddl`）就只剩"元素连续"，证明不了名字在起点 ⇒ 断言必须钉住两条函数。
        """
        rows = {row["name"]: row for row in self.table["rows"]}
        self.assertIn("Name", rows)
        functions = sorted(entry["function"] for entry in rows["Name"]["evidence"])
        for required in ("_ZN15IsaacRepentance5Music4PlayENS_6eMusicEf",
                         "_ZN15IsaacRepentance5Music9StreamSet4LoadERKNS0_5EntryEff"):
            with self.subTest(function=required):
                self.assertIn(required, functions,
                              "排除法那一行的两条读路径证据必须都在（少一条就只剩半个推断）")

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
                # ★ 用"去掉整个 struct 前缀"而不是 `split('.', 1)`：本表的 struct 自己带点
                #   （`Music.Entry`），按第一个点切会把 `Entry.Name` 当成字段名（写完就红了）。
                name = field[len(self.table["struct"]) + 1:]
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
        header = ROOT / "runtime" / "source" / "music_entry_layout.hpp"
        self.assertFalse(header.is_file(),
                         "出现了 music_entry_layout.hpp：要么补齐生成 + `--check` 那一半"
                         "（照 item_layout.hpp 的做法），要么删掉它 —— 不许半途生成")


if __name__ == "__main__":
    unittest.main()