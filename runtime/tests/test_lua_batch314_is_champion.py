"""门禁：`EntityNPC:IsChampion()`（批次 314，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧依据 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `EntityNPC:IsChampion()` | `EntityNPC.md:93` | 没有同名函数 ⇒ 直读 `Entity_NPC + 0xD0F` 那**一个字节** | `Bool` / `False` | 1（BOIStageAPI15） |

走**字段读取型数据行**（`isaac_api.cpp` 的 `kFieldApis`，**0 字节代码**）。

## ★★★ 这一批的核心：更正批次 296 的一条负结果

296 写「PC 的绑定 @ `0x68F550` 是 `cmp byte [ecx+0xB8C],0` + `mov eax,[ecx+0x160];
and eax,0x20000000` —— 两个条件」⇒ 判成"少一半证据、宁缺勿错"。
本批核了名字表：**`push 0x68F550` 在全镜像里出现 0 次**（没有任何名字表项指向它）
⇒ 那段代码**根本不是这条 API 的绑定**，是**读串了函数**。
真绑定是 **`0x68F580`** = `movb 0xbb3(%ecx), %al; ret`（**一条指令、读一个字节**）。

★ 名字表行序（`push <func>; push <name>`，本批的判别依据）在**批次 313 已用两条独立核过的函数
验证过**：`HasBossChallenge → 0x7FA860`、`GetCanSeeEverything → 0x7FA870`
（两条的反汇编我都逐字节核过）。同簇真身：`IsChampion → 0x68F580` / `MakeChampion → 0x6A6570` /
`SetCanSeeEverything → 0x59FED0` / `ControlsEnabled → 0x68F590`（那是 `movb 0x360(%ecx),%al`）。

## 偏移凭什么（三条）

1. **PC**：`movb 0xbb3(%ecx), %al; ret` ⇒ PC `Entity_NPC + 0x0BB3`（读一字节）。
2. **Switch 侧三个具名写入方**（296 当时已经锚定这一格，缺的"另一半"本批证明根本不需要）：
   `Entity_NPC::Init @ 0x105F34` **清 0**、`Entity_NPC::MakeChampion @ 0x108FDC` **置 1**、
   `Entity_NPC::Morph @ 0x10FB5C` **置 1** / 另一支 `0x10FB90` **清 0** —— 而且**每一次都与
   冠军色号 `+0xD10` 同批写**（`MakeChampion` 写 `1` 的同时把第二个实参写进色号）。
3. ★★★ **免费交叉印证**：PC 的标志 `0xBB3`（1 字节）与色号 `0xBB4`（i32）**紧邻、间距 1**；
   Switch 的 `0xD0F`（1 字节）与 `0xD10`（i32）**也是紧邻、间距 1** ⇒ 相对布局两边一致。

## 宿主验到了什么、没验到什么

* **验到**（字段行**没有入口指纹** ⇒ 伪造内存里的字节真会被读出来）：
  写进去什么读回什么、读的是**接收者自己**那一格、**"非 0 即真"**（`0x7F` 也答 true）、
  ★ **读的是"字节"而不是 `u32`**（判别组）、
  ★★★ **与紧邻的那一格分得开**（冠军色号在 `+0xD10`，夹具把两组摆成相反组合 ——
  读错格会立刻答反）、返回**布尔**、参数闸门与接收者闸门、
  ★ **与同族色号互相印证**（`Init`/`MakeChampion` 永远把标志与色号同批写）。
* **没验**：**真机上的偏移归属**。⇒ 真机项 = 作业单 **V64**。
"""

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

#: `(owner, 名字, 域内序号, 偏移常量, FieldKind, FieldMissing)`
FIELD_APIS = (
    ("EntityNPC", "IsChampion", 0x00D9, "kEntityNpcChampionFlagOffset", "Bool", "False"),
)

#: 冠军队列：`(标志字节, 冠军色号)` —— 两个 NPC **摆成相反组合**（读错格/读错对象立刻暴露）。
#: 色号的 `-1` 用 `0xFFFFFFFF` 写（i32 的有符号表示）。
NPC_A = (1, 7)              # 是冠军、色号 7
NPC_B = (0, -1)             # 不是冠军、没有色号


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状与批次 296 的用例同源）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                         = Game*
//   Game + kGamePlayerArrayBegin/End         = 两个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset
//   玩家对象 + kEntityParentOffset            = 第一个 NPC（`ToNPC()` 认它）
//   NPC A 对象首字                            = base + kEntityNpcVtableOffset
//   NPC A + 0xD0F                             = **本批读的冠军标志字节**
//   NPC A + 0xD10                             = 冠军色号（**紧邻那一格**，用来验"没读错格"）
//   NPC A + kEntityParentOffset               = NPC B（第二组相反值）
// ★ 本批是字段行 ⇒ **没有入口指纹** ⇒ 宿主里能真的读到伪造块里的字节（不是降级值）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_NpcABytes;
std::vector<unsigned char> g_NpcBBytes;
std::uintptr_t g_EngineBase = 0;

static_assert(kEntityNpcChampionFlagOffset + sizeof(std::uint8_t) <= kEntityPlayerSize,
              "champion flag must live inside the entity object");
static_assert(kEntityNpcChampionColorIdxOffset + sizeof(std::uint32_t) <= kEntityPlayerSize,
              "champion colour index must live inside the entity object");
//: ★★ 本批最容易犯的错：把标志与**紧邻的**色号读串（`0xD0F` 与 `0xD10` 只差 1）。
static_assert(kEntityNpcChampionFlagOffset + 1 == kEntityNpcChampionColorIdxOffset,
              "the flag must be the byte right before the champion colour index");
static_assert(kEntityNpcChampionFlagOffset != kEntityNpcBossColorIdxOffset,
              "champion flag must not alias the boss colour index");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void MakeFakeEntity(std::vector<unsigned char>& block, std::uintptr_t vtableOffset) {
    block.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(block, 0, g_EngineBase + vtableOffset);
    WriteAt<std::uint32_t>(block, kEntityTypeOffset, kEntityTypePlayer);
}

void WriteChampion(std::vector<unsigned char>& block, std::uint8_t flag, std::int32_t colour) {
    WriteAt<std::uint8_t>(block, kEntityNpcChampionFlagOffset, flag);
    WriteAt<std::int32_t>(block, kEntityNpcChampionColorIdxOffset, colour);
}

void PublishFakeGame(std::uint8_t flagA, std::int32_t colourA,
                     std::uint8_t flagB, std::int32_t colourB) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    MakeFakeEntity(g_NpcABytes, kEntityNpcVtableOffset);
    MakeFakeEntity(g_NpcBBytes, kEntityNpcVtableOffset);
    WriteChampion(g_NpcABytes, flagA, colourA);
    WriteChampion(g_NpcBBytes, flagB, colourB);
    WriteAt<std::uint64_t>(g_NpcABytes, kEntityParentOffset, AddressOf(g_NpcBBytes));

    MakeFakeEntity(g_PlayerBytes, kEntityPlayerVtableOffset);
    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityParentOffset, AddressOf(g_NpcABytes));

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
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
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    // 七个场景：
    //   values   —— A=(标志 1, 色号 7) / B=(标志 0, 色号 -1)（默认）
    //   flipped  —— 反过来摆 ⇒ 两条断言同时对调（专抓"读错对象/写死"）
    //   nonzero  —— 两格标志都写 0x7F（非 0 但不是 1）⇒ 必须 true
    //   highbyte —— 标志格写成 `u32 = 0x100`（低字节 0、第二字节 1）⇒ 必须 false（判别组）
    //   neighbor —— 标志格 0、**紧邻的色号格** 7 ⇒ 标志必须 false（专抓"读错格"）
    //   zero     —— 全 0（★ 色号 0 是**合法**色号，必须与"没有色"的 -1 分得开）
    //   args     —— 参数闸门与接收者闸门
    std::uint8_t flagA = NPC_A_FLAG, flagB = NPC_B_FLAG;
    std::int32_t colourA = NPC_A_COLOUR, colourB = NPC_B_COLOUR;
    bool highByteProbe = false;
    if (std::strcmp(scenario, "values") == 0 || std::strcmp(scenario, "args") == 0) {
        // 默认值即可。
    } else if (std::strcmp(scenario, "flipped") == 0) {
        flagA = 0; colourA = 3;
        flagB = 1; colourB = -1;
    } else if (std::strcmp(scenario, "nonzero") == 0) {
        flagA = 0x7F; colourA = 7;
        flagB = 0x7F; colourB = 7;
    } else if (std::strcmp(scenario, "highbyte") == 0) {
        flagA = 0x00; colourA = 7;
        flagB = 0x00; colourB = 7;
        highByteProbe = true;
    } else if (std::strcmp(scenario, "neighbor") == 0) {
        flagA = 0; colourA = 7;
        flagB = 0; colourB = 7;
    } else if (std::strcmp(scenario, "zero") == 0) {
        flagA = 0; colourA = 0;
        flagB = 0; colourB = 0;
    } else {
        return 91;
    }

    PublishFakeGame(flagA, colourA, flagB, colourB);
    if (highByteProbe) {
        // 覆盖成一个 `u32`：`0x00000100` ⇒ 低字节 0、第二字节 1
        // （★ 这会顺带把 `+0x100` 那一位写进 `+0xD10`，所以这一场**只断言标志**）。
        WriteAt<std::uint32_t>(g_NpcABytes, kEntityNpcChampionFlagOffset, 0x00000100u);
        WriteAt<std::uint32_t>(g_NpcBBytes, kEntityNpcChampionFlagOffset, 0x00000100u);
    }
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " local a = p.Parent:ToNPC()"
        " print('B314 pkind=' .. type(p))"
        " print('B314 akind=' .. type(a))"
        " print('B314 fn=' .. type(a.IsChampion))"
        " local ca = a:IsChampion()"
        " print('B314 achamp=' .. tostring(ca))"
        " print('B314 atype=' .. type(ca))"
        // ★ 同族色号（紧邻那一格）——"标志与色号互相印证"这条判据需要它一起读回来。
        " print('B314 acolour=' .. tostring(a:GetChampionColorIdx()))"
        " local b = a.Parent:ToNPC()"
        " print('B314 bkind=' .. type(b))"
        " print('B314 bchamp=' .. tostring(b:IsChampion()))"
        " print('B314 bcolour=' .. tostring(b:GetChampionColorIdx()))"
        // 参数闸门：字段行**恰好收一个**（只有接收者）。
        " print('B314 arg=' .. ok(function() return a:IsChampion(1) end))"
        " print('B314 argerr=' .. err(function() return a:IsChampion(1) end))"
        // 点号显式 self（1 个参数）⇒ 放行。
        " print('B314 dot=' .. ok(function() return a.IsChampion(a) end))"
        // 接收者闸门：不是实体句柄 ⇒ **硬报错**（全族共用）。
        " print('B314 badrecv=' .. ok(function() return a.IsChampion({}) end))"
        " print('B314 badrecverr=' .. err(function() return a.IsChampion({}) end))"
        // 对照：同族色号拿同一个坏接收者**也报同样的错**。
        " local g = a.GetChampionColorIdx"
        " print('B314 siblingbadrecv=' .. ok(function() return g({}) end))"
        " print('B314 sibling=' .. type(a.GetChampionColorIdx))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b314.lua");
    static_cast<void>(result);
    return 0;
}
'''
# 夹具里的取值从 Python 侧注进去（单一真值来源）。
HARNESS = (HARNESS
           .replace("NPC_A_FLAG", str(NPC_A[0]))
           .replace("NPC_A_COLOUR", str(NPC_A[1]))
           .replace("NPC_B_FLAG", str(NPC_B[0]))
           .replace("NPC_B_COLOUR", str(NPC_B[1])))


class NpcIsChampionBatch314Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b314-")
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
        # ★ 把 stderr 一起交回：只回 stdout 时，"脚本中途报错"与"什么都没做"长得一模一样。
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_flag_is_read_from_the_receivers_own_byte(self):
        """★ 写进去什么就读回什么，而且是**接收者自己那个对象**的格子、返回**布尔**。

        第一场：A =（标志 1、色号 7）、B =（标志 0、色号 -1）⇒ `achamp=true` / `bchamp=false`。
        ★★ 同时把两条同族色号读回来核对：`acolour=7` / `bcolour=-1` ——
        `MakeChampion` 在引擎里**永远把标志与色号同批写**，所以两者必须互相印证。
        """
        out = self.run_scenario("values")
        self.assertIn("B314 pkind=userdata", out)
        self.assertIn("B314 akind=userdata", out)
        self.assertIn("B314 fn=function", out)
        self.assertIn("B314 achamp=true", out)
        self.assertIn("B314 atype=boolean", out)
        self.assertIn("B314 acolour=7", out)
        self.assertIn("B314 bkind=userdata", out)
        self.assertIn("B314 bchamp=false", out)
        self.assertIn("B314 bcolour=-1", out)

    def test_flag_flips_with_the_receiver(self):
        """把两个 NPC 的取值**反过来摆** ⇒ 四条断言同时对调。

        这一场专抓三类错法：① 实现把接收者写死成"玩家/第一个 NPC"（那 `bchamp` 会跟 `achamp` 一样）；
        ② 把结果写死成 `true`/`false`；③ 读的是**紧邻的色号格**（那 `achamp` 会跟着色号走）。
        """
        out = self.run_scenario("flipped")
        self.assertIn("B314 achamp=false", out)
        self.assertIn("B314 acolour=3", out)
        self.assertIn("B314 bchamp=true", out)
        self.assertIn("B314 bcolour=-1", out)

    def test_non_zero_means_true(self):
        """`0x7F`（非 0 但**不是 1**）⇒ 必须答 `true`。

        PC 的绑定本体是 `movb 0xbb3(%ecx), %al` 加胶水层的布尔转换 ⇒ **非 0 即真**。
        写成"等于 1 才真"会在这一格被当成位标志用时静默答错。
        """
        out = self.run_scenario("nonzero")
        self.assertIn("B314 achamp=true", out)
        self.assertIn("B314 bchamp=true", out)

    def test_reads_a_byte_not_a_u32(self):
        """★ 判别组：标志格写 `u32 = 0x100`（低字节 0、第二字节 1）⇒ 按**字节**读必须答 `false`。

        按 `u32` 读（`BoolNonZero`）会读到 `256` ⇒ 答 `true`。
        ★ 这一场**只看标志**（那个 `u32` 会顺带盖掉紧邻色号格的高位）。
        """
        out = self.run_scenario("highbyte")
        self.assertIn("B314 achamp=false", out)
        self.assertIn("B314 bchamp=false", out)
        self.assertNotIn("B314 achamp=true", out)

    def test_does_not_read_the_neighbouring_colour_idx_byte(self):
        """★★★ **本批特有的判别组**：标志格 `=0`、**紧邻的色号格** `=7` ⇒ 标志必须答 `false`。

        两格在引擎里只差 1 字节（`+0xD0F` 是 byte、`+0xD10` 是 i32），而且**永远同批写**
        ⇒ 真机上把 `+0xD10` 读成 `+0xD0F`（或直接把偏移写成色号那一格）**完全看不出来**：
        冠军的两格都会是"非 0"。只有宿主能把它们分开 —— 所以这一场必须存在。
        """
        out = self.run_scenario("neighbor")
        self.assertIn("B314 achamp=false", out)
        self.assertIn("B314 bchamp=false", out)
        self.assertIn("B314 acolour=7", out)

    def test_zero_is_false_and_zero_colour_is_valid(self):
        """全 0 ⇒ 标志答 `false`；★ 同时色号答 **0**（0 是**合法**色号，与"没有"的 -1 分得开）。

        这一场钉住降级档：`FieldMissing::False` 的 `false` 与"读到 0"同值，
        而色号那边的 `-1` 才是"没有"（两条同族的降级档不同，别互相照抄）。
        """
        out = self.run_scenario("zero")
        self.assertIn("B314 achamp=false", out)
        self.assertIn("B314 bchamp=false", out)
        self.assertIn("B314 acolour=0", out)
        self.assertIn("B314 bcolour=0", out)

    def test_gates_and_receiver(self):
        """参数闸门 = **恰好一个**（只有接收者）；接收者不是实体句柄 = **硬报错**。"""
        out = self.run_scenario("args")
        self.assertIn("B314 arg=false", out)
        self.assertIn("EntityNPC:IsChampion accepts no arguments", out)
        self.assertIn("B314 dot=true", out)
        self.assertIn("B314 badrecv=false", out)
        self.assertIn("expected an Entity", out)
        self.assertIn("B314 siblingbadrecv=false", out)
        self.assertIn("B314 sibling=function", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与降级档 / 偏移常量 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for owner, name, index, prefix, kind, missing in FIELD_APIS:
            with self.subTest(api=f"{owner}:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "{owner}", '
                    f'"{name}"',
                    catalog, f"目录里没有 {owner}:{name}")
                self.assertRegex(
                    isaac,
                    rf"\{{\s*(?i:0x0e01{index:04x}),\s*{prefix},\s*0,\s*"
                    rf"FieldKind::{kind},\s*FieldMissing::{missing},\s*"
                    rf"FieldReceipt::Entity,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档不对：{owner}:{name}")
                self.assertRegex(constants, rf"inline constexpr uintptr_t {prefix}\s*=\s*0x[0-9A-Fa-f]+;")

        #: ★ 反回归：这一条**不许**被塞进引擎方法行表（引擎里没有同名函数，
        #:   `tools/mangled_impl_count.py IsChampion` = 0 个实现）。
        self.assertNotRegex(isaac, r"0x0E0100D9[^\n]*EngineCallShape")

    def test_the_evidence_is_recorded(self):
        """★ 常量段必须写明 PC 绑定 VA、"读串了函数"的更正、三个具名写入方与紧邻交叉印证。

        这条不是形式主义：批次 296 就是因为把**紧邻的另一个函数**当成这条 API 的绑定，
        才把它判成"两个条件、少一半证据"。丢掉这段，后人会**再犯一次同样的错**。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("inline constexpr uintptr_t kEntityNpcChampionFlagOffset = 0xD0F;", constants)
        for token in ("0x68F580", "0x68F550", "0xbb3", "0xBB3", "0xBB4", "0x108FDC", "0x105F34",
                      "0x10FB5C", "MakeChampion", "IsChampion", "0x14"):
            self.assertIn(token, constants, f"证据 {token} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()
