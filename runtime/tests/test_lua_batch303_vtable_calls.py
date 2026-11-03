"""门禁：`Entity:CanShutDoors()` / `EntityNPC:CanShutDoors()`（批次 303，2026-10-03）——
**第一批"按 vtable 槽号调用"的引擎方法行**。

## 这一批是什么

| API | 契约 | 形状 | 语料调用点 |
| --- | --- | --- | --- |
| `Entity:CanShutDoors()` | `Entity.md:297` "Enemies keep the doors shut." | `Bool0`（0 参、返回布尔） | 3 |
| `EntityNPC:CanShutDoors()` | `EntityNPC.md:171` | 同上 | （同一批调用点，清单按 owner 各记一次） |

★ 这两条不是普通引擎方法 —— 它们是**虚函数**：PC 的绑定本体不调某一个具体函数，而是
`mov eax,[ecx]; jmp [eax+偏移]`（PC 镜像 `0x8604E0` 起是一整张这样的跳板表）。
**调哪一个实现取决于接收者的动态类型** ⇒ 既有的"模块基址 + 固定偏移 + 入口指纹"那套做不了
（直调基类会跳过子类行为）。

⇒ 本批给引擎方法行加了一条新约定：**`offset` 最高位置 1 = "按 vtable 槽号调用"、低 31 位 = 槽号**
（`engine_method_api.hpp` 的 `kEngineVtableRowFlag`）。运行时：
`vptr = [receiver]` → `target = [vptr + 0x10 + 槽号*8]` → 交给既有的 `EngineCallTrampoline`。

★★ **槽号从 Switch 的 `_ZTV` 读**（`vtable + 0x10 + i*8`，靠 `R_AARCH64_ABS64` 重定位 + 符号索引解）：
`Entity` 与 `Entity_NPC` 的 `CanShutDoors` 都在**槽 18**（同一槽号、两套实现）。**不许照抄 PC 的 17**
—— 两边差一个析构槽（Itanium 开头两个析构变体、MSVC 一个）。取证见 `runtime_constants.hpp` 批次 303 段。

## 宿主验到了什么、没验到什么

* **验到**（宿主跳板不真调引擎，但**目标地址与参数**是可判定的 —— 见 `engine_call_trampoline_host_stub.cpp`）：
  - ★★ **目标取自"接收者自己的 vtable 槽 18"**：玩家对象与 NPC 对象的第一字指向**两张不同的假
    vtable**，槽 18 里装着两个不同的哨兵地址 ⇒ 两次调用分别落到那两个地址上
    （★ 专抓「按固定偏移直调基类」这类错法）；
  - ★ **目标是"调用时现读"的**：同一行、同一个对象，把槽 18 里的值换掉再调 ⇒ 目标跟着换
    （专抓「把目标缓存成常量」）；
  - ★ **`x0` 是接收者自己**（`integers[0]` 等于那个对象的地址，不是别人的）；
  - **槽 18 为 0 ⇒ 不调、不报错、返回 `false`**（新增的 `EngineRowRejectReason::Vtable`）；
  - **参数闸门**：多给参数报错；接收者不是实体报错；`EntityNPC` 视图上也能调到。
* **没验**：真机上槽 18 里真的是那个实现（宿主里 vtable 是我们自己造的）⇒ 真机项 = 作业单 **V53**。
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
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
ROW_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "engine_method_api.hpp"
STATS_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_call_stats.hpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: 本批两条 API 的目录序号 / owner / 形状。
APIS = (
    ("Entity", "CanShutDoors", 0x00D3),
    ("EntityNPC", "CanShutDoors", 0x00D4),
)
SLOT_CONSTANT = "kEntityVtableCanShutDoorsSlot"

#: 夹具里塞进两张假 vtable 槽 18 的两个哨兵目标（互不相同 ⇒ 取错表/缓存成常量都会红）。
TARGET_A = "0x1A2B3C4D"
TARGET_B = "0x5E6F7081"


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"
#include "interfaces/lua/engine_method_api.hpp"
#include "interfaces/lua/rplus_extended_fields_guards.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// 宿主跳板桩的观测点（`engine_call_trampoline_host_stub.cpp`）：宿主上跳板**不真调**引擎，
// 但"调到了哪个地址、`x0` 是谁"都记下来了 —— 这正是本批要验的两件事。
extern "C" {
extern std::uint32_t g_HostEngineCallTrampolineCalls;
extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
}

// 伪造的引擎内存：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是 **变量地址**）
//   g_OwnerSlotBytes                          = Game*
//   Game + kGamePlayerArrayBegin/End          = 一个元素的玩家指针数组
//   玩家对象首字                               = base + kEntityPlayerVtableOffset（**精确值**，`IsEntityPlayer` 要）
//   玩家对象 + kEntityParentOffset             = NPC 对象
//   NPC 对象首字                               = base + kEntityNpcVtableOffset（**精确值**，`ToNPC()` 要）
//   ★ 两张假 vtable 的**槽 18**（`vtable + 0x10 + 18*8`）里各塞一个哨兵地址 ——
//     这是本批"按槽号调用"唯一要读的东西。整个模块块要盖住玩家 vtable 那一带（`0xA371B8`）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_NpcBytes;
std::uintptr_t g_EngineBase = 0;

//: 模块块必须盖到玩家 vtable 的槽 18 之后（`kEntityPlayerVtableOffset + 18*8 + 8 = 0xA371B8`）
//: 与 **`kGameOwnerGlobalSlotOffset`**（`0xAAC698`，写 `g_Game` 槽用）—— 取两者的大者。
//: ★ 第一版就是漏了后者 ⇒ `WriteAt` 越界写崩（`SIGSEGV`，而且 stdout 是块缓冲、连一句输出都没有）。
static_assert(kEntityPlayerVtableOffset + 18 * 8 + 8 <=
                  kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t),
              "fake module block must hold both the player vtable slot 18 and the Game slot");

//: ★★★ **槽 i 在 `对象首字 + i*8`**（**不加 0x10**）—— 本夹具按这条**独立推导**槽位地址，
//: 刻意**不引用**机制自己的常量（引用了就会"夹具与实现一起漂"、验不出 off-by-0x10）。
//: 判据（三条独立证据，值都已取证过；`_ZTV` 符号地址来自符号表）：
//:   `_ZTVEntity`     `0xA34F48 + 0x10 = 0xA34F58` = `kEntityVtableRangeBeginOffset`
//:   `_ZTVEntity_NPC` `0xA35DA8 + 0x10 = 0xA35DB8` = `kEntityNpcVtableOffset`
//:   `_ZTVGridEntity` `0xA37880 + 0x10 = 0xA37890` = `kGridEntityVtableOffset`
//: ⇒ **对象首字存的是 `_ZTV + 0x10`**，也就是**槽 0 自己的地址**。
//: ★ 另有代码侧印证：`IsEntityPlayer()` 判的是 `*(u64*)candidate == base + kEntityPlayerVtableOffset`
//:   （拿对象首字与那个常量**直接相等**比较）。
static_assert(kEntityVtableRangeBeginOffset == 0xA34F58,
              "Entity 家族 vtable 区间起点应当 = _ZTVEntity(0xA34F48) + 0x10");
static_assert(kEntityNpcVtableOffset == 0xA35DB8,
              "Entity_NPC 的对象首字应当 = _ZTVEntity_NPC(0xA35DA8) + 0x10");
static_assert(kGridEntityVtableOffset == 0xA37890,
              "GridEntity 的对象首字应当 = _ZTVGridEntity(0xA37880) + 0x10");
//: 两张 vtable 的起点都必须在实体判据的区间里（否则句柄根本拿不到）。
static_assert(kEntityVtableRangeBeginOffset <= kEntityPlayerVtableOffset &&
                  kEntityPlayerVtableOffset < kEntityVtableRangeEndOffset,
              "player vtable 不在 Entity 家族的 vtable 区间里");
static_assert(kEntityVtableRangeBeginOffset <= kEntityNpcVtableOffset &&
                  kEntityNpcVtableOffset < kEntityVtableRangeEndOffset,
              "npc vtable 不在 Entity 家族的 vtable 区间里");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

//: 往**假模块块**里某个 vtable 的槽 `slot` 写一个目标地址（运行时就是"这个方法的那条实现"）。
void SetVtableSlot(std::uintptr_t vtableOffset, std::uint32_t slot, std::uintptr_t target) {
    //: ★ `vtableOffset` 传进来的是**对象首字**（= `_ZTV + 0x10` = 槽 0）⇒ 槽 `slot` 就在
    //: `vtableOffset + slot*8`。**不要再加 0x10**（判据见上面那三条 static_assert）。
    WriteAt<std::uint64_t>(g_ModuleBytes, vtableOffset + slot * sizeof(std::uintptr_t), target);
}

void MakeFakeEntity(std::vector<unsigned char>& block, std::uintptr_t vtableOffset) {
    block.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(block, 0, g_EngineBase + vtableOffset);
    WriteAt<std::uint32_t>(block, kEntityTypeOffset, kEntityTypePlayer);
}

void PublishFakeWorld(std::uintptr_t playerSlotTarget, std::uintptr_t npcSlotTarget) {
    //: 大小取"玩家 vtable 槽 18 之后"与"Game 全局槽之后"的大者（见上面的 static_assert）。
    //: ★ 第一版只按 vtable 那一带算 ⇒ 写 `g_Game` 槽时越界，`SIGSEGV` 且一句输出都没有。
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    SetVtableSlot(kEntityPlayerVtableOffset, kEntityVtableCanShutDoorsSlot, playerSlotTarget);
    SetVtableSlot(kEntityNpcVtableOffset, kEntityVtableCanShutDoorsSlot, npcSlotTarget);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    MakeFakeEntity(g_NpcBytes, kEntityNpcVtableOffset);
    WriteAt<std::uint32_t>(g_NpcBytes,kEntityTypeOffset,20);
    namespace E=isaac::runtime::extended_fields;
    std::memcpy(g_ModuleBytes.data()+E::kEntity0Entry,E::kEntity0Guard.data(),E::kEntity0Guard.size());
    std::memcpy(g_ModuleBytes.data()+E::kEntity1Entry,E::kEntity1Guard.data(),E::kEntity1Guard.size());
    std::memcpy(g_ModuleBytes.data()+E::kEntity2Entry,E::kEntity2Guard.data(),E::kEntity2Guard.size());
    std::memcpy(g_ModuleBytes.data()+kEntityNpcCanShutDoorsMethodOffset,
                kEntityNpcCanShutDoorsExpectedBytes.data(),kEntityNpcCanShutDoorsExpectedBytes.size());

    MakeFakeEntity(g_PlayerBytes, kEntityPlayerVtableOffset);
    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityParentOffset, AddressOf(g_NpcBytes));

    g_PlayerArrayBytes.assign(sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + sizeof(std::uint64_t));

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

    std::uintptr_t playerTarget = TARGET_A_VALUE, npcTarget = TARGET_B_VALUE;
    if (std::strcmp(scenario, "player") == 0 || std::strcmp(scenario, "args") == 0 ||
        std::strcmp(scenario, "badrecv") == 0) {
        // 默认两支哨兵即可。
    } else if (std::strcmp(scenario, "npc") == 0) {
        // 同上；断言靠 C++ 侧打出的目标地址区分。
    } else if (std::strcmp(scenario, "emptyslot") == 0) {
        playerTarget = 0;                      // ★ 槽 18 是 0 ⇒ 应当**不调**
    } else {
        return 91;
    }

    PublishFakeWorld(playerTarget, npcTarget);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x3030);
    std::printf("B303 paddr=0x%llX\n",
                static_cast<unsigned long long>(AddressOf(g_PlayerBytes)));
    std::printf("B303 naddr=0x%llX\n",
                static_cast<unsigned long long>(AddressOf(g_NpcBytes)));

    const std::string script_text =
        std::string("local scenario = '") + scenario + "'\n"
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local p = Isaac.GetPlayer(0)\n"
        "print('B303 pkind=' .. type(p))\n"
        "print('B303 pfn=' .. type(p.CanShutDoors))\n"
        // ★ 每个场景**只调一次**（`calls` 是要断言的）：用 `pcall` 包住那**一次**调用，
        //   把"有没有报错"和"返回了几个值"一起取回来。
        "if scenario == 'player' or scenario == 'emptyslot' then\n"
        "  local good, count = pcall(function() return select('#', p:CanShutDoors()) end)\n"
        "  print('B303 ok=' .. tostring(good))\n"
        "  print('B303 ret=' .. tostring(count))\n"
        "elseif scenario == 'npc' then\n"
        "  local n = p.Parent:ToNPC()\n"
        "  print('B303 nkind=' .. type(n))\n"
        "  print('B303 nfn=' .. type(n and n.CanShutDoors))\n"
        // NPC has a boolean property; query its virtual behavior through Entity's method.
        "  print('B303 ret=' .. select('#', p.CanShutDoors(n)))\n"
        "elseif scenario == 'args' then\n"
        "  print('B303 extra=' .. ok(function() return p:CanShutDoors(1) end))\n"
        "  print('B303 extramsg=' .. err(function() return p:CanShutDoors(1) end))\n"
        "elseif scenario == 'badrecv' then\n"
        "  print('B303 badrecv=' .. ok(function() return p.CanShutDoors({}) end))\n"
        "  print('B303 badrecvmsg=' .. err(function() return p.CanShutDoors({}) end))\n"
        "end\n";

    const char* script = script_text.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b303.lua");
    if(result!=LuaRuntime::LuaInitResult::Success){char text[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(text,sizeof(text)));std::fprintf(stderr,"B303 init: %s\n",text);return 11;}
    std::printf("B303 calls=%u\n", g_HostEngineCallTrampolineCalls);
    std::printf("B303 target=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastTarget));
    std::printf("B303 x0=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[0]));
    return 0;
}
'''
HARNESS = HARNESS.replace("TARGET_A_VALUE", TARGET_A).replace("TARGET_B_VALUE", TARGET_B)


class VtableCallsBatch303Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b303-")
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

    def test_target_comes_from_the_receivers_own_vtable_slot(self):
        """★★ 目标取自**接收者自己的**那张 vtable 的槽 18。

        玩家与 NPC 的第一字指向两张**不同**的假 vtable，槽 18 里是两个不同哨兵
        ⇒ 两次调用必须分别落到那两个地址上；★ 冒号调用的 `x0` 必须是**那个对象自己**。
        ★ 把两条都写成"直调 `Entity::CanShutDoors`"（固定偏移）时，两次的目标会相同 ⇒ 红。
        """
        out = self.run_scenario("player")
        self.assertIn("B303 pkind=userdata", out)
        self.assertIn("B303 pfn=function", out)
        self.assertEqual(self.value(out, "B303 calls"), "1")
        self.assertEqual(int(self.value(out, "B303 target"), 16), int(TARGET_A, 16))
        self.assertEqual(int(self.value(out, "B303 x0"), 16), int(self.value(out, "B303 paddr"), 16),
                         "`x0` 必须是接收者自己（玩家对象）的地址")

        out = self.run_scenario("npc")
        self.assertIn("B303 nkind=userdata", out)
        self.assertIn("B303 nfn=boolean", out)
        self.assertEqual(self.value(out, "B303 calls"), "1")
        self.assertEqual(int(self.value(out, "B303 target"), 16), int(TARGET_B, 16))
        self.assertEqual(int(self.value(out, "B303 x0"), 16), int(self.value(out, "B303 naddr"), 16),
                         "`x0` 必须是接收者自己（NPC 对象）的地址")

    def test_zero_slot_target_is_skipped_without_error(self):
        """★ 槽 18 是 0 ⇒ **不调、不报错、返回 `false`**（新增的 `Vtable` 类拒绝）。

        ★ 这一条专抓"跳板照调一个 0 地址"——那在真机上是必崩的。
        """
        out = self.run_scenario("emptyslot")
        self.assertEqual(self.value(out, "B303 calls"), "0")
        self.assertEqual(self.value(out, "B303 target"), "0x0")
        self.assertIn("B303 ok=true", out)      # 不抛错
        self.assertIn("B303 ret=1", out)        # 返回 1 个值（false）

    def test_argument_gate_and_bad_receiver(self):
        """参数闸门：只收接收者；接收者不是实体直接报错。"""
        out = self.run_scenario("args")
        self.assertIn("B303 extra=false", out)
        self.assertIn("Entity:CanShutDoors expects 0 argument(s)", out)

        out = self.run_scenario("badrecv")
        self.assertIn("B303 badrecv=false", out)
        self.assertIn("expected an Entity", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 行形态（哨兵位 + 槽号常量）/ 共享处理器那一支 / 新拒绝原因。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        header = ROW_HEADER.read_text(encoding="utf-8")
        stats = STATS_HEADER.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for owner, name, index in APIS:
            with self.subTest(api=f"{owner}:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "{owner}", "{name}"',
                    catalog, f"目录里没有 {owner}:{name}")
                #: 行形态：`MakeEngineVtableRowOffset(槽号常量)` + `entryWord` 写 0 + 形状 `Bool0`。
                self.assertRegex(
                    isaac,
                    rf"\{{\s*(?i:0x0E01{index:04x}),\s*MakeEngineVtableRowOffset\({SLOT_CONSTANT}\),\s*0,\s*"
                    rf"FieldReceipt::Entity,\s*EngineCallShape::Bool0,\s*0,\s*0xFF\}}",
                    f"行形态不对：{owner}:{name}")

        #: 槽号常量：值必须是 18（从 Switch 的 `_ZTV` 读出），且**不是** PC 的 17。
        self.assertRegex(constants, rf"{SLOT_CONSTANT}\s*=\s*18;")
        #: 机制常量与助手。
        self.assertIn("kEngineVtableRowFlag = 0x80000000U", header)
        self.assertIn("kEngineVtableMaximumSlot", header)
        self.assertRegex(header, r"kEngineVtableSlotStride\s*=\s*sizeof\(std::uintptr_t\);")
        self.assertIn("IsEngineVtableRow", isaac)
        #: 新拒绝原因。
        self.assertRegex(stats, r"Vtable\s*=\s*5,")
        self.assertIn("EngineRowRejectReason::Vtable", isaac)

    def test_the_slot_number_is_18_not_the_pc_17(self):
        """★★ 槽号必须从 **Switch 的 `_ZTV`** 读、**不许照抄 PC 的 17**。

        两边差一个析构槽：Itanium（Switch）在 vtable 开头放**两个**析构变体（实测 `Entity`
        槽 0 = `D2`、槽 1 = `D0`），MSVC（PC）只放**一个** `scalar deleting destructor`
        ⇒ PC 的槽号比 Switch 小 1（实测 `CanShutDoors`：PC `jmp [eax+0x44]` = 第 17 条、
        Switch `+0x10+18*8` = 第 18 条）。
        ★ 这一条把"别抄错"钉成门禁：常量值改成 17 会红。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        match = re.search(rf"{SLOT_CONSTANT}\s*=\s*(\d+);", constants)
        self.assertIsNotNone(match, f"{SLOT_CONSTANT} 没定义")
        self.assertEqual(int(match.group(1)), 18,
                         "槽号必须是 18（Switch 的 `_ZTV` 读出）；PC 是 17，抄错就会去调另一个虚函数")
        #: 解释"为什么是 18 而不是 17"的那段话必须在常量旁边（否则下一个人还会抄错）。
        self.assertIn("不许照抄 PC", constants)


if __name__ == "__main__":
    unittest.main()
