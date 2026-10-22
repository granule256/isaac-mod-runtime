"""门禁：`Room:GetGridEntityFromPos(Vector)`（批次 307，2026-10-03）。

## 这一条是什么

| API | 契约 | 语料调用点 |
| --- | --- | --- |
| `Room:GetGridEntityFromPos(Vector Position)` | `Room.md:352/354`（★ 同页带 `data-altreturn='nil'`） | 4 |

★ 谁在调：`IsaacOnTwitchReloaded` 用固定位置 `Vector(510, 370)` 找按钮、还有一处 `== nil` 判断与
一个 `while … == nil and room:IsPositionInRoom(...)` 的寻路循环；`BOIStageAPI15` 拿 `door.Position` 找门；
`ChallengeAPI` 在踩板子时找格子上的实体。**返回 nil 会让它们的分支静默走错**。

## ★★ 它是"两个已经有的机制"的合成 —— 本条零新增引擎偏移

1. **世界坐标 → 格坐标**：PC 的绑定本体（`0x447F80`）把这段算术**内联**了 ——
   `xmm1=[0xb6aa3c]=40.0f`、`xmm2=[0xb6a480]=0.5f` ⇒ `gx=(int)((pos.x−40)/40+0.5)`（`cvttss2si` 向零截断）；
   `[0xb6ab20]=**120.0f**`（★ y 的起点不是 40）⇒ `gy=(int)((pos.y−120)/40+0.5)`；
   边界 `[ecx+0xC]`/`[ecx+0x10]`（宽/高）；`index = 宽*gy + gx`。
   ★★★ **同一套算术在 Switch 侧有独立符号**：`Room::GetGridIndex(Vector2 const&) @ 0x459E3C`
   （`fmov` 出来的常量正是 -40.0f / 40.0f / 0.5f / -120.0f，收尾 `madd w8,w11,w10,w9`）
   —— 而那段我们**早就**复刻成了 `RoomGridCoordinateFromWorld`（`Room:GetGridIndex` 用的就是它）。
2. **按格下标读网格实体表**：与 `Room:GetGridEntity(index)` **同一张表**
   （`Room + kRoomGridEntityTableOffset`，PC 表头在 `+0x24`、Switch 在 `+0x30`，**不许平移**）
   ⇒ 本批把它抽成共享的 `PushGridEntityAtSlot`，两个 handler 共用一份。

## 宿主验到了什么、没验到什么

* **验到**（夹具把假房间的 13×7 个格子各摆一个**不同的**假网格实体，实体自己的 `+0x08`
  存着互不相同的 `Type`）：
  - ★★ **每一格的格心坐标问回去，必须命中那一格的实体**（用 `ge:GetType()` 读回来比 ——
    这比"不是 nil"强得多：**取错格**会红）；
  - ★★ **四舍五入的边界**：格心 ±19 像素仍落在本格、±21 像素落到邻格（这正是 `+0.5` 再截断的语义）；
  - **空槽位 ⇒ `nil`**（不是 `false`、不报错）；**房间外 ⇒ `nil`**；**拿不到房间 ⇒ `nil`**；
  - **参数闸门**：0 个 / 数字 / 表都报错，消息形如 `Room:GetGridEntityFromPos accepts one Vector`。
* **没验**：真机上"格心坐标"就是引擎认的那一套（宿主里 `(x−40)/40+0.5` 是照 PC 本体与
  Switch 的 `Room::GetGridIndex` 复刻的，两边都核过，但真机读数才作数）⇒ 真机项 = 作业单 **V57**。
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
REMAINING = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: 域内序号 / owner / 名字 / 契约页:行 / 绑定行 id。
API_INDEX = 0x0033
BINDING_ID = 0x04010033
CONTRACT = "Room.md:352/354"

#: 标准房间 13×7（与真机一致，也是 `Room:GetGridSize` 的注释里那个数）。
GRID_WIDTH = 13
GRID_HEIGHT = 7
CELL = 40.0
ORIGIN_X = 40.0
ORIGIN_Y = 120.0
#: 故意留空的槽位（验"空项 ⇒ nil"）。
EMPTY_SLOTS = (0, 5)
#: 每个假网格实体的 `Type` 值（互不相同 ⇒ 取错格必红）。`0x100 + index`。
TYPE_BASE = 0x100


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存：
//   g_RoomBytes[+0x14] = 宽、[+0x18] = 高、[+0x30 + 8*i] = 第 i 格的网格实体指针
//   每个假网格实体是独立一块内存，`+0x08`（`kGridEntityTypeOffset`）存一个互不相同的 Type
//   ★ 夹具**不引用** `Room:GetGridEntityFromPos` 自己的任何常量（那条 API 的常量是
//     `kRoomGridEntityTableOffset` / `kRoomGridWidthOffset` / `kRoomGridHeightOffset` ——
//     这些是**既有** API 的偏移，这里只用来"把假房间摆成引擎的样子"，
//     而**被测的那一步（坐标换算）**用的是写死在脚本里的格心坐标 ⇒ 不存在"夹具与实现一起漂"）。
namespace {

constexpr std::uint32_t kWidth = GRID_WIDTH_VALUE;
constexpr std::uint32_t kHeight = GRID_HEIGHT_VALUE;
constexpr std::uint32_t kCellCount = kWidth * kHeight;
constexpr std::size_t kEntityStride = 0x50;

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_EntityBytes;
bool g_RoomAvailable = true;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

std::uintptr_t EntityAddress(std::uint32_t index) {
    return AddressOf(g_EntityBytes) + index * kEntityStride;
}

void PublishFakeRoom() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EntityBytes.assign(kCellCount * kEntityStride, 0);
    g_RoomBytes.assign(kRoomGridEntityTableOffset + kCellCount * sizeof(std::uintptr_t) + 8, 0);

    WriteAt<std::uint32_t>(g_RoomBytes, kRoomGridWidthOffset, kWidth);
    WriteAt<std::uint32_t>(g_RoomBytes, kRoomGridHeightOffset, kHeight);
    for (std::uint32_t index = 0; index < kCellCount; ++index) {
        //: ★ Type 用 0x100 + index —— 互不相同，取错格一个都藏不住。
        WriteAt<std::uint32_t>(g_EntityBytes, index * kEntityStride + kGridEntityTypeOffset,
                               TYPE_BASE_VALUE + index);
    }
    for (std::uint32_t slot : EMPTY_SLOT_LIST) {
        WriteAt<std::uintptr_t>(g_RoomBytes,
                               kRoomGridEntityTableOffset + slot * sizeof(std::uintptr_t), 0);
    }
    for (std::uint32_t index = 0; index < kCellCount; ++index) {
        bool empty = false;
        for (std::uint32_t slot : EMPTY_SLOT_LIST) {
            if (slot == index) empty = true;
        }
        if (empty) continue;
        WriteAt<std::uintptr_t>(g_RoomBytes,
                               kRoomGridEntityTableOffset + index * sizeof(std::uintptr_t),
                               EntityAddress(index));
    }

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
    LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    if (!g_RoomAvailable) {
        *room = nullptr;
        return GameRoomObservation::GameNull;
    }
    *room = reinterpret_cast<void*>(AddressOf(g_RoomBytes));
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    if (std::strcmp(scenario, "nogame") == 0) g_RoomAvailable = false;
    PublishFakeRoom();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    // 每一格的**格心坐标**：x = 40 + 40*gx、y = 120 + 40*gy（由 PC 本体与 Switch 的
    // `Room::GetGridIndex @ 0x459E3C` 两边的常量 -40.0/40.0/0.5/-120.0 推出来）。
    static const char* kCells =
        "local room = Game():GetRoom()"
        " local parts = {}"
        " for gy = 0, GY_MAX do"
        "   for gx = 0, GX_MAX do"
        "     local p = Vector(40 + 40 * gx, 120 + 40 * gy)"
        "     local ge = room:GetGridEntityFromPos(p)"
        "     if ge == nil then parts[#parts + 1] = '-'"
        "     else parts[#parts + 1] = tostring(ge:GetType()) end"
        "   end"
        " end"
        " print('B307 cells=' .. table.concat(parts, ','))"
        " print('B307 kind=' .. type(room:GetGridEntityFromPos(Vector(80, 120))))";
    // 四舍五入的边界：以格 (3,2) 的格心 (160,200) 为中心，±19 / ±21 像素。
    static const char* kBounds =
        "local room = Game():GetRoom()"
        " local function t(x, y) local ge = room:GetGridEntityFromPos(Vector(x, y))"
        "   if ge == nil then return '-' end return tostring(ge:GetType()) end"
        " print('B307 xm21=' .. t(160 - 21, 200))"
        " print('B307 xm19=' .. t(160 - 19, 200))"
        " print('B307 xp19=' .. t(160 + 19, 200))"
        " print('B307 xp21=' .. t(160 + 21, 200))"
        " print('B307 ym21=' .. t(160, 200 - 21))"
        " print('B307 ym19=' .. t(160, 200 - 19))"
        " print('B307 yp19=' .. t(160, 200 + 19))"
        " print('B307 yp21=' .. t(160, 200 + 21))"
        // 房间外（明确越界）：左/上给明显为负的坐标、右/下越过宽高。
        " print('B307 farleft=' .. t(-200, 200))"
        " print('B307 fartop=' .. t(160, -200))"
        " print('B307 farright=' .. t(40 + 40 * 13 + 40, 200))"
        " print('B307 farbottom=' .. t(160, 120 + 40 * 7 + 40))";
    static const char* kArgs =
        "local room = Game():GetRoom()"
        " local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function msg(f) return tostring(select(2, pcall(f))) end"
        " print('B307 noargs=' .. ok(function() return room:GetGridEntityFromPos() end))"
        " print('B307 noargsmsg=' .. msg(function() return room:GetGridEntityFromPos() end))"
        " print('B307 twoargs=' .. ok(function() return room:GetGridEntityFromPos(Vector(1, 1), 2) end))"
        " print('B307 number=' .. ok(function() return room:GetGridEntityFromPos(1) end))"
        " print('B307 table=' .. ok(function() return room:GetGridEntityFromPos({}) end))"
        " print('B307 okone=' .. ok(function() return room:GetGridEntityFromPos(Vector(40, 120)) end))";
    static const char* kNoGame =
        "local ok, room = pcall(function() return Game():GetRoom() end)"
        " print('B307 nogame_get=' .. tostring(ok) .. ' kind=' .. type(room))"
        " local called, ge = pcall(function() return room:GetGridEntityFromPos(Vector(160, 200)) end)"
        " print('B307 nogame_ok=' .. tostring(called) .. ' val=' .. tostring(ge) .. ' t=' .. type(ge))";

    const char* script = nullptr;
    if (std::strcmp(scenario, "cells") == 0) {
        script = kCells;
    } else if (std::strcmp(scenario, "bounds") == 0) {
        script = kBounds;
    } else if (std::strcmp(scenario, "args") == 0) {
        script = kArgs;
    } else if (std::strcmp(scenario, "nogame") == 0) {
        script = kNoGame;
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b307.lua");
    static_cast<void>(result);
    return 0;
}
'''
HARNESS = (HARNESS
           .replace("GRID_WIDTH_VALUE", str(GRID_WIDTH))
           .replace("GRID_HEIGHT_VALUE", str(GRID_HEIGHT))
           .replace("GX_MAX", str(GRID_WIDTH - 1))
           .replace("GY_MAX", str(GRID_HEIGHT - 1))
           .replace("TYPE_BASE_VALUE", hex(TYPE_BASE))
           .replace("EMPTY_SLOT_LIST", "{" + ", ".join(str(s) for s in EMPTY_SLOTS) + "}"))


class RoomGridEntityFromPosBatch307Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b307-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    @staticmethod
    def value(out, label):
        match = re.search(rf"^{re.escape(label)}=(\S+)$", out, re.M)
        if match is None:
            raise AssertionError(f"输出里没有 {label} 那一行：\n{out}")
        return match.group(1)

    # ---------------------------------------------------------------- 行为（宿主）

    def test_every_cell_centre_resolves_to_that_cells_entity(self):
        """★★ 逐格问回去：每格的**格心坐标**必须命中**那一格**的实体。

        夹具给每个假网格实体的 `+0x08` 存了互不相同的 `Type`（`0x100 + index`）⇒
        用 `ge:GetType()` 读回来比 —— **取错格**（错位/错行/漏乘宽）会立刻红，
        这比"返回值不是 nil"强得多。★ 空槽位那两格应当是 `-`（nil）。
        """
        out = self.run_scenario("cells")
        got = self.value(out, "B307 cells").split(",")
        self.assertEqual(len(got), GRID_WIDTH * GRID_HEIGHT)
        expected = []
        for gy in range(GRID_HEIGHT):
            for gx in range(GRID_WIDTH):
                index = gy * GRID_WIDTH + gx
                expected.append("-" if index in EMPTY_SLOTS else str(TYPE_BASE + index))
        self.assertEqual(got, expected)
        #: 命中时是 `userdata`（句柄），不是数字 —— 顺带钉住类型。
        self.assertEqual(self.value(out, "B307 kind"), "userdata")

    def test_rounding_boundary_is_plus_half_then_truncate(self):
        """★★ `+0.5` 再向零截断 = **四舍五入到最近格心** ⇒ 格心 ±19 仍在本格、±21 落到邻格。

        以格 `(3,2)` 的格心 `(160, 200)` 为中心：
          * `x = 139`（−21）⇒ `(139−40)/40+0.5 = 2.975` ⇒ `gx = 2`（**左邻格**）；
          * `x = 141`（−19）⇒ `3.025` ⇒ `gx = 3`（本格）；
          * `x = 179`（+19）⇒ `3.975` ⇒ `gx = 3`；`x = 181`（+21）⇒ `4.025` ⇒ `gx = 4`（右邻格）。
          * y 同理（中心 `200`）。
        ★ 把 `+0.5` 去掉、或把截断改成向下取整，都会让其中两条红。
        """
        out = self.run_scenario("bounds")
        at = lambda gx, gy: str(TYPE_BASE + gy * GRID_WIDTH + gx)  # noqa: E731
        self.assertEqual(self.value(out, "B307 xm21"), at(2, 2))
        self.assertEqual(self.value(out, "B307 xm19"), at(3, 2))
        self.assertEqual(self.value(out, "B307 xp19"), at(3, 2))
        self.assertEqual(self.value(out, "B307 xp21"), at(4, 2))
        self.assertEqual(self.value(out, "B307 ym21"), at(3, 1))
        self.assertEqual(self.value(out, "B307 ym19"), at(3, 2))
        self.assertEqual(self.value(out, "B307 yp19"), at(3, 2))
        self.assertEqual(self.value(out, "B307 yp21"), at(3, 3))

    def test_outside_the_room_is_nil(self):
        """★ 房间外（明显越界）⇒ **`nil`**、不报错（契约 `data-altreturn='nil'`）。

        ★ 注意 `(0,0)` 附近**不是**越界：`(0−40)/40+0.5 = -0.5` 向零截断是 `0` ——
        这正是我们要与 PC 一致的那条（`cvttss2si` 也是向零截断），所以这里用**明显为负**的坐标。
        """
        out = self.run_scenario("bounds")
        for label in ("B307 farleft", "B307 fartop", "B307 farright", "B307 farbottom"):
            with self.subTest(label=label):
                self.assertEqual(self.value(out, label), "-")

    def test_argument_gate(self):
        """参数闸门：恰好一个 `Vector`；消息里现拼出方法名。合法的一次调用必须放行。"""
        out = self.run_scenario("args")
        self.assertIn("B307 noargs=false", out)
        self.assertIn("Room:GetGridEntityFromPos accepts one Vector", out)
        self.assertIn("B307 twoargs=false", out)
        self.assertIn("B307 number=false", out)
        self.assertIn("B307 table=false", out)
        self.assertIn("B307 okone=true", out)

    def test_missing_room_is_nil_without_erroring(self):
        """★ 拿不到当前房间 ⇒ **`nil`、不报错**（与 `Room:GetGridEntity` 同口径）。"""
        out = self.run_scenario("nogame")
        self.assertIn("B307 nogame_get=true", out)
        #: 房间句柄仍然拿得到（`Room` 是占位句柄），但**读不出现房 ⇒ 答 nil**。
        self.assertIn("B307 nogame_get=true kind=userdata", out)
        self.assertIn("B307 nogame_ok=true val=nil t=nil", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / **复用两套既有机制**（不许抄第二份）。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        self.assertIn(
            f'MakeId(ApiDomain::Room, 1, 0x{API_INDEX:04X}), ApiDomain::Room, "Room", '
            f'"GetGridEntityFromPos"',
            catalog, "目录里没有 Room:GetGridEntityFromPos")
        self.assertIn(f"{{0x{BINDING_ID:08X}, &RoomGetGridEntityFromPos}}", remaining,
                      "绑定表里没有 0x04010033 → RoomGetGridEntityFromPos")
        self.assertIn(CONTRACT, catalog, f"目录行的注释里没有引用契约 {CONTRACT}")

        #: ★★ 复用「世界坐标 → 格坐标」与「按格下标读表」这两份既有实现 —— 抽成共享助手。
        block = remaining[remaining.index("int RoomGetGridEntityFromPos(lua_State* state) {"):]
        block = block[:block.index("\n}\n")]
        self.assertIn("RoomGridCoordinateFromWorld", block, "必须复用既有的坐标换算")
        self.assertIn("ReadRoomGridDimensions", block, "必须复用既有的网格尺寸读取")
        self.assertIn("PushGridEntityAtSlot", block, "必须复用抽出来的读表助手")
        #: ★ `Room:GetGridEntity(index)` 也改用同一个助手（否则就是两份实现）。
        existing = remaining[remaining.index("int RoomGetGridEntity(lua_State* state) {"):]
        existing = existing[:existing.index("\n}\n")]
        self.assertIn("PushGridEntityAtSlot", existing,
                      "`Room:GetGridEntity` 也要走同一个助手（同一件事不写两遍）")
        #: ★ 反回归：不许在这一条里自己写坐标算术（常量必须是复用来的）。
        self.assertNotIn("40.0F", block)
        self.assertNotIn("120.0F", block)

        #: 本批**没有**新增 `k…Offset` ⇒ 常量段里那几个都还是既有值。
        self.assertRegex(constants, r"kRoomGridEntityTableOffset\s*=\s*0x30;")
        self.assertRegex(constants, r"kRoomGridWidthOffset\s*=\s*0x14;")
        self.assertRegex(constants, r"kRoomGridHeightOffset\s*=\s*0x18;")


if __name__ == "__main__":
    unittest.main()
