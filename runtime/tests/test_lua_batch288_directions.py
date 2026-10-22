"""门禁：`EntityPlayer` 的"方向"三条（批次 288，2026-10-02）。

## 这一批是什么

| API | 契约 | 引擎侧依据 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `EntityPlayer:GetHeadDirection()` | `EntityPlayer.md:994` | 没有同名函数 ⇒ 读 `+0x19FC` | `I32` / `MinusOne` | 12（IsaacOnTwitchReloaded） |
| `EntityPlayer:GetFireDirection()` | `EntityPlayer.md:968` | 没有同名函数 ⇒ 读 `+0x1A00` | `I32` / `MinusOne` | 13（IsaacOnTwitchReloaded / RepentancePlus） |
| `EntityPlayer:GetMovementDirection()` | `EntityPlayer.md:1096` | ★ **有真函数** `Entity::get_movement_direction() const` @ `0x5C8AC` | `Int0`（引擎方法行） | 12（IsaacOnTwitchReloaded / RepentancePlus） |

前两条走**字段读取型数据行**（`kFieldApis`），第三条走**引擎方法数据行**（`kEntityPlayerEngineRows`），
三條都是 **0 字节代码**。偏移与入口字的逐条证据（PC↔Switch 三方对应、`0x4A0` 那簇、
`Weapon::SetHeadDirection` / `SetAimDirection` 两个写点、`get_movement_direction` 的算法推导）
写在 `runtime_constants.hpp` 的**批次 288 段**。

## 三条为什么能一起做（值域问题）

PC 的 `Direction` 枚举（`runtime/source/program/doc_lua_enum_data.cpp:32`）是
`NO_DIRECTION = -1`、`LEFT = 0`、`UP = 1`、`RIGHT = 2`、`DOWN = 3`；
而引擎 `get_movement_direction()` 算出来的四个值逐个等于 `LEFT/RIGHT/UP/DOWN`，
`SetAimDirection` 在"零向量"时写 `-1` —— 也就是 `NO_DIRECTION`。
⇒ **两边数值同构，数据行原样返回整数即可**，不需要任何映射表。这条是本批的判据核心。

## 宿主验到了什么、没验到什么

* **验到**（字段行那两条）：写进去什么就读回什么、读的是**接收者自己那一格**、
  ★ **有符号**（写 `-1` 读回 `-1` 而不是 `4294967295` —— 这与批次 287 的 `U32` 恰好相反，
  是本批最容易抄错的一格）、`0` 是**数字**不是 `nil`、参数闸门与接收者闸门。
* **没验**：**引擎方法行那条在宿主里必然降级** —— 共享处理器要先核对"模块基址 + 偏移处 4 字节
  等于登记过的入口字"，宿主没有引擎、伪造块里那一片是零 ⇒ 一定对不上。
  所以 `GetMovementDirection` 这里只能验**接线**（能挂上、能调、不报错、代数闸门），
  它的**真值**只能真机看 ⇒ 真机项 = 作业单 **V39**。
* **也没验**：真机上的偏移归属（宿主里"偏移对不对"是同一张表的两处都引用同一个常量）。
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
    ("EntityPlayer", "GetHeadDirection", 0x00C6, "kEntityPlayerHeadDirectionOffset", "I32", "MinusOne"),
    ("EntityPlayer", "GetFireDirection", 0x00C7, "kEntityPlayerFireDirectionOffset", "I32", "MinusOne"),
)

#: 引擎方法行的那一条：`(名字, 域内序号, 偏移常量, 入口字常量, 形状)`
ENGINE_API = ("GetMovementDirection", 0x00C8, "kEntityGetMovementDirectionOffset",
              "kEntityGetMovementDirectionEntryWord", "Int0")

#: 夹具写进"玩家"与"父实体"的值。两个对象**故意不同**：读错对象（例如恒定读玩家）
#: 会被 `parent*=` 那几条断言抓住。取值就用 PC 的 `Direction` 语义：
#: `NO_DIRECTION=-1 / LEFT=0 / UP=1 / RIGHT=2 / DOWN=3`。
PLAYER = {"head": 1, "fire": 2}      # UP / RIGHT
PARENT = {"head": 3, "fire": 0}      # DOWN / LEFT


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状与批次 284/286/287 的用例同源）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_Game 变量（槽里是**变量地址**）
//   g_Game 变量                     = Game*
//   Game + kGamePlayerArrayBegin/End = 只有一个元素的玩家指针数组
//   玩家对象首字                     = base + kEntityPlayerVtableOffset（`IsEntityPlayer` 要它）
//   玩家对象 + kEntityParentOffset   = 第二个"玩家对象"（`Entity.Parent`，用来验"读自己那格"）
//
// ★ 本批前面两条是字段行 ⇒ **没有入口指纹** ⇒ 宿主里能读到真值；
//   第三条走引擎方法行 ⇒ 宿主里必定降级（那正是"引擎方法行"的性质，不是本批的缺陷）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_ParentBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

static_assert(kEntityParentOffset < kEntityPlayerSize,
              "parent pointer must live inside the Entity_Player object");
static_assert(kEntityPlayerHeadDirectionOffset + sizeof(std::uint32_t) <= kEntityPlayerSize,
              "head direction must live inside the Entity_Player object");
static_assert(kEntityPlayerFireDirectionOffset + sizeof(std::uint32_t) <= kEntityPlayerSize,
              "fire direction must live inside the Entity_Player object");
//: ★ 两个方向格**必须相邻且这个顺序**（Head 在前、Fire 在后）—— PC 侧那两个取值器
//:   就是 `0x155C` / `0x1560` 这个次序，写反了这张断言会当场炸。
static_assert(kEntityPlayerFireDirectionOffset - kEntityPlayerHeadDirectionOffset == 4,
              "head direction must sit immediately before fire direction");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void MakeFakePlayer(std::vector<unsigned char>& block) {
    block.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(block, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(block, kEntityTypeOffset, kEntityTypePlayer);
    WriteAt<std::uint32_t>(block, kEntityPlayerTypeOffset, 0);
    WriteAt<std::uint32_t>(block, kEntityPlayerIndexOffset, 0);
}

struct DirectionValues {
    std::int32_t head;
    std::int32_t fire;
};

void WriteDirections(std::vector<unsigned char>& block, const DirectionValues& values) {
    WriteAt<std::int32_t>(block, kEntityPlayerHeadDirectionOffset, values.head);
    WriteAt<std::int32_t>(block, kEntityPlayerFireDirectionOffset, values.fire);
}

void PublishFakeGame(const DirectionValues& player, const DirectionValues& parent) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    MakeFakePlayer(g_PlayerBytes);
    MakeFakePlayer(g_ParentBytes);
    WriteDirections(g_PlayerBytes, player);
    WriteDirections(g_ParentBytes, parent);
    WriteAt<std::uint64_t>(g_PlayerBytes, kEntityParentOffset, AddressOf(g_ParentBytes));

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

    // 四个场景：
    //   fields —— 正常方向值（UP/RIGHT 与 DOWN/LEFT，两个对象的四个值都不重样）
    //   zeroed —— 全 0（★ 0 是**合法方向** `LEFT`，不是"没有"）
    //   none   —— 全 `-1`（`NO_DIRECTION`；★ 这一场专门验**有符号**：`U32` 会读回 4294967295）
    //   signed —— 极端有符号值（`INT32_MIN` / `INT32_MAX`）
    DirectionValues player{1, 2};
    DirectionValues parent{3, 0};
    if (std::strcmp(scenario, "fields") == 0) {
        // 默认值（与 Python 侧的 `PLAYER` / `PARENT` 一致）。
    } else if (std::strcmp(scenario, "zeroed") == 0) {
        player = {0, 0};
        parent = {0, 0};
    } else if (std::strcmp(scenario, "none") == 0) {
        player = {-1, -1};
        parent = {-1, -1};
    } else if (std::strcmp(scenario, "signed") == 0) {
        player = {INT32_MIN, INT32_MAX};
        parent = {0, 0};
    } else {
        return 91;
    }

    PublishFakeGame(player, parent);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " print('B288 pkind=' .. type(p))"
        " print('B288 fn=' .. type(p.GetHeadDirection) .. ',' .. type(p.GetFireDirection)"
        "   .. ',' .. type(p.GetMovementDirection))"
        " print('B288 head=' .. tostring(p:GetHeadDirection()))"
        " print('B288 fire=' .. tostring(p:GetFireDirection()))"
        // 引擎方法行：宿主里必然降级（入口字对不上）⇒ 这里只求"挂上了、能调、不报错"。
        " print('B288 moveok=' .. ok(function() return p:GetMovementDirection() end))"
        " print('B288 movetype=' .. type(p:GetMovementDirection()))"
        " print('B288 movetypeval=' .. tostring(p:GetMovementDirection()))"
        // 参数闸门：字段行**恰好收一个**参数（只有接收者），多给一个就报错。
        " print('B288 headarg=' .. ok(function() return p:GetHeadDirection(1) end))"
        " print('B288 firearg=' .. ok(function() return p:GetFireDirection(1) end))"
        " print('B288 headargerr=' .. tostring(select(2, pcall(function()"
        "   return p:GetHeadDirection(1) end))))"
        // 读的是**接收者自己**那一格：`p.Parent` 是另一个"玩家对象"（四个值都不重样）。
        " local q = p.Parent"
        " print('B288 parentkind=' .. type(q))"
        " print('B288 parenthead=' .. tostring(q:GetHeadDirection()))"
        " print('B288 parentfire=' .. tostring(q:GetFireDirection()))"
        // 接收者闸门：非实体句柄 ⇒ **硬报错**（全族共用，本批没动它）。
        " local f = p.GetHeadDirection"
        " print('B288 badrecv=' .. ok(function() return f({}) end))"
        " print('B288 badrecverr=' .. tostring(select(2, pcall(f, {}))))"
        // 对照：同族老方法（头方向的老兄弟 `GetHeadColor` 不在；用 `GetHearts`）拿同一个坏接收者
        // 报同样的错 ⇒ 接收者那一层不是本批引入的。
        " local g = p.GetHearts"
        " print('B288 siblingbadrecv=' .. ok(function() return g({}) end))"
        " print('B288 sibling=' .. type(p.GetHearts))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b288.lua");
    static_cast<void>(result);
    return 0;
}
'''


class EntityPlayerDirectionsBatch288Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b288-")
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

    def test_values_are_read_from_the_receivers_own_object(self):
        """★ 写进去什么就读回什么，而且是**接收者自己那个对象**的格子。

        为什么这是硬判据：数据行没挂到 `EntityPlayer` 页 ⇒ `p.GetHeadDirection` 是 `nil`；
        两条偏移互换（`+0x19FC` ↔ `+0x1A00`）⇒ 两条值对调，下面会红；
        形状写成 `Bool` ⇒ 整数变 `true`；写成 `U32` ⇒ `none` 那一场的 `-1` 会变 `4294967295`。
        """
        out = self.run_scenario("fields")
        self.assertIn("B288 pkind=userdata", out)
        self.assertIn("B288 fn=function,function,function", out)
        self.assertIn(f"B288 head={PLAYER['head']}", out)
        self.assertIn(f"B288 fire={PLAYER['fire']}", out)
        #: `Parent` 是另一个对象（值不同）⇒ 证明读的是**接收者自己**那一格。
        self.assertIn("B288 parentkind=userdata", out)
        self.assertIn(f"B288 parenthead={PARENT['head']}", out)
        self.assertIn(f"B288 parentfire={PARENT['fire']}", out)

    def test_zero_is_a_valid_direction_and_a_number(self):
        """全零 ⇒ 回 `0`（= PC 的 `LEFT`，**是合法方向**），而且是**数字**不是 `nil`。

        这一场钉的是"0 不等于没有"：若实现写成"读到 0 就当没有、压 `nil` 或 `false`"，
        模组里 `if p:GetHeadDirection() == Direction.LEFT` 那一支会静默失效。
        """
        out = self.run_scenario("zeroed")
        self.assertIn("B288 head=0", out)
        self.assertIn("B288 fire=0", out)
        self.assertIn("B288 parenthead=0", out)

    def test_directions_are_signed(self):
        """★ `-1`（`NO_DIRECTION`）要读回 **`-1`**，不是 `4294967295`。

        这是本批与批次 287 最容易抄反的一格：287 的心数是 `U32`（写满回 `4294967295`），
        而方向是 `I32`（`-1` 必须原样出来）—— PC 契约的 `Direction.NO_DIRECTION` 就是 `-1`。
        极端值那一场再验一次两侧边界（`INT32_MIN` / `INT32_MAX`）。
        """
        out = self.run_scenario("none")
        self.assertIn("B288 head=-1", out)
        self.assertIn("B288 fire=-1", out)
        self.assertNotIn("B288 head=4294967295", out)

        signed = self.run_scenario("signed")
        self.assertIn("B288 head=-2147483648", signed)
        self.assertIn("B288 fire=2147483647", signed)

    def test_movement_direction_is_wired_and_callable(self):
        """第三条（引擎方法行）在宿主里**只验接线**：挂上了、能调、不报错、返回**数字**。

        ★ 不硬编返回值：引擎方法行带**入口指纹**，宿主没有引擎 ⇒ 共享处理器一定走降级分支，
        返回的是那个分支的保守值，不是引擎真值。它的值只能真机看（作业单 V39）。
        ★ 但"返回**数字**而不是 `nil`"这一条是要钉的：它说明形状取的是 `Int0`（0 参、返回整数），
        不是 `Void0`（那样会返回 `nil`）—— 形状选错会让模组拿返回值去比较时抛错。
        """
        out = self.run_scenario("fields")
        self.assertIn("B288 moveok=true", out)
        self.assertIn("B288 movetype=number", out)

    def test_argument_gate_and_receiver_gate(self):
        """参数闸门 = **恰好一个**（只有接收者）；接收者不是实体句柄 = **硬报错**。"""
        out = self.run_scenario("fields")
        self.assertIn("B288 headarg=false", out)
        self.assertIn("B288 firearg=false", out)
        self.assertIn("EntityPlayer:GetHeadDirection accepts no arguments", out)
        self.assertIn("B288 badrecv=false", out)
        self.assertIn("expected an Entity", out)
        #: 对照：同族老方法拿同一个坏接收者**也报同样的错** ⇒ 接收者那层不是本批引入的。
        self.assertIn("B288 siblingbadrecv=false", out)
        self.assertIn("B288 sibling=function", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与降级档 / 偏移常量 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        #: 字段行那两条。
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
                    rf"FieldReceipt::EntityPlayer,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档不对：{owner}:{name}")
                self.assertRegex(constants, rf"inline constexpr uintptr_t {prefix}\s*=\s*0x[0-9A-Fa-f]+;")

        #: 引擎方法行那一条。
        name, index, offset_name, entry_name, shape = ENGINE_API
        self.assertIn(
            f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "EntityPlayer", "{name}"',
            catalog, f"目录里没有 EntityPlayer:{name}")
        self.assertRegex(
            isaac,
            rf"\{{\s*(?i:0x0e01{index:04x}),\s*{offset_name},\s*{entry_name},\s*"
            rf"FieldReceipt::EntityPlayer,\s*EngineCallShape::{shape},\s*0,\s*0xFF\}}",
            f"引擎方法数据行缺失或形状不对：EntityPlayer:{name}")
        self.assertRegex(constants, rf"inline constexpr uintptr_t {offset_name}\s*=\s*0x[0-9A-Fa-f]+;")
        self.assertRegex(constants,
                         rf"inline constexpr std::uint32_t {entry_name}\s*=\s*0x[0-9A-Fa-f]+U;")

        #: ★ 反回归：前面两条**不许**被塞进引擎方法行表（它们没有引擎函数）。
        self.assertNotRegex(isaac, r"0x0E0100C[67][^\n]*EngineCallShape")

    def test_the_three_way_correspondence_is_recorded(self):
        """★ 常量段必须写明 PC↔Switch 三方对应、`0x4A0` 那簇、以及第三个锚点。

        这条不是形式主义：两个新偏移（`0x19FC` / `0x1A00`）是**一个 setter 写两个相邻格**的
        典型场景（`SetAimDirection` 两格都写）—— 少了"`Weapon::SetHeadDirection` 只写前一个"
        这条第二锚点，两个偏移就分不清谁是谁。丢掉它，后人只能看到"某处写过一次"。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("inline constexpr uintptr_t kEntityPlayerHeadDirectionOffset = 0x19FC;", constants)
        self.assertIn("inline constexpr uintptr_t kEntityPlayerFireDirectionOffset = 0x1A00;", constants)
        self.assertIn("inline constexpr uintptr_t kEntityGetMovementDirectionOffset = 0x5C8AC;", constants)
        self.assertIn("0x4A0", constants, "PC↔Switch 的恒定差（0x4A0）没有写进常量段")
        for va in ("0x422D80", "0x427810", "0x4A9A24", "0x2A1CDC", "0x5C8AC"):
            self.assertIn(va, constants, f"证据地址 {va} 没有写进常量段")
        #: PC 的 `Direction` 枚举值（含 `NO_DIRECTION = -1`）要能对上。
        self.assertIn("-1", constants)


if __name__ == "__main__":
    unittest.main()
