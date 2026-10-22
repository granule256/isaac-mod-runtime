"""门禁：`Room:IsDoorSlotAllowed(DoorSlot)`（批次 327，2026-10-03）。

## 这一条是什么

| API | 契约 | 引擎侧 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Room:IsDoorSlotAllowed(DoorSlot)` | `Room.md:655` | `RoomConfig::Room.Doors`（`Data + 0x40`，**8 字节位掩码**） | 字段行 `BoolBitArrayOfArg`（`offset2` = 元素宽度 8）/ 降级 `False` | 2 处（`IsaacOnTwitchReloaded`）|

**语义**（契约原文）："Returns whether or not the supplied door slot is valid for the current room.
This is contingent on the room definition in the STB/XML file. ... The value returned by this
method is **independent of whether or not a door currently exists** at the given slot."
⇒ 读的是 **房间定义（XML）里的门位掩码**，不是运行时那份。

**PC 的标尺**（绑定本体 `0x58BFD0`，逐字）：
`lea eax,[ecx+1]; cmp eax,8; ja false` → `[room+0x4]`（描述符）→ `[.+0x10]`（`Data`）→
`test dword [edx + 4*(Slot>>5) + 0x38], 1<<(Slot&31)`。那一格的正式名字是
`RoomConfig::Room.Doors`（`analysis/isaacdocs-snapshot/docs/RoomConfig_Room.md:29`：
`LEFT0 = 1 << DoorSlot.LEFT0` … `DOWN1 = 1 << DoorSlot.DOWN1`）。

**Switch 侧为什么是 `Data+0x40`**（四条独立证据，全在 `runtime_constants.hpp` 的批次 327 段）：
`Level::precalc_allowed_doors` 按门位逐位测它、`Level::get_room_neighbor_pos(int,eDoorSlot)`
函数名即语义、`Room::TrySpawnSecretExitEbb` 把"配置掩码 → 运行时掩码"的先后关系写死、
另有十余处门逻辑同形。

## 宿主验到了什么、没验到什么

* **验到**：
  - ★★ **读的是"实参指定的那一位"**：掩码摆成 `0x89`（bit0/3/7）⇒ 该真的真、该假的假，
    换个掩码（`swap` 只留 bit2）结论跟着换 ⇒ "读错位"必红；
  - ★★ **走对了"房间 → 描述符 → 配置对象"这条两跳**：房间块与描述符块的**同一偏移**
    各摆一个相反的诱饵（全 1 / 全 0），描述符 `+0x20`（运行时 `AllowedDoors`）也摆全 1
    ⇒ 少走一跳、或误用运行时那一格，都会红；
  - **链上任一环为空 ⇒ 答 `false`、不抛错**（三种断法各验一遍）；
  - **越界实参**（`-1` / `8`）⇒ `false`、不抛错；
  - 参数闸门：不给实参 / 给非整数 / 多给 ⇒ 报错（消息里有 API 名）；
    点号 + 显式 self 也是 1 个实参 ⇒ 放行。
* **没验**：
  1. 真机上 `Data+0x40` 是不是就是 `RoomConfig::Room.Doors`（宿主里"偏移对不对"是常量与行
     两处引用同一个值，自己证不了自己）⇒ 真机项见作业单第九节。
  2. `Slot ≥ 64` 的越界行为（会落到下一个 8 字节元素 `Data+0x48`）—— 契约域（`DoorSlot`）
     之外，沿用既有 `BoolBitArrayOfArg` 的口径，见数据行注释。
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
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
LAYOUT = ROOT / "tools" / "layout_tables" / "room_descriptor.json"
LAYOUT_HEADER = ROOT / "runtime" / "source" / "room_descriptor_layout.hpp"

#: 夹具里的门位掩码（**两场互补**）：
#: `doors` = bit0 + bit3 + bit7（该真的真、该假的假，跨了低字节的两端）；
#: `swap`  = 只留 bit2 ⇒ 若实现"读错位"（例如恒测 bit0）就会红。
MASK_DOORS = (1 << 0) | (1 << 3) | (1 << 7)
MASK_SWAP = 1 << 2

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "room_descriptor_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存：**三层**（与批次 290 的 `RoomConfigData` 用例同形）
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                        = &g_RoomBytes（"当前房间"）
//   g_RoomBytes   [kRoomDescriptorPointerOffset]          = &g_DescriptorBytes（① 描述符）
//   g_DescriptorBytes[layout::kRoomDescriptorDataOffset]  = &g_ConfigBytes（② 配置对象）
//   g_ConfigBytes [kRoomConfigDoorsOffset]                = 门位掩码（③ 值就在这一格，8 字节）
//
// ★★ 三块在**同一个偏移**（`+0x40`）上各摆一个不同/相反的值：
//   房间块 = 全 1（0xFF，每一位都"允许"）、描述符块 = 全 0，只有配置块是真掩码。
//   ⇒ 少走第一跳 ⇒ 全 true（`s1` 该 false ⇒ 红）；少走第二跳 ⇒ 全 false（`s0` 该 true ⇒ 红）。
// ★ 再加一个诱饵：描述符 `+0x20`（运行时的 `AllowedDoors`）也摆全 1 ⇒ 误用运行时那一格必红。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_DescriptorBytes;
std::vector<unsigned char> g_ConfigBytes;
bool g_RoomAvailable = true;
bool g_DescriptorAvailable = true;
bool g_DataAvailable = true;
std::uintptr_t g_EngineBase = 0;

//: 门位掩码（与 Python 侧的 `MASK_DOORS` / `MASK_SWAP` 是同一组值 —— 那边只用于断言里说明）。
constexpr std::uint64_t kMaskDoors = (1ULL << 0) | (1ULL << 3) | (1ULL << 7);
constexpr std::uint64_t kMaskSwap = (1ULL << 2);

constexpr std::size_t kBlockSize = 0x80;
static_assert(kRoomDescriptorPointerOffset + sizeof(std::uint64_t) <= kBlockSize,
              "fake room block must hold the descriptor pointer");
static_assert(isaac::runtime::layout::kRoomDescriptorDataOffset + sizeof(std::uint64_t) <= kBlockSize,
              "fake descriptor block must hold the Data pointer");
static_assert(kRoomConfigDoorsOffset + sizeof(std::uint64_t) <= kBlockSize,
              "fake config block must hold the door mask");
static_assert(isaac::runtime::layout::kRoomDescriptorAllowedDoorsOffset + sizeof(std::uint64_t)
                  <= kBlockSize,
              "fake descriptor block must also hold the runtime AllowedDoors decoy");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeRoom() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_RoomBytes.assign(kBlockSize, 0);
    g_DescriptorBytes.assign(kBlockSize, 0);
    g_ConfigBytes.assign(kBlockSize, 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset,
                           AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
    if (g_DescriptorAvailable) {
        WriteAt<std::uint64_t>(g_RoomBytes, kRoomDescriptorPointerOffset,
                               AddressOf(g_DescriptorBytes));
    }
    if (g_DataAvailable) {
        WriteAt<std::uint64_t>(g_DescriptorBytes,
                               isaac::runtime::layout::kRoomDescriptorDataOffset,
                               AddressOf(g_ConfigBytes));
    }
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

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
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    std::uint64_t mask = kMaskDoors;
    if (std::strcmp(scenario, "doors") == 0) {
        mask = kMaskDoors;
    } else if (std::strcmp(scenario, "swap") == 0) {
        mask = kMaskSwap;
    } else if (std::strcmp(scenario, "nodesc") == 0) {
        g_DescriptorAvailable = false;
    } else if (std::strcmp(scenario, "nodata") == 0) {
        g_DataAvailable = false;
    } else if (std::strcmp(scenario, "noroom") == 0) {
        g_RoomAvailable = false;
    } else {
        return 91;
    }

    PublishFakeRoom();
    // ★ 三个诱饵（都在 `+0x40` 或运行时那一格上，与真掩码相反/不同）。
    WriteAt<std::uint64_t>(g_RoomBytes, kRoomConfigDoorsOffset, 0xFFULL);
    WriteAt<std::uint64_t>(g_DescriptorBytes, kRoomConfigDoorsOffset, 0x00ULL);
    WriteAt<std::uint64_t>(g_DescriptorBytes,
                           isaac::runtime::layout::kRoomDescriptorAllowedDoorsOffset, 0xFFULL);
    // 真值只写在**配置对象**那一格。
    WriteAt<std::uint64_t>(g_ConfigBytes, kRoomConfigDoorsOffset, mask);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local room = Game():GetRoom()"
        " print('B327 roomkind=' .. type(room))"
        " print('B327 fn=' .. type(room.IsDoorSlotAllowed))"
        " local first"
        " for i = 0, 7 do"
        "   local v = room:IsDoorSlotAllowed(i)"
        "   if i == 0 then first = v end"
        "   print('B327 s' .. i .. '=' .. tostring(v))"
        " end"
        " print('B327 kind=' .. type(first))"
        // 越界实参：`-1`（`NO_DOOR_SLOT`）与 `8` 都答 false 且**不抛错**。
        " print('B327 negok=' .. ok(function() return room:IsDoorSlotAllowed(-1) end))"
        " print('B327 neg=' .. tostring(room:IsDoorSlotAllowed(-1)))"
        " print('B327 eight=' .. tostring(room:IsDoorSlotAllowed(8)))"
        // 参数闸门：不给 / 非整数 / 多给都报错；点号 + 显式 self 放行。
        " print('B327 noarg=' .. ok(function() return room:IsDoorSlotAllowed() end))"
        " print('B327 noargerr=' .. err(function() return room:IsDoorSlotAllowed() end))"
        " print('B327 strid=' .. ok(function() return room:IsDoorSlotAllowed('x') end))"
        " print('B327 twoargs=' .. ok(function() return room:IsDoorSlotAllowed(1, 2) end))"
        " print('B327 dotcall=' .. ok(function() return room.IsDoorSlotAllowed(room, 3) end))"
        // 对照：同族老方法（同为字段行、同为两跳链末端）仍照常可用。
        " print('B327 sibling=' .. ok(function() return room:GetRoomShape() end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b327.lua");
    static_cast<void>(result);
    return 0;
}
'''


class DoorSlotAllowedBatch327Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b327-")
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

    # ---------------------------------------------------------------- 行为（宿主）

    def test_each_door_bit_is_read_from_the_argument(self):
        """★★ 掩码 `0x89`（bit0 / bit3 / bit7）⇒ 恰好三位 true，其余 false。

        这条是本文件的核心判据：数据行没挂上 ⇒ `room.IsDoorSlotAllowed` 是 `nil`；
        读错位（例如恒测 bit0）⇒ `s3` / `s7` 会变 false；读错基对象 ⇒ 见下面几条。
        返回值必须是 **boolean**（PC 返回 `boolean`）—— 语料里它直接进 `and` 表达式。
        """
        out = self.run_scenario("doors")
        self.assertIn("B327 roomkind=userdata", out)
        self.assertIn("B327 fn=function", out)
        self.assertIn("B327 kind=boolean", out)
        self.assertIn("B327 s0=true", out)
        self.assertIn("B327 s1=false", out)
        self.assertIn("B327 s2=false", out)
        self.assertIn("B327 s3=true", out)
        self.assertIn("B327 s4=false", out)
        self.assertIn("B327 s5=false", out)
        self.assertIn("B327 s6=false", out)
        self.assertIn("B327 s7=true", out)

    def test_another_mask_moves_the_answers(self):
        """★ 换一场掩码（只留 bit2）⇒ 只有 `s2` 变 true ⇒ 专抓"读错位 / 读错基对象"。

        同一场里房间块（`+0x40` 全 1）与描述符 `+0x20`（运行时 `AllowedDoors`，全 1）
        两个诱饵仍在 —— 它们与真值**相反**，所以走错哪一格都会在这一场被抓到。
        """
        out = self.run_scenario("swap")
        self.assertIn("B327 s2=true", out)
        for slot in (0, 1, 3, 4, 5, 6, 7):
            self.assertIn(f"B327 s{slot}=false", out)

    def test_a_broken_chain_degrades_to_false_without_erroring(self):
        """★★ 链上任一环为空（没有房间 / 描述符指针 0 / `Data` 指针 0）⇒ 答 `false`、不抛错。

        三种断法各验一遍。★ 为什么不抛错：报错会把**整条模组回调**摘掉（批 250 定案），
        比"这次答了个保守值"严重得多；而 `false` 正是 PC 的 `ja` 分支（`xor al,al`）的答案。
        """
        for scenario in ("nodesc", "nodata", "noroom"):
            with self.subTest(scenario=scenario):
                out = self.run_scenario(scenario)
                #: 房间句柄本身仍在（批次 250：给空壳、不给 nil）⇒ 走的是"字段行降级"。
                self.assertIn("B327 roomkind=userdata", out)
                self.assertIn("B327 fn=function", out)
                for slot in range(8):
                    self.assertIn(f"B327 s{slot}=false", out)

    def test_out_of_range_slot_is_false_without_erroring(self):
        """★ `-1`（`NO_DOOR_SLOT`）与 `8` 都答 `false` 且**不抛错**。

        `8` 这一格同时验"越界不会误打到相邻字段"：房间块那一格是全 1（诱饵），
        若实现少走一跳，`s8` 之外的读数早就红了（见上一条）。
        """
        out = self.run_scenario("doors")
        self.assertIn("B327 negok=true", out)
        self.assertIn("B327 neg=false", out)
        self.assertIn("B327 eight=false", out)

    def test_argument_gate_is_exactly_one_integer(self):
        """参数闸门：**必须**给一个整数门位 —— 不给报错、给非整数报错、多给也报错。"""
        out = self.run_scenario("doors")
        self.assertIn("B327 noarg=false", out)
        self.assertIn("Room:IsDoorSlotAllowed expects one integer argument", out)
        self.assertIn("B327 strid=false", out)
        self.assertIn("B327 twoargs=false", out)
        #: 点号 + 显式 self 也是 1 个实参 ⇒ 放行。
        self.assertIn("B327 dotcall=true", out)
        #: 对照：同族老方法仍照常可用 ⇒ 本批没有动到族里别的东西。
        self.assertIn("B327 sibling=true", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与降级档 / 接收者 / 偏移常量 / 挂载点 / 布局表钉死。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        field_api = FIELD_HEADER.read_text(encoding="utf-8")

        self.assertIn(
            'MakeId(ApiDomain::Room, 1, 0x0036), ApiDomain::Room, "Room", "IsDoorSlotAllowed"',
            catalog, "目录里没有 Room:IsDoorSlotAllowed")
        #: ★ 数据行：`Data+0x40`、元素宽度 **8**、`BoolBitArrayOfArg`、降级 `False`、
        #:   接收者 `RoomConfigData`（两跳链末端）。
        self.assertRegex(
            remaining,
            r"\{\s*0x04010036,\s*kRoomConfigDoorsOffset,\s*8,\s*"
            r"FieldKind::BoolBitArrayOfArg,\s*FieldMissing::False,\s*"
            r"FieldReceipt::RoomConfigData,\s*0xFF\}",
            "数据行缺失或形状/宽度/降级档/接收者不对：Room:IsDoorSlotAllowed")
        #: ★★ 反回归：不许被塞进引擎方法行表（引擎里没有同名访问器）。
        self.assertNotRegex(remaining, r"0x04010036[^\n]*EngineCallShape")
        self.assertIn("inline constexpr uintptr_t kRoomConfigDoorsOffset = 0x40;", constants)
        #: 布局表那一行（`confirmed`）与生成物里的常量，编译期已由 `static_assert` 钉住，
        #: 这里再确认两处名字都在。
        self.assertIn("kRoomDescriptorDataDoorsOffset", LAYOUT_HEADER.read_text(encoding="utf-8"))
        self.assertIn("kRoomConfigDoorsOffset == layout::kRoomDescriptorDataDoorsOffset", remaining)
        #: 复用既有的接收者与 kind（**本批没有新机制** ⇒ 0 字节代码）。
        self.assertRegex(field_api, r"RoomConfigData\s*=\s*7")
        self.assertIn("BoolBitArrayOfArg = 12,", field_api)
        self.assertIn("case FieldKind::BoolBitArrayOfArg:",
                      ISAAC_API.read_text(encoding="utf-8"))
        #: 挂载点：本族的行表经由同一处 `AttachOwnerMethods(..., "Room", ...)`。
        self.assertRegex(remaining, r"AttachOwnerMethods\(state, \"Room\",[^;]*kRoomFieldApis")

    def test_the_evidence_and_the_pc_yardstick_are_recorded(self):
        """★ 常量段必须写明 PC 的护栏/读法、那一格的**正式名字**、四条 Switch 证据、以及
        "别用描述符 `+0x20` 的运行时那份代替它"。

        少了这几条，后人只看到"某处读过一次 `+0x40`"，很容易顺手换成
        `RoomDescriptor.AllowedDoors`（那是**运行时**那份，与契约那句"与门此刻在不在无关"正相反）。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        folded = constants.lower()
        #: PC 侧：绑定 VA + 护栏常量 + 那一格的文档出处。
        for needle in ("0x58bfd0", "roomconfig_room.md:29"):
            self.assertIn(needle, folded, f"PC 侧证据 {needle} 没有写进常量段")
        #: Switch 侧四条证据地址。
        for va in ("0x3D6A14", "0x3D8254", "0x464D44", "0x3D825C"):
            self.assertIn(va.lower(), folded, f"Switch 侧证据地址 {va} 没有写进常量段")
        #: 两条容易混的字段都要点名，并说明"不许平移 PC 的偏移"。
        self.assertIn("Data+0x40", constants)
        self.assertIn("Data+0x38", constants)
        self.assertIn("AllowedDoors", constants)
        self.assertIn("tools/layout_tables/room_descriptor.json", constants)

    def test_the_layout_table_row_is_confirmed_with_access_and_semantic_evidence(self):
        """布局表 `Data.Doors` 行必须是 `confirmed`，且 access 与 semantic 证据都齐全。

        `--verify` 会重新反汇编逐条核对（偏移/宽度/立即数）；"按门位右移之后测第 0 位"
        这条 semantic 就是"每一位各自对应一个门位"的锚点（不然只是一格被读过的整数）。
        """
        table = json.loads(LAYOUT.read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in table["rows"]}
        self.assertIn("Data.Doors", rows)
        row = rows["Data.Doors"]
        self.assertEqual(row["confidence"], "confirmed")
        self.assertEqual(row["offset"], 64)
        self.assertEqual(row["width"], 8)
        self.assertEqual(row["nested_in"], "Data")
        kinds = [e["kind"] for e in row["evidence"]]
        self.assertIn("semantic", kinds)
        self.assertGreaterEqual(kinds.count("access"), 2)
        functions = [e["function"] for e in row["evidence"]]
        for symbol in ("_ZN15IsaacRepentance5Level21precalc_allowed_doorsERNS_14RoomDescriptorE",
                       "_ZN15IsaacRepentance5Level21get_room_neighbor_posEiNS_9eDoorSlotE",
                       "_ZN15IsaacRepentance4Room18TrySpawnSecretExitEbb"):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, functions, f"布局表里没有 {symbol} 的证据")
        #: semantic 证据的立即数（"测第 0 位"与"`1 << 门位`"）。
        immediates = [e.get("immediate") for e in row["evidence"] if e["kind"] == "semantic"]
        self.assertIn(0, immediates)
        self.assertIn(1, immediates)


if __name__ == "__main__":
    unittest.main()
