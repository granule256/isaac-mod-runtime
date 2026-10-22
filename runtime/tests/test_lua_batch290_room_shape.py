"""门禁：`Room:GetRoomShape()`（批次 290，2026-10-02）。

## 这一批是什么

| API | 契约 | 引擎侧依据 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Room:GetRoomShape()` | `Room.md:530` | 没有同名函数 ⇒ 读 `Room → 描述符 → 房间配置对象` 的 `+0x5C` | `U32` + 新接收者 `RoomConfigData` | 19（其中 2 处在长注释里 = 死代码） |

走**字段读取型数据行**（`remaining_api.cpp` 的 `kRoomFieldApis` 第 3 行），**0 字节代码**。
偏移与三条独立读者的证据写在 `runtime_constants.hpp` 的**批次 290 段**；逐条可复核的证据在
`tools/layout_tables/room_descriptor.json` 的 `Data.Shape` 行
（`build_layout_table.py --verify` 会重新反汇编核对，本批实测 15 行 / 38 条证据全过）。

## 为什么接收者是"两跳链的末端"（`FieldReceipt::RoomConfigData`）

形状**不在 `Room` 上**：它在 `Room → RoomDescriptor → RoomConfig::Room` 这条固定指针链的末端。
这不是我们发明的绕法 —— PC 的绑定函数本体（`0x444C30`）就是这两跳：

    444c30  mov  eax, [ecx + 0x4]    ; ① 描述符（PC 在 Room+0x4；Switch 在 Room+0x8）
    444c37  mov  eax, [eax + 0x10]   ; ② 配置对象（RoomDescriptor.Data）
    444c3e  mov  eax, [eax + 0x48]   ; ③ 形状（PC 在 Data+0x48；Switch 在 Data+0x5C）
    444c42  mov  eax, 0x1            ; ★ 两跳任一为空 ⇒ 答 1（= ROOMSHAPE_1x1）

Switch 侧同一个形状被三条**具名**读者用逐字同形的两跳读出来（`Room::IsLShapedRoom() const @
0x48453C` —— 整个函数只有 28 字节；`Room::GetLRoomAreaDesc() const @ 0x484558`；
`Room::Init @ 0x45F974`），而且三条都把有效区间判成 **9..12**（四个 L 形）。

## 为什么语料的接收者口径是安全的

`RoomHandle` 是**不持引擎指针的空壳** ⇒ 接收者只能由 receipt 决定（与 `Room`/`Music`/`ItemPool`
同一处境）。所以落地前把 19 处调用点**逐条核过**：

- `BOIStageAPI15`：`shared.Room = shared.Game:GetRoom()`（`roomHandler.lua:53`、`roomgfx.lua:49/227`、
  `extrarooms.lua:505`、`callbacks.lua:962`、`customdoors.lua:433`、`extra/waves.lua:293/299`）；
- `IsaacOnTwitchReloaded`：`local room = Game():GetRoom()`（`mechanics.lua:543` → `:547`）；
- `MusicModCallback`：`local room = game:GetRoom()`（`repentance.lua:568` → `:594`；
  `Game():GetRoom()` 于 `:1199` → `:1521`）；
- `RepentancePlus`：`local room = game:GetRoom()`（`main.lua:684` → `:731/735/739`；
  `:1154` → `:1180/1184`）。

⇒ **没有一处是"别的房间"**。另外 `RepentancePlus/main.lua:453/463` 那两处位于 `--[[ … --]]`
长注释里（403–465 行）⇒ **死代码**，不影响判据（这也是本文件把 19 而不是 21 当分母的原因）。

## 宿主验到了什么、没验到什么

* **验到**（字段行**没有入口指纹**，所以宿主里能读到真值）：
  - ★ **走的是两跳、读的是最后一跳那一格**：夹具在**三块内存的同一偏移**（`+0x5C`）各放一个
    **互不相同**的值（房间块 12、描述符块 8、配置块 9），断言读回的是**配置块那个 9** ——
    少走一跳会拿到 12 或 8，两条诱饵值专抓这个；
  - 返回的是**整数**（PC 返回 `int`；模组拿它与 `RoomShape.ROOMSHAPE_*` 逐值比较）；
  - ★ **链上任一环为空 ⇒ 答 1**（描述符指针为 0 / `Data` 为 0 / 拿不到当前房间，三种都各验一遍），
    且**不抛 Lua 错误** —— 这正是 PC 的 `mov eax,0x1`；
  - ★ **内存里真写着 0 时答 0**（不是 1）—— 与上一条合起来才说明"降级值 1"与"读到的 0"
    是两件事，否则两条判据互相掩盖；
  - 参数闸门 = **恰好一个**（只有冒号调用压进来的 `self`）。
* **没验**：真机上那两跳与 `0x5C` 到底是不是这几格（宿主里"偏移对不对"是同一张表的两处引用
  同一个常量，自己证不了自己）、以及真机上的数值。⇒ 真机项 = 作业单 **V41**。
* **也没验**："接收者非零、但内存读不出来"那条降级分支（`ReadField` 失败）—— 它由所有字段行
  共享，且宿主的假内存永远可读，构造不出那一场。
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

#: `(名字, 域内序号, 偏移常量, FieldKind, FieldMissing, FieldReceipt)`。
FIELD_APIS = (("GetRoomShape", 0x0028, "kRoomConfigShapeOffset", "U32", "One",
               "RoomConfigData"),)

#: ★ 三块内存的同一偏移上各放一个**互不相同**的值 —— 这是本文件最锋利的一条：
#: 少走一跳就必然读到诱饵。`ROOM_DECOY` / `DESCRIPTOR_DECOY` 都挑**合法的形状值**
#: （12 = `ROOMSHAPE_LBR`、8 = `ROOMSHAPE_2x2`）⇒ 读错了不会"看起来像没读到"。
ROOM_DECOY = 12
DESCRIPTOR_DECOY = 8
#: 真值：9 = `ROOMSHAPE_LTL`（四个 L 形里的第一个；三条读者都把有效区间判成 9..12）。
TRUE_SHAPE = 9
#: `ROOMSHAPE_1x1` —— 也是"链断了"时 PC 自己答的那个 1。
SHAPE_1x1 = 1


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "room_descriptor_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存：**三层**（本批比批次 289 多两层的理由就是这条链有两跳）
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                        = &g_RoomBytes（"当前房间"）
//   g_RoomBytes   [kRoomDescriptorPointerOffset]         = &g_DescriptorBytes（① 描述符）
//   g_DescriptorBytes[layout::kRoomDescriptorDataOffset] = &g_ConfigBytes（② 配置对象）
//   g_ConfigBytes [kRoomConfigShapeOffset]               = 形状（③ 值就在这一格）
//
// ★ 三块的**同一个偏移**上各写一个互不相同的值（12 / 8 / 9）：
//   只读房间块 ⇒ 12、只走一跳 ⇒ 8、走对了两跳 ⇒ 9。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_DescriptorBytes;
std::vector<unsigned char> g_ConfigBytes;
//: 场景开关（批次 250 的口径：拿不到房间就**不报错**、给保守值）。
bool g_RoomAvailable = true;
bool g_DescriptorAvailable = true;
bool g_DataAvailable = true;
std::uintptr_t g_EngineBase = 0;

//: 三块都必须盖住要读的那一格（房间块与描述符块还要盖住各自的指针成员）。
static_assert(kRoomDescriptorPointerOffset + sizeof(std::uint64_t) <= 0x80,
              "fake room block must hold the descriptor pointer");
static_assert(isaac::runtime::layout::kRoomDescriptorDataOffset + sizeof(std::uint64_t) <= 0x80,
              "fake descriptor block must hold the Data pointer");
static_assert(kRoomConfigShapeOffset + sizeof(std::uint32_t) <= 0x80,
              "fake config block must hold the shape");

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
    g_RoomBytes.assign(0x80, 0);
    g_DescriptorBytes.assign(0x80, 0);
    g_ConfigBytes.assign(0x80, 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset,
                           AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
    // ① `Room + 0x8` = 描述符（场景 `nodesc` 时故意留 0）。
    if (g_DescriptorAvailable) {
        WriteAt<std::uint64_t>(g_RoomBytes, kRoomDescriptorPointerOffset,
                               AddressOf(g_DescriptorBytes));
    }
    // ② 描述符 + 0x10 = 房间配置对象（场景 `nodata` 时故意留 0）。
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

    // 六个场景：
    //   shape    —— 正常：三块同偏移各放 12 / 8 / 9，应当读到 **9**
    //   roomonly —— 形状写成 1（= ROOMSHAPE_1x1，与"链断"的降级值**同值**，
    //               所以另有 `zero` 来把两者分开）
    //   zero     —— 配置块里真写着 **0** ⇒ 必须答 0（不是 1）
    //   nodesc   —— ①那一跳为空（房间在、描述符指针 0）⇒ 答 1
    //   nodata   —— ②那一跳为空（描述符在、Data 指针 0）⇒ 答 1
    //   noroom   —— 拿不到当前房间 ⇒ 答 1
    std::uint32_t shape = 9;
    if (std::strcmp(scenario, "shape") == 0) {
        // 默认值。
    } else if (std::strcmp(scenario, "roomonly") == 0) {
        shape = 1;
    } else if (std::strcmp(scenario, "zero") == 0) {
        shape = 0;
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
    // ★ 两条诱饵：房间块与描述符块的**同一偏移**（`+0x5C`）。
    WriteAt<std::uint32_t>(g_RoomBytes, kRoomConfigShapeOffset, 12);
    WriteAt<std::uint32_t>(g_DescriptorBytes, kRoomConfigShapeOffset, 8);
    WriteAt<std::uint32_t>(g_ConfigBytes, kRoomConfigShapeOffset, shape);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local room = Game():GetRoom()"
        " print('B290 roomkind=' .. type(room))"
        " print('B290 fn=' .. type(room.GetRoomShape))"
        " local shape = room:GetRoomShape()"
        " print('B290 kind=' .. type(shape))"
        " print('B290 shape=' .. tostring(shape))"
        // ★ 与 `RoomShape` 枚举表逐值比：模组就是这么用的
        //   （`IsaacOnTwitchReloaded/scripts/mechanics.lua:547`）。
        " print('B290 isltl=' .. tostring(shape == RoomShape.ROOMSHAPE_LTL))"
        " print('B290 is1x1=' .. tostring(shape == RoomShape.ROOMSHAPE_1x1))"
        " print('B290 is2x2=' .. tostring(shape == RoomShape.ROOMSHAPE_2x2))"
        // 参数闸门：字段行**恰好收一个**参数（只有冒号调用压进来的 self）。
        " print('B290 args=' .. ok(function() return room:GetRoomShape(1) end))"
        " print('B290 argerr=' .. tostring(select(2, pcall(function()"
        "   return room:GetRoomShape(1) end))))"
        // 点号 + 显式 self 也是 1 个参数 ⇒ 允许。
        " print('B290 dotcall=' .. ok(function() return room.GetRoomShape(room) end))"
        // 对照：同族老方法（同为字段行的 `GetTopLeftPos`、手写的 `GetCenterPos`）仍照常可用
        // ⇒ 本批没有动到族里别的东西。
        " print('B290 sibling1=' .. ok(function() return room:GetTopLeftPos() end))"
        " print('B290 sibling2=' .. ok(function() return room:GetCenterPos() end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b290.lua");
    static_cast<void>(result);
    return 0;
}
'''


class RoomShapeBatch290Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b290-")
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

    def test_the_shape_is_read_from_the_end_of_the_two_hop_chain(self):
        """★★ 三块的同一偏移各放 12 / 8 / 9 ⇒ 必须读回 **9**。

        这条是本文件的核心判据：数据行没挂上 ⇒ `room.GetRoomShape` 是 `nil`；
        少走第一跳（直接读 `Room+0x5C`）⇒ 答 12；少走第二跳（读描述符 `+0x5C`）⇒ 答 8；
        两跳都走对 ⇒ 答 9。两条诱饵都挑的是**合法的形状值**，所以读错了不会"看起来像没读到"。
        """
        out = self.run_scenario("shape")
        self.assertIn("B290 roomkind=userdata", out)
        self.assertIn("B290 fn=function", out)
        #: ★ 整数（PC 返回 `int`），不是别的类型。
        self.assertIn("B290 kind=number", out)
        self.assertIn("B290 shape=9", out)
        self.assertNotIn("B290 shape=12", out)
        self.assertNotIn("B290 shape=8", out)
        #: 与枚举表逐值对照（模组的实际用法）。
        self.assertIn("B290 isltl=true", out)
        self.assertIn("B290 is2x2=false", out)

    def test_one_x_one_room_reports_the_same_number_as_the_enum(self):
        """形状 1 ⇒ 读回 1 且 `== RoomShape.ROOMSHAPE_1x1`。

        ★ 这一场与"链断了"的降级值**同值**（都是 1），所以它单独不能判"读到了"还是"降级了"；
        把两者分开的是下面 `zero` 那一场（配置块真写着 0 时必须答 0）。
        """
        out = self.run_scenario("roomonly")
        self.assertIn("B290 shape=1", out)
        self.assertIn("B290 is1x1=true", out)

    def test_zero_in_memory_is_answered_as_zero_not_as_the_fallback(self):
        """★★ 配置块里真写着 **0** ⇒ 必须答 **0**。

        与"链断了答 1"合起来才说明降级值选对了：若把 `FieldMissing::One` 写成 `Zero`（或反过来
        把"读到 0"也当成"没读到"），这两场里必有**至少一场**是错的 —— 单看一场看不出来。
        PC 侧的行为也是"读到什么答什么"，只有指针链断开时才退化成常量 1。
        """
        out = self.run_scenario("zero")
        self.assertIn("B290 kind=number", out)
        self.assertIn("B290 shape=0", out)
        self.assertIn("B290 is1x1=false", out)
        self.assertIn("B290 isltl=false", out)

    def test_a_broken_chain_degrades_to_one_without_erroring(self):
        """★★ 链上任一环为空 ⇒ 答 **1**、**不抛 Lua 错误**（三种断法各验一遍）。

        这正是 PC 自己的口径：`0x444C35`（描述符为空）与 `0x444C3C`（`Data` 为空）两处 `je`
        都跳到 `0x444C42 mov eax,0x1` —— 而 1 就是 `ROOMSHAPE_1x1`。
        ★ 为什么不抛错：报错会把**整条模组回调**摘掉（批 250 定案），比"这次答了个保守值"
        严重得多；本族语料拿它直接与枚举比（`room:GetRoomShape() == RoomShape.ROOMSHAPE_1x2`），
        答 1 只会让那一个分支不进，答错类型才会炸掉整条回调。
        """
        for scenario in ("nodesc", "nodata", "noroom"):
            with self.subTest(scenario=scenario):
                out = self.run_scenario(scenario)
                #: 房间句柄本身仍在（批次 250：给空壳、不给 nil）⇒ 说明走的是"字段行降级"，
                #: 不是"连方法都挂不上"。
                self.assertIn("B290 roomkind=userdata", out)
                self.assertIn("B290 fn=function", out)
                self.assertIn("B290 kind=number", out)
                self.assertIn("B290 shape=1", out)
                self.assertIn("B290 is1x1=true", out)

    def test_argument_gate_is_exactly_one(self):
        """参数闸门 = **恰好一个**（只有冒号调用压进来的 `self`），多给一个就报错。

        ★ 与批次 069 给 `Room` 的**引擎方法行**打的那个补丁不同：那条要减掉 `self` 再比，
        本批是**字段行**，闸门天然按"栈上 1 个值"算 ⇒ 冒号调用（`room:GetRoomShape()`）
        正好满足，不需要任何改动。语料 19 处全是冒号写法（含
        `game:GetRoom():GetRoomShape()` 这种链式调用）。
        """
        out = self.run_scenario("shape")
        self.assertIn("B290 args=false", out)
        self.assertIn("Room:GetRoomShape accepts no arguments", out)
        #: 点号 + 显式 self 也是 1 个参数 ⇒ 允许。
        self.assertIn("B290 dotcall=true", out)
        #: 对照：同族老方法仍照常可用 ⇒ 本批没有动到族里别的东西。
        self.assertIn("B290 sibling1=true", out)
        self.assertIn("B290 sibling2=true", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与降级档 / 偏移常量 / 挂载点 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        field_api = FIELD_API.read_text(encoding="utf-8")

        for name, index, offset_name, kind, missing, receipt in FIELD_APIS:
            with self.subTest(api=f"Room:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Room, 1, 0x{index:04X}), ApiDomain::Room, "Room", "{name}"',
                    catalog, f"目录里没有 Room:{name}")
                #: ★ 行住在 `remaining_api.cpp` 自己的 TU 里（家族的行表必须与家族同 TU，
                #:   否则 `test_field_api_rows.py` 的挂载判据与契约门禁都会报红）。
                self.assertRegex(
                    remaining,
                    rf"\{{\s*(?i:0x0401{index:04x}),\s*{offset_name},\s*0x00,\s*"
                    rf"FieldKind::{kind},\s*FieldMissing::{missing},\s*"
                    rf"FieldReceipt::{receipt},\s*0xFF\}}",
                    f"数据行缺失或形状/降级档/接收者不对：Room:{name}")
                self.assertRegex(constants,
                                 rf"inline constexpr uintptr_t {offset_name}\s*=\s*0x5C;")
                #: ★★ 反回归：这条**不许**被塞进引擎方法行表（没有引擎函数可调，
                #:   塞进去会变成"每次调用都要核对入口字"⇒ 真机上恒降级）。
                self.assertNotRegex(remaining, rf"0x0401{index:04x}[^\n]*EngineCallShape")

        #: ★ 新接收者存在，且**实现里真的走了那两跳**（`Room+0x8` 与 `RoomDescriptor.Data`）。
        self.assertRegex(field_api, r"RoomConfigData\s*=\s*7")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        self.assertRegex(isaac, r"case\s+FieldReceipt::RoomConfigData\s*:")
        self.assertRegex(
            isaac,
            r"LoadPointerAt\(engine_memory::AddressOf\(room\),\s*kRoomDescriptorPointerOffset")
        self.assertRegex(isaac,
                         r"LoadPointerAt\(descriptor,\s*layout::kRoomDescriptorDataOffset")

        #: ★ 降级档 `One` 必须存在，而且**真的被压成 1**（不是落到 `Zero` 的默认分支）。
        #: 允许分支体前面夹注释行（本批在那里写了"为什么是 1"）—— 判据是"这一支压 1"，
        #: 不是"这一支与标签同行"。
        self.assertRegex(field_api, r"One\s*=\s*4")
        self.assertRegex(isaac,
                         r"case\s+FieldMissing::One\s*:(?:\s*//[^\n]*)*\s*"
                         r"lua_pushinteger\(state,\s*1\)")

        #: 挂载点：本族三张表都经由同一处 `AttachOwnerMethods(..., "Room", ...)`。
        self.assertRegex(remaining, r"AttachOwnerMethods\(state, \"Room\",[^;]*kRoomFieldApis")

    def test_the_evidence_and_the_pc_yardstick_are_recorded(self):
        """★ 常量段必须写明"为什么是两跳"、三条独立读者、以及"为什么不搬 PC 的偏移"。

        这条不是形式主义：形状**不在 `Room` 上**，而"PC 用 `Data+0x48`、Switch 用 `Data+0x5C`"
        正是最容易顺手照抄的地方（批次 269/289 都被咬过同一口）。少了这三条，后人只看到
        "某处读过一次 `+0x5C`"。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("inline constexpr uintptr_t kRoomConfigShapeOffset = 0x5C;", constants)
        #: PC 侧那条链（两跳 + 缺省常量 1）。★ 按**不区分大小写**比对：常量段里
        #: `0x444C30` 出现在散文中，而 `0x444c42` 是反汇编清单的原样（`pc_exe_binding.py`
        #: 给出的就是小写）。判据是"这个地址被写进来了"，不是"十六进制字母是大写"。
        folded = constants.lower()
        for va in ("0x444C30", "0x444C42"):
            self.assertIn(va.lower(), folded, f"PC 侧证据地址 {va} 没有写进常量段")
        #: Switch 侧三条具名读者。
        for va in ("0x48453C", "0x484558", "0x45F974"):
            self.assertIn(va.lower(), folded, f"Switch 侧证据地址 {va} 没有写进常量段")
        #: "不能从 PC 搬"的理由（PC 32 位 / Switch 64 位、两处偏移都不同）。
        self.assertIn("Data+0x48", constants)
        self.assertIn("Data+0x5C", constants)
        #: 布局表指针（逐条可复核的那一份）。
        self.assertIn("tools/layout_tables/room_descriptor.json", constants)

    def test_the_layout_table_row_is_confirmed_with_semantic_evidence(self):
        """布局表 `Data.Shape` 行必须是 `confirmed`，且**至少有一条 `semantic` 证据**。

        本批给这一行补了 4 条新证据（`Room::IsLShapedRoom` 与 `Room::GetLRoomAreaDesc` 各一组
        access + semantic）—— `--verify` 会重新反汇编核对，而"9..12 是四个 L 形"这条
        就是形状语义的锚点（不然只是一格被读过 4 次的整数）。
        """
        table = json.loads(LAYOUT.read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in table["rows"]}
        self.assertIn("Data.Shape", rows)
        row = rows["Data.Shape"]
        self.assertEqual(row["confidence"], "confirmed")
        self.assertEqual(row["offset"], 92)
        self.assertEqual(row["width"], 4)
        self.assertEqual(row["nested_in"], "Data")
        kinds = [e["kind"] for e in row["evidence"]]
        self.assertIn("semantic", kinds)
        self.assertGreaterEqual(kinds.count("access"), 2)
        #: 本批补的那两条具名读者必须在表里（两组，各一条 access + 一条 semantic）。
        functions = [e["function"] for e in row["evidence"]]
        for symbol in ("_ZNK15IsaacRepentance4Room13IsLShapedRoomEv",
                       "_ZNK15IsaacRepentance4Room16GetLRoomAreaDescEv"):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, functions, f"布局表里没有 {symbol} 的证据")
        #: 形状的取值锚点：9..12（`sub #0x9` + `cmp #0x3/#0x4`）。
        immediates = [e.get("immediate") for e in row["evidence"] if e["kind"] == "semantic"]
        self.assertIn(9, immediates)


if __name__ == "__main__":
    unittest.main()
