"""门禁：`GridEntity:Destroy(boolean)` / `GridEntity:PostInit()`（批次 304，2026-10-03）——
**"按 vtable 槽号调用"的第二批**（第 1 批是 303 的 `Entity:CanShutDoors`）。

## 这一批是什么

| API | 契约 | 槽号（Switch 的 `_ZTVGridEntity`） | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `GridEntity:Destroy(boolean Immediate)` | `GridEntity.md:21/23` | **槽 6** | `BoolOpt1`（尾部布尔可省） | 5 |
| `GridEntity:PostInit()` | `GridEntity.md:81/83` | **槽 2** | `Void0` | 2 |

两条都是**虚函数**：`GridEntity_Door`/`_Rock`/`_Statue`/`_TNT`/`_Web` 各有自己的 `Destroy`
⇒ 直调基类会**跳过子类行为**（真机上「石头炸掉不喷掉落物」就是这么来的）。
⇒ 走批 303 立的那条约定（`offset` 最高位置 1 = 虚调用、低 31 位 = 槽号）。

## ★★ 这一批同时修正了 303 的一处**槽位算法错误**

批 303 的实现里写了 `vptr + 0x10 + 槽号*8` —— **多加了 `0x10`**。正确算法是
**`vptr + 槽号*8`**：Itanium 里 `_ZTV<类>` 符号指向 `[offset-to-top][typeinfo]`，
而**对象首字存的就是 `_ZTV + 0x10`（= 槽 0 自己的地址）**。三条独立证据：

* `_ZTVEntity`(`0xA34F48`) + 0x10 = `0xA34F58` = `kEntityVtableRangeBeginOffset`
* `_ZTVEntity_NPC`(`0xA35DA8`) + 0x10 = `0xA35DB8` = `kEntityNpcVtableOffset`
* `_ZTVGridEntity`(`0xA37880`) + 0x10 = `0xA37890` = `kGridEntityVtableOffset`
* 另有代码侧印证：`IsEntityPlayer()` 拿**对象首字**与那个常量**直接相等**比较。

★ 303 的宿主用例**没能发现**它 —— 夹具当时引用了机制自己的常量（`kEngineVtableSlotsOffset`），
于是"写进假 vtable 的槽号"与"handler 读的槽号"**一起漂**（与批 302/303 那条
「改常量值验不出来」同源）。⇒ 本批把那个常量删掉、夹具改成按「对象首字 = 槽 0」**独立推导**
（写 `vptr + 槽号*8`，不引用机制的常量），并在夹具里用 `static_assert` 把三条证据钉住。

## 宿主验到了什么、没验到什么

* **验到**（宿主跳板是**桩**，但它记下**目标地址**与参数数组）：
  - ★★ **目标取自「接收者自己那张 vtable 的槽」**：两个网格实体的第一字指向**两张不同的假
    vtable**、同一槽里装两个不同哨兵 ⇒ 两次调用分别落到那两个地址（专抓「按固定偏移直调基类」）；
  - ★ **槽位算法**：夹具按「对象首字 + 槽号*8」独立推导 ⇒ 实现多写 `0x10` 会**红**；
  - ★ `x0` 是接收者自己；`Destroy(true)` 的第 1 个实参 = 1、`Destroy()` 省略时 = 0；
  - **返回 0 个值**（`PostInit`，PC 是 `void`）；
  - 槽里是 0 ⇒ **不调、不报错**；接收者不是网格实体 ⇒ **报错**（`expected a GridEntity`）。
* **没验**：真机上那两槽里真的是那两条实现（宿主里的 vtable 是我们自己造的）⇒ 真机项 = 作业单 **V54**。
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
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: 本批两条 API 的目录序号 / 名字 / 槽号常量 / 形状 / 参数个数。
APIS = (
    ("Destroy", 0x00D5, "kGridEntityVtableDestroySlot", 6, "BoolOpt1", 1),
    ("PostInit", 0x00D6, "kGridEntityVtablePostInitSlot", 2, "Void0", 0),
)

#: 夹具里两个网格实体的网格下标（各自指向一张**不同的**假 vtable）。
GRID_INDEX_A = 20
GRID_INDEX_B = 21
#: 两张假 vtable 的哨兵目标（互不相同 ⇒ 取错表/缓存成常量都会红）。
TARGET_A = "0x1A2B3C4D"
TARGET_B = "0x5E6F7081"
#: `PostInit`（槽 2）单独用第三个哨兵 —— 这样"把 Destroy 的槽号写成 2"会**红**（否则两者同值、验不出来）。
TARGET_C = "0x0BADF00D"


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"
#include "interfaces/lua/engine_method_api.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

extern "C" {
extern std::uint32_t g_HostEngineCallTrampolineCalls;
extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
}

// 伪造的引擎内存（形状抄批次 298）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                         = Room*（本夹具里同时当 Game/Level/Room 的锚点）
//   Room + kRoomGridEntityTableOffset + i*8  = 第 i 个 `GridEntity*`
//   网格实体首字                              = base + 假 vtable 偏移（存活判据要它落在家族区间里）
//   假 vtable 的槽 `slot`                     = 哨兵地址（本批唯一要读的东西）
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_GridABytes;
std::vector<unsigned char> g_GridBBytes;
std::uintptr_t g_EngineBase = 0;

//: 两张假 vtable 的偏移：都在 `GridEntity` 家族的区间里，且**互不相同**
//: （第二个就是第一个 + 8 —— 用"另一张表"来验"目标取自接收者自己的那一个"）。
constexpr std::uintptr_t kVtableAOffset = kGridEntityVtableOffset;         // 0xA37890
constexpr std::uintptr_t kVtableBOffset = kGridEntityVtableOffset + 8;     // 0xA37898

//: ★★★ **槽 i 在 `对象首字 + i*8`（不加 0x10）** —— 本夹具按这条**独立推导**，刻意**不引用**
//: 机制自己的常量（引用了就会"夹具与实现一起漂"，批 303 的 off-by-0x10 就是这么漏过去的）。
//: 判据（`_ZTV` 符号地址来自符号表，常量值都已取证过）：
//:   `_ZTVGridEntity` `0xA37880 + 0x10 = 0xA37890` = `kGridEntityVtableOffset`
//:   `_ZTVEntity_NPC` `0xA35DA8 + 0x10 = 0xA35DB8` = `kEntityNpcVtableOffset`
//:   `_ZTVEntity`     `0xA34F48 + 0x10 = 0xA34F58` = `kEntityVtableRangeBeginOffset`
//: ⇒ **对象首字 = `_ZTV + 0x10` = 槽 0 自己的地址**。
static_assert(kGridEntityVtableOffset == 0xA37890,
              "GridEntity 的对象首字应当 = _ZTVGridEntity(0xA37880) + 0x10");
static_assert(kEntityNpcVtableOffset == 0xA35DB8,
              "Entity_NPC 的对象首字应当 = _ZTVEntity_NPC(0xA35DA8) + 0x10");
static_assert(kEntityVtableRangeBeginOffset == 0xA34F58,
              "Entity 家族 vtable 区间起点应当 = _ZTVEntity(0xA34F48) + 0x10");
//: 假 vtable 的两张表都要落在家族区间里（否则句柄过不了存活判据）。
static_assert(kGridEntityVtableRangeBeginOffset <= kVtableAOffset &&
                  kVtableBOffset + 8 * 8 < kGridEntityVtableRangeEndOffset,
              "两张假 vtable 都要落在 GridEntity 家族的区间里");
//: 模块块要盖住两样：Game 全局槽（0xAAC698）与两张假 vtable 的槽 6 之后。
static_assert(kVtableBOffset + 7 * 8 <= kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t),
              "fake module block must hold both the Game slot and the fake vtables");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

//: 往某个假 vtable 的槽 `slot` 写目标地址（槽位 = `对象首字 + slot*8`）。
void SetVtableSlot(std::uintptr_t vtableOffset, std::uint32_t slot, std::uintptr_t target) {
    WriteAt<std::uint64_t>(g_ModuleBytes, vtableOffset + slot * sizeof(std::uintptr_t), target);
}

void MakeFakeGridEntity(std::vector<unsigned char>& block, std::uintptr_t vtableOffset,
                        std::uint32_t gridIndex) {
    block.assign(kGridEntitySpriteOffset + 0x158 + 0x20, 0);
    WriteAt<std::uintptr_t>(block, 0, g_EngineBase + vtableOffset);
    WriteAt<std::uint32_t>(block, kGridEntityTypeOffset, 6);
    WriteAt<std::uint32_t>(block, kGridEntityGridIndexOffset, gridIndex);
}

void PublishFakeWorld(std::uintptr_t destroyTargetA, std::uintptr_t destroyTargetB,
                      std::uintptr_t postInitTargetA) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    SetVtableSlot(kVtableAOffset, kGridEntityVtableDestroySlot, destroyTargetA);
    SetVtableSlot(kVtableAOffset, kGridEntityVtablePostInitSlot, postInitTargetA);
    SetVtableSlot(kVtableBOffset, kGridEntityVtableDestroySlot, destroyTargetB);

    MakeFakeGridEntity(g_GridABytes, kVtableAOffset, GRID_INDEX_A);
    MakeFakeGridEntity(g_GridBBytes, kVtableBOffset, GRID_INDEX_B);

    const std::size_t tableOffset = kRoomGridEntityTableOffset;
    const std::size_t endA = tableOffset + (GRID_INDEX_A + 1) * sizeof(std::uintptr_t);
    const std::size_t endB = tableOffset + (GRID_INDEX_B + 1) * sizeof(std::uintptr_t);
    g_RoomBytes.assign((endA > endB ? endA : endB) + sizeof(std::uintptr_t), 0);
    WriteAt<std::uintptr_t>(g_RoomBytes, tableOffset + GRID_INDEX_A * sizeof(std::uintptr_t),
                            AddressOf(g_GridABytes));
    WriteAt<std::uintptr_t>(g_RoomBytes, tableOffset + GRID_INDEX_B * sizeof(std::uintptr_t),
                            AddressOf(g_GridBBytes));

    WriteAt<std::uintptr_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uintptr_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
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

    std::uintptr_t destroyA = TARGET_A_VALUE, destroyB = TARGET_B_VALUE, postInitA = TARGET_C_VALUE;
    int index = GRID_INDEX_A_VALUE;
    if (std::strcmp(scenario, "destroy") == 0 || std::strcmp(scenario, "noarg") == 0 ||
        std::strcmp(scenario, "postinit") == 0 || std::strcmp(scenario, "errors") == 0) {
        // 默认：A 号格。
    } else if (std::strcmp(scenario, "destroy_b") == 0) {
        index = GRID_INDEX_B_VALUE;      // ★ 另一张假 vtable ⇒ 目标必须跟着变
    } else if (std::strcmp(scenario, "emptyslot") == 0) {
        destroyA = 0;                    // ★ 槽 6 是 0 ⇒ 应当**不调**
    } else {
        return 91;
    }

    PublishFakeWorld(destroyA, destroyB, postInitA);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x3040);
    std::printf("B304 gridA=0x%llX\n", static_cast<unsigned long long>(AddressOf(g_GridABytes)));
    std::printf("B304 gridB=0x%llX\n", static_cast<unsigned long long>(AddressOf(g_GridBBytes)));

    std::string script_text =
        std::string("local scenario = '") + scenario + "'\n"
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local grid = Game():GetRoom():GetGridEntity(GRID_INDEX_VALUE)\n"
        "print('B304 kind=' .. type(grid))\n"
        "print('B304 fns=' .. type(grid.Destroy) .. ',' .. type(grid.PostInit))\n"
        "if scenario == 'destroy' or scenario == 'destroy_b' or scenario == 'emptyslot' then\n"
        "  local good, count = pcall(function() return select('#', grid:Destroy(true)) end)\n"
        "  print('B304 ok=' .. tostring(good))\n"
        "  print('B304 ret=' .. tostring(count))\n"
        "elseif scenario == 'noarg' then\n"
        // ★ `Destroy()` 不带实参 —— PC 的胶水层把缺省填 0 ⇒ 引擎收到的第 1 个实参应当是 0。
        "  local good, count = pcall(function() return select('#', grid:Destroy()) end)\n"
        "  print('B304 ok=' .. tostring(good))\n"
        "  print('B304 ret=' .. tostring(count))\n"
        "elseif scenario == 'postinit' then\n"
        "  local good, count = pcall(function() return select('#', grid:PostInit()) end)\n"
        "  print('B304 ok=' .. tostring(good))\n"
        "  print('B304 ret=' .. tostring(count))\n"
        "elseif scenario == 'errors' then\n"
        "  print('B304 extra=' .. ok(function() return grid:Destroy(true, true) end))\n"
        "  print('B304 extramsg=' .. err(function() return grid:Destroy(true, true) end))\n"
        "  print('B304 postextra=' .. ok(function() return grid:PostInit(1) end))\n"
        "  print('B304 postmsg=' .. err(function() return grid:PostInit(1) end))\n"
        "  print('B304 badrecv=' .. ok(function() return grid.Destroy({}) end))\n"
        "  print('B304 badrecvmsg=' .. err(function() return grid.Destroy({}) end))\n"
        "end\n";
    //: 把占位符换成这次要用的网格下标（夹具里两格各指向一张不同的假 vtable）。
    const std::string indexText = std::to_string(index);
    for (std::size_t position = script_text.find("GRID_INDEX_VALUE"); position != std::string::npos;
         position = script_text.find("GRID_INDEX_VALUE", position + indexText.size())) {
        script_text.replace(position, std::strlen("GRID_INDEX_VALUE"), indexText);
    }

    const char* script = script_text.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b304.lua");
    static_cast<void>(result);
    std::printf("B304 calls=%u\n", g_HostEngineCallTrampolineCalls);
    std::printf("B304 target=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastTarget));
    std::printf("B304 x0=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[0]));
    std::printf("B304 x1=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[1]));
    return 0;
}
'''
#: ★ 先换带 `_VALUE` 的（它们以 `GRID_INDEX_A` 为前缀，顺序反了就会被截断）。
HARNESS = (HARNESS
           .replace("TARGET_A_VALUE", TARGET_A)
           .replace("TARGET_B_VALUE", TARGET_B)
           .replace("TARGET_C_VALUE", TARGET_C)
           .replace("GRID_INDEX_A_VALUE", str(GRID_INDEX_A))
           .replace("GRID_INDEX_B_VALUE", str(GRID_INDEX_B))
           .replace("GRID_INDEX_A", str(GRID_INDEX_A))
           .replace("GRID_INDEX_B", str(GRID_INDEX_B)))


class GridEntityVtableBatch304Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b304-")
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

    def test_destroy_calls_the_receivers_own_vtable_slot(self):
        """★★ `Destroy(true)` 调到**接收者自己那张 vtable 的槽 6**，`x0` = 接收者、`x1` = 1。

        ★ 两个网格实体各指向**不同的**假 vtable（`destroy` 用 A 号格、`destroy_b` 用 B 号格），
        槽 6 里装两个不同哨兵 ⇒ 两次调用的目标必须不同 —— 专抓「按固定偏移直调基类」。
        ★ 槽位按「对象首字 + 槽号*8」推导（夹具独立算的）⇒ 实现多写 `0x10` 会红。
        """
        out = self.run_scenario("destroy")
        self.assertIn("B304 kind=userdata", out)
        self.assertIn("B304 fns=function,function", out)
        self.assertEqual(self.value(out, "B304 calls"), "1")
        self.assertEqual(int(self.value(out, "B304 target"), 16), int(TARGET_A, 16))
        self.assertEqual(int(self.value(out, "B304 x0"), 16), int(self.value(out, "B304 gridA"), 16))
        self.assertEqual(int(self.value(out, "B304 x1"), 16), 1, "`Destroy(true)` 的第 1 个实参应当是 1")
        self.assertIn("B304 ok=true", out)
        self.assertIn("B304 ret=1", out)

        out = self.run_scenario("destroy_b")
        self.assertEqual(self.value(out, "B304 calls"), "1")
        self.assertEqual(int(self.value(out, "B304 target"), 16), int(TARGET_B, 16))
        self.assertEqual(int(self.value(out, "B304 x0"), 16), int(self.value(out, "B304 gridB"), 16))

    def test_omitted_argument_becomes_zero(self):
        """★ `Destroy()` 省略实参 ⇒ 引擎收到的第 1 个实参是 **0**（PC 的缺省 = false）。"""
        out = self.run_scenario("noarg")
        self.assertEqual(self.value(out, "B304 calls"), "1")
        self.assertEqual(int(self.value(out, "B304 target"), 16), int(TARGET_A, 16))
        self.assertEqual(int(self.value(out, "B304 x1"), 16), 0)
        self.assertIn("B304 ret=1", out)

    def test_post_init_returns_no_values(self):
        """★ `PostInit()` 走**另一条槽**（槽 2）且返回 **0 个值**（PC 是 `void`）。"""
        out = self.run_scenario("postinit")
        self.assertEqual(self.value(out, "B304 calls"), "1")
        self.assertEqual(int(self.value(out, "B304 target"), 16), int(TARGET_C, 16),
                         "`PostInit` 必须走**自己那条槽**（槽 2），不是 `Destroy` 的槽 6")
        self.assertEqual(int(self.value(out, "B304 x0"), 16), int(self.value(out, "B304 gridA"), 16))
        self.assertIn("B304 ok=true", out)
        self.assertIn("B304 ret=0", out)

    def test_zero_slot_target_is_skipped_without_error(self):
        """★ 槽 6 是 0 ⇒ **不调、不报错**、返回 1 个值（`false`）。"""
        out = self.run_scenario("emptyslot")
        self.assertEqual(self.value(out, "B304 calls"), "0")
        self.assertEqual(self.value(out, "B304 target"), "0x0")
        self.assertIn("B304 ok=true", out)
        self.assertIn("B304 ret=1", out)

    def test_argument_gate_and_bad_receiver(self):
        """参数闸门：`Destroy` 最多 1 个、`PostInit` 恰好 0 个；接收者不是网格实体 ⇒ 报错。"""
        out = self.run_scenario("errors")
        self.assertIn("B304 extra=false", out)
        self.assertIn("GridEntity:Destroy expects at most 1 argument(s)", out)
        self.assertIn("B304 postextra=false", out)
        self.assertIn("GridEntity:PostInit expects 0 argument(s)", out)
        self.assertIn("B304 badrecv=false", out)
        self.assertIn("expected a GridEntity", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 行形态（哨兵位 + 槽号常量）/ 新接收者 / 共享助手是同一份。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        header = FIELD_HEADER.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for name, index, slot_constant, slot, shape, argc in APIS:
            with self.subTest(api=f"GridEntity:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "GridEntity", "{name}"',
                    catalog, f"目录里没有 GridEntity:{name}")
                self.assertRegex(
                    remaining,
                    rf"\{{\s*(?i:0x0E01{index:04x}),\s*MakeEngineVtableRowOffset\({slot_constant}\),\s*0,\s*"
                    rf"FieldReceipt::GridEntity,\s*EngineCallShape::{shape},\s*{argc},\s*0xFF\}}",
                    f"行形态不对：GridEntity:{name}")
                self.assertRegex(constants, rf"{slot_constant}\s*=\s*{slot};")
        #: 新接收者必须登记在 `FieldReceipt` 里，且解析走的是共享助手。
        self.assertIn("GridEntity = 9,", header)
        self.assertIn("case FieldReceipt::GridEntity", isaac)
        self.assertIn("CheckGridEntityHandle(state, index)", isaac)
        #: ★ 判据只有一份：`remaining_api.cpp` 的手写路径转发到那个共享助手。
        self.assertIn("return isaac::runtime::GridEntityHandleArgument(state, index);", remaining)
        #: ★ 槽位算法：不许再加 `0x10`（批 303 就是错在这儿）。
        self.assertRegex(isaac, r"slot\) \* kEngineVtableSlotStride,")
        self.assertNotRegex(isaac, r"kEngineVtableSlotsOffset")


if __name__ == "__main__":
    unittest.main()
