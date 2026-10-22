import ast
import subprocess
import tempfile
import unittest
import hashlib
import re
from pathlib import Path

try:
    from .test_support import layered_lua_runtime_sources
except ImportError:
    from test_support import layered_lua_runtime_sources


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

#: 生成器读的**用户提供的** PC 游戏源码。它不在仓库里（PC 游戏本体），所以两条需要它的用例
#: 在缺这份夹具时按仓库惯例**跳过**而不是报错 —— 生成物本身（`pc_lua_enum_data.*`）与
#: 它记录的 SHA-256 仍在仓库里，装了夹具的机器上照旧逐字节核对。
#:
#: ★ 2026-10-07（批次 398）：**改成按候选路径找** —— 本机把 PC 源码放在
#: `The Binding of Isaac Rebirth/resources/scripts/enums.lua`（SHA-256 `dce1892f…`，与生成物里
#: 记的那份**逐字节同一份**），而这里原来只认 `The Binding of Isaac Rebirth pc/…` ⇒ 那两条
#: **最强的检查（逐字节核对 + 逐值解析）在本机一直是 skipped**。
#: ⇒ 现在是"找得到就跑、找不到才跳"，**没有放宽任何判据**。
PC_ENUMS_SOURCE_CANDIDATES = (
    ROOT / "The Binding of Isaac Rebirth pc" / "resources/scripts/enums.lua",
    ROOT / "The Binding of Isaac Rebirth" / "resources/scripts/enums.lua",
)


def _resolve_pc_enums_source() -> Path:
    for candidate in PC_ENUMS_SOURCE_CANDIDATES:
        if candidate.is_file():
            return candidate
    return PC_ENUMS_SOURCE_CANDIDATES[0]


PC_ENUMS_SOURCE = _resolve_pc_enums_source()


def skip_without_pc_enums(test: unittest.TestCase, source: Path) -> None:
    if not source.is_file():
        test.skipTest(f"缺少用户提供的 PC 源码夹具：{source}")


# The fixed PC contract: these globals must exist in Lua, in this order, and
# `ModCallbacks` is registered last.
GENERATED_TABLES = (
    "CollectibleType",
    "ItemPoolType",
    "RoomType",
    "LevelStage",
    "PickupVariant",
    "ItemType",
    "PlayerForm",
    "PlayerType",
    "PillColor",
    "PillEffect",
    "EntityType",
    "UseFlag",
    "TrinketType",
    "Challenge",
    "LevelCurse",
    "GridEntityType",
    "EffectVariant",
    "EntityPartition",
    "Card",
    # ---- 2026-10-07 批次 398：从 20 张补到 61 张 ----
    # 真机实测挖出的缺口（`ActiveSlot` 缺 ⇒ `ActiveSlot.SLOT_PRIMARY` 是 nil global ⇒ 模组抛错
    # ⇒ 整条回调登记被摘；`Music` 缺 ⇒ 音乐模组加载期就炸）。做法 = 把 PC `enums.lua`（SHA-256
    # `dce1892f…`）的 78 张顶层表对本一遍、减去走文档生成器的那 17 张。
    # ⚠️ `TearFlags` 仍不在（值全是 `BitSet128`，本生成器装 int32）——见生成器 `TABLES` 的注释。
    "ActionTriggers",
    "ActiveSlot",
    "BabySubType",
    "BatterySubType",
    "BedSubType",
    "BombSubType",
    "BombVariant",
    "ChampionColor",
    "ChestSubType",
    "CoinSubType",
    "Difficulty",
    "DoorSlot",
    "DoorState",
    "EntityCollisionClass",
    "EntityGridCollisionClass",
    "FamiliarVariant",
    "GridCollisionClass",
    "GridRooms",
    "HeartSubType",
    "InputHook",
    "KeySubType",
    "Keyboard",
    "LaserOffset",
    "LaserSubType",
    "LaserVariant",
    "LocustSubtypes",
    "Mouse",
    "Music",
    "NpcState",
    "NullItemID",
    "PickupPrice",
    "PlayerSpriteLayer",
    "PoopPickupSubType",
    "PoopSpellType",
    "ProjectileVariant",
    "RoomTransitionAnim",
    "SackSubType",
    "SkinColor",
    "SortingLayer",
    "TearVariant",
    "WeaponType",
    "ModCallbacks",
)

# Entry counts pinned to the enums.lua revision identified by the SHA-256 that
# the generator writes into both products.
EXPECTED_ENTRY_COUNTS = {
    "CollectibleType": 753,
    "ItemPoolType": 40,
    "RoomType": 31,
    "LevelStage": 23,
    "PickupVariant": 30,
    "ItemType": 5,
    "PlayerForm": 16,
    "PlayerType": 47,
    "PillColor": 19,
    "PillEffect": 52,
    "EntityType": 344,
    "UseFlag": 12,
    "TrinketType": 195,
    "Challenge": 47,
    "LevelCurse": 10,
    "GridEntityType": 28,
    "EffectVariant": 200,
    "EntityPartition": 7,
    "Card": 100,
    # ---- 2026-10-07 批次 398 新增的 41 张 ----
    "ActionTriggers": 7,
    "ActiveSlot": 4,
    "BabySubType": 73,
    "BatterySubType": 4,
    "BedSubType": 2,
    "BombSubType": 7,
    "BombVariant": 21,
    "ChampionColor": 26,
    "ChestSubType": 2,
    "CoinSubType": 7,
    "Difficulty": 4,
    "DoorSlot": 10,
    "DoorState": 5,
    "EntityCollisionClass": 5,
    "EntityGridCollisionClass": 8,
    "FamiliarVariant": 165,
    "GridCollisionClass": 6,
    "GridRooms": 24,
    "HeartSubType": 12,
    "InputHook": 3,
    "KeySubType": 4,
    "Keyboard": 120,
    "LaserOffset": 7,
    "LaserSubType": 5,
    "LaserVariant": 16,
    "LocustSubtypes": 5,
    "Mouse": 12,
    "Music": 99,
    "NpcState": 19,
    "NullItemID": 134,
    "PickupPrice": 10,
    "PlayerSpriteLayer": 16,
    "PoopPickupSubType": 2,
    "PoopSpellType": 15,
    "ProjectileVariant": 17,
    "RoomTransitionAnim": 21,
    "SackSubType": 2,
    "SkinColor": 8,
    "SortingLayer": 3,
    "TearVariant": 51,
    "WeaponType": 16,
    "ModCallbacks": 74,
}

# ModCallbacks values the Runtime must publish for mod registration to work.
EXPECTED_MOD_CALLBACKS = {
    "MC_POST_UPDATE": 1,
    "MC_POST_RENDER": 2,
    "MC_INPUT_ACTION": 13,
    "MC_PRE_GET_COLLECTIBLE": 62,
    "MC_POST_GET_COLLECTIBLE": 63,
    "MC_USE_CARD": 5,
    "MC_PRE_USE_ITEM": 23,
    "MC_POST_NEW_ROOM": 19,
    "MC_POST_GAME_STARTED": 15,
    "MC_POST_PICKUP_INIT": 34,
    "MC_POST_PICKUP_UPDATE": 35,
    "MC_PRE_ROOM_ENTITY_SPAWN": 71,
    "MC_PRE_PICKUP_COLLISION": 38,
    "MC_PRE_GAME_EXIT": 17,
    "MC_POST_NEW_LEVEL": 18,
    "MC_POST_PLAYER_INIT": 9,
}

K_TABLE_ENTRY = re.compile(
    r'\{"([A-Za-z0-9_]+)", k([A-Za-z0-9_]+)Values, '
    r'sizeof\(k\2Values\) / sizeof\(k\2Values\[0\]\)\},'
)
K_VALUE_ENTRY = re.compile(r'^\s*\{"([A-Z0-9_]+)", -?\d+\},$', re.MULTILINE)


def lua_table_literal(mapping):
    return "{" + ", ".join(f'["{key}"] = {value}' for key, value in mapping.items()) + "}"


def load_generator():
    """The generator module itself, loaded by path (it is a script, not a package)."""
    import importlib.util

    path = ROOT / "tools" / "generate_pc_lua_enum_tables.py"
    spec = importlib.util.spec_from_file_location("generate_pc_lua_enum_tables", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def registered_tables(implementation):
    """Ordered (global name, value-array symbol) pairs from the generated kTables."""
    return K_TABLE_ENTRY.findall(implementation)


def generated_keys(implementation, symbol):
    """Keys of one generated value array, in generated (sorted) order."""
    match = re.search(
        rf"constexpr Value k{symbol}Values\[\] = \{{(.*?)\n\}};", implementation, re.DOTALL
    )
    if match is None:
        return None
    return K_VALUE_ENTRY.findall(match.group(1))


class LuaGlobalPcEnumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-global-enums-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        harness = temporary / "lua_global_enums_harness.cpp"
        harness.write_text(
            r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include "game_observer.hpp"

#include <cstring>

GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {
    return GameIsPausedObservation::ThunkUnavailable;
}
GameLevelStageObservation ReadCurrentGameLevelStage(uintptr_t, std::uint32_t*) {
    return GameLevelStageObservation::GameUnreadable;
}
GameIsGreedModeObservation ObserveGameIsGreedMode(uintptr_t, uintptr_t) {
    return GameIsGreedModeObservation::MethodUnavailable;
}
GameIsAscentObservation ObserveLevelIsAscent(uintptr_t, uintptr_t) {
    return GameIsAscentObservation::MethodUnavailable;
}
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {
    return GameItemPoolObservation::GameUnreadable;
}
GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {
    return GameRoomObservation::RoomUnreadable;
}
GameRoomObservation ReadCurrentGameRoomType(uintptr_t, std::uint32_t*) {
    return GameRoomObservation::RoomUnreadable;
}
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&, const char*, u8*, std::size_t, std::size_t*) {
    return TextReadResult::OpenFailed;
}
}

int main() {
    const char* script = R"lua(
local function CheckGlobalPcEnumTables()
local expectedCounts = __EXPECTED_COUNTS__
local expectedModCallbacks = __EXPECTED_MOD_CALLBACKS__
local missing = {}
for name, count in pairs(expectedCounts) do
    local published = _G[name]
    if type(published) ~= 'table' then
        missing[#missing + 1] = name
    else
        local actual = 0
        for _ in pairs(published) do actual = actual + 1 end
        if actual ~= count then
            error(name .. ' entry count ' .. actual .. ' ~= ' .. count)
        end
    end
end
if #missing > 0 then error('missing global tables: ' .. table.concat(missing, ',')) end
for name, value in pairs(expectedModCallbacks) do
    if ModCallbacks[name] ~= value then
        error('ModCallbacks.' .. name .. ' = ' .. tostring(ModCallbacks[name]) .. ' ~= ' .. value)
    end
end
if CollectibleType.COLLECTIBLE_DEATH_CERTIFICATE ~= 628 then error('collectible enum') end
if CollectibleType.NUM_COLLECTIBLES ~= 733 then error('collectible count') end
if ItemPoolType.POOL_ULTRA_SECRET ~= 24 then error('item pool enum') end
if RoomType.ROOM_ULTRASECRET ~= 29 then error('room enum') end
if LevelStage.STAGE8 ~= 13 then error('level enum') end
if PickupVariant.PICKUP_COLLECTIBLE ~= 100 then error('pickup variant enum') end
if ItemType.ITEM_ACTIVE ~= 3 then error('item type enum') end
if PlayerForm.PLAYERFORM_GUPPY ~= 0 then error('player form enum') end
if PlayerType.PLAYER_ISAAC ~= 0 then error('player type enum') end
if PillColor.PILL_NULL ~= 0 then error('pill color enum') end
if PillEffect.PILLEFFECT_BAD_GAS ~= 0 then error('pill effect enum') end
if EntityType.ENTITY_PLAYER ~= 1 then error('entity type enum') end
if UseFlag.USE_OWNED ~= 4 then error('use flag enum') end
if TrinketType.TRINKET_NULL ~= 0 then error('trinket enum') end
if Challenge.CHALLENGE_NULL ~= 0 then error('challenge enum') end
if LevelCurse.CURSE_OF_THE_UNKNOWN ~= 8 then error('curse enum') end
if GridEntityType.GRID_ROCK ~= 2 then error('grid entity enum') end
if EffectVariant.EFFECT_NULL ~= 0 then error('effect variant enum') end
if EntityPartition.PLAYER ~= 32 then error('entity partition enum') end
if Card.CARD_FOOL ~= 1 then error('card enum') end
-- 批次 048：由**仓库自带的 PC 文档快照**生成的那几张表（`pc_lua_enum_data` 之外的补充，
-- 见 `tools/generate_doc_enum_tables.py`）。真机事故：GoodTrip 的 `widget.lua:185` 读
-- `RoomShape.ROOMSHAPE_LTL`，我们没发这张表 ⇒ `attempt to index a nil value (global 'RoomShape')`
-- ⇒ 整条绘制回调在小地图画出来之前被打断（用户只看到"按地图键没反应"）。
for _, name in ipairs({'RoomShape', 'DoorVariant', 'Direction', 'StageType', 'DamageFlag',
                       'RoomDescriptor'}) do
    if _G[name] == nil then error('missing PC enum table: ' .. name) end
end
-- 批次 207（2026-09-29）：MCM 读的两张**按位**表（`ProjectileFlags` / `EntityFlag`）。
-- 缺表时模组拿到 nil 再按位与 ⇒ 整条回调报错被摘（与 RoomShape 那次同一形状）。
for _, name in ipairs({'ProjectileFlags', 'EntityFlag'}) do
    if _G[name] == nil then error('missing PC enum table: ' .. name) end
end
-- 批次 212（2026-09-30）：`SoundEffect` —— MCM 的声音路径（`modconfig.lua:2950`
-- `sfx:Play(SoundEffect.SOUND_BOSS2INTRO_ERRORBUZZ, …)`）。缺表时抛"index a nil value" ⇒
-- **整条回调**中断（不只是没声音）。真机读数 `dist/gdb-read-20260930-005757.txt` 里抓到的第 2 条。
if SoundEffect.SOUND_BOSS2INTRO_ERRORBUZZ ~= 187 then error('SoundEffect.SOUND_BOSS2INTRO_ERRORBUZZ') end
if SoundEffect.SOUND_NULL ~= 0 or SoundEffect.SOUND_1UP ~= 1 then error('SoundEffect 0/1') end
-- `NUM_SOUND_EFFECTS` 在文档里**每个 DLC 档各一行**（`.rep` = 833、`.repplus` = 1091）：
-- 生成器按登记在案的规则取最后一处 ⇒ 1091（目标版本 Rep+ / 1.7.9b）。
if SoundEffect.NUM_SOUND_EFFECTS ~= 1091 then error('SoundEffect.NUM_SOUND_EFFECTS') end
-- 批次 217（2026-09-30）：`SeedEffect` —— **中文版 MCM 的"开菜单"本行**：
-- `modconfig.lua:3616` 在"显示菜单"那段里 `seeds:AddSeedEffect(SeedEffect.SEED_NO_HUD)`
-- （`HideHudInMenu` 打开时必经）⇒ 缺表时紧跟其后的 `ModConfigMenu.IsVisible = true`
-- **永远执行不到** ⇒ 症状是"按右摇杆菜单打不开"。真机读数 `dist/gdb-read-20260930-1411-cn-menu-broken.txt`。
if SeedEffect.SEED_NO_HUD ~= 10 then error('SeedEffect.SEED_NO_HUD must be 10') end
if SeedEffect.SEED_NORMAL ~= 0 then error('SeedEffect.SEED_NORMAL must be 0') end
if SeedEffect.NUM_SEEDS ~= 80 then error('SeedEffect.NUM_SEEDS must be 80') end
-- `CANT_HIT_PLAYER` 是 bit31 —— 与引擎 `.data` 里的 `Entity_Projectile::CANT_HIT_PLAYER = 0x80000000`
-- 逐位吻合，也是我们读 `Entity_Projectile + 0x428` 后取的那一位。
if ProjectileFlags.CANT_HIT_PLAYER ~= 2147483648 then error('ProjectileFlags.CANT_HIT_PLAYER') end
if ProjectileFlags.SMART ~= 1 or ProjectileFlags.CONTINUUM ~= 1073741824 then
    error('ProjectileFlags.SMART/CONTINUUM')
end
-- `FLAG_NO_QUERY` 是 bit46（1 << 46 = 70368744177664）：**超出 32 位**，32 位装会静默变 0。
if EntityFlag.FLAG_NO_QUERY ~= 70368744177664 then error('EntityFlag.FLAG_NO_QUERY (1<<46)') end
if EntityFlag.FLAG_NO_STATUS_EFFECTS ~= 1 then error('EntityFlag.FLAG_NO_STATUS_EFFECTS') end
if RoomShape.ROOMSHAPE_1x1 ~= 1 or RoomShape.ROOMSHAPE_LTL ~= 9 then error('RoomShape 1x1/LTL') end
if RoomShape.ROOMSHAPE_IIH ~= 7 or RoomShape.ROOMSHAPE_LBR ~= 12 then error('RoomShape IIH/LBR') end
if DoorVariant.DOOR_HIDDEN ~= 7 or DoorVariant.DOOR_UNSPECIFIED ~= 0 then error('DoorVariant') end
-- `NO_DIRECTION` 是负数：寄存器里按有符号存/取，压成无符号会变成 4294967295。
if Direction.NO_DIRECTION ~= -1 or Direction.LEFT ~= 0 then error('Direction') end
if StageType.STAGETYPE_REPENTANCE ~= 4 then error('StageType') end
-- `DamageFlag` 里有 `1 << 32`：用 32 位装会**静默回绕成 0**（假读数）。这条钉的就是它。
if DamageFlag.DAMAGE_CURSED_DOOR ~= 65536 then error('DamageFlag.DAMAGE_CURSED_DOOR') end
if DamageFlag.DAMAGE_NO_PENALTIES ~= 268435456 then error('DamageFlag.DAMAGE_NO_PENALTIES') end
if DamageFlag.DAMAGE_SPAWN_RUNE ~= 4294967296 then error('DamageFlag.DAMAGE_SPAWN_RUNE (1<<32)') end
-- `RoomDescriptor` 页上有两张表格（`DISPLAY_*` 与 `FLAG_*`），PC 把它们都挂在同一个全局下。
if RoomDescriptor.FLAG_RED_ROOM ~= 1024 then error('RoomDescriptor.FLAG_RED_ROOM') end
if RoomDescriptor.DISPLAY_ALL ~= 4 then error('RoomDescriptor.DISPLAY_ALL') end
-- Bit-flag tables: `enums.lua` writes every one of these as a shift expression
-- (`1<<5`, `1 << 5`), and the generator used to truncate each one to its leading
-- `1`. Every member is pinned here so that regression cannot come back silently.
local entityPartition = {
    ['FAMILIAR'] = 1, ['BULLET'] = 2, ['TEAR'] = 4, ['ENEMY'] = 8,
    ['PICKUP'] = 16, ['PLAYER'] = 32, ['EFFECT'] = 64,
}
local partitionCount = 0
for name, value in pairs(entityPartition) do
    partitionCount = partitionCount + 1
    if EntityPartition[name] ~= value then
        error('EntityPartition.' .. name .. ' = ' .. tostring(EntityPartition[name]) ..
              ' ~= ' .. value)
    end
end
for name, _ in pairs(EntityPartition) do
    if entityPartition[name] == nil then error('unexpected EntityPartition.' .. name) end
end
if partitionCount ~= 7 then error('EntityPartition member count') end
-- EID 的 `searchPartitions`（`main.lua:1304`）就是这四个分区的和；它曾经算成 4
-- （等于 TEAR），正确的掩码是 57。
if EntityPartition.FAMILIAR + EntityPartition.ENEMY + EntityPartition.PICKUP +
   EntityPartition.PLAYER ~= 57 then
    error('EID searchPartitions mask')
end
if UseFlag.USE_NOANIM ~= 1 or UseFlag.USE_NOHUD ~= 2048 then error('UseFlag bits') end
if LevelCurse.CURSE_OF_DARKNESS ~= 1 or LevelCurse.CURSE_OF_GIANT ~= 128 then
    error('LevelCurse bits')
end
-- 十六进制字面量同样曾经被截断成 0（`0x800` → `0`）。
if PillColor.PILL_GIANT_FLAG ~= 2048 or PillColor.PILL_COLOR_MASK ~= 2047 then
    error('PillColor hex bits')
end
if TrinketType.TRINKET_GOLDEN_FLAG ~= 32768 or TrinketType.TRINKET_ID_MASK ~= 32767 then
    error('TrinketType hex bits')
end
local mod = RegisterMod('Global enum probe', 1)
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function() end)
end
-- The runtime returns a bare failure code, so report which check failed on
-- stdout before failing; the test surfaces that text in its own message.
local ok, failure = pcall(CheckGlobalPcEnumTables)
if not ok then
    print('global PC enum contract check failed: ' .. tostring(failure))
    error(failure)
end
)lua";
    return LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@global-enums.lua") ==
        LuaRuntime::LuaInitResult::Success ? 0 : 1;
}
'''.lstrip()
            .replace("__EXPECTED_COUNTS__", lua_table_literal(EXPECTED_ENTRY_COUNTS))
            .replace("__EXPECTED_MOD_CALLBACKS__", lua_table_literal(EXPECTED_MOD_CALLBACKS))
        )
        lua_root = SOURCE / "third_party/lua-5.3.3/src"
        excluded = {"lua.c", "luac.c", "liolib.c", "loslib.c", "loadlib.c", "ldblib.c", "linit.c"}
        lua_objects = []
        for lua_source in sorted(lua_root.glob("*.c")):
            if lua_source.name in excluded:
                continue
            output = temporary / f"{lua_source.stem}.o"
            build = subprocess.run(
                ["cc", "-std=c99", "-w", "-DLUA_C89_NUMBERS", "-I", str(lua_root), "-c",
                 str(lua_source), "-o", str(output)], text=True, capture_output=True,
            )
            if build.returncode != 0:
                raise AssertionError(build.stdout + build.stderr)
            lua_objects.append(output)
        cls.harness = temporary / "lua_global_enums_harness"
        # `lua_runtime.cpp` textually includes the generated implementation, so
        # linking it again would define PcLuaEnumData::Tables twice. Only pass the
        # generated file as its own translation unit when the runtime no longer
        # includes it; either way it is compiled exactly once.
        runtime_include = '#include "program/pc_lua_enum_data.cpp"'
        generated_sources = (
            [] if runtime_include in (SOURCE / "lua_runtime.cpp").read_text()
            else [str(SOURCE / "program/pc_lua_enum_data.cpp")]
        )
        build = subprocess.run(
            ["c++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-DLUA_C89_NUMBERS",
             "-DEXL_LAYERED_RUNTIME=1", "-DEXL_LOAD_KIND=Module",
             "-DEXL_LOAD_KIND_ENUM=2", "-DEXL_PROGRAM_ID=0",
             "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
             "-I", str(lua_root), str(harness),
             *(str(path) for path in layered_lua_runtime_sources(SOURCE)),
             *generated_sources, *map(str, lua_objects),
             "-o", str(cls.harness)], text=True, capture_output=True,
        )
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_global_pc_enum_tables_match_the_fixed_pc_contract(self):
        result = subprocess.run([str(self.harness)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generated_tables_are_global_and_not_starterr_specific(self):
        enum_source = PC_ENUMS_SOURCE
        skip_without_pc_enums(self, enum_source)
        header = SOURCE / "program/pc_lua_enum_data.hpp"
        implementation = SOURCE / "program/pc_lua_enum_data.cpp"
        digest = hashlib.sha256(enum_source.read_bytes()).hexdigest()
        self.assertIn(f"enums.lua SHA-256: {digest}", header.read_text())
        generated = implementation.read_text()
        self.assertIn(f"enums.lua SHA-256: {digest}", generated)

        tables = registered_tables(generated)
        self.assertEqual(tuple(name for name, _ in tables), GENERATED_TABLES)
        self.assertEqual(tables[-1][0], "ModCallbacks")

        counted = {}
        for name, symbol in tables:
            keys = generated_keys(generated, symbol)
            self.assertIsNotNone(keys, f"missing generated value array for {name}: k{symbol}Values")
            self.assertEqual(len(keys), len(set(keys)), f"duplicate keys generated for {name}")
            counted[name] = len(keys)
        self.assertEqual(counted, EXPECTED_ENTRY_COUNTS)

        self.assertNotIn("Starterr", generated)
        self.assertNotIn("starterr", generated)
        self.assertEqual(len(re.findall(r'\{"COLLECTIBLE_[A-Z0-9_]+",', generated)), 752)
        self.assertIn('{"NUM_COLLECTIBLES", 733}', generated)
        self.assertEqual(len(re.findall(r'\{"POOL_[A-Z0-9_]+",', generated)), 39)
        # 30 → 50（2026-10-07 批次 398）：新补的 `RoomTransitionAnim` 表里有 20 条 `ROOM_*`
        # （`ROOM_ANIM_*`）也落在这个正则下 ⇒ 计数合法地涨了。**不是放宽**：`RoomType` 那 30 条仍在
        # （下一行 `NUM_ROOMTYPES == 30` 独立钉着）。
        self.assertEqual(len(re.findall(r'\{"ROOM_[A-Z0-9_]+",', generated)), 50)
        self.assertEqual(len(re.findall(r'\{"STAGE[A-Z0-9_]+",', generated)), 21)
        self.assertIn('{"NUM_ITEMPOOLS", 31}', generated)
        self.assertIn('{"NUM_ROOMTYPES", 30}', generated)
        self.assertIn('{"NUM_STAGES", 14}', generated)
        self.assertIn('{"MC_POST_UPDATE", 1}', generated)
        self.assertIn('{"MC_PRE_GET_COLLECTIBLE", 62}', generated)
        self.assertIn('{"MC_POST_GET_COLLECTIBLE", 63}', generated)
        self.assertIn('{"MC_PRE_ROOM_ENTITY_SPAWN", 71}', generated)
        self.assertIn('{"ENTITY_PLAYER", 1}', generated)
        self.assertIn('{"USE_OWNED", 4}', generated)
        # 位标志表（`1<<N` / `1 << N`）与十六进制字面量都必须按源码取值生成。
        self.assertIn('{"FAMILIAR", 1}', generated)
        self.assertIn('{"BULLET", 2}', generated)
        self.assertIn('{"TEAR", 4}', generated)
        self.assertIn('{"ENEMY", 8}', generated)
        self.assertIn('{"PICKUP", 16}', generated)
        self.assertIn('{"PLAYER", 32}', generated)
        self.assertIn('{"EFFECT", 64}', generated)
        self.assertIn('{"USE_NOHUD", 2048}', generated)
        self.assertIn('{"CURSE_OF_THE_UNKNOWN", 8}', generated)
        self.assertIn('{"CURSE_OF_GIANT", 128}', generated)
        self.assertIn('{"PILL_COLOR_MASK", 2047}', generated)
        self.assertIn('{"PILL_GIANT_FLAG", 2048}', generated)
        self.assertIn('{"TRINKET_ID_MASK", 32767}', generated)
        self.assertIn('{"TRINKET_GOLDEN_FLAG", 32768}', generated)
        # 截断产物（位移表达式只剩开头的 `1`、`0x...` 只剩 `0`）必须彻底消失。
        self.assertNotIn('{"BULLET", 1}', generated)
        self.assertNotIn('{"TEAR", 1}', generated)
        self.assertNotIn('{"ENEMY", 1}', generated)
        self.assertNotIn('{"PICKUP", 1}', generated)
        self.assertNotIn('{"PLAYER", 1}', generated)
        self.assertNotIn('{"EFFECT", 1}', generated)
        self.assertNotIn('{"PILL_COLOR_MASK", 0}', generated)
        self.assertNotIn('{"TRINKET_ID_MASK", 0}', generated)
        for name, symbol in tables:
            self.assertIn(
                f'{{"{name}", k{symbol}Values, '
                f'sizeof(k{symbol}Values) / sizeof(k{symbol}Values[0])}},',
                generated,
            )

    def test_generator_contract_has_no_mod_name_or_source_dependency(self):
        generator = (ROOT / "tools/generate_pc_lua_enum_tables.py").read_text()
        self.assertIn("--enum-source", generator)
        self.assertNotIn("Starterr", generator)
        self.assertNotIn("starterr", generator)
        tables = None
        for node in ast.parse(generator).body:
            if isinstance(node, ast.Assign) and any(
                getattr(target, "id", None) == "TABLES" for target in node.targets
            ):
                tables = ast.literal_eval(node.value)
        self.assertIsNotNone(tables, "generator TABLES tuple not found")
        self.assertEqual(tuple(tables), GENERATED_TABLES)
        self.assertEqual(tuple(tables)[0], "CollectibleType")
        self.assertEqual(tuple(tables)[-1], "ModCallbacks")

    # --- 生成器取值：位移/十六进制回归 ------------------------------------------
    #
    # 这一组用例**直接对着生成器**（不等价于产物断言）：旧的条目正则只认十进制字面量，
    # 于是 `1<<3` 被读成 `1`、`0x800` 被读成 `0`，而"没匹配上"的行还会被静默跳过。
    # 这里同时钉住"算得对"和"读不懂就报错"两件事。

    def test_generator_evaluates_shift_and_hex_value_expressions(self):
        generator = load_generator()
        evaluate = generator._evaluate_expression
        cases = {
            "1 << 3": 8,
            "1<<3": 8,
            "(1 << 3)": 8,
            "1 << 1": 2,
            "1 << 30": 0x40000000,
            "3 << 2": 12,
            "0x800": 2048,
            "0X7ff": 2047,
            "0x8000": 32768,
            "0": 0,
            "-1": -1,
            "1 | 4": 5,
            "1 + 4": 5,
            "(1 << 2) | 1": 5,
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(evaluate(expression, "Table", "KEY"), expected)

    def test_generator_rejects_value_expressions_it_cannot_evaluate(self):
        generator = load_generator()
        evaluate = generator._evaluate_expression
        # 每一个都是"旧实现会静默截断或静默跳过"的形状，现在必须显式失败。
        for expression in ("TEARFLAG(1)", "BitSet128(0, 0)", "1 << 3 4", "OTHER_KEY + 1",
                           "1.5", "1 << ", ""):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    evaluate(expression, "Table", "KEY")
        # 生成的表把值存成 `std::int32_t`，所以超出 int32 的表达式必须**报错**而不是回绕。
        # 这条闸门同时说明了为什么 `EntityFlag`/`ProjectileFlags`/`DamageFlag`（`1<<32`、
        # `0x80000000` 一类）今天还不能进 `TABLES`：要发布它们得先把存储拓宽到 64 位。
        for expression in ("1 << 31", "1 << 32", "0x80000000"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    evaluate(expression, "Table", "KEY")

    def test_generator_fails_loudly_on_an_unparsable_table_entry(self):
        generator = load_generator()
        with self.assertRaises(ValueError):
            generator._parse_table("Leftover = {\n    A = TEARFLAG(1),\n}", "Leftover")
        # 能读的行照旧读出来（同一个函数里两种行为并存，不是"全都报错"）。
        parsed = generator._parse_table(
            "Leftover = {\n    A = 1 << 3, -- comment\n    B = A,\n}", "Leftover"
        )
        self.assertEqual(parsed, {"A": 8, "B": 8})

    def test_generator_reads_the_frozen_source_bit_flag_tables(self):
        generator = load_generator()
        enum_source = PC_ENUMS_SOURCE
        skip_without_pc_enums(self, enum_source)
        source = enum_source.read_text(encoding="utf-8")
        values = generator._parse_values(source)
        self.assertEqual(
            values["EntityPartition"],
            {"FAMILIAR": 1, "BULLET": 2, "TEAR": 4, "ENEMY": 8, "PICKUP": 16,
             "PLAYER": 32, "EFFECT": 64},
        )
        self.assertEqual(values["UseFlag"]["USE_NOCOSTUME"], 2)
        self.assertEqual(values["UseFlag"]["USE_OWNED"], 4)
        self.assertEqual(values["UseFlag"]["USE_NOHUD"], 2048)
        self.assertEqual(values["LevelCurse"]["CURSE_OF_THE_UNKNOWN"], 8)
        self.assertEqual(values["LevelCurse"]["CURSE_OF_GIANT"], 128)
        self.assertEqual(values["LevelCurse"]["NUM_CURSES"], 9)
        self.assertEqual(values["PillColor"]["PILL_GIANT_FLAG"], 0x800)
        self.assertEqual(values["PillColor"]["PILL_COLOR_MASK"], 0x7FF)
        self.assertEqual(values["TrinketType"]["TRINKET_GOLDEN_FLAG"], 0x8000)
        self.assertEqual(values["TrinketType"]["TRINKET_ID_MASK"], 0x7FFF)

        # 独立复核：源码里每一个 `1 << N` 形状的条目都必须等于 `1 << N`
        # （用正则自己算一遍，不复用生成器的求值器，避免同义反复）。
        shift_entries = 0
        for table in GENERATED_TABLES:
            body = generator._table_body(source, table)
            for line in body.splitlines():
                match = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*1\s*<<\s*(\d+)\s*,?\s*(?:--.*)?$", line)
                if match is None:
                    continue
                shift_entries += 1
                self.assertEqual(
                    values[table][match.group(1)], 1 << int(match.group(2)),
                    f"{table}.{match.group(1)}",
                )
        # 这个数字就是"曾经全部被截断成 1"的条目数，掉了说明用例自己失效了。
        # 24 → 29（2026-10-07 批次 398）：新补的 `ActionTriggers` 表里有 5 条 `1 << N`
        # （`UseFlag` 11 / `LevelCurse` 7 / `EntityPartition` 6 三条原有表不变）⇒ 合法地涨了。
        self.assertEqual(shift_entries, 29)


if __name__ == "__main__":
    unittest.main()
