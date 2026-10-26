"""批次 409（2026-10-08）：`ModManager::LoadConfigs` **尾部**那一步 ——
把 `gfx/ui/mod_defaults.anm2` 载进 `ModManager + 0x368` 那个 ANM2。

## 这一批修的是什么（一句话）

引擎在"逐模组喂完 content + `EntityConfig::PostLoadMods()`"之后还有一步收尾：把
`gfx/ui/mod_defaults.anm2` 载进 `ModManager + 0x368`（= **模组道具在暂停屏上的默认图标**）。
批次 378 重放 `ModManager::LoadConfigs` 时**只重放到 `PostLoadMods`**，漏了这一步 ⇒ 那个 ANM2
永远默认构造（层数组基址 `[ANM2+0xA8]` 为空）⇒ 暂停屏上出现**模组道具（id ≥ 733）**时
`RenderCustomCollectionItem` 走"默认"分支 ⇒ `ANM2::GetLayer(0)` 算出地址 `0`、再 `+0x80`
⇒ 写 `0x80` 的 `Data Abort`（真机 2026-10-08 13:45 实测；报告
`dist/crash-20261008-1345/01791438320_010021c000b6a000.log`）。

★ 为什么值得一条门禁：**这一步漏掉时没有任何别的可观察信号**（不涨容器、不产生回调、
不报错），只在"用户带着模组道具暂停"那一刻崩。

## 本门禁只做宿主机能做的判定

  1. `0x41ED54` 处那 25 字节字面量确实是 `"gfx/ui/mod_defaults.anm2"`，`0x41ED3C` 确实是
     `add x19, x19, #0x368`（⇒ 载入目标就是 `ModManager+0x368`）；
  2. 暂停屏那两处判据在现场：`0x433254 cmp w23, #0x2dd`（733 = 本体收集品上限之后）；
  3. 接线在 `mod_menu_native.cpp` 里**排在 `PostLoadMods` 之后**、同一个一次性闩锁里；
  4. `ANM2::Load` 地址取 `kSpriteLoadOffset`（**不**另立常量、**不**在运行期核对序言 ——
     那个入口已被批次 363 的中继改写过头部，核对会必然失败）；
  5. 状态面（75 个 u32）/ 读数工具（38 个字、`<75I`）/ 读数打印三处同步。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
CONSTANTS = SOURCE / "runtime_constants.hpp"
CPP = SOURCE / "mod_menu_native.cpp"
HPP = SOURCE / "mod_menu_native.hpp"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"
MOD_MENU_TEST = ROOT / "runtime" / "tests" / "test_mod_menu_native_production.py"
NRO = (
    ROOT
    / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
    / "Program #0"
    / "1"
    / ".nro"
    / "Repentance.nro"
)

#: `ModManager::LoadConfigs` 尾部那一步的两处现场（文件偏移）。
POS_ANM2_MEMBER = 0x41ED3C          # `add x19, x19, #0x368`
POS_PATH_LITERAL = 0x8AC790         # `"gfx/ui/mod_defaults.anm2"`
POS_PAUSE_MOD_ITEM_CMP = 0x433254   # `cmp w23, #0x2dd`
EXPECTED_ANM2_MEMBER = bytes.fromhex("73A20D91")
EXPECTED_PAUSE_CMP = bytes.fromhex("FF760B71")


class Batch409Test(unittest.TestCase):
    def setUp(self):
        self.constants = CONSTANTS.read_text(encoding="utf-8")
        self.cpp = CPP.read_text(encoding="utf-8")
        self.hpp = HPP.read_text(encoding="utf-8")
        self.reader = READER.read_text(encoding="utf-8")
        if not NRO.is_file():
            self.skipTest(f"没有游戏镜像 {NRO}")
        self.nro = NRO.read_bytes()

    # ---- 1) 常量与镜像现场 --------------------------------------------------

    def test_anm2_member_offset_is_the_engine_immediate(self):
        self.assertIn("inline constexpr uintptr_t kModManagerDefaultAnm2Offset = 0x368;",
                      self.constants, "载入目标必须是 `ModManager + 0x368`（引擎 `0x41ED3C` 的立即数）")
        self.assertEqual(self.nro[POS_ANM2_MEMBER:POS_ANM2_MEMBER + 4],
                         EXPECTED_ANM2_MEMBER,
                         "`0x41ED3C` 现场不是 `add x19, x19, #0x368` ⇒ 偏移写错了")

    def test_path_literal_matches_the_engine_and_the_constant(self):
        literal = self.nro[POS_PATH_LITERAL:self.nro.index(b"\0", POS_PATH_LITERAL)]
        self.assertEqual(literal, b"gfx/ui/mod_defaults.anm2",
                         "`0x8AC790` 现场不是那个文件名字面量")
        match = re.search(r'inline constexpr char kModManagerDefaultAnm2Path\[\] = "([^"]+)";',
                          self.constants)
        self.assertIsNotNone(match, "没找到 `kModManagerDefaultAnm2Path`")
        self.assertEqual(match.group(1).encode(), literal,
                         "常量里的路径与引擎字面量不一致（差一个字节就是静默空 ANM2）")

    def test_pause_screen_boundary_is_still_733(self):
        """暂停屏"这一条是模组道具吗"的判据（`cmp w23, #0x2dd` = 733）。"""
        self.assertEqual(self.nro[POS_PAUSE_MOD_ITEM_CMP:POS_PAUSE_MOD_ITEM_CMP + 4],
                         EXPECTED_PAUSE_CMP,
                         "`0x433254` 现场不是 `cmp w23, #0x2dd` ⇒ 崩溃链的描述需要重核")

    def test_no_duplicate_anm2_load_constant(self):
        """一个地址只留一个名字：不许另立 `kAnm2Load*`（它已被批次 363 的中继改写过头部）。"""
        self.assertNotIn("kAnm2LoadFileOffset", self.constants,
                         "`0xC970` 已有 `kSpriteLoadOffset` ⇒ 不许再立一个同地址常量")
        self.assertIn("inline constexpr uintptr_t kSpriteLoadOffset = 0xC970;", self.constants)
        self.assertIn("kModFeedAnm2LoadFailureBit = 1U << 18;", self.constants,
                      "`ANM2::Load` 拿不到时要占 bit18（`modEngineLoaderFailures`）")

    # ---- 2) 接线：顺序 + 地址来源 -------------------------------------------

    def test_call_is_after_post_load_mods_in_the_same_latch(self):
        body = self.cpp.split("void RunPostLoadModsOnceIfDue(", 1)[1]
        body = body.split("\n}\n", 1)[0]
        self.assertIn("g_PostLoadModsDone.compare_exchange_strong", body,
                      "收尾那一步必须在同一个一次性闩锁里（引擎只跑一次）")
        self.assertIn("modEnginePostLoadModsCalls += 1;", body)
        self.assertIn("LoadModManagerDefaultAnm2Once(manager);", body,
                      "收尾那一步必须在 `PostLoadMods` **之后**（引擎 `0x41ED34` → `0x41ED7C`）")
        self.assertLess(body.index("modEnginePostLoadModsCalls += 1;"),
                        body.index("LoadModManagerDefaultAnm2Once(manager);"),
                        "顺序反了：`PostLoadMods` 必须在前")

    def test_address_comes_from_kSpriteLoadOffset(self):
        self.assertIn("g_Anm2LoadAddress = module.base + kSpriteLoadOffset;", self.cpp,
                      "地址必须取 `模块基址 + kSpriteLoadOffset`")
        self.assertNotIn("VerifyEntryBytes(address + kAnm2Load", self.cpp,
                         "不许对那个入口做运行期序言核对（头部已被中继改写）")

    def test_content_loaded_is_measured_before_the_finish_step(self):
        """★★ 本批真正的根因：`EngineModContentLoaded()` 读的是 After/Before 这两对全局，
        而它们原来在收尾**之后**才赋值 ⇒ 收尾那道闸读到的是上一轮的读数 ⇒
        `PostLoadMods` + 紧跟的 ANM2 载入**永远不执行**。

        真机实测：`[70]=154`、`[72]=11`、`[73]=11`、`stage=2`（容器确实涨了：music 119→205、
        costume 132→160），唯独 `[71] PostLoadMods = 0`、`[74] ANM2 载入 = 0`。
        """
        body = self.cpp.split("bool LoadEngineModContent(", 1)[1]
        body = body.split("\n}\n", 1)[0]
        finish = body.index("RunPostLoadModsOnceIfDue(manager,")
        self.assertLess(body.index("g_MusicEntryCountAfter = CountMusicEntries(manager);"), finish,
                        "`g_MusicEntryCountAfter` 必须在收尾**之前**赋值"
                        "（否则 `EngineModContentLoaded()` 读到的是上一轮的读数）")
        self.assertLess(body.index("g_CostumeCountAfter = CountNullCostumeEntries(manager);"), finish,
                        "`g_CostumeCountAfter` 必须在收尾**之前**赋值")
        # 阶段字仍在收尾之后（它就该反映"这一轮最后的结果"）。
        self.assertGreater(body.index("g_ModEngineScanStage = 2;"), finish)

    def test_load_helper_passes_contract_arguments(self):
        body = self.cpp.split("void LoadModManagerDefaultAnm2Once(", 1)[1]
        body = body.split("\n}\n", 1)[0]
        # 三个实参：this = ModManager+0x368、路径串、bool = 1（引擎 `0x41ED70 mov w2, #0x1`）。
        self.assertIn("kManagerToModManagerOffset + kModManagerDefaultAnm2Offset", body)
        self.assertIn("kModManagerDefaultAnm2Path", body)
        self.assertIn("AddressOf(pathBytes)", body)
        self.assertTrue(re.search(r"AddressOf\(pathBytes\)\), 1\);", body),
                        "第三个实参必须是 1（引擎传的就是 1）")
        # 用引擎自己的 `std::string::assign` 造串（不自己写 libc++ 那 24 字节布局）。
        self.assertIn("g_ModEntryStringAssignAddress", body)
        # ★ 两处计数都要写：独立全局（读数工具按裸名直读）**与**状态面那一格 [74]。
        #   只写前者 ⇒ 读数工具打出来的 [74] 恒为 0（诊断口撒谎，比没有诊断更坏）。
        self.assertIn("g_ModEngineModDefaultsAnm2Loads += 1;", body)
        self.assertIn("g_ModMenuState.modEngineDefaultAnm2Loads += 1;", body,
                      "状态面那一格也要写，否则读数 [74] 恒 0")

    # ---- 3) 状态面 / 读数工具同步 -------------------------------------------

    def test_state_surface_has_the_new_field(self):
        self.assertIn("std::uint32_t modEngineDefaultAnm2Loads;", self.hpp,
                      "状态面要有 [74]（那一步被调几次，正常 = 1）")

    def test_reader_reads_the_new_word_and_prints_it(self):
        self.assertIn("'g_ModEngineModDefaultsAnm2Loads': 'g_ModEngineModDefaultsAnm2Loads',",
                      self.reader)
        self.assertIn("'mod_engine_mod_defaults_anm2_loads'", self.reader)
        # 状态面后来已扩到90格；仍核对读数宽度与生产测试的真实计数一致。
        from .test_mod_menu_native_production import STATE_FIELDS
        self.assertGreaterEqual(STATE_FIELDS,75)
        self.assertIn(f"('mod_menu_state', base + SYMS['mod_menu_state'], {(STATE_FIELDS+1)//2})", self.reader)
        self.assertIn(f"unpack_from('<{STATE_FIELDS}I'", self.reader)
        self.assertIn("[74]", self.reader, "读数里要把这一格打出来")

    def test_mod_menu_gate_pins_75_fields(self):
        text = MOD_MENU_TEST.read_text(encoding="utf-8")
        match=re.search(r"^STATE_FIELDS = (\d+)",text,re.M)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(int(match.group(1)),75)


if __name__ == "__main__":
    unittest.main()
