"""门禁：批次 321 —— `GridEntity:Update()`（1 处 / 1 个模组）**按 vtable 槽号虚调用**。

## 这一批是什么

`GridEntity:Update()`（契约 `tools/pc_contract_docs/GridEntity.md:152`）在 PC 上是**虚调用**：

| 面 | 证据 |
| --- | --- |
| 槽号 | **3** —— `tools/nro_vtable_slot.py GridEntity --find Update` |
| ★★★ 自证 | **基类 `_ZTVGridEntity` 的槽 3 就是 `__cxa_pure_virtual`（纯虚）**，而 `GridEntity_Door`/`_Rock`/`_Statue`/`_TNT`/`_Web`/`_Pit`/`_Fire`/`_Lock`/`_Poop`/`_Wall`/`_Spikes`/`_Stairs`/`_Gravity`/`_TrapDoor`/`_Decoration`/`_Teleporter`/`_PressurePlate` … **每一个**派生类都在槽 3 放自己的 `Update`（`--find-all Update` 能看到）⇒ 「基类纯虚 + 派生类逐类覆盖」正是虚函数的定义，而且**不存在**"某个派生类忘了覆盖 ⇒ 落到基类"的情形（基类那份根本不可调用）|
| PC 侧 | 名表里 `Update` 有一条指向跳板表 **`0x860507`** = `mov eax,[ecx]; jmp [eax+0x8]` ⇒ PC 序号 **2** ⇒ Switch 槽 **3**（`PC 序号 = Switch 槽号 − 1`）。★ 另一条指向 `0x860520` = 序号 3 = `Entity::Update` 的槽 4 —— 两条别混 |
| 接收者 / 形状 | 沿用批 304 的 `FieldReceipt::GridEntity` 与 `Void0` ⇒ **零新机制、0 字节代码** |

## 宿主怎么验（与批 304/319 同一套判据）

夹具造**两张不同的假 vtable**（都在 `GridEntity` 家族区间里）、**槽 3 各装不同的哨兵**，
断言跳板桩记下的**调用目标**是**接收者自己那张表**的槽 3，而不是别的表 / 别的槽 / 常量。
★ 夹具按「对象首字 + 槽号*8」**独立推导**槽位，不引用机制自己的常量。
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
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"

#: 夹具里两个网格实体的网格下标（各指向一张**不同的**假 vtable）。
GRID_INDEX_A = 22
GRID_INDEX_B = 23
#: 两张表在槽 3 的哨兵（不同 ⇒ 取错表会红）；再给一个"别的槽"的哨兵（把槽号写错也会红）。
TARGET_A = "0x31900303"
TARGET_B = "0x31900404"

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

// 伪造的引擎内存（形状抄批次 304）：Room 的网格实体表 + 两张假 vtable。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_RoomBytes;
std::vector<unsigned char> g_GridABytes;
std::vector<unsigned char> g_GridBBytes;
std::uintptr_t g_EngineBase = 0;

constexpr std::uintptr_t kVtableAOffset = kGridEntityVtableOffset;          // 0xA37890
constexpr std::uintptr_t kVtableBOffset = kGridEntityVtableOffset + 0x200;  // 隔开，别让槽位重叠

static_assert(kGridEntityVtableOffset == 0xA37890,
              "GridEntity 的对象首字应当 = _ZTVGridEntity(0xA37880) + 0x10");
static_assert(kVtableBOffset >= kVtableAOffset + 20 * 8,
              "两张假 vtable 不许重叠（槽位是 对象首字 + 槽号*8）");
static_assert(kVtableBOffset + 20 * 8 < kGridEntityVtableRangeEndOffset,
              "两张假 vtable 都要落在 GridEntity 家族的区间里");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

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

void PublishFakeWorld(bool clearSlot) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    SetVtableSlot(kVtableAOffset, kGridEntityVtableUpdateSlot,
                  clearSlot ? 0 : UPDATE_A_VALUE);
    SetVtableSlot(kVtableBOffset, kGridEntityVtableUpdateSlot, UPDATE_B_VALUE);

    MakeFakeGridEntity(g_GridABytes, kVtableAOffset, GRID_INDEX_A_VALUE);
    MakeFakeGridEntity(g_GridBBytes, kVtableBOffset, GRID_INDEX_B_VALUE);

    const std::size_t tableOffset = kRoomGridEntityTableOffset;
    const std::size_t endA = tableOffset + (GRID_INDEX_A_VALUE + 1) * sizeof(std::uintptr_t);
    const std::size_t endB = tableOffset + (GRID_INDEX_B_VALUE + 1) * sizeof(std::uintptr_t);
    g_RoomBytes.assign((endA > endB ? endA : endB) + sizeof(std::uintptr_t), 0);
    WriteAt<std::uintptr_t>(g_RoomBytes,
                            tableOffset + GRID_INDEX_A_VALUE * sizeof(std::uintptr_t),
                            AddressOf(g_GridABytes));
    WriteAt<std::uintptr_t>(g_RoomBytes,
                            tableOffset + GRID_INDEX_B_VALUE * sizeof(std::uintptr_t),
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
    const bool clearSlot = std::strcmp(scenario, "emptyslot") == 0;
    if (std::strcmp(scenario, "update") != 0 && std::strcmp(scenario, "b") != 0 &&
        std::strcmp(scenario, "emptyslot") != 0 && std::strcmp(scenario, "errors") != 0) {
        return 91;
    }
    const int index = std::strcmp(scenario, "b") == 0 ? GRID_INDEX_B_VALUE : GRID_INDEX_A_VALUE;
    PublishFakeWorld(clearSlot);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x3210);

    std::string script_text =
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local g = Game():GetRoom():GetGridEntity(INDEX_VALUE)\n"
        "print('B321 kind=' .. type(g))\n"
        "print('B321 fn=' .. type(g.Update))\n";
    if (std::strcmp(scenario, "errors") == 0) {
        script_text +=
            "print('B321 extra=' .. ok(function() return g:Update(1) end))\n"
            "print('B321 extramsg=' .. err(function() return g:Update(1) end))\n"
            "print('B321 badrecv=' .. ok(function() return g.Update({}) end))\n"
            "print('B321 badrecvmsg=' .. err(function() return g.Update({}) end))\n";
    } else {
        script_text +=
            "local good, count = pcall(function() return select('#', g:Update()) end)\n"
            "print('B321 ok=' .. tostring(good))\n"
            "print('B321 ret=' .. tostring(count))\n";
    }
    const std::string indexText = std::to_string(index);
    for (std::size_t position = script_text.find("INDEX_VALUE"); position != std::string::npos;
         position = script_text.find("INDEX_VALUE", position + indexText.size())) {
        script_text.replace(position, std::strlen("INDEX_VALUE"), indexText);
    }
    const char* script = script_text.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b321.lua");
    static_cast<void>(result);
    std::printf("B321 calls=%u\n", g_HostEngineCallTrampolineCalls);
    std::printf("B321 target=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastTarget));
    return 0;
}
'''

HARNESS = (HARNESS
           .replace("UPDATE_A_VALUE", TARGET_A)
           .replace("UPDATE_B_VALUE", TARGET_B)
           .replace("GRID_INDEX_A_VALUE", str(GRID_INDEX_A))
           .replace("GRID_INDEX_B_VALUE", str(GRID_INDEX_B)))


class GridEntityUpdateBatch321Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b321-")
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

    def test_update_dispatches_through_the_receivers_own_vtable(self):
        """★★★ 核心：目标是**接收者自己那张 vtable 的槽 3**（哨兵），不是基类实现。"""
        out = self.run_scenario("update")
        self.assertIn("B321 kind=userdata", out)
        self.assertIn("B321 fn=function", out)
        self.assertEqual(self.value(out, "B321 calls"), "1", out)
        self.assertEqual(int(self.value(out, "B321 target"), 16), int(TARGET_A, 16), out)

    def test_the_target_follows_the_receiver(self):
        """★★ 换一个网格实体（另一张 vtable）⇒ 目标跟着变（抓"固定偏移直调"与"缓存成常量"）。"""
        out = self.run_scenario("b")
        self.assertEqual(self.value(out, "B321 calls"), "1", out)
        self.assertEqual(int(self.value(out, "B321 target"), 16), int(TARGET_B, 16), out)

    def test_a_cleared_slot_is_not_called(self):
        """槽 3 是 0 ⇒ 不调（0 次），也不抛错。"""
        out = self.run_scenario("emptyslot")
        self.assertEqual(self.value(out, "B321 calls"), "0", out)
        self.assertIn("B321 ok=true", out)

    def test_argument_and_receiver_gates(self):
        """参数/接收者闸门（引擎方法行那套文案：`expects N argument(s)`）。"""
        out = self.run_scenario("errors")
        self.assertIn("B321 extra=false", out)
        self.assertIn("GridEntity:Update expects 0 argument(s)", out)
        self.assertIn("B321 badrecv=false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """槽号常量与数据行形态。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        rows = REMAINING_API.read_text(encoding="utf-8")
        self.assertRegex(constants,
                         r"inline constexpr std::uint32_t kGridEntityVtableUpdateSlot\s*=\s*3;")
        self.assertRegex(
            rows,
            r"\{0x0E0100DC,\s*MakeEngineVtableRowOffset\(kGridEntityVtableUpdateSlot\),\s*0,\s*"
            r"FieldReceipt::GridEntity,\s*EngineCallShape::Void0,\s*0,\s*0xFF\}")
        self.assertIn("RowCount(kGridEntityEngineRows) == 3", rows)
        #: ★ 反回归：批 304 那两条不能被碰到。
        self.assertIn("kGridEntityVtableDestroySlot", rows)
        self.assertIn("kGridEntityVtablePostInitSlot", rows)


if __name__ == "__main__":
    unittest.main()
