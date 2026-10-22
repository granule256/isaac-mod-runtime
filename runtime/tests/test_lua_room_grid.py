"""`Room` 网格族（宽/高/尺寸/格坐标/通行代价）—— 批次 098 把占位实现换成真实现后的门禁。

## 这个测试解决什么问题

真机上"走到地上药丸/卡片旁边只显示一个问号"（用户 2026-09-20 报）的根因，是本运行时里
`Room:GetGridPath()` **恒返回 1000**（批次 7 的保守占位），而 EID 的判据是
`collision <= 900 = 可走`（`features/eid_api.lua:3362`）：
→ `EID:HasPathToPosition` 恒 false → `EID:attemptPathfind` 恒 false
→ `main.lua:1639-1648`（药丸）/`1614-1622`（卡片）走"够不到就不给看"分支、只画问号。
宿主复现（用 EID 自己的寻路器）：`tools/room_grid_reachability_probe.py`。

真实现的偏移来自对游戏本体模块的反汇编（`tools/nro_disasm.py`），三条互相印证：

| 事实 | 来源 |
| --- | --- |
| `Room + 0x14` 宽、`Room + 0x18` 高 | `Room::GetGridPath(int,int) @ 0x484120` 的两条边界检查 |
| `Room + 0xE98` 通行代价数组（int32/格，下标 `W*y + x`，越界返回 0） | 同一条函数的尾部 `ldr w0, [x8, #0xe98]` |
| 世界→格：`(int)((pos − origin)/40 + 0.5)`，返回 `W*gy + gx`，越界 −1 | `Room::GetGridIndex(Vector2) @ 0x459e3c` |

## 断言口径

1. **宽/高/尺寸**读的是那两个字段（13/7/91）—— 以前是硬编码 13/13/169；
2. **`GetGridPath` 不再是常量**：本测试一次读三个不同格子（0 / 950 / 900），
   再读"刚好越界"的两格（−1 与 `W*H`）⇒ 越界按**引擎口径**给 0；
3. 整数实参口径：`GetGridPath(5)` 与 `GetGridPath(5.0)` 必须同值（EID 会传整值浮点）；
4. **`GetGridIndex` 的口径与偏移**：格子中心 `(40+40gx, 120+40gy)`、边界在 `pos ≡ 60 (mod 40)`、
   越界（含负格、`x>=W`、`y>=H`）给 **−1 而不是报错**（PC 文档：`Returns -1 for invalid index`）；
5. **读不到房间时要报错**，不能编一个尺寸（编了会让 EID 的下标算出别的格子 —— "条件为假、不报错"
   是最难查的一类）；
6. 源码层面钉住"不许退回占位"：实现里不许再出现 `kRoomGridPathBlocked` 这种恒值口径。
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from .test_support import build_lua_harness
except ImportError:
    from test_support import build_lua_harness


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

#: 合成房间：标准房间的网格是 **13 宽 × 7 高**（引擎 `GetGridIndex` 的 y 偏移 −120 = −3 格
#: 正是"房间在 13×13 网格里偏下 3 格"的来处）。
GRID_WIDTH = 13
GRID_HEIGHT = 7
GRID_CELLS = GRID_WIDTH * GRID_HEIGHT  # 91

#: 写进假房间的那几个格子：0（默认可走）、5（950 = 火）、20（1000 > 900 = 不可走）、
#: 90（最后一格，900 = "高代价但仍可走"，EID 判据说 `<= 900` 算可走）。
CELL_ZERO = 0
CELL_FIRE = 950
CELL_BLOCKED = 1000
CELL_HEAVY = 900

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
std::vector<unsigned char> g_RoomBytes;
bool g_RoomUnreadable = false;

template <typename T>
void WriteAt(std::vector<unsigned char>& block, std::size_t offset, T value) {
    std::memcpy(block.data() + offset, &value, sizeof(T));
}

std::uintptr_t AddressOf(const std::vector<unsigned char>& block) {
    return reinterpret_cast<std::uintptr_t>(block.data());
}

void PublishFakeRoom() {
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
    g_OwnerSlotBytes.assign(sizeof(std::uint64_t), 0);
    // 假房间：尺寸字段 + 整张通行代价表（int32/格）都要真的存在，越界读才会被守卫挡住。
    const std::size_t roomSize =
        kRoomGridPathArrayOffset + GRID_CELLS * sizeof(std::int32_t) + 16;
    g_RoomBytes.assign(roomSize, 0);

    WriteAt<std::uint32_t>(g_RoomBytes, kRoomGridWidthOffset, GRID_WIDTH);
    WriteAt<std::uint32_t>(g_RoomBytes, kRoomGridHeightOffset, GRID_HEIGHT);
    const auto writeCell = [](std::size_t index, std::int32_t value) {
        WriteAt<std::int32_t>(g_RoomBytes,
                              kRoomGridPathArrayOffset + index * sizeof(std::int32_t), value);
    };
    writeCell(0, CELL_ZERO);
    writeCell(5, CELL_FIRE);
    writeCell(20, CELL_BLOCKED);
    writeCell(GRID_CELLS - 1, CELL_HEAVY);

    WriteAt<std::uintptr_t>(g_ModuleBytes, kGameOwnerGlobalSlotOffset, AddressOf(g_OwnerSlotBytes));
    WriteAt<std::uintptr_t>(g_OwnerSlotBytes, 0, AddressOf(g_RoomBytes));
    LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
}

}  // namespace

// 覆盖共享默认桩：本场景只关心"当前房间"，游戏对象那条链用最简单的方式接上。
GameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {
    if (g_RoomUnreadable) return GameRoomObservation::RoomUnreadable;
    if (room == nullptr) return GameRoomObservation::RoomNull;
    *room = reinterpret_cast<void*>(AddressOf(g_RoomBytes));
    return GameRoomObservation::Success;
}

int main(int argc, char** argv) {
    if (argc != 2) return 90;
    const char* scenario = argv[1];
    g_RoomUnreadable = std::strcmp(scenario, "unreadable") == 0;

    PublishFakeRoom();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script = nullptr;
    if (std::strcmp(scenario, "dims") == 0) {
        script =
            "local room = Game():GetRoom()"
            " print('DIMS='..room:GetGridWidth()..','..room:GetGridHeight()..','"
            " ..room:GetGridSize())";
    } else if (std::strcmp(scenario, "path") == 0) {
        script =
            "local room = Game():GetRoom()"
            " local v0 = room:GetGridPath(0)"
            " local v5 = room:GetGridPath(5)"
            " local v5f = room:GetGridPath(5.0)"
            " local vneg = room:GetGridPath(-1)"
            " local vhigh = room:GetGridPath(91)"
            " local vlast = room:GetGridPath(90)"
            " print('PATH='..v0..','..v5..','..v5f..','..vneg..','..vhigh..','..vlast)";
    } else if (std::strcmp(scenario, "index") == 0) {
        // 八个格坐标一次问完（顺序见 Python 侧断言）：
        //   格 (2,3) 的格心 / 整数重载同值 / 末格 (12,6) / x=19 仍在第 0 列 /
        //   角落 (0,0) 算出负行 ⇒ 越界 / x=W / y=H / 负数重载
        script =
            "local room = Game():GetRoom()"
            " local center = room:GetGridIndex(Vector(120, 240))"
            " local pair = room:GetGridIndex(2, 3)"
            " local last = room:GetGridIndex(Vector(520, 360))"
            " local edge = room:GetGridIndex(Vector(19, 240))"
            " local corner = room:GetGridIndex(Vector(0, 0))"
            " local bigx = room:GetGridIndex(13, 0)"
            " local bigy = room:GetGridIndex(0, 7)"
            " local negpair = room:GetGridIndex(-1, 0)"
            " print('INDEX='..center..','..pair..','..last..','..edge..','..corner..','"
            " ..bigx..','..bigy..','..negpair)";
    } else if (std::strcmp(scenario, "unreadable") == 0) {
        // 批次 250：口径从"报错"改成"回退值" ⇒ 这里改成打印**返回值**（而不是错误文本）。
        script =
            "local ok, value = pcall(function() return Game():GetRoom():GetGridWidth() end)"
            " print('UNREADABLE ok='..tostring(ok)..' value='..tostring(value))";
    } else {
        return 91;
    }

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                                         "@roomgrid.lua");
    // ★ 批次 043 起：顶层（非托管回调）调用不再被作用域守卫拒绝，所以这几个场景都直接跑顶层。
    static_cast<void>(result);
    return 0;
}
'''


class LuaRoomGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-lua-roomgrid-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS.replace("GRID_WIDTH", str(GRID_WIDTH))
                                 .replace("GRID_HEIGHT", str(GRID_HEIGHT))
                                 .replace("GRID_CELLS", str(GRID_CELLS))
                                 .replace("CELL_ZERO", str(CELL_ZERO))
                                 .replace("CELL_FIRE", str(CELL_FIRE))
                                 .replace("CELL_BLOCKED", str(CELL_BLOCKED))
                                 .replace("CELL_HEAVY", str(CELL_HEAVY)),
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self, scenario: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(self.binary), scenario], text=True, capture_output=True)

    def test_grid_dimensions_come_from_the_room_fields(self):
        """宽/高/尺寸读 `Room + 0x14`/`+0x18`，尺寸是两者相乘。

        以前这里是硬编码 13/13/169；真机标准房间是 13×7 ⇒ 91。
        断言打在一行上（13,7,91），失败时三个数字一起看得见。
        """
        result = self.run_scenario("dims")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"DIMS={GRID_WIDTH},{GRID_HEIGHT},{GRID_CELLS}", result.stdout)

    def test_grid_path_reads_the_path_table_and_is_not_a_constant(self):
        """★ 这条就是"药丸/卡片只有问号"的直接判据。

        三个不同格子必须读出三个不同的值（0 / 950 / 900）—— 只要它退化成任何常量，
        这条就红；`GetGridPath(5)` 与 `GetGridPath(5.0)` 还必须同值（EID 会传整值浮点）。
        越界的两格（−1 与 `W*H`）按**引擎口径**给 0，而不是像 PC 的 Lua 那样越界读内存。
        """
        result = self.run_scenario("path")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            f"PATH={CELL_ZERO},{CELL_FIRE},{CELL_FIRE},0,0,{CELL_HEAVY}", result.stdout)

    def test_grid_index_matches_the_engine_formula_and_offsets(self):
        """`W*gy + gx`，格中心在 `(40+40gx, 120+40gy)`，越界给 −1（不是报错）。

        八个值一次性打在 `INDEX=` 行上（顺序 = 格心 / 整数重载 / 末格 / 列边界 / 角落负格 /
        x 越界 / y 越界 / 负数重载），边界口径与断言写在一起。
        """
        result = self.run_scenario("index")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        center = GRID_WIDTH * 3 + 2        # 格 (2,3)
        last = GRID_WIDTH * 6 + 12         # 格 (12,6)
        edge = GRID_WIDTH * 3 + 0          # x=19 仍在第 0 列
        self.assertIn(f"INDEX={center},{center},{last},{edge},-1,-1,-1,-1", result.stdout)

    def test_unreadable_room_yields_a_fallback_value_not_an_error(self):
        """读不到房间 ⇒ 给**回退值 0**、不报错（批次 250 改的口径）。

        ★ 本条与批次 098 的原断言相反，**理由要写清楚**：旧断言的依据是"编一个 13 会让 EID 的
        下标算出别的格子，且不报错"。但权衡的另一端更重 —— **抛 Lua 错误会摘掉整条模组回调**，
        真机代价是"整个模组的功能在加载期消失"（2026-10-01 的 GoodTrip，`scripts/floor.lua:12`）。
        而回退值只是"这一个数不对"，并且**回退次数有探针**（`NativeFallbackProbe`），
        不是"悄悄失真"。更根本的是：**PC 上这些调用根本不失败**（PC 拿的是模组手上那个
        有效对象，没有"解析"这一步），所以抛错等于让模组行为偏离 PC。

        旧断言：`assertIn("could not read", ...)`。
        """
        result = self.run_scenario("unreadable")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("UNREADABLE ok=true", result.stdout)
        self.assertIn("value=0", result.stdout)

    def test_placeholder_implementation_cannot_come_back(self):
        """源码层面钉住口径：旧的恒值占位不许回来，新常量必须带证据注释。

        这条不是"风格检查"：`GetGridPath` 一旦退回常量，EID 就会重新把地上每一颗药丸、
        每一张卡片判成"够不到"、只画问号 —— 那是**用户可见**的缺陷，必须有东西挡住。
        """
        remaining = (SOURCE.parent / "src" / "interfaces" / "lua" / "remaining_api.cpp").read_text(
            encoding="utf-8")
        self.assertNotIn("kRoomGridPathBlocked", remaining)
        self.assertNotIn("kRoomGridFallbackWidth", remaining)
        self.assertNotIn("kRoomGridFallbackHeight", remaining)
        constants = (SOURCE / "runtime_constants.hpp").read_text(encoding="utf-8")
        for name in ("kRoomGridWidthOffset", "kRoomGridHeightOffset", "kRoomGridPathArrayOffset",
                     "kRoomGridWorldOffsetX", "kRoomGridWorldOffsetY"):
            with self.subTest(constant=name):
                self.assertIn(name, constants)
        self.assertIn("0x484120", constants, "通行代价数组的偏移必须写上反汇编出处")
        self.assertIn("0x459e3c", constants, "格坐标换算必须写上反汇编出处")


if __name__ == "__main__":
    unittest.main()
