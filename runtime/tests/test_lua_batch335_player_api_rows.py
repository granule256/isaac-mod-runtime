"""门禁：批次 335（2026-10-03）—— 交接第八份 §3「批 A」的三条**引擎方法数据行**。

## 这一批补的是哪三条、为什么能合成一批

| API | 处 | 契约 | 引擎符号 | 形状 |
| --- | --- | --- | --- | --- |
| `EntityPlayer:ChangePlayerType(PlayerType)` | 1 | `EntityPlayer.md:581` | `Entity_Player::ChangePlayerType(ePlayerType, bool)` @ `0x2AACCC` | **新形状 33** `VoidIntBoolOpt1` |
| `EntityPlayer:DischargeActiveItem(ActiveSlot)` | 1 | `EntityPlayer.md:642` | `Entity_Player::DischargeActiveItem(int, bool)` @ `0x2B9540` | **同一个新形状** |
| `Seeds:SetStartSeed(int)` | 2 | `Seeds.md:170` | `Seeds::SetStartSeed(unsigned int)` @ `0x4A1114` | 既有 `Void1` |

三条的**共同点**（这就是它们能合成一批的理由）：
* 契约写的形参个数 < 引擎符号的形参个数，且**差的那一格是尾部一个 `bool`**
  （`SetStartSeed` 是另一回事：契约写 `string`、语料给数字 ⇒ 引擎里有两个重载，取数字那个）；
* 都在 `needs_new_receiver` 桶里，但**接收者其实早就有了**（`FieldReceipt::EntityPlayer`）
  —— 只有 `Seeds` 真的缺一档，本批补了。

## 判据

★★★ 本批**没有**任何一种"新能力"塞进处理器逻辑：形状是**一行 16 字节只读描述符**、
接收者是 `ResolveFieldReceipt` 里**多一个 `case`**。所以这里能验的是：
1. **接线对了**（目标地址 == 模块基址 + 那个偏移；这正是"调到哪个函数"的唯一判据）；
2. **省略的那一格落到 `x2` 时是 0**（= 形状声明"尾部 1 个可省、省略即保持 0"，
   与 PC 契约里那句"vanilla 带缺省值的形参缺省一律是 0"一致）；
3. **给值时原样透传**（证明不是"永远 0"）；
4. **`Seeds` 的接收者就是 `Game + kGameSeedsObjectOffset`**（内嵌子对象，不是指针）；
5. 参数个数闸门（1..2；0 个与 3 个都报错）；
6. 入口指纹对不上 / 拿不到 `Game` ⇒ **不调引擎、也不报错**（静默降级）。

## 没验到的（只能真机）

宿主把引擎调用桩掉、返回值一律清零 ⇒ 这里**证明不了**"引擎真的换了角色 / 真的把充能置 0 /
真的换了起始种子"。★ 尤其 `DischargeActiveItem` 那第 2 格 `bool`：它**确实参与引擎分支**
（`0x2B9C54` 的 `tbnz w27,#0x0`），本批按"契约只暴露 1 个形参 ⇒ 取 0"处理，
**是不是与 PC 一致只能真机核对**（作业单第九节）。`ChangePlayerType` 那条则可以断言"对语料惰性"
（分支要求 `PlayerType ∈ {16,17}`，语料传 `PLAYER_EVE`(5)），但同样没验真值。
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
GAME_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "game_api.cpp"
SHAPES = ROOT / "runtime" / "src" / "interfaces" / "lua" / "engine_method_api.hpp"

PLAYER_TYPE_EVE = 5
ACTIVE_SLOT_PRIMARY = 0
SEED_VALUE = 1234567890

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

// 伪造的引擎内存（形状抄批次 326/333 的同一条"全局 owner 槽"链）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里放的是**变量地址**）
//   g_OwnerSlotBytes                          = Game*
//   Game + kGamePlayerArrayBegin/End          = 玩家指针数组（Isaac.GetPlayer(0) 走它）
//   Game + kGameSeedsObjectOffset             = Seeds（**内嵌**子对象，不是指针）
// 三个引擎入口的**入口首 4 字节**分别种在模块块的对应偏移上（`noentry` 场景不种）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::uintptr_t g_EngineBase = 0;

//: ★★ 模块块要**盖住 `g_Game` 那个全局槽**（这是最容易写错的一格：入口偏移都在 `0x00xx'xxxx`
//: 量级，而全局槽在 `0xAAC698` —— 只按入口偏移开块就会越界写）。
inline constexpr std::size_t kModuleBytesSize =
    kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t);
static_assert(kEntityPlayerChangePlayerTypeOffset < kGameOwnerGlobalSlotOffset,
              "入口偏移必须落在全局槽之前，否则假模块块盖不住它");
static_assert(kEntityPlayerDischargeActiveItemOffset < kGameOwnerGlobalSlotOffset,
              "入口偏移必须落在全局槽之前");
static_assert(kSeedsSetStartSeedOffset < kGameOwnerGlobalSlotOffset,
              "入口偏移必须落在全局槽之前");

//: `Game` 块要盖住"玩家数组"与 `Seeds` 子对象的起始（本机制不读 `Seeds` 内部，
//: 但接收者指针会算到那里 ⇒ 开够以免读者误判）。
inline constexpr std::size_t kGameBytesSize = kGameSeedsObjectOffset + sizeof(std::uint64_t);

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

void PlantEntryWord(std::size_t offset, std::uint32_t word) {
    for (std::size_t index = 0; index < 4; ++index) {
        g_ModuleBytes[offset + index] =
            static_cast<unsigned char>((word >> (8 * index)) & 0xFFU);
    }
}

void PublishFakeWorld(bool plantEntryWords, bool publishGame) {
    g_ModuleBytes.assign(kModuleBytesSize, 0);
    g_EngineBase = reinterpret_cast<std::uintptr_t>(g_ModuleBytes.data());
    if (plantEntryWords) {
        PlantEntryWord(kEntityPlayerChangePlayerTypeOffset, kEntityPlayerChangePlayerTypeEntryWord);
        PlantEntryWord(kEntityPlayerDischargeActiveItemOffset,
                       kEntityPlayerDischargeActiveItemEntryWord);
        PlantEntryWord(kSeedsSetStartSeedOffset, kSeedsSetStartSeedEntryWord);
    }

    g_GameBytes.assign(kGameBytesSize, 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uintptr_t>(g_PlayerBytes, 0,
                            g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);

    g_PlayerArrayBytes.assign(2 * sizeof(std::uint64_t), 0);
    WriteAt<std::uint64_t>(g_PlayerArrayBytes, 0,
                           reinterpret_cast<std::uintptr_t>(g_PlayerBytes.data()));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset,
                           reinterpret_cast<std::uintptr_t>(g_PlayerArrayBytes.data()));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           reinterpret_cast<std::uintptr_t>(g_PlayerArrayBytes.data()) +
                               sizeof(std::uint64_t));

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset,
                           reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()));
    if (publishGame) {
        WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0,
                               reinterpret_cast<std::uintptr_t>(g_GameBytes.data()));
    }
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
    const bool known =
        std::strcmp(scenario, "change_omitted") == 0 ||
        std::strcmp(scenario, "change_explicit") == 0 ||
        std::strcmp(scenario, "discharge_omitted") == 0 ||
        std::strcmp(scenario, "seed") == 0 ||
        std::strcmp(scenario, "seed_extra") == 0 ||
        std::strcmp(scenario, "noentry") == 0 ||
        std::strcmp(scenario, "argzero") == 0 ||
        std::strcmp(scenario, "argextra") == 0 ||
        std::strcmp(scenario, "nogame") == 0;
    if (!known) return 91;
    const bool plantEntry = std::strcmp(scenario, "noentry") != 0;
    const bool publishGame = std::strcmp(scenario, "nogame") != 0;
    PublishFakeWorld(plantEntry, publishGame);

    std::string script =
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local p = Isaac.GetPlayer(0)\n"
        "local seeds = Game():GetSeeds()\n"
        "print('B335 p=' .. type(p))\n"
        "print('B335 seeds=' .. type(seeds))\n"
        "print('B335 fn=' .. type(p and p.ChangePlayerType))\n";
    if (std::strcmp(scenario, "change_omitted") == 0 ||
        std::strcmp(scenario, "noentry") == 0) {
        // ★ 语料写法（`RepentancePlus/RepentancePlus/main.lua:1008`）：只传角色。
        script +=
            "local good = pcall(function() return p:ChangePlayerType(5) end)\n"
            "print('B335 ok=' .. tostring(good))\n";
    } else if (std::strcmp(scenario, "nogame") == 0) {
        // ★ 这一档**不能用 `Isaac.GetPlayer(0)`**：拿不到 `Game` 时它按 PC 语义交回 `nil`
        //   （`B335 p=nil`），于是 `p:ChangePlayerType(...)` 报的是 Lua 自己的
        //   "attempt to index a nil value" —— 那是 Lua 语义，**不是**我们的处理器降级，
        //   拿它当判据会把"没验到"当成"验到了"。改用 `seeds` 句柄：它在没有 `Game` 时
        //   照样是 userdata（`Game():GetSeeds()` 交回空壳），调用时才走接收者解析。
        script +=
            "local good = pcall(function() return seeds:SetStartSeed(1) end)\n"
            "print('B335 ok=' .. tostring(good))\n";
    } else if (std::strcmp(scenario, "change_explicit") == 0) {
        script +=
            "local good = pcall(function() return p:ChangePlayerType(5, true) end)\n"
            "print('B335 ok=' .. tostring(good))\n";
    } else if (std::strcmp(scenario, "discharge_omitted") == 0) {
        // ★ 语料写法（`RepentancePlus/RepentancePlus/main.lua:2249`）：只传槽位。
        script +=
            "local good = pcall(function() return p:DischargeActiveItem(0) end)\n"
            "print('B335 ok=' .. tostring(good))\n";
    } else if (std::strcmp(scenario, "seed") == 0) {
        // ★ 语料写法（`IsaacOnTwitchReloaded/scripts/events.lua:1433`）：传的是**数字**。
        script +=
            "local good = pcall(function() return seeds:SetStartSeed(1234567890) end)\n"
            "print('B335 ok=' .. tostring(good))\n";
    } else if (std::strcmp(scenario, "seed_extra") == 0) {
        script +=
            "print('B335 ok=' .. ok(function() return seeds:SetStartSeed(1, 2) end))\n"
            "print('B335 msg=' .. err(function() return seeds:SetStartSeed(1, 2) end))\n";
    } else if (std::strcmp(scenario, "argzero") == 0) {
        script +=
            "print('B335 ok=' .. ok(function() return p:ChangePlayerType() end))\n"
            "print('B335 msg=' .. err(function() return p:ChangePlayerType() end))\n";
    } else {
        script +=
            "print('B335 ok=' .. ok(function() return p:ChangePlayerType(5, true, 1) end))\n"
            "print('B335 msg=' .. err(function() return p:ChangePlayerType(5, true, 1) end))\n";
    }

    const char* text = script.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(text, std::strlen(text), "@b335.lua");
    static_cast<void>(result);
    std::printf("B335 base=0x%llX\n", static_cast<unsigned long long>(g_EngineBase));
    std::printf("B335 calls=%u\n", g_HostEngineCallTrampolineCalls);
    std::printf("B335 target=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastTarget));
    std::printf("B335 x0=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[0]));
    std::printf("B335 x1=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[1]));
    std::printf("B335 x2=0x%llX\n",
                static_cast<unsigned long long>(g_HostEngineCallTrampolineLastIntegers[2]));
    //: ★ `Seeds` 的接收者**没法从 `base` 推**（Game 块是另一块堆内存）⇒ 直接把期望值打出来。
    std::printf("B335 seedreceiver=0x%llX\n",
                static_cast<unsigned long long>(
                    reinterpret_cast<std::uintptr_t>(g_GameBytes.data()) +
                    kGameSeedsObjectOffset));
    return 0;
}
'''


class Batch335PlayerApiRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b335-")
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
        # ★ 批次 285 的教训：`stderr` 也要一起回 —— 只回 stdout 时，
        #   "Lua 脚本中途报错"和"什么都没做"长得一模一样。
        return result.stdout + result.stderr

    @staticmethod
    def value(out, label):
        match = re.search(rf"^{re.escape(label)}=(\S+)$", out, re.M)
        if match is None:
            raise AssertionError(f"输出里没有 {label} 那一行：\n{out}")
        return match.group(1)

    # ---------------------------------------------------------------- 行为（宿主）

    def test_change_player_type_targets_the_engine_entry_and_zero_fills_the_tail(self):
        """语料那种 1 参写法：目标 = 基址 + `0x2AACCC`；`x1` = 角色、**`x2` = 0（省略的那一格）**。"""
        out = self.run_scenario("change_omitted")
        self.assertIn("B335 p=userdata", out)
        self.assertIn("B335 fn=function", out)
        base = int(self.value(out, "B335 base"), 16)
        self.assertEqual(self.value(out, "B335 calls"), "1", out)
        self.assertEqual(int(self.value(out, "B335 target"), 16), base + 0x2AACCC, out)
        self.assertEqual(int(self.value(out, "B335 x1"), 16), PLAYER_TYPE_EVE, out)
        self.assertEqual(int(self.value(out, "B335 x2"), 16), 0, out)

    def test_change_player_type_passes_an_explicit_tail_through(self):
        """给全 2 个实参时原样透传（证明第 2 格不是"永远 0"）。"""
        out = self.run_scenario("change_explicit")
        self.assertEqual(self.value(out, "B335 calls"), "1", out)
        self.assertEqual(int(self.value(out, "B335 x1"), 16), PLAYER_TYPE_EVE, out)
        self.assertEqual(int(self.value(out, "B335 x2"), 16), 1, out)

    def test_discharge_active_item_targets_the_engine_entry(self):
        """`DischargeActiveItem(slot)`：目标 = 基址 + `0x2B9540`；`x1` = 槽位、`x2` = 0。"""
        out = self.run_scenario("discharge_omitted")
        base = int(self.value(out, "B335 base"), 16)
        self.assertEqual(self.value(out, "B335 calls"), "1", out)
        self.assertEqual(int(self.value(out, "B335 target"), 16), base + 0x2B9540, out)
        self.assertEqual(int(self.value(out, "B335 x1"), 16), ACTIVE_SLOT_PRIMARY, out)
        self.assertEqual(int(self.value(out, "B335 x2"), 16), 0, out)

    def test_set_start_seed_uses_the_inlined_seeds_object_as_receiver(self):
        """★★ `Seeds` 的接收者 = `Game + kGameSeedsObjectOffset`（**内嵌**子对象，不是指针）。"""
        out = self.run_scenario("seed")
        base = int(self.value(out, "B335 base"), 16)
        self.assertIn("B335 seeds=userdata", out)
        self.assertEqual(self.value(out, "B335 calls"), "1", out)
        self.assertEqual(int(self.value(out, "B335 target"), 16), base + 0x4A1114, out)
        #: `x1` = 传进去的那个数字（语料给的就是 `GetNextSeed()` 的返回值）。
        self.assertEqual(int(self.value(out, "B335 x1"), 16), SEED_VALUE, out)
        #: `x0` 是接收者：必须**正好**落在 `Game + kGameSeedsObjectOffset` 上
        #: （`SetStartSeed` 只收 1 格 ⇒ 实参进 `x1`、接收者留在 `x0`）。
        #: ★ 期望值由夹具自己算并打印 —— Game 块是一块独立的堆内存，**不能**用 `base` 推。
        self.assertEqual(int(self.value(out, "B335 x0"), 16),
                         int(self.value(out, "B335 seedreceiver"), 16), out)

    def test_missing_entry_word_never_calls_the_engine(self):
        """入口首 4 字节对不上 ⇒ 不调引擎、也不报错（静默降级）。"""
        out = self.run_scenario("noentry")
        self.assertEqual(self.value(out, "B335 calls"), "0", out)
        self.assertIn("B335 ok=true", out)

    def test_missing_game_never_calls_the_engine(self):
        """拿不到 `Game`（全局槽为空）⇒ 接收者解析失败 ⇒ 不调引擎、不报错。"""
        out = self.run_scenario("nogame")
        self.assertEqual(self.value(out, "B335 calls"), "0", out)
        self.assertIn("B335 ok=true", out)

    def test_argument_count_gates(self):
        """`VoidIntBoolOpt1` 收 **1..2** 个：0 个与 3 个都报错；`Void1` 恰好收 1 个。"""
        zero = self.run_scenario("argzero")
        self.assertIn("B335 ok=false", zero)
        self.assertIn("EntityPlayer:ChangePlayerType expects at most 2 argument(s)", zero)
        self.assertEqual(self.value(zero, "B335 calls"), "0", zero)

        extra = self.run_scenario("argextra")
        self.assertIn("B335 ok=false", extra)
        self.assertIn("EntityPlayer:ChangePlayerType expects at most 2 argument(s)", extra)
        self.assertEqual(self.value(extra, "B335 calls"), "0", extra)

        seed_extra = self.run_scenario("seed_extra")
        self.assertIn("B335 ok=false", seed_extra)
        self.assertIn("Seeds:SetStartSeed expects 1 argument(s)", seed_extra)
        self.assertEqual(self.value(seed_extra, "B335 calls"), "0", seed_extra)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """形状 33 + 三条常量 + 三行数据 + 目录 id + 新接收者。"""
        shapes = SHAPES.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        rows = ISAAC_API.read_text(encoding="utf-8")
        game_rows = GAME_API.read_text(encoding="utf-8")

        self.assertRegex(shapes, r"VoidIntBoolOpt1\s*=\s*33,")
        self.assertRegex(
            rows,
            r"\{2, \{EngineArgKind::Int, EngineArgKind::Bool,[^}]*\},\s*\n"
            r"\s*EngineReturnKind::Void, FieldReceipt::EntityPlayer, IntArgumentGuard::None, 1, "
            r"\{0, 0, 0\}\}")
        self.assertIn("kEntityPlayerChangePlayerTypeOffset = 0x2AACCC", constants)
        #: ★ 后缀大小写照 **源码逐字**（本批这一段沿用邻居的 `u` 小写写法；
        #: 早期批次用的是 `U` —— 断言写成源码里的样子，别"顺手规范化"。
        self.assertIn("kEntityPlayerChangePlayerTypeEntryWord = 0xD10243FFu", constants)
        self.assertIn("kEntityPlayerDischargeActiveItemOffset = 0x2B9540", constants)
        self.assertIn("kEntityPlayerDischargeActiveItemEntryWord = 0xD103C3FFu", constants)
        self.assertIn("kSeedsSetStartSeedOffset = 0x4A1114", constants)
        self.assertIn("kSeedsSetStartSeedEntryWord = 0xA9BE7BFDu", constants)
        self.assertRegex(rows, r"\{0x0E0100E7, kEntityPlayerChangePlayerTypeOffset,")
        self.assertRegex(rows, r"\{0x0E0100E8, kEntityPlayerDischargeActiveItemOffset,")
        self.assertRegex(game_rows, r"\{0x0F01000A, kSeedsSetStartSeedOffset,")
        #: ★ 新接收者 `FieldReceipt::Seeds`：多一个 `case`，并且 `Seeds` 那条行用它。
        self.assertIn("FieldReceipt::Seeds", rows)
        self.assertRegex(rows, r"case FieldReceipt::Seeds:")
        self.assertRegex(game_rows, r"FieldReceipt::Seeds,\s*\n\s*EngineCallShape::VoidSeed1,")
        #: ★ 反回归：新形状只该被这两条 API 用（`Seeds:SetStartSeed` 用的是既有 `Void1`）
        #: —— 数"数据行里引用它"的处数（形状描述符那段注释里也会出现这个名字，所以
        #: 必须带上 `FieldReceipt::…, ` 前缀，否则会把注释也数进去）。
        self.assertEqual(
            len(re.findall(r"FieldReceipt::EntityPlayer, EngineCallShape::VoidIntBoolOpt1", rows)),
            1)


if __name__ == "__main__":
    unittest.main()
