"""后端选择来自 domain 的**侵入点登记表**（`kHookCatalog`）：入口中继 + GOT 槽 + RelaySlot。

登记表是唯一真值源（路由适配器用 `CatalogBackends()` 派生 `kHookBackends`），
所以这里解析登记表本身，并顺带钉住它的几条不变量。

（2026-09-20 批次 102：入口中继从四路涨到八路 —— 新增的四个事件靶点
`UseActiveItem`/`UseCard`/`UsePill`/`GameExit` 全部走 `EntryRelay`。下面两条期望值
跟着加长；**不是放宽**：每个挂点仍必须恰好一行、顺序仍必须与 `HookId` 一致。
2026-09-23 批次 077（模组页搬生产）：同样加长三条 —— `MenuGameRender`/`MenuTitleRender`/
`MenuManagerSetState` 都走 `EntryRelay`。）
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "runtime" / "src"
CATALOG = SRC / "domain" / "runtime" / "hook_catalog.hpp"
ROUTING = SRC / "infrastructure" / "hook_routing_adapter.hpp"

EXPECTED = ("ManagerUpdate", "ManagerRender", "PreGetCollectible",
            "ManagerPresent", "RebuildMountPoints", "GameStart",
            "UseActiveItem", "UseCard", "UsePill", "GameExit", "PickupCollision",
            "RoomEntitySpawn", "ImagePcxLoad",
            "ImageManagerLoadFile", "ContentGetMountedFilePath",
            "MenuGameRender", "MenuTitleRender", "MenuManagerSetState",
            # 批次 098（禁成就）：闸门挂在 `SetReadOnly` 上，同样走入口中继。
            "PersistentGameDataSetReadOnly",
            # 批次 147（2026-09-26）：引擎那条"模组 content 加载"路的闸门
            # （`ModManager::LoadConfigs` 入口），同样走入口中继。
            "ModManagerLoadConfigs",
            # 批次 363（2026-10-04）：`ANM2::Load` 入口中继（模组覆盖本体资源的最后一环）。
            "Anm2Load",
            # 批次 390（2026-10-07）：`MC_INPUT_ACTION` 的三条查询中继。
            "ManagerIsActionPressed", "ManagerIsActionTriggered", "ManagerGetActionValue",
            # 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG` 的四条 + `MC_EVALUATE_CACHE`，
            # 全部走零占洞入口中继。
            "EntityTakeDamage", "EntityPlayerTakeDamage", "EntityPickupTakeDamage",
            "EntitySlotTakeDamage", "EvaluateItems",
            # 批次 397（2026-10-07）：补全回调（第 2 批）的三条 hookable 改走入口中继
            # + `MC_POST_FIRE_TEAR`（同批，用批次 337 已定死的 ABI）。
            "EntityKill", "NpcDeathRemove", "GameEnd", "FireTear",
            'FamiliarCollision', 'NpcCollision', 'PlayerCollision', 'TearCollision', 'ProjectileCollision', 'KnifeCollision', 'BombCollision', 'NpcRender', 'ItemPoolGetPill', 'ItemPoolGetPillEffect', 'GameDevolveEnemy', 'NpcUpdateAi', 'GameSpawnEx', 'ItemPoolTrinketFirstRandom', 'ItemPoolTrinketSelected', 'RoomClearAward', 'EntityRemovePointers', 'EntityDestructorRemove', 'LevelCurseFirstRandom', 'LevelCurseEvaluation', 'PickupSelection', 'PickupSelectionSpecial', 'ItemPoolGetCard', 'ModManagerUnload', 'ConsoleUnknownLength', 'ConsoleUnknownCompare', 'HudRender', 'RoomConfigLoadStageBinary', 'LevelLoadRoom', 'LevelInit', 'ConsoleLifecycle', 'PressurePlateAnimationWriter', 'PressurePlateDestructor', 'PressurePlateDeletingDestructor', 'ProjectileUpdate', 'ProjectileInit', 'EntityPlayerInit', 'GameStartStageTransition', 'EntityInit', 'NativeInputPoll', 'RoomConstructor', 'GameRerollLevelPickups', 'GameRerollLevelCollectibles', 'EntityTearInit', 'EntityEffectInit')


def catalog_entries(text):
    """解析登记表，返回 [(挂点名, 后端, 是否必需), ...]，顺序即 HookId 顺序。"""
    body = re.search(r"kHookCatalog\s*=\s*\{\{(.*?)\}\};", text, re.S).group(1)
    rows = re.findall(
        r"\{\s*HookId::(\w+)\s*,\s*\"([^\"]*)\"\s*,\s*HookBackend::(\w+)\s*,\s*(true|false)\s*\}",
        body)
    return [(hook_id, backend, required == "true") for hook_id, _name, backend, required in rows]


class HookCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CATALOG.read_text(encoding="utf-8")

    def test_one_row_per_hook_in_id_order(self):
        entries = catalog_entries(self.text)
        self.assertEqual([row[0] for row in entries], list(EXPECTED),
                         "登记表必须每个挂点一行、顺序与 HookId 一致")
        order = re.search(r"enum class HookId[^{]*\{(.*?)\};", self.text, re.S).group(1)
        names = re.findall(r"(\w+)\s*(?:=\s*\d+)?\s*,", order)
        self.assertEqual(names[:len(EXPECTED)], list(EXPECTED), "HookId 顺序必须与登记表一致")

    def test_backends(self):
        backends = [row[1] for row in catalog_entries(self.text)]
        self.assertEqual(
            backends,
            ["EntryRelay", "EntryRelay", "EntryRelay", "GotSlot", "EntryRelay", "RelaySlot",
             "EntryRelay", "EntryRelay", "EntryRelay", "EntryRelay", "EntryRelay",
             "Internal", "EntryRelay", "EntryRelay", "EntryRelay",
             # 批次 077 的三个入口中继。
             "EntryRelay", "EntryRelay", "EntryRelay",
             # 批次 092：成就解锁的唯一漏斗（入口中继）。
             "EntryRelay",
             # 批次 147：模组 content 加载闸门（`ModManager::LoadConfigs` 入口中继）。
             "EntryRelay",
             # 批次 363：`ANM2::Load` 入口中继。
             "EntryRelay",
            # 批次 390（2026-10-07）：`MC_INPUT_ACTION` 的三条查询中继。
            "EntryRelay", "EntryRelay", "EntryRelay",
            # 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG` 四条 + `MC_EVALUATE_CACHE`。
            "EntryRelay", "EntryRelay", "EntryRelay", "EntryRelay", "EntryRelay",
            # 批次 397（2026-10-07）：补全回调（第 2 批）的四条。
            "EntryRelay", "EntryRelay", "EntryRelay", "EntryRelay"] + ["EntryRelay"] * 11 + ["GotSlot", "EntryRelay"] + ["Internal"] * 3 + ["GotSlot", "Internal"] + ["Internal"] * 4 + ["GotSlot", "GotSlot", "Internal", "Internal", "GotSlot", "GotSlot", "GotSlot", "GotSlot", "GotSlot", "EntryRelay", "Internal", "Internal", "RelaySlot", "RelaySlot", "EntryRelay", "EntryRelay", "GotSlot", "GotSlot", "EntryRelay", "GotSlot", "GotSlot", "GotSlot", "GotSlot"],
            "M2b 之后：入口中继 + ManagerPresent 走 GOT 槽；"
            "GameStart 走 RelaySlot（引擎侧中继已放好代码，我们只往槽里写回调指针）；"
            "批次 102 的四个事件靶点都走入口中继（零占洞）")

    def test_required_points_gate_mod_loading(self):
        required = [row[0] for row in catalog_entries(self.text) if row[2]]
        self.assertEqual(required, ["ManagerUpdate", "EntityInit", "NativeInputPoll",
                                    "RoomConstructor", "EntityTearInit", "EntityEffectInit"],
                         "原生更新、输入轮询、房间初始化及真实实体 Init 都是加载 Mod 的前置条件")

    def test_routing_table_is_derived_not_duplicated(self):
        routing = ROUTING.read_text(encoding="utf-8")
        self.assertIn("kHookBackends = CatalogBackends()", routing,
                      "路由表必须由登记表派生，不能出现第二处定义")
        self.assertNotIn("HookBackend::EntryRelay,", routing,
                         "路由表里不得再逐个列出后端（真值源在登记表）")

    def test_routing_adapter_delegates_to_all_backends(self):
        cpp = (ROUTING.parent / "hook_routing_adapter.cpp").read_text(encoding="utf-8")
        self.assertIn("kHookBackends", cpp)
        for member in ("legacy_", "relay_", "gotSlot_", "relaySlot_", "internal_"):
            self.assertIn(member, cpp)


if __name__ == "__main__":
    unittest.main()
