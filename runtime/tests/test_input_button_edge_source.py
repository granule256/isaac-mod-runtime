"""批次 403：按键侧采样**换源** —— 从"读设备对象 `+0x30`"改成"逐个问引擎"。

## 为什么（真机读数定案，**用户是对的**）

中文版 MCM 靠 `Input.IsButtonTriggered(13, i)`（右摇杆按下）开菜单。用户实测「**按右摇杆完全
没有反应，连"房间不安全"那声错误音效都没有**」⇒ `IsButtonTriggered(13, …)` 一次都没真。

读数 `dist/gdb-read-20261007-1732-after-fire-stick.txt`（**8523 帧、用户正在玩**）：

| 按键 | `lastEdgeFrame` |
| --- | --- |
| 0/1/2/3（十字） | 5711 / 5687 / 5735 / 5758 ✓ |
| 4（A） | 1239 ✓ |
| 14（减号） | 117 ✓ |
| **5..13、15..17**（B/X/Y/L/ZL/两摇杆按下/R/ZR/+ 都在这一带） | **全部"从未答过按住"** ✗ |
| `g_InputButtonEdgeCounts`（按键侧"刚按下"累计报过几次） | **一次都没报过** ✗ |

★ 这是**按位位置的规律**（0..4 与 14 活、5..13 与 15+ 死），**不是"用户按过哪些键"的规律** ——
一个 8523 帧、用户全程在玩的会话里，B/X/Y/L/R/ZL/ZR/摇杆按下**必然被按过**。
⇒ **我们采样的那一格不是引擎的按键位图。**
★ 而**引擎自己对 code 13 是能答 true 的**：批次 380 那一版（**查询时现问引擎**）真机读到
`g_InputButtonEdgeCounts[13] = 3`、用户实测 **MCM 能开**。

⇒ 修法：采样器的**按键侧数据源换成"问引擎"**（对每台手柄的按键号 0..17 逐个问，
`ManagerBase::IsButtonPressed`，与 `Input.IsButtonPressed` 的**回退分支同一枚入口**），
**判定语义一个字都不改**（`SampleRow` 第三个实参仍 `nullptr`、`Triggered`/`Pressed` 仍纯读）。

## 本文件的两半断言

1. **行为（宿主真跑，端到端）**：用**假的按键查询**（宿主里造 `0..17` 的应答）驱动**真实**的
   `SampleInputFrame`（通过帧边界钩子 `ManagedFrameClock::MarkPostUpdateDispatch`），再从
   **模组那一侧**（`Input.IsButtonTriggered(13, i)` / `Input.IsButtonPressed(13, i)`，与 MCM 同一句）
   读答案，断言 **code 13 从"没按住"变"按住"的那一帧 `Triggered` 为真、下一帧为假**
   （= 381 的"一帧一次事件"仍在）。夹具伪造了引擎模块基址 / 输入管理器 / 设备表
   （与真机同形：表里第 0 项是触摸屏、第 1 项是设备号 33 的手柄）。
2. **接线可见性（源码级）**：钉住"采样器按键侧调的是引擎查询、不再读 `+0x30`"，
   以及"旧形状（手算边沿 / 读那一格）没有回来"。
"""

import shutil
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
SRC = ROOT / "runtime" / "src"
LUA_DIR = SRC / "interfaces" / "lua"

HARNESS = r'''
#include "interfaces/lua/input_api.hpp"
#include "interfaces/lua/isaac_api.hpp"

#include "application/callback/callback_dispatcher.hpp"   // `ManagedFrameClock`
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"
#include "pc_ns_input_device_map.hpp"
#include "runtime_constants.hpp"                           // `kKage*` / `kKageInputManagerSlotOffset`

#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

extern "C" {
#include <lauxlib.h>
}

// 采样器的每帧计数（定义在 `input_api.cpp` 的命名空间作用域、匿名命名空间**之前** ⇒ 有外部链接）。
namespace isaac::runtime {
extern std::atomic<std::uint32_t> g_InputSampleCalls;
extern std::atomic<std::uint32_t> g_InputSampleCodes;
extern std::atomic<std::uint32_t> g_InputSampleFailures;
}  // namespace isaac::runtime

namespace {

int failures = 0;
void Check(bool condition, const char* what) {
    if (!condition) {
        std::printf("FAILED_CHECK %s\n", what);
        ++failures;
    }
}

// ---- 伪造的"引擎内存"（宿主上 `EngineMemoryReadable` 恒真 ⇒ 这些字节真的被读出来）----
std::vector<std::uint8_t> g_Module;                       // 模块映像（含 GOT 槽）
std::array<std::uint8_t, 0x40> g_TouchscreenDevice{};     // 表里第 0 项（设备号 0）
std::array<std::uint8_t, 0x40> g_GamepadDevice{};         // 表里第 1 项（设备号 33）
std::array<std::uintptr_t, 2> g_DeviceTable{};            // 设备指针向量
std::array<std::uint8_t, 0x20> g_Manager{};               // `KAGE::Input::ManagerBase`

// ---- 假的按键查询：bit i = "按键 i 此刻被按住"。记录收到的号与次数。----
unsigned g_heldButtons = 0;
unsigned g_buttonCalls = 0;
unsigned g_lastButton = 0xFFFFFFFFu;

bool FakeButtonPressed(void* /*manager*/, std::uint32_t button, std::uint32_t /*deviceId*/,
                       void* /*out*/) {
    ++g_buttonCalls;
    g_lastButton = button;
    return ((g_heldButtons >> (button & 31u)) & 1u) != 0u;
}

// 假的动作查询：本用例不关心动作侧，恒 false（但仍要发布，否则采样器会记采样失败）。
unsigned g_actionCalls = 0;
bool FakeActionPressed(void* /*manager*/, std::uint32_t action, std::uint32_t /*deviceId*/,
                       void* /*out*/) {
    ++g_actionCalls;
    return action == 14u && (g_heldButtons & (1u << 13)) != 0;
}

void StoreU64(void* base, std::size_t offset, std::uint64_t value) {
    std::memcpy(static_cast<std::uint8_t*>(base) + offset, &value, sizeof(value));
}
void StoreU32(void* base, std::size_t offset, std::uint32_t value) {
    std::memcpy(static_cast<std::uint8_t*>(base) + offset, &value, sizeof(value));
}

// 与 MCM 同一句：读"按键号 13（右摇杆按下）、PC 的 controllerId 1（第 1 台手柄）"。
const char* kQueryScript =
    "captured = { Input.IsButtonTriggered(13, 1), Input.IsButtonPressed(13, 1),"
    "Input.IsActionTriggered(14, 1), Input.IsActionPressed(14, 1) }";

}  // namespace

int main() {
    // ① 伪造引擎模块基址：`g_Module[kKageInputManagerSlotOffset] = &g_Manager`。
    g_Module.assign(static_cast<std::size_t>(kKageInputManagerSlotOffset) + sizeof(std::uintptr_t),
                    0);

    // ② 伪造设备表：第 0 项 = 触摸屏（设备号 0）、第 1 项 = 手柄（设备号 33，
    //    = 真机上"第 1 台手柄 ⇒ PC 的 controllerId 1"翻出来的设备号）。
    StoreU32(g_TouchscreenDevice.data(), kKageInputDeviceIdOffset,
             isaac::runtime::kNsTouchscreenDeviceId);
    StoreU32(g_GamepadDevice.data(), kKageInputDeviceIdOffset, 33u);
    g_DeviceTable[0] = reinterpret_cast<std::uintptr_t>(g_TouchscreenDevice.data());
    g_DeviceTable[1] = reinterpret_cast<std::uintptr_t>(g_GamepadDevice.data());

    // ③ 伪造 manager：`+0x8` = 设备向量 begin、`+0x10` = end。
    const std::uintptr_t begin = reinterpret_cast<std::uintptr_t>(g_DeviceTable.data());
    StoreU64(g_Manager.data(), kKageInputDeviceVectorBeginOffset, begin);
    StoreU64(g_Manager.data(), kKageInputDeviceVectorEndOffset, begin + 2u * sizeof(std::uintptr_t));
    StoreU64(g_Module.data(), kKageInputManagerSlotOffset,
             reinterpret_cast<std::uintptr_t>(g_Manager.data()));

    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(g_Module.data()));
    // 按键侧：把"引擎入口"发布成假查询（= `InputIsButtonPressedThunk()` 会交回的那一枚）。
    LuaRuntime::SetInputButtonBindings(reinterpret_cast<std::uintptr_t>(&FakeButtonPressed), 0);
    // 动作侧同理（采样器两边都会跑）。
    LuaRuntime::SetInputBindings(reinterpret_cast<std::uintptr_t>(&FakeActionPressed), 0, 0);
    // 装"帧边界钩子"（真机上由会话初始化调用）—— 之后每推一帧就采一次。
    isaac::runtime::ResetInputEdgeState();

    // 建一个最小 Lua 环境，只挂 `Input` 表（与 `lua_runtime.cpp` 里 `RegisterNeutralInputApi`
    // 做的两句相同）—— 用**模组那一侧**的入口问（与 MCM 同一句）。
    lua_State* state = luaL_newstate();
    if (state == nullptr) {
        std::printf("FAILED_CHECK luaL_newstate\n");
        return 1;
    }
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachInputMethods(state));
    lua_setglobal(state, "Input");

    const auto advance_frame = []() -> std::uint32_t {
        isaac::runtime::NativeFrameClock::MarkNativeFrame();
        return static_cast<std::uint32_t>(isaac::runtime::NativeFrameClock::Count());
    };
    const auto run_query = [&](int* triggered, int* pressed) {
        if (luaL_dostring(state, kQueryScript) != LUA_OK) {
            std::printf("FAILED_CHECK script error: %s\n", lua_tostring(state, -1));
            ++failures;
            return;
        }
        lua_getglobal(state, "captured");
        lua_rawgeti(state, -1, 1);
        *triggered = lua_toboolean(state, -1);
        lua_pop(state, 1);
        lua_rawgeti(state, -1, 2);
        *pressed = lua_toboolean(state, -1);
        lua_pop(state, 1);
        lua_rawgeti(state, -1, 3);
        Check(lua_toboolean(state, -1) == *triggered, "action and button edges share the native cycle");
        lua_pop(state, 1);
        lua_rawgeti(state, -1, 4);
        Check(lua_toboolean(state, -1) == *pressed, "action and button held states share the native cycle");
        lua_pop(state, 2);
    };

    int triggered = 0;
    int pressed = 0;

    // ---- 帧 1：没按住（建立"上一帧 held = false"的历史）--------------------------------
    g_heldButtons = 0;
    g_buttonCalls = 0;
    advance_frame();
    Check(g_buttonCalls == 18u, "按键侧每帧对 0..17 各问一次引擎（= 18 次）");
    Check(g_lastButton == 17u, "按键侧的最后一个被问的号是 17");
    Check(g_actionCalls > 0u, "动作侧也在问引擎（采样器两条都跑）");
    run_query(&triggered, &pressed);
    Check(triggered == 0, "帧1：13 没按住 ⇒ 无 边沿");

    // ---- 帧 2：13 从"没按住"变"按住" ⇒ 这一帧必须有边沿（MCM 靠的就是这一步）----------
    g_heldButtons = (1u << 13);
    advance_frame();
    run_query(&triggered, &pressed);
    Check(pressed == 1, "帧2：13 按住（读同一次采样）");
    Check(triggered == 1, "★★★ 帧2：13 首次按下 ⇒ 边沿为真（右摇杆能开 MCM）");

    // The simulation update and every consumer in this native poll share one snapshot.
    const auto callsAtEdge = g_buttonCalls;
    isaac::runtime::ManagedFrameClock::MarkPostUpdateDispatch();
    run_query(&triggered, &pressed);
    Check(triggered == 1 && pressed == 1, "update cannot consume or resample render edge");
    run_query(&triggered, &pressed);
    Check(triggered == 1, "another mod in same render sees the same edge");
    Check(g_buttonCalls == callsAtEdge, "queries and logic dispatch never resample input");
    Check(isaac::runtime::ManagedFrameClock::Count() == 1u, "logic clock remains independent");
    Check(isaac::runtime::NativeFrameClock::Count() == 2u, "native clock counts both render cycles");

    // ---- 帧 3：仍然按住 ⇒ 下一帧必须 false（381 的"一帧一次事件"仍在）------------------
    advance_frame();
    run_query(&triggered, &pressed);
    Check(triggered == 0, "帧3：仍按住 ⇒ 下一帧无 边沿");

    // ---- 帧 4 松开；帧 5 再按 ⇒ 又一次边沿（"一次按键只报一次"的完整性）----------------
    g_heldButtons = 0;
    advance_frame();
    run_query(&triggered, &pressed);
    Check(triggered == 0, "帧4：松开无 边沿");
    g_heldButtons = (1u << 13);
    advance_frame();
    run_query(&triggered, &pressed);
    Check(triggered == 1, "帧5：松开后再按 ⇒ 又一次边沿");

    // Entering the next native update expires the previous cycle before any native callback.
    const auto beforeNativeCallback = isaac::runtime::NativeFrameClock::Count();
    isaac::runtime::NativeFrameClock::BeginNativeFrame();
    run_query(&triggered, &pressed);
    Check(triggered == 0, "callback before Poll cannot reuse the preceding native edge");
    g_heldButtons = 0; // native Poll has now updated its source state
    isaac::runtime::NativeFrameClock::CompleteInputPoll();
    const auto callsAfterPoll = g_buttonCalls;
    run_query(&triggered, &pressed);
    Check(triggered == 0 && pressed == 0, "callback inside original Update sees current Poll");
    isaac::runtime::NativeFrameClock::CompleteInputPoll();
    Check(g_buttonCalls == callsAfterPoll, "post Update completion cannot sample Poll twice");
    Check(isaac::runtime::NativeFrameClock::Count() == beforeNativeCallback + 1,
          "frame count is identical before and after native callbacks");
    isaac::runtime::NativeFrameClock::BeginNativeFrame();
    g_heldButtons = (1u << 13);
    isaac::runtime::NativeFrameClock::CompleteInputPoll();
    run_query(&triggered, &pressed);
    Check(triggered == 1 && pressed == 1, "native callback sees a fresh press before Update returns");
    isaac::runtime::NativeFrameClock::CompleteInputPoll();
    run_query(&triggered, &pressed);
    Check(triggered == 1, "render after native callback sees identical current edge");

    // A native interpolation tick which skipped Poll expires the edge without another scan.
    const auto callsBeforeSkip = g_buttonCalls;
    isaac::runtime::NativeFrameClock::MarkNativeFrame(false);
    run_query(&triggered, &pressed);
    Check(triggered == 0, "an edge never repeats in a later native render cycle");
    Check(g_buttonCalls == callsBeforeSkip + 1u, "skipped Poll does not run the sampler");
    // Native polling continues with no simulation update, as it does while paused.
    g_heldButtons = 0;
    advance_frame();
    g_heldButtons = (1u << 13);
    advance_frame();
    run_query(&triggered, &pressed);
    Check(triggered == 1 && pressed == 1, "paused render can observe a new physical press");
    Check(isaac::runtime::ManagedFrameClock::Count() == 1u, "paused input never advances logic");

    // ---- 采样代价的账：每台手柄计划 50 个号（18 按键 + 32 动作），失败为 0 -----------------
    Check(isaac::runtime::g_InputSampleCodes.load() == 50u,
          "每台手柄计划采 50 个号（18 按键 + 32 动作）");
    Check(isaac::runtime::g_InputSampleCalls.load() >= 18u,
          "g_InputSampleCalls 至少含按键侧 18 次（换源后这笔账要能看见）");
    Check(isaac::runtime::g_InputSampleFailures.load() == 0u, "换源后采样不该失败");

    // The global PC clock counts native cycles and survives Lua API re-registration.
    const auto nativeBeforeReload = isaac::runtime::NativeFrameClock::Count();
    static_cast<void>(isaac::runtime::RegisterIsaacApi(state));
    lua_getglobal(state, "Isaac");
    lua_getfield(state, -1, "GetFrameCount");
    Check(lua_pcall(state, 0, 1, 0) == LUA_OK, "Isaac.GetFrameCount remains callable");
    Check(static_cast<std::uint64_t>(lua_tointeger(state, -1)) == nativeBeforeReload,
          "Isaac global clock is native60 and survives Lua reload");
    lua_pop(state, 2);

    lua_close(state);

    if (failures != 0) {
        std::printf("INPUT_BUTTON_EDGE_SOURCE_CHECKS_FAILED %d\n", failures);
        return 1;
    }
    std::printf("INPUT_BUTTON_EDGE_SOURCE_CHECKS_PASSED\n");
    return 0;
}
'''


def host_compiler() -> str | None:
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


class ButtonEdgeSourceBehaviourTests(unittest.TestCase):
    """行为（宿主真跑，端到端）：假按键查询 → 真实 `SampleInputFrame` → 模组侧的 `Input.*`。"""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-input-button-edge-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name),
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_button_edge_comes_from_the_engine_query(self):
        result = subprocess.run([str(self.binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("INPUT_BUTTON_EDGE_SOURCE_CHECKS_PASSED", result.stdout)
        self.assertNotIn("FAILED_CHECK", result.stdout)


class ButtonEdgeSourceWiringTests(unittest.TestCase):
    """接线可见性（源码级）。**不验行为** —— 这一半只保证"换源换对了、旧形状没回来"。"""

    @classmethod
    def setUpClass(cls):
        cls.input_api = (LUA_DIR / "input_api.cpp").read_text(encoding="utf-8")
        cls.constants = (SOURCE / "runtime_constants.hpp").read_text(encoding="utf-8")
        cls.deviation = (LUA_DIR / "api_deviation.cpp").read_text(encoding="utf-8")

    def _sample_input_frame_source(self) -> str:
        start = self.input_api.index("void SampleInputFrame(")
        end = self.input_api.index("void FrameBoundaryHookEntry(", start)
        return self.input_api[start:end]

    def test_button_side_asks_the_engine(self):
        """★ 批次 403：采样器按键侧必须**问引擎**（与 `Input.IsButtonPressed` 回退分支同一套三件）。"""
        sampler = self._sample_input_frame_source()
        self.assertIn("LuaRuntime::InputIsButtonPressedThunk()", sampler)
        self.assertIn("ResolveButtonQuery(", sampler)
        self.assertIn("LuaRuntime::ValidateInputIsButtonPressedBinding(", sampler)
        # 递进引擎的是**按键号**，不是设备 `+0x30` 那格位图。
        self.assertIn("code,", sampler)
        self.assertIn("deviceId, nullptr)", sampler)

    def test_button_side_no_longer_reads_the_keys_bitmap(self):
        """★ 按键侧**不许**再读设备对象 `+0x30` / `+0x38`（那一格不是引擎用的按键位图）。"""
        sampler = self._sample_input_frame_source()
        self.assertNotIn("kKageInputDeviceKeysCurrentOffset", sampler)
        self.assertNotIn("kKageInputDeviceKeysPreviousOffset", sampler)
        # 手算的边沿数组也不许回来（旧形状）。
        # ⚠️ 只钉**代码形状**（声明 / 读取 / 实参名），不钉注释里的文字 —— 本批的注释里就要
        #   写出"原先传的是哪个表达式"，把注释算进去会自己把自己判红（与 400 那条门禁同一条纪律）。
        self.assertNotIn("std::uint32_t keysCurrent", sampler)
        self.assertNotIn("bool buttonEdge", sampler)
        self.assertNotIn("aggButtonEdge", sampler)

    def test_sample_row_still_takes_a_null_edge(self):
        """★ 判定语义不变：`SampleRow` 第三个实参仍是 `nullptr`（边沿由本类按帧自己差分）。"""
        sampler = self._sample_input_frame_source()
        self.assertIn("g_ButtonEdge.SampleRow(", sampler)
        self.assertIn("buttonPressed, nullptr)", sampler)
        self.assertIn("aggButtonPressed, nullptr)", sampler)

    def test_the_constant_is_documented_as_not_the_engine_bitmap(self):
        """★ 顺手留痕：那一格常量的注释里要写明"不是引擎用的按键位图、别拿它算边沿"
        （只加不删 —— 原有注释必须仍在）。"""
        self.assertIn("不是引擎用的按键位图", self.constants)
        self.assertIn("本帧 / 上一帧的**按键位图**", self.constants)
        self.assertIn("kKageInputDeviceKeysCurrentOffset = 0x30", self.constants)
        self.assertIn("kKageInputDeviceKeysPreviousOffset = 0x38", self.constants)

    def test_the_deviation_is_appended(self):
        """★ 换源必须进偏离台账（追加一段，旧文不许动）。"""
        entry = self.deviation[self.deviation.index("{0x09010004,"):]
        entry = entry[:entry.index("},")]
        self.assertIn("批次 403", entry)
        self.assertIn("InputIsButtonPressedThunk", entry)
        self.assertIn("g_InputSampleFailures", entry)
        # 旧文仍在（只加不删）。
        self.assertIn("批次 381", entry)
        self.assertIn("判据：runtime/tests/test_input_action_edge.py", entry)


if __name__ == "__main__":
    unittest.main()
