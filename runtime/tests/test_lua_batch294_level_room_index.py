"""门禁：`Level` 的两个房间索引 + `GridEntityDoor:IsRoomType`（批次 294，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧依据 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `Level:GetPreviousRoomIndex()` | `Level.md:193` | 直读 `Level + 0x2155C`（`i32`） | `I32` / 降级 `-1` | 2 |
| `Level:GetLastBossRoomListIndex()` | `Level.md:167` | 直读 `Level + 0x21568`（`i32`） | `I32` / 降级 `-1` | 1 |
| `GridEntityDoor:IsRoomType(RoomType)` | `GridEntityDoor.md:63` | 门自己的两个房型字段（`+0x1A4` / `+0x1A8`） | **手写处理器** | 4 |

★ 前两条是字段行（接收者是既有的 `FieldReceipt::Level`）；第三条是**手写**——
PC 的绑定本体只有「实参 == 门当前所在房间的房型 **或** == 门通向房间的房型」两条比较，
而现有字段行 kind 里没有"拿实参跟两个字段比"的形状（`BoolEquals` 比的是行里的**常量**）。

## `Level` 的两个索引为什么长这样

引擎把房间索引**成对**存放（索引 + 维度），而且两个对都已被具名读者钉住：

* `0x21558` 当前索引 / `0x21560` 维度（本项目早有的常量，`Level::GetCurrentRoomDesc` 读它们）；
* `0x2155C` **上一个**索引 / `0x21564` 它的维度（本批）——
  `Level::GetLastRoomDesc()` 把 `[+0x2155C]` 当**第一个实参**、`[+0x8]`（= `+0x21564`）当第二个，
  尾调 `Level::GetRoomByIdx(int, int)`；另有三个 `Room::TrySpawn*Door` 在读它
  （恶魔房 / Boss Rush / 蓝子宫门都只在"刚从 Boss 房出来"时才可能开）；
* `0x21568` **本层最后一个 Boss 房**的列表索引（本批）——
  `Room::IsCurrentRoomLastBoss()` 把"当前房间描述符的 `+0x8`"（房间自己的列表索引）与它比较，
  另有 `Level::ShowBossRoom` / `Level::CanBossDevilRoom` 等六个具名读者。

## 宿主验到了什么、没验到什么

* **验到**（前两条字段行**没有入口指纹** ⇒ 伪造内存里的值真会被读出来）：
  - 写什么读回什么（两个字段各摆一个**互不相同**的值 ⇒ 读错格会立刻暴露）；
  - ★ **有符号读法**：写 `0xFFFFFFF6` 必须读回 **-10**（不是 4294967286）——
    PC 返回的是 `int`，模组拿它与 `-1` 比较是常见写法；
  - 拿不到 `Game`/`Level` ⇒ 两条都答 **-1**、**不抛 Lua 错误**；
  - 参数闸门：多给一个参数报错。
  - ★ **门那条只做静态判据**（登记进 `kGridEntityDoorHandlers[]`、走
    `AttachOwnerMethods(..., "GridEntityDoor", ...)`、两个偏移是门自己那两个具名常量、
    报错消息与实参类型）—— 与批次 284 同一条理由：**宿主造不出门句柄**
    （`DoorHandle` 没有从 Lua 构造它的入口，真机那条路要 `Room:GetDoor`）。
* **没验**：真机上这两个偏移与门那两个字段是不是就是这些量（宿主里"偏移对不对"是同一张表
  的两处引用同一个常量，自己证不了自己）。⇒ 真机项 = 作业单 **V45**。
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
LAYOUT_GAME = ROOT / "tools" / "layout_tables" / "game.json"
LAYOUT_DOOR = ROOT / "tools" / "layout_tables" / "grid_entity_door.json"

#: `(名字, 域内序号, 偏移常量)` —— 两条都是 `I32` + `FieldMissing::MinusOne` + `FieldReceipt::Level`。
LEVEL_APIS = (
    ("GetPreviousRoomIndex", 0x0019, "kLevelPreviousRoomIndexOffset"),
    ("GetLastBossRoomListIndex", 0x001A, "kLevelLastBossRoomListIndexOffset"),
)

#: 两个值**互不相同**（读错格立刻暴露）：上一个房间 100、最后一个 Boss 房 7。
PREVIOUS = 100
LAST_BOSS = 7
#: `0xFFFFFFF6` = **-10**（有符号）；PC 返回 `int`，模组会拿它与 `-1` 比。
NEGATIVE = -10


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（`Game`/`Level` 同一地址 —— `Level` 内嵌在 `Game` 起始处）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes                         = Game*（= Level*）
//   g_GameBytes[0x2155C]                     = 上一个房间索引
//   g_GameBytes[0x21568]                     = 最后一个 Boss 房的列表索引
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_GameBytes;
std::uintptr_t g_EngineBase = 0;
bool g_GameAvailable = true;

static_assert(kLevelPreviousRoomIndexOffset + sizeof(std::int32_t) <= 0x21570,
              "fake Game block must hold the previous room index");
static_assert(kLevelLastBossRoomListIndexOffset + sizeof(std::int32_t) <= 0x21570,
              "fake Game block must hold the last boss room list index");

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
    g_GameBytes.assign(0x21570, 0);
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

    // 四个场景：
    //   values   —— 100 / 7（两个字段互不相同）
    //   negative —— -10 / 3（看**有符号**读法）
    //   nogame   —— 拿不到 Game ⇒ 两条都该答 -1
    //   args     —— 参数闸门
    std::int32_t previous = 100;
    std::int32_t lastBoss = 7;
    if (std::strcmp(scenario, "values") == 0) {
        // 默认值。
    } else if (std::strcmp(scenario, "negative") == 0) {
        previous = -10;
        lastBoss = 3;
    } else if (std::strcmp(scenario, "nogame") == 0) {
        g_GameAvailable = false;
    } else if (std::strcmp(scenario, "args") == 0) {
        // 默认值。
    } else {
        return 91;
    }

    PublishFakeGame();
    WriteAt<std::int32_t>(g_GameBytes, kLevelPreviousRoomIndexOffset, previous);
    WriteAt<std::int32_t>(g_GameBytes, kLevelLastBossRoomListIndexOffset, lastBoss);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local level = Game():GetLevel()"
        " print('B294 lvkind=' .. type(level))"
        " print('B294 fn=' .. type(level.GetPreviousRoomIndex) .. ','"
        "   .. type(level.GetLastBossRoomListIndex))"
        " local prev = level:GetPreviousRoomIndex()"
        " local last = level:GetLastBossRoomListIndex()"
        " print('B294 prevkind=' .. type(prev) .. ',' .. type(last))"
        " print('B294 prev=' .. tostring(prev))"
        " print('B294 last=' .. tostring(last))"
        // 参数闸门：字段行**恰好收一个**（只有接收者）。
        " print('B294 argprev=' .. ok(function() return level:GetPreviousRoomIndex(1) end))"
        " print('B294 arglast=' .. ok(function() return level:GetLastBossRoomListIndex(1) end))"
        " print('B294 argerr=' .. tostring(select(2, pcall(function()"
        "   return level:GetPreviousRoomIndex(1) end))))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b294.lua");
    static_cast<void>(result);
    return 0;
}
'''


class LevelRoomIndexBatch294Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b294-")
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

    def test_each_index_is_read_from_its_own_field(self):
        """★★ 两个字段各摆一个**互不相同**的值（100 / 7）⇒ 读错格会立刻暴露。"""
        out = self.run_scenario("values")
        self.assertIn("B294 lvkind=userdata", out)
        self.assertIn("B294 fn=function,function", out)
        #: 两条都返回**整数**（PC 返回 `int`）。
        self.assertIn("B294 prevkind=number,number", out)
        self.assertIn("B294 prev=100", out)
        self.assertIn("B294 last=7", out)
        #: 反向：不许把两个值读串。
        self.assertNotIn("B294 prev=7", out)
        self.assertNotIn("B294 last=100", out)

    def test_negative_index_reads_back_signed(self):
        """★ 写 `0xFFFFFFF6` 必须读回 **-10**（不是 4294967286）——`i32` 的有符号读法。

        PC 返回的是 `int`，而模组拿这些索引与 `-1` 比较是常见写法（"没有上一个房间"）。
        用 `FieldKind::U32` 读会得到 4294967286 ⇒ 那种实现在这里红。
        """
        out = self.run_scenario("negative")
        self.assertIn("B294 prev=-10", out)
        self.assertIn("B294 last=3", out)
        self.assertNotIn("4294967286", out)

    def test_missing_game_degrades_to_minus_one_without_erroring(self):
        """★ 拿不到 `Game`/`Level` ⇒ 两条都答 **-1**、**不抛 Lua 错误**。

        `-1` 而不是 `0` 是刻意的：**0 是合法的房间索引**（答 0 等于说"上一个房间是 0 号"）。
        """
        out = self.run_scenario("nogame")
        self.assertIn("B294 prev=-1", out)
        self.assertIn("B294 last=-1", out)
        self.assertIn("B294 prevkind=number,number", out)

    def test_argument_gate_is_exactly_one(self):
        """参数闸门 = **恰好一个**（只有冒号调用压进来的 `self`），多给一个就报错。"""
        out = self.run_scenario("args")
        self.assertIn("B294 argprev=false", out)
        self.assertIn("B294 arglast=false", out)
        self.assertIn("Level:GetPreviousRoomIndex accepts no arguments", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与降级档 / 接收者 / 偏移常量。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        for name, index, offset_name in LEVEL_APIS:
            with self.subTest(api=f"Level:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Level, 1, 0x{index:04X}), ApiDomain::Level, "Level", "{name}"',
                    catalog, f"目录里没有 Level:{name}")
                self.assertRegex(
                    remaining,
                    rf"\{{\s*(?i:0x0301{index:04x}),\s*{offset_name},\s*0,\s*"
                    rf"FieldKind::I32,\s*FieldMissing::MinusOne,\s*FieldReceipt::Level,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档/接收者不对：Level:{name}")
                #: ★ 反回归：不许塞进引擎方法行表（引擎里没有这两个同名访问器）。
                self.assertNotRegex(remaining, rf"0x0301{index:04x}[^\n]*EngineCallShape")

        self.assertRegex(constants,
                         r"inline constexpr uintptr_t kLevelPreviousRoomIndexOffset\s*=\s*0x2155C;")
        self.assertRegex(constants,
                         r"inline constexpr uintptr_t kLevelLastBossRoomListIndexOffset\s*=\s*0x21568;")
        #: 布局表生成物与本头文件的同名同值常量：两条 `static_assert` 钉住不许漂移。
        for generated in ("kGamePreviousRoomIndexOffset", "kGameLastBossRoomListIndexOffset"):
            self.assertRegex(remaining, rf"static_assert\(kLevel\w+Offset\s*==\s*layout::{generated}")

    def test_the_door_api_is_registered_and_uses_the_door_own_fields(self):
        """★ 门那条是**手写**：必须登记进 `kGridEntityDoorHandlers[]`，且只读门自己的两个字段。

        ★ 与批次 284 同一条口径：宿主**造不出门句柄**（`DoorHandle` 没有从 Lua 构造它的入口）
        ⇒ 这条只做静态判据，行为留到真机（V45）。
        """
        catalog = CATALOG.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        self.assertIn('MakeId(ApiDomain::Isaac, 1, 0x00CC), ApiDomain::Isaac, "GridEntityDoor", '
                      '"IsRoomType"', catalog)
        #: 手写处理器必须挂在**门族自己的** handler 表上（否则挂到别的元表 ⇒ 模组调它是 nil）。
        self.assertRegex(remaining, r"kGridEntityDoorHandlers\[\] = \{(?:[^{}]|\{[^}]*\})*\n\};")
        door_table = remaining[remaining.index("kGridEntityDoorHandlers[]"):
                               remaining.index("constexpr LuaHandlerBinding kRoomHandlers[]")]
        self.assertIn("0x0E0100CC, &GridEntityDoorIsRoomType", door_table)
        self.assertIn("AttachOwnerMethods(state, \"GridEntityDoor\", kGridEntityDoorHandlers", remaining)
        #: 实现里必须读**门自己**的两个房型字段（PC 的 `[ecx+0x158]` / `[ecx+0x15c]` 对应）。
        body = remaining[remaining.index("int GridEntityDoorIsRoomType(lua_State* state) {"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("kGridEntityDoorCurrentRoomTypeOffset", body)
        self.assertIn("kGridEntityDoorTargetRoomTypeOffset", body)
        #: 实参是整数（PC 的 `eRoomType`）；不是整数要报错。
        self.assertIn("IsIntegerArgument(state, 2)", body)
        self.assertIn("GridEntityDoor:IsRoomType expects one integer argument", body)
        #: 两个偏移必须是 `runtime_constants.hpp` 里的具名常量。
        for name in ("kGridEntityDoorCurrentRoomTypeOffset", "kGridEntityDoorTargetRoomTypeOffset"):
            self.assertIn(f"inline constexpr uintptr_t {name} = ", constants)

    def test_the_layout_rows_are_confirmed_with_named_evidence(self):
        """★ 布局表：`Game` 两行 + 门表两行都必须 `confirmed` 且带具名证据。"""
        import json

        game = json.loads(LAYOUT_GAME.read_text(encoding="utf-8"))
        game_rows = {row["name"]: row for row in game["rows"]}
        for name, offset, functions in (
            ("PreviousRoomIndex", 0x2155C,
             ["_ZN15IsaacRepentance5Level15GetLastRoomDescEv",
              "_ZN15IsaacRepentance4Room21TrySpawnDevilRoomDoorEbb"]),
            ("LastBossRoomListIndex", 0x21568,
             ["_ZNK15IsaacRepentance4Room21IsCurrentRoomLastBossEv",
              "_ZN15IsaacRepentance5Level12ShowBossRoomEv"]),
        ):
            with self.subTest(row=name):
                self.assertIn(name, game_rows)
                row = game_rows[name]
                self.assertEqual(row["confidence"], "confirmed")
                self.assertEqual(row["offset"], offset)
                self.assertEqual(row["width"], 4)
                kinds = [e["kind"] for e in row["evidence"]]
                self.assertIn("semantic", kinds)
                cited = [e["function"] for e in row["evidence"]]
                for function in functions:
                    self.assertIn(function, cited, f"{name} 行缺少 {function} 的证据")

        door = json.loads(LAYOUT_DOOR.read_text(encoding="utf-8"))
        door_rows = {row["name"]: row for row in door["rows"]}
        for name, offset in (("CurrentRoomType", 0x1A4), ("TargetRoomType", 0x1A8)):
            with self.subTest(row=name):
                self.assertIn(name, door_rows)
                row = door_rows[name]
                self.assertEqual(row["confidence"], "confirmed")
                self.assertEqual(row["offset"], offset)
                self.assertEqual(row["width"], 4)
                kinds = [e["kind"] for e in row["evidence"]]
                self.assertIn("semantic", kinds)
                self.assertIn("access", kinds)
                #: ★ 写入方 `SetRoomTypes` 必须在证据里（两个字段的分工由**实参顺序**定死）。
                cited = [e["function"] for e in row["evidence"]]
                self.assertIn("_ZN15IsaacRepentance15GridEntity_Door12SetRoomTypesENS_9eRoomTypeES1_",
                              cited)

        #: 常量段落要写下 PC 的标尺与关键具名读者。
        import re

        constants = CONSTANTS.read_text(encoding="utf-8")
        written = {int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", constants)}
        for va in (0x59FEC0, 0x4C0530,          # PC 两个绑定本体
                   0x3DC69C, 0x465AB4, 0x466C48, 0x472130,   # 上一个房间索引的读者
                   0x464430, 0x3E7128, 0x3E7A14):            # 最后 Boss 房索引的读者
            self.assertIn(va, written, f"证据地址 {va:#x} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()
