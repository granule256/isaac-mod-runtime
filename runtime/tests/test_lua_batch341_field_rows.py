"""门禁：批次 341（2026-10-04）—— 四条 API（两条字段行 + 两条引擎方法行）。

## 这一批是什么

| API | 契约 | 引擎侧 | 机制 | 语料 |
| --- | --- | --- | --- | --- |
| `Entity:IsInvincible()` | `Entity.md:486` | 直读 `Entity + 0x384` 一个字节 | 字段数据行（`FieldKind::Bool`，**0 字节代码**） | 2 处 |
| `EntityLaser:SetMaxDistance(float)` | `EntityLaser.md:126` | 赋值 `Entity_Laser + 0x4F8` 一个 float | 字段数据行（**本批新开** `FieldKind::FloatFromArg`） | 1 处 |
| `EntityPlayer:TryRemoveTrinketCostume(TrinketType)` | `EntityPlayer.md:1838` | 转发 `TryRemoveCostume(eTrinketType) @ 0x2A25B0` | 引擎方法行（`Void1`，**0 字节代码**） | 1 处 |
| `EntityFamiliar:FollowPosition(Vector Pos)` | `EntityFamiliar.md:70` | 转发 `follow_position(Vector2 const&) @ 0xAFCC0` | 引擎方法行（**本批新开** `VoidVector2Ref`，纯数据） | 1 处 |

四条的判决依据都来自只读取证报告
（`docs/取证-C组-三条字段-20261004.md` / `docs/取证-D组-杂项八条-20261004.md`）。

## ★★ 两条被推翻的旧负结果（本批最重要的产出）

1. **`EntityFamiliar:FollowPosition`**：批次 331 记「符号在，但函数体**从不读实参** ⇒ 不能接」。
   复核证明那次是**线性读漏了分支** —— 函数有两条路，守卫**不成立**支（`0xAFD20`，同一栈帧）
   的 `mov x0, x1` 用的就是**原始实参**，而且与 PC 的 `FollowPosition`（`0x5F4EB0`）两条路逐条同形。
2. **`Entity:IsInvincible`**：批次 336 记「Switch 侧找不到锚」。锚一直在 ——
   具名写入方 `Entity_NPC_VisageMask::SetNoDamage(bool)`、`Entity::Init` 出生清零、
   `Entity::TakeDamage` / `Entity::IsVulnerableEnemy` 两条受击闸门，
   加上本区 PC `0x2C4`…`0x308` 的增量恒为 `+0x7C`（三个已 confirmed 字段作证）。

## 宿主验到了什么、没验到什么

* ★★ **字段行两条验到了真值**：字段数据行**没有入口指纹、读/写的就是我们伪造的那块内存**
  ⇒ 夹具摆初值、调 API、**读回来比**。
  * `IsInvincible`：`0x00` ⇒ `false`、`0x01` ⇒ `true`、`0x02` ⇒ `true`（非零即真）、`0xFF` ⇒ `true`；
  * `SetMaxDistance`：两次摆不同初值/不同实参，**返回值必须是那一格的新值**（整格覆盖，不是乘、不是写错格）。
* **验到**（两条写/读侧）：返回值个数（`IsInvincible` = 1 个布尔；`SetMaxDistance` = **0** 个）；
  参数闸门（多给/少给/类型不对都报错，消息里有名字；★ `SetMaxDistance` 必须放行非整值浮点）。
* **验到**（两条引擎方法行）：方法真的挂上了（`type(...) == "function"`）；
  宿主里**入口字对不上** ⇒ **不调引擎、不报错**（`FollowPosition` 返回 0 个值）；
  `FollowPosition` 的**接收者精确闸门**（点号 + 显式传别的实体 ⇒ 不报错、什么都不做）。
* **没验到**：真机上引擎真的做了什么 / 那两格到底是哪个语义 ⇒ 真机项（作业单第九节）。
"""

import json
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
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
METHOD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "engine_method_api.hpp"
LAYOUT_ENTITY = ROOT / "tools" / "layout_tables" / "entity.json"
LAYOUT_LASER = ROOT / "tools" / "layout_tables" / "entity_laser.json"
LAYOUT_ENTITY_HEADER = ROOT / "runtime" / "source" / "entity_layout.hpp"
SURFACE = ROOT / "runtime" / "tests" / "contract" / "test_engine_row_api_surface.py"

#: `(场景, Entity+0x384 的初值, Lua 期望值)`。
INVINCIBLE_CASES = (
    ("inv0", 0x00, "false"),
    ("inv1", 0x01, "true"),
    ("inv2", 0x02, "true"),
    ("invff", 0xFF, "true"),
)

#: `(场景, Entity_Laser+0x4F8 的初值, 实参, 期望的新值)` —— ★ 三条互不相同，
#: 用来同时堵住「乘出来」「写成常量」「写错格」三种错法。
MAXDISTANCE_CASES = (
    ("las_a", 0.0, 40.0, 40.0),
    ("las_b", 12.5, 1.5, 1.5),
    ("las_c", 300.0, 0.0, 0.0),
)

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 330/333 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                         = Game*
//   Game + kGamePlayerArrayBegin/End         = 只有一个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset / Type = PLAYER
//   玩家对象 + kEntityParentOffset            = g_TargetBytes（本批那条激光 / familiar）
//
// ★★ 字段行（`IsInvincible` / `SetMaxDistance`）读/写的就是这块内存 ⇒ **真值可验**。
// ★ 引擎方法行（`TryRemoveTrinketCostume` / `FollowPosition`）在宿主里**入口字必然对不上**
//   （模块块是零）⇒ 静默降级、不调引擎 —— 这正是我们要验的那条路。
//   ★ 模块块**故意开得足够大**，盖住本批用到的最大引擎偏移：不这么做就是一次越界读
//   （`EngineEntryWordMatches` 对地址是裸 `memcpy`，没有边界判定）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_TargetBytes;
std::vector<unsigned char> g_OtherBytes;
std::uintptr_t g_EngineBase = 0;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void WriteIsInvincible(std::uint8_t value) {
    g_PlayerBytes[kEntityIsInvincibleOffset] = value;
}

std::uint8_t ReadIsInvincible() { return g_PlayerBytes[kEntityIsInvincibleOffset]; }

void WriteMaxDistance(float value) {
    std::memcpy(g_TargetBytes.data() + kEntityLaserMaxDistanceOffset, &value, sizeof(value));
}

float ReadMaxDistance() {
    float value = 0.0F;
    std::memcpy(&value, g_TargetBytes.data() + kEntityLaserMaxDistanceOffset, sizeof(value));
    return value;
}

//: `target`：0 = 不设（只测玩家自己的字段），1 = 激光，2 = familiar。
void PublishFakeGame(int target) {
    // ★ 盖住本批最大的引擎偏移（否则 `EngineEntryWordMatches` 会越界读）。
    g_ModuleBytes.assign(kEntityFamiliarFollowPositionOffset + 16, 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);

    static_assert(kEntityIsInvincibleOffset + 1 <= kEntityPlayerSize,
                  "the fake player block must cover the is-invincible cell");
    static_assert(kEntityLaserMaxDistanceOffset + sizeof(float) <= kEntityPlayerSize,
                  "the fake target block must cover the max-distance cell");

    g_TargetBytes.assign(kEntityPlayerSize, 0);
    if (target == 1) {
        WriteAt<std::uint64_t>(g_TargetBytes, 0, g_EngineBase + kEntityLaserVtableOffset);
        WriteAt<std::uint32_t>(g_TargetBytes, kEntityTypeOffset, kEntityTypeLaser);
    } else if (target == 2) {
        WriteAt<std::uint64_t>(g_TargetBytes, 0, g_EngineBase + kEntityFamiliarVtableOffset);
        WriteAt<std::uint32_t>(g_TargetBytes, kEntityTypeOffset, kEntityTypeFamiliar);
    }
    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityParentOffset, AddressOf(g_TargetBytes));

    //: ★ 一个**不是** familiar 的实体（vptr 是玩家的、Type 也是玩家的）——
    //: 用来验"接收者精确闸门"：`fam.FollowPosition(other, Vector(1,2))` 必须被**静默**挡下
    //: （`follow_position` 一进去就解引用 `[this+0xF50]`，拿错对象会野读）。
    //: 挂成 familiar 的 `Parent`，Lua 侧用 `fam.Parent` 取它。
    g_OtherBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_OtherBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_OtherBytes, kEntityTypeOffset, kEntityTypePlayer);
    WriteAt<std::uint64_t>(g_TargetBytes, kEntityParentOffset, AddressOf(g_OtherBytes));

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + sizeof(std::uint64_t));

    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    std::uint8_t initialByte = 0;
    float initialDistance = 0.0F;
    float newDistance = 0.0F;
    int target = 0;
    if (std::strcmp(scenario, "inv0") == 0) { initialByte = INV0; }
    else if (std::strcmp(scenario, "inv1") == 0) { initialByte = INV1; }
    else if (std::strcmp(scenario, "inv2") == 0) { initialByte = INV2; }
    else if (std::strcmp(scenario, "invff") == 0) { initialByte = INVFF; }
    else if (std::strcmp(scenario, "las_a") == 0) { target = 1; initialDistance = LA_INIT; newDistance = LA_NEW; }
    else if (std::strcmp(scenario, "las_b") == 0) { target = 1; initialDistance = LB_INIT; newDistance = LB_NEW; }
    else if (std::strcmp(scenario, "las_c") == 0) { target = 1; initialDistance = LC_INIT; newDistance = LC_NEW; }
    else if (std::strcmp(scenario, "fam") == 0) { target = 2; }
    else if (std::strcmp(scenario, "gate") == 0) { target = 1; }
    else { return 91; }

    PublishFakeGame(target);
    WriteIsInvincible(initialByte);
    WriteMaxDistance(initialDistance);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);
    std::printf("B341 before=%u dist=%.6f\n", static_cast<unsigned>(ReadIsInvincible()),
                static_cast<double>(ReadMaxDistance()));

    char script[2048];
    if (std::strcmp(scenario, "inv0") == 0 || std::strcmp(scenario, "inv1") == 0 ||
        std::strcmp(scenario, "inv2") == 0 || std::strcmp(scenario, "invff") == 0) {
        std::snprintf(script, sizeof(script),
            "local function count(...) return select('#', ...) end"
            " local p = Isaac.GetPlayer(0)"
            " print('B341 invfn=' .. type(p.IsInvincible))"
            " print('B341 inv=' .. tostring(p:IsInvincible()))"
            " print('B341 invn=' .. tostring(count(p:IsInvincible())))");
    } else if (std::strcmp(scenario, "las_a") == 0 || std::strcmp(scenario, "las_b") == 0 ||
               std::strcmp(scenario, "las_c") == 0) {
        std::snprintf(script, sizeof(script),
            "local function count(...) return select('#', ...) end"
            " local p = Isaac.GetPlayer(0)"
            " local laser = p.Parent:ToLaser()"
            " print('B341 lasfn=' .. type(laser and laser.SetMaxDistance))"
            " print('B341 lasn=' .. tostring(count(laser:SetMaxDistance(%.9g))))",
            static_cast<double>(newDistance));
    } else if (std::strcmp(scenario, "fam") == 0) {
        const char* s =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function count(...) return select('#', ...) end"
            " local p = Isaac.GetPlayer(0)"
            " local raw = p.Parent"
            " local fam = raw:ToFamiliar()"
            " print('B341 famkind=' .. type(fam))"
            " print('B341 famfn=' .. type(fam and fam.FollowPosition))"
            // 宿主里入口字对不上 ⇒ 不调引擎、不报错、返回 0 个值。
            " print('B341 famcall=' .. ok(function() return fam:FollowPosition(Vector(1, 2)) end))"
            " print('B341 famret=' .. tostring(count(fam:FollowPosition(Vector(1, 2)))))"
            // ★★ 接收者精确闸门：**点号调用 + 显式传一个别的实体**（`fam.Parent` 是玩家不是够看体）
            // ⇒ 不报错、什么都不做（那条野读被挡在这里）。★ 必须补齐参数个数（2 个），
            // 否则先撞的是"参数个数"那道闸、验不到接收者那一道。
            " local other = fam.Parent"
            " print('B341 famforeign=' .. ok(function() return fam.FollowPosition(other, Vector(1, 2)) end))"
            " print('B341 famforeignret=' .. tostring(count(fam.FollowPosition(other, Vector(1, 2)))))"
            // 参数闸门。
            " print('B341 famnoarg=' .. ok(function() return fam:FollowPosition() end))"
            " print('B341 famnoargerr=' .. tostring(select(2, pcall(function() return fam:FollowPosition() end))))"
            " print('B341 famstrarg=' .. ok(function() return fam:FollowPosition('x') end))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else {
        const char* s =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function err(f) return tostring(select(2, pcall(f))) end"
            " local p = Isaac.GetPlayer(0)"
            " local laser = p.Parent:ToLaser()"
            // --- 字段行：参数闸门 ---------------------------------------------
            " print('B341 invgate=' .. ok(function() return p:IsInvincible(1) end))"
            " print('B341 invgateerr=' .. err(function() return p:IsInvincible(1) end))"
            " print('B341 lasnoarg=' .. ok(function() return laser:SetMaxDistance() end))"
            " print('B341 lasnoargerr=' .. err(function() return laser:SetMaxDistance() end))"
            " print('B341 lasstr=' .. ok(function() return laser:SetMaxDistance('x') end))"
            " print('B341 lastwo=' .. ok(function() return laser:SetMaxDistance(1, 2) end))"
            // --- 引擎方法行：挂上了 + 参数闸门 --------------------------------
            " print('B341 trkfn=' .. type(p.TryRemoveTrinketCostume))"
            " print('B341 trknoarg=' .. ok(function() return p:TryRemoveTrinketCostume() end))"
            " print('B341 trknoargerr=' .. err(function() return p:TryRemoveTrinketCostume() end))"
            " print('B341 trktwo=' .. ok(function() return p:TryRemoveTrinketCostume(1, 2) end))"
            // 宿主里入口字对不上 ⇒ 静默降级（不报错）。
            " print('B341 trkcalls=' .. ok(function() return p:TryRemoveTrinketCostume(1) end))";
        std::snprintf(script, sizeof(script), "%s", s);
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b341.lua");
    static_cast<void>(result);
    std::printf("B341 after=%u dist=%.6f\n", static_cast<unsigned>(ReadIsInvincible()),
                static_cast<double>(ReadMaxDistance()));
    return 0;
}
'''


class Batch341FieldAndMethodRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b341-")
        source = HARNESS
        for name, initial, expected in INVINCIBLE_CASES:
            source = source.replace(f"{name.upper()}", repr(initial))
        for name, initial, new, _expected in MAXDISTANCE_CASES:
            tag = name.split("_")[1].upper()
            source = source.replace(f"L{tag}_INIT", repr(initial))
            source = source.replace(f"L{tag}_NEW", repr(new))
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

    def test_is_invincible_reads_the_real_cell(self):
        """★★ **字段行的真值判据**：`Entity + 0x384` 写 `0x00/0x01/0x02/0xFF` ⇒ `false/true/true/true`。

        `FieldKind::Bool` = 「读一个字节、非零即真」（与 PC 绑定本体「读一个字节」逐字对应）。
        读错偏移会得到 `false`、写成常量会四场相同 —— 都会让至少一场红。
        """
        for name, initial, expected in INVINCIBLE_CASES:
            with self.subTest(scenario=name):
                out = self.run_scenario(name)
                self.assertIn("B341 invfn=function", out)
                self.assertIn(f"B341 inv={expected}", out)
                self.assertIn("B341 invn=1", out)
                self.assertIn(f"B341 before={initial}", out)

    def test_set_max_distance_overwrites_the_real_cell(self):
        """★★ **字段行的真值判据**：`Entity_Laser + 0x4F8` 被**赋成**实参（不是乘、不是写常量）。

        三场互不相同：`0.0 → 40.0`、`12.5 → 1.5`、`300.0 → 0.0`。
        「乘出来」（会得到 0 / 18.75 / 0）、「写错格」（读回初值）、「写整数位型」（会得到 ~1e-45）
        都会让至少一场红。
        """
        for name, initial, new, expected in MAXDISTANCE_CASES:
            with self.subTest(scenario=name):
                out = self.run_scenario(name)
                self.assertIn("B341 lasfn=function", out)
                self.assertIn(f"B341 before=0 dist={initial:.6f}", out)
                self.assertIn(f"B341 after=0 dist={expected:.6f}", out)

    def test_the_write_side_returns_no_values(self):
        """★ 写侧 kind 的口径：`SetMaxDistance` 必须返回 **0** 个值（PC 返回 `void`）。

        ★ 这条兜住「新增写侧 kind 忘了进 `RowReturnsNoValues`」那类错 —— 忘了就会多压一个值。
        """
        out = self.run_scenario("las_a")
        self.assertIn("B341 lasn=0", out)

    def test_engine_rows_are_wired_and_gate_their_arguments(self):
        """两条引擎方法行：真的挂上了 + 参数闸门 + 宿主里静默降级（不报错）。

        * `EntityPlayer:TryRemoveTrinketCostume`：`type(...) == "function"`；
          0 个 / 2 个实参都报错、消息里有名字；正确调用 ⇒ 入口字对不上 ⇒ 不报错。
        * `EntityFamiliar:FollowPosition`：同上 + **接收者精确闸门**（点号 + 显式传别的实体
          ⇒ 不报错、什么都不做 —— 那条野读被挡在这里）+ `Vector` 类型闸门。
        """
        gate = self.run_scenario("gate")
        self.assertIn("B341 trkfn=function", gate)
        self.assertIn("B341 trknoarg=false", gate)
        self.assertIn("EntityPlayer:TryRemoveTrinketCostume expects 1 argument(s)", gate)
        self.assertIn("B341 trktwo=false", gate)
        self.assertIn("B341 trkcalls=true", gate)

        fam = self.run_scenario("fam")
        self.assertIn("B341 famkind=userdata", fam)
        self.assertIn("B341 famfn=function", fam)
        self.assertIn("B341 famcall=true", fam)
        self.assertIn("B341 famret=0", fam)
        self.assertIn("B341 famforeign=true", fam)
        self.assertIn("B341 famforeignret=0", fam)
        self.assertNotIn("B341 famforeign=false", fam)
        self.assertIn("B341 famnoarg=false", fam)
        self.assertIn("EntityFamiliar:FollowPosition expects 1 argument(s)", fam)
        self.assertIn("B341 famstrarg=false", fam)

    def test_field_row_argument_gates(self):
        """两条字段行的参数闸门：只收接收者 / 只收一个**数值**。

        ★★ `SetMaxDistance('x')` 必须报错、而 `1.5` 必须**放行**（非整值浮点）——
        若误用了同族的整数闸，`las_b`（实参 `1.5`）会直接报错、`dist` 会停在初值上。
        """
        out = self.run_scenario("gate")
        self.assertIn("B341 invgate=false", out)
        self.assertIn("Entity:IsInvincible accepts no arguments", out)
        self.assertIn("B341 lasnoarg=false", out)
        self.assertIn("EntityLaser:SetMaxDistance expects one number argument", out)
        self.assertIn("B341 lasstr=false", out)
        self.assertIn("B341 lastwo=false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 新 kind / 新形状 / 偏移常量 / 布局表 / 编译期对账。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        field_header = FIELD_HEADER.read_text(encoding="utf-8")
        method_header = METHOD_HEADER.read_text(encoding="utf-8")
        surface = SURFACE.read_text(encoding="utf-8")

        # --- 目录行（Isaac 域 0x00ED / 0x00EE / 0x00EF / 0x00F0）------------------
        for index, owner, name in (
            (0x00ED, "Entity", "IsInvincible"),
            (0x00EE, "EntityLaser", "SetMaxDistance"),
            (0x00EF, "EntityPlayer", "TryRemoveTrinketCostume"),
            (0x00F0, "EntityFamiliar", "FollowPosition"),
        ):
            with self.subTest(api=f"{owner}:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, '
                    f'"{owner}", "{name}"', catalog, f"目录里没有 {owner}:{name}")

        # --- 两条字段行 ---------------------------------------------------------
        self.assertRegex(
            api,
            r"\{\s*0x0E0100ED,\s*kEntityIsInvincibleOffset,\s*0,\s*"
            r"FieldKind::Bool,\s*FieldMissing::False,\s*FieldReceipt::Entity,\s*0xFF\}",
            "IsInvincible 的数据行缺失或形状/接收者不对")
        self.assertRegex(
            api,
            r"\{\s*0x0E0100EE,\s*kEntityLaserMaxDistanceOffset,\s*0,\s*"
            r"FieldKind::FloatFromArg,\s*FieldMissing::Zero,\s*FieldReceipt::Entity,\s*0xFF\}",
            "SetMaxDistance 的数据行缺失或形状/接收者不对")
        #: ★ 反回归：这两条是**字段**行，不许被塞进引擎方法行。
        self.assertNotRegex(api, r"0x0E0100ED[^\n]*EngineCallShape")
        self.assertNotRegex(api, r"0x0E0100EE[^\n]*EngineCallShape")

        # --- 两条引擎方法行 -----------------------------------------------------
        self.assertRegex(
            api,
            r"\{0x0E0100EF,\s*kEntityPlayerTryRemoveTrinketCostumeOffset,\s*"
            r"kEntityPlayerTryRemoveTrinketCostumeEntryWord,\s*FieldReceipt::EntityPlayer,\s*"
            r"EngineCallShape::Void1,\s*1,\s*0xFF\}",
            "TryRemoveTrinketCostume 的引擎方法行缺失或形状/接收者不对")
        self.assertRegex(
            api,
            r"\{0x0E0100F0,\s*kEntityFamiliarFollowPositionOffset,\s*"
            r"kEntityFamiliarFollowPositionEntryWord,\s*FieldReceipt::EntityFamiliar,\s*"
            r"EngineCallShape::VoidVector2Ref,\s*1,\s*0xFF\}",
            "FollowPosition 的引擎方法行缺失或形状/接收者不对")
        #: ★ 反回归：这两条是**调用**，不许被塞进字段行表。
        self.assertNotRegex(api, r"0x0E0100EF[^\n]*FieldKind::")
        self.assertNotRegex(api, r"0x0E0100F0[^\n]*FieldKind::")

        # --- 新 kind / 新形状 ---------------------------------------------------
        self.assertIn("FloatFromArg = 20,", field_header)
        self.assertRegex(api, r"RowReturnsNoValues[\s\S]{0,1200}FieldKind::FloatFromArg")
        self.assertRegex(api, r"wantsNumberArgument[\s\S]{0,220}FieldKind::FloatFromArg")
        self.assertIn("case FieldKind::FloatFromArg:", api)
        self.assertIn("VoidVector2Ref = 34,", method_header)
        self.assertRegex(
            api,
            r"\{1,\s*\{EngineArgKind::Vector2Ref,\s*EngineArgKind::Int[\s\S]{0,240}?"
            r"EngineReturnKind::Void,\s*FieldReceipt::Entity,\s*IntArgumentGuard::None,\s*0,\s*\{0, 0, 0\}\}",
            "形状 34 的描述符行缺失")

        # --- 偏移常量 -----------------------------------------------------------
        for needle in ("inline constexpr uintptr_t kEntityIsInvincibleOffset = 0x384;",
                       "inline constexpr uintptr_t kEntityLaserMaxDistanceOffset = 0x4F8;",
                       "inline constexpr uintptr_t kEntityPlayerTryRemoveTrinketCostumeOffset = 0x2A25B0;",
                       "inline constexpr std::uint32_t kEntityPlayerTryRemoveTrinketCostumeEntryWord = 0xA9BD7BFDu;",
                       "inline constexpr uintptr_t kEntityFamiliarFollowPositionOffset = 0xAFCC0;",
                       "inline constexpr std::uint32_t kEntityFamiliarFollowPositionEntryWord = 0xD100C3FFu;"):
            self.assertIn(needle, constants, f"常量缺失：{needle}")

        # --- 编译期对账 + 布局表生成物 ------------------------------------------
        self.assertIn("kEntityIsInvincibleOffset == layout::kEntityIsInvincibleOffset", api)
        self.assertIn("kEntityIsInvincibleOffset", LAYOUT_ENTITY_HEADER.read_text(encoding="utf-8"))

        # --- 表面表（`test_engine_row_api_surface` 按 Lua 名字钉形状）-------------
        self.assertIn('"EntityPlayer:TryRemoveTrinketCostume": "Void1"', surface)
        self.assertIn('"EntityFamiliar:FollowPosition": "VoidVector2Ref"', surface)

    def test_the_layout_rows_are_confirmed(self):
        """两张布局表的新行都必须 `confirmed`，且**带具名证据**（写入方/消费者，不是"某处有个格"）。

        `--verify` 会重新反汇编逐条核对；这里额外钉住"证据的形态"：
        `IsInvincible` 要有具名写入方 + 受击闸门；`MaxDistance` 要有两条消费者 + 一条写入方。
        """
        entity = json.loads(LAYOUT_ENTITY.read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in entity["rows"]}
        self.assertIn("IsInvincible", rows)
        row = rows["IsInvincible"]
        self.assertEqual(row["confidence"], "confirmed")
        self.assertEqual(row["offset"], 900)  # 0x384
        self.assertEqual(row["width"], 1)
        self.assertGreaterEqual(len(row["evidence"]), 4)
        functions = " ".join(e["function"] for e in row["evidence"])
        self.assertIn("SetNoDamage", functions)
        self.assertIn("TakeDamage", functions)

        laser = json.loads(LAYOUT_LASER.read_text(encoding="utf-8"))
        self.assertEqual(laser["struct"], "Entity_Laser")
        lrows = {row["name"]: row for row in laser["rows"]}
        self.assertIn("MaxDistance", lrows)
        lrow = lrows["MaxDistance"]
        self.assertEqual(lrow["confidence"], "confirmed")
        self.assertEqual(lrow["offset"], 1272)  # 0x4F8
        self.assertEqual(lrow["width"], 4)
        self.assertEqual(lrow["kind"], "float")
        lfunctions = " ".join(e["function"] for e in lrow["evidence"])
        self.assertIn("update_laser", lfunctions)
        self.assertIn("init_laser", lfunctions)
        self.assertIn("shoot", lfunctions)

    def test_the_two_overturned_negative_results_are_recorded(self):
        """★★ 本批最重要的一条纪律：**推翻旧负结果要留痕、要写清错在哪**。

        `runtime_constants.hpp` 里必须写明：
        * `FollowPosition` 推翻批次 331 的「函数体从不读实参」——错因是**线性读漏了分支**
          （守卫不成立支在 `0xAFD20`，那里 `mov x0, x1` 用的就是实参）；
        * `IsInvincible` 的锚（`SetNoDamage` / `Init` 清零 / 含 `TakeDamage` 的受击闸门）。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        for needle in ("0xAFCC0", "0xAFD20", "0xD100C3FF", "0x2A25B0", "0xA9BD7BFD",
                       "0x384", "0x4F8", "SetNoDamage", "IsVulnerableEnemy",
                       "331", "推翻", "线性读"):
            self.assertIn(needle, constants, f"证据 {needle} 没有写进常量段")
        self.assertIn("EntityFamiliar.md", constants)
        self.assertIn("EntityLaser.md", constants)
        self.assertIn("EntityPlayer.md", constants)


if __name__ == "__main__":
    unittest.main()
