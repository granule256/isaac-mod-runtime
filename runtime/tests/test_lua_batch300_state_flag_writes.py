"""门禁：`Game:SetStateFlag(int Flag, boolean Value)` / `Level:SetStateFlag(...)`（批次 300，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧 | 走法 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Game:SetStateFlag(int Flag, boolean Value)` | `Game.md:469` | `Game + 0x26FA50` 的位数组（每字节 8 位） | 字段行（**0 字节代码**） | 1 |
| `Level:SetStateFlag(int Flag, boolean Value)` | `Level.md:408` | `Level + 0x215F0` 的 `u64` | 同上（`offset2` = 8） | 1 |

这是批次 297 那两条**读**侧（`GetStateFlag`）的**写侧** —— 同一对数组、同一份取证；
PC 侧四条绑定也成对地落在同一对格上（`Game+0x1822C`：读 `0x4E61D0` / 写 `0x55DC20`；
`Level+0x1C3168`：读 `0x41C430` / 写 `0x4C0540`）⇒ 本批**只加写的那一半**，偏移不重取。
★ 语料里 `ChallengeAPI` 同时用了读与写（`SetStateFlag(STATE_BACKWARDS_PATH_INIT, true)`），
写侧缺了那条模组照样断。

新种类 `FieldKind::BoolBitArrayOfWriteArg`（第 13 种）：`offset` = 位数组基址、
**`offset2` = 元素宽度（字节）**、两个实参 = `(标志号 n, 位值)`、**返回 0 个值** ——
它与 297 的 `BoolBitArrayOfArg` 的关系，正如 `BoolBitWrite` 与 `BoolBit` 的关系。

## 宿主验到了什么、没验到什么

* **验到**：
  - ★ **写真的落到了那一格**：`SetStateFlag(48, true)` 之后**读侧** `GetStateFlag(48)` 立刻为 `true`
    （读的是同一块内存 ⇒ 这条断言同时穿过写分支与读分支）；`false` 亦然；
  - ★★ **只动那一位**：同一元素里**别的位**（同字节的 47/49、别的字节的 2/60）在写前后必须**原样不变**
    —— 专抓「整格覆盖写」这类错法；
  - `Level` 那格（`u64`）同样验一遍（位 2 与位 7 互相不影响）；
  - **越界标志号 ⇒ 什么都不写、不报错**（负号 / 十万级）；
  - **参数闸门**：少给、只给一个、标志号非整数、多给 —— 都报错；
  - **返回值个数 = 0**（PC 是 `void`）⇒ Lua 侧 `local r = ...; type(r)` 是 `nil`。
* **没验**：真机上这两格是不是就是那些标志位。⇒ 与 297 的 **V48** 合并在同一条真机项里验
  （先 `SetStateFlag(flag, true)` 再 `GetStateFlag(flag)` 必须读回 `true`）。
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
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: `(owner, 域, 序号, 偏移常量, offset2, 行所在文件)`。
ROWS = (
    ("Game", "Game", 0x0016, "kGameStateFlagsOffset", 1, GAME_API),
    ("Level", "Level", 0x001C, "kLevelStateFlagsOffset", 8, REMAINING_API),
)

#: `Game` 那格 8 个字节的初值：字节 0 = bit0|bit2、字节 5 = bit7、字节 6 = bit0、字节 7 = bit4。
GAME_BYTES = (0x05, 0x00, 0x00, 0x00, 0x00, 0x80, 0x01, 0x10)
#: `Level` 那格的 `u64`：bit2 + bit7。
LEVEL_FLAGS = (1 << 2) | (1 << 7)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 297 的用例）：只要 `g_Game`（`FieldReceipt::Level` 的解析链）。
//   Game + kGameStateFlagsOffset (0x26FA50) = 8 个标志字节
//   Game + kLevelStateFlagsOffset (0x215F0) = `u64`
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

constexpr std::size_t kGameBlockSize = kLevelStateFlagsOffset + sizeof(std::uint64_t) + 8;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeGame(const unsigned char (&gameBytes)[8], std::uint64_t levelFlags) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGameBlockSize, 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
    for (std::size_t index = 0; index < 8; ++index) {
        WriteAt<std::uint8_t>(g_GameBytes, kGameStateFlagsOffset + index, gameBytes[index]);
    }
    WriteAt<std::uint64_t>(g_GameBytes, kLevelStateFlagsOffset, levelFlags);
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

    unsigned char gameBytes[8] = {GAME_BYTE_VALUES};
    std::uint64_t levelFlags = LEVEL_FLAG_VALUES;
    if (std::strcmp(scenario, "write") == 0 || std::strcmp(scenario, "args") == 0) {
        // 默认值即可。
    } else if (std::strcmp(scenario, "zero") == 0) {
        for (int index = 0; index < 8; ++index) gameBytes[index] = 0;
        levelFlags = 0;
    } else {
        return 91;
    }

    PublishFakeGame(gameBytes, levelFlags);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    // `ok(f)` = 「这次调用**没抛错**」（`pcall` 的第一个返回值）；`err(f)` = 错误消息。
    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local g = Game()"
        " local l = Game():GetLevel()"
        // ★ 每一位**带标签**打印：直接 `..` 拼 `tostring` 会得到 "truetruetruefalse…" 这种
        //   没法一眼数清的串（本批第一版就是这么写的，白追了一轮）。
        " local function dump(tag)"
        "   return tag"
        "     .. ' g0=' .. tostring(g:GetStateFlag(0))"
        "     .. ' g2=' .. tostring(g:GetStateFlag(2))"
        "     .. ' g47=' .. tostring(g:GetStateFlag(47))"
        "     .. ' g48=' .. tostring(g:GetStateFlag(48))"
        "     .. ' g49=' .. tostring(g:GetStateFlag(49))"
        "     .. ' g60=' .. tostring(g:GetStateFlag(60))"
        "     .. ' l2=' .. tostring(l:GetStateFlag(2))"
        "     .. ' l7=' .. tostring(l:GetStateFlag(7))"
        " end"
        // 写：置位 / 清位（读写两侧走同一块内存 ⇒ 这条断言同时穿过两条分支）
        " print(dump('B300 before'))"
        " local r = g:SetStateFlag(48, true)"
        " print('B300 ret=' .. type(r))"
        " print(dump('B300 after48'))"
        " print('B300 clear48=' .. tostring(g:SetStateFlag(48, false) == nil))"
        " print(dump('B300 cleared'))"
        // `Level` 那格：位 2 与位 7 互相不影响
        " print(dump('B300 lv7off=' .. tostring(l:SetStateFlag(7, false) == nil)))"
        " print(dump('B300 lv2off=' .. tostring(l:SetStateFlag(2, false) == nil)))"
        " print(dump('B300 lv2on=' .. tostring(l:SetStateFlag(2, true) == nil)))"
        // 越界：什么都不写、不报错
        " print(dump('B300 oob=' .. ok(function() g:SetStateFlag(100000, true) end)"
        "   .. ',' .. ok(function() g:SetStateFlag(-1, true) end)))"
        // 参数闸门
        " print('B300 gates=' .. ok(function() g:SetStateFlag() end)"
        "   .. ',' .. ok(function() g:SetStateFlag(48) end)"
        "   .. ',' .. ok(function() g:SetStateFlag('x', true) end)"
        "   .. ',' .. ok(function() g:SetStateFlag(48, true, 3) end))"
        " print('B300 gateerr=' .. err(function() g:SetStateFlag(48) end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b300.lua");
    static_cast<void>(result);
    return 0;
}'''
HARNESS = (HARNESS.replace("GAME_BYTE_VALUES", ", ".join("0x%02X" % b for b in GAME_BYTES))
                  .replace("LEVEL_FLAG_VALUES", "0x%XULL" % LEVEL_FLAGS))


class StateFlagWritesBatch300Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b300-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> str:
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_writing_a_bit_lands_in_memory_and_leaves_its_neighbours_alone(self):
        """★★ 写真的落到那一格（读侧立刻看得见），而且**别的位一个都不许动**。

        夹具（`Game` 那格 8 个字节）= `05 00 00 00 00 80 01 10`：
        位 0 / 位 2 / 位 47（字节 5 的 bit7）/ 位 48（字节 6 的 bit0）/ 位 60（字节 7 的 bit4）置着，
        位 49（字节 6 的 bit1）没置。`dump()` 每一位都带标签打印（**别**用无分隔符拼接 ——
        第一版就是那么写的，`truetruetruefalse…` 根本数不清，白追了一轮）。
        """
        out = self.run_scenario("write")
        #: 初值：位 48 置着、位 49 没置（两者同在字节 6）。
        self.assertIn("B300 before g0=true g2=true g47=true g48=true g49=false g60=true "
                      "l2=true l7=true", out)
        #: 置一个**已经置着**的位 ⇒ 读数不变。
        self.assertIn("B300 after48 g0=true g2=true g47=true g48=true g49=false g60=true "
                      "l2=true l7=true", out)
        #: ★★ 清掉位 48 ⇒ **只有它**变 false（同在字节 6 的位 49 照旧、别的字节照旧）。
        self.assertIn("B300 cleared g0=true g2=true g47=true g48=false g49=false g60=true "
                      "l2=true l7=true", out)

    def test_level_word_write_touches_only_the_named_bit(self):
        """`Level` 那格（`u64`）：位 7 清掉、位 2 清掉、位 2 再置回来 —— 每一步都只动得着那一位。"""
        out = self.run_scenario("write")
        self.assertIn("B300 lv7off=true g0=true g2=true g47=true g48=false g49=false g60=true "
                      "l2=true l7=false", out)
        self.assertIn("B300 lv2off=true g0=true g2=true g47=true g48=false g49=false g60=true "
                      "l2=false l7=false", out)
        self.assertIn("B300 lv2on=true g0=true g2=true g47=true g48=false g49=false g60=true "
                      "l2=true l7=false", out)

    def test_out_of_range_flag_is_a_silent_no_op(self):
        """越界标志号 ⇒ **什么都不写**（整串读数不变）且**不报错**。"""
        out = self.run_scenario("write")
        self.assertIn("B300 oob=true,true g0=true g2=true g47=true g48=false g49=false g60=true "
                      "l2=true l7=false", out)

    def test_return_value_count_is_zero(self):
        """PC 的返回类型是 `void` ⇒ `SetStateFlag(...)` 返回 **0 个值**（Lua 侧取到 `nil`）。"""
        out = self.run_scenario("write")
        self.assertIn("B300 ret=nil", out)
        self.assertIn("B300 clear48=true", out)

    def test_argument_gates(self):
        """参数闸门：必须**恰好**给一个整数标志号 + 一个位值（少给/只给一个/标志号非整数/多给都报错）。"""
        out = self.run_scenario("write")
        self.assertIn("B300 gates=false,false,false,false", out)
        self.assertIn("SetStateFlag expects an integer flag and a value", out)

    def test_all_zero_writes_then_reads_back(self):
        """全零起步：置位之前全 false，置位之后**只有那一位**变 true（再一次穿过写/读两条分支）。"""
        out = self.run_scenario("zero")
        self.assertIn("B300 before g0=false g2=false g47=false g48=false g49=false g60=false "
                      "l2=false l7=false", out)
        self.assertIn("B300 after48 g0=false g2=false g47=false g48=true g49=false g60=false "
                      "l2=false l7=false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 新种类 / 参数个数 / 共享处理器分支。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        header = FIELD_HEADER.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for owner, domain, index, offset_name, width, path in ROWS:
            with self.subTest(api=f"{owner}:SetStateFlag"):
                self.assertIn(
                    f'MakeId(ApiDomain::{domain}, 1, 0x{index:04X}), ApiDomain::{domain}, '
                    f'"{owner}", "SetStateFlag"', catalog, f"目录里没有 {owner}:SetStateFlag")
                text = path.read_text(encoding="utf-8")
                self.assertRegex(
                    text,
                    rf"\{{\s*(?i:0x0[23]01{index:04x}),\s*{offset_name},\s*{width},\s*"
                    rf"FieldKind::BoolBitArrayOfWriteArg,\s*FieldMissing::False,\s*"
                    rf"FieldReceipt::Level,\s*0xFF\}}",
                    f"数据行缺失或形状/宽度/接收者不对：{owner}:SetStateFlag")

        self.assertIn("BoolBitArrayOfWriteArg = 13,", header)
        self.assertIn("case FieldKind::BoolBitArrayOfWriteArg:", isaac)
        #: ★ 写侧必须走受保护的写原语（`WriteAt` = 先过 `IsEngineMemoryWritable`），
        #:   不许直接解引用（写错地址是"静默破坏别人的内存"）。
        body = isaac[isaac.index("case FieldKind::BoolBitArrayOfWriteArg:")::]
        body = body[:body.index("case FieldKind::U32:")]
        self.assertIn("engine_memory::WriteAt(", body)
        self.assertIn("&IsEngineMemoryWritable", body)
        self.assertNotIn("= *reinterpret_cast", body)
        #: 两个实参：标志号按整数闸、位值按 Lua 真值语义。
        self.assertIn("wantsBitArrayWriteArguments", isaac)
        self.assertIn("lua_toboolean(state, 3)", isaac)
        #: 两个偏移常量都是既有常量（本批零新增）。
        for name in ("kGameStateFlagsOffset", "kLevelStateFlagsOffset"):
            self.assertIn(f"inline constexpr uintptr_t {name} =", constants)


if __name__ == "__main__":
    unittest.main()
