"""门禁：批次 342（2026-10-04）—— 三条 API（两条字段行 + 一条共用表构造的 getter）。

## 这一批是什么

| API | 契约 | 机制 | Switch 落点 |
| --- | --- | --- | --- |
| `EntityPlayer:StopExtraAnimation()` | `EntityPlayer.md:1760` | 字段行 + **本批新开** `FieldKind::TwoByteConstZero`（两格各写常量 0） | `Entity_Player + 0x1710` 与 `+0x1712`（中间 `+0x1711` **不许碰**） |
| `Game:Darken(float, int)` | `Game.md:129` | 字段行 + **本批新开** `FieldKind::FloatThenIntFromArgs`（两实参写两格） | `Game + 0x24F9C0`(float) 与 `Game + 0x24F9B8`(int)（**两格不相邻**） |
| `GridEntity:GetSaveState()` | `GridEntity.md:46` | 与属性 `Desc` **共用** `PushGridEntityDescTable` | `GridEntity + 0x08` 起的三格（`Type`/`Variant`/`VarData`） |

依据 = `docs/取证-F组-Explode与明暗与动画落地规格-20261004b.md` 与
`docs/取证-G组-SaveState与列表落地规格-20261004b.md`；偏移在落地前**自己反汇编复过一遍**
（★ F 组把「每帧递减 Timeout」那处记成 `ai_dark_one`，实际所属符号是 `Game::Update`）。

## 本批的三条判据（都能在宿主里**验真值**，因为两条字段行没有入口指纹）

1. ★★ `Game:Darken(0.5, 120)` 之后，伪造 `Game` 块的 `+0x24F9C0` 必须是 **`0.5f` 的位型**、
   `+0x24F9B8` 必须是 **120** —— **两格不相邻**，写错其中任何一格这条就红。
2. ★★ `p:StopExtraAnimation()` 之后 `+0x1710` 与 `+0x1712` **都必须变 0**，而**中间那格 `+0x1711`
   必须原封不动**（预置 `0xAB`）—— 这条挡的是「用一个 `u16 = 0` 一次写两格」那种偷懒
   （那会连带清掉中间那格，与 PC 不一致）。
3. ★ `ge.Desc` 与 `ge:GetSaveState()` 的 `Type`/`Variant`/`VarData` **逐值相等** —— 契约
   `GridEntity.md:49` 逐字要求两者返回**同一个** `GridEntityDesc` 对象（本批把两处抽成同一个助手）。

## 没验到的（真机项）

* 真机上「玩家的额外动画真的被中止」「房间真的变暗」「那三格确实是 Desc 的三格」
  ⇒ 夹具与实现引用同一批常量，**自己证不了自己**；挂作业单第九节。
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness

SOURCE = Path(__file__).resolve().parent.parent / "source"
ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
GAME_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "game_api.cpp"
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
LAYOUT_GAME = ROOT / "tools" / "layout_tables" / "game.json"
LAYOUT_EP = ROOT / "tools" / "layout_tables" / "entity_player.json"
GAME_HEADER = ROOT / "runtime" / "source" / "game_layout.hpp"
EP_HEADER = ROOT / "runtime" / "source" / "entity_player_layout.hpp"

#: 黑暗那一场用的两个实参：`Darkness = 0.5`（非整值浮点，必须放行）、`Timeout = 120`。
DARK_DARKNESS = 0.5
DARK_TIMEOUT = 120

#: 网格实体那三格的夹具值（三格互不相同 ⇒ 「读错格 / 取常量」都能被抓出来）。
GE_TYPE = 8
GE_VARIANT = 3
GE_VAR_DATA = 7
GRID_INDEX = 31
GRID_WIDTH = 13

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_player_layout.hpp"
#include "runtime_constants.hpp"
#include "interfaces/lua/api500_world.guards.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 341 与本目录的 `test_lua_grid_entity_fields.py`）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                         = Game*（**这一批 Owner 槽指向 Game 块**）
//   Game + kGamePlayerArrayBegin/End         = 一个元素的玩家指针数组（`Isaac.GetPlayer(0)` 要）
//   Game + 0x24F9B8 / +0x24F9C0              = Darken 的两格（**不相邻**）
//   玩家块                                    = vptr + Type=PLAYER，`+0x1710/0x1711/0x1712` 三字节
//   g_RoomBytes（由 `ReadCurrentGameRoom` 直接交回）= 网格实体表（按网格下标索引）
//   网格实体块                                = Type/Variant/VarData 三格
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_EntityBytes;
std::uintptr_t g_EngineBase = 0;

constexpr std::uint32_t kGridWidth = GRID_WIDTH;
constexpr std::uint32_t kGridIndex = GRID_INDEX;
constexpr std::uint32_t kGeType = GE_TYPE;
constexpr std::uint32_t kGeVariant = GE_VARIANT;
constexpr std::uint32_t kGeVarData = GE_VAR_DATA;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

float ReadDarkness() {
    float value = 0.0F;
    std::memcpy(&value, g_GameBytes.data() + kGameTargetDarknessOffset, sizeof(value));
    return value;
}

std::uint32_t ReadTimeout() {
    std::uint32_t value = 0;
    std::memcpy(&value, g_GameBytes.data() + kGameDarknessTimeoutOffset, sizeof(value));
    return value;
}

void PublishFakeMemory() {
    //: ★ 模块块只要盖住全局槽；两条字段行没有入口指纹，所以**不需要**盖引擎代码区。
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    //: `Game` 块：要盖住玩家数组两个偏移与 Darken 的两格。
    const std::size_t gameSize =
        (kGameTargetDarknessOffset > kGamePlayerArrayEndOffset ? kGameTargetDarknessOffset
                                                               : kGamePlayerArrayEndOffset) +
        sizeof(std::uint64_t) + 8;
    g_GameBytes.assign(gameSize, 0);
    //: Darken 的两格与中间那格都预置成 0（判据是"调用后被写成实参"）。
    WriteAt<std::uint32_t>(g_GameBytes, kGameTargetDarknessOffset, 0u);
    WriteAt<std::uint32_t>(g_GameBytes, kGameDarknessTimeoutOffset, 0u);

    //: 玩家块：三字节预置 —— `+0x1710`/`+0x1712` 会被 API 清 0，`+0x1711` **必须保持 0xAB**。
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);
    g_PlayerBytes[kEntityPlayerExtraAnimationPlayingOffset] = 0x01;
    g_PlayerBytes[kEntityPlayerExtraAnimationPlayingOffset + 1] = 0xAB;
    g_PlayerBytes[kEntityPlayerExtraAnimationFinishedOffset] = 0x01;

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + sizeof(std::uint64_t));

    //: 网格实体块与"房间里的网格实体表"（`Room + kRoomGridEntityTableOffset`，每项一个指针）。
    g_EntityBytes.assign(0x48, 0);
    WriteAt<std::uintptr_t>(g_EntityBytes,0,AddressOf(g_ModuleBytes)+kGridEntity_SpikesVtableOffset);
    const auto& gridLayout=isaac::runtime::api500_world::kLayouts[0];
    std::memcpy(g_ModuleBytes.data()+gridLayout.offset,gridLayout.bytes.data(),gridLayout.bytes.size());
    WriteAt<std::uint32_t>(g_EntityBytes, kGridEntityTypeOffset, kGeType);
    WriteAt<std::uint32_t>(g_EntityBytes, kGridEntityVariantOffset, kGeVariant);
    WriteAt<std::uint32_t>(g_EntityBytes, kGridEntityVarDataOffset, kGeVarData);
    WriteAt<std::uint32_t>(g_EntityBytes, kGridEntityGridIndexOffset, kGridIndex);

    const std::size_t tableOffset =
        kRoomGridEntityTableOffset + kGridIndex * sizeof(std::uintptr_t);
    g_RoomBytes.assign(tableOffset + sizeof(std::uintptr_t) + 8, 0);
    WriteAt<std::uint32_t>(g_RoomBytes, kRoomGridWidthOffset, kGridWidth);
    WriteAt<std::uintptr_t>(g_RoomBytes, tableOffset, AddressOf(g_EntityBytes));

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

//: 当前房间直接交回伪造的房间块（与 `test_lua_grid_entity_fields.py` 同一形态）——
//: 本批只关心"网格实体能不能拿到"，房间那条链怎么接不影响判据。
GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = reinterpret_cast<void*>(AddressOf(g_RoomBytes));
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    PublishFakeMemory();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);
    std::printf("B342 before darkness=%.6f timeout=%u\n", static_cast<double>(ReadDarkness()),
                static_cast<unsigned>(ReadTimeout()));
    std::printf("B342 bytes playing=%u middle=0x%02X finished=%u\n",
                static_cast<unsigned>(g_PlayerBytes[kEntityPlayerExtraAnimationPlayingOffset]),
                static_cast<unsigned>(g_PlayerBytes[kEntityPlayerExtraAnimationPlayingOffset + 1]),
                static_cast<unsigned>(g_PlayerBytes[kEntityPlayerExtraAnimationFinishedOffset]));

    char script[2048];
    if (std::strcmp(scenario, "dark") == 0) {
        std::snprintf(script, sizeof(script),
            "local function count(...) return select('#', ...) end"
            " local g = Game()"
            " print('B342 darkfn=' .. type(g.Darken))"
            " print('B342 darkn=' .. tostring(count(g:Darken(%.9g, %d))))",
            static_cast<double>(DARK_DARKNESS), static_cast<int>(DARK_TIMEOUT));
    } else if (std::strcmp(scenario, "dark_gate") == 0) {
        const char* s =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function err(f) return tostring(select(2, pcall(f))) end"
            " local g = Game()"
            " print('B342 darknoarg=' .. ok(function() return g:Darken() end))"
            " print('B342 darknoargerr=' .. err(function() return g:Darken() end))"
            " print('B342 darkonearg=' .. ok(function() return g:Darken(0.5) end))"
            " print('B342 darkthreearg=' .. ok(function() return g:Darken(0.5, 10, 20) end))"
            // ★ 第 2 格必须**整数**：`1.5` 要报错。
            " print('B342 darkfloat2=' .. ok(function() return g:Darken(0.5, 1.5) end))"
            " print('B342 darkfloat2err=' .. err(function() return g:Darken(0.5, 1.5) end))"
            // ★ 第 1 格必须是**数值**：字符串要报错。
            " print('B342 darkstr1=' .. ok(function() return g:Darken('x', 10) end))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else if (std::strcmp(scenario, "stop") == 0) {
        const char* s =
            "local function count(...) return select('#', ...) end"
            " local p = Isaac.GetPlayer(0)"
            " print('B342 stopfn=' .. type(p.StopExtraAnimation))"
            " print('B342 stopn=' .. tostring(count(p:StopExtraAnimation())))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else if (std::strcmp(scenario, "stop_gate") == 0) {
        const char* s =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function err(f) return tostring(select(2, pcall(f))) end"
            " local p = Isaac.GetPlayer(0)"
            " print('B342 stopextra=' .. ok(function() return p:StopExtraAnimation(1) end))"
            " print('B342 stopextraerr=' .. err(function() return p:StopExtraAnimation(1) end))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else if (std::strcmp(scenario, "desc") == 0) {
        const char* s =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local room = Game():GetRoom()"
            " local ge = room:GetGridEntity(GRID_INDEX)"
            " local desc = ge.Desc"
            " local save = ge:GetSaveState()"
            " print('B342 savefn=' .. type(ge.GetSaveState))"
            " print('B342 save=' .. tostring(save.Type)..','..tostring(save.Variant)..','"
            " ..tostring(save.VarData))"
            " print('B342 desc=' .. tostring(desc.Type)..','..tostring(desc.Variant)..','"
            " ..tostring(desc.VarData))"
            " print('B342 same=' .. tostring(save.Type == desc.Type and save.Variant == desc.Variant"
            " and save.VarData == desc.VarData))"
            " print('B342 saveextra=' .. ok(function() return ge:GetSaveState(1) end))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b342.lua");
    static_cast<void>(result);
    std::printf("B342 after darkness=%.6f timeout=%u\n", static_cast<double>(ReadDarkness()),
                static_cast<unsigned>(ReadTimeout()));
    std::printf("B342 bytes playing=%u middle=0x%02X finished=%u\n",
                static_cast<unsigned>(g_PlayerBytes[kEntityPlayerExtraAnimationPlayingOffset]),
                static_cast<unsigned>(g_PlayerBytes[kEntityPlayerExtraAnimationPlayingOffset + 1]),
                static_cast<unsigned>(g_PlayerBytes[kEntityPlayerExtraAnimationFinishedOffset]));
    return 0;
}
'''


class Batch342FieldRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b342-")
        source = HARNESS
        for token, value in (
            ("DARK_DARKNESS", repr(DARK_DARKNESS)),
            ("DARK_TIMEOUT", repr(DARK_TIMEOUT)),
            ("GE_TYPE", str(GE_TYPE)),
            ("GE_VARIANT", str(GE_VARIANT)),
            ("GE_VAR_DATA", str(GE_VAR_DATA)),
            ("GRID_INDEX", str(GRID_INDEX)),
            ("GRID_WIDTH", str(GRID_WIDTH)),
        ):
            source = source.replace(token, value)
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=source,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主 · 真值）

    def test_darken_writes_both_cells(self):
        """★★ **真值判据**：`Game():Darken(0.5, 120)` ⇒ `Game+0x24F9C0 = 0.5f` 且 `+0x24F9B8 = 120`。

        两格**不相邻**（中间夹着 `+0x24F9BC`）⇒ 「只写了一格」「两格写反」「用一条 u64 连中间那格
        一起覆盖」都会让这条红。`0.5` 是非整值浮点 ⇒ 同时验了「第 1 格的数值闸不套整数闸」。
        """
        out = self.run_scenario("dark")
        self.assertIn("B342 darkfn=function", out)
        self.assertIn("B342 before darkness=0.000000 timeout=0", out)
        self.assertIn(f"B342 after darkness={DARK_DARKNESS:.6f} timeout={DARK_TIMEOUT}", out)
        self.assertIn("B342 darkn=0", out)

    def test_darken_argument_gate(self):
        """参数闸门：**恰好两个**（一个数值 + 一个整数）；第 2 格非整值要报错。"""
        out = self.run_scenario("dark_gate")
        self.assertIn("B342 darknoarg=false", out)
        self.assertIn("Game:Darken expects one number argument and one integer argument", out)
        self.assertIn("B342 darkonearg=false", out)
        self.assertIn("B342 darkthreearg=false", out)
        #: ★ 第 2 格是**整数**闸：`1.5` 必须被拒（与第 1 格相反）。
        self.assertIn("B342 darkfloat2=false", out)
        self.assertIn("B342 darkstr1=false", out)

    def test_stop_extra_animation_clears_exactly_two_bytes(self):
        """★★ **真值判据**：两格清 0，而**中间那格 `+0x1711` 必须原封不动**。

        预置 `+0x1710 = 0x01`、`+0x1711 = 0xAB`、`+0x1712 = 0x01`。
        调完必须是 `0 / 0xAB / 0`。★ 若有人图省事「往 `+0x1710` 写一个 `u16 = 0`」，
        中间那格会变成 `0x00` ⇒ 这条立刻红（PC 明确跳过它）。
        """
        out = self.run_scenario("stop")
        self.assertIn("B342 stopfn=function", out)
        self.assertIn("B342 bytes playing=1 middle=0xAB finished=1", out)
        self.assertIn("B342 stopn=0", out)
        self.assertIn("B342 bytes playing=0 middle=0xAB finished=0", out)
        self.assertNotIn("middle=0x00", out)

    def test_stop_extra_animation_argument_gate(self):
        """参数闸门：**恰好一个**（就是接收者）。"""
        out = self.run_scenario("stop_gate")
        self.assertIn("B342 stopextra=false", out)
        self.assertIn("EntityPlayer:StopExtraAnimation accepts no arguments", out)

    def test_get_save_state_matches_the_desc_property(self):
        """★ `ge:GetSaveState()` 与 `ge.Desc` **逐值相等** —— 契约 `GridEntity.md:49` 的逐字要求。

        本批把两处抽成同一个助手（`PushGridEntityDescTable`）⇒ 这条同时是那次**去重**的回归：
        若只改了 `Desc` 而没改 `GetSaveState`（或反过来），两个表就会不一致。
        三格夹具值互不相同（`8/3/7`），所以「读错格」「取常量」也都会被这条抓出来。
        """
        out = self.run_scenario("desc")
        self.assertIn("B342 savefn=function", out)
        self.assertIn(f"B342 save={GE_TYPE},{GE_VARIANT},{GE_VAR_DATA}", out)
        self.assertIn(f"B342 desc={GE_TYPE},{GE_VARIANT},{GE_VAR_DATA}", out)
        self.assertIn("B342 same=true", out)
        self.assertIn("B342 saveextra=false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 字段行 / 新 kind / 偏移常量 / 布局表 / 编译期对账 / 共用助手。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        game = GAME_API.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        field_header = FIELD_HEADER.read_text(encoding="utf-8")

        # --- 目录行 -------------------------------------------------------------
        for needle in (
            'MakeId(ApiDomain::Isaac, 1, 0x00F1), ApiDomain::Isaac, "GridEntity", "GetSaveState"',
            'MakeId(ApiDomain::Isaac, 1, 0x00F2), ApiDomain::Isaac, "EntityPlayer", "StopExtraAnimation"',
            'MakeId(ApiDomain::Game, 1, 0x0018), ApiDomain::Game, "Game", "Darken"',
        ):
            self.assertIn(needle, catalog, f"目录行缺失：{needle}")

        # --- 两条字段行 ---------------------------------------------------------
        self.assertRegex(
            api,
            r"\{\s*0x0E0100F2,\s*kEntityPlayerExtraAnimationPlayingOffset,\s*"
            r"static_cast<std::uint32_t>\(kEntityPlayerExtraAnimationFinishedOffset\),\s*"
            r"FieldKind::TwoByteConstZero,\s*FieldMissing::False,\s*"
            r"FieldReceipt::EntityPlayer,\s*0xFF\}",
            "StopExtraAnimation 的数据行缺失或形状/接收者不对")
        self.assertRegex(
            game,
            r"\{\s*0x02010018,\s*kGameTargetDarknessOffset,\s*"
            r"static_cast<std::uint32_t>\(kGameDarknessTimeoutOffset\),\s*"
            r"FieldKind::FloatThenIntFromArgs,\s*FieldMissing::Zero,\s*"
            r"FieldReceipt::Level,\s*0xFF\}",
            "Darken 的数据行缺失或形状/接收者不对")

        # --- 新 kind ------------------------------------------------------------
        self.assertIn("FloatThenIntFromArgs = 21,", field_header)
        self.assertIn("TwoByteConstZero = 22,", field_header)
        self.assertRegex(api, r"RowReturnsNoValues[\s\S]{0,1500}FieldKind::FloatThenIntFromArgs")
        self.assertRegex(api, r"RowReturnsNoValues[\s\S]{0,1500}FieldKind::TwoByteConstZero")
        self.assertIn("case FieldKind::FloatThenIntFromArgs:", api)
        self.assertIn("case FieldKind::TwoByteConstZero:", api)
        self.assertRegex(api, r"wantsFloatThenIntArguments[\s\S]{0,400}FieldKind::FloatThenIntFromArgs")

        # --- 偏移常量 + 编译期对账 ------------------------------------------------
        for needle in (
            "inline constexpr uintptr_t kGameTargetDarknessOffset = 0x24F9C0;",
            "inline constexpr uintptr_t kGameDarknessTimeoutOffset = 0x24F9B8;",
            "inline constexpr uintptr_t kEntityPlayerExtraAnimationPlayingOffset = 0x1710;",
            "inline constexpr uintptr_t kEntityPlayerExtraAnimationFinishedOffset = 0x1712;",
        ):
            self.assertIn(needle, constants, f"常量缺失：{needle}")
        self.assertIn("kGameTargetDarknessOffset == layout::kGameTargetDarknessOffset", game)
        self.assertIn("kGameDarknessTimeoutOffset == layout::kGameDarknessTimeoutOffset", game)
        self.assertIn(
            "kEntityPlayerExtraAnimationPlayingOffset ==\n"
            "                  layout::kEntity_PlayerExtraAnimationPlayingOffset", api)
        self.assertIn("kGameTargetDarknessOffset", GAME_HEADER.read_text(encoding="utf-8"))
        self.assertIn("kEntity_PlayerExtraAnimationPlayingOffset",
                      EP_HEADER.read_text(encoding="utf-8"))

        # --- `GetSaveState` 与 `Desc` 共用同一份表构造 ----------------------------
        self.assertRegex(remaining,r"bool\s+PushGridEntityDescTable\(lua_State\*\s*state,\s*std::uintptr_t\s*entity\)")
        self.assertEqual(remaining.count("PushGridEntityDescTable(state, entity)"), 2,
                         "`Desc` 与 `GetSaveState` 必须**各调一次**同一个助手（去重没做全）")
        self.assertRegex(remaining, r"\{0x0E0100F1, &GridEntityGetSaveState\},")

    def test_the_layout_rows_are_confirmed(self):
        """两张布局表的新行都必须 `confirmed`（`--verify` 会重新反汇编逐条核对）。"""
        import json
        game = json.loads(LAYOUT_GAME.read_text(encoding="utf-8"))
        grows = {row["name"]: row for row in game["rows"]}
        self.assertEqual(grows["TargetDarkness"]["offset"], 0x24F9C0)
        self.assertEqual(grows["TargetDarkness"]["confidence"], "confirmed")
        self.assertEqual(grows["DarknessTimeout"]["offset"], 0x24F9B8)
        self.assertEqual(grows["DarknessTimeout"]["confidence"], "confirmed")
        #: ★ 两格**不相邻**：差值必须是 8（中间夹着 0x24F9BC）。
        self.assertEqual(grows["TargetDarkness"]["offset"] - grows["DarknessTimeout"]["offset"], 8)

        ep = json.loads(LAYOUT_EP.read_text(encoding="utf-8"))
        erows = {row["name"]: row for row in ep["rows"]}
        self.assertEqual(erows["ExtraAnimationPlaying"]["offset"], 0x1710)
        self.assertEqual(erows["ExtraAnimationFinished"]["offset"], 0x1712)
        self.assertEqual(erows["ExtraAnimationPlaying"]["confidence"], "confirmed")
        self.assertEqual(erows["ExtraAnimationFinished"]["confidence"], "confirmed")
        #: ★ 两格**相隔 2**（中间那格不在表里 = 我们不认它）。
        self.assertEqual(erows["ExtraAnimationFinished"]["offset"] -
                         erows["ExtraAnimationPlaying"]["offset"], 2)

    def test_the_evidence_and_the_corrected_symbol_are_recorded(self):
        """常量段必须写明四条来源、并**更正 F 组那处符号归属**（`ai_dark_one` → `Game::Update`）。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        for needle in ("0x24F9B8", "0x24F9C0", "0x1710", "0x1712",
                       "0x432F60", "0x57B1D0", "0x71FF60",
                       "IsExtraAnimationFinished", "PlayExtraAnimation",
                       "GetLightingAlpha", "ai_lamb",
                       "Game::Update"):
            self.assertIn(needle, constants, f"证据 {needle} 没有写进常量段")
        self.assertIn("ai_dark_one", constants)  # 被更正的那处也要留痕
        self.assertIn("Game.md", constants)
        self.assertIn("EntityPlayer.md", constants)
        self.assertIn("GridEntity.md", constants)


if __name__ == "__main__":
    unittest.main()
