"""门禁：`SoundEffects::SoundEffect` 布局表（`tools/layout_tables/sound_effect.json`，批次 265）。

## 为什么单开这张表

`runtime_constants.hpp` 里既有的音效常量只登记**单例地址**（`kManagerSoundEffectsOffset`）与
**容器边界**（`kSoundEffectVectorBeginOffset`/`EndOffset`/`kSoundEffectSize`），
元素的**内部字段**从来没登记过；而 `Isaac:GetSoundIdByName` 要读元素里的名字串
⇒ 按批次 047 起的纪律（"字段在布局表里 ≠ 字段对外可用"，对外可用要求那一行 `confirmed`）
必须有这一张表。与 `music_entry.json` / `item_config_item.json` 同一条处置。

**消费者**：`tools/api_definition_of_done.json` 里 `Isaac:GetSoundIdByName` 的 `provenance.field`。

## 它钉住什么

1. **证据可复现**：`--verify` 重新反汇编每条证据引的那条指令；
2. **口径合法**：confidence 取值、每行必须有语义与证据、宽度必须写明；
3. **`confirmed` 必须有机器可核对的证据**（`access` / `device`）；
4. **与手写常量不许漂移**：同一偏移在 `runtime_constants.hpp` 里还有手写的一份；
5. **与台账不许漂移**：台账里任何 `provenance.field` 以本表 `struct` 开头的条目，都必须在本表里有
   `confirmed` 的一行；
6. **版本锁定**：`build_id` 必须是仓库里那一个固定镜像。

## ★ 与 `music_entry.json` 第一版错误的关系（本表的证据形态是刻意选的）

曲目表的第一版把名字登记在偏移 0，依据是**读路径排除法**，被真机否掉了（`+0x00` 其实是编号）。
本表两行都用**写侧属性分派**（`strcmp(属性名, …)` → 目标槽）这种能一锤定音的证据，
不走排除法 —— `test_evidence_is_the_write_side_attribute_dispatch` 这一格就是钉住这一点：
两行引的都必须是 `SoundEffects::LoadConfig`。
"""

import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "build_layout_table.py"
TABLE = ROOT / "tools" / "layout_tables" / "sound_effect.json"
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

#: 行名 → 手写常量名（显式列出，不按名字拼 —— 拼名字会静默漏对账）。
HANDWRITTEN = {"Id": "kSoundEffectIdOffset", "Name": "kSoundEffectNameStringOffset"}
#: 本表两行都必须引到的那个函数（写侧属性分派）。
LOAD_CONFIG = "_ZN15IsaacRepentance12SoundEffects10LoadConfigEPKcb"


class SoundEffectLayoutTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = json.loads(TABLE.read_text(encoding="utf-8"))

    def test_evidence_reproduces_against_the_fixed_nro(self):
        """每条证据都要能重新反汇编核对 —— 这是"布局表可复核"的全部意义。"""
        if not NRO.is_file():
            self.skipTest(f"缺少用户提供的固定 NRO：{NRO}")
        result = subprocess.run(
            [sys.executable, str(TOOL), "--table", str(TABLE), "--verify"],
            text=True, capture_output=True, cwd=ROOT,
        )
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
        for row in self.table["rows"]:
            if row["confidence"] != "confirmed":
                continue
            with self.subTest(row=row["name"]):
                kinds = {entry.get("kind", "access") for entry in row["evidence"]}
                self.assertTrue(kinds & MACHINE_CHECKED_KINDS,
                                f"{row['name']} 没有机器可核对的证据（{sorted(kinds)}）")

    def test_evidence_is_the_write_side_attribute_dispatch(self):
        """★ 两行的锚点都必须是**写侧属性分派**（`LoadConfig`），不许用读路径排除法。

        理由就是曲目表那次返工（见文件头）：排除法给出的「唯一自洽位置」可能是别的东西。
        """
        for row in self.table["rows"]:
            with self.subTest(row=row["name"]):
                functions = {entry["function"] for entry in row["evidence"]}
                self.assertIn(LOAD_CONFIG, functions,
                              f"{row['name']} 没有引写侧属性分派（{sorted(functions)}）")

    def test_offsets_agree_with_the_handwritten_constants(self):
        """同一偏移的手写常量与表里那一行必须同值（迁移前两边不许漂移）。"""
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
                name = field[len(self.table["struct"]) + 1:]
                referenced.add((key, name))
                with self.subTest(api=key, field=field):
                    self.assertIn(name, confirmed,
                                  f"{key} 的真值来源引用了 {field}，但本表没有 `confirmed` 的那一行")
        self.assertTrue(referenced, "台账里没有一条引用本表？那这张表多半已经没人用了")

    def test_build_id_is_the_fixed_target(self):
        self.assertEqual(self.table["build_id"], "91C73FDD575061318D68886316AFEAC72388B2AB")

    def test_no_generated_header_yet(self):
        """★ 本表**目前没有生成的头文件**（消费者是台账）—— 半途生成会让"哪份是真值"变模糊。"""
        header = ROOT / "runtime" / "source" / "sound_effect_layout.hpp"
        self.assertFalse(header.is_file(),
                         "出现了 sound_effect_layout.hpp：要么补齐生成 + `--check` 那一半"
                         "（照 item_layout.hpp 的做法），要么删掉它 —— 不许半途生成")


if __name__ == "__main__":
    unittest.main()
