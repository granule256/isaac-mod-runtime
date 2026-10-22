"""门禁：批次 345（2026-10-04）—— `Isaac.Explode(Vector pos, Entity source, float damage)`（5 处）。

## 这一批是什么

| API | 处数 | 机制 | Switch 落点 |
| --- | --- | --- | --- |
| `Isaac.Explode(pos, source, damage)` | **5** | **手写处理器**（9 个形参 ⇒ 第 9 格**走栈**；第 4 格是 16 字节**按值**的 `bitset128_t`） | `Game::BombExplosionEffects @ 0x355C68`（入口字 `0xD10443FF`） |

依据 = `docs/取证-L组-两条手写处理器的可执行规格-20261004d.md` **§A**（完整可执行规格；
上游 = F 组，独立复核 = N 组，★ N 组复核了 9 格落位 / `Bitset128` 全 0 / 末尾四常量）。
语料 = `RepentancePlus/main.lua:2242` 与 `IsaacOnTwitchReloaded/scripts/passiveItems.lua:183/184/185/187`
（**全是点号调用**，栈上没有 `self`）。

## 为什么必须手写（不是"懒得走数据行"）

* **9 个形参** ⇒ AAPCS64 下第 9 格 `bool` 落到**调用者的栈**上（序言 `ldrb w21,[x29,#0x60]`），
  而通用跳板只填 `x0..x7` / `d0..d7`、**填不了栈** ⇒ 必须用 `AsFunction<Fn>` 让编译器按签名放栈
  （与批次 340 的 `Game::SpawnEx` 同一条路）。
* 第 4 格是 **16 字节按值**的 `bitset128_t`（走 `x2:x3`，**不是** HFA）⇒ `Bitset128` 的类型定义
  必须让 `sizeof == 16` 且成员是整数，否则编译器会当 HFA、**静默错位**。

## 宿主验到了什么、没验到什么

* **验到**：`type(Isaac.Explode) == "function"`；四种参数闸门的**逐字消息**；
  正确调用（含 `source` 传 `nil` 与传真实体两种）在宿主里**入口字对不上** ⇒
  **不调引擎、不报错、返回 0 个值**（契约返回 `void`）。
* **没验到**：真机上「那一点真的生成了一次爆炸」（伤害/视觉）。
  ★ 宿主跳板把引擎返回值一律清零 ⇒ 「爆炸真的发生了」**只能真机**（作业单第九节）。
* ★ `Bitset128` 的 HFA 判断**只能在编译期自证一半**（`static_assert(sizeof == 16)` 在源码里，
  本文件用静态判据再钉一次）；「引擎有没有按 `x2:x3` 收到」**只能真机**。
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
SURFACE = ROOT / "runtime" / "tests" / "contract" / "test_engine_row_api_surface.py"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状抄批次 340/341 的用例）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                         = Game*
//   Game + 玩家数组 begin/end                 = 只有一个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset / Type = PLAYER
//
// ★ `Isaac.Explode` 在宿主里**入口字必然对不上**（模块块是零）⇒ 处理器走**静默降级** ——
//   这正是我们要验的那条路。★ 模块块**故意开得足够大**，盖住本批的引擎偏移：
//   不这么做就是一次越界读（`EngineEntryWordMatches` 对地址是裸 `memcpy`，没有边界判定）。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::uintptr_t g_EngineBase = 0;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeGame() {
    g_ModuleBytes.assign(kGameBombExplosionEffectsOffset + 16, 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);

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
    if (std::strcmp(scenario, "explode") != 0) {
        return 91;
    }

    PublishFakeGame();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);
    std::printf("B345 base=%d\n", g_EngineBase != 0 ? 1 : 0);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local function count(...) return select('#', ...) end"
        " print('B345 fn=' .. type(Isaac.Explode))"
        // source 传 nil（PC 允许）与传真实体（走实体句柄校验）两种都要放行。
        " print('B345 nilok=' .. ok(function() return Isaac.Explode(Vector(0, 0), nil, 30) end))"
        " print('B345 niln=' .. tostring(count(Isaac.Explode(Vector(0, 0), nil, 30))))"
        " local p = Isaac.GetPlayer(0)"
        " print('B345 entok=' .. ok(function() return Isaac.Explode(Vector(1, 2), p, 110) end))"
        " print('B345 entn=' .. tostring(count(Isaac.Explode(Vector(1, 2), p, 110))))"
        // --- 参数闸门（逐字消息）---------------------------------------------------
        " print('B345 none=' .. ok(function() return Isaac.Explode() end))"
        " print('B345 noneerr=' .. err(function() return Isaac.Explode() end))"
        " print('B345 two=' .. ok(function() return Isaac.Explode(Vector(0, 0), nil) end))"
        " print('B345 twoerr=' .. err(function() return Isaac.Explode(Vector(0, 0), nil) end))"
        " print('B345 badpos=' .. ok(function() return Isaac.Explode(1, nil, 30) end))"
        " print('B345 badposerr=' .. err(function() return Isaac.Explode(1, nil, 30) end))"
        " print('B345 badsrc=' .. ok(function() return Isaac.Explode(Vector(0, 0), 'x', 30) end))"
        " print('B345 badsrcerr=' .. err(function() return Isaac.Explode(Vector(0, 0), 'x', 30) end))"
        " print('B345 baddmg=' .. ok(function() return Isaac.Explode(Vector(0, 0), nil, 'x') end))"
        " print('B345 baddmgerr=' .. err(function() return Isaac.Explode(Vector(0, 0), nil, 'x') end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b345.lua");
    static_cast<void>(result);
    return 0;
}
'''


class Batch345ExplodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b345-")
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
        # ★ 批次 285 的教训：只回 stdout 时「Lua 报错」与「什么都没做」长得一样。
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_explode_is_wired_and_degrades_silently(self):
        """★ 挂上了 + `source` 传 `nil`/真实体都放行 + 宿主里静默降级（返回 0 个值）。

        宿主里 `EngineEntryWordMatches` 必然对不上（模块块是零）⇒
        **不调引擎、不报错、不压值**（契约返回 `void`）—— 这与 PC 的"这次没生效"同观感，
        而报错会把整条模组回调摘掉。
        """
        out = self.run_scenario("explode")
        self.assertIn("B345 base=1", out)
        self.assertIn("B345 fn=function", out)
        self.assertIn("B345 nilok=true", out)
        self.assertIn("B345 niln=0", out)
        self.assertIn("B345 entok=true", out)
        self.assertIn("B345 entn=0", out)

    def test_explode_argument_gates(self):
        """四种错法的报错消息**逐字**（与 PC 的"参数写错了"同类：都该报，而不是静默吞掉）。

        ① 实参数 ≠ 3；② 第 1 格不是 `Vector`；③ 第 2 格既非 `nil` 又解不成实体；
        ④ 第 3 格不是数值。★ 注意：`Isaac.Explode` 是**点号全局调用** ⇒ 栈上没有 `self`。
        """
        out = self.run_scenario("explode")
        self.assertIn("B345 none=false", out)
        self.assertIn("Isaac:Explode expects a position, a source entity and a damage number", out)
        self.assertIn("B345 two=false", out)
        self.assertIn("B345 badpos=false", out)
        self.assertIn("Isaac:Explode expects a position vector", out)
        self.assertIn("B345 badsrc=false", out)
        self.assertIn("Isaac:Explode expects a source entity", out)
        self.assertIn("B345 baddmg=false", out)
        self.assertIn("Isaac:Explode expects a number damage", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 处理器 / 两个常量 / `Bitset128` 的编译期自证 / 不是数据行。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        surface = SURFACE.read_text(encoding="utf-8")

        self.assertIn('MakeId(ApiDomain::Isaac, 1, 0x00F8), ApiDomain::Isaac, "Isaac", "Explode"',
                      catalog)
        self.assertIn("{0x0E0100F8, &IsaacExplode},", api)
        self.assertRegex(api, r"std::uintptr_t GameBombExplosionEffectsMethod\(\) noexcept")
        self.assertRegex(api, r"int IsaacExplode\(lua_State\* state\)")
        #: ★★ 反回归：它是**手写**（第 9 格走栈，跳板填不了），不许被塞进引擎方法行表。
        self.assertNotRegex(api, r"0x0E0100F8[^\n]*EngineCallShape")
        self.assertNotRegex(api, r"0x0E0100F8[^\n]*FieldKind::")
        self.assertNotIn('"Isaac:Explode"', surface)

        #: ★★ `Bitset128` 必须是 16 字节**非 HFA** 聚合体（否则编译器走 `d0..d3`、**静默错位**）。
        self.assertRegex(api, r"struct Bitset128 \{[\s\S]{0,160}?\};")
        self.assertIn('static_assert(sizeof(Bitset128) == 16', api)
        self.assertIn("std::uint64_t lo;", api)
        self.assertIn("std::uint64_t hi;", api)

        #: 末尾 4 格是**绑定常量**（照 PC 绑定逐字节）——写死在这里，防止有人"顺手改成 0"。
        self.assertIn("/*f=*/1.0F, /*b=*/true, /*ul=*/4UL, /*b2=*/false", api)
        #: `tearFlags` 是 PC 绑定的**全 0**。
        self.assertIn("const Bitset128 tearFlags{0, 0};", api)

        for needle in ("inline constexpr uintptr_t kGameBombExplosionEffectsOffset = 0x355C68;",
                       "inline constexpr std::uint32_t kGameBombExplosionEffectsEntryWord = "
                       "0xD10443FFu;"):
            self.assertIn(needle, constants, f"常量缺失：{needle}")

        #: ★ 契约页必须**在仓里**（台账引的是 `Isaac.md:112`）。
        self.assertTrue((ROOT / "tools" / "pc_contract_docs" / "Isaac.md").is_file())

    def test_the_load_bearing_evidence_is_recorded(self):
        """★★ 两条最容易做错的地方必须在常量段里写清依据（后人照做时按它走）。

        * **9 格落位 + 第 9 格走栈的偏移算法**（`x29 + 0x60`，与批次 340 的 `SpawnEx` 同一套）；
        * **`tearFlags` 全 0 的语义**（引擎把它当掩码与全局眼泪标志集合 `&`，全 0 ⇒ 无标志）；
        * **末尾 4 格确实被引擎消费**（不是死参）的证据。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        for needle in ("0x355C68", "0xD10443FF", "0x355CFC", "0x355D08", "0x355D74", "0x355D78",
                       "0x355D7C", "0x355D98", "TEAR_CROSS_BOMB", "0x80BB83", "0x80BB85",
                       "0x80BB87", "0x80BB8A", "x29 + 0x60", "Isaac.md"):
            self.assertIn(needle, constants, f"证据 {needle} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()
