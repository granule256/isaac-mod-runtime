"""门禁：`Entity_NPC` 的两个颜色索引 + `Entity_Player` 的主动道具充能（批次 296，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧字段 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `EntityNPC:GetChampionColorIdx()` | `EntityNPC.md:77` | `Entity_NPC + 0xD10`（`i32`） | 字段行 `I32` / 降级 `MinusOne` | 1 |
| `EntityNPC:GetBossColorIdx()` | `EntityNPC.md:69` | `Entity_NPC + 0xD24`（`i32`） | 字段行 `I32` / 降级 `MinusOne` | 1 |
| `EntityPlayer:GetActiveCharge(slot = 0)` | `EntityPlayer.md:757` | `Entity_Player + 0x1968 + 0x1C*槽位`（`i32`） | **手写处理器**（要按下标取） | 3 |

前两条走**字段读取型数据行**（`0 字节代码`）、第三条是**手写处理器** —— 因为现有 kind 里没有
「带下标」的形状（`SumU32Array` 是整段求和、`BoolBit` 的 `offset2` 是位号），而同族的
`EntityPlayerGetActiveItem` 就是手写的直读，两者逐字同形。

## 为什么这三格就是这三个量

**PC 侧的标尺**（`tools/pc_exe_binding.py <名字> --disasm`，三条绑定本体都只有 `mov`+`ret`）：

| API | PC 绑定 VA | 指令 | PC 偏移 | Switch 偏移 |
| --- | --- | --- | --- | --- |
| `GetChampionColorIdx` | `0x680DE0` | `mov eax,[ecx+0xBB4]` | `0xBB4` | `0xD10` |
| `GetBossColorIdx` | `0x7A7FD0` | `mov eax,[ecx+0xBC8]` | `0xBC8` | `0xD24` |
| `GetActiveCharge` | `0x4F3F30` | `mov eax,[ecx+4*eax+0x14C8]`（`eax=7*槽位`） | `0x14C8 + 0x1C*槽位` | `0x1968 + 0x1C*槽位` |

★ PC 的两个颜色索引**相距 `0x14`**，Switch 的**也相距 `0x14`** ⇒ 顺序与间距一致是免费印证；
但**偏移数值完全不同**，不许平移。

**Switch 侧的具名消费者**（不是"照 PC 平移"）：

* `0xD10` = 冠军色号：写入方 `Entity_NPC::Init`（`0x105F14`，值 = `mov w25,#-0x1` ⇒ 默认 -1）、
  `MakeChampion(int Seed, ChampionColorIdx, bool Init)`（`0x108FE0`，第二个实参）、
  `Morph(type, Variant, SubType, ChampionColorIdx)`（`0x10FB58`，第四个实参；另一支
  `0x10FB8C` 在实体配置说「不冠军」时写回 -1）；读者 `fix_champion_color @ 0x107090`
  （`cmp w8,#0x6` / `mov w8,#0x11` 是取值锚点）。
* `0xD24` = Boss 色号：写入方 `Init`（`0x105F40`，默认 -1）、`SetBossColorIdx(int,bool) @ 0x11FDA0`
  （`0x11FDB0` 写第一个实参；`0x11FDA0`+`cmp`+`b.eq` 是「值没变就不做事」的守卫）、
  `load_entity_config`；读者 `translate_gfx_path @ 0x107AA8`（读它 → `tbnz w8,#0x1F` 判负 →
  按 `0x80` 步长到 `EntityConfig::BossColor` 取第 idx 项）、`reset_color @ 0x10FE00`。
* `0x1968` = 主动道具充能：**同一个槽位数组**的第 `slot` 个元素（步长 `0x1C`、元素基址 `0x1964`，
  该数组的 `+0` 格早被 `GetActiveItem` 消费）。写入方 `Entity_Player::SetActiveCharge(int,int)
  @ 0x27F984`（主充能 = `min(实参, GetActiveMaxCharge)` 写 `0x1968`；溢出写 `0x196C`），
  读者 `Entity_Player::GetTotalActiveCharge(int) @ 0x29B43C`（把 `0x1968` 与 `0x196C` **相加**）。

## 宿主验到了什么、没验到什么

* **验到**（字段行没有入口指纹 ⇒ 伪造内存里的值真会被读出来）：
  - ★★ **读的是"接收者自己"**：夹具里有两个 NPC 对象（值两两不同）与两个玩家（同一槽位不同充能）
    ⇒ 读错对象/读错槽位都会红；
  - ★ **读取失败与读到合法值要分开**：`-1` 是降级值也是引擎 `Init` 的默认值，而 `0` 是**合法色号**
    ⇒ 夹具里摆一个真写 0 的对象，两条路径必须分别给出 0 与 -1；
  - ★ **带下标的读**：`GetActiveCharge(0)` 与 `(1)` 取到**不同**的值 ⇒ 「不按下标读」会红；
  - ★ **缺省参数**：`GetActiveCharge()` 等于 `GetActiveCharge(0)`（PC 的 `ActiveSlot` 缺省
    `SLOT_PRIMARY = 0`）；
  - **越界/负槽位 ⇒ 0**（`GetActiveItem` 的既有口径），且**不抛 Lua 错误**；
  - **参数闸门**：字段行恰好收一个（多给报错）；`GetActiveCharge` 最多收一个槽位。
* **没验**：
  1. 真机上这三格是不是就是那三个量（宿主里"偏移对不对"是同一张表的两处引用同一个常量，
     自己证不了自己）、以及真机上的数值。⇒ 真机项 = 作业单 **V47**。
  2. 「接收者解析成 0 ⇒ 降级成 -1 / 0」那条分支在宿主里**不可达**：`EntityNPC` 句柄只能由
     `Entity:ToNPC()` 产生，而它已经校验过 vptr ⇒ 到行处理器里指针必然有效；而传一个非实体
     （如一张表）会被共享的 `CheckEntityHandle` **直接报错**（批次 287/288 同口径）。
     ⇒ 本文件只验"非实体接收者会报错"，降级的**值**由行形状（`FieldMissing::MinusOne`）钉住。
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
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
LAYOUT_NPC = ROOT / "tools" / "layout_tables" / "entity_npc.json"
LAYOUT_TOOL = ROOT / "tools" / "build_layout_table.py"

#: `(名字, 域内序号, 偏移常量, 降级档)` —— 前两条是 `EntityNPC` 的字段行。
FIELD_APIS = (
    ("GetChampionColorIdx", 0x00CD, "kEntityNpcChampionColorIdxOffset"),
    ("GetBossColorIdx", 0x00CE, "kEntityNpcBossColorIdxOffset"),
)

#: `EntityPlayer:GetActiveCharge` 的目录序号与两个**既有**常量（本批零新增偏移）。
CHARGE_API = ("GetActiveCharge", 0x00CF, "kEntityPlayerActiveItemChargeOffset",
              "kEntityPlayerActiveItemStride")

#: 夹具里两个 NPC 的 `(champion, boss)` 组合（互不相同 ⇒ 读错对象会红）。
NPC_A = (2, 5)
NPC_B = (-1, 0)
#: 两个玩家的充能：`(槽位0, 槽位1, 槽位2, 槽位3)`。
PLAYER_A = (4, 7, 1, 11)
PLAYER_B = (9, 0, 0, 3)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 287/293 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                         = Game*
//   Game + kGamePlayerArrayBegin/End         = 两个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset（`IsEntityPlayer` 要**精确**这个值）
//   玩家对象 + kEntityParentOffset            = 第一个 NPC 对象
//   NPC 对象首字                              = base + kEntityNpcVtableOffset（`ToNPC()` 的区间判据要它）
//   NPC 对象 + 0xD10 / +0xD24                 = 本批读的两格颜色
//   NPC 对象 + kEntityParentOffset            = 第二个 NPC 对象
//   玩家对象 + 0x1968 + 0x1C*槽位             = 本批读的充能（同一槽位数组，`GetActiveItem` 用它的 +0 格）
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerABytes;
std::vector<unsigned char> g_PlayerBBytes;
std::vector<unsigned char> g_NpcABytes;
std::vector<unsigned char> g_NpcBBytes;
std::uintptr_t g_EngineBase = 0;

static_assert(kEntityNpcChampionColorIdxOffset + sizeof(std::uint32_t) <= kEntityPlayerSize,
              "champion colour index must live inside the entity object");
static_assert(kEntityNpcBossColorIdxOffset + sizeof(std::uint32_t) <= kEntityPlayerSize,
              "boss colour index must live inside the entity object");
static_assert(kEntityPlayerActiveItemChargeOffset + 4 * kEntityPlayerActiveItemStride
                  <= kEntityPlayerSize,
              "the four charge slots must live inside the player object");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
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

void WriteColours(std::vector<unsigned char>& block, std::uint32_t champion, std::uint32_t boss) {
    WriteAt<std::uint32_t>(block, kEntityNpcChampionColorIdxOffset, champion);
    WriteAt<std::uint32_t>(block, kEntityNpcBossColorIdxOffset, boss);
}

void WriteCharges(std::vector<unsigned char>& block, const std::uint32_t (&charges)[4]) {
    for (std::size_t slot = 0; slot < 4; ++slot) {
        WriteAt<std::uint32_t>(block,
                               kEntityPlayerActiveItemChargeOffset +
                                   slot * kEntityPlayerActiveItemStride,
                               charges[slot]);
    }
}

void PublishFakeGame(const std::uint32_t (&chargesA)[4], const std::uint32_t (&chargesB)[4],
                     std::uint32_t championA, std::uint32_t bossA,
                     std::uint32_t championB, std::uint32_t bossB) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    // 两个 NPC：`p.Parent` 是第一个（`ToNPC()` 会按 vptr 认出它是 NPC 家族）、
    // 第一个的 `Parent` 是第二个 ⇒ 两个都能转成 `EntityNPC` 句柄。
    MakeFakeEntity(g_NpcABytes, kEntityNpcVtableOffset);
    MakeFakeEntity(g_NpcBBytes, kEntityNpcVtableOffset);
    WriteColours(g_NpcABytes, championA, bossA);
    WriteColours(g_NpcBBytes, championB, bossB);
    WriteAt<std::uint64_t>(g_NpcABytes, kEntityParentOffset, AddressOf(g_NpcBBytes));

    MakeFakeEntity(g_PlayerABytes, kEntityPlayerVtableOffset);
    MakeFakeEntity(g_PlayerBBytes, kEntityPlayerVtableOffset);
    WriteCharges(g_PlayerABytes, chargesA);
    WriteCharges(g_PlayerBBytes, chargesB);
    WriteAt<std::uint64_t>(g_PlayerABytes, kEntityParentOffset, AddressOf(g_NpcABytes));

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0, AddressOf(g_PlayerABytes));
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, sizeof(std::uint64_t), AddressOf(g_PlayerBBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + 2 * sizeof(std::uint64_t));

    LuaRuntime::SetEngineModuleBase(g_EngineBase);
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

    // 三个场景：
    //   values —— 两个 NPC / 两个玩家各摆**互不相同**的值（默认）
    //   zero   —— 全 0（`0` 是合法色号 ⇒ 与"读不到"的 -1 必须分开）
    //   args   —— 参数闸门、越界槽位、以及"接收者不是实体"时报错
    std::uint32_t chargesA[4] = {PLAYER_A_VALUES};
    std::uint32_t chargesB[4] = {PLAYER_B_VALUES};
    std::uint32_t championA = NPC_A_CHAMPION, bossA = NPC_A_BOSS;
    std::uint32_t championB = NPC_B_CHAMPION, bossB = NPC_B_BOSS;
    if (std::strcmp(scenario, "values") == 0 || std::strcmp(scenario, "args") == 0) {
        // 默认值即可。
    } else if (std::strcmp(scenario, "zero") == 0) {
        for (int i = 0; i < 4; ++i) { chargesA[i] = 0; chargesB[i] = 0; }
        championA = 0; bossA = 0; championB = 0; bossB = 0;
    } else {
        return 91;
    }

    PublishFakeGame(chargesA, chargesB, championA, bossA, championB, bossB);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* readings =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " local npc = p.Parent:ToNPC()"
        " print('B296 pkind=' .. type(p))"
        " print('B296 npckind=' .. type(npc))"
        " print('B296 npcfn=' .. type(npc.GetChampionColorIdx) .. ',' .. type(npc.GetBossColorIdx))"
        // 第一个 NPC 的两格
        " print('B296 achamp=' .. tostring(npc:GetChampionColorIdx()))"
        " print('B296 aboss=' .. tostring(npc:GetBossColorIdx()))"
        " print('B296 ckind=' .. type(npc:GetBossColorIdx()))"
        // 第二个 NPC（`npc.Parent`）—— 与第一个值不同
        " local npc2 = npc.Parent:ToNPC()"
        " print('B296 npc2kind=' .. type(npc2))"
        " print('B296 bchamp=' .. tostring(npc2:GetChampionColorIdx()))"
        " print('B296 bboss=' .. tostring(npc2:GetBossColorIdx()))"
        // 充能：同一个玩家不同槽位、两个玩家同一槽位
        " print('B296 p0c0=' .. tostring(p:GetActiveCharge(0)))"
        " print('B296 p0c1=' .. tostring(p:GetActiveCharge(1)))"
        " print('B296 p0c3=' .. tostring(p:GetActiveCharge(3)))"
        " print('B296 p0cdef=' .. tostring(p:GetActiveCharge()))"
        " local p2 = Isaac.GetPlayer(1)"
        " print('B296 p2kind=' .. type(p2))"
        " print('B296 p1c0=' .. tostring(p2:GetActiveCharge(0)))";

    // 参数闸门 + 越界槽位 + "接收者不是实体"。
    // ★ 最后两条**会报错**（`CheckEntityHandle` 对非句柄直接 `luaL_error`）—— 这是既有口径
    //   （批次 287/288 的用例同样断言 `badrecv=false` + `expected an Entity`），不是本批的缺陷：
    //   `EntityNPC` 句柄只能由 `ToNPC()` 产生、那时指针必然有效，所以"接收者解析成 0"那条
    //   降级分支在宿主里**不可达**（见文件头《宿主验到了什么》）。
    const char* gate =
        "local p = Isaac.GetPlayer(0)"
        " local npc = p.Parent:ToNPC()"
        " local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " print('B296 argchamp=' .. ok(function() return npc:GetChampionColorIdx(1) end))"
        " print('B296 argchamperr=' .. err(function() return npc:GetChampionColorIdx(1) end))"
        " print('B296 argcharge2=' .. ok(function() return p:GetActiveCharge(0, 1) end))"
        " print('B296 slotneg=' .. tostring(p:GetActiveCharge(-1)))"
        " print('B296 slotbig=' .. tostring(p:GetActiveCharge(9)))"
        " print('B296 badchamp=' .. ok(function() return npc.GetChampionColorIdx({}) end))"
        " print('B296 badcharge=' .. ok(function() return p.GetActiveCharge({}) end))"
        " print('B296 badmsg=' .. err(function() return p.GetActiveCharge({}) end))";

    const char* script = std::strcmp(scenario, "args") == 0 ? gate : readings;
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b296.lua");
    static_cast<void>(result);
    return 0;
}
'''
# 夹具里两个 NPC / 两个玩家的取值从 Python 侧注进去（单一真值来源）。
HARNESS = (HARNESS
           .replace("PLAYER_A_VALUES", ", ".join(str(v) for v in PLAYER_A))
           .replace("PLAYER_B_VALUES", ", ".join(str(v) for v in PLAYER_B))
           .replace("NPC_A_CHAMPION", str(NPC_A[0])).replace("NPC_A_BOSS", str(NPC_A[1]))
           .replace("NPC_B_CHAMPION", str(NPC_B[0])).replace("NPC_B_BOSS", str(NPC_B[1])))


class NpcColoursAndChargeBatch296Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b296-")
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

    def test_reads_from_the_receiver_itself(self):
        """★★ 两个 NPC 与两个玩家各摆互不相同的值 ⇒ 读错对象 / 读错槽位都会红。

        只断言"函数被调到了"是没用的（常量、恒 -1、读错格都能过）；这里四组值两两不同。
        """
        out = self.run_scenario("values")
        self.assertIn("B296 pkind=userdata", out)
        self.assertIn("B296 npckind=userdata", out)
        self.assertIn("B296 npcfn=function,function", out)
        self.assertIn("B296 ckind=number", out)
        #: 第一个 NPC：冠军 2 / Boss 5
        self.assertIn("B296 achamp=2", out)
        self.assertIn("B296 aboss=5", out)
        #: 第二个 NPC（`npc.Parent`）：冠军 -1 / Boss 0 —— 与第一个互不相同
        self.assertIn("B296 npc2kind=userdata", out)
        self.assertIn("B296 bchamp=-1", out)
        self.assertIn("B296 bboss=0", out)
        #: 同一个玩家的不同槽位取到不同值（"不按下标读"会红）
        self.assertIn("B296 p0c0=4", out)
        self.assertIn("B296 p0c1=7", out)
        self.assertIn("B296 p0c3=11", out)
        #: 缺省参数 = 槽位 0（PC 的 `ActiveSlot` 缺省 `SLOT_PRIMARY = 0`）
        self.assertIn("B296 p0cdef=4", out)
        #: 第二个玩家的同一槽位是另一个值
        self.assertIn("B296 p2kind=userdata", out)
        self.assertIn("B296 p1c0=9", out)

    def test_zero_is_a_legal_value_and_differs_from_degradation(self):
        """★ `0` 是**合法**色号/充能；读不到时那两条颜色行答的是 `-1` ⇒ 两条路径必须分开。

        这一场全 0：颜色读回 `0`（不是 -1），充能读回 `0`。
        """
        out = self.run_scenario("zero")
        self.assertIn("B296 achamp=0", out)
        self.assertIn("B296 aboss=0", out)
        self.assertIn("B296 bchamp=0", out)
        self.assertIn("B296 bboss=0", out)
        self.assertIn("B296 p0c0=0", out)
        self.assertIn("B296 p0cdef=0", out)
        self.assertIn("B296 p1c0=0", out)
        #: 与降级值区分：降级是 -1，而这里是 0。
        self.assertNotIn("B296 achamp=-1", out)

    def test_non_entity_receiver_errors_like_the_rest_of_the_family(self):
        """接收者不是实体（把一张表当作 `self`）⇒ **报错**（`expected an Entity…`），与同族口径一致。

        ★ 这一场**不**验"接收者解析成 0 ⇒ 降级成 -1/0"那条分支：`EntityNPC` 句柄只能由
        `Entity:ToNPC()` 产生，而 `ToNPC()` 已经做过 vptr 校验 ⇒ 到了行处理器里指针必然有效，
        那条分支在宿主里**不可达**（批次 287/288 的用例同样只断言报错）。降级的**值**
        （颜色 -1：照 `Entity_NPC::Init` 的构造默认值；充能 0：0 就是「没有充能」）
        由 `FieldMissing`/`PushPlayerUintOrZero` 与本文件 `test_wiring` 的行形状共同钉住。
        """
        out = self.run_scenario("args")
        self.assertIn("B296 badchamp=false", out)
        self.assertIn("B296 badcharge=false", out)
        #: 报错消息来自共享的 `CheckEntityHandle`（不是本批新写的），里面列出了合法视图。
        self.assertIn("expected an Entity", out)

    def test_argument_gate_and_slot_bounds(self):
        """参数闸门：字段行恰好收一个（多给报错）；充能最多收一个槽位、越界答 0。"""
        out = self.run_scenario("args")
        #: 字段行多给一个参数 ⇒ `pcall` 返回 false，且错误消息里有 API 名与"不收参数"。
        self.assertIn("B296 argchamp=false", out)
        self.assertIn("EntityNPC:GetChampionColorIdx accepts no arguments", out)
        #: 充能多给一个参数 ⇒ 报错
        self.assertIn("B296 argcharge2=false", out)
        #: 负槽位 / 越界槽位 ⇒ 0（不读可能落在别的字段上的地址）
        self.assertIn("B296 slotneg=0", out)
        self.assertIn("B296 slotbig=0", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 种类与降级档 / 接收者 / 偏移常量 / 手写处理器的登记。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for name, index, offset_name in FIELD_APIS:
            with self.subTest(api=f"EntityNPC:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "EntityNPC", "{name}"',
                    catalog, f"目录里没有 EntityNPC:{name}")
                #: 两条都是 `I32` + `MinusOne` + `FieldReceipt::Entity`（既有接收者）。
                self.assertRegex(
                    isaac,
                    rf"\{{\s*(?i:0x0E01{index:04x}),\s*{offset_name},\s*(?:0x00|0),\s*"
                    rf"FieldKind::I32,\s*FieldMissing::MinusOne,\s*FieldReceipt::Entity,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档/接收者不对：EntityNPC:{name}")
                #: ★ 反回归：不许被塞进引擎方法行表 —— 这两条引擎里没有同名访问器。
                self.assertNotRegex(isaac, rf"0x0E01{index:04x}[^\n]*EngineCallShape")

        #: 第三条是手写处理器：目录行 + `kEntityPlayerHandlers` 绑定 + 函数定义。
        charge_name, charge_index, charge_offset, charge_stride = CHARGE_API
        self.assertIn(
            f'MakeId(ApiDomain::Isaac, 1, 0x{charge_index:04X}), ApiDomain::Isaac, "EntityPlayer", '
            f'"{charge_name}"', catalog, "目录里没有 EntityPlayer:GetActiveCharge")
        self.assertRegex(
            isaac,
            rf"\{{\s*(?i:0x0E01{charge_index:04x}),\s*&EntityPlayerGetActiveCharge\}}",
            "`kEntityPlayerHandlers` 里没有 GetActiveCharge 的绑定行")
        self.assertIn("int EntityPlayerGetActiveCharge(lua_State* state);", isaac,
                      "手写处理器缺少前置声明（绑定表在定义之前）")
        self.assertIn("int EntityPlayerGetActiveCharge(lua_State* state) {", isaac,
                      "手写处理器没有定义")
        #: 它必须**复用**既有常量，而不是新写一个偏移。
        self.assertRegex(
            isaac,
            rf"{charge_offset}\s*\+\s*\n\s*static_cast<std::uintptr_t>\(slot\)\s*\*\s*{charge_stride}",
            "手写处理器没有按 槽位*步长 取元素（或没有复用既有常量）")
        #: 这两条常量必须**本来就存在**（本批零新增偏移）。
        self.assertRegex(constants, r"inline constexpr uintptr_t "
                                    r"kEntityPlayerActiveItemChargeOffset\s*=\s*0x1968;")
        self.assertRegex(constants, r"inline constexpr uintptr_t "
                                    r"kEntityPlayerActiveItemStride\s*=\s*0x1C;")

        #: 本批新加的两个常量（布局表那一对）。
        self.assertRegex(constants, r"inline constexpr uintptr_t "
                                    r"kEntityNpcChampionColorIdxOffset\s*=\s*0xD10;")
        self.assertRegex(constants, r"inline constexpr uintptr_t "
                                    r"kEntityNpcBossColorIdxOffset\s*=\s*0xD24;")
        #: ★ 常量段要写下 PC 的三个绑定 VA 与三段证据里最关键的地址（标尺 + 锚点）。
        import re

        written = {int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", constants)}
        for va in (0x680DE0, 0x7A7FD0, 0x4F3F30,          # PC 三个绑定本体
                   0x105F14, 0x105F40,                    # Init 写两个默认 -1
                   0x108FE0, 0x10FB58, 0x11FDB0,          # MakeChampion / Morph / SetBossColorIdx
                   0x107090, 0x1070D0,                    # fix_champion_color（读 + 取值锚点）
                   0x107AA8, 0x107AB0, 0x10FE00,          # translate_gfx_path / reset_color
                   0x27F984, 0x27FAEC, 0x29B43C, 0x29B458):  # SetActiveCharge / GetTotalActiveCharge
            self.assertIn(va, written, f"证据地址 {va:#x} 没有写进常量段")
        #: PC 侧那两对偏移也要写下来（"相距 0x14 且顺序一致"这条免费印证的一半）。
        for off in (0xBB4, 0xBC8, 0x14C8, 0x1964, 0x1968):
            self.assertIn(off, written, f"PC 侧的偏移 {off:#x} 没有写进常量段")

    def test_layout_rows_are_confirmed_with_named_consumers(self):
        """★ 布局表两行必须 `confirmed` 且带**具名**消费者与语义锚点。"""
        table = json.loads(LAYOUT_NPC.read_text(encoding="utf-8"))
        self.assertEqual(table["struct"], "Entity_NPC")
        rows = {row["name"]: row for row in table["rows"]}
        expected = {
            "ChampionColorIdx": (0xD10, [
                "_ZN15IsaacRepentance10Entity_NPC4InitENS_11eEntityTypeEjjj",
                "_ZN15IsaacRepentance10Entity_NPC12MakeChampionEjib",
                "_ZN15IsaacRepentance10Entity_NPC5MorphENS_11eEntityTypeEjji",
                "_ZN15IsaacRepentance10Entity_NPC18fix_champion_colorEv"]),
            "BossColorIdx": (0xD24, [
                "_ZN15IsaacRepentance10Entity_NPC4InitENS_11eEntityTypeEjjj",
                "_ZN15IsaacRepentance10Entity_NPC15SetBossColorIdxEib",
                "_ZN15IsaacRepentance10Entity_NPC18translate_gfx_pathERKNSt3__112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE",
                "_ZN15IsaacRepentance10Entity_NPC11reset_colorEv"]),
        }
        for name, (offset, functions) in expected.items():
            with self.subTest(row=name):
                self.assertIn(name, rows, f"布局表里没有 {name} 行")
                row = rows[name]
                self.assertEqual(row["confidence"], "confirmed")
                self.assertEqual(row["offset"], offset)
                self.assertEqual(row["width"], 4)
                kinds = [e["kind"] for e in row["evidence"]]
                self.assertIn("semantic", kinds, f"{name} 行缺少取值锚点（semantic 证据）")
                cited = [e["function"] for e in row["evidence"]]
                for function in functions:
                    self.assertIn(function, cited, f"{name} 行缺少 {function} 的证据")

    def test_layout_evidence_reproduces_against_the_fixed_nro(self):
        """布局表的每条证据都要能重新反汇编核对（`--verify`）。"""
        nro = ROOT / (
            "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
            "/Program #0/1/.nro/Repentance.nro")
        if not nro.is_file():
            self.skipTest("仓库里没有游戏镜像（公开仓库不带游戏资源）")
        result = subprocess.run(
            ["python3", str(LAYOUT_TOOL), "--table", str(LAYOUT_NPC), "--verify"],
            text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("通过", result.stdout)


if __name__ == "__main__":
    unittest.main()
