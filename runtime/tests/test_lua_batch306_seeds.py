"""门禁：`Seeds:GetStageSeed(LevelStage)` / `Seeds:GetNextSeed()`（批次 306，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧 | 语料调用点 |
| --- | --- | --- | --- |
| `Seeds:GetStageSeed(stage)` | `Seeds.md:71/73` `int GetStageSeed ( LevelStage Stage )` | 读 `Seeds + 0x18 + 4*stage` 的 u32 | 3 |
| `Seeds:GetNextSeed()` | `Seeds.md:56/58` `int GetNextSeed ( )` | **调引擎 `RNG::Next()`**（`this` = `Seeds + 0x8` 的内嵌 RNG） | 3 |

★ 谁在调：`BOIStageAPI15` 拿 `GetStageSeed` 当 `StageRNG:SetSeed(...)` 的参数、
`MusicModCallback` 拿它挑曲目；`TBOI_Better-Voiding` 把 `GetNextSeed()` 当 `Game:Spawn` 的种子、
`IsaacOnTwitchReloaded` 把它喂给 `MakeChampion(seed)`。**都是直接把返回值当参数用** ⇒
返回 `nil` 会让那一行整块抛错。

## 为什么这两条是手写、而不是数据行

* `Seeds` 句柄**不持引擎指针**（`SeedHandle` 只有一个保留字节）⇒ 接收者必须
  `Game + kGameSeedsObjectOffset` 现算 ⇒ 想走数据行**先得新开一档 `FieldReceipt::Seeds`**；
* `GetNextSeed` 还要**调引擎函数**（`RNG::Next`）⇒ 数据行机制本来就表达不了；
* 这个家族已有的 5 条（`IsCustomRun`/`GetStartSeed`/`Has|Add|RemoveSeedEffect`/`ForgetStageSeed`）
  **全是手写**。为一个 3 处的调用点新开 receipt + 新 kind，比写两条处理器更贵。

## 偏移凭什么（两条独立证据 + PC 交叉印证）

见 `runtime_constants.hpp` 的批次 306 段（逐条指令都写在那里）：

* `Seeds::Seeds()`（构造函数）@ `0x49CBD4`：`add x0, x0, #0x8` + `bl RNG::RNG()`
  ⇒ `Seeds + 0x8` 是**内嵌 RNG**（16 字节）⇒ stage 种子数组被推进到 `+0x18`；
* `Seeds::ForgetStageLevel(eLevelStage)` @ `0x4A1228`：`add x19, x0, w1, uxtw #2` →
  `ldr w1, [x19, #0x18]` → … → `str w0, [x19, #0x18]` ⇒ **基址 `+0x18`、步长 4 直接读出来**；
* PC 对照（数值不许平移，只印证基址/步长）：`GetStageSeed @ 0x705F30` = `mov eax, [esi+4*eax+0x18]`；
  `GetNextSeed @ 0x6C4560` = 内联的同一个 xorshift（读 `[esi+8/+0xc/+0x10/+0x14]`、写回 `[esi+8]`）。

## 宿主验到了什么、没验到什么

* **验到**：
  - ★★ **`GetStageSeed(i)` 读的确实是第 `i` 格**：夹具在 16 个槽里摆**互不相同**的值，
    逐个读回来必须逐个相等（读错基址 / 步长 / 下标都会红）；
  - ★ **越界（16 / 100 / -1）返回 0 且不报错**（PC 无边界检查 ⇒ 这是**刻意偏离**）；
  - **参数闸门**：少给 / 多给 / 非整数都报错；
  - ★★ **`GetNextSeed()` 真的推进了那颗 RNG**：宿主注入一个**真函数**当 `RNG::Next`，
    连调两次的值**必须不同**，且第二次 == 用第一次的值当状态再摇一次；
  - ★ **`this` 就是 `Seeds + 0x8`**（宿主把收到的指针记下来，与
    `Game + kGameSeedsObjectOffset + kSeedsRngOffset` 比较）；
  - **拿不到 `Game`** 时两条都答 0、不报错、**不调引擎**。
* **没验**：真机上这一格就是那个 stage 的种子（宿主里夹具与实现引用同一个常量，自己证不了自己）、
  以及 `GetNextSeed` 读到的确实推进了**引擎真值**（只能用真机的种子显示来核）⇒ 真机项 = 作业单 **V56**。
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
GAME_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "game_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: 本批两条 API 的域内序号 / owner / 名字 / 契约页:行。
APIS = (
    ("Seeds", "GetStageSeed", 0x0008, "Seeds.md:73"),
    ("Seeds", "GetNextSeed", 0x0009, "Seeds.md:58"),
)

#: 夹具里 16 个 stage 槽的值（**互不相同** ⇒ 读错下标/基址必红）。
STAGE_VALUES = tuple(0x10000001 + i * 0x00010101 for i in range(16))
#: 内嵌 RNG 的四个字（状态 + 三个移位量）。移位量取非 0，避免退化。
RNG_STATE = 0x12345678
RNG_SHIFTS = (2, 3, 5)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 301/305 的同一条"全局 owner 槽"链）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里放的是**变量地址**）
//   g_OwnerSlotBytes                          = Game*
//   Game + kGameSeedsObjectOffset             = Seeds（**内嵌**子对象，不是指针）
//   Seeds + kSeedsStageSeedArrayOffset        = 16 个 u32 的 stage 种子槽
//   Seeds + kSeedsRngOffset                   = 内嵌 RNG 的 4 个字
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::uintptr_t g_EngineBase = 0;

//: 模块块要盖住 `g_Game` 那个全局槽。
static_assert(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t) <= 0xB00000,
              "fake module block sizing assumption changed");
//: `Game` 块要盖住 stage 种子数组的最后一格（`0x25D40 + 0x18 + 16*4`）。
inline constexpr std::size_t kGameBytesSize =
    kGameSeedsObjectOffset + kSeedsStageSeedArrayOffset +
    kSeedsStageSeedStride * kSeedsStageSeedSlotCount + sizeof(std::uint64_t);

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uint32_t ReadU32(std::size_t offset) {
    std::uint32_t value = 0;
    std::memcpy(&value, g_GameBytes.data() + offset, sizeof(value));
    return value;
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

std::uintptr_t SeedsAddress() {
    return AddressOf(g_GameBytes) + kGameSeedsObjectOffset;
}

}  // namespace

// ---- 引擎 `RNG::Next` 的宿主替身 ----------------------------------------------------------
//
// ★ 只做**引擎那一件事**：按 `RNG` 的四个字做 xorshift、写回状态字、返回新值
//   （设备侧 `RNG::Next() @ 0x44E464` 的指令逐句写在 `runtime_constants.hpp` 的
//   `kSeedsRngOffset` 段；PC 的绑定本体是同一段逻辑的内联版）。
// ★ `this` 记下来 —— 用例要断言"传进去的就是 `Seeds + 0x8`"。
std::uintptr_t g_LastRngThis = 0;
unsigned g_RngNextCalls = 0;

extern "C" std::uint32_t HostRngNext(void* rng) {
    auto* words = static_cast<std::uint32_t*>(rng);
    g_LastRngThis = reinterpret_cast<std::uintptr_t>(rng);
    ++g_RngNextCalls;
    const std::uint32_t state = words[0];
    std::uint32_t x = (state >> (words[1] & 31U)) ^ state;
    x = (x << (words[2] & 31U)) ^ x;
    x = (x >> (words[3] & 31U)) ^ x;
    words[0] = x;
    return x;
}

extern "C" void HostRngSetSeed(void*, std::uint32_t, std::uint32_t) {}

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    const bool noGame = std::strcmp(scenario, "nogame") == 0;

    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGameBytesSize, 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    if (!noGame) {
        WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
        WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
    }
    //: 16 个 stage 槽各摆一个互不相同的值。
    for (std::size_t i = 0; i < kSeedsStageSeedSlotCount; ++i) {
        WriteAt<std::uint32_t>(g_GameBytes,
                               kGameSeedsObjectOffset + kSeedsStageSeedArrayOffset +
                                   kSeedsStageSeedStride * i,
                               static_cast<std::uint32_t>(STAGE_BASE_VALUE + i * STAGE_STEP_VALUE));
    }
    //: 内嵌 RNG 的四个字。
    WriteAt<std::uint32_t>(g_GameBytes, kGameSeedsObjectOffset + kSeedsRngOffset + 0x0,
                           static_cast<std::uint32_t>(RNG_STATE_VALUE));
    WriteAt<std::uint32_t>(g_GameBytes, kGameSeedsObjectOffset + kSeedsRngOffset + 0x4,
                           SHIFT0_VALUE);
    WriteAt<std::uint32_t>(g_GameBytes, kGameSeedsObjectOffset + kSeedsRngOffset + 0x8,
                           SHIFT1_VALUE);
    WriteAt<std::uint32_t>(g_GameBytes, kGameSeedsObjectOffset + kSeedsRngOffset + 0xc,
                           SHIFT2_VALUE);

    LuaRuntime::SetEngineModuleBase(g_EngineBase);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);
    LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&HostRngSetSeed),
                               reinterpret_cast<std::uintptr_t>(&HostRngNext));

    static const char* kStage =
        "local seeds = Game():GetSeeds()"
        " local parts = {}"
        " for i = 0, 15 do parts[#parts + 1] = tostring(seeds:GetStageSeed(i)) end"
        " print('B306 stage=' .. table.concat(parts, ','))"
        " print('B306 kind=' .. type(seeds) .. ',' .. type(seeds.GetStageSeed))";
    static const char* kStageOob =
        "local seeds = Game():GetSeeds()"
        " local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function msg(f) return tostring(select(2, pcall(f))) end"
        " print('B306 oob16=' .. tostring(seeds:GetStageSeed(16)))"
        " print('B306 oob100=' .. tostring(seeds:GetStageSeed(100)))"
        " print('B306 neg=' .. tostring(seeds:GetStageSeed(-1)))"
        " print('B306 noargs=' .. ok(function() return seeds:GetStageSeed() end))"
        " print('B306 noargsmsg=' .. msg(function() return seeds:GetStageSeed() end))"
        " print('B306 twoargs=' .. ok(function() return seeds:GetStageSeed(1, 2) end))"
        " print('B306 float=' .. ok(function() return seeds:GetStageSeed(1.5) end))"
        " print('B306 str=' .. ok(function() return seeds:GetStageSeed('x') end))"
        " print('B306 ok0=' .. ok(function() return seeds:GetStageSeed(0) end))"
        " print('B306 slot0=' .. tostring(seeds:GetStageSeed(0)))";
    static const char* kNext =
        "local seeds = Game():GetSeeds()"
        " local a = seeds:GetNextSeed()"
        " local b = seeds:GetNextSeed()"
        " print('B306 next=' .. tostring(a) .. ',' .. tostring(b))"
        " print('B306 nexttype=' .. type(a))"
        " print('B306 nextargs=' .. tostring(select(1, pcall(function() return seeds:GetNextSeed(1) end))))";
    static const char* kNoGame =
        "local ok, seeds = pcall(function() return Game():GetSeeds() end)"
        " print('B306 nogame_get=' .. tostring(ok))"
        " local s = seeds"
        " print('B306 stage0=' .. tostring(s:GetStageSeed(0)))"
        " print('B306 next0=' .. tostring(s:GetNextSeed()))";

    const char* script = nullptr;
    if (std::strcmp(scenario, "stage") == 0) {
        script = kStage;
    } else if (std::strcmp(scenario, "oob") == 0) {
        script = kStageOob;
    } else if (std::strcmp(scenario, "next") == 0) {
        script = kNext;
    } else if (noGame) {
        script = kNoGame;
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b306.lua");
    static_cast<void>(result);
    //: ★ 结账：C++ 侧**独立读**内嵌 RNG 的状态字（不经过 Lua），
    //:   以及宿主替身收到的 `this` 与调用次数。
    std::printf("B306 rng_state=%u\n", ReadU32(kGameSeedsObjectOffset + kSeedsRngOffset));
    std::printf("B306 rng_this=0x%llX\n",
                static_cast<unsigned long long>(g_LastRngThis));
    std::printf("B306 rng_seed_addr=0x%llX\n",
                static_cast<unsigned long long>(SeedsAddress() + kSeedsRngOffset));
    std::printf("B306 rng_calls=%u\n", g_RngNextCalls);
    return 0;
}
'''
HARNESS = (HARNESS
           .replace("STAGE_BASE_VALUE", "0x10000001")
           .replace("STAGE_STEP_VALUE", "0x00010101")
           .replace("RNG_STATE_VALUE", hex(RNG_STATE))
           .replace("SHIFT0_VALUE", str(RNG_SHIFTS[0]))
           .replace("SHIFT1_VALUE", str(RNG_SHIFTS[1]))
           .replace("SHIFT2_VALUE", str(RNG_SHIFTS[2])))


def engine_next(state):
    """设备侧 `RNG::Next()` 的等价实现（用于独立算出"第二次应当等于什么"）。"""
    x = ((state >> (RNG_SHIFTS[0] & 31)) ^ state) & 0xFFFFFFFF
    x = ((x << (RNG_SHIFTS[1] & 31)) ^ x) & 0xFFFFFFFF
    x = ((x >> (RNG_SHIFTS[2] & 31)) ^ x) & 0xFFFFFFFF
    return x


class SeedsBatch306Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b306-")
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

    def test_get_stage_seed_reads_exactly_the_indexed_slot(self):
        """★★ 16 个槽各摆一个**互不相同**的值 ⇒ 逐个读回来必须逐个相等。

        读错基址（例如把数组当 `+0x8` 的 RNG）、读错步长（当 1 字节）、
        或把下标当成"数组前一段"都会让这条红。★ 顺带钉住返回类型是 `number`。
        """
        out = self.run_scenario("stage")
        self.assertIn("B306 kind=userdata,function", out)
        got = self.value(out, "B306 stage").split(",")
        self.assertEqual(len(got), 16, f"应当读回 16 个值：{got}")
        #: ★ 用**有符号**呈现（PC 的返回类型是 `int`）。
        expected = [str(v - (1 << 32) if v >= (1 << 31) else v) for v in STAGE_VALUES]
        self.assertEqual(got, expected)

    def test_out_of_range_degrades_to_zero_without_erroring(self):
        """★ 越界（16 / 100 / -1）⇒ **返回整数 0、不报错**（刻意偏离：PC 没有边界检查）。

        ★ 同时验"合法的 0 号槽真的能读"——否则上面那几条"返回 0"可能是"一律返回 0"的假绿。
        """
        out = self.run_scenario("oob")
        self.assertIn("B306 oob16=0", out)
        self.assertIn("B306 oob100=0", out)
        self.assertIn("B306 neg=0", out)
        #: ★ 合法的 0 号槽要**真的读得到值**（`ok0` 是"没报错"，`slot0` 才是值）——
        #:   否则上面三条"返回 0"可能是"一律返回 0"的假绿。
        self.assertIn("B306 ok0=true", out)
        self.assertEqual(self.value(out, "B306 slot0"),
                         str(STAGE_VALUES[0] - (1 << 32)
                             if STAGE_VALUES[0] >= (1 << 31) else STAGE_VALUES[0]))

    def test_argument_gate(self):
        """参数个数/类型闸门：恰好一个整数 stage，消息里现拼出 `Seeds:GetStageSeed`。"""
        out = self.run_scenario("oob")
        self.assertIn("B306 noargs=false", out)
        self.assertIn("Seeds:GetStageSeed expects a stage", out)
        self.assertIn("B306 twoargs=false", out)
        self.assertIn("B306 float=false", out)
        self.assertIn("B306 str=false", out)

    def test_get_next_seed_advances_the_embedded_rng(self):
        """★★ `GetNextSeed()` 走的是引擎自己的 `RNG::Next()`，而且**真的推进了**那颗 RNG。

        三条一起成立才算过：
          ① 连调两次的值**不同**（不推进就是同一个值）；
          ② 第二次的值 == **用第一次的值当状态再摇一次**（Python 侧独立算，不复用实现）；
          ③ ★ `this` 就是 `Seeds + kSeedsRngOffset`（宿主替身把收到的指针记下来，
             并与 `C++ 侧算出来的` 地址比较）—— 传错对象（例如传 `Seeds` 本身）会红。
        """
        out = self.run_scenario("next")
        first, second = self.value(out, "B306 next").split(",")
        first, second = int(first, 10), int(second, 10)
        self.assertNotEqual(first, second, "两次 GetNextSeed 不该相同（说明没推进 RNG）")
        #: ★ 独立算：C++ 替身按引擎语义算一遍，Python 这里按同一份规格**另算一遍**。
        raw_first = first & 0xFFFFFFFF
        self.assertEqual(second & 0xFFFFFFFF, engine_next(raw_first))
        #: 内嵌 RNG 的状态字最终应当等于第二次的值。
        self.assertEqual(int(self.value(out, "B306 rng_state")), second & 0xFFFFFFFF)
        self.assertEqual(self.value(out, "B306 rng_calls"), "2")
        self.assertEqual(int(self.value(out, "B306 rng_this"), 16),
                         int(self.value(out, "B306 rng_seed_addr"), 16),
                         "`this` 必须是 `Seeds + kSeedsRngOffset`")
        self.assertIn("B306 nexttype=number", out)
        self.assertIn("B306 nextargs=false", out)

    def test_missing_game_degrades_on_both_apis_without_calling_the_engine(self):
        """★ 拿不到 `Game` ⇒ 两条都答 **0**、不报错；`GetNextSeed` **不调引擎**（调用数 0）。"""
        out = self.run_scenario("nogame")
        self.assertIn("B306 stage0=0", out)
        self.assertIn("B306 next0=0", out)
        self.assertEqual(self.value(out, "B306 rng_calls"), "0",
                         "拿不到 Game 时不许调引擎")
        self.assertEqual(self.value(out, "B306 rng_this"), "0x0")

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 常量字面值与证据 / 复用 RNG 那一条链路。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        game = GAME_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for owner, name, index, _page in APIS:
            with self.subTest(api=f"{owner}:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Seed, 1, 0x{index:04X}), ApiDomain::Seed, "{owner}", '
                    f'"{name}"',
                    catalog, f"目录里没有 {owner}:{name}（域内序号 0x{index:04x}）")
                self.assertIn(f"{{0x0F01{index:04X}, &Seeds{name}}}", game,
                              f"绑定表里没有 0x0F01{index:04X} → Seeds{name}")

        #: ★ 偏移字面值（接线用例的职责就是钉字面值）。
        self.assertRegex(constants,
                         r"inline constexpr uintptr_t kSeedsStageSeedArrayOffset\s*=\s*0x18;")
        self.assertRegex(constants, r"inline constexpr std::size_t kSeedsStageSeedStride\s*=\s*4;")
        self.assertRegex(constants,
                         r"inline constexpr std::uint32_t kSeedsStageSeedSlotCount\s*=\s*16;")
        self.assertRegex(constants, r"inline constexpr uintptr_t kSeedsRngOffset\s*=\s*0x08;")

        #: 实现必须**复用** RNG:Next 那条链路（发布点 + 指纹），不许自己抄 xorshift。
        self.assertIn("RngNextThunk()", game)
        self.assertIn("ValidateRngNextBinding(method)", game)
        block = game[game.index("int SeedsGetNextSeed(lua_State* state) {"):]
        block = block[:block.index("\n}\n")]
        self.assertIn("kSeedsRngOffset", block, "`this` 必须是 Seeds + 0x8 那个内嵌 RNG")
        #: ★ 反回归：不许在这两条里出现"自己算 xorshift"的痕迹。
        self.assertNotIn(">> 31", block)
        self.assertNotIn("<< 31", block)

        #: `GetStageSeed` 必须过"越界降级"（返回 0）—— 与 `BoolBitArrayOfArg` 同一口径。
        stage = game[game.index("int SeedsGetStageSeed(lua_State* state) {"):]
        stage = stage[:stage.index("\n}\n")]
        self.assertIn("kSeedsStageSeedSlotCount", stage)
        self.assertIn("IsIntegerArgument(state, 2)", stage)


if __name__ == "__main__":
    unittest.main()
