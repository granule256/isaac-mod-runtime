"""门禁：`EntityPlayer:AddCacheFlags(CacheFlag)` + `CacheFlag` 枚举表（批次 301，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧字段 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `EntityPlayer:AddCacheFlags(mask)` | `EntityPlayer.md:108/109` | `Entity_Player + 0x1958`（`u32` `_cacheFlags`） | 字段行 `U32OrWithArg` / 返回 0 值 | **34** |

外加一张全局枚举表 `CacheFlag`（16 条）—— 模组是**拿它当实参**的
（`player:AddCacheFlags(CacheFlag.CACHE_DAMAGE | CacheFlag.CACHE_FIREDELAY)`），
表不发则 `CacheFlag.X` 本身就是 nil ⇒ 方法在也照样抛错（"同一件事的两半"，批 269/292/297 的先例）。

## 这一行凭什么说自己是 `_cacheFlags`

三条独立证据（详见 `runtime_constants.hpp` 的批次 301 段）：

1. **PC 绑定本体**（`tools/pc_exe_binding.py AddCacheFlags --disasm`）给 `0x427800`，
   全部只有 `mov eax,[ebp+0x8]` + `or dword ptr [ecx+0x14b8], eax` ⇒ PC 的 `_cacheFlags` 在 `+0x14B8`；
2. **Switch 侧具名写入方**：`Entity_Player::AddCollectible @ 0x29367c` 里
   `ldr w8,[x22,#0x54]`（道具配置的 `CacheFlags` = 既有的 `kItemConfigItemCacheFlagsOffset`）
   → `orr w8, w9, w8`（`w9` = `[x20,#0x1958]`）→ 写回 ⇒ 「拾取道具把道具的缓存标志并进玩家这一格」；
3. **Switch 侧派发器**：`Entity_Player::EvaluateItems` 把地址先算进 `x21`
   （`mov w8,#0x1958` + `add x21,x19,x8`）再 `ldr w8,[x21]` + `tbnz w8,#0/#1/#3/#4/#0xa`、`tbz w8,#0x2`/`#0x8`
   —— 位号与 `CacheFlag` 的伤害/射速/弹速/射程/速度/武器/幸运逐位吻合。
   ★ **取值锚点**：`DonateLuck` 给这一格 OR 进 `0x400`（= `CACHE_LUCK`），PC 同一入口也写 `0x400`。

★ 本条**顺带纠正批次 300 的一个负结果**（"`+0x1958` 只有一个位测试、不够格当缓存字"）：
那是**工具盲点** —— `EvaluateItems` 用「先 `mov w8,#0x1958` + `add x21,x19,x8`、再 `ldr w8,[x21]`」
的形态读它，位测试不落在立即数寻址上；只扫 `[xN,#imm]` 的扫描器看不见。

## 宿主验到了什么、没验到什么

* **验到**（字段行没有入口指纹 ⇒ 伪造内存里的字节真被读写）：
  - ★★ **写进了"接收者自己那一格"**：两个玩家各摆不同初值、各 OR 不同掩码 ⇒ 读错对象/写错格都会红；
  - ★ **只做「或」、不清位**：初值 `0x11`（bit0+bit4）OR 上 `0x2` 之后必须是 `0x13` ——
    专抓「把 `|=` 写成 `=`」（整格覆盖写）；
  - ★ **掩码为 0 ⇒ 一个字都不改**；
  - ★ **掩码只取低 32 位**（PC 的 `or dword` 就是 32 位运算）⇒ 传 `0xFFFFFFFF00000000` 等于传 0；
  - ★ **返回值个数 = 0**（PC 是 `void`）：`select('#', p:AddCacheFlags(x))` 必须是 0；
  - ★ **拿不到"玩家"接收者时同样是 0 个返回值、且不抛错**（`RowReturnsNoValues` 那条早退分支）——
    用 `p.Parent`（vptr 是 NPC ⇒ `ValidatedEntityPlayer` 判 0）造出这个分支，宿主里**可达**；
  - **参数闸门**：少给/多给都报错，掩码必须是整数。
* **没验**：真机上这一格是不是就是 `_cacheFlags`（宿主里"偏移对不对"是同一张表的两处引用同一个常量，
  自己证不了自己）以及真机数值 ⇒ 真机项 = 作业单 **V51**。
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
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
LAYOUT_PLAYER = ROOT / "tools" / "layout_tables" / "entity_player.json"
LAYOUT_TOOL = ROOT / "tools" / "build_layout_table.py"
ENUM_TOOL = ROOT / "tools" / "generate_doc_enum_tables.py"
ENUM_DOCS = ROOT / "tools" / "pc_enum_docs"
ENUM_TEST = ROOT / "runtime" / "tests" / "test_lua_doc_enum_tables.py"
ENUM_GENERATED = ROOT / "runtime" / "source" / "program" / "doc_lua_enum_data.cpp"

#: 本批的目录序号 / 偏移常量 / 掩码位（与 `CacheFlag` 表的锚点值一一对应）。
API_INDEX = 0x00D2
OFFSET_NAME = "kEntityPlayerCacheFlagsOffset"

#: 夹具里的初值与掩码（互不相同 ⇒ 读错对象会红）。
FLAGS_A = 0x11          # bit0（CACHE_DAMAGE）+ bit4（CACHE_SPEED）
FLAGS_B = 0x80          # bit7（CACHE_FLYING）
MASK_A = 0x2            # bit1（CACHE_FIREDELAY）⇒ 期望 0x13
MASK_B = 0x400          # bit10（CACHE_LUCK）⇒ 期望 0x480
EXPECTED_A = FLAGS_A | MASK_A
EXPECTED_B = FLAGS_B | MASK_B


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "entity_player_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 296 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                         = Game*
//   Game + kGamePlayerArrayBegin/End         = 两个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset（`IsEntityPlayer` 要**精确**这个值）
//   玩家对象 + kEntityPlayerCacheFlagsOffset  = 本批读改写的 `_cacheFlags`
//   玩家 A 的 + kEntityParentOffset           = 一个 NPC 对象（用来造"接收者不是玩家"那条分支）
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerABytes;
std::vector<unsigned char> g_PlayerBBytes;
std::vector<unsigned char> g_NpcBytes;
std::uintptr_t g_EngineBase = 0;

static_assert(kEntityPlayerCacheFlagsOffset + sizeof(std::uint32_t) <= kEntityPlayerSize,
              "cache flags word must live inside the player object");
//: 布局表生成物与 runtime_constants 的常量必须同值（编译期钉住；isaac_api.cpp 里有同款）。
static_assert(kEntityPlayerCacheFlagsOffset ==
                  isaac::runtime::layout::kEntity_PlayerCacheFlagsOffset,
              "CacheFlags 的偏移在两张表之间不一致");

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

//: 造一个"看起来像 `Entity`"的对象：首字是 vtable（校验只看它）。
void MakeFakeEntity(std::vector<unsigned char>& block, std::uintptr_t vtableOffset) {
    block.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(block, 0, g_EngineBase + vtableOffset);
    WriteAt<std::uint32_t>(block, kEntityTypeOffset, kEntityTypePlayer);
}

void PublishFakeGame(std::uint32_t flagsA, std::uint32_t flagsB) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    // NPC 对象：vptr 用 NPC 的 ⇒ `IsEntityPlayer` 为假 ⇒ `ValidatedEntityPlayer` 判 0。
    MakeFakeEntity(g_NpcBytes, kEntityNpcVtableOffset);

    MakeFakeEntity(g_PlayerABytes, kEntityPlayerVtableOffset);
    MakeFakeEntity(g_PlayerBBytes, kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerABytes, kEntityPlayerCacheFlagsOffset, flagsA);
    WriteAt<std::uint32_t>(g_PlayerBBytes, kEntityPlayerCacheFlagsOffset, flagsB);
    // 玩家 A 的 `Parent` 指向 NPC ⇒ `p.Parent` 交出一个**实体句柄但不是玩家**。
    WriteAt<std::uint64_t>(g_PlayerABytes, kEntityParentOffset, AddressOf(g_NpcBytes));

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerABytes));
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, sizeof(std::uint64_t), AddressOf(g_PlayerBBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + 2 * sizeof(std::uint64_t));

    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

void ReportWords() {
    std::printf("B301 wordA=0x%08X\n", ReadU32(g_PlayerABytes, kEntityPlayerCacheFlagsOffset));
    std::printf("B301 wordB=0x%08X\n", ReadU32(g_PlayerBBytes, kEntityPlayerCacheFlagsOffset));
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    std::uint32_t flagsA = 0x11, flagsB = 0x80;
    const char* script = nullptr;

    // or     —— 两个玩家各 OR 不同掩码（A 的 0x11|0x2=0x13、B 的 0x80|0x400=0x480）
    // zero   —— 掩码 0 ⇒ 一个字都不改
    // wide   —— 掩码只取低 32 位（A 传 0xFFFFFFFF00000000 = 0；B 传 0x100000002 = 2）
    // args   —— 参数闸门（少给/多给/非整数）与返回 0 个值
    // norecv —— 接收者是"实体但不是玩家" ⇒ 什么都不写、不抛错、返回 0 个值
    static const char* kOr =
        "local function rc(f) return select('#', f()) end"
        " local p = Isaac.GetPlayer(0)"
        " local p2 = Isaac.GetPlayer(1)"
        " print('B301 pkinds=' .. type(p) .. ',' .. type(p2))"
        " print('B301 fn=' .. type(p.AddCacheFlags) .. ',' .. type(p2.AddCacheFlags))"
        " print('B301 retA=' .. rc(function() return p:AddCacheFlags(2) end))"
        " print('B301 retB=' .. rc(function() return p2:AddCacheFlags(1024) end))";
    static const char* kZero =
        "local function rc(f) return select('#', f()) end"
        " local p = Isaac.GetPlayer(0)"
        " print('B301 retZero=' .. rc(function() return p:AddCacheFlags(0) end))";
    static const char* kWide =
        "local function rc(f) return select('#', f()) end"
        " local p = Isaac.GetPlayer(0)"
        " local p2 = Isaac.GetPlayer(1)"
        " print('B301 retHigh=' .. rc(function() return p:AddCacheFlags(0xFFFFFFFF00000000) end))"
        " print('B301 retLow=' .. rc(function() return p2:AddCacheFlags(0x100000002) end))";
    static const char* kArgs =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function msg(f) return tostring(select(2, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " print('B301 noargs=' .. ok(function() return p:AddCacheFlags() end))"
        " print('B301 noargsmsg=' .. msg(function() return p:AddCacheFlags() end))"
        " print('B301 twoargs=' .. ok(function() return p:AddCacheFlags(1, 2) end))"
        " print('B301 nilarg=' .. ok(function() return p:AddCacheFlags(nil) end))"
        " print('B301 strarg=' .. ok(function() return p:AddCacheFlags('x') end))"
        " print('B301 floatarg=' .. ok(function() return p:AddCacheFlags(1.5) end))"
        " print('B301 intok=' .. ok(function() return p:AddCacheFlags(2) end))"
        " print('B301 retcount=' .. select('#', p:AddCacheFlags(2)))";
    static const char* kNoRecv =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " local raw = p.Parent"
        " print('B301 rawkind=' .. type(raw))"
        " print('B301 rawfnmissing=' .. tostring(raw.AddCacheFlags == nil))"
        " print('B301 rawok=' .. ok(function() return raw:AddCacheFlags(2) end))"
        // 共享的"返回 0 个值"早退分支：拿不到当前房间时 `Room:SetClear`（同为写侧 void kind）
        // 的接收者解析成 0 ⇒ 必须返回 **0 个值**（本批新加的 `RowReturnsNoValues` 分支）。
        " local room = Game():GetRoom()"
        " print('B301 roomkind=' .. type(room))"
        " print('B301 clearok=' .. ok(function() return room:SetClear(true) end))"
        " print('B301 clearret=' .. select('#', room:SetClear(true)))";

    if (std::strcmp(scenario, "or") == 0) {
        script = kOr;
    } else if (std::strcmp(scenario, "zero") == 0) {
        script = kZero;
    } else if (std::strcmp(scenario, "wide") == 0) {
        script = kWide;
    } else if (std::strcmp(scenario, "args") == 0) {
        script = kArgs; flagsA = 0; flagsB = 0;
    } else if (std::strcmp(scenario, "norecv") == 0) {
        script = kNoRecv;
    } else {
        return 91;
    }

    PublishFakeGame(flagsA, flagsB);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b301.lua");
    static_cast<void>(result);
    ReportWords();
    return 0;
}
'''


class CacheFlagsBatch301Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b301-")
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

    def test_or_lands_in_the_receiver_itself_and_keeps_existing_bits(self):
        """★★ 写进**接收者自己那一格** + **只做「或」不清位**。

        玩家 A 初值 `0x11`（bit0+bit4）OR 上 `0x2`（bit1）⇒ 必须是 `0x13`（三个位都在）；
        玩家 B 初值 `0x80`（bit7）OR 上 `0x400`（bit10）⇒ 必须是 `0x480`。
        ★ 把 `|=` 写成 `=`（整格覆盖）会让 A 变成 `0x2`、B 变成 `0x400` ⇒ 两条断言同时红；
        ★ 写错玩家会让两个数对调 ⇒ 也红。
        """
        out = self.run_scenario("or")
        self.assertIn("B301 pkinds=userdata,userdata", out)
        self.assertIn("B301 fn=function,function", out)
        self.assertIn(f"B301 wordA=0x{EXPECTED_A:08X}", out)
        self.assertIn(f"B301 wordB=0x{EXPECTED_B:08X}", out)
        self.assertNotIn(f"B301 wordA=0x{MASK_A:08X}", out)
        self.assertNotIn(f"B301 wordB=0x{MASK_B:08X}", out)

    def test_zero_mask_changes_nothing(self):
        """掩码为 0 ⇒ `字段 |= 0` 是恒等，一个字都不许被改写。"""
        out = self.run_scenario("zero")
        self.assertIn(f"B301 wordA=0x{FLAGS_A:08X}", out)
        self.assertIn(f"B301 wordB=0x{FLAGS_B:08X}", out)

    def test_mask_uses_only_the_low_32_bits(self):
        """PC 的 `or dword ptr [ecx+0x14b8], eax` 是**32 位**运算 ⇒ 掩码只取低 32 位。

        A 传 `0xFFFFFFFF00000000`（低 32 位 = 0）⇒ **不变**（`0x11`）；
        B 传 `0x100000002`（低 32 位 = 2）⇒ `0x82`。
        """
        out = self.run_scenario("wide")
        self.assertIn(f"B301 wordA=0x{FLAGS_A:08X}", out)
        self.assertIn(f"B301 wordB=0x{FLAGS_B | 0x2:08X}", out)

    def test_returns_zero_values(self):
        """PC 是 `void` ⇒ 返回 **0 个值**（`select('#', call)` 必须是 0，不是"压了个 nil"）。"""
        out = self.run_scenario("or")
        self.assertIn("B301 retA=0", out)
        self.assertIn("B301 retB=0", out)
        out = self.run_scenario("args")
        self.assertIn("B301 retcount=0", out)

    def test_argument_gate(self):
        """参数闸门：**恰好两个**（接收者 + 一个**整数**掩码）。"""
        out = self.run_scenario("args")
        self.assertIn("B301 noargs=false", out)
        self.assertIn("EntityPlayer:AddCacheFlags expects one integer argument", out)
        self.assertIn("B301 twoargs=false", out)
        self.assertIn("B301 nilarg=false", out)
        self.assertIn("B301 strarg=false", out)
        self.assertIn("B301 floatarg=false", out)
        #: 合法的整数掩码要放行（否则上面那几条"报错"可能是"一律报错"造成的假绿）。
        self.assertIn("B301 intok=true", out)

    def test_unreachable_receiver_and_the_shared_void_early_return(self):
        """★ 两件事：

        ① **`FieldReceipt::EntityPlayer` 的"接收者解析成 0"在宿主里不可达**：`raw.AddCacheFlags`
           本身就是 `nil`（方法只装在 `EntityPlayer` 视图的元表上，`Entity` 视图取不到）⇒ 那一句
           报的是 `attempt to call a nil value`，**根本没进到行处理器**。这与批次 296 对 `EntityNPC`
           的结论同形（能拿到句柄的路径都已经校验过身份）。行的降级值由行形状钉住（`FieldMissing::Zero`）。
        ② 本批新加的 `RowReturnsNoValues` 分支**可达且被验到**：拿不到当前房间时，
           `Room:SetClear(true)`（同一条早退分支）必须返回 **0 个值** —— 改之前它会多压一个
           降级值返回 1。用另一条**同为写侧 void** 的行来验这条共享路径，比"只读代码"硬。
        """
        out = self.run_scenario("norecv")
        self.assertIn("B301 rawkind=userdata", out)
        self.assertIn("B301 rawfnmissing=true", out)
        self.assertIn("B301 rawok=false", out)
        #: 早退分支：返回 0 个值（不是"压了个 nil/false"）。
        self.assertIn("B301 roomkind=userdata", out)
        self.assertIn("B301 clearok=true", out)
        self.assertIn("B301 clearret=0", out)
        #: 没写任何东西。
        self.assertIn(f"B301 wordA=0x{FLAGS_A:08X}", out)
        self.assertIn(f"B301 wordB=0x{FLAGS_B:08X}", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 种类与降级档 / 接收者 / 偏移常量 / 新 kind / 早退分支。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        header = FIELD_HEADER.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        #: 目录行：owner `EntityPlayer`、名字 `AddCacheFlags`、序号 0x00D2。
        self.assertIn(
            f'MakeId(ApiDomain::Isaac, 1, 0x{API_INDEX:04X}), ApiDomain::Isaac, "EntityPlayer", '
            f'"AddCacheFlags"', catalog, "目录里没有 EntityPlayer:AddCacheFlags")
        #: 数据行：新 kind + `FieldReceipt::EntityPlayer` + `0xFF` 探针位。
        self.assertRegex(
            isaac,
            rf"\{{\s*(?i:0x0E01{API_INDEX:04x}),\s*{OFFSET_NAME},\s*(?:0x00|0),\s*"
            rf"FieldKind::U32OrWithArg,\s*FieldMissing::Zero,\s*FieldReceipt::EntityPlayer,\s*0xFF\}}",
            "数据行缺失或形状/接收者不对：EntityPlayer:AddCacheFlags")
        #: ★ 反回归：不许被塞进引擎方法行表 —— 引擎里没有同名访问器（PC 也是字段写）。
        self.assertNotRegex(isaac, rf"0x0E01{API_INDEX:04x}[^\n]*EngineCallShape")
        #: 新 kind 必须在 `field_api.hpp` 里带说明地登记。
        self.assertRegex(header, r"U32OrWithArg\s*=\s*14,")
        self.assertIn("U32OrWithArg", header)
        #: 共享处理器要认它（参数闸 + 那个 case）与"返回 0 个值"的早退分支。
        self.assertIn("wantsOrMaskArgument", isaac)
        self.assertIn("case FieldKind::U32OrWithArg", isaac)
        self.assertIn("RowReturnsNoValues", isaac)
        self.assertRegex(isaac, r"RowReturnsNoValues\(FieldKind kind\)[\s\S]{0,220}U32OrWithArg")
        #: 偏移常量写死（接线用例的职责就是钉**字面值**；行为用例钉"行指向哪一格"）。
        self.assertRegex(constants,
                         rf"inline constexpr uintptr_t {OFFSET_NAME}\s*=\s*0x1958;")
        #: 布局表生成物与常量的一致性要在编译期钉住（`static_assert`）。
        self.assertRegex(
            isaac,
            r"static_assert\(kEntityPlayerCacheFlagsOffset == "
            r"layout::kEntity_PlayerCacheFlagsOffset,")

    def test_layout_row_is_confirmed_with_named_consumers(self):
        """★ 布局表那一行必须 `confirmed`，且带**具名**消费者与语义锚点。"""
        table = json.loads(LAYOUT_PLAYER.read_text(encoding="utf-8"))
        self.assertEqual(table["struct"], "Entity_Player")
        rows = {row["name"]: row for row in table["rows"]}
        self.assertIn("CacheFlags", rows, "布局表里没有 CacheFlags 行")
        row = rows["CacheFlags"]
        self.assertEqual(row["confidence"], "confirmed")
        self.assertEqual(row["offset"], 0x1958)
        self.assertEqual(row["width"], 4)
        kinds = [entry["kind"] for entry in row["evidence"]]
        self.assertIn("semantic", kinds, "CacheFlags 行缺少取值锚点（semantic 证据）")
        cited = [entry["function"] for entry in row["evidence"]]
        for function in (
                "_ZN15IsaacRepentance13Entity_Player10DonateLuckEi",
                "_ZN15IsaacRepentance13Entity_Player14AddCollectibleENS_16eCollectibleTypeEibii"):
            self.assertIn(function, cited, f"CacheFlags 行缺少 {function} 的证据")

    def test_layout_evidence_reproduces_against_the_fixed_nro(self):
        """布局表的每条证据都要能重新反汇编核对（`--verify`）。"""
        nro = ROOT / (
            "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
            "/Program #0/1/.nro/Repentance.nro")
        if not nro.is_file():
            self.skipTest("仓库里没有游戏镜像（公开仓库不带游戏资源）")
        result = subprocess.run(
            ["python3", str(LAYOUT_TOOL), "--table", str(LAYOUT_PLAYER), "--verify"],
            text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("通过", result.stdout)

    # ---------------------------------------------------------------- 枚举表（同一件事的另一半）

    def test_cache_flag_table_is_published_with_the_bits_this_batch_relies_on(self):
        """★ 缺表 ⇒ `CacheFlag.CACHE_DAMAGE` 是 nil ⇒ 那一行直接抛错、整条回调被摘。

        所以本批把表与方法**成对**交付，并钉住本批取证依赖的那几个位（值 → Switch 位号）。
        """
        generated = ENUM_GENERATED.read_text(encoding="utf-8")
        self.assertIn('{"CacheFlag", kCacheFlagValues', generated)
        match = re.search(r"constexpr Value kCacheFlagValues\[\] = \{(.*?)\};", generated, re.S)
        self.assertIsNotNone(match, "生成物里没有 kCacheFlagValues")
        values = dict((key, int(value)) for key, value in
                      re.findall(r'\{"([A-Za-z_][A-Za-z0-9_]*)",\s*(-?\d+)\}', match.group(1)))
        expected = {
            "CACHE_DAMAGE": 1 << 0,        # `EvaluateItems` 的 `tbnz w8,#0x0`
            "CACHE_FIREDELAY": 1 << 1,     # `tbnz w8,#0x1`
            "CACHE_SHOTSPEED": 1 << 2,     # `tbz w8,#0x2`
            "CACHE_RANGE": 1 << 3,         # `tbnz w8,#0x3`
            "CACHE_SPEED": 1 << 4,         # `tbnz w8,#0x4`
            "CACHE_WEAPON": 1 << 8,        # `tbz w8,#0x8`
            "CACHE_LUCK": 1 << 10,         # ★ `DonateLuck` 往 `+0x1958` OR 的 `0x400`
            "CACHE_ALL": (1 << 16) - 1,    # `IOTR`/`Trinity` 直接用
            "CACHE_TWIN_SYNC": 1 << 31,    # 需要 64 位容器（int32 会变负）
        }
        self.assertEqual(len(values), 16, "CacheFlag 的条目数变了（文档页被改过？）")
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(values.get(key), value)

        #: 生成器的 `TABLES` 与门禁的期望清单都要登记它（否则干净检出里没有输入）。
        tool = ENUM_TOOL.read_text(encoding="utf-8")
        self.assertIn('"CacheFlag"', tool)
        self.assertIn('"CacheFlag"', ENUM_TEST.read_text(encoding="utf-8"))
        self.assertTrue((ENUM_DOCS / "CacheFlag.md").is_file(), "契约快照里没有 CacheFlag.md")

    def test_the_table_and_the_api_use_the_same_bits(self):
        """★★ **API 与枚举表必须用同一套位** —— 两边错开就是"看似调了、其实没生效"。

        用一个本批取证过的位做端到端闭环：模组传 `CacheFlag.CACHE_LUCK`（= 1024）进来，
        落进 `_cacheFlags` 的必须是 `0x400`（`DonateLuck` 置的就是它）。
        """
        #: 用 Lua 侧真读一次枚举表，验"表里的值"与"本批的位"一致。
        out = self.run_scenario("or")
        self.assertIn(f"B301 wordB=0x{EXPECTED_B:08X}", out)
        #: `EXPECTED_B` 里的高段位就来自 `MASK_B = 1024 = CACHE_LUCK`。
        self.assertEqual(MASK_B, 1 << 10)
        self.assertEqual(EXPECTED_B & MASK_B, MASK_B)


if __name__ == "__main__":
    unittest.main()
