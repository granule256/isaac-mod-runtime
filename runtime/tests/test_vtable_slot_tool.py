"""门禁：`tools/nro_vtable_slot.py`（批次 318，2026-10-03）—— 从 `_ZTV<类>` 反查虚函数槽号。

## 为什么要有这条门禁

`HUD:Update` / `GridEntity:Update` 各 **95 个实现**、`EntityPlayer:GetShootingInput` 14 处 ——
这些 API 的**名字完全没用**，唯一出路是走 **vtable 槽号**（本仓库约定：`offset` 最高位置 1 =
按槽号虚调用、低 31 位 = 槽号；`target = [对象首字 + 槽号*8]`，批 303 立、批 304 修正）。

槽号**看不出来、只能读出来**：vtable 在文件里全是 0，靠加载时的 `R_AARCH64_ABS64`(257) +
符号索引填（★ **不是** `R_AARCH64_RELATIVE` —— `parse_dynamic_relocations()` 会把 `sym == 0`
的记录跳过 ⇒ 那条路拿不到东西）。**批 303/304 当年是手工读的**，本批把它固化成工具。

## 这条门禁钉住什么

★ **在批 303/304 已经落地、槽号早已核过的四组上复核工具** ——
工具是"证据生成器"，它自己错了会让后面每一批都错，所以**必须拿已知答案验它**：

| 类 | 槽 | 应当是 |
| --- | --- | --- |
| `Entity` | 0 / 1 | 两个析构变体（Itanium 特有；★ PC/MSVC 只有一个 ⇒ **PC 槽号比 Switch 小 1**）|
| `Entity` | 2 / 4 | `Init` / `Update` |
| `Entity` | **18** | `CanShutDoors`（批 303 落地的那条）|
| `Entity_NPC` | **18** | `CanShutDoors` **另一份实现** ⇒ "同一槽号、整棵树一致" |
| `GridEntity` | 2 / 6 | `PostInit` / `Destroy(bool)`（批 304 落地的两条）|
| `GridEntity` | 3 / 4 | `__cxa_pure_virtual`（纯虚槽，派生类必须覆盖）|

★ 还要钉住**边界**：`_ZTV` 在 `.data.rel.ro` 里是**紧挨着排**的 ⇒ 长度必须有上界，
否则槽表会一路走进下一张表（本工具第一版就这么错的：`Entity` 的 `--find` 一次报出 4 个槽）。
"""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "nro_vtable_slot.py"
NRO = ROOT / (
    "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    "/Program #0/1/.nro/Repentance.nro"
)


def run_tool(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *arguments],
        text=True, capture_output=True, cwd=ROOT,
    )


class VtableSlotToolTests(unittest.TestCase):
    def setUp(self):
        if not NRO.is_file():
            self.skipTest(f"缺少用户提供的固定 NRO：{NRO}")

    def slots_of(self, class_name: str) -> dict[int, str]:
        result = run_tool(class_name)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        slots: dict[int, str] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line.startswith("slot "):
                continue
            index_text, name = line.split("=", 1)
            slots[int(index_text.split()[1])] = name.strip()
        return slots

    def test_entity_slots_match_batch_303(self):
        """`Entity`：槽 18 = `CanShutDoors`（批 303 落地的那条）、槽 2/4 = `Init`/`Update`。"""
        slots = self.slots_of("Entity")
        #: Itanium 特有：开头两个析构变体（`D2` = 完整对象析构、`D0` = 删除析构）。
        self.assertIn("D2Ev", slots[0])
        self.assertIn("D0Ev", slots[1])
        self.assertIn("4Init", slots[2])
        self.assertIn("6UpdateEv", slots[4])
        self.assertIn("CanShutDoors", slots[18])

    def test_the_same_slot_holds_another_class_implementation(self):
        """★ `Entity_NPC` 的槽 18 是 **另一份** `CanShutDoors` 实现 ⇒ 槽号整棵树一致（虚函数的定义）。"""
        entity = self.slots_of("Entity")
        npc = self.slots_of("Entity_NPC")
        self.assertIn("CanShutDoors", npc[18])
        self.assertNotEqual(entity[18], npc[18],
                            "两个类在同一个槽上必须各有自己的实现（否则不是虚函数）")
        self.assertIn("Entity", entity[18])
        self.assertIn("Entity_NPC", npc[18])

    def test_grid_entity_slots_match_batch_304(self):
        """`GridEntity`：槽 2 = `PostInit`、槽 6 = `Destroy`（批 304 落地）、槽 3/4 = 纯虚。"""
        slots = self.slots_of("GridEntity")
        self.assertIn("8PostInitEv", slots[2])
        self.assertIn("7DestroyEb", slots[6])
        self.assertEqual(slots[3], "__cxa_pure_virtual")
        self.assertEqual(slots[4], "__cxa_pure_virtual")

    def test_the_slot_table_is_bounded_by_the_next_symbol(self):
        """★ 长度必须有上界：`Entity` 的 vtable 是 26 个槽（无上界时会走进下一张表）。

        ★ 边界证据：`Entity` 与 `Entity_NPC` 的槽表**槽数相同**（26）—— 两张表挨着排，
        它们之间只隔着各自的 `_ZTI…`（在 vtable+8、落在槽 0 之前）。
        """
        entity = self.slots_of("Entity")
        npc = self.slots_of("Entity_NPC")
        self.assertEqual(sorted(entity), list(range(26)))
        self.assertEqual(sorted(npc), list(range(26)))

    def test_find_all_scans_every_vtable_at_once(self):
        """★ `--find-all`（320 起）：一次扫**所有** vtable 找名字。

        为什么值得单独钉：它是「**这个虚函数被哪些类覆盖**」这个问题的唯一工具化入口
        （319/321 都靠它：`--find-all Update` 一次列出几十个派生类都在槽 3/4）。
        ★ 实现上它必须**一次解析、反复查**（早先每查一个类都重解析一遍重定位 ⇒ 全表扫要几分钟，
        改良后 **0.3 秒**）—— 所以这里顺带断言"它真的扫到了不止一张表"。
        """
        result = run_tool("--find-all", "CanShutDoors")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("_ZTVN15IsaacRepentance6EntityE", result.stdout)
        self.assertIn("_ZTVN15IsaacRepentance10Entity_NPCE", result.stdout)
        #: 同一个槽号出现在**两张不同的表**里 ⇒ 它真的在逐表扫，而不是只看第一张。
        self.assertGreaterEqual(result.stdout.count("slot 18"), 2, result.stdout)

    def test_find_all_reports_nothing_for_a_bogus_name(self):
        """找不到 ⇒ 退出码非 0 + 说清楚（不是静默空输出）。"""
        result = run_tool("--find-all", "NoSuchSlotNameForSure")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("没有名字含", result.stderr + result.stdout)

    def test_unknown_class_is_reported(self):
        """名字拼错 ⇒ 报错、不是静默给一张空表。"""
        result = run_tool("NoSuchClassForSure")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("_ZTV", result.stderr + result.stdout)

    def test_list_mode_names_the_vtables(self):
        """`--list` 能列出镜像里的 `_ZTV<类>`（接手时不知道类名拼法就靠它）。"""
        result = run_tool("--list")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("_ZTVN15IsaacRepentance6EntityE", result.stdout)
        self.assertIn("_ZTVN15IsaacRepentance10GridEntityE", result.stdout)


if __name__ == "__main__":
    unittest.main()
