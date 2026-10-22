"""门禁：`Level` 头部两个布尔标志字节（批次 313，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧依据 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Level:HasBossChallenge()` | `Level.md:271` | 没有同名函数 ⇒ 直读 `Level + 0x08` 那**一个字节** | `Bool` / `False` | 3（BOIStageAPI15） |
| `Level:GetCanSeeEverything()` | `Level.md:104` | 同族 ⇒ 直读 `Level + 0x11` 那**一个字节** | `Bool` / `False` | 1（MusicModCallback） |

走**字段读取型数据行**（`remaining_api.cpp` 的 `kLevelFieldApis`，**0 字节代码**），
接收者是既有的 `FieldReceipt::Level`（`Game`/`Level` 同一地址）。

## 偏移凭什么（这一批的判据是"头部逐格一致 + 具名存读者"）

* PC 侧两条绑定各自只有两条指令（`pc_exe_binding.py` 拿到 VA、按地址区间取）：
  `HasBossChallenge @ 0x7FA860: movb 0x8(%ecx), %al; ret`、
  `GetCanSeeEverything @ 0x7FA870: movb 0x11(%ecx), %al; ret`
  —— 它们在同一张 **Level 布尔名字表簇**里（同簇还有 `SetCanSeeEverything` /
  `IsDevilRoomDisabled` / `IsPillIdentified` / `IsCustomRun` / `DungeonReturnPosition`）。
* ★★★ **Switch 的 `Level` 头部与 PC 逐格一致**（三条独立锚点，Switch 侧各自有具名函数）：
  `+0x00` / `+0x04`（`Level::SetStage` 用 `stp w21, w20, [x19]` 把两个枚举**连着**写）、
  `+0x0C`（`Level::IsNextStageAvailable @ 0x3DBF14` 读 `[x20, #0xc]`，与 PC 的
  `Level::GetCurses` 的 `orl 0xc(%ecx), %esi` 同格）⇒ 夹在 `+0x04` 与 `+0x0C` 之间的
  `+0x08` **同格**。
* ★★ 这两格都是 `Level::StoreGameState`（`0x3E5898` 读 `[x0,#0x8]`、`0x3E5A54` 读 `[x0,#0x11]`）
  与 `Level::RestoreGameState`（`0x3E4E80` 写 `[x19,#0x8]`、`0x3E4E78` 写 `[x19,#0x11]`）
  存读的**四个字节标志**之二（同一个存档区块 `+0x1B8~+0x1BB`，四格各自独立）。
* ★★★ `+0x11` 的语义有**具名消费者**：`Level::try_display_room`（`0x3D90C4` 起）先问
  `PlayerManager::FirstCollectibleOwner(0x4C = COLLECTIBLE_XRAY_VISION /*透视*/)`，
  没有透视才去读 `[x20,#0x11]`、为 0 就不显示 ⇒「有透视 **或** 这一格非 0 ⇒ 地图全开」
  正是 `GetCanSeeEverything` 的语义。

逐条证据写在 `runtime_constants.hpp` 的**批次 313 段**。

## 宿主验到了什么、没验到什么

* **验到**（字段行**没有入口指纹** ⇒ 伪造内存里的字节真会被读出来）：
  - 两条各读**自己那一格**（两场把两格摆成相反值 ⇒ 读串/写反立刻红）；
  - **"非 0 即真"**（那两格写 `0x7F` 也答 true，不是 "== 1"）；
  - ★ **读的是"字节"而不是 `u32`**（写 `u32 = 0x100` ⇒ 低字节 0 ⇒ 必须答 `false`；
    按 `u32` 读会答 `true` —— 判别组）；
  - ★ **不读相邻那一格**（`+0x09` / `+0x10` 摆 1、目标格摆 0 ⇒ 必须答 `false`）；
  - 返回**布尔**（不是数字）、参数闸门（多给一个参数报错）、
    拿不到 `Game`/`Level` ⇒ 答 `false` 且**不抛 Lua 错误**。
* **没验**：**真机上的偏移归属**（宿主里"偏移对不对"是同一张表的两处引用同一个常量，
  自己证不了自己）。⇒ 真机项 = 作业单 **V63**。
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
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: `(名字, 域内序号, 偏移常量)` —— 两条都是 `Bool` + `FieldMissing::False` + `FieldReceipt::Level`。
LEVEL_APIS = (
    ("HasBossChallenge", 0x001D, "kLevelBossChallengeOffset"),
    ("GetCanSeeEverything", 0x001E, "kLevelCanSeeEverythingOffset"),
)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（`Game`/`Level` 同一地址 —— `Level` 内嵌在 `Game` 起始处，与批次 294 同源）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                         = Game*（= Level*）
//   g_GameBytes[0x08] / [0x09] / [0x10] / [0x11] = 四个**字节标志**（后两个是"邻格"，用来验
//                                                  "读的是不是自己那一格"）
// ★ 本批是字段行 ⇒ **没有入口指纹** ⇒ 宿主里能真的读到伪造块里的字节（不是降级值）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::uintptr_t g_EngineBase = 0;
bool g_GameAvailable = true;

static_assert(kLevelBossChallengeOffset + sizeof(std::uint8_t) <= 0x80,
              "fake Game block must hold the boss challenge flag");
static_assert(kLevelCanSeeEverythingOffset + sizeof(std::uint8_t) <= 0x80,
              "fake Game block must hold the can-see-everything flag");
//: ★ 两格**不许重合**（重合会让"读串"这一类错在宿主里看不出来）。
static_assert(kLevelBossChallengeOffset != kLevelCanSeeEverythingOffset,
              "the two flags must be different bytes");
//: ★ 也不许跟头部已定案的另外三格（`+0x00`/`+0x04`/`+0x0C`）撞。
static_assert(kLevelBossChallengeOffset != kLevelStageOffset &&
              kLevelBossChallengeOffset != kLevelStageTypeOffset &&
              kLevelBossChallengeOffset != kLevelCursesOffset,
              "boss challenge flag must not alias the level header scalars");
static_assert(kLevelCanSeeEverythingOffset != kLevelStageOffset &&
              kLevelCanSeeEverythingOffset != kLevelStageTypeOffset &&
              kLevelCanSeeEverythingOffset != kLevelCursesOffset,
              "can-see-everything flag must not alias the level header scalars");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeGame() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_GameBytes.assign(0x80, 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    if (g_GameAvailable) {
        WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
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
    if (argc != 2) return 90;
    const char* scenario = argv[1];

    // 七个场景：
    //   boss     —— 0x08=1、0x09=0、0x10=0、0x11=0 ⇒ boss=true / cansee=false
    //   cansee   —— 反过来摆（0x11=1，其余 0）⇒ boss=false / cansee=true
    //               ★ 这两场合起来专抓"两条读同一格""两个偏移写反""结果写死"
    //   nonzero  —— 两格都写 0x7F（**非 0 但不是 1**）⇒ 两条都必须 true（"非 0 即真"）
    //   highbyte —— 两格各写 **`u32 = 0x100`**（低字节 0、第二字节 1）⇒ 必须 false（判别组）
    //   neighbors—— 目标两格 =0，**邻格** 0x09 / 0x10 =1 ⇒ 必须 false（"读的不是邻格"）
    //   nogame   —— 拿不到 Game ⇒ 两条都该答 false 且不抛错
    //   args     —— 参数闸门
    std::uint8_t b08 = 1, b09 = 0, b10 = 0, b11 = 0;
    bool highByteProbe = false;
    if (std::strcmp(scenario, "boss") == 0) {
        // 默认值。
    } else if (std::strcmp(scenario, "cansee") == 0) {
        b08 = 0;
        b11 = 1;
    } else if (std::strcmp(scenario, "nonzero") == 0) {
        b08 = 0x7F;
        b11 = 0x7F;
    } else if (std::strcmp(scenario, "highbyte") == 0) {
        b08 = 0;
        b11 = 0;
        highByteProbe = true;
    } else if (std::strcmp(scenario, "neighbors") == 0) {
        b08 = 0;
        b09 = 1;
        b10 = 1;
        b11 = 0;
    } else if (std::strcmp(scenario, "nogame") == 0) {
        g_GameAvailable = false;
    } else if (std::strcmp(scenario, "args") == 0) {
        // 默认值。
    } else {
        return 91;
    }

    PublishFakeGame();
    WriteAt<std::uint8_t>(g_GameBytes, kLevelBossChallengeOffset, b08);
    WriteAt<std::uint8_t>(g_GameBytes, kLevelBossChallengeOffset + 1, b09);
    WriteAt<std::uint8_t>(g_GameBytes, kLevelCanSeeEverythingOffset - 1, b10);
    WriteAt<std::uint8_t>(g_GameBytes, kLevelCanSeeEverythingOffset, b11);
    if (highByteProbe) {
        // 覆盖成 `u32`：`0x00000100` ⇒ 低字节 0、第二字节 1。
        WriteAt<std::uint32_t>(g_GameBytes, kLevelBossChallengeOffset, 0x00000100u);
        WriteAt<std::uint32_t>(g_GameBytes, kLevelCanSeeEverythingOffset, 0x00000100u);
    }
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local level = Game():GetLevel()"
        " print('B313 lvkind=' .. type(level))"
        " print('B313 fn=' .. type(level.HasBossChallenge) .. ','"
        "   .. type(level.GetCanSeeEverything))"
        " local boss = level:HasBossChallenge()"
        " local see = level:GetCanSeeEverything()"
        " print('B313 kinds=' .. type(boss) .. ',' .. type(see))"
        " print('B313 boss=' .. tostring(boss))"
        " print('B313 see=' .. tostring(see))"
        // 参数闸门：字段行**恰好收一个**（只有接收者），多给一个就报错。
        " print('B313 argboss=' .. ok(function() return level:HasBossChallenge(1) end))"
        " print('B313 argerr=' .. tostring(select(2, pcall(function()"
        "   return level:HasBossChallenge(1) end))))"
        " print('B313 argsee=' .. ok(function() return level:GetCanSeeEverything(1) end))"
        // 点号显式 self（`level.HasBossChallenge(level)`）也是 1 个参数 ⇒ 放行。
        " print('B313 dot=' .. ok(function() return level.HasBossChallenge(level) end))"
        // ★ 这一族的接收者是**引擎给**的（`FieldReceipt::Level` 走 `g_Game` 那条链，不取栈上的
        //   self）⇒ 传一个假表当 self 也**不会被拒**（与 `EntityPlayer` 那一族不同，
        //   那族的接收者是实体句柄、必须从栈上认）。这里断言它**只按参数个数**把关。
        " local f = level.GetCanSeeEverything"
        " print('B313 fakeself=' .. ok(function() return f({}) end))"
        " print('B313 fakeselftwo=' .. ok(function() return f({}, 1) end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b313.lua");
    static_cast<void>(result);
    return 0;
}
'''


class LevelFlagBytesBatch313Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b313-")
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

    def test_boss_challenge_is_read_from_its_own_byte(self):
        """第一场：`+0x08 = 1`、`+0x11 = 0` ⇒ `boss=true` / `see=false`，且返回**布尔**。"""
        out = self.run_scenario("boss")
        self.assertIn("B313 lvkind=userdata", out)
        self.assertIn("B313 fn=function,function", out)
        self.assertIn("B313 kinds=boolean,boolean", out)
        self.assertIn("B313 boss=true", out)
        self.assertIn("B313 see=false", out)

    def test_can_see_everything_is_read_from_its_own_byte(self):
        """第二场：把两格**反过来**摆 ⇒ 两条断言同时对调。

        ★ 两场合起来是本批最强的宿主判据：专抓三类错法 —— ① 两条读**同一格**、
        ② 两个偏移**写反**、③ 结果**写死**成 `true`/`false`（两场不可能同时对上）。
        """
        out = self.run_scenario("cansee")
        self.assertIn("B313 boss=false", out)
        self.assertIn("B313 see=true", out)

    def test_non_zero_means_true(self):
        """`0x7F`（非 0 但**不是 1**）⇒ 两条都必须答 `true`。

        PC 的绑定本体是 `movb 0x8(%ecx), %al` / `movb 0x11(%ecx), %al` 加胶水层的布尔转换
        ⇒ **非 0 即真**。写成"等于 1 才真"会在这一格被当成位标志用时静默答错。
        """
        out = self.run_scenario("nonzero")
        self.assertIn("B313 boss=true", out)
        self.assertIn("B313 see=true", out)

    def test_reads_a_byte_not_a_u32(self):
        """★ 判别组：两格各写 `u32 = 0x100`（低字节 0、第二字节 1）⇒ 按**字节**读必须答 `false`。

        按 `u32` 读（`BoolNonZero`）会读到 `256` ⇒ 答 `true`。这是
        `FieldKind::Bool`（`ReadField<uint8_t>`）与 `FieldKind::BoolNonZero`
        （`ReadField<uint32_t>`）**唯一能被分开**的输入。
        """
        out = self.run_scenario("highbyte")
        self.assertIn("B313 boss=false", out)
        self.assertIn("B313 see=false", out)
        self.assertNotIn("B313 boss=true", out)
        self.assertNotIn("B313 see=true", out)

    def test_does_not_read_the_neighbouring_byte(self):
        """★ 目标两格 `=0`、**邻格**（`+0x09` / `+0x10`）`=1` ⇒ 两条都必须答 `false`。

        这两格与邻格同属"四个存档字节标志"，写错一格（把 `+0x08` 写成 `+0x09`、
        或把 `+0x11` 写成 `+0x10`）在真机上完全看不出来（都是同一批标志），
        只有宿主能把它们分开 —— 所以这一场必须存在。
        """
        out = self.run_scenario("neighbors")
        self.assertIn("B313 boss=false", out)
        self.assertIn("B313 see=false", out)

    def test_gates_and_degrades_without_game(self):
        """参数闸门（**只按个数**）+ 拿不到 `Game` ⇒ 答 `false` 且**不抛 Lua 错误**。

        ★ 与 `EntityPlayer` 那一族不同：这一族的接收者是**引擎给**的
        （`FieldReceipt::Level` 走 `g_Game` 那条解析链，不取栈上的 `self`）⇒ 传假表当 self
        不会被拒。所以这里断言的是"只按参数个数把关"，而不是"接收者闸门"。
        """
        out = self.run_scenario("args")
        #: 多给一个参数 ⇒ 报错（消息按 catalog 里的 owner:name 现拼）。
        self.assertIn("B313 argboss=false", out)
        self.assertIn("Level:HasBossChallenge accepts no arguments", out)
        self.assertIn("B313 argsee=false", out)
        #: 点号显式 self（1 个参数）⇒ 放行（字段行的既有口径）。
        self.assertIn("B313 dot=true", out)
        #: 接收者不由栈决定 ⇒ 假 self 也放行（只数参数个数）。
        self.assertIn("B313 fakeself=true", out)
        #: 但**多一个实参**就被个数闸拦下（说明闸门盯的确实是个数）。
        self.assertIn("B313 fakeselftwo=false", out)

        #: 拿不到 Game ⇒ 两条都答 `false`（PC 上"读到 0"同值），**不抛错**。
        no_game = self.run_scenario("nogame")
        self.assertIn("B313 boss=false", no_game)
        self.assertIn("B313 see=false", no_game)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与降级档 / 偏移常量 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for name, index, prefix in LEVEL_APIS:
            with self.subTest(api=f"Level:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Level, 1, 0x{index:04X}), ApiDomain::Level, "Level", '
                    f'"{name}"',
                    catalog, f"目录里没有 Level:{name}")
                self.assertRegex(
                    remaining,
                    rf"\{{\s*(?i:0x0301{index:04x}),\s*{prefix},\s*0,\s*"
                    rf"FieldKind::Bool,\s*FieldMissing::False,\s*"
                    rf"FieldReceipt::Level,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档不对：Level:{name}")
                self.assertRegex(constants, rf"inline constexpr uintptr_t {prefix}\s*=\s*0x[0-9A-Fa-f]+;")

        #: ★ 反回归：这两条**不许**被塞进引擎方法行表（引擎里没有同名函数，
        #:   `tools/mangled_impl_count.py HasBossChallenge` = 0 个实现）。
        self.assertNotRegex(remaining, r"0x0301001D[^\n]*EngineCallShape")
        self.assertNotRegex(remaining, r"0x0301001E[^\n]*EngineCallShape")

    def test_the_evidence_is_recorded(self):
        """★ 常量段必须写明 PC 绑定 VA、Switch 三条锚点与两个具名存读者、以及那个透视消费者。

        这条不是形式主义：本批的偏移**不是**靠"函数体里读写同一格"定的，而是靠
        「Switch 的 `Level` 头部与 PC 逐格一致」（`+0x00`/`+0x04`/`+0x0C` 三条锚点）+
        `StoreGameState`/`RestoreGameState` 存读这四格 + `try_display_room` 的透视分支。
        丢掉任何一条，后人只会看到"某两个字节看起来像标志"。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("inline constexpr uintptr_t kLevelBossChallengeOffset = 0x08;", constants)
        self.assertIn("inline constexpr uintptr_t kLevelCanSeeEverythingOffset = 0x11;", constants)
        for token in ("0x7FA860", "0x7FA870", "0x3E5898", "0x3E4E78", "0x3E4E80", "0x3D90C4",
                      "0x3DBF14", "FirstCollectibleOwner", "XRAY_VISION", "COLLECTIBLE_XRAY_VISION",
                      "try_display_room", "StoreGameState", "RestoreGameState", "0x1B8"):
            self.assertIn(token, constants, f"证据 {token} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()
