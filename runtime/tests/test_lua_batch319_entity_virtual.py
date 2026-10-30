"""门禁：批次 319 —— **修正批 238 四条 `Entity` API 的调用方式**（直调基类 → 按 vtable 槽虚调用）。

## 这一批修的是什么

批 238 把 28 条 API 一次性落成"引擎方法数据行"，分层依据只有"**形状与接收者都现成**"，
**没有核过"PC 那条绑定是不是虚调用"**。本批按本项目自己的"判法四档"第 ③ 档复核了一遍：

| API | PC 绑定 | 跳板表里的偏移 | PC 序号 | Switch 槽 | 判定 |
| --- | --- | --- | --- | --- | --- |
| `Entity:Update()` | `0x860520` | `jmp [eax+0xc]` | 3 | **4** | ★ 虚函数 ⇒ 要改 |
| `Entity:Kill()` | `0x8604FD` | `jmp [eax+0x24]` | 9 | **10** | ★ 虚函数 ⇒ 要改 |
| `Entity:Remove()` | `0x860511` | `jmp [eax+0x28]` | 10 | **11** | ★ 虚函数 ⇒ 要改 |
| `Entity:IsBoss()` | `0x86051B` | `jmp [eax+0x48]` | 18 | **19** | ★ 虚函数 ⇒ 要改 |
| `Entity:IsEnemy()` | `0x684620` | 不在表里 | — | — | 直调正确（**不改**）|

**判据**：PC 绑定落在 `0x8604E0` 起那张 `mov eax,[ecx]; jmp [eax+偏移]` **跳板表**里 ⇒ 它是虚函数。
换算关系与批 303 的实测一致：**PC 序号 = Switch 槽号 − 1**（Itanium 两个析构变体 / MSVC 一个）。
★ 四条覆盖情况（`tools/nro_vtable_slot.py --find-all <名字>`）：`Update` **每个** 派生类都覆盖、
`Kill` 有 `Entity_Familiar`/`Entity_NPC`、`Remove` 有 `Entity_Familiar`/`Entity_Pickup`、
`IsBoss` 有 `Entity_NPC` ⇒ 直调基类会**跳过子类行为**。

## 宿主怎么验（判据核心）

★ **不引用机制自己的常量**：夹具按「对象首字 + 槽号*8」**独立推导**槽位（批 303 的 off-by-0x10
就是这么漏过去的）。两张**不同的**假 vtable 装**不同的**哨兵函数 ⇒
「按固定偏移直调基类」「取错表」「缓存成常量」三种错都当场红。
真正的判据 = 跳板桩记录的**调用目标**（`g_HostEngineCallTrampolineLastTarget`）：
它必须等于**接收者自己那张 vtable 的对应槽**里的哨兵，**而不是**基类实现地址
（`Entity::Update @ 0x60040` / `Kill @ 0x5C8E0` / `Remove @ 0x5D3E0` / `IsBoss @ 0x67580`）。
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

#: `(方法名, 域内序号, 槽号常量, 基类实现偏移, 形状)`
APIS = (
    ("Update", 0x006B, "kEntityVtableUpdateSlot", 0x60040, "Void0"),
    ("Kill", 0x0069, "kEntityVtableKillSlot", 0x5C8E0, "Void0"),
    ("Remove", 0x006A, "kEntityVtableRemoveSlot", 0x5D3E0, "Void0"),
    ("IsBoss", 0x0067, "kEntityVtableIsBossSlot", 0x67580, "Bool0"),
)

#: 两张假 vtable 的哨兵（每张表四个槽各一个 ⇒ 「把两张表弄混」也会红）。
TARGETS_A = ("0x1A2B0004", "0x1A2B0010", "0x1A2B0011", "0x1A2B0019")
TARGETS_B = ("0x5E6F0004", "0x5E6F0010", "0x5E6F0011", "0x5E6F0019")
#: 基类实现的地址（**不该**出现在调用目标里）。
BASE_ADDRESSES = {0x60040: "Update", 0x5C8E0: "Kill", 0x5D3E0: "Remove", 0x67580: "IsBoss"}

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"
#include "interfaces/lua/engine_method_api.hpp"
#include "interfaces/lua/rplus_extended_fields_guards.hpp"

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

// 伪造的引擎内存（形状抄批次 315 的 Entity 夹具 + 批次 304 的假 vtable）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                         = Game*
//   Game + kGamePlayerArrayBegin/End         = 只有一个元素的玩家指针数组
//   玩家对象首字                              = base + 假 vtable A（落在 Entity 家族区间里）
//   玩家对象 + kEntityParentOffset            = 第二个实体（首字 = 假 vtable B）
//   假 vtable 的槽 4/10/11/19                 = 各自不同的哨兵（唯一要读的东西）
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_ParentBytes;
std::uintptr_t g_EngineBase = 0;

//: 两张假 vtable 的偏移：都落在 `Entity` 家族的区间里（存活判据要它过），且互不相同。
//: ★ A 必须是 `kEntityPlayerVtableOffset` —— `Isaac.GetPlayer(0)` 认的是
//:   **Entity_Player 那张确切的 vptr**（不是"区间内就行"），否则它直接答 nil。
//: ★ B 只要落在区间里即可（它走 `p.Parent`，拿到的是普通 `Entity` 元表）。
//: ★★ 两张表必须**隔开 ≥ 20 个槽**（160 字节）：本夹具第一版只隔了 8 字节 ⇒ A 的槽 11 与
//:    B 的槽 10 **同址**、后写的覆盖先写的 ⇒ `Remove` 读到了 `Kill_B` 的哨兵（当场红，正好证明判据有效）。
constexpr std::uintptr_t kVtableAOffset = kEntityPlayerVtableOffset;            // 0xA37110
constexpr std::uintptr_t kVtableBOffset = kEntityPlayerVtableOffset + 0x200;    // 0xA37310

//: ★★ 槽 i 在 `对象首字 + i*8`（**不加** 0x10）—— 夹具按这条**独立推导**、刻意不引用机制常量。
static_assert(kEntityVtableRangeBeginOffset == 0xA34F58,
              "Entity 家族的对象首字应当 = _ZTVEntity(0xA34F48) + 0x10");
static_assert(kEntityVtableRangeBeginOffset < kVtableAOffset &&
                  kVtableBOffset + 20 * 8 < kEntityVtableRangeEndOffset,
              "两张假 vtable 都要落在 Entity 家族的区间里");
static_assert(kVtableBOffset >= kVtableAOffset + 20 * 8,
              "两张假 vtable 不许重叠（槽位是 对象首字 + 槽号*8）");
static_assert(kVtableBOffset + 20 * 8 < kGameOwnerGlobalSlotOffset,
              "假 vtable 要落在模块块内（否则写不进去）");

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

void MakeFakeEntity(std::vector<unsigned char>& block, std::uintptr_t vtableOffset) {
    block.assign(kEntityPlayerSize, 0);
    WriteAt<std::uintptr_t>(block, 0, g_EngineBase + vtableOffset);
    WriteAt<std::uint32_t>(block, kEntityTypeOffset, kEntityTypePlayer);
}

void PublishFakeWorld(bool clearUpdateSlot, bool clearIsBossSlot) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    // Parent now uses the production extended-field layout guard. Supply the
    // fixed-NRO fingerprints, as the other native Parent fixtures already do.
    namespace E = isaac::runtime::extended_fields;
    std::memcpy(g_ModuleBytes.data()+E::kEntity0Entry,E::kEntity0Guard.data(),E::kEntity0Guard.size());
    std::memcpy(g_ModuleBytes.data()+E::kEntity1Entry,E::kEntity1Guard.data(),E::kEntity1Guard.size());
    std::memcpy(g_ModuleBytes.data()+E::kEntity2Entry,E::kEntity2Guard.data(),E::kEntity2Guard.size());

    SetVtableSlot(kVtableAOffset, kEntityVtableUpdateSlot,
                  clearUpdateSlot ? 0 : UPDATE_A_VALUE);
    SetVtableSlot(kVtableAOffset, kEntityVtableKillSlot, KILL_A_VALUE);
    SetVtableSlot(kVtableAOffset, kEntityVtableRemoveSlot, REMOVE_A_VALUE);
    SetVtableSlot(kVtableAOffset, kEntityVtableIsBossSlot,
                  clearIsBossSlot ? 0 : ISBOSS_A_VALUE);
    SetVtableSlot(kVtableBOffset, kEntityVtableUpdateSlot, UPDATE_B_VALUE);
    SetVtableSlot(kVtableBOffset, kEntityVtableKillSlot, KILL_B_VALUE);
    SetVtableSlot(kVtableBOffset, kEntityVtableRemoveSlot, REMOVE_B_VALUE);
    SetVtableSlot(kVtableBOffset, kEntityVtableIsBossSlot, ISBOSS_B_VALUE);

    MakeFakeEntity(g_PlayerBytes, kVtableAOffset);
    MakeFakeEntity(g_ParentBytes, kVtableBOffset);
    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityParentOffset, AddressOf(g_ParentBytes));

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

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    bool clearUpdate = std::strcmp(scenario, "emptyslot") == 0;
    bool clearIsBoss = std::strcmp(scenario, "emptyslot") == 0;
    bool useParent = std::strcmp(scenario, "b") == 0;
    PublishFakeWorld(clearUpdate, clearIsBoss);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x3190);

    std::string method;
    bool errors = false;
    if (std::strcmp(scenario, "errors") == 0) {
        method = "Update";
        errors = true;
    } else if (std::strcmp(scenario, "b") == 0 || std::strcmp(scenario, "emptyslot") == 0) {
        //: `b` = 换接收者；`emptyslot` = 槽清 0 —— 两者都还是调 `Update`。
        method = "Update";
    } else {
        method = scenario;
    }

    std::string script_text =
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local p = Isaac.GetPlayer(0)\n"
        "local e = p\n"
        "if USE_PARENT then e = p.Parent end\n"
        "print('B319 kind=' .. type(e))\n"
        "print('B319 fn=' .. type(e.METHOD))\n";
    if (errors) {
        script_text +=
            "print('B319 extra=' .. ok(function() return p:Update(1) end))\n"
            "print('B319 extramsg=' .. err(function() return p:Update(1) end))\n"
            "print('B319 badrecv=' .. ok(function() return p.Update({}) end))\n"
            "print('B319 badrecvmsg=' .. err(function() return p.Update({}) end))\n";
    } else if (method == "IsBoss") {
        script_text +=
            "local good, value = pcall(function() return e:IsBoss() end)\n"
            "print('B319 ok=' .. tostring(good))\n"
            "print('B319 value=' .. tostring(value))\n";
    } else {
        script_text +=
            "local good, count = pcall(function() return select('#', e:METHOD()) end)\n"
            "print('B319 ok=' .. tostring(good))\n"
            "print('B319 ret=' .. tostring(count))\n";
    }

    const std::string parentText = useParent ? "true" : "false";
    for (std::size_t position = script_text.find("USE_PARENT"); position != std::string::npos;
         position = script_text.find("USE_PARENT", position + parentText.size())) {
        script_text.replace(position, std::strlen("USE_PARENT"), parentText);
    }
    for (std::size_t position = script_text.find("METHOD"); position != std::string::npos;
         position = script_text.find("METHOD", position + method.size())) {
        script_text.replace(position, std::strlen("METHOD"), method);
    }

    const char* script = script_text.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b319.lua");
    static_cast<void>(result);
    std::printf("B319 calls=%u\n", g_HostEngineCallTrampolineCalls);
    std::printf("B319 target=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastTarget));
    return 0;
}
'''

HARNESS = (HARNESS
           .replace("UPDATE_A_VALUE", TARGETS_A[0])
           .replace("KILL_A_VALUE", TARGETS_A[1])
           .replace("REMOVE_A_VALUE", TARGETS_A[2])
           .replace("ISBOSS_A_VALUE", TARGETS_A[3])
           .replace("UPDATE_B_VALUE", TARGETS_B[0])
           .replace("KILL_B_VALUE", TARGETS_B[1])
           .replace("REMOVE_B_VALUE", TARGETS_B[2])
           .replace("ISBOSS_B_VALUE", TARGETS_B[3]))


class EntityVirtualDispatchBatch319Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b319-")
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

    def assert_dispatches_to(self, scenario, expected):
        """★ 判据 = 跳板桩记下的**调用目标**必须是接收者自己那张 vtable 的哨兵。"""
        out = self.run_scenario(scenario)
        self.assertEqual(self.value(out, "B319 calls"), "1", out)
        actual = self.value(out, "B319 target")
        self.assertEqual(
            int(actual, 16), int(expected, 16),
            f"{scenario}：调用目标是 {actual}，应当是 {expected}（接收者自己那张 vtable 的槽）\n{out}")
        base = {value: name for value, name in BASE_ADDRESSES.items()}
        self.assertNotIn(
            int(actual, 16), base,
            f"{scenario}：调到了**基类实现**（{base.get(int(actual, 16))}）—— 说明还在直调、没走虚调用\n{out}")

    # ---------------------------------------------------------------- 行为（宿主）

    def test_each_api_dispatches_through_the_receivers_own_vtable(self):
        """★★★ 本批的核心：四条 API 的目标都取自**接收者自己那张 vtable 的槽**，不是基类实现。"""
        self.assert_dispatches_to("Update", TARGETS_A[0])
        self.assert_dispatches_to("Kill", TARGETS_A[1])
        self.assert_dispatches_to("Remove", TARGETS_A[2])
        self.assert_dispatches_to("IsBoss", TARGETS_A[3])

    def test_the_target_follows_the_receiver(self):
        """★★ 换一个接收者（另一张 vtable）⇒ 目标跟着变（专抓"按固定偏移直调"与"缓存成常量"）。"""
        self.assert_dispatches_to("b", TARGETS_B[0])

    def test_a_cleared_slot_is_not_called(self):
        """槽是 0（没有实现）⇒ **不调**（0 次），也不抛错。"""
        out = self.run_scenario("emptyslot")
        self.assertEqual(self.value(out, "B319 calls"), "0", out)
        self.assertIn("B319 ok=true", out)

    def test_argument_and_receiver_gates(self):
        """参数/接收者闸门不变（换调用方式不该动它们）。

        ★ 引擎方法行（共用 `EngineMethodHandler`）的报错文案是 `expects N argument(s)`，
        与字段行那套 `accepts no arguments` **不是同一份**（别照抄另一族的用例）。
        """
        out = self.run_scenario("errors")
        self.assertIn("B319 extra=false", out)
        self.assertIn("Entity:Update expects 0 argument(s)", out)
        self.assertIn("B319 badrecv=false", out)
        self.assertIn("expected an Entity", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """四条的数据行必须是 vtable 形态、且槽号常量在 `runtime_constants.hpp` 里。"""
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        expected_slots = {
            "kEntityVtableUpdateSlot": "4",
            "kEntityVtableKillSlot": "10",
            "kEntityVtableRemoveSlot": "11",
            "kEntityVtableIsBossSlot": "19",
        }
        for _, index, slot_constant, _, shape in APIS:
            with self.subTest(slot=slot_constant):
                self.assertRegex(constants,
                                 rf"inline constexpr std::uint32_t {slot_constant}\s*=\s*"
                                 rf"{expected_slots[slot_constant]};")
                self.assertRegex(
                    isaac,
                    rf"\{{\s*(?i:0x0e01{index:04x}),\s*MakeEngineVtableRowOffset\("
                    rf"{slot_constant}\),\s*0,\s*FieldReceipt::Entity,\s*"
                    rf"EngineCallShape::{shape},\s*0,\s*0xFF\}}",
                    f"0x0E01{index:04X} 的数据行不是 vtable 形态（形状应为 {shape}）")
        #: ★ 反回归：`IsEnemy` **不该**被改（它不在跳板表里、Switch 侧也没有槽）。
        self.assertRegex(
            isaac, r"\{0x0E010068,\s*kEntityIsEnemyOffset,\s*kEntityIsEnemyEntryWord,")


if __name__ == "__main__":
    unittest.main()
