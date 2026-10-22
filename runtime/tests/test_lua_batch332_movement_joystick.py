"""门禁：`EntityPlayer:GetMovementJoystick()`（批次 332，2026-10-03）。

## 这一条是什么

| API | 契约 | 引擎侧 | 语料 |
| --- | --- | --- | --- |
| `EntityPlayer:GetMovementJoystick()` | `EntityPlayer.md:1106` | `Entity_Player::get_movement_input()` @ `0x2B0D9C` → 返回 `Vector` | 4 处 |

**与 328 那对同型**：PC 侧 `GetMovementInput`(:1100) 与 `GetMovementJoystick`(:1106)
**共用同一个绑定 VA `0x741880`**（同一先例：328 的 `GetShootingInput`/`GetShootingJoystick` 共用 `0x741B00`）；
返回 `Vector` 是两个 `float` 的 **HFA**（走 `s0`/`s1`）⇒ 通用跳板只回填 `x0`/`d0` ⇒ **手写处理器**。

## ★★★ 本批的难点：**名字对不上**（这是与 328 最大的区别）

328 那次是"**同一个名字的两种拼写**"（`GetShootingInput` ↔ `get_shooting_input`）——
329 修好工具之后，那种情况**工具自动就能找到**。
这一批不一样：Lua 叫 `GetMovementJoystick`，引擎里那个函数叫 **`get_movement_input`**
（`joystick` vs `input`）—— **符号表里根本没有 `get_movement_joystick`**，
329 那套"归一化名兜底"同样搜不到（名字本身就是两个词）。

⇒ **定案只能靠函数体**：把 PC 绑定（`0x741880`）与 Switch（`0x2B0D9C`）逐条对齐 ——
玩家类型 `0x14`/`0x1d`/`0x26`、父指针 `[ptr+0x28]==1`、双子索引比较、`ControlsEnabled`、
`ControlsCooldown`、**动作号 `0x0b`(11)** 的 `IsActionPressed`、未按下时 `GetActionValue(0/1/2)` 累加
—— **七条 + 动作号 + 两条分支的做法一一对应**（详见 `runtime_constants.hpp` 批次 332 段）。
★ 这条经验写在这里：**"符号在 ≠ 能用"（331 的教训）的另一面是"名字不同 ≠ 没关系"——
判据永远是函数体。**

## 宿主验到了什么、没验到什么

* **验到**：方法挂得上；调用**不报错**且返回**一个 Lua `Vector`**（不是 `nil` —— 语料里
  `p:GetMovementJoystick().X` 是连写的，`nil` 会让整条回调以 "attempt to index a nil value" 被摘）；
  参数闸门（多给一个报错且带名字）；点号 + 显式 `self` 放行。
* **没验**：**引擎那一步真的返回了什么** —— 宿主里没有引擎函数 ⇒ 必然走"入口取不到"那条降级
  ⇒ 只能证明"接线对、形状对、降级档选对" ⇒ **真值只能真机**。
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

INDEX = 0x00E4
HANDLER = "EntityPlayerGetMovementJoystick"
OFFSET_NAME = "kEntityPlayerGetMovementJoystickOffset"
ENTRY_NAME = "kEntityPlayerGetMovementJoystickEntryWord"

HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "entity_layout.hpp"
#include "runtime_constants.hpp"

#include <cstdint>
#include <cstring>
#include <vector>

// 伪造的引擎内存（与批次 328 的夹具同形）：只要一个"当前玩家"。
//   ★ 本批**故意不提供引擎函数** ⇒ 处理器必然走"入口取不到"那条降级 ⇒ 宿主看到 `Vector(0, 0)`。
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
    g_ModuleBytes.assign(kGameOwnerGlobalSlotOffset + sizeof(std::uint64_t), 0);
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
    static_cast<void>(argv);
    if (argc != 2) return 90;

    PublishFakeGame();
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x2222);

    const char* script =
        "local function ok(f) return tostring(select(1, pcall(f))) end"
        " local function err(f) return tostring(select(2, pcall(f))) end"
        " local p = Isaac.GetPlayer(0)"
        " print('B332 pkind=' .. type(p))"
        " print('B332 fn=' .. type(p.GetMovementJoystick))"
        " local v = p:GetMovementJoystick()"
        " print('B332 kind=' .. type(v))"
        " print('B332 count=' .. tostring(select('#', p:GetMovementJoystick())))"
        " print('B332 comps=' .. type(v.X) .. '/' .. type(v.Y))"
        " print('B332 x=' .. tostring(v.X) .. ' y=' .. tostring(v.Y))"
        // 模组的真实用法：连写取分量做算术。
        " print('B332 use=' .. tostring(v.X * 10 + v.Y * 10))"
        // 参数闸门。
        " print('B332 extra=' .. ok(function() return p:GetMovementJoystick(1) end))"
        " print('B332 extraerr=' .. err(function() return p:GetMovementJoystick(1) end))"
        " print('B332 dot=' .. ok(function() return p.GetMovementJoystick(p) end))";

    const auto result = LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@b332.lua");
    static_cast<void>(result);
    return 0;
}
'''


class MovementJoystickBatch332Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-b332-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name) / "harness",
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_scenario(self):
        result = subprocess.run([str(self.binary), "run"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    # ---------------------------------------------------------------- 行为（宿主）

    def test_the_method_returns_a_vector(self):
        """★ 方法挂得上，且返回**一个 Lua `Vector`**（不是 `nil`）—— 语料里 `.X`/`.Y` 是连写的。"""
        out = self.run_scenario()
        self.assertIn("B332 pkind=userdata", out)
        self.assertIn("B332 fn=function", out)
        self.assertIn("B332 kind=userdata", out)
        self.assertIn("B332 count=1", out)
        self.assertIn("B332 comps=number/number", out)

    def test_without_an_engine_the_fallback_is_vector_zero(self):
        """★ 宿主里没有引擎函数 ⇒ 走"入口取不到" ⇒ `Vector(0, 0)`、不报错（验的是**降级档选对了**）。"""
        out = self.run_scenario()
        self.assertIn("B332 x=0.0 y=0.0", out)
        self.assertNotIn("attempt to", out)

    def test_argument_gate_is_exactly_one(self):
        """参数闸门：**恰好一个**（`self`）；多给一个报错，且消息里有 API 名字；点号显式 `self` 放行。"""
        out = self.run_scenario()
        self.assertIn("B332 extra=false", out)
        self.assertIn("EntityPlayer:GetMovementJoystick accepts no arguments", out)
        self.assertIn("B332 dot=true", out)

    # ---------------------------------------------------------------- 静态接线

    def test_wiring(self):
        """目录行 / 绑定行 / 常量 / 入口首字核对 —— 完成定义台账引用的就是这个方法。"""
        catalog = CATALOG.read_text(encoding="utf-8")
        api = ISAAC_API.read_text(encoding="utf-8")
        constants = CONSTANTS.read_text(encoding="utf-8")

        self.assertIn(
            f'MakeId(ApiDomain::Isaac, 1, 0x{INDEX:04X}), ApiDomain::Isaac, '
            f'"EntityPlayer", "GetMovementJoystick"', catalog, "目录行缺失")
        self.assertIn(f"{{0x0E01{INDEX:04X}, &{HANDLER}}}", api, "绑定行缺失")
        self.assertIn(f"inline constexpr uintptr_t {OFFSET_NAME} = 0x2B0D9C;", constants)
        self.assertIn(f"inline constexpr std::uint32_t {ENTRY_NAME} = 0xD10103FFu;", constants)
        self.assertRegex(api, rf"EngineEntryWordMatches\(method, {ENTRY_NAME}\)")
        #: ★★ 反回归：这条返回 16 字节的 `Vector`（HFA）⇒ **不许**被塞进数据行/引擎方法行表。
        self.assertNotRegex(api, rf"0x0E01{INDEX:04X}[^\n]*EngineCallShape")
        self.assertNotRegex(api, rf"0x0E01{INDEX:04X}[^\n]*FieldKind::")
        #: 与 328 那两条**共用同一套手写接法**（`EngineVector2Abi` + `PushLuaVector`）。
        self.assertIn("EngineVector2Abi", api)
        self.assertRegex(api, r"isaac::runtime::PushLuaVector\(state, value\.x, value\.y\)")

    def test_the_name_mismatch_evidence_is_recorded(self):
        """★★ 常量段必须写明「名字不一样」这件事本身，以及**逐条对照函数体**的结论。

        这条不是形式主义：这一条的 Lua 名（`GetMovementJoystick`）与引擎函数名
        （`get_movement_input`）**是两个词**，将来有人照着名字去查、查不到就会误判成"引擎没有"。
        """
        constants = CONSTANTS.read_text(encoding="utf-8")
        folded = constants.lower()
        for needle in ("0x741880", "0x2b0d9c", "get_movement_input", "0x0b",
                       "isactionpressed", "getactionvalue", "controlscooldown"):
            self.assertIn(needle, folded, f"证据 {needle} 没有写进常量段")
        #: "名字不一样"这件事本身、以及两条分支的返回做法，都要留痕。
        self.assertIn("joystick", folded)
        self.assertIn("input", folded)
        self.assertIn("HFA", constants)
        #: 契约页与行号。
        self.assertIn("EntityPlayer.md", constants)
        self.assertIn("1106", constants)


if __name__ == "__main__":
    unittest.main()
