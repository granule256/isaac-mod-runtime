"""门禁：`Isaac.GetFreeNearPosition` / `Isaac.GridSpawn`（批次 262，2026-10-01）。

## 这两条为什么是"拼出来的"

工作清单把它们归在 `glue_compose`（"PC 在 Lua 胶水层实现"）。**做法不是照文档猜的** ——
是把 PC 的绑定函数反汇编出来看它到底调了什么（配方 `tools/pc_exe_binding.py`）：

* `Isaac.GetFreeNearPosition` 的绑定函数（`isaac-ng.exe` VA `0x80BB30`）最后一句是
  `call 0x7CF240`，而 `0x7CF240` 反查出来正是 **`Room::FindFreePickupSpawnPosition` 的绑定函数**
  ⇒ PC 的实现就是 `room:FindFreePickupSpawnPosition(pos, step, false, false)`（那条我们批次 259 刚做过）。
* `Isaac.GridSpawn`（VA `0x80B900`）：世界坐标算格下标（与 `Room::GetGridIndex` 同公式）→
  越界返回 0（nil）→ 那一格已有实体且 Type ∉ {1, 10} 且 `forced == false` 也返回 0 →
  否则 `seed = RandomU32()` 后调 `Room::SpawnGridEntity(index, type, variant, seed, 0)` →
  **最后再读一次那一格的实体指针当返回值**。

⇒ 两条都只用**我们已经有的**原语，不需要新引擎符号；唯一新登记的是一个随机源
（引擎自己的 `RandomU32()`，`kRandomU32Offset`）。

## 本文件钉什么、不钉什么

钉**接线与参数闸门**：目录行 / 绑定行 / 契约页:行 / 参数个数与类型 / "取不到房间时压 nil 与
零向量"这两种不同的降级口径 / 以及**"没有第二份格坐标换算"**这条（复用共享助手，
而不是把 `(x-40)/40+0.5` 再写一遍）。

★ **不钉值**：宿主没有引擎 ⇒ 证明不了"真的生成了那个网格实体"、也证明不了坐标换算的结果。
那要真机（见存档 README 的 V8/V9）。
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

#: `(名字, 域内序号, 契约页:行)`
APIS = (
    ("GetFreeNearPosition", 0x008B, "Isaac.md:263"),
    ("GridSpawn", 0x008C, "Isaac.md:472"),
)

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
    // 盖住 `kGameOwnerGlobalSlotOffset`（`Isaac.GetChallenge` 那批踩过的坑：铺太小 = 越界读
    // ⇒ 宿主偶发 SIGSEGV）。槽里全 0 ⇒ 拿不到 `Game`/`Room` ⇒ 两条都走降级。
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
        script =
            "local p, perr = pcall(function() return Isaac.GetFreeNearPosition(Vector(320, 280), 10) end)"
            " print('ICOMP free ok='..tostring(p)..' type='..type(perr))"
            " if type(perr) == 'userdata' then print('ICOMP free xy='..perr.X..','..perr.Y) end"
            " local g, gerr = pcall(function()"
            "     return Isaac.GridSpawn(GridEntityType and GridEntityType.GRID_PIT or 7, 0,"
            "                             Vector(320, 280), true) end)"
            " print('ICOMP grid ok='..tostring(g)..' value='..tostring(gerr))";
    } else if (std::strcmp(scenario, "arity") == 0) {
        script =
            "local function ok(f) return tostring(select(1, pcall(f))) end"
            " print('ICOMP arity='..ok(function() return Isaac.GetFreeNearPosition(Vector(1, 2)) end)"
            "   ..','..ok(function() return Isaac.GetFreeNearPosition(42, 1) end)"
            "   ..','..ok(function() return Isaac.GridSpawn(7, 0, Vector(1, 2)) end)"
            "   ..','..ok(function() return Isaac.GridSpawn(Vector(1, 2), 0, Vector(1, 2), true) end)"
            "   ..','..ok(function()"
            "       return Isaac.GridSpawn(7, 0, 'x', true) end))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@icompose.lua");
    static_cast<void>(result);
    return 0;
}
'''


class IsaacComposeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-icompose-")
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

    def test_two_different_degradations(self):
        """★ 两条的降级口径**故意不同**，这一格把差别钉住。

        * `GetFreeNearPosition` 返回 **`Vector`** ⇒ 拿不到房间时压 `Vector(0,0)`（不压 nil：
          模组会立刻 `pos.X`，抛错就摘掉整条回调）；
        * `GridSpawn` 返回 **`GridEntity`** ⇒ 拿不到房间时压 **`nil`**（PC 那边就是返回 0 ⇒ nil，
          语料也都写在 `if grid then` 里）。
        """
        out = self.run_scenario("degrade")
        self.assertIn("ICOMP free ok=true type=userdata", out)
        self.assertIn("ICOMP free xy=0.0,0.0", out)
        self.assertIn("ICOMP grid ok=true value=nil", out)

    def test_argument_gates(self):
        """参数个数与类型不对必须报错（模组写错了就该报错）。

        五格：`GetFreeNearPosition` 少一个 / 位置传数字；`GridSpawn` 少一个 /
        第 1 个位置传了 `Vector` 而不是整数 / 第 3 个位置（position）传了字符串。
        """
        out = self.run_scenario("arity")
        self.assertIn("ICOMP arity=false,false,false,false,false", out)

    # ---------------------------------------------------------------- 静态接线

    def test_catalog_rows_and_binding_rows_exist(self):
        catalog = CATALOG.read_text(encoding="utf-8")
        isaac = ISAAC_API.read_text(encoding="utf-8")
        for name, index, _page in APIS:
            with self.subTest(name):
                self.assertIn(
                    f'MakeId(ApiDomain::Isaac, 1, 0x{index:04X}), ApiDomain::Isaac, "Isaac", "{name}"',
                    catalog, f"catalog 里没有 Isaac:{name}（域内序号 0x{index:04x}）")
                self.assertRegex(
                    isaac, rf"\{{\s*(?i:0x{0x0E010000 + index:08x}),\s*&\w*{name}\s*\}}",
                    f"Isaac 绑定表里没有 0x{0x0E010000 + index:08X} → {name}")

    def test_handlers_live_where_the_room_primitives_are(self):
        """两条的**定义**必须在 `remaining_api.cpp`（格坐标换算与网格实体表都只在那里有一份）。"""
        source = REMAINING_API.read_text(encoding="utf-8")
        for name, _index, _page in APIS:
            with self.subTest(name):
                self.assertRegex(source, rf"\nint Isaac{name}\(lua_State\* state\) \{{",
                                 f"Isaac{name} 的处理器定义体不在 remaining_api.cpp")

    def test_contract_page_and_line_are_quoted_in_the_implementation(self):
        source = REMAINING_API.read_text(encoding="utf-8")
        for name, _index, page in APIS:
            with self.subTest(name):
                self.assertIn(page, source, f"{name} 的实现处没有引用契约 {page}")

    def test_grid_spawn_reuses_the_single_grid_index_conversion(self):
        """★ 格坐标换算**不许有第二份**：必须用共享助手，而不是把 `(x-40)/40+0.5` 再写一遍。

        两处各写一份必然漂（这是本项目对坐标换算的硬要求）—— 而且 `Room:GetGridIndex` 那一份
        是批次 097 反复核对过的，重写一遍就等于把那次的核对作废。
        """
        source = REMAINING_API.read_text(encoding="utf-8")
        handler = source[source.index("\nint IsaacGridSpawn(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("RoomGridCoordinateFromWorld", handler,
                      "Isaac.GridSpawn 必须复用共享的格坐标换算")
        self.assertIn("ReadRoomGridDimensions", handler,
                      "Isaac.GridSpawn 必须复用共享的网格尺寸读取")
        self.assertIn("kRoomGridEntityTableOffset", handler,
                      "返回网格实体必须走既有的网格实体表偏移")
        # 反过来的半边：公式的常量不许在这里被"重新拼一遍"。
        self.assertNotIn("kRoomGridCellSize", handler,
                         "不要在 Isaac.GridSpawn 里再写一遍 40.0 的除法（复用助手）")

    def test_grid_spawn_reproduces_pc_s_occupancy_rule_and_seed(self):
        """覆盖判定与种子来源必须与 PC 绑定函数逐条对上（1 / 10 / `forced` / `RandomU32()`）。"""
        source = REMAINING_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")
        self.assertIn("kGridEntityDecorationType = 1", source, "缺 GRID_DECORATION 的覆盖豁免")
        self.assertIn("kGridEntitySpiderWebType = 10", source, "缺 GRID_SPIDERWEB 的覆盖豁免")
        self.assertIn("kRandomU32Offset = 0x35830", constants, "缺 RandomU32 的偏移常量")
        self.assertIn("kRandomU32EntryWord = 0xA9BF7BFDU", constants, "缺 RandomU32 的入口首字")
        handler = source[source.index("\nint IsaacGridSpawn(lua_State* state) {"):]
        handler = handler[:handler.index("\n}\n")]
        self.assertIn("EngineRandomU32()", handler, "种子必须来自引擎自己的 RandomU32()")
        self.assertIn("const bool forced = lua_toboolean(state, 4) != 0;", handler,
                      "第 4 个参数是 forced")

    def test_isaac_members_are_called_with_a_dot_so_argument_one_is_the_first_parameter(self):
        """★ 口径：`Isaac` 是全局表 ⇒ 按 `.` 调 ⇒ 栈上不含 `self`，实参从 `[1]` 开始。

        （与 `Room`/`Game` 的方法调用相反 —— 批次 249 正是栽在这一格。）
        """
        source = REMAINING_API.read_text(encoding="utf-8")
        free = source[source.index("\nint IsaacGetFreeNearPosition(lua_State* state) {"):]
        free = free[:free.index("\n}\n")]
        self.assertIn("lua_gettop(state) != 2", free, "两个参数 ⇒ lua_gettop == 2（不含 self）")
        self.assertIn("ReadRoomVectorArgument(state, 1, &position)", free,
                      "第 1 个实参就是 Vector pos（不含 self）")


if __name__ == "__main__":
    unittest.main()
