"""门禁：`GridEntity:SetType(eGridEntityType)`（批次 308，2026-10-03）—— `GridEntity` 家族的
**第一张字段数据行** + 新种类 `FieldKind::U32FromArg`。

## 这一条是什么

| API | 契约 | 引擎侧 | 语料调用点 |
| --- | --- | --- | --- |
| `GridEntity:SetType(eGridEntityType Type)` | `GridEntity.md:91/93`（`void SetType ( GridEntityType Type )`） | 写 `GridEntity + 0x08`（= `GetType()` 读的那一格） | 1 |

★ 谁在调：`BOIStageAPI15/scripts/stageapi/room/roomHandler.lua:1316` ——
`rockToConvert:SetType(GridEntityType.GRID_ROCK_GOLD)` **紧跟** `rockToConvert:Init(seed)`，
把一块石头变成**金石头**（金色是 `Init` 重跑子类初始化带来的；`Init` 我们已有，批次 272）。
⇒ 真机的顺带判据：把这两行对着同一块石头执行，石头**当场变金色**。

## 凭什么说它是一次"字段写"

★★ **PC 的绑定本体自己就是两条指令**（`GridEntity:SetType @ 0x6DAD50`）：
`mov eax,[ebp+0x8]`（实参）+ `mov [ecx+0x4],eax`（写进类型那一格）+ `ret 0x4`
—— **不调任何引擎函数**。

★★ **Switch 侧两处具名证据**（都在 `remaining_api.cpp` 的 `kGridEntityFieldApis` 段注释里）：
* `Room::CreateGridEntity(eGridEntityType, unsigned) @ 0x37FC50`：`0x380084 str w20, [x21, #0x8]`
  （w20 = 类型实参）⇒ 类型落在 `+0x08`；
* `GridEntity::IsRock() @ 0x37FBEC` 读 `+0x08` 后按岩石族的位集（`0x03D0001F`）判类，
  与 `GridEntityType.md` 的岩石族逐项吻合。

★ PC `+0x4` 与 Switch `+0x08` 差 4 字节 = **指针宽度差**（Switch 对象首字是 8 字节 vptr）
—— 与 `Room` 网格实体表（PC `+0x24` / Switch `+0x30`）同一类；**数值不许平移**。

## 宿主验到了什么、没验到什么

* **验到**（字段行没有入口指纹 ⇒ 伪造内存里的字节真被写）：
  - ★★ **写进了 `GetType()` 读的那一格**：`SetType(t)` 之后 **C++ 侧直接读那块伪造内存**
    与 `ge:GetType()` 都必须等于 `t`（两条独立读数，且与 `GetType` 的既有实现互证）；
  - ★ **只取低 32 位**（PC 的 `mov [ecx+0x4],eax` 是 32 位存储）；
  - ★ **返回值个数 = 0**（PC 是 `void`）；
  - **参数闸门**：少给 / 多给 / 非整数都报错，消息里现拼出 `GridEntity:SetType`；
  - **接收者闸门**：不是网格实体句柄 ⇒ **报错**（`CheckGridEntityHandle`）；
  - ★ **句柄还活着但底层指针已失效** ⇒ **什么都不写、也不抛错**、返回 0 个值
    （`IsLiveGridEntityPointer` 判 0 ⇒ 共享处理器的静默降级分支；用例里用"vptr 不在网格实体区间"
    的假对象造出这一支，宿主里**可达**）。
* **没验**：真机上 `+0x08` 就是类型（宿主里夹具与实现引用同一个常量，自己证不了自己）
  ⇒ 真机项 = 作业单 **V58**（读数判据 + 顺带看石头变金色）。
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
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
FIELD_ROWS_TEST = ROOT / "runtime" / "tests" / "test_field_api_rows.py"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

API_INDEX = 0x00D7
BINDING_ID = 0x0E0100D7
OFFSET_NAME = "kGridEntityTypeOffset"
#: 夹具里两个假网格实体的初值（互不相同 ⇒ 写错对象会红）。
TYPE_A = 0x0A
TYPE_B = 0x0B
#: 写进去的值（`0x1234` 与"低 32 位"各一次）。
NEW_TYPE = 0x1234
WIDE_TYPE = 0x100000002          # ⇒ 低 32 位 = 2
WIDE_LOW = 0x2


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存：
//   g_ModuleBytes[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                       = Game*
//   g_GameBytes + kGameSeedsObjectOffset…  （不碰）
//   g_RoomBytes[+0x14]/[+0x18]             = 宽 / 高（`ReadRoomGridDimensions` 要）
//   g_RoomBytes[+0x30 + 8*i]               = 第 i 格的网格实体指针
//   假网格实体 A：首字 = base + kGridEntityVtableOffset（★ `IsLiveGridEntityPointer` 要它落在区间里）
//   假网格实体 B：首字 = 0（**活着但判失效**的那一支）
namespace {

constexpr std::uint32_t kWidth = GRID_W;
constexpr std::uint32_t kHeight = GRID_H;
constexpr std::size_t kEntitySize = 0x60;

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_EntityA;
std::vector<unsigned char> g_EntityB;
std::uintptr_t g_EngineBase = 0;

//: 模块块要同时盖住：网格实体 vtable 区间（判存活用）与 `g_Game` 全局槽。
static_assert(kGridEntityVtableRangeEndOffset + 8 <= kGameOwnerGlobalSlotOffset + 8,
              "module block sizing assumption changed");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uint32_t ReadU32(const std::vector<unsigned char>& block, std::size_t offset) {
    std::uint32_t value = 0;
    std::memcpy(&value, block.data() + offset, sizeof(value));
    return value;
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeWorld() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_GameBytes.assign(0x100, 0);
    g_RoomBytes.assign(kRoomGridEntityTableOffset + 2 * sizeof(std::uintptr_t) + 8, 0);
    g_EntityA.assign(kEntitySize, 0);
    g_EntityB.assign(kEntitySize, 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    //: ★ A 的首字落在网格实体 vtable 区间里 ⇒ 判"活着"；B 的首字是 0 ⇒ 判"失效"。
    WriteAt<std::uint64_t>(g_EntityA, 0, g_EngineBase + kGridEntityVtableOffset);
    WriteAt<std::uint32_t>(g_EntityA, kGridEntityTypeOffset, TYPE_A_VALUE);
    WriteAt<std::uint32_t>(g_EntityB, kGridEntityTypeOffset, TYPE_B_VALUE);

    WriteAt<std::uint32_t>(g_RoomBytes, kRoomGridWidthOffset, kWidth);
    WriteAt<std::uint32_t>(g_RoomBytes, kRoomGridHeightOffset, kHeight);
    WriteAt<std::uintptr_t>(g_RoomBytes, kRoomGridEntityTableOffset, AddressOf(g_EntityA));
    WriteAt<std::uintptr_t>(g_RoomBytes, kRoomGridEntityTableOffset + sizeof(std::uintptr_t),
                            AddressOf(g_EntityB));

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = reinterpret_cast<void*>(AddressOf(g_RoomBytes));
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    PublishFakeWorld();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    static const char* kWrite =
        "local room = Game():GetRoom()"
        " local a = room:GetGridEntity(0)"
        " print('B308 kind=' .. type(a) .. ',' .. type(a and a.SetType))"
        " print('B308 before=' .. tostring(a:GetType()))"
        " print('B308 ret=' .. select('#', a:SetType(NEW_TYPE_VALUE)))"
        " print('B308 after=' .. tostring(a:GetType()))"
        // 另一个对象（B）不动它 ⇒ 它必须还是初值（专抓"写到同一个对象上"）。
        " local b = room:GetGridEntity(1)"
        " print('B308 btype=' .. tostring(b:GetType()))";
    static const char* kWide =
        "local a = Game():GetRoom():GetGridEntity(0)"
        " print('B308 wideret=' .. select('#', a:SetType(WIDE_VALUE)))"
        " print('B308 widetype=' .. tostring(a:GetType()))";
    static const char* kArgs =
        "local a = Game():GetRoom():GetGridEntity(0)"
        " local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function msg(f) return tostring(select(2, pcall(f))) end"
        " print('B308 noargs=' .. ok(function() return a:SetType() end))"
        " print('B308 noargsmsg=' .. msg(function() return a:SetType() end))"
        " print('B308 twoargs=' .. ok(function() return a:SetType(1, 2) end))"
        " print('B308 str=' .. ok(function() return a:SetType('x') end))"
        " print('B308 float=' .. ok(function() return a:SetType(1.5) end))"
        " print('B308 nil=' .. ok(function() return a:SetType(nil) end))"
        // 合法的整数要放行（否则上面几条"报错"可能是"一律报错"造成的假绿）。
        " print('B308 intok=' .. ok(function() return a:SetType(NEW_TYPE_VALUE) end))";
    static const char* kBadRecv =
        "local a = Game():GetRoom():GetGridEntity(0)"
        " local f = a.SetType"
        " local function ok(g) return tostring(select(1, pcall(g))) end"
        " local function msg(g) return tostring(select(2, pcall(g))) end"
        " print('B308 table=' .. ok(function() return f({}, 1) end))"
        " print('B308 tablemsg=' .. msg(function() return f({}, 1) end))";
    static const char* kDead =
        "local b = Game():GetRoom():GetGridEntity(1)"
        " print('B308 deadkind=' .. type(b))"
        " local okv, err = pcall(function() return select('#', b:SetType(NEW_TYPE_VALUE)) end)"
        " print('B308 deadok=' .. tostring(okv) .. ' ret=' .. tostring(err))"
        " print('B308 deadtype=' .. tostring(b:GetType()))";

    const char* script = nullptr;
    if (std::strcmp(scenario, "write") == 0) {
        script = kWrite;
    } else if (std::strcmp(scenario, "wide") == 0) {
        script = kWide;
    } else if (std::strcmp(scenario, "args") == 0) {
        script = kArgs;
    } else if (std::strcmp(scenario, "badrecv") == 0) {
        script = kBadRecv;
    } else if (std::strcmp(scenario, "dead") == 0) {
        script = kDead;
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b308.lua");
    static_cast<void>(result);
    //: ★ 结账：C++ 侧**独立读**两个假对象的类型格（不经过 Lua、也不经过 `GetType` 的实现）。
    std::printf("B308 raw_a=%u\n", ReadU32(g_EntityA, kGridEntityTypeOffset));
    std::printf("B308 raw_b=%u\n", ReadU32(g_EntityB, kGridEntityTypeOffset));
    return 0;
}
'''
HARNESS = (HARNESS
           .replace("GRID_W", "13").replace("GRID_H", "7")
           .replace("TYPE_A_VALUE", hex(TYPE_A))
           .replace("TYPE_B_VALUE", hex(TYPE_B))
           .replace("NEW_TYPE_VALUE", hex(NEW_TYPE))
           .replace("WIDE_VALUE", hex(WIDE_TYPE)))


class GridEntitySetTypeBatch308Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b308-")
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

    def test_set_type_writes_the_same_slot_get_type_reads(self):
        """★★ 写进去的那一格**就是** `GetType()` 读的那一格。

        三条一起成立才算过：
          ① `SetType(0x1234)` 之后 `ge:GetType()` 答 `0x1234`（往返）；
          ② ★ **C++ 侧直接读那块伪造内存**（`B308 raw_a`）也必须是 `0x1234`
             —— 这一条不依赖 `GetType` 的实现，是独立读数；
          ③ 同一房间里**另一个**网格实体的类型格**不许被动**（`B308 raw_b` 仍是初值）
             —— 专抓"写到同一个对象上"这类错法。
        """
        out = self.run_scenario("write")
        self.assertIn("B308 kind=userdata,function", out)
        self.assertEqual(self.value(out, "B308 before"), str(TYPE_A))
        self.assertEqual(self.value(out, "B308 ret"), "0", "PC 是 `void` ⇒ 必须返回 0 个值")
        self.assertEqual(self.value(out, "B308 after"), str(NEW_TYPE))
        self.assertEqual(self.value(out, "B308 raw_a"), str(NEW_TYPE),
                         "C++ 侧直接读那一格也必须变（独立于 `GetType` 的实现）")
        self.assertEqual(self.value(out, "B308 raw_b"), str(TYPE_B),
                         "另一个对象的类型格不许被动")
        self.assertEqual(self.value(out, "B308 btype"), str(TYPE_B))

    def test_only_the_low_32_bits_are_stored(self):
        """★ PC 的 `mov [ecx+0x4],eax` 是 **32 位**存储 ⇒ 传 64 位只取低半。

        `SetType(0x100000002)` ⇒ 那一格必须是 `2`（不是 `0`、也不是原值）。
        """
        out = self.run_scenario("wide")
        self.assertEqual(self.value(out, "B308 wideret"), "0")
        self.assertEqual(self.value(out, "B308 widetype"), str(WIDE_LOW))
        self.assertEqual(self.value(out, "B308 raw_a"), str(WIDE_LOW))

    def test_argument_gate(self):
        """参数闸门：恰好一个整数；消息里现拼出 `GridEntity:SetType`。合法调用要放行。"""
        out = self.run_scenario("args")
        self.assertIn("B308 noargs=false", out)
        self.assertIn("GridEntity:SetType expects one integer argument", out)
        self.assertIn("B308 twoargs=false", out)
        self.assertIn("B308 str=false", out)
        self.assertIn("B308 float=false", out)
        self.assertIn("B308 nil=false", out)
        self.assertIn("B308 intok=true", out)

    def test_a_non_grid_entity_receiver_is_rejected(self):
        """★ 接收者不是网格实体句柄 ⇒ **报错**（`CheckGridEntityHandle`，与 `GetType` 同口径）。

        手法：把方法取出来当普通函数、用一个**表**当接收者 —— 这时栈上第 1 格不是网格实体句柄。
        """
        out = self.run_scenario("badrecv")
        self.assertIn("B308 table=false", out)
        self.assertIn("expected a GridEntity", out)

    def test_a_dead_handle_is_a_silent_no_op(self):
        """★★ 句柄在、但底层指针已失效 ⇒ **什么都不写、不抛错、返回 0 个值**。

        夹具里对象 B 的首字是 0（不在网格实体 vtable 区间里）⇒ `IsLiveGridEntityPointer` 判 0
        ⇒ 走共享处理器的静默降级分支。★ 这一支在宿主里**可达**（与批 304 的结论一致）。
        """
        out = self.run_scenario("dead")
        self.assertIn("B308 deadkind=userdata", out)
        self.assertIn("B308 deadok=true ret=0", out)
        self.assertEqual(self.value(out, "B308 raw_b"), str(TYPE_B), "失效句柄不许写任何东西")

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行形状 / 新种类 / 早退分支 / 偏移常量字面值 / 门禁登记。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING.read_text(encoding="utf-8")
        header = FIELD_HEADER.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        self.assertIn(
            f'MakeId(ApiDomain::Isaac, 1, 0x{API_INDEX:04X}), ApiDomain::Isaac, "GridEntity", '
            f'"SetType"',
            catalog, "目录里没有 GridEntity:SetType")
        self.assertIn("GridEntity.md:91/93", catalog, "目录行的注释里没有引用契约行")
        #: 数据行形状：新种类 + `FieldReceipt::GridEntity` + `0xFF` 探针位。
        self.assertRegex(
            remaining,
            rf"\{{\s*(?i:0x{BINDING_ID:08X}),\s*{OFFSET_NAME},\s*(?:0x00|0),\s*"
            rf"FieldKind::U32FromArg,\s*FieldMissing::Zero,\s*FieldReceipt::GridEntity,\s*0xFF\}}",
            "数据行缺失或形状不对：GridEntity:SetType")
        #: ★ 反回归：不许被塞进引擎方法行表（引擎里没有同名方法）。
        self.assertNotRegex(remaining, rf"0x{BINDING_ID:08X}[^\n]*EngineCallShape")
        #: 三张表一起挂（手写处理器 + 字段行 + 引擎方法行）。
        self.assertIn("kGridEntityFieldApis", remaining)
        self.assertIn("RowCount(kGridEntityFieldApis)", remaining)

        #: 新 kind 登记 + 共享处理器认它 + 进"返回 0 个值"的早退分支。
        self.assertRegex(header, r"U32FromArg\s*=\s*17,")
        isaac = (ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp").read_text(
            encoding="utf-8")
        self.assertIn("case FieldKind::U32FromArg", isaac)
        self.assertRegex(isaac, r"RowReturnsNoValues\(FieldKind kind\)[\s\S]{0,260}U32FromArg")
        self.assertRegex(isaac, r"wantsIntegerArgument[\s\S]{0,120}U32FromArg")
        #: 写侧必须走受保护写原语。
        block = isaac[isaac.index("case FieldKind::U32FromArg"):]
        block = block[:block.index("case FieldKind::U32:")]
        self.assertIn("engine_memory::WriteField", block, "写侧必须走 `WriteField`")
        self.assertIn("IsEngineMemoryWritable", block, "写侧必须过 `IsEngineMemoryWritable`")

        #: ★ 偏移常量写死（接线用例的职责就是钉字面值）。
        self.assertRegex(constants, rf"inline constexpr uintptr_t {OFFSET_NAME}\s*=\s*0x08;")

        #: ★★ 门禁登记（漏登记 ⇒ 整张表对门禁**隐形**，静默）。
        gate = FIELD_ROWS_TEST.read_text(encoding="utf-8")
        self.assertIn("kGridEntityFieldApis", gate, "门禁里没登记 kGridEntityFieldApis")
        self.assertIn('"GridEntity": {"GridEntity"}', gate,
                      "OWNERS_BY_RECEIPT 里没加 GridEntity")


if __name__ == "__main__":
    unittest.main()
