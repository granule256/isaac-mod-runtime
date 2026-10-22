"""门禁：`Room` 的房间边界两条（批次 289，2026-10-02）。

## 这一批是什么

| API | 契约 | 引擎侧依据 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Room:GetTopLeftPos()` | `Room.md:566` | 没有同名函数 ⇒ 读 `+0x1C`（`Vector2`） | `Vector2Pair` | 32 |
| `Room:GetBottomRightPos()` | `Room.md:119` | 没有同名函数 ⇒ 读 `+0x24`（`Vector2`） | `Vector2Pair` | 36 |

两条都走**字段读取型数据行**（`remaining_api.cpp` 的 `kRoomFieldApis`），**0 字节代码**。
偏移的由来（PC↔Switch 为什么不能互搬、四条独立互证、"哪一格是左上/右下"怎么判）写在
`runtime_constants.hpp` 的**批次 289 段**；逐条可复核的证据在 `tools/layout_tables/room.json`
的 `TopLeft` / `BottomRight` 两行（`build_layout_table.py --verify` 会重新反汇编核对）。

## 为什么接收者用 `FieldReceipt::Room`（而不是从栈上取）

`FieldReceipt::Room` 的含义是"接收者**不从 Lua 栈上取**，而是解析**当前房间**"
（`ReadCurrentGameRoom` → `Game + 当前房间槽`，与 `Game:GetRoom()` 同一条链）。
这对本批是**必须**的，也是**正确**的，两条理由：

1. **必须**：本批语料里没有一处用点号把房间当普通参数传，全是对**房间句柄**做方法调用；
   而 `Room` 句柄（`RoomHandle`）是个**不持引擎指针的空壳**（只有一个保留字），
   从它身上取不到 `Room*` —— `FieldReceipt::Level` / `Music` 是同样的处境。
2. **正确**：本批 68 处调用点的接收者**逐条核过，全部是"当前房间"**：
   - `IsaacOnTwitchReloaded`：`local room = Game():GetRoom()`（events.lua 里 20 余处）、
     `local r = Game():GetRoom()`（events.lua:504）、`local game = Game()` → `game:GetRoom()`
     （activeItems.lua:32）；
   - `BOIStageAPI15`：`shared.Room = shared.Game:GetRoom()`（basic.lua:305/319、
     saveSystem.lua:446）；
   - `RepentancePlus`：`local room = game:GetRoom()`（`local game = Game()`，main.lua:12）。
   ⇒ 没有一处是 `Level:GetRoomByIdx(i):GetTopLeftPos()` 这类"**别的**房间"，所以
   "恒定解析当前房间"与 PC 的方法接收者在语料范围内**语义等价**。
   （★ 这条与批次 259 `GetClampedPosition` 之类**手写**处理器不同：手写处理器能从头查
   `Isaac.GetRoom()`/`Game():GetRoom()` 交出来的句柄是否与当前房间是同一个对象；
   本批走数据行，接收者只能由 receipt 决定，所以必须先把语料核干净。）

## 宿主验到了什么、没验到什么

* **验到**（字段行**没有入口指纹**，所以宿主里能读到真值）：
  - 写进 `0x1C` / `0x24` 的四个 float **原样**读回，且 `Room+0x1C` 落在返回值的
    `.X`/`.Y`、`Room+0x24` 落在另一条的 `.X`/`.Y`（**两条不许读同一格**）；
  - 返回的是**真正的 Lua `Vector`**（userdata：`:Length()` 能调、`+` 能用），
    不是 `nil`、不是一张只有 `X`/`Y` 的表；
  - ★ **按 float 读**（写 `-13.5` 读回 `-13.5`，不是 `0xC1580000` 那个整数）——
    这一格专抓"照抄批次 287 的 `U32` 写法"；
  - 参数闸门 = **恰好一个**（只有冒号调用压进来的 `self`）；
  - 拿不到房间时压 **`Vector(0,0)`**（不压 `nil`、不报错）—— 语料拿到返回值第一件事
    几乎都是取分量（`r:GetTopLeftPos().Y + 10`），压 `nil` 会 `attempt to index a nil value`
    把**整条模组回调**摘掉。
* **没验**：真机上 `0x1C` / `0x24` 到底是不是那两格（宿主里"偏移对不对"是同一张表的两处
  引用同一个常量，自己证不了自己）、以及真机上的**数值**。⇒ 真机项 = 作业单 **V40**。
* **也没验**："接收者非零、但内存读不出来"那条降级分支（`ReadField` 失败）—— 它由所有
  字段行共享，且宿主的假内存永远可读，构造不出那一场；本文件只钉 `receiver == 0` 那条。
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

#: `(名字, 域内序号, 偏移常量, 第二半偏移, FieldKind)`。
#: ★ `第二半偏移` 是同一个 `Vector2` 的 Y：`X + 4`。写成别的值（例如 `X + 16`）会读到下一格。
FIELD_APIS = (
    ("GetTopLeftPos", 0x0026, "kRoomTopLeftPosOffset", 0x20, "Vector2Pair"),
    ("GetBottomRightPos", 0x0027, "kRoomBottomRightPosOffset", 0x28, "Vector2Pair"),
)

#: 夹具写进"房间"块的四格：`(左上.X, 左上.Y, 右下.X, 右下.Y)`。
#: **四个值互不相同**，否则"X/Y 写反"或"两条读同一格"都抓不住。
BOUNDS = (40.0, 120.0, 480.0, 320.0)
ZEROED = (0.0, 0.0, 0.0, 0.0)
#: ★ 非整数：专抓"按整数读"。若形状写成 `U32`/`Sum2U32` 一类，`-13.5` 会变成 `0xC1580000`
#: 或两次整数读取的怪值，下面那几条断言必红。
FRACTIONAL = (-13.5, 0.25, 1024.75, -0.5)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状与批次 259 的 `test_lua_room_position_fallback.py` 同源）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                        = "当前房间"（本批的桩直接把它当房间块）
//   g_RoomBytes[0x00 .. 0x40)               = 房间成员区（`0x1C`/`0x24` 是那两格）
//
// ★ 本批两条是字段行 ⇒ **没有入口指纹** ⇒ 宿主里能读到真值（这正是本批比批次 288 强的
//   一点：288 的第三条走引擎方法行，在宿主里必然降级）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
//: ★ 场景开关：`false` 时桩报 `GameNull` ⇒ `Game:GetRoom()` 给**空壳句柄**
//:   （批次 250 定的口径：不报错、不给 nil），两条字段行的接收者解析随之失败 ⇒ 走降级分支。
bool g_RoomAvailable = true;
std::uintptr_t g_EngineBase = 0;

//: 房间块必须盖住两格的**第二个 float**（`0x24 + 4`）。写在编译期，写小了当场炸。
static_assert(kRoomBottomRightPosOffset + 2 * sizeof(float) <= 0x40,
              "fake room block must cover both corners");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

struct Bounds {
    float topLeftX;
    float topLeftY;
    float bottomRightX;
    float bottomRightY;
};

void WriteBounds(const Bounds& bounds) {
    // ★ 第二格是 `X + 4`（同一个 `Vector2` 的 Y），不是 `+16`、也不是"下一个 Vector2"。
    WriteAt<float>(g_RoomBytes, kRoomTopLeftPosOffset, bounds.topLeftX);
    WriteAt<float>(g_RoomBytes, kRoomTopLeftPosOffset + 4, bounds.topLeftY);
    WriteAt<float>(g_RoomBytes, kRoomBottomRightPosOffset, bounds.bottomRightX);
    WriteAt<float>(g_RoomBytes, kRoomBottomRightPosOffset + 4, bounds.bottomRightY);
}

void PublishFakeRoom() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_RoomBytes.assign(0x40, 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    // "当前房间"就是这个假房间块（`ReadCurrentGameRoom` 的桩不看 ownerSlot）。
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
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

    // 三个场景：
    //   fields     —— 正常矩形（四格互不相同，且左上 < 右下）
    //   zeroed     —— 全 0（★ 0 是**合法坐标**，不是"没有"）
    //   fractional —— 非整数（★ 专抓"按整数读"）
    //   noroom     —— 拿不到房间 ⇒ 压 Vector(0,0)，**不压 nil、不报错**
    Bounds bounds{40.0F, 120.0F, 480.0F, 320.0F};
    if (std::strcmp(scenario, "fields") == 0) {
        // 默认值。
    } else if (std::strcmp(scenario, "zeroed") == 0) {
        bounds = Bounds{0.0F, 0.0F, 0.0F, 0.0F};
    } else if (std::strcmp(scenario, "fractional") == 0) {
        bounds = Bounds{-13.5F, 0.25F, 1024.75F, -0.5F};
    } else if (std::strcmp(scenario, "noroom") == 0) {
        g_RoomAvailable = false;
    } else {
        return 91;
    }

    PublishFakeRoom();
    WriteBounds(bounds);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local room = Game():GetRoom()"
        " print('B289 roomkind=' .. type(room))"
        " print('B289 fn=' .. type(room.GetTopLeftPos) .. ',' .. type(room.GetBottomRightPos))"
        " local tl = room:GetTopLeftPos()"
        " local br = room:GetBottomRightPos()"
        " print('B289 tlkind=' .. type(tl) .. ',' .. type(br))"
        " print('B289 tl=' .. tostring(tl))"
        " print('B289 br=' .. tostring(br))"
        " print('B289 tlxy=' .. string.format('%.4f,%.4f', tl.X, tl.Y))"
        " print('B289 brxy=' .. string.format('%.4f,%.4f', br.X, br.Y))"
        // 真 Vector（不是"只有 X/Y 的表"）：方法能调、运算符能用。
        " print('B289 lenmeth=' .. type(tl.Length))"
        " print('B289 lenok=' .. ok(function() return tl:Length() end))"
        " print('B289 addok=' .. tostring(tl + br))"
        // 与真机判据同向的两条恒等式：左上在右下之"前"、两点不是同一个点。
        " print('B289 order=' .. tostring(tl.X < br.X and tl.Y < br.Y))"
        " print('B289 distinct=' .. tostring(tl.X ~= br.X and tl.Y ~= br.Y))"
        // 参数闸门：字段行**恰好收一个**参数（只有冒号调用压进来的 self）。
        " print('B289 tlargs=' .. ok(function() return room:GetTopLeftPos(1) end))"
        " print('B289 brargs=' .. ok(function() return room:GetBottomRightPos(1) end))"
        " print('B289 tlargerr=' .. tostring(select(2, pcall(function()"
        "   return room:GetTopLeftPos(1) end))))"
        " print('B289 brargerr=' .. tostring(select(2, pcall(function()"
        "   return room:GetBottomRightPos(1) end))))"
        // 点号 + 显式 self 也是 1 个参数 ⇒ 允许（PC 的"无参"在 Lua 里就是"除 self 外无参"）。
        " print('B289 dotcall=' .. ok(function() return room.GetTopLeftPos(room) end))"
        // 对照：同族老方法（`Room:GetCenterPos`，手写处理器）拿同一个句柄仍照常可用
        // ⇒ 本批没有动到族里别的东西。
        " print('B289 sibling=' .. type(room.GetCenterPos))"
        " print('B289 siblingok=' .. ok(function() return room:GetCenterPos() end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b289.lua");
    static_cast<void>(result);
    return 0;
}
'''


class RoomBoundsBatch289Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b289-")
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

    def test_corners_are_read_from_the_two_distinct_cells(self):
        """★ 写进去什么就读回什么，而且是**两格不同的成员**（`0x1C` 与 `0x24`）。

        为什么这是硬判据：数据行没挂到 `Room` 页 ⇒ `room.GetTopLeftPos` 是 `nil`；
        两条的行互换（TopLeft 读 `0x24`）⇒ `distinct` 变 `false`、两条的四个值各自对调；
        `offset2` 写成 `X + 16` ⇒ `.Y` 读到别的格；形状写成 `U32` ⇒ `-13.5` 那场必红。
        """
        out = self.run_scenario("fields")
        self.assertIn("B289 roomkind=userdata", out)
        self.assertIn("B289 fn=function,function", out)
        self.assertIn("B289 tlkind=userdata,userdata", out)
        #: ★ 四个值互不相同 ⇒ 这一句同时证明"哪一格进哪一条"和"X/Y 没写反"。
        self.assertIn("B289 tlxy=40.0000,120.0000", out)
        self.assertIn("B289 brxy=480.0000,320.0000", out)
        self.assertIn("B289 order=true", out)
        self.assertIn("B289 distinct=true", out)

    def test_the_returned_value_is_a_real_vector(self):
        """返回值必须是**真正的 `Vector`**（能调 `:Length()`、能用 `+`），不是 `nil` 也不是表。

        语料里的用法（`Vector(room:GetTopLeftPos().X, i)`、`room:GetTopLeftPos().Y + 10`、
        `StageAPI.Lerp(shared.Room:GetTopLeftPos(), shared.Room:GetBottomRightPos(), 0.5)`）
        要求它既能取分量、又能当向量继续用 —— 一张只有 `X`/`Y` 的表能满足前者、满足不了后者。
        """
        out = self.run_scenario("fields")
        self.assertIn("B289 lenmeth=function", out)
        self.assertIn("B289 lenok=true", out)
        #: `__tostring` 走的是 `Vector` 的元表 ⇒ 顺带证明换元没换错。
        self.assertIn("B289 tl=Vector(40,120)", out)
        self.assertIn("B289 br=Vector(480,320)", out)
        #: `+` 是元表上的运算符（`Vector` 独有）⇒ 这张表确实是 Vector。
        self.assertIn("B289 addok=Vector(520,440)", out)

    def test_zero_is_a_valid_position_and_a_number(self):
        """全零 ⇒ 回 `Vector(0,0)`（**合法坐标**），而且是**数字**不是 `nil`。

        这一场钉的是"0 不等于没有"：若实现写成"读到 0 就当没有、压 `nil`"，
        模组里 `if room:GetTopLeftPos().X == 0` 那一支会静默失效。
        """
        out = self.run_scenario("zeroed")
        self.assertIn("B289 tlxy=0.0000,0.0000", out)
        self.assertIn("B289 brxy=0.0000,0.0000", out)
        self.assertIn("B289 tl=Vector(0,0)", out)

    def test_the_two_floats_are_read_as_floats_not_integers(self):
        """★ 非整数必须原样出来 —— 这一格专抓"照抄批次 287 的按整数读"。

        `-13.5` 的位模式是 `0xC1580000`；若按 `u32` 读，`.X` 会变成 `3244269568`；
        若 `offset2` 只当"第二个 u32 偏移"用同一套整数读法，`.Y` 也会是 `1048576000`
        （`0.25F` 的位模式）。两边的整数值都与这里断言的两个小数**不可能**相等。
        """
        out = self.run_scenario("fractional")
        self.assertIn("B289 tlxy=-13.5000,0.2500", out)
        self.assertIn("B289 brxy=1024.7500,-0.5000", out)
        self.assertNotIn("3244269568", out)
        self.assertNotIn("1048576000", out)

    def test_missing_room_degrades_to_a_zero_vector_without_erroring(self):
        """★★ 拿不到房间 ⇒ 压 **`Vector(0,0)`**、**不报错**、**不压 `nil`**。

        为什么这条比"值对"更重：语料拿到返回值第一件事几乎都是取分量
        （`r:GetTopLeftPos().Y + 10`、`Vector(room:GetTopLeftPos().X, i)`）——
        压 `nil` 会 `attempt to index a nil value`、压数字 `0` 会
        `attempt to index a number value`，两种都会把**整条模组回调**摘掉。
        口径与批次 249/259 对 `Room` 位置类方法定的那条**逐字相同**。

        实现上这一刻走的是 `ResolveFieldReceipt` 的 `receiver == 0` 分支 ⇒
        `PushMissingFieldValueForRow`（而不是通用的 `PushMissingFieldValue`）。
        """
        out = self.run_scenario("noroom")
        #: 房间句柄本身仍在（批次 250：给空壳、不给 nil）⇒ 说明走的是"字段行降级"，
        #: 不是"连方法都挂不上"。
        self.assertIn("B289 roomkind=userdata", out)
        self.assertIn("B289 fn=function,function", out)
        self.assertIn("B289 tlkind=userdata,userdata", out)
        self.assertIn("B289 tl=Vector(0,0)", out)
        self.assertIn("B289 br=Vector(0,0)", out)
        self.assertIn("B289 tlxy=0.0000,0.0000", out)
        self.assertNotIn("B289 tl=nil", out)

    def test_argument_gate_is_exactly_one(self):
        """参数闸门 = **恰好一个**（只有冒号调用压进来的 `self`），多给一个就报错。

        ★ 与批次 069 给 `Room` 的**引擎方法行**打的那个补丁不同：那条要减掉 `self` 再比，
        本批是**字段行**，闸门天然按"栈上 1 个值"算 ⇒ 冒号调用（`room:GetTopLeftPos()`）
        正好满足，不需要任何改动。语料里两条共 68 处**全是冒号写法**。
        """
        out = self.run_scenario("fields")
        self.assertIn("B289 tlargs=false", out)
        self.assertIn("B289 brargs=false", out)
        self.assertIn("Room:GetTopLeftPos accepts no arguments", out)
        self.assertIn("Room:GetBottomRightPos accepts no arguments", out)
        #: 点号 + 显式 self 也是 1 个参数 ⇒ 允许（PC 的"无参"在 Lua 里就是"除 self 外无参"）。
        self.assertIn("B289 dotcall=true", out)
        #: 对照：同族老方法仍照常可用 ⇒ 本批没有动到族里别的东西。
        self.assertIn("B289 sibling=function", out)
        self.assertIn("B289 siblingok=true", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与降级档 / 偏移常量 / 挂载点 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        field_api = FIELD_API.read_text(encoding="utf-8")

        for name, index, offset_name, second_half, kind in FIELD_APIS:
            with self.subTest(api=f"Room:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Room, 1, 0x{index:04X}), ApiDomain::Room, "Room", "{name}"',
                    catalog, f"目录里没有 Room:{name}")
                #: ★ 行住在 `remaining_api.cpp` 自己的 TU 里（家族的行表必须与家族同 TU，
                #:   否则 `test_field_api_rows.py` 的挂载判据与契约门禁都会报红）。
                self.assertRegex(
                    remaining,
                    rf"\{{\s*(?i:0x0401{index:04x}),\s*{offset_name},\s*0x{second_half:02x},\s*"
                    rf"FieldKind::{kind},\s*FieldMissing::Zero,\s*"
                    rf"FieldReceipt::Room,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档/第二半偏移不对：Room:{name}")
                self.assertRegex(constants,
                                 rf"inline constexpr uintptr_t {offset_name}\s*=\s*0x[0-9A-Fa-f]+;")
                #: ★★ 反回归：这两条**不许**被塞进引擎方法行表（它们没有引擎函数，
                #:   塞进去会变成"每次调用都要核对入口字"⇒ 真机上恒降级）。
                self.assertNotRegex(remaining, rf"0x0401{index:04x}[^\n]*EngineCallShape")

        #: ★ 新形状存在，而且**降级档不是 `FieldMissing`**（要压真 `Vector`）。
        self.assertRegex(field_api, r"Vector2Pair\s*=\s*9")
        self.assertRegex(isaac, r"case\s+FieldKind::Vector2Pair\s*:")
        self.assertRegex(isaac, r"PushMissingFieldValueForRow\s*\(lua_State\* state,\s*"
                                r"const FieldApiRow\* row\)")
        #: 降级路径必须走 `PushMissingFieldValueForRow`（它会区分 `Vector2Pair`），
        #: 而不是通用的 `PushMissingFieldValue`。
        #: ★ 2026-10-03（批次 301）：产品侧在 `receiver == 0` 分支的最前面插了一道**共享早退闸**
        #:   ——「返回 0 个值的写侧 kind」（`RowReturnsNoValues`，`BoolBitWrite` /
        #:   `BoolBitArrayOfWriteArg` / `U32OrWithArg`）在这里先 `return 0`，其余 kind 才落到
        #:   `PushMissingFieldValueForRow`。形状因此从"进分支即压值"变成"进分支先过一道闸再压值"，
        #:   旧正则 `\{\s*PushMissingFieldValueForRow` 不再匹配。
        #:   证据：批次 301 = `git show 99e2d3af`（`docs/改动日志-20261003.md` §六「另修一处共享行为」）；
        #:   现状源码 `isaac_api.cpp:8583`（`RowReturnsNoValues` 的说明在 `isaac_api.cpp:8584`）。
        #:   ★ 这里仍钉**同一件事**：那条分支还在、还在做"压降级值"这件事；
        #:   并且顺带确认中间那道闸就是批次 301 的 `RowReturnsNoValues`（不是被别的东西顶掉）。
        self.assertRegex(
            isaac,
            r"if\s*\(receiver == 0\)\s*\{\s*"
            r"(?://[^\n]*\n\s*)*"
            r"if\s*\(RowReturnsNoValues\(row->kind\)\)\s*\{\s*return 0;\s*\}\s*"
            r"(?://[^\n]*\n\s*)*"
            r"PushMissingFieldValueForRow\s*\(\s*state\s*,\s*row\s*\)")

        #: 挂载点：第 5/6 个实参就是这两条的表（原来是 `nullptr, 0`）。
        self.assertRegex(remaining, r"AttachOwnerMethods\(state, \"Room\",[^;]*kRoomFieldApis")

    def test_the_evidence_and_the_pc_yardstick_are_recorded(self):
        """★ 常量段必须写明"为什么不能从 PC 搬"、四条独立互证、以及 PC 侧那把尺。

        这条不是形式主义：`0x1C`/`0x24` 是**同一个 `Vector2` 族里的两格**，
        少了"`0x24` = `0x1C` + 正的跨度"这条结构性铁证，后人只能看到"某处读过一次"，
        分不清谁是谁 —— 而"哪一格是左上"正是这一批唯一的语义风险。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("inline constexpr uintptr_t kRoomTopLeftPosOffset = 0x1C;", constants)
        self.assertIn("inline constexpr uintptr_t kRoomBottomRightPosOffset = 0x24;", constants)
        #: 四条互证各自的关键地址（写入方 / 摆位置 / 矩形判定 / 房间中心）。
        for va in ("0x45B88C", "0x45B9EC", "0x45BA28", "0x45BA30", "0x45BA40", "0x45EF08",
                   "0x464560", "0x4645BC", "0x48437C", "0x456250"):
            self.assertIn(va, constants, f"Switch 侧证据地址 {va} 没有写进常量段")
        #: ★ PC 侧那把尺：PC 自己的取值器 + 同名判定函数的符号模式（加 Margin = 下界）。
        for va in ("0x432630", "0x432650", "0x7CF0A0"):
            self.assertIn(va, constants, f"PC 侧对齐证据 {va} 没有写进常量段")
        self.assertIn("0x432630", constants)
        #: "不能从 PC 搬"的理由（32 位 vs 64 位、`0x14/0x18` 在 Switch 是网格宽高）。
        self.assertIn("kRoomGridWidthOffset", constants)
        self.assertIn("kRoomGridHeightOffset", constants)
        #: 布局表指针（逐条可复核的那一份）。
        self.assertIn("tools/layout_tables/room.json", constants)
        self.assertRegex(constants, r"confirmed")

    def test_the_layout_table_rows_are_confirmed_with_semantic_evidence(self):
        """布局表两行必须是 `confirmed`，且 `width` 记 **8**（`Vector2` = 两个 float）。

        ★ `width` 记 16 是这一批最容易踩的坑：`0x1C`/`0x24` 都能被 16 整除，直觉上写 16
        更"整齐"，但 `Vector2` 真实宽度就是 8（与 `game.json` 的 `ScreenShakeOffset` 一致），
        而类型一致性门禁按"偏移整除"近似判"读得比记的宽"⇒ 记 16 会被判红。
        既有的 `RenderScrollOffset`（`width 16`）是**豁免行**，不许顺手改它。
        """
        layout = (ROOT / "tools" / "layout_tables" / "room.json").read_text(encoding="utf-8")
        table = json.loads(layout)
        rows = {row["name"]: row for row in table["rows"]}
        for name in ("TopLeft", "BottomRight"):
            with self.subTest(row=name):
                self.assertIn(name, rows, f"布局表里没有 {name} 行")
                row = rows[name]
                self.assertEqual(row["confidence"], "confirmed")
                self.assertEqual(row["kind"], "vector2")
                self.assertEqual(row["width"], 8)
                #: `confirmed` 行必须至少有一条 `semantic` 或 `device` 证据
                #: （只有"访问证据"的行不许 confirmed —— 这正是"哪一格是左上"的判据来源）。
                kinds = [e["kind"] for e in row["evidence"]]
                self.assertTrue({"semantic", "device"} & set(kinds),
                                f"{name} 行没有 semantic/device 证据：{kinds}")
                self.assertGreaterEqual(kinds.count("access"), 1)
        self.assertEqual(rows["TopLeft"]["offset"], 28)
        self.assertEqual(rows["BottomRight"]["offset"], 36)
        #: 豁免行不许被本批改动（它当年是唯一那个"没有值锚点也 confirmed"的例外）。
        self.assertEqual(rows["RenderScrollOffset"]["width"], 16)


if __name__ == "__main__":
    unittest.main()
