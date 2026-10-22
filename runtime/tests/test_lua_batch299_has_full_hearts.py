"""门禁：`EntityPlayer:HasFullHearts()`（批次 299，2026-10-03）。

## 这一批是什么

| API | 契约 | 引擎侧 | 走法 | 语料调用点 |
| --- | --- | --- | --- | --- |
| `EntityPlayer:HasFullHearts()` | `EntityPlayer.md:1357` | `[+0x16BC] >= 有效最大红心` | **手写处理器**（判据要跨三格算） | 6 |

## 判据（★ 三方互相印证后才落的）

PC 侧绑定本体（`0x6B1B40`）先调一个**按玩家类型的跳表**（助手 `0x78CDC0`：读 `[this+0x130c]`
= PlayerType → `movzx eax,byte[eax+0x78CE0C]` → 跳表 → 分类 1/2/3/4/0），然后：

* 分类 **1 或 2** ⇒ `[+0x1294] >= [+0x1290]`（**骨心不算**）；
* 其余（含类型不在 `4..0x28` 范围内）⇒ `[+0x1294] >= [+0x1290] + 2*[+0x1CA8]`。

★★ 把 PC 那 **37 字节的表**独立解出来（类型 4..0x28 逐个分类），得到的「走简单支」的集合与
成品里**既有**的 `kEntityPlayerBoneHeartlessTypeMask = 0x11883021410` **逐位相等（零差异）**；
而既有的 `EntityPlayer:GetEffectiveMaxHearts()` 用的正是同一个掩码的同一套分支
（它的注释记着「与引擎自己的 `Entity_Player::GetEffectiveMaxHearts()`（`0x27E8AC`）逐分支一致」）。

⇒ 两边的**判据是同一条**：

```
HasFullHearts()  ⇔  当前红心（+0x16BC） >= 有效最大红心（容器 + 2×骨心，骨心不计的类型只算容器）
```

所以本批把 `GetEffectiveMaxHearts` 里那段**抽成共享函数**（`ReadEffectiveMaxHearts`）供两条 API
共用 —— **判据只有一份**。四个偏移全是既有常量（本批**零新增**）。

## 宿主验到了什么、没验到什么

* **验到**（真值，夹具摆两名**字段完全相同、只有玩家类型不同**的玩家）：
  - ★★ **类型分支真的在起作用**：`(type 0, 红 4+骨 2, 当前 7)` 答 **false**（上限 8），
    而 `(type 4, 同样的 4/2/7)` 答 **true**（上限 4，骨心不计）—— **同样的字段、不同的答案**，
    漏掉类型分支这条断言立刻红；
  - 够到上限时答 **true**（红 8 对上限 8 ⇒ `setge` 是**有符号**比较，相等即真）；
  - 全零 ⇒ **true**（`0 >= 0`）；
  - 恒返回 `boolean`；参数闸门（多给实参报错）。
* **没验**：真机上那几个字段与类型的组合是否与 PC 一致。⇒ 真机项 = 作业单 **V50**
  （最强判据 = 让玩家**恰好满红心**时 `HasFullHearts()` 为 true，再挨一下变 false；
  ★ 骨心角色（The Forgotten 等）与普通角色在同等红心下读数**不同**）。
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
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

API_INDEX = 0x00D1

#: 三名玩家的夹具。★ p0 与 p1 **字段完全相同、只有类型不同** —— 那是本批最要命的断言。
PLAYERS = (
    {"type": 0, "hearts": 7, "containers": 4, "bone": 2},   # 类型 0（骨心计入）⇒ 上限 8 ⇒ false
    {"type": 4, "hearts": 7, "containers": 4, "bone": 2},   # 类型 4（骨心不计）⇒ 上限 4 ⇒ true
    {"type": 0, "hearts": 8, "containers": 4, "bone": 2},   # 恰好够到上限 8 ⇒ true
)
#: 全零那一场（判据是 `>=` ⇒ `0 >= 0` 答 true）。
PLAYERS_ZERO = tuple({"type": 0, "hearts": 0, "containers": 0, "bone": 0} for _ in PLAYERS)


def _cpp_players(values) -> str:
    return ", ".join("{%d, %d, %d, %d}" % (p["type"], p["hearts"], p["containers"], p["bone"])
                     for p in values)


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 287 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes（槽里是**变量地址**）
//   g_OwnerSlotBytes        = Game*
//   Game + kGamePlayerArrayBegin/End = 三名玩家的指针数组
//   每个玩家对象首字         = base + kEntityPlayerVtableOffset（`ValidatedEntityPlayer` 只认它）
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes[3];
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

static_assert(kEntityPlayerHeartsOffset + sizeof(std::uint32_t) <= kEntityPlayerSize,
              "hearts must live inside the Entity_Player object");
static_assert(kEntityPlayerTypeOffset + sizeof(std::uint32_t) <= kEntityPlayerSize,
              "player type must live inside the Entity_Player object");
static_assert(kEntityPlayerBoneHeartsOffset + sizeof(std::uint32_t) <= kEntityPlayerSize,
              "bone hearts must live inside the Entity_Player object");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

struct PlayerValues {
    std::uint32_t type;
    std::uint32_t hearts;
    std::uint32_t containers;
    std::uint32_t bone;
};

void PublishFakeGame(const PlayerValues (&values)[3]) {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    g_PlayerArrayBytes.assign(3 * sizeof(std::uint64_t), 0);
    for (int index = 0; index < 3; ++index) {
        std::vector<unsigned char>& player = g_PlayerBytes[index];
        player.assign(kEntityPlayerSize, 0);
        WriteAt<std::uint64_t>(player, 0, g_EngineBase + kEntityPlayerVtableOffset);
        WriteAt<std::uint32_t>(player, kEntityTypeOffset, kEntityTypePlayer);
        WriteAt<std::uint32_t>(player, kEntityPlayerTypeOffset, values[index].type);
        WriteAt<std::uint32_t>(player, kEntityPlayerIndexOffset,
                               static_cast<std::uint32_t>(index));
        WriteAt<std::uint32_t>(player, kEntityPlayerHeartsOffset, values[index].hearts);
        WriteAt<std::uint32_t>(player, kEntityPlayerRedHeartContainersOffset,
                               values[index].containers);
        WriteAt<std::uint32_t>(player, kEntityPlayerBoneHeartsOffset, values[index].bone);
        WriteAt<std::uint64_t>(g_PlayerArrayBytes, index * sizeof(std::uint64_t),
                               AddressOf(player));
    }
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayBeginOffset, AddressOf(g_PlayerArrayBytes));
    WriteAt<std::uint64_t>(g_GameBytes, kGamePlayerArrayEndOffset,
                           AddressOf(g_PlayerArrayBytes) + 3 * sizeof(std::uint64_t));

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

    PlayerValues players[3] = {COUNT_VALUES};
    if (std::strcmp(scenario, "counts") == 0) {
        // 默认（与 Python 侧的 `PLAYERS` 一致）。
    } else if (std::strcmp(scenario, "zero") == 0) {
        const PlayerValues zero[3] = {ZERO_VALUES};
        for (int index = 0; index < 3; ++index) players[index] = zero[index];
    } else {
        return 91;
    }

    PublishFakeGame(players);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local p0 = Isaac.GetPlayer(0)"
        " local p1 = Isaac.GetPlayer(1)"
        " local p2 = Isaac.GetPlayer(2)"
        " print('B299 types=' .. tostring(p0:GetPlayerType()) .. ',' .. tostring(p1:GetPlayerType()))"
        // 顺带证明「有效上限」那条既有 API 没被这次重构弄坏
        " print('B299 max0=' .. tostring(p0:GetEffectiveMaxHearts()))"
        " print('B299 kind=' .. type(p0:HasFullHearts()))"
        // ★★ 两名字段完全相同的玩家、只有类型不同 ⇒ 答案必须不同
        " print('B299 samefields=' .. tostring(p0:HasFullHearts()) .. ','"
        "   .. tostring(p1:HasFullHearts()))"
        " print('B299 full=' .. tostring(p2:HasFullHearts()))"
        " print('B299 arity=' .. ok(function() return p0:HasFullHearts(1) end))"
        " print('B299 arityerr=' .. err(function() return p0:HasFullHearts(1) end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b299.lua");
    static_cast<void>(result);
    return 0;
}'''
HARNESS = (HARNESS.replace("COUNT_VALUES", _cpp_players(PLAYERS))
                  .replace("ZERO_VALUES", _cpp_players(PLAYERS_ZERO)))


class HasFullHeartsBatch299Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b299-")
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

    def test_the_player_type_branch_actually_decides(self):
        """★★ **两名字段完全相同、只有玩家类型不同的玩家必须给出不同答案。**

        `p0 = (type 0, 红容器 4 + 骨心 2, 当前红心 7)` ⇒ 上限 8 ⇒ **false**；
        `p1 = (type 4, 同样的 4/2/7)` ⇒ 骨心不计 ⇒ 上限 4 ⇒ **true**。
        ★ 漏掉类型分支（一律把骨心算进去）时 p1 会变成 false，这条断言立刻红。
        """
        out = self.run_scenario("counts")
        self.assertIn("B299 types=0,4", out)
        self.assertIn("B299 samefields=false,true", out)

    def test_reaching_the_effective_maximum_is_true(self):
        """恰好够到上限 ⇒ `true`（PC 用 `setge` 做**有符号**比较，相等即真）。"""
        out = self.run_scenario("counts")
        self.assertIn("B299 full=true", out)

    def test_all_zero_is_true_and_the_result_is_boolean(self):
        """全零 ⇒ `0 >= 0` ⇒ **true**；且返回值恒为 `boolean`。"""
        out = self.run_scenario("zero")
        self.assertIn("B299 samefields=true,true", out)
        self.assertIn("B299 full=true", out)
        self.assertIn("B299 kind=boolean", out)

    def test_the_shared_max_hearts_helper_still_works(self):
        """本批把"有效上限"那段抽成了共享函数 —— 既有的 `GetEffectiveMaxHearts()` 必须没被弄坏。

        `p0`：容器 4 + 2×骨心 2 = **8**。
        """
        out = self.run_scenario("counts")
        self.assertIn("B299 max0=8", out)

    def test_argument_gate_is_exactly_zero(self):
        """0 参方法多给实参必须报错。"""
        out = self.run_scenario("counts")
        self.assertIn("B299 arity=false", out)
        self.assertIn("EntityPlayer:HasFullHearts accepts no arguments", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 前置声明 / 共享判据（判据只有一份）。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        self.assertIn(
            f'MakeId(ApiDomain::Isaac, 1, 0x{API_INDEX:04X}), ApiDomain::Isaac, "EntityPlayer", '
            f'"HasFullHearts"', catalog)
        self.assertRegex(isaac, rf"\{{\s*(?i:0x0E01{API_INDEX:04x}),\s*&EntityPlayerHasFullHearts\}}")
        self.assertIn("int EntityPlayerHasFullHearts(lua_State* state);", isaac)
        self.assertIn("int EntityPlayerHasFullHearts(lua_State* state) {", isaac)

        #: ★ "判据只有一份"：两条 API 共用同一个 helper，谁都不许自己再抄一遍掩码逻辑。
        #: ★ 数的是**代码行**：注释里当然会反复提到这个名字（批 298 就在这上面踩过一次）。
        def code_only(text: str) -> str:
            return "\n".join(re.sub(r"//.*$", "", line) for line in text.splitlines())

        self.assertEqual(code_only(isaac).count("kEntityPlayerBoneHeartlessTypeMask"), 1,
                         "掩码只应在共享的 ReadEffectiveMaxHearts 里出现一次（注释不计）")
        self.assertIn("bool ReadEffectiveMaxHearts(std::uintptr_t entity, std::int64_t* value)",
                      isaac)
        #: 既要被 `GetEffectiveMaxHearts` 用、也要被 `HasFullHearts` 用。
        self.assertEqual(isaac.count("ReadEffectiveMaxHearts("), 3,
                         "应有 1 处定义 + 2 处调用（GetEffectiveMaxHearts / HasFullHearts）")

        #: 四个字段读的都是**既有常量**（本批零新增偏移）。
        for name in ("kEntityPlayerHeartsOffset", "kEntityPlayerRedHeartContainersOffset",
                     "kEntityPlayerBoneHeartsOffset", "kEntityPlayerTypeOffset"):
            with self.subTest(constant=name):
                self.assertIn(f"inline constexpr uintptr_t {name} =", constants)
                self.assertIn(name, isaac, f"{name} 没有被用到")


if __name__ == "__main__":
    unittest.main()
