# 2026-10-09更正：列表现在是实时const userdata，Get为冒号调用，越界报错，#可用。
"""门禁：批次 343（2026-10-04）—— `Entity:GetColor` + `ItemConfig:GetCollectibles|GetTrinkets`。

## 这一批是什么

| API | 处数 | 机制 | Switch 落点 |
| --- | --- | --- | --- |
| `Entity:GetColor()` | **4** | 字段行 + **本批新开** `FieldKind::ColorModRead`（读 44 字节 `ColorMod` → 压 Lua `Color`） | `Entity + 0x138`（**当前/生效色**） |
| `ItemConfig:GetCollectibles()` | 1 | 手写处理器（`{Size, Get}` 表） | 向量 `ItemConfig + 0x00 / +0x08` |
| `ItemConfig:GetTrinkets()` | 1 | 同上（共用 `PushItemConfigList`） | 向量 `ItemConfig + 0x18 / +0x20` |

依据 = `docs/取证-K组-GetColor落地规格-20261004d.md`（其上游是
`docs/取证-I组-GetColor离线定案尝试-20261004c.md` 的**离线定案**）与
`docs/取证-G组-SaveState与列表落地规格-20261004b.md`。

## 本批的三条核心判据（宿主里都能验**真值**）

1. ★★ **三格 `ColorMod` 不许取错**：夹具把 `+0x138`（本 API 读的「当前/生效色」）、
   `+0x220`（Lua `Entity.Color` **属性**那一格）、`+0x24C`（`SplatColor`）摆成
   **互不相同**的值 ⇒ 「读到 `+0x220`/`+0x24C`」与「写死常量」都会被抓住。
2. ★★ **是值拷贝、不是活引用**：先取一次、**改句柄自己的 `.R`**、再取一次 ——
   第二次必须仍是引擎里那个值 ⇒ 证明每次调用都重新读引擎那一格、且句柄不持有引擎内存
   （与 PC 的「按值返回」一致）。
3. ★ **两张列表的向量不许读串**：收藏品向量摆 **2** 个元素、饰品向量摆 **3** 个 ⇒
   两个 `.Size` 必须分别等于 2 与 3（读错向量会得到另一个数）。

## 没验到的（真机项）

* 真机上 `+0x138` **确实**是"渲染真正拿去画的那份当前色"（夹具与实现引用同一个常量）。
* 真机上那两对向量偏移**确实**是收藏品表 / 饰品表。
* ★ 与 PC 的一处**已登记的形状差异**：`GetCollectibles()`/`GetTrinkets()` 在 PC 侧返回
  userdata 列表对象，我们返回 `{Size, Get}` 表（`.Size`/`:Get(i)` 同形、**`#` 不支持**）——
  语料只用到 `.Size`；详见 `tools/api_definition_of_done.json` 那两条的 `boundary.detail`。
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
COLOR_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "engine_color_mod.hpp"
SIGNATURES = ROOT / "tools" / "engine_symbol_signatures.json"
CONTRACT_PAGE = ROOT / "tools" / "pc_contract_docs" / "ItemConfig.md"

#: 三格 `ColorMod` 的夹具值：`(+0x138)` 本 API 读的、`(+0x220)` Lua `Entity.Color` 属性、
#: `(+0x24C)` `SplatColor`。**三组互不相同** ⇒ 取错格会被抓住。
CURRENT_TINT = (0.1, 0.2, 0.3, 0.4)
CURRENT_SHIFT = (0.5, 0.6, 0.7)
DEFAULT_TINT = (0.9, 0.8, 0.7, 0.6)
SPLAT_TINT = (0.11, 0.22, 0.33, 0.44)

#: 两张向量的元素个数（**故意不同** ⇒ 读错向量会被抓住）。
COLLECTIBLE_COUNT = 2
TRINKET_COUNT = 3

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存：
//   模块块[base + kGameOwnerGlobalSlotOffset]   = &g_OwnerSlotBytes   → Game*
//   模块块[base + kGameManagerGlobalSlotOffset] = &g_ManagerSlotBytes → Manager*
//   Game + 玩家数组 begin/end                    = 一个元素的玩家指针数组
//   玩家块                                       = vptr + Type=PLAYER，**三格 ColorMod**（+0x138/+0x220/+0x24C）
//   Manager + kManagerItemConfigOffset          = ItemConfig；它 +0x00/+0x08 是收藏品向量、
//                                                 +0x18/+0x20 是饰品向量（长度故意不同）
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_ManagerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_ManagerBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_ItemBytes;
std::uintptr_t g_EngineBase = 0;

constexpr std::uint32_t kCollectibleCount = COLLECTIBLE_COUNT;
constexpr std::uint32_t kTrinketCount = TRINKET_COUNT;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

//: 往一块内存的 `offset` 处放一组 float（`ColorMod` 的 tint / shift）。
void WriteFloats(std::vector<unsigned char>& block, std::size_t offset, const float* values,
                 std::size_t count) {
    std::memcpy(block.data() + offset, values, count * sizeof(float));
}

void PublishFakeMemory() {
    const std::size_t moduleSize =
        (kGameOwnerGlobalSlotOffset > kGameManagerGlobalSlotOffset ? kGameOwnerGlobalSlotOffset
                                                                   : kGameManagerGlobalSlotOffset) +
        sizeof(std::uint64_t) + 8;
    g_ModuleBytes.assign(moduleSize, 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_ManagerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameManagerGlobalSlotOffset,
                           AddressOf(g_ManagerSlotBytes));

    //: Game：玩家数组（1 个元素）。
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t) + 8, 0);

    //: 玩家块：三格 `ColorMod` —— **三组值互不相同**（本批最关键的夹具设计）。
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);
    const float currentTint[4] = {CURRENT_TINT_0, CURRENT_TINT_1, CURRENT_TINT_2, CURRENT_TINT_3};
    const float currentShift[3] = {CURRENT_SHIFT_0, CURRENT_SHIFT_1, CURRENT_SHIFT_2};
    const float defaultTint[4] = {DEFAULT_TINT_0, DEFAULT_TINT_1, DEFAULT_TINT_2, DEFAULT_TINT_3};
    const float splatTint[4] = {SPLAT_TINT_0, SPLAT_TINT_1, SPLAT_TINT_2, SPLAT_TINT_3};
    WriteFloats(g_PlayerBytes, kEntityGetColorOffset, currentTint, 4);
    WriteFloats(g_PlayerBytes, kEntityGetColorOffset + 0x20, currentShift, 3);
    WriteFloats(g_PlayerBytes, ENTITY_DEFAULT_COLOR_OFFSET, defaultTint, 4);
    WriteFloats(g_PlayerBytes, ENTITY_SPLAT_COLOR_OFFSET, splatTint, 4);

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + sizeof(std::uint64_t));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    //: Manager → ItemConfig：两张向量（**长度故意不同** ⇒ 读串会被抓住）。
    //: ★ 一次把整块 `assign` 到位（元素数组也排在块尾），**之后不再 `insert`** ——
    //:   否则 `vector` 重新分配会让先前写进去的绝对指针失效（本项目踩过这类坑）。
    const std::size_t icOff = kManagerItemConfigOffset;
    const std::size_t entriesStart = icOff + kItemConfigTrinketEndOffset + sizeof(std::uint64_t);
    const std::size_t entriesBytes =
        (kCollectibleCount + kTrinketCount) * sizeof(std::uint64_t);
    g_ManagerBytes.assign(entriesStart + entriesBytes + 64, 0);
    g_ItemBytes.assign(0x40, 0);
    for (std::size_t i = 0; i < g_ItemBytes.size(); ++i) {
        g_ItemBytes[i] = static_cast<unsigned char>(i & 0xFF);   // 可读即可（内容不是判据）
    }
    //: ★ 每个条目指针都指向同一块可读内存 —— 本批只验 `.Size` 与 `Get(i)` 的**形状**，
    //:   条目本身的内容不是判据（PC 文档自己说 `Get()` 在这些 list 上是坏的）。
    const std::uintptr_t entriesBase = AddressOf(g_ManagerBytes) + entriesStart;
    auto publish = [&](std::uintptr_t beginOffset, std::uintptr_t endOffset,
                       std::size_t slotStart, std::uint32_t count) {
        for (std::uint32_t i = 0; i < count; ++i) {
            WriteAt<std::uint64_t>(g_ManagerBytes,
                                   entriesStart + (slotStart + i) * sizeof(std::uint64_t),
                                   AddressOf(g_ItemBytes));
        }
        WriteAt<std::uint64_t>(g_ManagerBytes, icOff + beginOffset,
                               entriesBase + slotStart * sizeof(std::uint64_t));
        WriteAt<std::uint64_t>(g_ManagerBytes, icOff + endOffset,
                               entriesBase + (slotStart + count) * sizeof(std::uint64_t));
    };
    publish(kItemConfigCollectibleBeginOffset, kItemConfigCollectibleEndOffset, 0,
            kCollectibleCount);
    publish(kItemConfigTrinketBeginOffset, kItemConfigTrinketEndOffset, kCollectibleCount,
            kTrinketCount);
    WriteAt<std::uint64_t>(g_ManagerSlotBytes, 0, AddressOf(g_ManagerBytes));

    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

//: 供脚本"改完句柄再读一次"用的那一支：本批不做 C 侧的二次改动，
//: 值拷贝判据完全在 Lua 侧完成（改句柄自己的 `.R`，再看第二次 `GetColor()`）。
}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    PublishFakeMemory();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    char script[2048];
    if (std::strcmp(scenario, "color") == 0) {
        const char* s =
            "local function f(v) return string.format('%.3f', v) end"
            " local p = Isaac.GetPlayer(0)"
            " print('B343 colorfn=' .. type(p.GetColor))"
            " local c = p:GetColor()"
            " print('B343 kind=' .. type(c))"
            " print('B343 rgb=' .. f(c.R)..','..f(c.G)..','..f(c.B)..','..f(c.A))"
            " print('B343 shift=' .. f(c.RO)..','..f(c.GO)..','..f(c.BO))"
            // ★★ 值拷贝判据：改**句柄自己**的 R，再取一次 —— 第二次必须仍是引擎里那个值。
            " c.R = 0.9"
            " print('B343 mutated=' .. f(c.R))"
            " local again = p:GetColor()"
            " print('B343 again=' .. f(again.R))"
            " print('B343 sameobj=' .. tostring(again == c))"
            " print('B343 retn=' .. tostring(select('#', p:GetColor())))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else if (std::strcmp(scenario, "color_gate") == 0) {
        const char* s =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function err(f) return tostring(select(2, pcall(f))) end"
            " local p = Isaac.GetPlayer(0)"
            " print('B343 colorextra=' .. ok(function() return p:GetColor(1) end))"
            " print('B343 colorextraerr=' .. err(function() return p:GetColor(1) end))"
            " print('B343 colordot=' .. ok(function() return p.GetColor(p) end))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else if (std::strcmp(scenario, "lists") == 0) {
        const char* s =
            "local ic = Isaac.GetItemConfig()"
            " print('B343 collfn=' .. type(ic.GetCollectibles))"
            " local coll = ic:GetCollectibles()"
            " local trk = ic:GetTrinkets()"
            " print('B343 kind=' .. type(coll)..'/'..type(trk))"
            " print('B343 sizes=' .. tostring(coll.Size)..','..tostring(trk.Size))"
            " print('B343 firstkind=' .. type(coll:Get(0))..'/'..type(trk:Get(0)))"
            " print('B343 lastkind=' .. type(coll:Get(1))..'/'..type(trk:Get(2)))"
            " print('B343 oob=' .. tostring(pcall(function() coll:Get(99) end))..','..tostring(pcall(function() trk:Get(99) end)))"
            " print('B343 neg=' .. tostring(pcall(function() coll:Get(-1) end)))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else if (std::strcmp(scenario, "lists_gate") == 0) {
        const char* s =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local function err(f) return tostring(select(2, pcall(f))) end"
            " local ic = Isaac.GetItemConfig()"
            " print('B343 gcarg=' .. ok(function() return ic:GetCollectibles(1) end))"
            " print('B343 gcargerr=' .. err(function() return ic:GetCollectibles(1) end))"
            " print('B343 gtarg=' .. ok(function() return ic:GetTrinkets(1) end))"
            " print('B343 gtargerr=' .. err(function() return ic:GetTrinkets(1) end))";
        std::snprintf(script, sizeof(script), "%s", s);
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b343.lua");
    static_cast<void>(result);
    return 0;
}
'''

#: `Entity` 上另外两格 `ColorMod` 的偏移 —— 本批**不读**它们，只在夹具里摆成不同的值。
#: ★ 值来自 `docs/取证-I组-GetColor离线定案尝试-20261004c.md`（`+0x220` = Lua `Entity.Color`
#: 属性、`+0x24C` = `SplatColor`）。它们**不是**本批的落地件（不引常量），只作为夹具对照。
ENTITY_DEFAULT_COLOR_OFFSET = 0x220
ENTITY_SPLAT_COLOR_OFFSET = 0x24C


class Batch343ColorAndListsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b343-")
        source = HARNESS
        for token, value in (
            ("CURRENT_TINT_0", repr(CURRENT_TINT[0])),
            ("CURRENT_TINT_1", repr(CURRENT_TINT[1])),
            ("CURRENT_TINT_2", repr(CURRENT_TINT[2])),
            ("CURRENT_TINT_3", repr(CURRENT_TINT[3])),
            ("CURRENT_SHIFT_0", repr(CURRENT_SHIFT[0])),
            ("CURRENT_SHIFT_1", repr(CURRENT_SHIFT[1])),
            ("CURRENT_SHIFT_2", repr(CURRENT_SHIFT[2])),
            ("DEFAULT_TINT_0", repr(DEFAULT_TINT[0])),
            ("DEFAULT_TINT_1", repr(DEFAULT_TINT[1])),
            ("DEFAULT_TINT_2", repr(DEFAULT_TINT[2])),
            ("DEFAULT_TINT_3", repr(DEFAULT_TINT[3])),
            ("SPLAT_TINT_0", repr(SPLAT_TINT[0])),
            ("SPLAT_TINT_1", repr(SPLAT_TINT[1])),
            ("SPLAT_TINT_2", repr(SPLAT_TINT[2])),
            ("SPLAT_TINT_3", repr(SPLAT_TINT[3])),
            ("COLLECTIBLE_COUNT", str(COLLECTIBLE_COUNT)),
            ("TRINKET_COUNT", str(TRINKET_COUNT)),
            ("ENTITY_DEFAULT_COLOR_OFFSET", hex(ENTITY_DEFAULT_COLOR_OFFSET)),
            ("ENTITY_SPLAT_COLOR_OFFSET", hex(ENTITY_SPLAT_COLOR_OFFSET)),
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

    def test_get_color_reads_the_current_color_cell(self):
        """★★ **真值判据**：`p:GetColor()` 的 7 个分量 = 夹具摆在 **`+0x138`** 那一组。

        ★★ 夹具把 `+0x138`（本 API 读的）/`+0x220`（`Entity.Color` 属性那一格）/`+0x24C`
        （`SplatColor`）摆成**互不相同**的值 ⇒ 读到另外两格会立刻红（这是本条最主要的落地风险）。
        """
        out = self.run_scenario("color")
        self.assertIn("B343 colorfn=function", out)
        self.assertIn("B343 kind=userdata", out)
        self.assertIn(
            f"B343 rgb={CURRENT_TINT[0]:.3f},{CURRENT_TINT[1]:.3f},"
            f"{CURRENT_TINT[2]:.3f},{CURRENT_TINT[3]:.3f}", out)
        self.assertIn(
            f"B343 shift={CURRENT_SHIFT[0]:.3f},{CURRENT_SHIFT[1]:.3f},{CURRENT_SHIFT[2]:.3f}", out)
        #: ★ 反回归：不许读到 `+0x220`（默认色）或 `+0x24C`（SplatColor）那两组。
        self.assertNotIn(f"{DEFAULT_TINT[0]:.3f},{DEFAULT_TINT[1]:.3f}", out)
        self.assertNotIn(f"{SPLAT_TINT[0]:.3f},{SPLAT_TINT[1]:.3f}", out)
        self.assertIn("B343 retn=1", out)

    def test_get_color_returns_a_value_copy_not_a_live_reference(self):
        """★★ **值拷贝判据**：改**句柄自己**的 `.R` 不会影响引擎那一格，再取一次仍是原值。

        PC 的 `GetColor()` **按值返回** `Color` ⇒ 我们每次调用都重新读引擎那一格、
        句柄不持有引擎内存。这条把"值拷贝 vs 活引用"在宿主里分开（真机上几乎不可分）。
        """
        out = self.run_scenario("color")
        self.assertIn("B343 mutated=0.900", out)          # 句柄自己被改了
        self.assertIn(f"B343 again={CURRENT_TINT[0]:.3f}", out)  # 引擎那一格没变
        self.assertIn("B343 sameobj=false", out)          # 两次调用是两个不同的 userdata

    def test_get_color_argument_gate(self):
        """参数闸门：**恰好一个**（就是接收者）；点号显式传 self 也放行。"""
        out = self.run_scenario("color_gate")
        self.assertIn("B343 colorextra=false", out)
        self.assertIn("Entity:GetColor accepts no arguments", out)
        self.assertIn("B343 colordot=true", out)

    def test_the_two_lists_report_their_own_vector(self):
        """★ 两张列表各读**自己的**向量：`.Size` 必须分别等于 2 与 3（夹具故意摆成不同长度）。

        ★ 同时钉住 `Get(i)` 的**0 基**与越界口径（越界/负数 ⇒ `nil`，**不抛错**）。
        """
        out = self.run_scenario("lists")
        self.assertIn("B343 collfn=function", out)
        self.assertIn("B343 kind=userdata/userdata", out)
        self.assertIn(f"B343 sizes={COLLECTIBLE_COUNT},{TRINKET_COUNT}", out)
        self.assertIn("B343 firstkind=userdata/userdata", out)
        self.assertIn("B343 lastkind=userdata/userdata", out)
        self.assertIn("B343 oob=false,false", out)
        self.assertIn("B343 neg=false", out)

    def test_lists_argument_gate(self):
        """参数闸门：两条都**恰好一个**（就是接收者）。"""
        out = self.run_scenario("lists_gate")
        self.assertIn("B343 gcarg=false", out)
        self.assertIn("ItemConfig:GetCollectibles accepts no arguments", out)
        self.assertIn("B343 gtarg=false", out)
        self.assertIn("ItemConfig:GetTrinkets accepts no arguments", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 字段行 / 新 kind / 反向映射助手 / 常量 / 契约页 / 台账引用。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        field_header = FIELD_HEADER.read_text(encoding="utf-8")
        color_header = COLOR_HEADER.read_text(encoding="utf-8")

        for needle in (
            'MakeId(ApiDomain::Isaac, 1, 0x00F3), ApiDomain::Isaac, "Entity", "GetColor"',
            'MakeId(ApiDomain::Isaac, 1, 0x00F4), ApiDomain::Isaac, "ItemConfig", "GetCollectibles"',
            'MakeId(ApiDomain::Isaac, 1, 0x00F5), ApiDomain::Isaac, "ItemConfig", "GetTrinkets"',
        ):
            self.assertIn(needle, catalog, f"目录行缺失：{needle}")

        #: 字段行（`Entity:GetColor`）。
        self.assertRegex(
            api,
            r"\{\s*0x0E0100F3,\s*kEntityGetColorOffset,\s*0,\s*"
            r"FieldKind::ColorModRead,\s*FieldMissing::Zero,\s*FieldReceipt::Entity,\s*0xFF\}",
            "GetColor 的数据行缺失或形状/接收者不对")
        self.assertNotRegex(api, r"0x0E0100F3[^\n]*EngineCallShape")
        #: 两条列表的绑定行。
        self.assertRegex(api, r"\{0x0E0100F4, &ItemConfigGetCollectibles\},")
        self.assertRegex(api, r"\{0x0E0100F5, &ItemConfigGetTrinkets\},")
        #: 两条列表**共用**同一个助手（读错向量那类错法的第一道闸）。
        self.assertEqual(api.count("PushItemConfigList(state,"), 2,
                         "两条列表必须各调一次同一个助手")
        #: 新 kind + 反向映射助手 + 缺省白那一支。
        self.assertIn("ColorModRead = 23,", field_header)
        self.assertIn("PushLuaColorFromEngineColorMod", color_header)
        self.assertRegex(api, r"case FieldKind::ColorModRead:")
        self.assertRegex(api, r"PushMissingFieldValueForRow[\s\S]{0,900}FieldKind::ColorModRead")
        #: ★ 反回归：`ColorModRead` 是**读侧**，不许进 `RowReturnsNoValues`。
        self.assertNotRegex(
            api, r"RowReturnsNoValues\(FieldKind kind\)[\s\S]{0,1500}FieldKind::ColorModRead")
        #: 常量 + 契约页。
        self.assertIn("inline constexpr uintptr_t kEntityGetColorOffset = 0x138;", constants)
        self.assertTrue(CONTRACT_PAGE.is_file(), "ItemConfig.md 没有 vendor 进 tools/pc_contract_docs/")
        self.assertIn(b"GetCollectibles", CONTRACT_PAGE.read_bytes())

    def test_the_contract_page_is_vendored_verbatim(self):
        """★ `ItemConfig.md` 必须是**逐字节** vendor 的（与 `analysis/` 快照一致、5750 字节）。

        `analysis/` 是 gitignore 的 ⇒ 指过去对别人不可做（本项目老规矩）；字节数登记在
        `runtime/tests/contract/test_api_deviation.py` 的 `CONTRACT_PAGE_SIZES` 里。
        """
        self.assertEqual(CONTRACT_PAGE.stat().st_size, 5750)
        snapshot = ROOT / "analysis" / "isaacdocs-snapshot" / "docs" / "ItemConfig.md"
        if snapshot.is_file():
            self.assertEqual(CONTRACT_PAGE.read_bytes(), snapshot.read_bytes(),
                             "vendor 进来的契约页与快照不一致")
        #: 台账引用的两行必须真的是那两条 API 的签名行。
        lines = CONTRACT_PAGE.read_text(encoding="utf-8").splitlines()
        self.assertIn("GetCollectibles", lines[46])
        self.assertIn("GetTrinkets", lines[103])

    def test_the_new_offset_is_registered_in_the_signature_table(self):
        """新常量必须登记进 `engine_symbol_signatures.json`（否则完成定义门禁红）。"""
        table = json.loads(SIGNATURES.read_text(encoding="utf-8"))
        constants = {row["constant"] for row in table}
        self.assertIn("kEntityGetColorOffset", constants)
        #: ★ 反回归：`0x138` 上本来就有别人的条目（`kModEntryUserEnabledFlagOffset`），不许被顶掉。
        self.assertIn("kModEntryUserEnabledFlagOffset", constants)

    def test_the_evidence_is_recorded(self):
        """常量段必须写明 PC 绑定、`SetColor` 逐字同构那三条交叉印证、以及"极易取错"的警告。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        for needle in ("0x138", "0x220", "0x24C", "0xE4", "0x1B0", "0x1DC",
                       "0x4F3DE0", "0x68A380", "0x63B84", "SetColor", "reset_color",
                       "0x2DAD90", "0x2C"):
            self.assertIn(needle, constants, f"证据 {needle} 没有写进常量段")
        self.assertIn("Entity.md", constants)


if __name__ == "__main__":
    unittest.main()
