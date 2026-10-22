"""门禁：`EntityLaser` 视图 + `EntityLaser:SetActiveRotation`（批次 282，2026-10-02）。

## 这一批是什么

照批次 281 给 `EntityTear` 立的那套「**新视图六处接线**」逐条复制，给 `EntityLaser` 建视图，
并把 `Entity:ToLaser()` 改成压它 —— 语料 `laser:SetActiveRotation(...)`（6 处）此前报
`attempt to call a nil value`，根因同样是「`ToLaser()` 压的是 `Entity` 元表 ⇒ 方法没地方挂」。

## 为什么这个文件是**静态**的

与批次 281 同一个原因：**宿主造不出一根激光句柄** —— 唯一的句柄来源 `Isaac.GetPlayer(0)` 按
`vptr == base + kEntityPlayerVtableOffset` 校验，而 `ToLaser()` 的判据要求
`vptr == base + kEntityLaserVtableOffset` ⇒ 不可能同时成立。
⇒ 这里只钉**六处接线与目录/台账**；**行为判据 = 作业单 V33**（打出一道激光科技、看
`e:ToLaser()` 给 `userdata` 且 `SetActiveRotation` 不报错）。
★ 与其写一条"连不上所以恒过"的假断言，不如把范围说清楚。
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
HANDLES = ROOT / "runtime" / "source" / "lua_object_handles.hpp"
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
CATALOG_TEST = ROOT / "runtime" / "tests" / "contract" / "test_api_catalog.py"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"


class EntityLaserViewBatch282Tests(unittest.TestCase):
    def test_view_is_wired_in_every_place(self):
        """★ 六处接线必须都在（漏一处就是"方法取不到"或"死代码"）。"""
        body = ISAAC_API.read_text(encoding="utf-8")
        handles = HANDLES.read_text(encoding="utf-8")
        self.assertIn('kEntityLaserMetatable[] = "IsaacRuntime.EntityLaser"', handles)
        self.assertIn("EntityView::Laser", body)
        self.assertIn("int EntityLaserIndex(lua_State* state) {", body)
        self.assertIn("EntityView::Laser);", body)
        self.assertIn("luaL_testudata(state, index, kEntityLaserMetatable)", body)
        self.assertIn("luaL_newmetatable(state, kEntityLaserMetatable)", body)

    def test_old_entity_methods_are_not_lost_on_the_new_view(self):
        """新视图不能退化：`IndexEntity` 的回落链必须仍然指向 `Entity` 的方法表。"""
        body = ISAAC_API.read_text(encoding="utf-8")
        self.assertIn("if (view != EntityView::Base && PushMethodFrom(state, kEntityMetatable, field))",
                      body)

    def test_catalog_binding_and_owner_table(self):
        """目录行 + 绑定行；★ 还要在「文件 → 允许的 owner」表里登记新 owner（否则门禁红）。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        body = ISAAC_API.read_text(encoding="utf-8")
        self.assertIn('MakeId(ApiDomain::Isaac, 1, 0x00BA), ApiDomain::Isaac, "EntityLaser", '
                      '"SetActiveRotation"', catalog)
        self.assertRegex(body, r"\{\s*(?i:0x0e0100ba),\s*&EntityLaserSetActiveRotation\s*\}")
        self.assertIn('"EntityLaser"', CATALOG_TEST.read_text(encoding="utf-8"))

    def test_entry_offset_is_sixteen_byte_guarded(self):
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("kEntityLaserSetActiveRotationOffset = 0xF7540", constants)
        self.assertIn("kEntityLaserSetActiveRotationExpectedBytes", constants)

    def test_shoot_angle_is_included_with_the_seventh_argument_recorded(self):
        """★ 2026-10-03（批次 325）：`ShootAngle` 由「**故意不收**」翻成「**已收**」—— 原排除理由被推翻。

        批 282 当年按「引擎符号 **7** 参 vs 契约 **6** 参」（多一个尾参 `bool`）把它排除；
        批 325 去读了 PC 那条绑定（`0x8C7550`）：PC 也收 **7** 个参数、`push byte [ebp+0x20]`
        原样转发给 `Game::Spawn` ⇒ 差的第 7 格只是 **C++ 头里的缺省值**（契约页不写带缺省值的参数），
        ⇒ 按「**尾部 1 个可省**」处理（省略时保持 0），与 `Room:SetGridPath(int,int,int)` 同一档。
        ★ 教训：「契约少写一个」≠「引擎真的少一个」—— 遇到"文档参数个数 ≠ 符号参数个数"，
        必须先去 PC 看那条绑定收几个参数，而不是当缺口排除（这正是批 282 踩过的坑，本测试就是它的现场）。

        ⇒ 这条判据现在钉**翻案后**的现状：常量段既要有偏移 / 入口 word，也要留下
        "7 参 = 6 参 + 1 尾参 `bool`"与 PC 对齐的证据 —— 而不是像原版那样断言"常量不存在"。

        证据：批次 325 = `git show 95bef1e1`；`docs/改动日志-20261003.md` §二十九
        「★★★ 本批推翻了批 282 的一条排除理由」；现状常量 `runtime_constants.hpp:6631`
        （`kEntityLaserShootAngleOffset = 0xF743C`）。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        #: 翻案后：偏移常量 + 入口 word 都已进常量段（原来这里断言的正好相反）。
        self.assertIn("kEntityLaserShootAngleOffset = 0xF743C", constants)
        self.assertIn("kEntityLaserShootAngleEntryWord = 0xD101C3FFU", constants)
        #: ★ 翻案证据必须在：PC 那条绑定的地址 + 「尾部 1 个可省」的处置口径。
        #:   少了这两样，"7 参 vs 6 参"就又变回一个没人知道所以然的差异。
        self.assertIn("0x8C7550", constants)
        self.assertIn("尾部 1 个可省", constants)
        #: 常量段仍要提到 `ShootAngle` 这个名字（这条 API 的常量段本身）。
        self.assertIn("ShootAngle", constants)


if __name__ == "__main__":
    unittest.main()
