"""门禁：`EntityPlayer` 两条查询 + `GridEntityDoor` 三条（批次 284，2026-10-02）。

## 这一批是什么

| API | 调用点 | 引擎入口 | 形态 |
| --- | --- | --- | --- |
| `EntityPlayer:IsHoldingItem()` | 2 | `Entity_Player::IsHoldingItem() const` @ `0x2929D0` | 0 参 → 布尔 |
| `EntityPlayer:IsExtraAnimationFinished()` | 1 | `Entity_Player::IsExtraAnimationFinished() const` @ `0x2B78C4` | 0 参 → 布尔 |
| `GridEntityDoor:Open()` | 1 | `GridEntity_Door::Open()` @ `0x385894` | 0 参 → `void` |
| `GridEntityDoor:Close(boolean Force)` | 2 | `GridEntity_Door::Close(bool)` @ `0x3820F4` | 布尔 → `void` |
| `GridEntityDoor:IsTargetRoomArcade()` | 2 | `GridEntity_Door::IsTargetRoomArcade() const` @ `0x386038` | 0 参 → 布尔 |

## ★ 本批同时**更正了批次 273 留下的一句错话**

273 在目录里写过「`GridEntityDoor:Open/Close` 那种**有重写**的不收」。本批用**扫全镜像
mangled 名字**（不是"dynsym 里没看见"，也不靠名字眼熟）核实：这两条在整份 `Repentance.nro`
里**各只有一条** mangled 名字 ⇒ **没有子类重写**。当初多半是把
`Entity_NPC_HornfelDoor::Open(int)` / `Close()` 看成了重写 —— 那是**另一个类**（NPC），
只是方法名撞了。⇒ 这两条本批收下。完整说明在 `runtime_constants.hpp` 的批次 284 段。

同一把尺子也筛掉了（都**不收**，原因见常量段）：`Entity:CanShutDoors()`（4 个实现，
且报告给的偏移落在**导入跳板区**、守卫是 `return null` 的桩）、
`GridEntity:PostInit()`（8 个实现）、`GridEntity:Destroy(bool)`（多个实现，
且 `0x380C40` 那条是虚分派转发、会把实参丢掉换成常量 4）、
`Entity:IsVulnerableEnemy()`（只有一个实现，但引擎签名多一个**来源实体**参数，
而 PC 的无参重载到底传什么**无从确定** ⇒ 按纪律不猜；它是目前最大的单条未做项，22 处）。

## 宿主验到了什么、没验到什么

* **验到**：五条的接线（常量 / 守卫 / 目录行 / 绑定行 / owner / 门的 `__methods` 与回落顺序）、
  `EntityPlayer` 两条的**参数闸门**与**降级口径**（拿不到引擎入口时给 `false`、不报错）。
* **没验**：门三条的**行为** —— 宿主造不出门句柄（`Room:GetDoor` 需要一个真房间，
  而门句柄是 `DoorHandle` userdata，没有从 Lua 构造它的入口）⇒ 那三条是**静态**判据，
  行为与引擎副作用交真机（作业单 V35）。
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
REMAINING_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
LUA_RUNTIME = ROOT / "runtime" / "source" / "lua_runtime.cpp"
CATALOG_TEST = ROOT / "runtime" / "tests" / "contract" / "test_api_catalog.py"

#: `(owner, 名字, 域内序号, 引擎常量前缀, C++ 处理器名, 所在 TU)`
APIS = (
    ("EntityPlayer", "IsHoldingItem", 0x00BB, "kEntityPlayerIsHoldingItem",
     "EntityPlayerIsHoldingItem", ISAAC_API),
    ("EntityPlayer", "IsExtraAnimationFinished", 0x00BC, "kEntityPlayerIsExtraAnimationFinished",
     "EntityPlayerIsExtraAnimationFinished", ISAAC_API),
    ("GridEntityDoor", "Open", 0x00BD, "kGridEntityDoorOpen", "GridEntityDoorOpen", REMAINING_API),
    ("GridEntityDoor", "Close", 0x00BE, "kGridEntityDoorClose", "GridEntityDoorClose",
     REMAINING_API),
    ("GridEntityDoor", "IsTargetRoomArcade", 0x00BF, "kGridEntityDoorIsTargetRoomArcade",
     "GridEntityDoorIsTargetRoomArcade", REMAINING_API),
)

#: 门的那三条（宿主造不出句柄 ⇒ 只有静态判据）。
DOOR_APIS = tuple(a for a in APIS if a[0] == "GridEntityDoor")


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄 `test_lua_entity_cleanup_batch274.py` 那套，只留本批要用的几格）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_Game 变量（槽里是**变量地址**，不是对象）
//   g_Game 变量            = Game*
//   Game + kGamePlayerArrayBegin/End = 只有一个元素的玩家指针数组
//   Entity_Player 首字      = base + kEntityPlayerVtableOffset（`ValidatedEntityPlayer` 要它）
// 有它才能真的走到"取接收者"那一步 —— 否则 `Isaac.GetPlayer(0)` 是 nil，参数闸门根本没被执行。
//
// ★ 本批的两条**只验到"降级那一支"**：`EntityMethodByExpectedBytes` 会把入口按
//   `base + 偏移` 算出来（假模块只有几 KB，够不到 0x2929D0 / 0x2B78C4）⇒ 入口对不上 ⇒
//   走 `PushNativeFallbackBoolean(false)`。这正是我们要钉的**保守降级**口径；
//   真值只有真机给（作业单 V35）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeGame() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, 1);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerTypeOffset, 0);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityPlayerIndexOffset, 0);
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
    PublishFakeGame();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "queries") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local p = Isaac.GetPlayer(0)"
            " print('B284 holding=' .. tostring(p:IsHoldingItem())"
            "   .. ',' .. ok(function() return p:IsHoldingItem(1) end))"
            " print('B284 extra=' .. tostring(p:IsExtraAnimationFinished())"
            "   .. ',' .. ok(function() return p:IsExtraAnimationFinished(1) end));";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b284.lua");
    static_cast<void>(result);
    return 0;
}
'''


class ReceiversAndDoorBatch284Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b284-")
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
        return result.stdout

    # ---------------------------------------------------------------- 行为（宿主）

    def test_entity_player_queries_have_a_gate_and_a_conservative_fallback(self):
        """两条 0 参查询：**多给参数要报错**；引擎入口够不到时给 `false` 且**不报错**。

        ★ `false` 是这两条保守的那一边（"没拿着东西" / "额外动画已结束"）。
        ★ 为什么宿主只验到降级那一支，见文件头"宿主验到了什么"。
        """
        out = self.run_scenario("queries")
        #: 值 = false（降级），闸门 = false（pcall 失败 = 真的报错了）⇒ `false,false`。
        self.assertIn("B284 holding=false,false", out)
        self.assertIn("B284 extra=false,false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """★ 五条的接线：目录行 / 绑定行 / 常量与守卫 / owner / 门的方法表与回落顺序。

        这条就是完成定义台账里引用的判据。
        """
        catalog = CATALOG.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        remaining = REMAINING_API.read_text(encoding="utf-8")
        runtime = LUA_RUNTIME.read_text(encoding="utf-8")
        owner_table = CATALOG_TEST.read_text(encoding="utf-8")

        for owner, name, index, prefix, cpp, unit in APIS:
            with self.subTest(api=f"{owner}:{name}"):
                body = unit.read_text(encoding="utf-8")
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "{owner}", '
                    f'"{name}"',
                    catalog, f"目录里没有 {owner}:{name}")
                self.assertRegex(body, rf"\{{\s*(?i:0x0e01{index:04x}),\s*&{cpp}\s*\}}",
                                 f"绑定表里没有 0x{index:04X} → {cpp}")
                self.assertIn(f"inline constexpr uintptr_t {prefix}Offset", constants)
                self.assertIn(f"inline constexpr std::array<u8, 16> {prefix}ExpectedBytes",
                              constants)

        # 门的 owner 必须登记进「文件 → 允许的 owner」表，否则 `api_catalog` 门禁报"不属于该文件"。
        self.assertIn('"GridEntityDoor"', owner_table)

        # 门从本批起有**自己的**方法表，且 `__index` 的回落顺序是 字段 → 门自己 → GridEntity。
        # ★ 只在 `GridEntityDoorIndex` **函数体内**比位置：那两句注释在别的函数里也出现过，
        #   拿全文 index 会撞到前面的那处（第一版就这么红的）。
        self.assertIn("AttachGridEntityDoorMethods", remaining)
        self.assertIn('AttachOwnerMethods(state, "GridEntityDoor"', remaining)
        self.assertIn("AttachGridEntityDoorMethods(state)", runtime)
        index_start = remaining.index("int GridEntityDoorIndex(lua_State* state) {")
        index_end = remaining.index("\nint ", index_start + 10)
        door_body = remaining[index_start:index_end]
        self.assertIn("批次 284：门**自己**的方法表", door_body)
        self.assertLess(door_body.index("批次 284：门**自己**的方法表"),
                        door_body.index("落到 `GridEntity` **基类**"),
                        "门的 __methods 必须在 GridEntity 基类回落**之前**查（先查门自己）")
        # ★★ 反回归：门那张表**不许**在 `GridEntityIndex`（基类）里被查。
        #    第一版就是写错在那儿了 —— 后果是**石头/便便**去取 `Open` 也会命中门的方法，
        #    等于拿一个 `GridEntity_Rock*` 去调 `GridEntity_Door::Open()`（对别人内存的破坏）。
        #    这条断言把它钉死。
        base_start = remaining.index("int GridEntityIndex(lua_State* state) {")
        base_end = remaining.index("\nint ", base_start + 10)
        self.assertNotIn("kGridEntityDoorMetatable", remaining[base_start:base_end],
                         "基类 `__index` 里不许出现门的元表（会让普通网格实体取到门的方法）")

    def test_offsets_and_guards(self):
        """五个偏移常量必须两两点名，且十六字节守卫与镜像逐字节一致（由守卫核对工具覆盖）。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        for _owner, _name, _index, prefix, _cpp, _unit in APIS:
            with self.subTest(constant=prefix):
                self.assertIn(f"{prefix}Offset", constants)
                self.assertIn(f"{prefix}ExpectedBytes", constants)

    def test_the_two_entity_player_queries_use_the_conservative_fallback_ids(self):
        """两条布尔查询的降级走既有的探针出口（`PushNativeFallbackBoolean`），不是裸 `pushfalse`。"""
        body = ISAAC_API.read_text(encoding="utf-8")
        self.assertIn("PushNativeFallbackBoolean(state, kFbEntityPlayerIsHoldingItem, false)", body)
        self.assertIn("PushNativeFallbackBoolean(state, kFbEntityPlayerIsExtraAnimationFinished, false)",
                      body)

    def test_door_methods_are_not_taken_from_another_class(self):
        """★ 反回归：`GridEntityDoor` 的三条必须调**门自己**的入口。

        这一批的存在理由就是"273 曾以为门这两条收不了"。这里把当时的判断依据写进断言：
        三条的引擎符号名都是 `GridEntity_Door::`（不是 `Entity_NPC_HornfelDoor::`）。
        ★ 注意：常量段里**故意**写到了 `HornfelDoor` —— 那是"当初看串了的那个类"，
        所以这里只断言**没有它的常量**（`kHornfelDoor…`），不断言这个词在文件里不出现。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("GridEntity_Door::Open()", constants)
        self.assertIn("GridEntity_Door::Close(bool)", constants)
        self.assertIn("GridEntity_Door::IsTargetRoomArcade() const", constants)
        self.assertNotIn("kHornfelDoor", constants)

    def test_door_open_close_are_no_longer_claimed_to_have_overrides(self):
        """★ 反回归：目录里那句「`GridEntityDoor:Open/Close` 有重写的不收」必须已经被更正。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        self.assertIn("更正（批次 284", catalog)
        self.assertIn("各只有一条", catalog)


if __name__ == "__main__":
    unittest.main()
