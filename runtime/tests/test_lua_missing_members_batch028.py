"""门禁：批次 028 那四条"接口面补缺"的常量与登记不许漂。

## 为什么要有它

这一批接的四条（`ItemPool:GetPillEffect` / `ItemPool:GetPoolForRoom` / `Level:GetLastRoomDesc` /
`EntityPickup:CanReroll`）都是**直接调引擎方法**的接口，判据是"模块基址 + 偏移 + 4 字节入口指纹"。
三样里任何一样写错，现象都是**真机上悄悄调错函数或调不动**（不是报错），而真机一轮验证的代价很高。

所以这里把"我们声明的值"与"镜像里的值"钉在一起：

1. 四个偏移常量与四个入口字常量必须在 `runtime_constants.hpp` 里，且**取值与镜像一致**
   （这里的字面量是取证结果，写死是有意的：改了常量而没重新取证，这条就红）；
2. 四个处理器必须在各自的绑定表里登记（模块基址 + 偏移那一套调用点的前提）；
3. 处理器里必须**真的核对入口指纹**（少了它，"偏移写错"就没人拦）。

（与项目其它源码门禁同一形态：不做 C++ 解析，只做受控的文本提取。）
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"

#: 取证结果（偏移 / 入口整字 / 符号），来自 `tools/nro_disasm.py` 与符号表。
EXPECTED = {
    "kItemPoolGetPillEffectOffset": ("0x3C857C", "0xA9BD7BFD"),
    "kItemPoolGetPoolForRoomOffset": ("0x3C5C7C", "0xD10103FF"),
    "kLevelGetLastRoomDescOffset": ("0x3DC69C", "0x5282AB88"),
    "kEntityPickupCanRerollOffset": ("0x26AFA8", "0x39470C09"),
}


class MissingMembersBatch028Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.constants = CONSTANTS.read_text(encoding="utf-8")
        cls.isaac_api = ISAAC_API.read_text(encoding="utf-8")
        cls.remaining_api = REMAINING_API.read_text(encoding="utf-8")
        cls.catalog = CATALOG.read_text(encoding="utf-8")

    def test_offsets_and_entry_words_match_the_evidence(self):
        for name, (offset, word) in EXPECTED.items():
            with self.subTest(constant=name):
                self.assertIn(f"inline constexpr uintptr_t {name} = {offset};", self.constants)
                word_name = name.replace("Offset", "EntryWord")
                self.assertIn(f"inline constexpr std::uint32_t {word_name} = {word}U;",
                              self.constants)

    def test_handlers_verify_the_entry_word_before_calling(self):
        """四条处理器都必须在调用前核对入口指纹 —— 少了它，偏移写错就没人拦。"""
        for function, word in (("ItemPoolGetPillEffect", "kItemPoolGetPillEffectEntryWord"),
                               ("ItemPoolGetPoolForRoom", "kItemPoolGetPoolForRoomEntryWord"),
                               ("LevelGetLastRoomDesc", "kLevelGetLastRoomDescEntryWord"),
                               ("EntityPickupCanReroll", "kEntityPickupCanRerollEntryWord")):
            with self.subTest(function=function):
                source = self.isaac_api if function == "EntityPickupCanReroll" else self.remaining_api
                body = source[source.index(f"int {function}(lua_State* state) {{"):]
                body = body[:body.index("\n}\n") + 3]
                fingerprint = "kItemPoolGetPillEffectExpectedBytes" if function == "ItemPoolGetPillEffect" else word
                self.assertIn(fingerprint, body, f"{function} 没有核对入口指纹")
                self.assertIn("IsEngineMemoryReadable", body, f"{function} 没有可读性检查")

    def test_table_entries_and_catalog_rows_exist(self):
        # ⚠️ 登记**在哪张表里**同样重要：实体方法按 owner 分表挂到各自的元表上，
        # 登记错表的现象是"处理器在、目录行在、门禁也过"，但模组调它得到 nil
        # （2026-09-18 实测：`EntityPickup:CanReroll` 被登记进 `EntityPlayer` 那张表 ⇒ 探针 `R=ERR`）。
        for binding in ("{0x05010004, &ItemPoolGetPillEffect}",
                        "{0x05010005, &ItemPoolGetPoolForRoom}",
                        "{0x0301000E, &LevelGetLastRoomDesc}"):
            with self.subTest(binding=binding):
                self.assertIn(binding, self.remaining_api, f"绑定表里没有 {binding}")
        pickup_table = self.isaac_api[
            self.isaac_api.index("constexpr LuaHandlerBinding kEntityPickupHandlers[]"):]
        pickup_table = pickup_table[:pickup_table.index("};")]
        self.assertIn("{0x0E01002B, &EntityPickupCanReroll}", pickup_table,
                      "`EntityPickup:CanReroll` 必须登记在 `kEntityPickupHandlers` 里"
                      "（登记到别的 owner 的表 ⇒ 模组调它是 nil）")
        for row in ("ApiDomain::ItemPool, 1, 0x0004", "ApiDomain::ItemPool, 1, 0x0005",
                    "ApiDomain::Level, 1, 0x000E", "ApiDomain::Isaac, 1, 0x002B"):
            with self.subTest(row=row):
                self.assertIn(row, self.catalog, f"目录里没有 {row}")

    def test_entity_npc_can_reroll_is_deferred_not_silently_missing(self):
        """同名的 `EntityNPC:CanReroll` 是**故意没做**（我们没有 `EntityNPC` 视图）——
        理由必须写在源码里，免得下一个人以为漏了。"""
        self.assertIn("Entity_NPC::CanReroll", self.constants)
        self.assertIn("本批不做", self.constants)


if __name__ == "__main__":
    unittest.main()
