"""门禁：批次 336（2026-10-03 深夜）—— 交接第八份「批 B/批 C 纯取证批」落地的两条**字段数据行**。

| API | 处 | 契约 | PC 绑定本体 | Switch 那一格 |
| --- | --- | --- | --- | --- |
| `Room:GetTintedRockIdx()` | 1 | `Room.md:561` | `0x427750` = `mov eax,[ecx+0x764]; ret` | **`Room + 0xE90`**（i32） |
| `Entity:CollidesWithGrid()` | 1 | `Entity.md:308` | `0x641420` = `mov al,[ecx+0x188]; ret` | **`Entity + 0x1EC`**（u8） |

## 这一批是什么

**不是"又两条 API"，而是"一次把 7+1 条 `field_row` 全查一遍"的纯取证批** —— 只落地两条
**证据链闭合**的，其余五条的**负结果**写进 `docs/改动日志-20261003.md` 第四十节。
两条都复用现成的 `FieldKind`（`I32` / `Bool`）与现成的 `FieldReceipt`（`Room` / `Entity`）
⇒ **0 字节代码**（本批没开任何新机制）。

## 判据（★ 与引擎方法行不同：字段行**能验到真值**）

字段行**没有入口指纹**，可读性判定退化成"地址非零、长度非零"
（`engine_memory::EngineMemoryReadable` 的宿主分支）⇒ **夹具在伪造块里写的字节，真的会被读出来**
（批次 287 立的判据）。所以这里验的是：
1. **值真的来自那一格**：换一个值 ⇒ 读数跟着变（不是常量、不是别的格）；
2. **接收者解析**：`Room` 那条走"当前房间"（夹具覆写 `ReadCurrentGameRoom`）、
   `Entity` 那条走栈上的玩家句柄；
3. **降级**：拿不到当前房间 ⇒ 答 **0**、**不报错**（PC 那半边没有兜底；同族的
   `GetDecorationSeed`/`GetSpawnSeed` 的口径也是 0）。

★ 没验到的：真机上那一格**确实**是染色石头索引 / 碰撞标志（宿主里夹具与实现引用同一个常量，
自己证不了自己）⇒ 两条都挂真机项（作业单第九节）。
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
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"
LAYOUT_ROOM = ROOT / "tools" / "layout_tables" / "room.json"
LAYOUT_ENTITY = ROOT / "tools" / "layout_tables" / "entity.json"

#: 两个夹具用的值（**故意互不相同**：换值还能读对 ⇒ 证明是"读那一格"，不是常量）。
TINTED_A = 0x00001234
TINTED_B = 0x00005678

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "room_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存：
//   * `Room:GetTintedRockIdx()` 的接收者**不从栈上取** —— 走 `ReadCurrentGameRoom`
//     （下面覆写的那个桩）⇒ 只要一块"房间块"（批次 289 立的做法）；
//   * `Entity:CollidesWithGrid()` 的接收者**从栈上取** —— 走 `Isaac.GetPlayer(0)`，
//     所以还要模块块 + 全局 owner 槽 + 玩家数组 + 假玩家（抄批次 333 的形状）。
namespace {

std::vector<unsigned char> g_RoomBytes;
bool g_RoomAvailable = true;

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::uintptr_t g_EngineBase = 0;

//: ★ 夹具用的两个值（**故意互不相同**）：C++ 侧也要有一份 —— 下面 HARNESS 是 C++ 源码，
//: 看不到 Python 模块级的 `TINTED_A/TINTED_B`。两处由 `test_tinted_rock_index_reads_that_cell`
//: 的断言对齐（断言里用的是 Python 那两个）。
constexpr std::uint32_t kTintedA = 0x00001234;
constexpr std::uint32_t kTintedB = 0x00005678;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeWorld() {
    //: ★ 房间块要盖住要读的那一格（`Room + kRoomTintedRockIdxOffset`，i32）。
    static_assert(kRoomTintedRockIdxOffset + sizeof(std::uint32_t) <= 0xE98,
                  "the fake room block must cover the tinted-rock-index cell");
    g_RoomBytes.assign(0xE98, 0);

    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    //: ★ `Entity + kEntityCollidesWithGridOffset` 那一格也要在块里（u8）。
    static_assert(kEntityCollidesWithGridOffset + sizeof(std::uint8_t) <= kEntityPlayerSize,
                  "the fake player block must cover the collides-with-grid cell");
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + sizeof(std::uint64_t));

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

//: ★★ 批次 289 立的做法：`FieldReceipt::Room` 的接收者**不从 Lua 栈上取**，走这个函数
//: ⇒ 宿主里覆写它就能让"当前房间"指向我们的伪造块（而且 `Game:GetRoom` 也走同一条）。
GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    if (!g_RoomAvailable) {
        *room = nullptr;
        return GameRoomObservation::GameNull;
    }
    *room = g_RoomBytes.data();
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    const bool known = std::strcmp(scenario, "tinted_a") == 0 ||
                       std::strcmp(scenario, "tinted_b") == 0 ||
                       std::strcmp(scenario, "noroom") == 0 ||
                       std::strcmp(scenario, "collides_false") == 0 ||
                       std::strcmp(scenario, "collides_true") == 0;
    if (!known) return 91;

    PublishFakeWorld();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    //: 场景各自的初值（★ 两个 tinted 场景用**不同**的值 ⇒ 换值还能读对才说明是"读那一格"）。
    if (std::strcmp(scenario, "tinted_a") == 0) {
        WriteAt<std::uint32_t>(g_RoomBytes, kRoomTintedRockIdxOffset, kTintedA);
    } else if (std::strcmp(scenario, "tinted_b") == 0) {
        WriteAt<std::uint32_t>(g_RoomBytes, kRoomTintedRockIdxOffset, kTintedB);
    } else if (std::strcmp(scenario, "noroom") == 0) {
        g_RoomAvailable = false;
    } else if (std::strcmp(scenario, "collides_true") == 0) {
        WriteAt<std::uint8_t>(g_PlayerBytes, kEntityCollidesWithGridOffset, 1);
    }

    std::string script =
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local p = Isaac.GetPlayer(0)\n"
        "local room = Game():GetRoom()\n"
        "print('B336 p=' .. type(p) .. ' room=' .. type(room))\n"
        "print('B336 tintedfn=' .. type(room and room.GetTintedRockIdx))\n"
        "print('B336 collidesfn=' .. type(p and p.CollidesWithGrid))\n";
    if (std::strcmp(scenario, "collides_false") == 0 ||
        std::strcmp(scenario, "collides_true") == 0) {
        script +=
            "local good, value = pcall(function() return p:CollidesWithGrid() end)\n"
            "print('B336 ok=' .. tostring(good))\n"
            "print('B336 value=' .. tostring(value))\n";
    } else {
        script +=
            "local good, value = pcall(function() return room:GetTintedRockIdx() end)\n"
            "print('B336 ok=' .. tostring(good))\n"
            "print('B336 value=' .. tostring(value))\n";
    }

    const char* text = script.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(text, std::strlen(text), "@b336.lua");
    static_cast<void>(result);
    return 0;
}
'''


class FieldRowsBatch336Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b336-")
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
        # ★ 批次 285 的教训：stderr 也要一起回。
        return result.stdout + result.stderr

    @staticmethod
    def value(out, label):
        match = re.search(rf"^{re.escape(label)}=(\S+)$", out, re.M)
        if match is None:
            raise AssertionError(f"输出里没有 {label} 那一行：\n{out}")
        return match.group(1)

    # ---------------------------------------------------------------- 行为（宿主）

    def test_tinted_rock_index_reads_that_cell(self):
        """★ 换一个值 ⇒ 读数跟着变 ⇒ 真的是"读 `Room + 0xE90`"，不是常量也不是别的格。"""
        a = self.run_scenario("tinted_a")
        self.assertIn("B336 p=userdata room=userdata", a)
        self.assertIn("B336 tintedfn=function", a)
        self.assertIn("B336 ok=true", a)
        self.assertEqual(int(self.value(a, "B336 value")), TINTED_A, a)

        b = self.run_scenario("tinted_b")
        self.assertEqual(int(self.value(b, "B336 value")), TINTED_B, b)
        self.assertNotEqual(TINTED_A, TINTED_B)

    def test_collides_with_grid_reads_that_byte(self):
        """★ u8 那格：写 0 ⇒ `false`、写 1 ⇒ `true`（`FieldKind::Bool` = 读字节、非零即真）。"""
        off = self.run_scenario("collides_false")
        self.assertIn("B336 collidesfn=function", off)
        self.assertIn("B336 ok=true", off)
        self.assertEqual(self.value(off, "B336 value"), "false", off)

        on = self.run_scenario("collides_true")
        self.assertIn("B336 ok=true", on)
        self.assertEqual(self.value(on, "B336 value"), "true", on)

    def test_missing_room_degrades_to_zero_without_erroring(self):
        """拿不到"当前房间" ⇒ 答 0、**不报错**（PC 那半边没有兜底；同族口径也是 0）。"""
        out = self.run_scenario("noroom")
        self.assertIn("B336 ok=true", out)
        self.assertEqual(int(self.value(out, "B336 value")), 0, out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """两条常量 + 两行数据 + 两条目录 id + 布局表两行 + 编译期钉死不漂移。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        field_rows = ISAAC_API.read_text(encoding="utf-8")
        room_rows = REMAINING_API.read_text(encoding="utf-8")
        catalog = CATALOG.read_text(encoding="utf-8")
        room_table = LAYOUT_ROOM.read_text(encoding="utf-8")
        entity_table = LAYOUT_ENTITY.read_text(encoding="utf-8")

        self.assertIn("kRoomTintedRockIdxOffset = 0xE90", constants)
        self.assertIn("kEntityCollidesWithGridOffset = 0x1EC", constants)
        self.assertRegex(
            room_rows,
            r"\{0x04010037, kRoomTintedRockIdxOffset, 0, FieldKind::I32, FieldMissing::Zero,\s*\n"
            r"\s*FieldReceipt::Room, 0xFF\}")
        self.assertRegex(
            field_rows,
            r"\{0x0E0100E9, kEntityCollidesWithGridOffset, 0, FieldKind::Bool, "
            r"FieldMissing::False,\s*\n\s*FieldReceipt::Entity, 0xFF\}")
        self.assertRegex(catalog, r"MakeId\(ApiDomain::Room, 1, 0x0037\).*\"GetTintedRockIdx\"")
        self.assertRegex(catalog, r"MakeId\(ApiDomain::Isaac, 1, 0x00E9\).*\"CollidesWithGrid\"")
        #: ★ 布局表两行（字段行的偏移必须来自布局表）。
        self.assertIn('"name": "TintedRockIdx"', room_table)
        self.assertIn('"name": "CollidesWithGrid"', entity_table)
        self.assertIn('"confidence": "confirmed"', room_table)
        self.assertIn('"confidence": "confirmed"', entity_table)
        #: ★ 编译期钉死：手写常量必须与布局表生成物一致（值写两遍不许漂移）。
        self.assertIn("kRoomTintedRockIdxOffset == layout::kRoomTintedRockIdxOffset", room_rows)
        self.assertIn("kEntityCollidesWithGridOffset == layout::kEntityCollidesWithGridOffset",
                      field_rows)


if __name__ == "__main__":
    unittest.main()
