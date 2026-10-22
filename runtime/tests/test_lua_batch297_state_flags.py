"""门禁：`Game:GetStateFlag(int Flag)` / `Level:GetStateFlag(int Flag)` + 两张状态枚举表
（批次 297，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Game:GetStateFlag(int Flag)` | `Game.md:374` | `Game + 0x26FA50` 的**位数组**（每字节 8 位） | 字段行 `BoolBitArrayOfArg` / 降级 `False` | 13 |
| `Level:GetStateFlag(int Flag)` | `Level.md:266` | `Level + 0x215F0` 的 **`u64`** | 同上（`offset2` = 8） | 13 |

合 **2 条 / 26 处**（清单里处数最多的一块），外加两张枚举表 `GameStateFlag`（55 条）与
`LevelStateFlag`（25 条）—— 模组是**拿枚举常量当实参**的（`GameStateFlag.STATE_BACKWARDS_PATH`
一类），缺表时那一行直接抛错、整条回调被摘。

新机制 `FieldKind::BoolBitArrayOfArg`：`offset` = 位数组基址、**`offset2` = 元素宽度（字节）**、
实参 = 标志号 `n` ⇒ 读第 `n / (8*宽度)` 个元素的第 `n % (8*宽度)` 位。

## 为什么基址是这两个（两处**互相独立**的位点位）

**PC 侧的标尺**：`Game:GetStateFlag` @ `0x4E61D0` 是 `test dword [esi + 4*(Flag>>5) + 0x1822C],
1<<(Flag&31)`（**32 位字**）；`Level:GetStateFlag` @ `0x41C430` 是 64 位掩码 + `and [ecx +
8*(Flag>>6) + 0x1C3168]`（**64 位字**）。

**Switch 侧**（枚举值来自 `tools/pc_enum_docs/`，两处都换过字节/位）：

* `Game + 0x26FA50`（每字节 8 位）：
  - `Level::IsBackwardsPath() @ 0x3E1DBC` 读 `0x26FA56` 的 **bit 0** —— `STATE_BACKWARDS_PATH = 48`
    （48 = 6*8+0 ⇒ 基址 `0x26FA50`）；
  - `Level::CanSpawnDevilRoom() @ 0x3E79A0` 读 `0x26FA55` 的 **bit 7** ——
    `STATE_BACKWARDS_PATH_INIT = 47`（5*8+7）；
  - 另有 `CanSpawnTrapDoor` / `SetNextStage` / `Level::Init`（后者把「基址 +0x26FA50、读字节 6」
    直接写出来）。
* `Level + 0x215F0`（`u64`）：
  - `Level::SetRedHeartDamage() @ 0x3E7F00` 做 `orr x9,x9,#0x4` —— `STATE_REDHEART_DAMAGED = 2`；
  - `Level::ApplyCompassEffect(bool) @ 0x3E7024` 做 `orr x8,x8,#0x80` —— `STATE_COMPASS_EFFECT = 7`。

★ 顺带纠正一条历史负结果：交接文档记的「用 PC 间距推的 `Game+0x215F0` 没被证实」——
真身是 **`Level + 0x215F0`**（那次把基址对象认错了）。

## 宿主验到了什么、没验到什么

* **验到**（字段行没有入口指纹 ⇒ 伪造内存里的位真会被读出来）：
  - ★★ **读的是"实参指定的那一位"**：同一字节里置**不同**位、以及跨字节（47 在字节 5、48 在字节 6）
    ⇒ "读错字节"与"读错位"都会红；
  - ★ **同一格里的两位互不影响**（`Level` 那格：bit2 与 bit7 分别单独置）；
  - **越界标志号 ⇒ false**（负号、巨大号），**不抛错**；
  - 参数闸门：不给实参 / 给非整数 ⇒ 报错（消息里有 API 名）。
* **没验**：
  1. 真机上这两格是不是就是那些标志（宿主里"基址对不对"是常量与行两处引用同一个值，
     自己证不了自己）。⇒ 真机项 = 作业单 **V48**。
  2. 「接收者解析不到（拿不到 `g_Game`）⇒ false」那条分支：本夹具总是能拿到 `g_Game`；
     要造"拿不到"得把模块槽清掉 —— 与 `Room`/`Level` 族既有用例同一处缺口。
"""

import json
import re
import subprocess
import sys
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
GAME_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "game_api.cpp"
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
FIELD_HEADER = ROOT / "runtime" / "src" / "interfaces" / "lua" / "field_api.hpp"
ENUM_TOOL = ROOT / "tools" / "generate_doc_enum_tables.py"
ENUM_DOCS = ROOT / "tools" / "pc_enum_docs"

#: `(owner, 名字, 域, 序号, 偏移常量, offset2, 行所在文件)`。
FIELD_APIS = (
    ("Game", "GetStateFlag", "Game", 0x0015, "kGameStateFlagsOffset", 1, GAME_API),
    ("Level", "GetStateFlag", "Level", 0x001B, "kLevelStateFlagsOffset", 8, REMAINING_API),
)

#: 夹具里的取值（**互不相同** ⇒ 读错字节/读错位都会红）。
#: `Game` 那格按字节给出（`0x26FA50` 起 8 个字节）：字节 0 = bit2（标志 2）、
#: 字节 5 = bit7（标志 47）、字节 6 = bit0（标志 48）、字节 7 = bit4（标志 60）。
GAME_BYTES = (0x04, 0x00, 0x00, 0x00, 0x00, 0x80, 0x01, 0x10)
#: `Level` 那格的 `u64`：bit2（标志 2）+ bit7（标志 7）。
LEVEL_FLAGS = (1 << 2) | (1 << 7)
#: `swap` 那一场：只留 bit2 ⇒ 若实现"读错位"（例如恒测 bit7）就会红。
LEVEL_FLAGS_SWAP = 1 << 2


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 293/287 的用例，但**不需要玩家** —— 只要 `g_Game`）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                         = Game*
//   Game + kGameStateFlagsOffset (0x26FA50)  = 本批读的**位数组**（8 个字节）
//   Game + kLevelStateFlagsOffset (0x215F0)  = 本批读的 **u64**
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

//: `Game` 块要盖住两个数组里靠后的那个（+8 字节足够容纳 `u64`）。
constexpr std::size_t kGameBlockSize = kLevelStateFlagsOffset + sizeof(std::uint64_t) + 8;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeGame(const unsigned char* gameBytes, std::uint64_t levelFlags) {
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

    // 四个场景：
    //   values  —— 两个数组各摆互不相同的位（默认）
    //   swap    —— `Level` 那格只留 bit2 ⇒ 专抓"读错位"
    //   args    —— 参数闸门与越界标志号
    //   zero    —— 全 0
    unsigned char gameBytes[8] = {GAME_BYTE_VALUES};
    std::uint64_t levelFlags = LEVEL_FLAG_VALUES;
    if (std::strcmp(scenario, "swap") == 0) {
        levelFlags = LEVEL_FLAG_SWAP_VALUES;
    } else if (std::strcmp(scenario, "zero") == 0) {
        for (int index = 0; index < 8; ++index) gameBytes[index] = 0;
        levelFlags = 0;
    } else if (std::strcmp(scenario, "values") == 0 || std::strcmp(scenario, "args") == 0) {
        // 默认值即可。
    } else {
        return 91;
    }

    PublishFakeGame(gameBytes, levelFlags);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* readings =
        "local g = Game()"
        " local l = Game():GetLevel()"
        " print('B297 gfn=' .. type(g.GetStateFlag) .. ' lfn=' .. type(l.GetStateFlag))"
        // Game 那格：不同字节、不同位
        " print('B297 g2='  .. tostring(g:GetStateFlag(2)))"
        " print('B297 g47=' .. tostring(g:GetStateFlag(47)))"
        " print('B297 g48=' .. tostring(g:GetStateFlag(48)))"
        " print('B297 g60=' .. tostring(g:GetStateFlag(60)))"
        " print('B297 g0='  .. tostring(g:GetStateFlag(0)))"
        " print('B297 gkind=' .. type(g:GetStateFlag(2)))"
        // Level 那格：同一 u64 里的不同位
        " print('B297 l2=' .. tostring(l:GetStateFlag(2)))"
        " print('B297 l7=' .. tostring(l:GetStateFlag(7)))"
        " print('B297 l0=' .. tostring(l:GetStateFlag(0)))"
        " print('B297 l23=' .. tostring(l:GetStateFlag(23)))";

    const char* gates =
        "local g = Game()"
        " local l = Game():GetLevel()"
        " local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " print('B297 gneg=' .. tostring(g:GetStateFlag(-1)))"
        " print('B297 gbig=' .. tostring(g:GetStateFlag(100000)))"
        " print('B297 lneg=' .. tostring(l:GetStateFlag(-5)))"
        " print('B297 lbig=' .. tostring(l:GetStateFlag(99999)))"
        " print('B297 gnoarg=' .. ok(function() return g:GetStateFlag() end))"
        " print('B297 gnoargerr=' .. err(function() return g:GetStateFlag() end))"
        " print('B297 gstrid=' .. ok(function() return g:GetStateFlag('x') end))"
        " print('B297 gstridok=' .. ok(function() return g:GetStateFlag(2, 3) end))";

    const char* script = std::strcmp(scenario, "args") == 0 ? gates : readings;
    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b297.lua");
    static_cast<void>(result);
    return 0;
}
'''
HARNESS = (HARNESS
           .replace("GAME_BYTE_VALUES", ", ".join("0x%02X" % b for b in GAME_BYTES))
           .replace("LEVEL_FLAG_VALUES", "0x%XULL" % LEVEL_FLAGS)
           .replace("LEVEL_FLAG_SWAP_VALUES", "0x%XULL" % LEVEL_FLAGS_SWAP))


class StateFlagsBatch297Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b297-")
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

    def test_each_flag_is_read_from_the_byte_and_bit_the_argument_names(self):
        """★★ `Game` 那格：四个标志落在**三个不同字节**、**四个不同位** ⇒ 读错字节/位都会红。

        夹具把 `0x26FA50` 起 8 个字节摆成 `04 00 00 00 00 80 01 10`：
        标志 2 = 字节 0 的 bit2、标志 47 = 字节 5 的 bit7、标志 48 = 字节 6 的 bit0、
        标志 60 = 字节 7 的 bit4 ⇒ 每条断言都同时钉住"基址 + 每字节 8 位"这条模型。
        """
        out = self.run_scenario("values")
        self.assertIn("B297 gfn=function lfn=function", out)
        self.assertIn("B297 gkind=boolean", out)
        self.assertIn("B297 g2=true", out)
        self.assertIn("B297 g47=true", out)
        self.assertIn("B297 g48=true", out)
        self.assertIn("B297 g60=true", out)
        #: 置位以外的都答 false（同一字节里别的位、以及别的字节）。
        self.assertIn("B297 g0=false", out)

    def test_level_flag_word_reads_the_argument_bit_only(self):
        """★ `Level` 那格：`u64` 里 bit2 与 bit7 都置 ⇒ 两位都 true，别的位 false。

        `swap` 那一场只留 bit2 ⇒ `l7` 变 false —— 专抓"读错位"（例如恒测 bit7 或恒测 bit0）。
        """
        out = self.run_scenario("values")
        self.assertIn("B297 l2=true", out)
        self.assertIn("B297 l7=true", out)
        self.assertIn("B297 l0=false", out)
        self.assertIn("B297 l23=false", out)

        swapped = self.run_scenario("swap")
        self.assertIn("B297 l2=true", swapped)
        self.assertIn("B297 l7=false", swapped)
        #: `Game` 那格不受影响（两条 API 读的是**不同的基址**）。
        self.assertIn("B297 g48=true", swapped)

    def test_all_zero_reads_false(self):
        out = self.run_scenario("zero")
        for key in ("g2", "g47", "g48", "g60", "g0", "l2", "l7", "l0", "l23"):
            self.assertIn(f"B297 {key}=false", out)

    def test_out_of_range_index_degrades_to_false_without_erroring(self):
        """★ 越界标志号 ⇒ false 且**不抛错**（PC 没有边界检查、会读飞，我们刻意不读）。

        ★ 这一条同时验"越界的 47/48 号不会误打到相邻字段"：`Level` 那格的 `u64` 里
        bit2/bit7 是置着的，而 `l:GetStateFlag(99999)` / `g:GetStateFlag(100000)` 都答 false。
        """
        out = self.run_scenario("args")
        self.assertIn("B297 gneg=false", out)
        self.assertIn("B297 gbig=false", out)
        self.assertIn("B297 lneg=false", out)
        self.assertIn("B297 lbig=false", out)

    def test_argument_gate_is_exactly_one_integer(self):
        """参数闸门：**必须**给一个整数标志号 —— 不给报错、给非整数报错、多给也报错。"""
        out = self.run_scenario("args")
        self.assertIn("B297 gnoarg=false", out)
        self.assertIn("Game:GetStateFlag expects one integer argument", out)
        self.assertIn("B297 gstrid=false", out)
        self.assertIn("B297 gstridok=false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 种类与降级档 / 接收者 / 偏移常量 / 两处挂载 / 新机制的登记。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        header = FIELD_HEADER.read_text(encoding="utf-8")

        for owner, name, domain, index, offset_name, width, path in FIELD_APIS:
            with self.subTest(api=f"{owner}:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::{domain}, 1, 0x{index:04X}), ApiDomain::{domain}, '
                    f'"{owner}", "{name}"', catalog, f"目录里没有 {owner}:{name}")
                text = path.read_text(encoding="utf-8")
                self.assertRegex(
                    text,
                    rf"\{{\s*(?i:0x0[23]01{index:04x}),\s*{offset_name},\s*{width},\s*"
                    rf"FieldKind::BoolBitArrayOfArg,\s*FieldMissing::False,\s*"
                    rf"FieldReceipt::Level,\s*0xFF\}}",
                    f"数据行缺失或形状/宽度/降级档/接收者不对：{owner}:{name}")
                #: ★ 反回归：不许被塞进引擎方法行表 —— 这两条引擎里没有同名访问器。
                self.assertNotRegex(text, rf"0x0[23]01{index:04x}[^\n]*EngineCallShape")

        #: 两个偏移常量。
        self.assertRegex(constants, r"inline constexpr uintptr_t kGameStateFlagsOffset\s*=\s*0x26FA50;")
        self.assertRegex(constants, r"inline constexpr uintptr_t kLevelStateFlagsOffset\s*=\s*0x215F0;")
        #: 新种类要在头文件里有名字、在共享处理器里有分支。
        self.assertIn("BoolBitArrayOfArg = 12,", header)
        self.assertIn("case FieldKind::BoolBitArrayOfArg:", ISAAC_API.read_text(encoding="utf-8"))
        #: `Game` 那一条是本族**第一张**字段行表 —— 必须真的挂到 `AttachGameMethods`。
        self.assertRegex(GAME_API.read_text(encoding="utf-8"),
                         r"AttachOwnerMethods\(state, kGameOwner,[^;]*kGameFieldApis",
                         "`kGameFieldApis` 没有传给 AttachOwnerMethods ⇒ 那条 API 根本挂不上")
        #: `Level` 那一条挂在既有的 `kLevelFieldApis` 上（那张表的挂载断言在
        #: `test_field_api_rows.py` 里已有，这里只确认行在里面）。
        self.assertRegex(REMAINING_API.read_text(encoding="utf-8"),
                         r"0x0301001B,\s*kLevelStateFlagsOffset")

        #: ★ 常量段要写下取证依赖的那几个地址与枚举值（标尺 + 两个基址 + 四个位点位）。
        written = {int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", constants)}
        for va in (0x4E61D0, 0x41C430,            # PC 两条绑定
                   0x3E1DBC, 0x3E79A0, 0x3E0F5C,  # Game 那格：三个具名读者（含"基址+字节6"那一条）
                   0x3E7F00, 0x3E7F10,            # Level 那格：SetRedHeartDamage 的 orr #0x4
                   0x3E7024, 0x3E7028):           #           ApplyCompassEffect 的 orr #0x80
            self.assertIn(va, written, f"证据地址 {va:#x} 没有写进常量段")
        for off in (0x26FA50, 0x26FA55, 0x26FA56, 0x215F0, 0x1822C, 0x1C3168):
            self.assertIn(off, written, f"偏移 {off:#x} 没有写进常量段")

    def test_the_two_state_enum_tables_are_published_with_the_values_this_batch_relies_on(self):
        """★ 两张枚举表必须真的发布，且本批取证依赖的那几个值不许变。

        `GameStateFlag` / `LevelStateFlag` 是**两个不同的枚举**（`Game` 上一个、`Level` 上一个），
        模组**拿它们当实参** ⇒ 缺哪一张，那一边的 `GetStateFlag(...)` 就直接抛错。
        """
        sys.path.insert(0, str(ROOT / "tools"))
        import generate_doc_enum_tables as tool  # noqa: PLC0415

        for table in ("GameStateFlag", "LevelStateFlag"):
            self.assertIn(table, tool.TABLES, f"{table} 没有登记进生成器的 TABLES")
            self.assertTrue((ENUM_DOCS / f"{table}.md").is_file(), f"缺契约页 {table}.md")
        #: ★ 本批的**取证直接依赖**这几个值（值 → Switch 位点位的对应见常量段与台账）。
        expected = {
            ("GameStateFlag", "STATE_BACKWARDS_PATH"): 48,
            ("GameStateFlag", "STATE_BACKWARDS_PATH_INIT"): 47,
            ("LevelStateFlag", "STATE_REDHEART_DAMAGED"): 2,
            ("LevelStateFlag", "STATE_COMPASS_EFFECT"): 7,
        }
        parsed = {table: dict(tool.parse_table(table, ENUM_DOCS / f"{table}.md"))
                  for table in ("GameStateFlag", "LevelStateFlag")}
        for (table, key), value in expected.items():
            with self.subTest(table=table, key=key):
                self.assertIn(key, parsed[table], f"{table} 里没有 {key}")
                self.assertEqual(parsed[table][key], value,
                                 f"{table}.{key} 的值变了 ⇒ 本批的基址结论必须重做")
        #: 生成物里的表名也要有（`--check` 由 `test_lua_doc_enum_tables.py` 管，这里只确认数据在）。
        generated = (ROOT / "runtime" / "source" / "program"
                     / "doc_lua_enum_data.cpp").read_text(encoding="utf-8")
        self.assertIn('"GameStateFlag"', generated)
        self.assertIn('"LevelStateFlag"', generated)

    def test_batch_evidence_addresses_are_present_in_the_ledger(self):
        """台账两条都必须在 `api_definition_of_done.json` 里、且 `provenance.offsets` 指向真常量。"""
        ledger = json.loads((ROOT / "tools" / "api_definition_of_done.json").read_text(encoding="utf-8"))
        rows = ledger["rows"]
        for owner, name, _domain, _index, offset_name, _width, _path in FIELD_APIS:
            key = f"{owner}:{name}"
            with self.subTest(api=key):
                self.assertIn(key, rows, f"台账里没有 {key}")
                provenance = rows[key]["provenance"]
                self.assertEqual(provenance["kind"], "engine_call")
                self.assertIn(offset_name, provenance["offsets"])


if __name__ == "__main__":
    unittest.main()
