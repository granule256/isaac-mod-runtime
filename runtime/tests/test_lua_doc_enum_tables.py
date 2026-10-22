"""门禁：由**PC 文档快照**生成的全局枚举表（`runtime/source/program/doc_lua_enum_data.*`）。

## 为什么有这条门禁（2026-09-19 批次 048）

真机上 GoodTrip 的 `widget.lua:185` 报 `attempt to index a nil value (global 'RoomShape')` ——
我们只发布了 `pc_lua_enum_data` 里那 20 张表（输入是**用户 PC 游戏本体的 `enums.lua`**，不在仓库里），
那之外的表**没人能补**，于是模组读 `RoomShape.ROOMSHAPE_LTL` 拿到 `nil`，
整条绘制回调在小地图画出来之前被打断（用户只看到"按地图键没反应"）。

现在这几张表由 `tools/generate_doc_enum_tables.py` 从 **`analysis/isaacdocs-snapshot/docs/enums/`**
（仓库自带的 PC 文档快照）生成。这条门禁钉四件事：

1. **生成物与文档一致**：跑一次 `--check`，不一致就说明"改了文档没重新生成"（或反过来）；
2. **不许与 `pc_lua_enum_data` 的表名重叠**：重叠会在运行时互相覆盖，而且是**静默**的；
3. **本批真正要用的那几个值逐个钉死**（`RoomShape.ROOMSHAPE_LTL` 等）——
   它们是 GoodTrip 真机上读到的东西，文档漂了必须有人来解释；
4. **值用 64 位装**：`DamageFlag.DAMAGE_SPAWN_RUNE` 是 `1 << 32`，用 32 位会**静默回绕成 0**
   （与"假读数"同一类事故）。

（表"有没有真的注册进 Lua"这一半由 `test_lua_global_pc_enums.py` 的宿主 harness 端到端验证 ——
那里会真的起一个 Lua 状态机去读这些全局。）
"""

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
TOOL = ROOT / "tools" / "generate_doc_enum_tables.py"
GENERATED_HEADER = SOURCE / "program" / "doc_lua_enum_data.hpp"
GENERATED_IMPLEMENTATION = SOURCE / "program" / "doc_lua_enum_data.cpp"
FROZEN_IMPLEMENTATION = SOURCE / "program" / "pc_lua_enum_data.cpp"
RUNTIME = SOURCE / "lua_runtime.cpp"
CONTRACT_DOCS = ROOT / "tools" / "pc_enum_docs"

#: 本批发布的表（**只能多不能少地解释**：改这张清单要在此处写明原因）。
#:
#: 2026-09-20（批次 105）加 `CallbackPriority`：**又一条"模组读不到"的实例**，而且它是
#: GoodTrip 的**加载期**拦路虎 —— `main.lua:84` 起有 7 处
#: `_gt:AddPriorityCallback(…, CallbackPriority.EARLY, …)` **没被 pcall 包住**，
#: 这个全局是 nil 时整块 main.lua 就在第 84 行中止（后面所有回调都注册不上）。
#: 它同时是"优先级真排序"那条改动的**输入**：模组用 `CallbackPriority.EARLY/LATE` 表达顺序。
EXPECTED_TABLES = ("RoomShape", "DoorVariant", "Direction", "StageType", "DamageFlag",
                   "RoomDescriptor", "CallbackPriority", "ProjectileFlags", "EntityFlag",
                   # 批次 212（2026-09-30）：MCM 的声音路径要它 —— 缺表时
                   # `modconfig.lua:2950` 抛 `attempt to index a nil value (global 'SoundEffect')`
                   # ⇒ **整条回调**当场中断（不只是"没声音"）。
                   "SoundEffect",
                   # 批次 217（2026-09-30）：`SeedEffect` —— **第三次同形状**，这次卡的是中文版 MCM
                   # **"开菜单"本行**：`modconfig.lua:3616` 的
                   # `seeds:AddSeedEffect(SeedEffect.SEED_NO_HUD)`（`HideHudInMenu` 打开时必经）
                   # 抛 `attempt to index a nil value (global 'SeedEffect')`
                   # ⇒ 紧跟其后的 `ModConfigMenu.IsVisible = true` 永远执行不到
                   # ⇒ 症状是"按右摇杆菜单打不开"（真机读数 `dist/gdb-read-20260930-1411-…`）。
                   "SeedEffect",
                   # 批次 269（2026-10-02）：`RenderMode` —— **第四次同形状**，这次拦的是
                   # BOIStageAPI15 `scripts/stageapi/grid/customdoors.lua:415`
                   # （`== RenderMode.RENDER_NORMAL` 没被 pcall 包住）。
                   "RenderMode",
                   # 批次 292（2026-10-02）：`BackdropType` —— 与本批新落的
                   # `Room:GetBackdropType()` 是**同一件事的两半**（与 269 那批的
                   # `RenderMode` + `Room:GetRenderMode()` 逐字同形）：模组拿返回值
                   # **以枚举值为键**建表（`MusicModCallback/.../repentance.lua:431` 起
                   # `[BackdropType.BASEMENT] = Music.MUSIC_BASEMENT`），表是 nil 时那些键
                   # 全成 nil ⇒ 选曲**静默**错；`BOIStageAPI15` 的 `customFloorGen.lua:874`
                   # 也拿它与自定义楼层的 `Backdrop` 比。
                   "BackdropType",
                   # 批次 297（2026-10-03）：`GameStateFlag` / `LevelStateFlag` —— 与本批的
                   # `Game:GetStateFlag(int Flag)` / `Level:GetStateFlag(int Flag)` 是**同一件事
                   # 的两半**（第五次同形状）。模组**拿枚举常量当实参**：
                   # `ChallengeAPI/.../stage_transition.lua:34` 的
                   # `Game():SetStateFlag(GameStateFlag.STATE_BACKWARDS_PATH_INIT, true)`
                   # 与多处 `GetStateFlag(GameStateFlag.STATE_*)` / `GetStateFlag(LevelStateFlag.STATE_*)`
                   # （`MinimapAPI` 的小地图四条、`MusicModCallback`/`BOIStageAPI15` 等）
                   # ⇒ 表是 nil 时那一行直接抛错、整条回调被摘。
                   # ★ 两张表是**两个不同的枚举**（`GameStateFlag` 在 `Game` 上、
                   #   `LevelStateFlag` 在 `Level` 上），模组哪一边都可能用 ⇒ 都要发。
                   "GameStateFlag", "LevelStateFlag",
                   # 批次 301（2026-10-03）：`CacheFlag` —— 与本批新落的
                   # `EntityPlayer:AddCacheFlags(CacheFlag)` 是**同一件事的两半**
                   # （第六次同形状）。模组**拿枚举常量当实参**：
                   # `Trinity/main.lua:754` 的
                   # `player:AddCacheFlags(CacheFlag.CACHE_DAMAGE | CacheFlag.CACHE_FIREDELAY)`、
                   # `RepentancePlus/.../main.lua:758` 的 `CacheFlag.CACHE_LUCK`、
                   # `IsaacOnTwitchReloaded` 各脚本的 `CACHE_ALL` / `CACHE_SPEED` /
                   # `CACHE_FLYING`（`main.lua:700` 还把值存进自己的表
                   # `IOTR.Items.Passive[key].cacheFlag`）⇒ 表是 nil 时那一行直接抛错、
                   # 整条回调被摘（与 `RoomShape` 那次同一形状）。
                   # ★ 值与本批的 Switch 取证**逐位对上**（都打在 `Entity_Player+0x1958` 上）：
                   #   1<<0/1/2/3/4 = `EvaluateItems` 的 `tbnz #0/#1/#3/#4` + `tbz #0x2`、
                   #   1<<10 = `DonateLuck` 的 `orr #0x400`、1<<8 = `tbz #0x8`。
                   "CacheFlag")

#: 每张表的条目数（文档快照被改动时，这里会红 —— 那时要人工确认改了什么）。
EXPECTED_ENTRY_COUNTS = {
    "RoomShape": 13,
    "DoorVariant": 9,
    "Direction": 5,
    "StageType": 6,
    "DamageFlag": 33,
    "RoomDescriptor": 24,
    "CallbackPriority": 4,
    # 批次 207（2026-09-29）：两张**按位**表，成员全部来自文档页。
    "ProjectileFlags": 58,
    "EntityFlag": 62,
    # 批次 212：981 条（`SOUND_NULL`=0 … `SOUND_UNBORN_WARP`=1090，外加 `NUM_SOUND_EFFECTS`）。
    "SoundEffect": 981,
    # 批次 217：**71** 条（`SEED_NORMAL`=0 … `NUM_SEEDS`=80；值域里有 10 个空号 ⇒ 81-10 = 71）。
    # ★ 这一页**没有重复键**（`NUM_SEEDS` 只出现一次）⇒ 不需要进生成器的 `DUPLICATE_LAST_WINS`。
    "SeedEffect": 71,
    # 批次 269：**6** 条（`RENDER_NULL`=0 … `RENDER_WATER_REFLECT`=5；值域连续、无空号、
    # 也没有重复键）。
    "RenderMode": 6,
    # 批次 292：**64** 条（`BACKDROP_NULL`=0 … `LIL_PORTAL`=62 与 `NUM_BACKDROPS`=63）。
    # ★ 这一页**有重复键** `NUM_BACKDROPS`（`.abrep` 档 61 / `.repplus` 档 63）⇒ 已按规程
    #   登记进生成器的 `DUPLICATE_LAST_WINS`（与 `SoundEffect.NUM_SOUND_EFFECTS` 同口径：
    #   取最后一处 = 目标版本 Rep+ / 1.7.9b 的值 63）。
    "BackdropType": 64,
    # 批次 297：**55** 条（值 0..53；`NUM_STATE_FLAGS` 在页里出现两次 —— `.rep` 档 49 /
    # `.repplus` 档 53 —— 已按规程登记进 `DUPLICATE_LAST_WINS` 取 53；另有**同值两名**
    # `STATE_SISTERS_VIS_SELECTED` / `STATE_MAX_COINS_OBTAINED` 都 = 43，两者都保留）。
    "GameStateFlag": 55,
    # 批次 297：**25** 条（`STATE_BUM_KILLED`=0 … `STATE_MIRROR_BROKEN`=23 + `NUM_STATE_FLAGS`=24；
    # 值域连续、无空号、**没有重复键**）。
    "LevelStateFlag": 25,
    # 批次 301（2026-10-03）：**16** 条（`CACHE_DAMAGE`=1<<0 … `CACHE_PICKUP_VISION`=1<<13，
    # 外加 `CACHE_ALL`=(1<<16)-1 与 `CACHE_TWIN_SYNC`=1<<31）。
    # ★ 值域**有跳跃**（bit14/bit15 没有名字 —— 文档页里就没有），`CACHE_ALL` 是**求和式**
    #   （`(1 << 16) - 1`，生成器的表达式白名单支持括号与减法）；**没有重复键**。
    "CacheFlag": 16,
}

#: GoodTrip 在真机上真正读过的常量（值来自文档快照）。
EXPECTED_VALUES = {
    ("RoomShape", "ROOMSHAPE_LTL"): 9,
    ("RoomShape", "ROOMSHAPE_LTR"): 10,
    ("RoomShape", "ROOMSHAPE_LBL"): 11,
    ("RoomShape", "ROOMSHAPE_LBR"): 12,
    ("RoomShape", "ROOMSHAPE_IIH"): 7,
    # 批次 297（2026-10-03）：**本批的取证直接依赖这几个值** —— 它们的"值 → Switch 位点位"
    # 对应关系写在 `runtime_constants.hpp` 的批次 297 段（`Level::IsBackwardsPath` /
    # `Level::CanSpawnDevilRoom` / `SetRedHeartDamage` / `ApplyCompassEffect`）。
    # 上游文档若改了这些值，本批的基址结论就必须重做 ⇒ 钉在这里让门禁先红。
    ("GameStateFlag", "STATE_BACKWARDS_PATH"): 48,
    ("GameStateFlag", "STATE_BACKWARDS_PATH_INIT"): 47,
    ("GameStateFlag", "NUM_STATE_FLAGS"): 53,
    ("LevelStateFlag", "STATE_REDHEART_DAMAGED"): 2,
    ("LevelStateFlag", "STATE_COMPASS_EFFECT"): 7,
    ("LevelStateFlag", "NUM_STATE_FLAGS"): 24,
    ("DoorVariant", "DOOR_HIDDEN"): 7,
    ("Direction", "NO_DIRECTION"): -1,
    ("StageType", "STAGETYPE_REPENTANCE"): 4,
    ("RoomDescriptor", "FLAG_RED_ROOM"): 1024,
    # 批次 105：优先级的四个值。**数值大小就是执行顺序**（越小越早），
    # 所以这四个值必须与文档逐字一致 —— 写错会让模组以为自己是 EARLY 而实际排在最后。
    ("CallbackPriority", "IMPORTANT"): -200,
    ("CallbackPriority", "EARLY"): -100,
    ("CallbackPriority", "DEFAULT"): 0,
    ("CallbackPriority", "LATE"): 100,
    # 批次 207：MCM 真正读过的两个常量。
    #   * `ProjectileFlags.CANT_HIT_PLAYER` —— 与引擎 `.data` 里的
    #     `Entity_Projectile::CANT_HIT_PLAYER = 0x80000000` **逐位吻合**，
    #     也是我们 `Entity_Projectile::CanShutDoors()` 反汇编读 `+0x428` 后取 bit31 的那一位
    #     （见 `runtime_constants.hpp` 的 `kEntityProjectileFlagsOffset`）；
    #   * `EntityFlag.FLAG_NO_QUERY` —— bit46，`Entity:HasEntityFlags` 的实参来源。
    ("ProjectileFlags", "CANT_HIT_PLAYER"): 1 << 31,
    ("EntityFlag", "FLAG_NO_QUERY"): 1 << 46,
    # 批次 212：MCM 真正用到的那个声音常量（`modconfig.lua:2950`），以及**那个重复键的裁决**：
    # 文档里 `NUM_SOUND_EFFECTS` 每个 DLC 档各一行（`.rep` = 833、`.repplus` = 1091），
    # 生成器按登记在案的规则取**最后一处** = 1091（目标版本 Rep+ / 1.7.9b）。
    ("SoundEffect", "SOUND_BOSS2INTRO_ERRORBUZZ"): 187,
    ("SoundEffect", "NUM_SOUND_EFFECTS"): 1091,
    # ★ 中文版 MCM 走的就是这一个：`SeedEffect.SEED_NO_HUD` 必须是 10（用错了就静默按别的效果走）。
    ("SeedEffect", "SEED_NO_HUD"): 10,
    ("SeedEffect", "SEED_NORMAL"): 0,
    ("SeedEffect", "NUM_SEEDS"): 80,
    # 批次 269：`Room:GetRenderMode()` 给的那个常量必须与这张表**同值** ——
    # 它们是"同一件事的两半"（模组写 `GetRenderMode() == RenderMode.RENDER_NORMAL`），
    # 两边错开就会变成"永远不相等"这种最隐蔽的失效。
    ("RenderMode", "RENDER_NORMAL"): 1,
    ("RenderMode", "RENDER_NULL"): 0,
    ("RenderMode", "RENDER_WATER_REFLECT"): 5,
    # 批次 292：三个**有独立锚点**的值。
    #   * `MINES = 32` —— 与 Switch 侧**同值对照**：`Room::pre_render_pits @ 0x47F03C` 读
    #     `Room+0x21B0`（本批新做的那个字段）后 `cmp w8,#0x20` ⇒ "这是矿层"，
    #     之后才看 `Flags` bit5 决定画不画水坑 ⇒ 引擎里的 0x20 就是这张表的 32。
    #     ★ 这一条同时是"`Room:GetBackdropType()` 的返回值能直接与 `BackdropType.*` 比"
    #     的判据（两边错开就会变成"永远不相等"这种最隐蔽的失效）。
    #   * `BASEMENT = 1` / `NUM_BACKDROPS = 63`（后者是重复键的裁决结果）。
    ("BackdropType", "MINES"): 32,
    ("BackdropType", "BASEMENT"): 1,
    ("BackdropType", "NUM_BACKDROPS"): 63,
    # 批次 301（2026-10-03）：**本批的取证直接依赖这几个位** —— 它们的"值 → Switch 位号"
    # 对应关系写在 `runtime_constants.hpp` 的批次 301 段（`Entity_Player::EvaluateItems`
    # 里 `tbnz w8,#0/#1/#3/#4` + `tbz w8,#0x2`/`#0x8`，以及 `DonateLuck` 的 `orr #0x400`）。
    # 上游文档若改了这些值，本批的位号结论（以及 `CacheFlag` 表本身）就必须重做 ⇒ 钉在这里。
    ("CacheFlag", "CACHE_DAMAGE"): 1 << 0,
    ("CacheFlag", "CACHE_FIREDELAY"): 1 << 1,
    ("CacheFlag", "CACHE_SHOTSPEED"): 1 << 2,
    ("CacheFlag", "CACHE_RANGE"): 1 << 3,
    ("CacheFlag", "CACHE_SPEED"): 1 << 4,
    ("CacheFlag", "CACHE_WEAPON"): 1 << 8,
    ("CacheFlag", "CACHE_LUCK"): 1 << 10,
    ("CacheFlag", "CACHE_ALL"): (1 << 16) - 1,
    ("CacheFlag", "CACHE_TWIN_SYNC"): 1 << 31,
}

#: 超出 32 位的那些：一旦有人把生成器的值类型改回 32 位，这几条会立刻红。
WIDE_VALUES = {
    ("DamageFlag", "DAMAGE_CURSED_DOOR"): 1 << 16,
    ("DamageFlag", "DAMAGE_NO_PENALTIES"): 1 << 28,
    ("DamageFlag", "DAMAGE_SPAWN_RUNE"): 1 << 32,
    # 批次 207：这两张表把"必须 64 位"这件事推得更远 —— `ProjectileFlags` 到 `1 << 57`、
    # `EntityFlag` 到 `1 << 59`，32 位容器会直接变成 0。
    ("ProjectileFlags", "CHANGE_VELOCITY_AFTER_TIMEOUT"): 1 << 33,
    ("EntityFlag", "FLAG_NO_QUERY"): 1 << 46,
}


def load_tool():
    spec = importlib.util.spec_from_file_location("generate_doc_enum_tables", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_generated(text: str) -> dict[str, dict[str, int]]:
    """把生成物解析成 `{表名: {常量名: 值}}`。

    不 import 生成的 C++，只按它的固定文本形状读 —— 这样连"值类型被改成 int32"
    都能通过 `4294967296` 变成 `0` 暴露出来（真出事时就是那个样子）。
    """
    tables: dict[str, dict[str, int]] = {}
    for match in re.finditer(r'constexpr Value (k\w+Values)\[\] = \{(.*?)\};', text, re.S):
        symbol, body = match.group(1), match.group(2)
        tables[symbol] = dict(
            (key, int(value))
            for key, value in re.findall(r'\{"([A-Za-z_][A-Za-z0-9_]*)",\s*(-?\d+)\}', body)
        )
    registered = dict(re.findall(r'\{"([A-Za-z_][A-Za-z0-9_]*)",\s*(k\w+Values),', text))
    return {name: tables[symbol] for name, symbol in registered.items() if symbol in tables}


class DocEnumTableGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generated_text = GENERATED_IMPLEMENTATION.read_text(encoding="utf-8")
        cls.tables = parse_generated(cls.generated_text)

    def test_generated_files_match_the_docs_snapshot(self):
        """生成物必须与文档快照逐字节一致：不一致说明有人改了文档没重新生成。"""
        result = subprocess.run([sys.executable, str(TOOL), "--check"],
                                capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0,
                         "生成物与 PC 文档快照不一致：\n" + result.stdout + result.stderr)
        self.assertIn("文档枚举表与生成物一致", result.stdout)

    def test_the_published_tables_are_the_expected_ones(self):
        self.assertEqual(tuple(self.tables.keys()), EXPECTED_TABLES,
                         "发布的表清单变了 —— 改这里要写明原因（新表要连值一起钉）")
        counted = {name: len(values) for name, values in self.tables.items()}
        self.assertEqual(counted, EXPECTED_ENTRY_COUNTS,
                         "条目数变了：文档快照被更新过，先确认改了什么再改这里")

    def test_tables_do_not_overlap_the_frozen_generated_ones(self):
        """与 `pc_lua_enum_data` 的表名**不许重叠** —— 重叠会互相覆盖，而且不报错。"""
        frozen = set(re.findall(r'\{"([A-Za-z_][A-Za-z0-9_]*)",\s*k',
                                FROZEN_IMPLEMENTATION.read_text(encoding="utf-8")))
        overlap = sorted(frozen & set(self.tables))
        self.assertEqual(overlap, [],
                         f"这些表同时在两个生成物里，注册顺序会决定谁赢：{overlap}")
        self.assertGreater(len(frozen), 0, "解析 pc_lua_enum_data 的表名失败了（格式变了？）")

    def test_values_goodtrip_reads_are_pinned(self):
        """真机读过的值逐个钉死（`RoomShape.ROOMSHAPE_LTL` = 9 等）。"""
        for (table, key), expected in EXPECTED_VALUES.items():
            with self.subTest(f"{table}.{key}"):
                self.assertIn(table, self.tables, f"生成物里没有 {table}")
                self.assertEqual(self.tables[table].get(key), expected)

    def test_wide_values_are_stored_beyond_32_bits(self):
        """`1 << 32` 必须原样存下来 —— 32 位会静默回绕成 0（假读数）。"""
        for (table, key), expected in WIDE_VALUES.items():
            with self.subTest(f"{table}.{key}"):
                self.assertEqual(self.tables[table].get(key), expected)
        self.assertEqual(self.tables["DamageFlag"]["DAMAGE_SPAWN_RUNE"], 4294967296)
        self.assertIn("std::int64_t value;", GENERATED_HEADER.read_text(encoding="utf-8"),
                      "值类型必须是 64 位")

    def test_runtime_registers_the_doc_tables(self):
        """运行时要真的把这张表挂上去（端到端由宿主 harness 验，这里钉住接线）。"""
        text = RUNTIME.read_text(encoding="utf-8")
        self.assertIn('#include "program/doc_lua_enum_data.cpp"', text)
        self.assertIn("DocLuaEnumData::Tables(&docCount)", text)
        self.assertIn("lua_setglobal(state, docTables[tableIndex].name);", text)

    def test_generator_fails_loudly_on_shapes_it_cannot_read(self):
        """读不懂的形状必须**响亮失败** —— 静默跳过等于让模组拿到 nil。"""
        tool = load_tool()
        with self.assertRaises(tool.DocEnumError):
            tool._evaluate_expression("TEARFLAG(1)", "Table", "KEY")
        with self.assertRaises(tool.DocEnumError):
            tool._evaluate_expression("", "Table", "KEY")
        with self.assertRaises(tool.DocEnumError):
            tool._evaluate_expression("1 << 3 4", "Table", "KEY")
        # 白名单里的形状照旧能算（含负数与左移）。
        self.assertEqual(tool._evaluate_expression("1 << 32", "Table", "KEY"), 4294967296)
        self.assertEqual(tool._evaluate_expression("-1", "Table", "KEY"), -1)
        self.assertEqual(tool._evaluate_expression("0x800", "Table", "KEY"), 2048)

    def test_every_declared_table_has_a_doc_page(self):
        tool = load_tool()
        for name in tool.TABLES:
            with self.subTest(name):
                self.assertTrue((CONTRACT_DOCS / f"{name}.md").is_file(),
                                f"契约快照里没有 {name}.md")
        self.assertEqual(tuple(tool.TABLES), EXPECTED_TABLES)
        self.assertEqual(tool.DOC_DIR, CONTRACT_DOCS,
                         "生成器读的目录必须是进门禁的契约快照 —— 读 analysis/ 那种被 gitignore 的"
                         "目录会让干净检出里根本没有输入")

    def test_the_contract_snapshot_is_really_tracked(self):
        """契约快照必须**进仓库**：被 gitignore 的输入等于"这类工作对别人不可做"。

        2026-09-19 的第一版就踩了这个坑：直接读 `analysis/isaacdocs-snapshot/`，
        而 `analysis/` 是 gitignore 的 ⇒ 门禁里那个"只用 `git ls-files` 复制被跟踪文件"的
        用例一跑就红（那里没有这些页）。
        """
        ignored = subprocess.run(["git", "-C", str(ROOT), "check-ignore", str(CONTRACT_DOCS)],
                                 capture_output=True, text=True)
        self.assertNotEqual(ignored.returncode, 0,
                            f"契约快照目录被 git 忽略了：{ignored.stdout.strip()}")
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "tools/pc_enum_docs"],
                                 capture_output=True, text=True)
        # 新加的文件在 `git add` 之前还没被跟踪 —— 那种情况只要求"没被忽略"。
        if tracked.stdout.strip():
            self.assertIn("RoomShape.md", tracked.stdout)

    def test_contract_snapshot_bytes_are_pinned(self):
        """契约页的字节被钉死：生成物头部的 sha256 依赖它们，改了必须有人来解释。"""
        expected = {
            "RoomShape.md": 1590,
            "DoorVariant.md": 778,
            "Direction.md": 418,
            "StageType.md": 724,
            "DamageFlag.md": 4607,
            "RoomDescriptor.md": 3487,
            "CallbackPriority.md": 380,
            # 批次 207（2026-09-29）：MCM 的两张按位表。
            "ProjectileFlags.md": 5761,
            "EntityFlag.md": 9093,
            # 批次 292（2026-10-02）：`BackdropType`（与 `Room:GetBackdropType()` 同一批）。
            "BackdropType.md": 4828,
            # 批次 297（2026-10-03）：两张状态标志表（与 `GetStateFlag` 同一批）。
            "GameStateFlag.md": 6321,
            "LevelStateFlag.md": 2304,
            # 批次 301（2026-10-03）：`CacheFlag`（与 `AddCacheFlags` 同一批）。
            "CacheFlag.md": 1582,
        }
        for name, size in expected.items():
            with self.subTest(name):
                path = CONTRACT_DOCS / name
                self.assertTrue(path.is_file(), f"缺契约页 {name}")
                self.assertEqual(path.stat().st_size, size,
                                 f"{name} 的字节数变了 —— 契约页被改动过，先核对上游再改这里")
        self.assertTrue((CONTRACT_DOCS / ".gitattributes").is_file(),
                        "契约页目录要有 `.gitattributes`（`-text`）：生成物头部写着它们的 sha256，"
                        "行尾被规范化就会对不上")


if __name__ == "__main__":
    unittest.main()
