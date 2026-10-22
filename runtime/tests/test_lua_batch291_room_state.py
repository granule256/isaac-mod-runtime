"""门禁：`Room` 的四个只读状态量（批次 291，2026-10-02）。

## 这一批是什么

| API | 契约 | 引擎侧依据 | 接收者 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Room:GetBossID()` | `Room.md:109` | `Room + 0x1FC0`（`Room::Init` 写入 entities2.xml 的 `bossID`） | `Room` | 15 |
| `Room:IsFirstVisit()` | `Room.md:670` | `Room + 0x1` 的**字节**（PC 绑定就是 `mov al,[ecx+1]`） | `Room` | 14 |
| `Room:IsAmbushDone()` | `Room.md:639` | 描述符 `Flags`（`+0x50`）的 **bit3** | `RoomDescriptor`（本批新收） | 9 |
| `Room:HasWaterPits()` | `Room.md:622` | 同一个 `Flags` 的 **bit5** | `RoomDescriptor`（本批新收） | 2 |

四条在引擎里都**没有同名访问器**（Switch 构建里连符号都没有）⇒ 全部走**字段读取型数据行**
（`remaining_api.cpp` 的 `kRoomFieldApis`），**0 字节代码**。偏移的由来、PC 绑定函数本体、
Switch 侧具名消费者的证据链写在 `runtime_constants.hpp` 的**批次 291 段**。

## 本批新增的两样"能力"（都是一次性成本，不是每条 API 的成本）

1. **新接收者 `FieldReceipt::RoomDescriptor`** —— 「当前房间 → `Room + 0x8` → 描述符」这**一跳**
   链的末端（`room_descriptor` 的字段都在它上面）。
   ★ 为什么**不能**拿现成的 `FieldReceipt::Room` 加一个 `+0x50` 凑：`Room + 0x50` 与
   描述符 `+0x50` 是**两个不同的字段**（后者是 `Flags` 位掩码，前者是 `Room` 自己的东西）。
   读了前者不会报错，只会**静默给错值** —— 本文件用"同一偏移上各放一个诱饵"把它抓死。
2. **新种类 `FieldKind::BoolBit`** —— 读 `u32` 位掩码、**单独测 `offset2` 指定的那一位**。
   ★ 为什么既有种类覆盖不了：`BoolNonZero`（非零即真）在这一格上**恒真**（低六位里
   bit0 已清、bit1 压板…常年置着），`BoolEquals`（整字 == 常量）**几乎恒假**（同一时刻
   可能有多个位）。PC 侧的依据就是那两个绑定函数本体里的 `shr eax,N` + `and al,1`。

## 宿主验到了什么、没验到什么

* **验到**（字段行**没有入口指纹**，所以宿主里能读到真值）：
  - ★ **接收者走对了**：房间块与描述符块在**同一个偏移** `+0x50` 上各放一个**互不相同**的位图
    （房间块 `0x20` = 只有 bit5、描述符块 `0x08` = 只有 bit3）⇒ 正确的答案是
    `IsAmbushDone() == true` **且** `HasWaterPits() == false`；用错了 receipt 这两条会**同时翻转**。
  - ★ **测的是"那一位"，不是"非零"**：描述符写成 `0x17`（bit0/1/2/4 置着、bit3/bit5 没置）
    ⇒ 两条都必须答 `false`（`BoolNonZero` 在这里会答 true ⇒ 这条专抓那种实现）。
  - ★ **两个位各自独立**：只有 bit5 时 `HasWaterPits()==true` / `IsAmbushDone()==false`。
  - ★ `IsFirstVisit` 读的是**恰好 `+0x1` 那个字节**：把 `+0x00` 与 `+0x02` 写成 `0xFF`、
    `+0x01` 写 `0` ⇒ 必须答 `false`（读成 4 字节或读错格都会答 true）；
    再写 `+0x01 = 2` ⇒ 答 `true`（"非零即真"，不是"等于 1"）。
  - ★ `GetBossID()` 返回**整数**（模组拿它 `== 55` 之类逐值比较）。
  - ★ **描述符那两条断了链时降级成 `false`、且不抛 Lua 错误**；同时
    **`GetBossID`/`IsFirstVisit` 仍照常工作**（它们的接收者不经过描述符）——
    这一条把"两个 receipt 是分开的"钉死。
  - 参数闸门 = **恰好一个**（只有冒号调用压进来的 `self`）；点号 + 显式 self 放行。
* **没验**：真机上这几格到底是不是这几个量（宿主里"偏移对不对"是同一张表的两处引用同一个
  常量，自己证不了自己）、以及真机上的数值。⇒ 真机项 = 作业单 **V42**。
"""

import json
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
FIELD_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
LAYOUT = ROOT / "tools" / "layout_tables" / "room_descriptor.json"
LAYOUT_ROOM = ROOT / "tools" / "layout_tables" / "room.json"

#: `(名字, 域内序号, 偏移常量, offset2, FieldKind, FieldMissing, FieldReceipt)`。
FIELD_APIS = (
    ("GetBossID", 0x0029, "kRoomBossIdOffset", "0x00", "U32", "Zero", "Room"),
    ("IsFirstVisit", 0x002A, "kRoomFirstVisitOffset", "0x00", "Bool", "False", "Room"),
    ("IsAmbushDone", 0x002B, "kRoomDescriptorFlagsOffset", "3", "BoolBit", "False",
     "RoomDescriptor"),
    ("HasWaterPits", 0x002C, "kRoomDescriptorFlagsOffset", "5", "BoolBit", "False",
     "RoomDescriptor"),
)

#: 真值（场景 `state`）：Boss id = Mega Satan 的 55（语料里 `Enhanced-Boss-Bars` /
#: `MusicModCallback` 真的在比这个数）；首次访问字节 = 1。
TRUE_BOSS_ID = 55
#: 描述符的位图：**只有 bit3**（= `CHALLENGE_DONE`）⇒ `IsAmbushDone()==true`、
#: `HasWaterPits()==false`。
DESCRIPTOR_FLAGS = 0x08
#: ★ 诱饵：把**同一个偏移** `+0x50` 放在**房间块**上，只置 bit5 ⇒ 万一实现用
#: `FieldReceipt::Room` 去读这一格，两条断言会同时翻转（`IsAmbushDone` 变 false、
#: `HasWaterPits` 变 true）。两个值都挑的"合法位图"，读错了不会"看起来像没读到"。
ROOM_BLOCK_DECOY = 0x20
#: 只有 bit5 的描述符位图（场景 `wateronly`）。
WATER_ONLY_FLAGS = 0x20
#: bit0/1/2/4 置着、**bit3 与 bit5 都没置**（场景 `otherbits`）★ 专抓 `BoolNonZero` 式实现。
OTHER_BITS_FLAGS = 0x17

#: 房间块必须盖住 `Room + 0x1FC0`（`GetBossID` 那一格）→ 末尾取 `0x1FC8`。
ROOM_BLOCK_SIZE = 0x1FC8
#: 描述符块只需盖住 `+0x50`（`Flags`），取 `0x80` 留出余量。
DESCRIPTOR_BLOCK_SIZE = 0x80


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（与批次 289/290 同一套形状，本批只需要两层）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                              = &g_RoomBytes（"当前房间"）
//   g_RoomBytes [kRoomDescriptorPointerOffset]    = &g_DescriptorBytes（描述符）
//   g_RoomBytes [kRoomBossIdOffset]               = Boss id
//   g_RoomBytes [kRoomFirstVisitOffset]           = 首次访问字节
//   g_RoomBytes [kRoomDescriptorFlagsOffset]      = ★ 诱饵（同偏移、不同的位图）
//   g_DescriptorBytes[kRoomDescriptorFlagsOffset] = Flags 位掩码（bit3 / bit5）
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_DescriptorBytes;
//: 场景开关（批次 250 的口径：拿不到房间就**不报错**、给保守值）。
bool g_RoomAvailable = true;
bool g_DescriptorAvailable = true;
std::uintptr_t g_EngineBase = 0;

//: 房间块必须盖住 `GetBossID` 那一格（本批最远的偏移）。
static_assert(kRoomBossIdOffset + sizeof(std::uint32_t) <= 0x1FC8,
              "fake room block must hold the boss id");
static_assert(kRoomDescriptorPointerOffset + sizeof(std::uint64_t) <= 0x1FC8,
              "fake room block must hold the descriptor pointer");
static_assert(kRoomFirstVisitOffset + sizeof(std::uint8_t) <= 0x1FC8,
              "fake room block must hold the first-visit byte");
static_assert(kRoomDescriptorFlagsOffset + sizeof(std::uint32_t) <= 0x80,
              "fake descriptor block must hold the Flags word");

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
    g_RoomBytes.assign(0x1FC8, 0);
    g_DescriptorBytes.assign(0x80, 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset,
                           AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
    // `Room + 0x8` = 描述符（场景 `nodesc` 时故意留 0）。
    if (g_DescriptorAvailable) {
        WriteAt<std::uint64_t>(g_RoomBytes, kRoomDescriptorPointerOffset,
                               AddressOf(g_DescriptorBytes));
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

    // 七个场景：
    //   state     —— 正常：Boss id 55、首次访问字节 1；描述符位图 **只有 bit3**，
    //                而房间块的**同一偏移**上放着诱饵（只有 bit5）
    //   otherbits —— 描述符位图 = bit0/1/2/4（bit3、bit5 都没置）⇒ 两条都必须 false
    //   wateronly —— 描述符位图只有 **bit5** ⇒ 水坑 true / 伏击 false
    //   byte2     —— 首次访问字节 = 2 ⇒ 必须 true（"非零即真"，不是"等于 1"）
    //   neighbor  —— `+0x00` 与 `+0x02` 写 0xFF、`+0x01` 写 0 ⇒ 必须 false
    //   nodesc    —— 描述符指针为 0 ⇒ 描述符那两条降级成 false，
    //                但 `GetBossID`/`IsFirstVisit` 仍照常（接收者不同）
    //   noroom    —— 拿不到当前房间 ⇒ 四条全部降级、且不抛错
    std::uint32_t bossId = 55;
    std::uint8_t firstVisit = 1;
    std::uint32_t descriptorFlags = 0x08;
    bool neighboursPoisoned = false;
    if (std::strcmp(scenario, "state") == 0) {
        // 默认值。
    } else if (std::strcmp(scenario, "otherbits") == 0) {
        bossId = 0;
        firstVisit = 0;
        descriptorFlags = 0x17;
    } else if (std::strcmp(scenario, "wateronly") == 0) {
        bossId = 0;
        firstVisit = 0;
        descriptorFlags = 0x20;
    } else if (std::strcmp(scenario, "byte2") == 0) {
        firstVisit = 2;
    } else if (std::strcmp(scenario, "neighbor") == 0) {
        firstVisit = 0;
        neighboursPoisoned = true;
    } else if (std::strcmp(scenario, "nodesc") == 0) {
        g_DescriptorAvailable = false;
    } else if (std::strcmp(scenario, "noroom") == 0) {
        g_RoomAvailable = false;
    } else {
        return 91;
    }

    PublishFakeRoom();
    WriteAt<std::uint32_t>(g_RoomBytes, kRoomBossIdOffset, bossId);
    WriteAt<std::uint8_t>(g_RoomBytes, kRoomFirstVisitOffset, firstVisit);
    if (neighboursPoisoned) {
        // ★ 只有"恰好读 `+0x1` 那个字节"才会答 false。
        WriteAt<std::uint8_t>(g_RoomBytes, 0x0, 0xFF);
        WriteAt<std::uint8_t>(g_RoomBytes, 0x2, 0xFF);
    }
    // ★ 诱饵：**同一个偏移** `+0x50`，房间块上与描述符块上是**不同**的位图。
    WriteAt<std::uint32_t>(g_RoomBytes, kRoomDescriptorFlagsOffset, 0x20);
    WriteAt<std::uint32_t>(g_DescriptorBytes, kRoomDescriptorFlagsOffset, descriptorFlags);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local room = Game():GetRoom()"
        " print('B291 roomkind=' .. type(room))"
        " print('B291 fn=' .. type(room.GetBossID) .. ',' .. type(room.IsFirstVisit) .. ','"
        "   .. type(room.IsAmbushDone) .. ',' .. type(room.HasWaterPits))"
        " local boss = room:GetBossID()"
        " print('B291 bosskind=' .. type(boss))"
        " print('B291 bossid=' .. tostring(boss))"
        " print('B291 bossis55=' .. tostring(boss == 55))"
        " local first = room:IsFirstVisit()"
        " print('B291 firstkind=' .. type(first))"
        " print('B291 first=' .. tostring(first))"
        " print('B291 ambush=' .. tostring(room:IsAmbushDone()))"
        " print('B291 ambushkind=' .. type(room:IsAmbushDone()))"
        " print('B291 water=' .. tostring(room:HasWaterPits()))"
        // 参数闸门：字段行**恰好收一个**参数（只有冒号调用压进来的 self）。
        " print('B291 args=' .. ok(function() return room:GetBossID(1) end))"
        " print('B291 argerr=' .. tostring(select(2, pcall(function()"
        "   return room:IsFirstVisit(1) end))))"
        " print('B291 args2=' .. ok(function() return room:IsAmbushDone(1) end))"
        " print('B291 argerr2=' .. tostring(select(2, pcall(function()"
        "   return room:IsAmbushDone(1) end))))"
        // 点号 + 显式 self 也是 1 个参数 ⇒ 允许。
        " print('B291 dotcall=' .. ok(function() return room.GetBossID(room) end))"
        // 对照：同族老方法（字段行的 `GetRoomShape`、手写的 `GetCenterPos`）仍照常可用
        // ⇒ 本批没有动到族里别的东西。
        " print('B291 sibling1=' .. ok(function() return room:GetRoomShape() end))"
        " print('B291 sibling2=' .. ok(function() return room:GetCenterPos() end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b291.lua");
    static_cast<void>(result);
    return 0;
}
'''


class RoomStateBatch291Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b291-")
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
        #: ★ `stderr` 一起返回：只回 `stdout` 时"Lua 脚本中途报错"与"什么都没做"长得一样。
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_the_descriptor_fields_read_through_the_descriptor_receipt(self):
        """★★ 房间块与描述符块在**同一个偏移**上各放一个位图 ⇒ 只有走对 receipt 才答得对。

        房间块 `+0x50` = `0x20`（只有 bit5）；描述符 `+0x50` = `0x08`（只有 bit3）。
        正确答案 ⇒ `IsAmbushDone() == true` **且** `HasWaterPits() == false`。
        ★ 若实现拿 `FieldReceipt::Room` 加一个 `+0x50` 去凑（本批最想杜绝的那种写法），
        这两条会**同时翻转**（伏击 false、水坑 true）—— 一个诱饵抓两条判据，
        比"断言读到某个值"强得多（后者在"读错格但恰好同值"时是假绿）。
        """
        out = self.run_scenario("state")
        self.assertIn("B291 roomkind=userdata", out)
        self.assertIn("B291 fn=function,function,function,function", out)
        self.assertIn("B291 ambush=true", out)
        self.assertIn("B291 water=false", out)
        #: 反向断言：诱饵值造成的镜像结果一旦出现就红。
        self.assertNotIn("B291 ambush=false", out)
        self.assertNotIn("B291 water=true", out)

    def test_bit_fields_test_their_own_bit_not_merely_non_zero(self):
        """★★ 描述符位图 = bit0/1/2/4（bit3、bit5 **都没置**）⇒ 两条都必须 `false`。

        ★ 这条专抓 `BoolNonZero` 式的实现（读一个 `u32`、非零即真）：`Flags` 的低位在真实
        游戏里常年置着（bit0 已清房、bit1 压板触发…）⇒ 那种实现会让 `IsAmbushDone()` 恒答
        `true`，模组会以为"这场伏击已经打完了"而跳过它 —— 静默的错误分支，不报错。
        PC 侧的依据是两个绑定函数本体里的 `shr eax,3` / `shr eax,5` + `and al,1`。
        """
        out = self.run_scenario("otherbits")
        self.assertIn("B291 ambush=false", out)
        self.assertIn("B291 water=false", out)
        #: 对照：位图整体**非零** ⇒ 若实现按"非零即真"算，这里就会答 true。
        self.assertNotIn("B291 ambush=true", out)
        self.assertNotIn("B291 water=true", out)

    def test_the_two_bits_are_independent(self):
        """只有 bit5 ⇒ 水坑 true、伏击 false（与 `state` 那一场互为镜像）。"""
        out = self.run_scenario("wateronly")
        self.assertIn("B291 water=true", out)
        self.assertIn("B291 ambush=false", out)

    def test_first_visit_reads_exactly_the_single_byte_at_plus_one(self):
        """★ `IsFirstVisit()` 读的是**恰好 `Room + 0x1` 那个字节**。

        把 `+0x00` 与 `+0x02` 写成 `0xFF`、`+0x01` 写 `0` ⇒ 必须答 `false`。
        读成 4 字节（`+0x0`）、或读错格（`+0x0`/`+0x2`），这一场全都会答 `true`。
        """
        out = self.run_scenario("neighbor")
        self.assertIn("B291 first=false", out)
        self.assertNotIn("B291 first=true", out)

    def test_first_visit_is_non_zero_not_equals_one(self):
        """★ `+0x01` 写 `2` ⇒ 答 `true`（'非零即真'，不是"等于 1"）。

        PC 的绑定函数是 `mov al,[ecx+1]; ret` —— 一个字节原样返回，胶水层再按"非零"
        转成 Lua 布尔 ⇒ 判据必须是"非零"。
        """
        out = self.run_scenario("byte2")
        self.assertIn("B291 firstkind=boolean", out)
        self.assertIn("B291 first=true", out)

    def test_the_boss_id_is_read_from_the_room_object_as_an_integer(self):
        """★ `GetBossID()` 返回**整数**（模组拿它 `== 55` 之类逐值比较）。"""
        out = self.run_scenario("state")
        self.assertIn("B291 bosskind=number", out)
        self.assertIn("B291 bossid=55", out)
        self.assertIn("B291 bossis55=true", out)

    def test_broken_descriptor_degrades_without_erroring_and_leaves_the_room_fields_alone(self):
        """★★ 描述符指针为 0 ⇒ 描述符那两条答 `false`、**不抛 Lua 错误**；
        而 `GetBossID`/`IsFirstVisit` **仍照常工作**（它们的接收者不经过描述符）。

        最后半句是本批"两个 receipt 确实分开"的判据：两条描述符位的降级**没有**连累
        同一个表里的另外两行。不抛错的理由与批次 250 一致 —— 报错会把整条模组回调摘掉。
        """
        out = self.run_scenario("nodesc")
        self.assertIn("B291 roomkind=userdata", out)
        self.assertIn("B291 fn=function,function,function,function", out)
        self.assertIn("B291 ambush=false", out)
        self.assertIn("B291 water=false", out)
        #: 房间上的两格照旧可读。
        self.assertIn("B291 bossid=55", out)
        self.assertIn("B291 first=true", out)

    def test_no_current_room_degrades_all_four_without_erroring(self):
        """★ 拿不到当前房间 ⇒ 四条全部按各自的降级档作答（0 / false / false / false），不抛错。

        ★ 房间句柄本身仍在（批次 250：给空壳、不给 `nil`）⇒ 说明走的是"字段行降级"，
        而不是"连方法都挂不上"。
        """
        out = self.run_scenario("noroom")
        self.assertIn("B291 roomkind=userdata", out)
        self.assertIn("B291 fn=function,function,function,function", out)
        self.assertIn("B291 bosskind=number", out)
        self.assertIn("B291 bossid=0", out)
        self.assertIn("B291 firstkind=boolean", out)
        self.assertIn("B291 first=false", out)
        self.assertIn("B291 ambush=false", out)
        self.assertIn("B291 water=false", out)

    def test_argument_gate_is_exactly_one(self):
        """参数闸门 = **恰好一个**（只有冒号调用压进来的 `self`），多给一个就报错。

        ★ 与批次 069 给 `Room` 的**引擎方法行**打的那个补丁不同：本批四条都是**字段行**，
        闸门天然按"栈上 1 个值"算 ⇒ 语料那 40 处冒号写法正好满足，不需要任何改动。
        """
        out = self.run_scenario("state")
        self.assertIn("B291 args=false", out)
        self.assertIn("Room:IsFirstVisit accepts no arguments", out)
        self.assertIn("B291 args2=false", out)
        self.assertIn("Room:IsAmbushDone accepts no arguments", out)        #: 点号 + 显式 self 也是 1 个参数 ⇒ 允许。
        self.assertIn("B291 dotcall=true", out)
        #: 对照：同族老方法仍照常可用 ⇒ 本批没有动到族里别的东西。
        self.assertIn("B291 sibling1=true", out)
        self.assertIn("B291 sibling2=true", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 种类与降级档 / 接收者 / 偏移常量 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for name, index, offset_name, offset2, kind, missing, receipt in FIELD_APIS:
            with self.subTest(api=f"Room:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Room, 1, 0x{index:04X}), ApiDomain::Room, "Room", "{name}"',
                    catalog, f"目录里没有 Room:{name}")
                #: ★ 行住在 `remaining_api.cpp` 自己的 TU 里（家族的表必须与家族同 TU）。
                self.assertRegex(
                    remaining,
                    rf"\{{\s*(?i:0x0401{index:04x}),\s*{offset_name},\s*{offset2},\s*"
                    rf"FieldKind::{kind},\s*FieldMissing::{missing},\s*"
                    rf"FieldReceipt::{receipt},\s*0xFF\}}",
                    f"数据行缺失或形状/降级档/接收者不对：Room:{name}")
                #: ★★ 反回归：这四条**不许**被塞进引擎方法行表（引擎里没有同名函数可调，
                #:   塞进去会变成"每次调用都要核对入口字"⇒ 真机上恒降级）。
                self.assertNotRegex(remaining, rf"0x0401{index:04x}[^\n]*EngineCallShape")

        #: 偏移常量（值 + 出处门禁只认这个头文件）。
        self.assertRegex(constants, r"inline constexpr uintptr_t kRoomBossIdOffset\s*=\s*0x1FC0;")
        self.assertRegex(constants, r"inline constexpr uintptr_t kRoomFirstVisitOffset\s*=\s*0x1;")
        self.assertRegex(constants,
                         r"inline constexpr uintptr_t kRoomDescriptorFlagsOffset\s*=\s*0x50;")
        #: ★ 同一个偏移在两处（本头文件 + 布局表生成物）各有一个常量的地方要有编译期钉子。
        self.assertRegex(
            remaining,
            r"static_assert\(kRoomDescriptorFlagsOffset\s*==\s*"
            r"layout::kRoomDescriptorFlagsOffset")
        self.assertRegex(
            remaining,
            r"static_assert\(kRoomBossIdOffset\s*==\s*layout::kRoomBossIdOffset")
        self.assertRegex(
            remaining,
            r"static_assert\(kRoomFirstVisitOffset\s*==\s*"
            r"layout::kRoomFirstVisitOffset")

    def test_the_new_receipt_and_kind_exist_and_are_implemented(self):
        """★ 新接收者与新种类必须**真的实现**，而且接收者走的是"当前房间 → `Room+0x8`"。"""
        field_api = FIELD_API.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")

        self.assertRegex(field_api, r"RoomDescriptor\s*=\s*8")
        self.assertRegex(field_api, r"BoolBit\s*=\s*10")
        self.assertRegex(isaac, r"case\s+FieldReceipt::RoomDescriptor\s*:")
        self.assertRegex(
            isaac,
            r"LoadPointerAt\(engine_memory::AddressOf\(room\),\s*kRoomDescriptorPointerOffset")
        #: 位测试真的按"那一位"算（`1 << offset2` 与 `&`），不是 `!= 0`。
        self.assertRegex(isaac, r"case\s+FieldKind::BoolBit\s*:")
        self.assertRegex(isaac, r"<<\s*row->offset2")
        #: 位号越界要按"读不到"降级，而不是静默 `& 0`（那会恒答 false，同样难查）。
        self.assertRegex(isaac, r"row->offset2\s*>=\s*32")

        #: 挂载点：本族的字段行表经由同一处 `AttachOwnerMethods(..., "Room", ...)`。
        remaining = REMAINING_API.read_text(encoding="utf-8")
        self.assertRegex(remaining, r"AttachOwnerMethods\(state, \"Room\",[^;]*kRoomFieldApis")

    def test_the_evidence_and_the_pc_yardstick_are_recorded(self):
        """★ 常量段必须写明 PC 绑定函数本体与 Switch 侧具名消费者，以及"不能搬 PC 偏移"。

        这条不是形式主义：这一批四条全部是"靠消费者反推字段"，而 PC 的四个偏移
        （`Room+0x1D1C` / `Room+0x1` / 描述符 `+0x44`）里**有两个与 Switch 不同**
        （`0x1FC0` / `+0x50`）⇒ 顺手照抄是最容易犯的错（批次 269/289/290 都被咬过同一口）。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        folded = constants.lower()
        #: PC 侧四条绑定函数本体。★ 大小写不敏感：常量段里散文用大写、反汇编清单是原样小写，
        #: 判据是"这个地址被写进来了"，不是"十六进制字母是大写"。
        for va in ("0x430D60", "0x638F90", "0x6DCE00", "0x4F3EC0", "0x427700"):
            self.assertIn(va.lower(), folded, f"PC 侧证据地址 {va} 没有写进常量段")
        #: Switch 侧具名消费者（每条至少两条独立）。
        for va in ("0x45C6C4", "0x499674", "0x451948",   # GetBossID 三条
                   "0x45CCD8", "0x488B28", "0x451E9C",   # IsFirstVisit 三条
                   "0x408C", "0x3E6C50",                 # bit3 两条
                   "0x47F048", "0x47F6C8"):              # bit5 两条
            self.assertIn(va.lower(), folded, f"Switch 侧证据地址 {va} 没有写进常量段")
        #: 契约页行号（G2：写不出页:行号就不许写代码）。
        for page_line in ("Room.md:109", "Room.md:670", "Room.md:639"):
            self.assertIn(page_line, constants, f"契约出处 {page_line} 没有写进常量段")
        #: "不能搬 PC 的偏移"的理由与两处不同的偏移。
        self.assertIn("0x1D1C", constants)
        self.assertIn("0x1FC0", constants)
        #: 布局表指针（逐条可复核的那一份）。
        self.assertIn("tools/layout_tables/room_descriptor.json", constants)
        #: ★ 别把 `Room::HasWater()`（水位浮点）当成 `HasWaterPits` 的锚点 —— 这条写下来了。
        self.assertIn("0x487FA0", constants)

    def test_the_layout_table_flags_row_is_confirmed_with_semantic_evidence(self):
        """布局表 `Flags` 行必须是 `confirmed`，且**至少有一条 `semantic` 证据**。

        本批两位（bit3 / bit5）的依据就挂在这一行上：行是 `confirmed` + 有取值锚点，
        才能用于对外 API（`build_layout_table.py` 的 `API_ALLOWED_CONFIDENCE`）。
        """
        table = json.loads(LAYOUT.read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in table["rows"]}
        self.assertIn("Flags", rows)
        row = rows["Flags"]
        self.assertEqual(row["confidence"], "confirmed")
        self.assertEqual(row["offset"], 80)
        self.assertEqual(row["width"], 4)
        kinds = [e["kind"] for e in row["evidence"]]
        self.assertIn("semantic", kinds)
        self.assertGreaterEqual(kinds.count("access"), 2)
        #: bit3 的独位测试必须在证据里（`CanOpenChallengeRoom` 的 `tbnz w9,#0x3`）。
        functions = [e["function"] for e in row["evidence"]]
        self.assertIn("_ZNK15IsaacRepentance5Level20CanOpenChallengeRoomEi", functions)
        immediates = [e.get("immediate") for e in row["evidence"] if e["kind"] == "semantic"]
        self.assertIn(3, immediates)
        #: ★ 本批补的 bit5（`HAS_WATER`）两条独立读者也必须在证据里 —— 否则"水坑"这一位
        #: 只有 PC 文档的说法，没有 Switch 侧的锚点。
        self.assertIn("_ZN15IsaacRepentance4Room15pre_render_pitsEv", functions)
        self.assertIn("_ZN15IsaacRepentance4Room16pre_render_waterEv", functions)
        self.assertIn(5, immediates)

    def test_the_two_room_fields_are_promoted_to_confirmed_with_their_own_anchors(self):
        """★ 作业单 G4：字段偏移要**在布局表里升到 `confirmed`** 才允许进对外 API。

        `Room.BossId`（`+0x1FC0`）与 `Room.FirstVisit`（`+0x1`）本批新写进
        `tools/layout_tables/room.json`，各自带**具名写入方 / 读出方 + 语义锚点**
        （`test_confirmed_rows_need_name_justifying_evidence` 要求 confirmed 行至少有一条
        semantic 或 device 证据）。`build_layout_table.py --verify` 会重新反汇编逐条核对。
        """
        table = json.loads(LAYOUT_ROOM.read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in table["rows"]}
        for name, offset, width in (("BossId", 0x1FC0, 4), ("FirstVisit", 0x1, 1)):
            with self.subTest(row=name):
                self.assertIn(name, rows, f"布局表里没有 {name} 行")
                row = rows[name]
                self.assertEqual(row["confidence"], "confirmed")
                self.assertEqual(row["offset"], offset)
                self.assertEqual(row["width"], width)
                kinds = [e["kind"] for e in row["evidence"]]
                self.assertIn("semantic", kinds, f"{name} 行缺少语义锚点")
                self.assertGreaterEqual(kinds.count("access"), 2, f"{name} 行缺少独立读者")
        #: 语义锚点必须点名那两条具名函数（不是"某处有个字节"）。
        self.assertIn("_ZN15IsaacRepentance4Room9PlayMusicEv",
                      [e["function"] for e in rows["BossId"]["evidence"]])
        self.assertIn("_ZN15IsaacRepentance4Room14RespawnEnemiesEv",
                      [e["function"] for e in rows["FirstVisit"]["evidence"]])
        #: ★ `FirstVisit` 必须记的是**字节**（`width 1`）—— 写成 4 会让读法变成读一个 `u32`，
        #: 把相邻字节也算进来（宿主用例 `neighbor` 那一场就是抓这个的）。
        self.assertEqual(rows["FirstVisit"]["width"], 1)


if __name__ == "__main__":
    unittest.main()
