"""门禁：批次 340（2026-10-04）—— `Game:Spawn(...)` 与 `Isaac.Spawn(...)`（各 1 处）。

## 这一批是什么

两条都是**引擎真身逐字存在、但必须手写**的：

| API | 契约 | 引擎 | 为什么不能走数据行 |
| --- | --- | --- | --- |
| `Game:Spawn(Type, Variant, Position, Velocity, Spawner, SubType, Seed)` | `Game.md:520`（7 格、无缺省） | `Game::SpawnEx` @ `0x3540D0`（8 格） | 第 8 格**走栈** |
| `Isaac.Spawn(type, variant, subtype, position, velocity, Spawner)` | `Isaac.md:621`（6 格） | 同一个 `SpawnEx` | 同上 + 形参序不同 + 随机种子 |

★★★ **本批最重要的发现**：`Game::SpawnEx` 的**第 8 个形参在栈上**
（入口第一条 `ldr w8,[x29,#0x60]`），而通用跳板只填 `x0..x7`/`d0..d7`、**填不了栈**
⇒ 这条**不能用数据行**。手写时由编译器按编译期签名把它放到栈上 ✓。
⇒ **这是本项目第一个"参数上栈"的引擎调用**，也是"什么时候必须手写"的又一条硬判据。

## 判据

* 两条各自的**实参个数**（`Game:Spawn` = 7、`Isaac.Spawn` = 6）与**类型闸门**；
* `Isaac.Spawn` 的**随机种子**：宿主里 `EngineRandomU32()` 取不到 ⇒ 返回 0 ⇒ **必须兜底成 1**
  （契约警告种子 0 会崩游戏）；这一支在宿主里必然走到；
* **拿不到 `Game` / 入口字对不上** ⇒ 不调引擎、不报错、压 `nil`。
* ★ 两个 API 是**两个不同的处理器**（形参序不同，不能共用一条绑定行）。

★ 没验到的（真机项，作业单第九节）：真机上真的生成了那个实体、`Isaac.Spawn` 的随机种子不是 0。
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
CONSTANTS = ROOT / "runtime" / "source" / "runtime_constants.hpp"
ISAAC_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "isaac_api.cpp"
GAME_API = ROOT / "runtime" / "src" / "interfaces" / "lua" / "game_api.cpp"
CATALOG = ROOT / "runtime" / "src" / "interfaces" / "lua" / "api_catalog.cpp"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// 伪造的引擎内存：只要一条能解析出 `Game*` 的链（`Game:Spawn`/`Isaac.Spawn` 的接收者
// 都来自 `FieldReceipt::Level` = 全局 `g_Game` 槽）。
// ★ **故意不种 `kGameSpawnExEntryWord`** —— 本批走 `AsFunction`（直接按签名调），
//   种了入口字就会跳进伪造块 ⇒ 用例只跑"降级 + 参数闸门"。
namespace {

std::vector<unsigned char> g_ModuleBytes;
std::vector<unsigned char> g_GameBytes;
std::vector<unsigned char> g_OwnerSlotBytes;
std::uintptr_t g_EngineBase = 0;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeWorld() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_GameBytes.assign(0x100, 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    g_EngineBase = AddressOf(g_ModuleBytes);
    WriteAt<std::uint64_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uint64_t>(g_OwnerSlotBytes, 0, AddressOf(g_GameBytes));
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
}

}  // namespace

GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = nullptr;
    return GameRoomObservation::GameNull;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    const bool known = std::strcmp(scenario, "game_degrade") == 0 ||
                       std::strcmp(scenario, "game_badcount") == 0 ||
                       std::strcmp(scenario, "game_badvec") == 0 ||
                       std::strcmp(scenario, "isaac_degrade") == 0 ||
                       std::strcmp(scenario, "isaac_badcount") == 0 ||
                       std::strcmp(scenario, "isaac_badvec") == 0;
    if (!known) return 91;
    PublishFakeWorld();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    std::string script =
        "local function ok(f) return tostring(select(1, pcall(f))) end\n"
        "local function err(f) return tostring(select(2, pcall(f))) end\n"
        "local g = Game()\n"
        "print('B340 g=' .. type(g) .. ' fn=' .. type(g and g.Spawn)"
        " .. ' ifn=' .. type(Isaac.Spawn))\n";
    if (std::strcmp(scenario, "game_degrade") == 0) {
        // ★ 语料写法（`BOIStageAPI15/.../taintedkeepercoins.lua:63`）：7 个实参。
        script +=
            "local good, value = pcall(function()\n"
            "  return g:Spawn(5, 100, Vector(1,2), Vector(0,0), nil, 0, 12345)\n"
            "end)\n"
            "print('B340 ok=' .. tostring(good))\n"
            "print('B340 value=' .. tostring(value))\n";
    } else if (std::strcmp(scenario, "game_badcount") == 0) {
        script +=
            "print('B340 ok=' .. ok(function() return g:Spawn(5, 100, Vector(1,2), Vector(0,0), nil, 0) end))\n"
            "print('B340 msg=' .. err(function() return g:Spawn(5, 100, Vector(1,2), Vector(0,0), nil, 0) end))\n";
    } else if (std::strcmp(scenario, "game_badvec") == 0) {
        script +=
            "print('B340 ok=' .. ok(function() return g:Spawn(5, 100, 1, Vector(0,0), nil, 0, 1) end))\n"
            "print('B340 msg=' .. err(function() return g:Spawn(5, 100, 1, Vector(0,0), nil, 0, 1) end))\n";
    } else if (std::strcmp(scenario, "isaac_degrade") == 0) {
        // ★ 语料写法（`RepentancePlus/main.lua:610`）：6 个实参。
        script +=
            "local good, value = pcall(function()\n"
            "  return Isaac.Spawn(5, 350, 0, Vector(1,2), Vector(0,0), nil)\n"
            "end)\n"
            "print('B340 ok=' .. tostring(good))\n"
            "print('B340 value=' .. tostring(value))\n";
    } else if (std::strcmp(scenario, "isaac_badcount") == 0) {
        script +=
            "print('B340 ok=' .. ok(function() return Isaac.Spawn(5, 350, 0, Vector(1,2), Vector(0,0)) end))\n"
            "print('B340 msg=' .. err(function() return Isaac.Spawn(5, 350, 0, Vector(1,2), Vector(0,0)) end))\n";
    } else {
        script +=
            "print('B340 ok=' .. ok(function() return Isaac.Spawn(5, 350, 0, 1, Vector(0,0), nil) end))\n"
            "print('B340 msg=' .. err(function() return Isaac.Spawn(5, 350, 0, 1, Vector(0,0), nil) end))\n";
    }

    const char* text = script.c_str();
    const auto result = LuaRuntime::InitializeFromBuffer(text, std::strlen(text), "@b340.lua");
    static_cast<void>(result);
    return 0;
}
'''


class SpawnBatch340Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b340-")
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
        return result.stdout + result.stderr

    @staticmethod
    def value(out, label):
        match = re.search(rf"^{re.escape(label)}=(\S+)$", out, re.M)
        if match is None:
            raise AssertionError(f"输出里没有 {label} 那一行：\n{out}")
        return match.group(1)

    # ---------------------------------------------------------------- 行为（宿主）

    def test_game_spawn_degrades_without_erroring(self):
        """★ 语料那种 7 参写法：入口字对不上 ⇒ 不调引擎、不报错，返回值是 `nil`。"""
        out = self.run_scenario("game_degrade")
        self.assertIn("B340 g=userdata", out)
        self.assertIn("fn=function", out)
        self.assertIn("B340 ok=true", out)
        self.assertEqual(self.value(out, "B340 value"), "nil", out)

    def test_isaac_spawn_degrades_without_erroring(self):
        """★ 语料那种 6 参写法（含随机种子那一支 ⇒ 宿主里必然走"兜底成 1"）。"""
        out = self.run_scenario("isaac_degrade")
        self.assertIn("B340 ok=true", out)
        self.assertEqual(self.value(out, "B340 value"), "nil", out)

    def test_argument_count_and_type_gates(self):
        game_count = self.run_scenario("game_badcount")
        self.assertIn("B340 ok=false", game_count)
        self.assertIn("Game:Spawn expects a type, a variant, a position, a velocity", game_count)
        isaac_count = self.run_scenario("isaac_badcount")
        self.assertIn("B340 ok=false", isaac_count)
        self.assertIn("Isaac.Spawn expects an entity type, a variant, a sub type", isaac_count)
        game_vec = self.run_scenario("game_badvec")
        self.assertIn("B340 ok=false", game_vec)
        self.assertIn("Game:Spawn expects a position vector", game_vec)
        isaac_vec = self.run_scenario("isaac_badvec")
        self.assertIn("B340 ok=false", isaac_vec)
        self.assertIn("Isaac.Spawn expects a position vector", isaac_vec)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """两个常量 + ★ **两条独立的处理器与绑定行**（形参序不同，不能共用）。"""
        constants = CONSTANTS.read_text(encoding="utf-8")
        source = ISAAC_API.read_text(encoding="utf-8")
        game = GAME_API.read_text(encoding="utf-8")
        catalog = CATALOG.read_text(encoding="utf-8")

        self.assertIn("kGameSpawnExOffset = 0x3540D0", constants)
        self.assertIn("kGameSpawnExEntryWord = 0xD10283FFu", constants)
        self.assertIn("int GameSpawn(lua_State* state)", source)
        self.assertIn("int IsaacSpawn(lua_State* state)", source)
        #: ★ 共用一份实现（`SpawnEntityCommon`）+ 两个入口。
        self.assertIn("int SpawnEntityCommon(", source)
        #: ★ `Isaac.Spawn` 的种子必须现取且兜底成 1。
        self.assertIn("EngineRandomU32()", source)
        self.assertIn("seed = 1;", source)
        self.assertRegex(game, r"\{0x02010017, &GameSpawn\},")
        self.assertRegex(source, r"\{0x0E0100EC, &IsaacSpawn\},")
        self.assertRegex(catalog, r"MakeId\(ApiDomain::Game, 1, 0x0017\).*\"Game\", \"Spawn\"")
        self.assertRegex(catalog, r"MakeId\(ApiDomain::Isaac, 1, 0x00EC\).*\"Isaac\", \"Spawn\"")
        #: ★ `EngineRandomU32` 的声明必须提到头文件里（跨 TU）。
        header = (ROOT / "runtime" / "src" / "interfaces" / "lua" / "remaining_api.hpp").read_text(
            encoding="utf-8")
        self.assertIn("EngineRandomU32() noexcept;", header)


if __name__ == "__main__":
    unittest.main()
