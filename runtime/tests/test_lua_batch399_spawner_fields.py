"""门禁：批次 399（2026-10-07）—— `Entity.SpawnerEntity` / `SpawnerType` / `SpawnerVariant` 三个字段。

## 这一批是什么

| 字段 | 契约 | 引擎侧 | 机制 | 语料 |
| --- | --- | --- | --- | --- |
| `Entity.SpawnerEntity` | `tools/pc_contract_docs/Entity.md:824`（`data-altreturn='nil'`） | 裸 `Entity*` @ `Entity + 0x3A8` | `PushEntityField` 的裸指针分支（与 `Parent` 同形） | `Trinity/main.lua:129` |
| `Entity.SpawnerType` | `Entity.md:829` | u32 @ `+0x44` | `kEntityIntegerFields` 静态表（0 字节代码） | — |
| `Entity.SpawnerVariant` | `Entity.md:834` | u32 @ `+0x48` | 同上 | — |

**为什么必须有它**：语料模组 `Trinity` 给 Peter 角色写的"红眼泪"效果是
`local player = tear.SpawnerEntity:ToPlayer()`（`analysis/mod-corpus/Trinity/main.lua:129`）。
`SpawnerEntity` 那一格我们从来没对外开 ⇒ Lua 拿到 `nil` ⇒ 链式取值抛
`attempt to index a nil value (field 'SpawnerEntity')` ⇒ 派发器**静默摘掉整条
`MC_POST_FIRE_TEAR` 登记**（真机错误环逐字：`dist/gdb-read-20261007-2045-char-error.txt`）。

偏移的取证（批次 268 已给 `0x3A8`，本批补 `0x44`/`0x48`）全文见 `runtime_constants.hpp` 批次 399 段：
* `SpawnerEntity`：`Entity::GetLastSpawner @ 0x58C10`（`ldr x0,[x0,#0x3a8]` + `cbnz`）、
  `EntityList::CountSpawned @ 0x7A1CC`、写入方 `Entity::SetSpawnerEntity @ 0x59638`。
* `SpawnerType` / `SpawnerVariant`：`Entity_NPC::query_npcs_spawnertype @ 0x11FE60`
  （`ldr w8,[x24,#0x44]` 与形参 `SpawnerType` 比较）+ `Game::Spawn @ 0x3540D0`
  （`ldr w8,[x24,#0x38]→str w8,[x22,#0x44]`、`ldr w8,[x24,#0x3c]→str w8,[x22,#0x48]`）。

## 宿主验到了什么、没验到什么

* **验到（真值）**：三个字段读的就是我们伪造的那块内存 ——
  `SpawnerEntity` 交出的句柄再读 `.Type` 得到的是**被指对象自己** `+0x38` 的值（证明指针真的解了）；
  `SpawnerType` / `SpawnerVariant` 写什么读回什么，且两格**互不串位**（两只格摆不同值）。
* **验到（nil 分支）**：`+0x3A8` 为 0 ⇒ `SpawnerEntity` 必须给 **`nil`**（PC 的 `data-altreturn='nil'`），
  ★ 同时 `SpawnerType` / `SpawnerVariant` 在那种情形下仍是**数字 0**（不是 `nil`）——
  它们是 u32、PC 的 getter 无条件返回整数。
* **没验到**：真机上引擎是不是真这么填 ⇒ 真机项（让用户选 Peter 打一枪，错误环为空）。
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
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"

#: 伪造对象里摆的值 —— 处处不同，任何"读错格 / 读错对象"都会让至少一条断言翻转。
PLAYER_SPAWNER_TYPE = 111          # 玩家 + 0x44
PLAYER_SPAWNER_VARIANT = 222       # 玩家 + 0x48
SPAWNER_OBJ_TYPE = 9               # 被指对象（生成者）自己的 + 0x38
SPAWNER_OBJ_VARIANT = 7            # 被指对象自己的 + 0x3C


HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（形状与批次 288/293 的用例同源）：
//   模块块[base + kGameOwnerGlobalSlotOffset] = &g_OwnerSlotBytes
//   g_OwnerSlotBytes                         = Game*
//   Game + kGamePlayerArrayBegin/End         = 只有一个元素的玩家指针数组
//   玩家对象首字                              = base + kEntityPlayerVtableOffset（`IsEntityPlayer` 要它）
//   玩家对象 + kEntitySpawnerEntityOffset     = g_SpawnerBytes（本批的核心那格）
//   玩家对象 + kEntitySpawnerType/Variant     = 111 / 222
//   g_SpawnerBytes 首字                        = base + kEntityTearVtableOffset（一个"眼泪"实体）
//   g_SpawnerBytes + Type/Variant             = 9 / 7（用来验"句柄真的解到了那个对象"）
//
// ★ 三个字段都没有入口指纹、读的就是这块内存 ⇒ **真值可验**。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::vector<unsigned char> g_PlayerArrayBytes;
std::vector<unsigned char> g_PlayerBytes;
std::vector<unsigned char> g_SpawnerBytes;
std::uintptr_t g_EngineBase = 0;

static_assert(kEntitySpawnerEntityOffset < kEntityPlayerSize,
              "the spawner pointer must live inside the Entity_Player object");
static_assert(kEntitySpawnerTypeOffset < kEntityPlayerSize,
              "SpawnerType must live inside the Entity_Player object");
static_assert(kEntitySpawnerVariantOffset < kEntityPlayerSize,
              "SpawnerVariant must live inside the Entity_Player object");
//: ★ `+0x44`(SpawnerType) 必须**紧跟在** `+0x40`(SubType) 之后、`+0x48`(SpawnerVariant) 之前，
//:   与 PC 的 own `0x28/0x2C/0x30` + spawner `0x34/0x38` 那一串同构（间距都是 +4）。
static_assert(kEntitySpawnerTypeOffset == kEntitySubTypeOffset + 4,
              "SpawnerType must sit immediately after SubType");
static_assert(kEntitySpawnerVariantOffset == kEntitySpawnerTypeOffset + 4,
              "SpawnerVariant must sit immediately after SpawnerType");

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

//: 先把各块分配好（`SpawnerEntity` 那一格先写 0 = "没有生成者"），
//: 需要"有生成者"时调用方再直接把 `g_SpawnerBytes` 的地址写进那一格。
void PublishFakeGame(std::uint32_t spawnerType, std::uint32_t spawnerVariant) {
    // ★ 盖住本批用到的最大引擎偏移（`EngineEntryWordMatches` 对地址是裸 `memcpy`）。
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(kGamePlayerArrayEndOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);

    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));

    //: "生成者"对象（一个"眼泪"实体）：own `Type`/`Variant` 摆成 9 / 7。
    g_SpawnerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_SpawnerBytes, 0, g_EngineBase + kEntityTearVtableOffset);
    WriteAt<std::uint32_t>(g_SpawnerBytes, kEntityTypeOffset, SPAWNER_OBJ_TYPE);
    WriteAt<std::uint32_t>(g_SpawnerBytes, kEntityVariantOffset, SPAWNER_OBJ_VARIANT);

    g_PlayerBytes.assign(kEntityPlayerSize, 0);
    WriteAt<std::uint64_t>(g_PlayerBytes, 0, g_EngineBase + kEntityPlayerVtableOffset);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntityTypeOffset, kEntityTypePlayer);
    WriteAt<std::uint64_t>(g_PlayerBytes, kEntitySpawnerEntityOffset, 0);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntitySpawnerTypeOffset, spawnerType);
    WriteAt<std::uint32_t>(g_PlayerBytes, kEntitySpawnerVariantOffset, spawnerVariant);

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

    std::uint32_t spawnerType = SPAWNER_TYPE;
    std::uint32_t spawnerVariant = SPAWNER_VARIANT;
    bool withSpawner = false;
    if (std::strcmp(scenario, "withspawner") == 0) {
        withSpawner = true;
    } else if (std::strcmp(scenario, "nospawner") == 0) {
        withSpawner = false;
    } else if (std::strcmp(scenario, "zeroed") == 0) {
        spawnerType = 0;
        spawnerVariant = 0;
    } else {
        return 91;
    }

    PublishFakeGame(spawnerType, spawnerVariant);
    if (withSpawner) {
        WriteAt<std::uint64_t>(g_PlayerBytes, kEntitySpawnerEntityOffset, AddressOf(g_SpawnerBytes));
    }
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local p = Isaac.GetPlayer(0)"
        " print('B399 pkind=' .. type(p))"
        " local s = p.SpawnerEntity"
        " print('B399 skind=' .. type(s))"
        " print('B399 snil=' .. tostring(s == nil))"
        " print('B399 stype=' .. tostring(p.SpawnerType))"
        " print('B399 svariant=' .. tostring(p.SpawnerVariant))"
        // 句柄真的解到了"被指对象"：它的 own `Type`/`Variant` 是我们给那个对象摆的值。
        " print('B399 sobjtype=' .. tostring(s and s.Type))"
        " print('B399 sobjvariant=' .. tostring(s and s.Variant))"
        // ★ 反回归：这一格必须是**数字**、不是句柄（`SpawnerType` 与 `SpawnerEntity` 不许串位）。
        " print('B399 stypenum=' .. tostring(type(p.SpawnerType) == 'number'))"
        " print('B399 svariantnum=' .. tostring(type(p.SpawnerVariant) == 'number'))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b399.lua");
    static_cast<void>(result);
    return 0;
}
'''


class Batch399SpawnerFieldsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b399-")
        source = HARNESS
        #: ★ 顺序无关：`SPAWNER_TYPE` 不是 `SPAWNER_OBJ_TYPE` 的子串（`SPAWNER_T` ≠ `SPAWNER_O`），
        #:   两边互不误伤。
        source = source.replace("SPAWNER_TYPE", repr(PLAYER_SPAWNER_TYPE))
        source = source.replace("SPAWNER_VARIANT", repr(PLAYER_SPAWNER_VARIANT))
        source = source.replace("SPAWNER_OBJ_TYPE", repr(SPAWNER_OBJ_TYPE))
        source = source.replace("SPAWNER_OBJ_VARIANT", repr(SPAWNER_OBJ_VARIANT))
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=source,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario):
        result = subprocess.run([str(self.binary), scenario], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主 · 真值）

    def test_spawner_entity_and_type_variant_read_the_real_cells(self):
        """★ 三个字段读的就是伪造对象上的那三格，而且 `SpawnerEntity` 真的解到了被指对象。

        判据为什么硬：
        * `SpawnerEntity` 若没开 ⇒ `p.SpawnerEntity` 是 `nil`（`skind=nil`）；
        * 指针偏移写错（指到别的格）⇒ `sobjtype` / `sobjvariant` 不会是 9 / 7；
        * `SpawnerType`/`SpawnerVariant` 偏移互换 ⇒ 111/222 对调、下面会红；
        * 把 `SpawnerType` 误接到 `SpawnerEntity` 的裸指针分支 ⇒ 类型变 `userdata`、`stypenum=false`。
        """
        out = self.run_scenario("withspawner")
        self.assertIn("B399 pkind=userdata", out)
        self.assertIn("B399 skind=userdata", out)
        self.assertIn("B399 snil=false", out)
        self.assertIn(f"B399 stype={PLAYER_SPAWNER_TYPE}", out)
        self.assertIn(f"B399 svariant={PLAYER_SPAWNER_VARIANT}", out)
        #: 被指对象（"生成者"）自己的 `Type`/`Variant` —— 证明句柄解到了对的那个对象。
        self.assertIn(f"B399 sobjtype={SPAWNER_OBJ_TYPE}", out)
        self.assertIn(f"B399 sobjvariant={SPAWNER_OBJ_VARIANT}", out)
        self.assertIn("B399 stypenum=true", out)
        self.assertIn("B399 svariantnum=true", out)

    def test_missing_spawner_is_nil_but_type_and_variant_are_zero(self):
        """★ 指针为 0 ⇒ `SpawnerEntity` = **`nil`**（PC 契约 `data-altreturn='nil'`）；
        但 `SpawnerType`/`SpawnerVariant` 仍是**数字 0**（它们是 u32 字段、PC 的 getter 无条件返回整数）。

        `Trinity` 那类写法 `tear.SpawnerEntity:ToPlayer()` 在有生成者时才有意义；
        PC 上"没有生成者"就是 `nil`，我们给了空壳句柄会让模组的 `== nil` 判断失效。
        """
        out = self.run_scenario("nospawner")
        self.assertIn("B399 snil=true", out)
        self.assertIn(f"B399 stype={PLAYER_SPAWNER_TYPE}", out)
        self.assertIn("B399 stypenum=true", out)
        self.assertIn("B399 svariantnum=true", out)

    def test_zero_type_and_variant_are_numbers_not_nil(self):
        """全 0 的一对 spawner 字段 ⇒ 回 `0`（**是数字**，不是 `nil`）。

        这一场钉"0 不等于没有"：若实现把 0 当"没有"压成 `nil`，模组里
        `if e.SpawnerType == 0 then` 那一支会静默失效。
        """
        out = self.run_scenario("zeroed")
        self.assertIn("B399 stype=0", out)
        self.assertIn("B399 svariant=0", out)
        self.assertIn("B399 stypenum=true", out)
        self.assertIn("B399 svariantnum=true", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """偏移常量 / 字段表条目 / 裸指针分支 / 编译期顺序断言。"""
        api = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        self.assertIn("inline constexpr uintptr_t kEntitySpawnerTypeOffset = 0x44;", constants)
        self.assertIn("inline constexpr uintptr_t kEntitySpawnerVariantOffset = 0x48;", constants)
        self.assertIn("inline constexpr uintptr_t kEntitySpawnerEntityOffset = 0x3A8;", constants)

        #: 两个 u32 走 `kEntityIntegerFields` 静态表（0 字节代码）。
        self.assertIn('{"SpawnerType", kEntitySpawnerTypeOffset, false},', api)
        self.assertIn('{"SpawnerVariant", kEntitySpawnerVariantOffset, false},', api)
        #: `SpawnerEntity` 走裸指针分支（与 `Parent` 同形），nil 分支必须在。
        self.assertIn('std::strcmp(field, "SpawnerEntity") == 0', api)
        self.assertRegex(
            api,
            r"std::strcmp\(field, \"SpawnerEntity\"\) == 0\)\s*\{[\s\S]{0,400}?"
            r"spawner == 0\)\s*\{\s*lua_pushnil\(state\);\s*return true;\s*\}",
            "SpawnerEntity 的 nil 分支缺失（指针为 0 时必须给 nil）")

        #: 证据链必须留在常量段（别人复核时不用重新反汇编）。
        for needle in ("0x11FE60", "0x3540D0", "0x58C10", "0x59638", "0x3A8", "0x44", "0x48",
                       "query_npcs_spawnertype", "Game::Spawn", "Entity.md:824",
                       "Entity.md:829", "Entity.md:834"):
            self.assertIn(needle, constants, f"证据 {needle} 没有写进常量段")


if __name__ == "__main__":
    unittest.main()
