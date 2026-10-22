"""门禁：`EntityPlayer` 的"心数 / 金色钥匙"三条只读字段（批次 287，2026-10-02）。

## 这一批是什么

| API | 契约 | 引擎入口 | 形状 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `EntityPlayer:GetBoneHearts()` | `EntityPlayer.md:866` | **没有同名函数** ⇒ 读 `+0x2450` | `U32` / `Zero` | 8（IsaacOnTwitchReloaded） |
| `EntityPlayer:GetEternalHearts()` | `EntityPlayer.md:956` | **没有同名函数** ⇒ 读 `+0x16C0` | `U32` / `Zero` | 1（Trinity） |
| `EntityPlayer:HasGoldenKey()` | `EntityPlayer.md:1372` | **没有同名函数** ⇒ 读 `+0x16D8`（1 字节） | `Bool` / `False` | 4（BOIStageAPI15 / RepentancePlus） |

三条都走**字段读取型数据行**（`kFieldApis`，0 字节代码）—— 三条在 Switch 镜像里按 mangled
**长度前缀**逐段解析各得 **0 个实现**，PC 同样是内联/字段访问器 ⇒ 只能读字段。
偏移的三方对应（每条都是「PC 读点 + PC 写点 + Switch 写点」）与那条**结构级互证**
（PC 上四个取值器相邻、PC↔Switch 恒定差 `0x428`）写在 `runtime_constants.hpp` 的**批次 287 段**。

## ★ 本批的宿主用例**能验到真值**（比批次 284/286 强一档）

引擎方法数据行（`EngineMethodRow`）在宿主里必然降级：共享处理器要先核对"模块基址 + 偏移处
那 4 个字节等于登记过的入口字"，而宿主没有引擎、伪造模块块里那一片是零 ⇒ 一定对不上。
**字段行没有入口指纹**，它的可读性判定在宿主上就是"地址非零、长度非零"
（`engine_memory::EngineMemoryReadable` 的 `#else` 分支）⇒ 伪造块里的字节**真的被读出来**。
所以这里可以断言"写进去 3，Lua 读回 3"，而不是只能断言"没报错"。

## 宿主验到了什么、没验到什么

* **验到**：三条的**接线**（目录行 / 数据行 id / 偏移常量 / owner / 形状与降级档）、
  **读的是接收者自己那一格**（同一个句柄族、两个不同的对象，读回各自的值）、
  **`U32` 与 `Bool` 的区别**（同一个字节写 2 ⇒ `HasGoldenKey` 为真，说明读的是"非 0 即真"
  的布尔而不是"等于 1"的比较）、**无符号**（写 `0xFFFFFFFF` 读回 `4294967295`，不是 `-1`）、
  **参数个数闸门**（恰好 1 个参数 = 只有接收者，多给就报错）、**接收者闸门**（非实体 ⇒ 硬报错）。
* **没验**：**真机上的偏移是否真的落在 `Entity_Player` 的这几个字段上**。宿主里"偏移对不对"
  是**同一张表的两处**（夹具的写入偏移、数据行的读取偏移）都引用同一个常量 —— 常量本身错了，
  这里照样绿。那一层只能靠 `runtime_constants.hpp` 的三方对应 + 真机读数（作业单 **V38**）。
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
CATALOG_TEST = ROOT / "runtime" / "tests" / "contract" / "test_api_catalog.py"

#: `(owner, 名字, 域内序号, 偏移常量, FieldKind, FieldMissing)`
APIS = (
    ("EntityPlayer", "GetBoneHearts", 0x00C3, "kEntityPlayerBoneHeartsOffset", "U32", "Zero"),
    ("EntityPlayer", "GetEternalHearts", 0x00C4, "kEntityPlayerEternalHeartsOffset", "U32", "Zero"),
    ("EntityPlayer", "HasGoldenKey", 0x00C5, "kEntityPlayerGoldenKeyFlagOffset", "Bool", "False"),
)

#: 夹具写进"玩家"与"父实体"的值。两个对象的值**故意不同**：读错对象（例如恒定读玩家）
#: 会被 `parent*=` 那几条断言抓住。骨心取 `3`（契约正文说"3 颗骨心就返回 3"，**不翻倍**）。
PLAYER = {"bone": 3, "eternal": 2, "golden": 1, "red": 6}
PARENT = {"bone": 7, "eternal": 5, "golden": 0}
#: `EntityPlayer:GetEffectiveMaxHearts()` = 红心容器 + 2 × 骨心（既有实现，本批只是别把它挤坏）。
EFFECTIVE_MAX_HEARTS = PLAYER["red"] + 2 * PLAYER["bone"]


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 284/286 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_Game 变量（槽里是**变量地址**，不是对象）
//   g_Game 变量                     = Game*
//   Game + kGamePlayerArrayBegin/End = 只有一个元素的玩家指针数组
//   玩家对象首字                     = base + kEntityPlayerVtableOffset（`IsEntityPlayer` 要它）
//   玩家对象 + kEntityParentOffset   = 第二个"玩家对象"（`Entity.Parent`，见下）
//
// ★ 本批**不需要**那个"覆盖到引擎方法偏移"的大模块块：三条都是字段行，没有入口指纹。
//   模块块只要够放 `g_Game` 槽即可（`kGameOwnerGlobalSlotOffset + 8`，约 10.7 MiB，与
//   批次 286 同一个量级 —— 这个尺寸是 `Isaac.GetPlayer` 那条链早就需要的）。
//
// ★ 为什么夹具里要放"父实体"：`Entity.Parent` 的实现（`isaac_api.cpp` 的 `Parent` 分支）
//   把指针**原样包成句柄**，并按 `IsEntityPlayer(parent)` 给元表 —— 所以把父指针指向**另一个
//   vptr = 玩家 vtable 的对象**，就能在 Lua 里拿到"第二个玩家句柄"。用它证明三条 API 读的是
//   **接收者自己那一格**（同样的偏移、不同的对象），而不是恒定读某个全局。
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
static_assert(kEntityPlayerBoneHeartsOffset + sizeof(std::uint32_t) <= kEntityPlayerSize,
              "bone hearts must live inside the Entity_Player object");
static_assert(kEntityPlayerEternalHeartsOffset + sizeof(std::uint32_t) <= kEntityPlayerSize,
              "eternal hearts must live inside the Entity_Player object");
static_assert(kEntityPlayerGoldenKeyFlagOffset + sizeof(std::uint8_t) <= kEntityPlayerSize,
              "golden key flag must live inside the Entity_Player object");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

// 造一个"看起来像 `Entity_Player`"的对象：首字是玩家 vtable（`IsEntityPlayer` 只认这个）。
void MakeFakePlayer(std::vector<unsigned char>& block) {
    block.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(block, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(block, kEntityTypeOffset, kEntityTypePlayer);
    WriteAt<std::uint32_t>(block, kEntityPlayerTypeOffset, 0);
    WriteAt<std::uint32_t>(block, kEntityPlayerIndexOffset, 0);
}

struct FieldValues {
    std::uint32_t bone;
    std::uint32_t eternal;
    std::uint8_t golden;
    std::uint32_t red;
};

void WriteFields(std::vector<unsigned char>& block, const FieldValues& values) {
    WriteAt<std::uint32_t>(block, kEntityPlayerBoneHeartsOffset, values.bone);
    WriteAt<std::uint32_t>(block, kEntityPlayerEternalHeartsOffset, values.eternal);
    WriteAt<std::uint8_t>(block, kEntityPlayerGoldenKeyFlagOffset, values.golden);
    WriteAt<std::uint32_t>(block, kEntityPlayerRedHeartContainersOffset, values.red);
}

void PublishFakeGame(const FieldValues& player, const FieldValues& parent) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    MakeFakePlayer(g_PlayerBytes);
    MakeFakePlayer(g_ParentBytes);
    WriteFields(g_PlayerBytes, player);
    WriteFields(g_ParentBytes, parent);
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

    // 三个场景：正常值 / 全零 / 边界（同一个字节写 2、"非 0 即真"；`u32` 写满看**无符号**）。
    FieldValues player{3, 2, 1, 6};
    FieldValues parent{7, 5, 0, 0};
    if (std::strcmp(scenario, "fields") == 0) {
        // 用默认值（与 Python 侧的 `PLAYER` / `PARENT` 一致）。
    } else if (std::strcmp(scenario, "zeroed") == 0) {
        player = {0, 0, 0, 0};
        parent = {0, 0, 0, 0};
    } else if (std::strcmp(scenario, "edge") == 0) {
        player = {0x80000000U, 0xFFFFFFFFU, 2, 0};
        parent = {0, 0, 0, 0};
    } else {
        return 91;
    }

    PublishFakeGame(player, parent);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    // `ok(f)` = "这次调用**没抛错**"（`pcall` 的第一个返回值）。
    // ★ `stdout + stderr` 一起回（批 285 被"只回 stdout"骗过一次）：脚本里报了 Lua 错时
    //   `print` 之前就中断、stdout 是空的，只回 stdout 等于"什么都没说"。
    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " print('B287 pkind=' .. type(p))"
        " print('B287 fn=' .. type(p.GetBoneHearts) .. ',' .. type(p.GetEternalHearts)"
        "   .. ',' .. type(p.HasGoldenKey))"
        " print('B287 bone=' .. tostring(p:GetBoneHearts()))"
        " print('B287 eternal=' .. tostring(p:GetEternalHearts()))"
        " print('B287 golden=' .. tostring(p:HasGoldenKey()))"
        " print('B287 eff=' .. tostring(p:GetEffectiveMaxHearts()))"
        // 参数闸门：字段行**恰好收一个**参数（= 只有接收者）。多给一个就报错，
        // 与既有同族字段行（`GetSoulHearts` 等）逐字同口径。
        " print('B287 bonearg=' .. ok(function() return p:GetBoneHearts(1) end))"
        " print('B287 eternalarg=' .. ok(function() return p:GetEternalHearts(1) end))"
        " print('B287 goldenarg=' .. ok(function() return p:HasGoldenKey(true) end))"
        " print('B287 boneargerr=' .. tostring(select(2, pcall(function()"
        "   return p:GetBoneHearts(1) end))))"
        // 读的是**接收者自己**那一格：`p.Parent` 是另一个"玩家对象"（值不同）。
        " local q = p.Parent"
        " print('B287 parentkind=' .. type(q))"
        " print('B287 parentbone=' .. tostring(q:GetBoneHearts()))"
        " print('B287 parenteternal=' .. tostring(q:GetEternalHearts()))"
        " print('B287 parentgolden=' .. tostring(q:HasGoldenKey()))"
        // ★ 接收者闸门：`CheckEntityHandle` 对**非实体**是**硬报错**（不是静默降级）——
        //   这是**全族共用**的判据（同一段代码，`GetSoulHearts` 等老方法一样报），本批没动它。
        //   写成 `f({})` 只压**一个**值（那张表）当接收者；写成 `p.GetBoneHearts({})` 会把
        //   `p` 也压进去 ⇒ 那一刻报的是**参数个数**错，验不到接收者这一层。
        " local f = p.GetBoneHearts"
        " print('B287 badrecv=' .. ok(function() return f({}) end))"
        " print('B287 badrecverr=' .. tostring(select(2, pcall(f, {}))))"
        " local g = p.GetSoulHearts"
        " print('B287 siblingbadrecv=' .. ok(function() return g({}) end))"
        " print('B287 sibling=' .. type(p.GetSoulHearts))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b287.lua");
    static_cast<void>(result);
    return 0;
}
'''


class EntityPlayerHeartsBatch287Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b287-")
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
        #: 连 `stderr` 一起交出去（见 harness 里那段说明）。
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_values_are_read_from_the_receivers_own_object(self):
        """★ 写进去什么就读回什么，而且是**接收者自己那个对象**的格子。

        为什么这是硬判据：数据行没挂到 `EntityPlayer` 页 ⇒ `p.GetBoneHearts` 是 `nil`；
        偏移抄错一格（例如与 `+0x16C4` 的魂心、`+0x16B8` 的红心容器互换）⇒ 读回的是别的数；
        形状写成 `Bool` ⇒ 整数会变成 `true`；`U32` 写成 `I32` ⇒ 边界场景里 `0xFFFFFFFF` 读回 `-1`。
        四条里任何一条断了，下面都会红。
        """
        out = self.run_scenario("fields")
        self.assertIn("B287 pkind=userdata", out)
        self.assertIn("B287 fn=function,function,function", out)
        #: 三条的真值。
        self.assertIn(f"B287 bone={PLAYER['bone']}", out)
        self.assertIn(f"B287 eternal={PLAYER['eternal']}", out)
        self.assertIn(f"B287 golden={'true' if PLAYER['golden'] else 'false'}", out)
        #: 既有消费方没被挤坏：`GetEffectiveMaxHearts` = 红心容器 + 2 × 骨心。
        self.assertIn(f"B287 eff={EFFECTIVE_MAX_HEARTS}", out)
        #: `Parent` 是另一个对象（值不同）⇒ 证明读的是**接收者自己**那一格。
        self.assertIn("B287 parentkind=userdata", out)
        self.assertIn(f"B287 parentbone={PARENT['bone']}", out)
        self.assertIn(f"B287 parenteternal={PARENT['eternal']}", out)
        self.assertIn(f"B287 parentgolden={'true' if PARENT['golden'] else 'false'}", out)

    def test_zero_is_a_number_and_zero_is_false(self):
        """全零：两条心数回 `0`（数字，**不是** `nil` / `false`），金色钥匙回 `false`。

        `0` 与 `nil` 在模组里差别很大（`nil` 会抛 `attempt to perform arithmetic on a nil value`，
        而 EID 那类代码对心数做算术）。
        """
        out = self.run_scenario("zeroed")
        self.assertIn("B287 bone=0", out)
        self.assertIn("B287 eternal=0", out)
        self.assertIn("B287 golden=false", out)
        self.assertIn("B287 parentbone=0", out)
        self.assertIn("B287 parentgolden=false", out)

    def test_boolean_is_nonzero_and_integers_are_unsigned(self):
        """边界：金色钥匙那一格写 `2` ⇒ **真**（读的是"非 0 即真"的字节，不是"等于 1"的比较）；
        两条心数按**无符号**读（`0xFFFFFFFF` ⇒ `4294967295`，不是 `-1`；`0x80000000` ⇒ `2147483648`）。

        这三条钉的是 `FieldKind` 选得对不对 —— 选 `BoolEquals(1)` 会让"置了 2"的玩家答 `false`；
        选 `I32` 会让写了满格的心数变成负数，模组拿去算血量就会走进错误分支。
        """
        out = self.run_scenario("edge")
        self.assertIn("B287 golden=true", out)
        self.assertIn("B287 eternal=4294967295", out)
        self.assertIn("B287 bone=2147483648", out)

    def test_argument_gate_and_receiver_gate(self):
        """参数闸门 = **恰好一个**（只有接收者）；接收者不是实体句柄 = **硬报错**。

        ★ 与引擎方法数据行（批次 286 的 `IsVulnerableEnemy`）不同：那边允许"尾部可省"，
        所以点号写法显式传 self 是放行的；字段行没有"可省参数"的概念，`p.GetBoneHearts(p)`
        会**报参数个数错**（两个参数）。这里刻意把这条差异也钉住，免得后人照抄 286 的形状。
        """
        out = self.run_scenario("fields")
        #: 多给一个参数 ⇒ 报错（`false` = pcall 失败），消息逐字包含 API 名。
        self.assertIn("B287 bonearg=false", out)
        self.assertIn("B287 eternalarg=false", out)
        self.assertIn("B287 goldenarg=false", out)
        self.assertIn("EntityPlayer:GetBoneHearts accepts no arguments", out)
        #: 接收者不是实体句柄 ⇒ **硬报错**（`CheckEntityHandle` 的全族共用判据，本批没动它）。
        self.assertIn("B287 badrecv=false", out)
        self.assertIn("expected an Entity", out)
        #: ★ 对照：同族老字段行（`GetSoulHearts`）拿同一个坏接收者**也报同样的错** ⇒
        #:   接收者这一层不是本批引入的、也不是本批改坏的。
        self.assertIn("B287 siblingbadrecv=false", out)
        self.assertIn("B287 sibling=function", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 数据行 / 形状与降级档 / 偏移常量 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        owner_table = CATALOG_TEST.read_text(encoding="utf-8")

        for owner, name, index, prefix, kind, missing in APIS:
            with self.subTest(api=f"{owner}:{name}"):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "{owner}", '
                    f'"{name}"',
                    catalog, f"目录里没有 {owner}:{name}")
                #: 数据行：`{0x0E01____, k…Offset, 0, FieldKind::X, FieldMissing::Y,`
                #:        `FieldReceipt::EntityPlayer, 0xFF}`
                self.assertRegex(
                    isaac,
                    rf"\{{\s*(?i:0x0e01{index:04x}),\s*{prefix},\s*0,\s*"
                    rf"FieldKind::{kind},\s*FieldMissing::{missing},\s*"
                    rf"FieldReceipt::EntityPlayer,\s*0xFF\}}",
                    f"数据行缺失或形状/降级档不对：{owner}:{name}")
                #: 偏移必须是**具名常量**（不许在实现里现编）—— 常量本身要在头文件里。
                self.assertRegex(constants, rf"inline constexpr uintptr_t {prefix}\s*=\s*0x[0-9A-Fa-f]+;")

        #: ★ 本批**没有**动引擎方法行（那是 286 的表），反回归：别顺手把这三条塞进那张表。
        self.assertNotRegex(isaac, r"0x0E0100C[345][^\n]*EngineCallShape")
        #: `EntityPlayer` owner 早就登记在「文件 → 允许的 owner」表里（新视图才需要加）。
        self.assertIn('"EntityPlayer"', owner_table)

    def test_offsets_and_the_structural_cross_check_are_recorded(self):
        """★ 常量段必须写明三方对应与那条**结构级互证**（PC 四处等差的 `0x428`）。

        这条不是形式主义：本批两个新偏移（`0x16C0` / `0x16D8`）的"取值锚点"就是靠它加厚的 ——
        丢掉它，后人只能看到"某处有过一次读写"，看不出这一簇在 PC/Switch 上是**整体平移**。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("inline constexpr uintptr_t kEntityPlayerEternalHeartsOffset = 0x16C0;", constants)
        self.assertIn("inline constexpr uintptr_t kEntityPlayerGoldenKeyFlagOffset = 0x16D8;", constants)
        self.assertIn("0x428", constants, "结构级互证（恒定差 0x428）没有写进常量段")
        #: 三条 PC 绑定 VA 要能核（相邻的三个槽是这条互证的第一层加强）。
        for va in ("0x6B1BE0", "0x6B1BF0", "0x6B1C00", "0x5EF450", "0x5EF420"):
            self.assertIn(va, constants, f"PC 绑定 VA {va} 没有写进常量段")
        #: 骨心不在那一簇里（必须写明，免得后人把 0x428 往它身上套）。
        self.assertIn("0x7A8", constants, "骨心不适用 0x428 这条互证的说明缺失")


if __name__ == "__main__":
    unittest.main()
