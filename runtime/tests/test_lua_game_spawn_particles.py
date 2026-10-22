"""门禁：`Game:SpawnParticles`（批次 267，2026-10-02）。

## 这条为什么"必须手写"，而不是数据行

项目的第一选择是数据行（0 字节代码），但这一条不行：第 5 个参数是 **`ColorMod const&`** ——
它不是"把 Lua 值按某个标量宽度搬进寄存器"，而是**要先用 Lua 的 `Color` 句柄构造一个 44 字节的
引擎对象**（`kColorModSize = 0x2C`、tint@+0x00、shift@+0x10）。形状机制（`EngineCallShape`）
只能表达前者 ⇒ 只能手写处理器。

## 从反汇编读出来的两个易错点（`python3 tools/nro_disasm.py 0x3598F8 0xB0`）

1. **`Height` 走 `s1`**（不是 `s0`，`s0` 是 `Speed`）—— 证据 `00359938 mov v8.16b, v1.16b`
   与 `0035994c fcmp s1, s0`；
2. **引擎拿 `height == 100000.0f` 比一次决定分支**（`0x47c35000` 由 `0035992c/00359930`
   两条 `mov/movk` 拼出）⇒ 缺省值必须按契约原文给 `100000`，**不能图省事给 0**。

## 本文件钉什么、不钉什么

钉**接线与参数闸门**：目录行 / 绑定行 / 契约页:行 / 参数个数区间（4..7 个实参 + `self`）/
各参数的形状 / 缺省值（颜色全 1、高度 100000、亚型 0）/ `ColorMod` 的字段与尺寸 /
"颜色→ColorMod 的映射与 `sprite_api.cpp` 同源" / 以及降级时**什么都不做且不报错**。

★ **不钉值**：宿主没有引擎 ⇒ 证明不了"真的生成了粒子"、也证明不了颜色真的被引擎读对。
那要真机（见存档 README 的 V11）。
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
SPRITE_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "sprite_api.cpp"
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
COLOR_MOD = (ROOT / "runtime" / "src" / "interfaces" / "lua"
             / "engine_color_mod.hpp")

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_OwnerSlotBytes;

void PublishZeroedModule() {
    // 盖住 `kGameOwnerGlobalSlotOffset`（铺太小会越界读 ⇒ 宿主偶发 SIGSEGV，261 那批踩过）。
    // 槽里全 0 ⇒ `ResolveGame()` 拿不到 `Game*` ⇒ 必须走"什么都不做"那条路。
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + 16, 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(g_ModuleBytes.data()));
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
    PublishZeroedModule();
    LuaRuntime::SetGameBindings(reinterpret_cast<std::uintptr_t>(g_OwnerSlotBytes.data()), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "degrade") == 0) {
        // 六参（语料里最常见的形式）与四参（全靠缺省）都要能过且不报错、不返回值。
        // ★ 用 `pcall(f, args…)` 而不是 `pcall(function() … end)`：后者的内层函数**没有可变参数**，
        //   写 `...` 会直接编译错（Lua 报 "cannot use '...' outside a vararg function"），
        //   而那种错在夹具里表现为"整段脚本一行输出都没有"，很容易误判成引擎侧的问题。
        script =
            "local g = Game()"
            " local a, r1 = pcall(g.SpawnParticles, g, Vector(100, 200), 1, 2, 1.5,"
            "     Color(1, 0, 0, 1, 0.1, 0.1, 0.1), 0)"
            " local b, r2 = pcall(g.SpawnParticles, g, Vector(100, 200), 1, 2, 1.5)"
            " print('PART a='..tostring(a)..' ret='..tostring(r1)..' b='..tostring(b)"
            "   ..' ret2='..tostring(r2))";
    } else if (std::strcmp(scenario, "arity") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " local g = Game()"
            " print('PART arity='..ok(function() return g:SpawnParticles(Vector(1, 2), 1, 2) end)"
            "   ..','..ok(function() return g:SpawnParticles(Vector(1, 2), 1, 2, 1, Color(1,1,1,1), 0, 0, 0) end)"
            "   ..','..ok(function() return g:SpawnParticles(42, 1, 2, 1) end)"
            "   ..','..ok(function() return g:SpawnParticles(Vector(1, 2), Vector(1, 2), 2, 1) end)"
            "   ..','..ok(function() return g:SpawnParticles(Vector(1, 2), 1, 2, 1, 'x') end)"
            "   ..','..ok(function() return g:SpawnParticles(Vector(1, 2), 1, 2, 1, Color(1,1,1,1), 0, 'x') end))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@spawnparticles.lua");
    static_cast<void>(result);
    return 0;
}
'''


class GameSpawnParticlesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-particles-")
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
        return result.stdout

    # ---------------------------------------------------------------- 宿主行为

    def test_no_game_means_no_action_and_no_error(self):
        """拿不到 `Game*` ⇒ **什么都不做**：`pcall` 成功、**不返回值**（契约是 `void`）、不报错。

        ★ 这一格同时钉住"返回类型"：压了 `nil` 之外的任何值都会与契约的 `void` 不符。
        """
        out = self.run_scenario("degrade")
        self.assertIn("PART a=true ret=nil b=true ret2=nil", out)

    def test_argument_gates(self):
        """六格：少参数 / 多参数 / 位置不是 Vector / 变体给了 Vector / 颜色给了字符串 / 亚型给了字符串。

        前三格是"个数"（4..7 个实参 + `self`），后三格是"形状"。
        """
        out = self.run_scenario("arity")
        self.assertIn("PART arity=false,false,false,false,false,false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_row_and_binding_row_exist(self):
        self.assertIn(
            'MakeId(ApiDomain::Game, 1, 0x0014), ApiDomain::Game, "Game", "SpawnParticles"',
            CATALOG.read_text(encoding="utf-8"), "catalog 里没有 Game:SpawnParticles（0x0014）")
        self.assertRegex(GAME_API.read_text(encoding="utf-8"),
                         r"\{\s*(?i:0x02010014),\s*&GameSpawnParticles\s*\}",
                         "Game 手写绑定表里没有 0x02010014 → GameSpawnParticles")

    def test_contract_page_and_line_are_quoted(self):
        self.assertIn("Game.md:546", GAME_API.read_text(encoding="utf-8"),
                      "SpawnParticles 的实现处没有引用契约 Game.md:546")

    def test_it_is_a_handler_not_a_data_row(self):
        """★ 它**不能**走数据行（理由见文件头）⇒ 必须没有同 id 的引擎方法数据行。"""
        game = GAME_API.read_text(encoding="utf-8")
        rows = game[game.index("kGameEngineRows"):]
        rows = rows[:rows.index("\n};")]
        self.assertNotIn("0x02010014", rows,
                         "0x0014 出现在引擎方法数据行表里了：那会与手写处理器抢同一个 id")

    def test_abi_details_carry_their_evidence(self):
        """两个易错点（`Height` 走 `s1`、引擎拿它跟 100000 比）必须在注释与常量里留证。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        game = GAME_API.read_text(encoding="utf-8")
        for needle in ("kGameSpawnParticlesOffset = 0x3598F8",
                       "kGameSpawnParticlesEntryWord = 0xD102C3FFU"):
            with self.subTest(needle):
                self.assertIn(needle, constants, f"缺常量：{needle}")
        self.assertIn("s1", constants, "常量注释里必须写明 Height 走 s1")
        self.assertIn("0x47c35000", constants, "常量注释里必须留下 100000.0f 那两条 mov/movk")
        self.assertIn("100000.0F", game, "缺省高度必须是 100000（不是 0）")

    def test_color_mod_layout_lives_in_one_shared_header(self):
        """★ `ColorMod` 的字段/尺寸与"颜色 → ColorMod"的映射**只有一份**（批次 271 抽出去的）。

        原来那份住在 `GameSpawnParticles` 的**函数体里**；而 `Entity:SetColor` 的第一个参数
        是**同一个类型**（`ColorMod const&`）⇒ 再抄一份就是第三份拷贝
        （`sprite_api.cpp` 写 `Sprite.Color` 时还有一份同源的映射）。
        ⇒ 真值搬进 `engine_color_mod.hpp`，两个处理器都**转调**它。
        """
        game = GAME_API.read_text(encoding="utf-8")
        handler = game[game.index("\nint GameSpawnParticles(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        #: 处理器里**保留**的那行 static_assert：门禁钉的是"它确实在用那个被钉住尺寸的类型"。
        self.assertIn("static_assert(sizeof(EngineColorMod) == kColorModSize", handler,
                      "必须用 static_assert 把 ColorMod 的尺寸钉住（字段数写错要编译期就红）")
        self.assertIn("FillEngineColorMod(state, 6, &color)", handler,
                      "颜色那一步必须转调共享头里的映射（不许在这个处理器里再写一份）")
        self.assertIn("DefaultEngineColorMod()", handler,
                      "缺省颜色必须是共享头给的那份（契约的 Color.Default）")

        shared = COLOR_MOD.read_text(encoding="utf-8")
        self.assertIn("struct EngineColorMod {", shared)
        self.assertIn("static_assert(sizeof(EngineColorMod) == kColorModSize", shared)
        for field in ("handle.red", "handle.green", "handle.blue", "handle.alpha",
                      "handle.offsetRed", "handle.offsetGreen", "handle.offsetBlue"):
            with self.subTest(field=field):
                self.assertIn(field, shared, f"共享头的颜色映射缺 {field}")
        # 与 sprite 那一份同源：两边都把 tint 写成 R/G/B/A、shift 写成三个偏移分量。
        sprite = SPRITE_API.read_text(encoding="utf-8")
        for field in ("colorOffsetRed", "colorOffsetGreen", "colorOffsetBlue"):
            with self.subTest(sprite_field=field):
                self.assertIn(field, sprite, f"sprite_api 的映射变了？{field}")
        self.assertIn("kColorModTintOffset", sprite, "sprite_api 必须仍然写 tint 那一格")
        self.assertIn("kColorModShiftOffset", sprite, "sprite_api 必须仍然写 shift 那一格")

    def test_native_fallback_does_not_raise(self):
        """★ 降级不许抛 Lua 错误（批次 250 的口径）：三条前置条件任一不成立都只返回 `0`。"""
        game = GAME_API.read_text(encoding="utf-8")
        handler = game[game.index("\nint GameSpawnParticles(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        guard = re.search(r"if \(game == 0 \|\|.*?\) \{\s*return 0;", handler, re.S)
        self.assertIsNotNone(guard,
                             "降级分支必须同时检查 game 与入口指纹，并 `return 0`（不报错）")


if __name__ == "__main__":
    unittest.main()
