"""批次 406：输入边沿表的**槽撞车** —— 同帧对同一个槽写两次会把边沿抹掉。

## 根因（证据齐全，别再重新论证）

边沿表 `LuaRuntime::InputFrameEdges` 按 **`设备号 & 31`** 入槽；而引擎手柄号 ∈ {1..8, 33}
（`NpadId + 1`，候选表 `{0..7,32}`），⇒ **`1` 与 `33` 相差 32、落进同一个槽 1**。
真机读数（批次 404）证明设备表里**有 2 台真手柄**（`g_InputSampleCalls = 88 = 2 × 44`）。

而 `InputFrameEdges::SampleRow` 在**同一帧对同一槽不幂等**：

```
edge = cur && has_history && !entry.held;   // 第一次写：held=false ⇒ edge=cur
entry.held = cur;                           // 紧接着写回
```

⇒ 同一帧第二次写同一个槽时 `entry.held` 已经是 `cur` ⇒ `!entry.held == false` ⇒
`edge = false` ⇒ **`entry.edge` 被覆盖成 false，第一次那条边沿就没了**。

⇒ 每次边沿都在写入那一刻被抹掉 ⇒ 中文版 MCM 的 `Input.IsButtonTriggered(13, i)`（右摇杆按下）
在**局内、不暂停**时永远读不到边沿 ⇒ **MCM 开不出来**。

## 修法（批次 406，最小）

`SampleInputFrame` 里**按槽聚合、每槽每帧只写一次**：先把本帧所有设备的按键/动作结果按
`deviceId & 31` **OR** 聚合进 per-slot 缓冲，再对每个槽**只调一次** `SampleRow`。
第三个实参仍 `nullptr`（边沿仍由 `InputFrameEdges` 用**它自己上一帧的 `held`** 差分）。

## 本文件的两半断言

1. **行为（宿主真跑，端到端）**：伪造引擎内存（表里第 0 项触摸屏、第 1 台手柄设备号 33、
   第 2 台手柄设备号 **1** ⇒ **1 与 33 同槽**），用**假的按键查询**驱动**真实**的
   `SampleInputFrame`，再从**模组那一侧**（`Input.IsButtonTriggered(13, 1)`，与 MCM 同一句）
   读答案：两设备同帧按下 code 13 ⇒ `Triggered` 为真、**下一帧为假**。
   另含一段**反向自证**：直接对**真实** `InputFrameEdges` 同帧同槽写两次，断言第二次把边沿抹掉
   —— 那条就是旧采样器的形状（把采样器还原成"每设备一次 SampleRow"时，本文件的行为用例必红）。
2. **接线可见性（源码级）**：钉住"采样器按槽聚合、每槽每帧最多一次 `SampleRow`"、
   "第三个实参仍是 `nullptr`"、"聚合槽 `kNsAnyInputDevice` 仍是任一设备按下"、
   "查询仍按设备逐个问引擎（不是退回读位图）"。
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

#include "application/callback/callback_dispatcher.hpp"   // `ManagedFrameClock`
#include "input_edge.hpp"                                  // `InputFrameEdges`（反向自证用）
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
std::array<std::uint8_t, 0x40> g_Gamepad33Device{};        // 表里第 1 项（设备号 33）
std::array<std::uint8_t, 0x40> g_Gamepad1Device{};         // 表里第 2 项（设备号 1）★ 与 33 同槽
std::array<std::uintptr_t, 3> g_DeviceTable{};            // 设备指针向量
std::array<std::uint8_t, 0x20> g_Manager{};               // `KAGE::Input::ManagerBase`

// ---- 假的按键查询：**两台设备各一份**"按住"位图（用来造"同帧同槽撞车"）----
unsigned g_heldBy33 = 0;
unsigned g_heldBy1 = 0;
unsigned g_buttonCalls = 0;
unsigned g_lastDevice = 0xFFFFFFFFu;

bool FakeButtonPressed(void* /*manager*/, std::uint32_t button, std::uint32_t deviceId,
                       void* /*out*/) {
    ++g_buttonCalls;
    g_lastDevice = deviceId;
    unsigned bits = 0;
    if (deviceId == 33u) {
        bits = g_heldBy33;
    } else if (deviceId == 1u) {
        bits = g_heldBy1;
    }
    return ((bits >> (button & 31u)) & 1u) != 0u;
}

// 假的动作查询：本用例不关心动作侧，恒 false（但仍要发布，否则采样器会记采样失败）。
unsigned g_actionCalls = 0;
bool FakeActionPressed(void* /*manager*/, std::uint32_t /*action*/, std::uint32_t /*deviceId*/,
                       void* /*out*/) {
    ++g_actionCalls;
    return false;
}

void StoreU64(void* base, std::size_t offset, std::uint64_t value) {
    std::memcpy(static_cast<std::uint8_t*>(base) + offset, &value, sizeof(value));
}
void StoreU32(void* base, std::size_t offset, std::uint32_t value) {
    std::memcpy(static_cast<std::uint8_t*>(base) + offset, &value, sizeof(value));
}

// 与 MCM 同一句：读"按键号 13（右摇杆按下）、PC 的 controllerId 1（第 1 台手柄）"；
// 外加"任意设备"聚合槽（`0xFFFFFFFF`）。
const char* kQueryScript =
    "captured = { Input.IsButtonTriggered(13, 1), Input.IsButtonPressed(13, 1),"
    " Input.IsButtonTriggered(13, 4294967295) }";

}  // namespace

int main() {
    // ① 伪造引擎模块基址：`g_Module[kKageInputManagerSlotOffset] = &g_Manager`。
    g_Module.assign(static_cast<std::size_t>(kKageInputManagerSlotOffset) + sizeof(std::uintptr_t),
                    0);

    // ② 伪造设备表：第 0 项 = 触摸屏（设备号 0）；第 1 项 = 手柄（设备号 33）；
    //    第 2 项 = 手柄（设备号 **1**）—— **33 与 1 相差 32 ⇒ 落进同一个槽 1**（本批的病灶）。
    StoreU32(g_TouchscreenDevice.data(), kKageInputDeviceIdOffset,
             isaac::runtime::kNsTouchscreenDeviceId);
    StoreU32(g_Gamepad33Device.data(), kKageInputDeviceIdOffset, 33u);
    StoreU32(g_Gamepad1Device.data(), kKageInputDeviceIdOffset, 1u);
    g_DeviceTable[0] = reinterpret_cast<std::uintptr_t>(g_TouchscreenDevice.data());
    g_DeviceTable[1] = reinterpret_cast<std::uintptr_t>(g_Gamepad33Device.data());
    g_DeviceTable[2] = reinterpret_cast<std::uintptr_t>(g_Gamepad1Device.data());

    // ③ 伪造 manager：`+0x8` = 设备向量 begin、`+0x10` = end。
    const std::uintptr_t begin = reinterpret_cast<std::uintptr_t>(g_DeviceTable.data());
    StoreU64(g_Manager.data(), kKageInputDeviceVectorBeginOffset, begin);
    StoreU64(g_Manager.data(), kKageInputDeviceVectorEndOffset, begin + 3u * sizeof(std::uintptr_t));
    StoreU64(g_Module.data(), kKageInputManagerSlotOffset,
             reinterpret_cast<std::uintptr_t>(g_Manager.data()));

    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(g_Module.data()));
    LuaRuntime::SetInputButtonBindings(reinterpret_cast<std::uintptr_t>(&FakeButtonPressed), 0);
    LuaRuntime::SetInputBindings(reinterpret_cast<std::uintptr_t>(&FakeActionPressed), 0, 0);
    isaac::runtime::ResetInputEdgeState();

    lua_State* state = luaL_newstate();
    if (state == nullptr) {
        std::printf("FAILED_CHECK luaL_newstate\n");
        return 1;
    }
    lua_newtable(state);
    static_cast<void>(isaac::runtime::AttachInputMethods(state));
    lua_setglobal(state, "Input");

    const auto advance_frame = []() -> std::uint32_t {
        isaac::runtime::ManagedFrameClock::MarkPostUpdateDispatch();
        return static_cast<std::uint32_t>(isaac::runtime::ManagedFrameClock::Count());
    };
    const auto run_query = [&](int* triggered, int* pressed, int* any_triggered) {
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
        *any_triggered = lua_toboolean(state, -1);
        lua_pop(state, 2);
    };

    int triggered = 0;
    int pressed = 0;
    int any_triggered = 0;

    // ---- 帧 1：两台设备都"没按住"（建立上一帧 held = false 的历史）--------------------
    g_heldBy33 = 0;
    g_heldBy1 = 0;
    g_buttonCalls = 0;
    advance_frame();
    // 按键侧：每台手柄问 18 个号（2 台 = 36 次），查询仍**按设备**做。
    Check(g_buttonCalls == 36u, "按键侧每帧对每台手柄 0..17 各问一次引擎（2 台 = 36 次）");
    Check(g_lastDevice == 1u, "最后一台被问的手柄是设备号 1（表里第 2 台）");
    run_query(&triggered, &pressed, &any_triggered);
    Check(triggered == 0, "帧1：13 没按住 ⇒ 无 边沿");

    // ---- 帧 2：★ 两台设备**同帧同槽**都从"没按住"变"按住" ⇒ 该槽必须有边沿 -------------
    //    旧采样器（每设备一次 SampleRow）在这一帧会把边沿写两次 ⇒ 第二次抹掉第一次 ⇒ 红。
    g_heldBy33 = (1u << 13);
    g_heldBy1 = (1u << 13);
    advance_frame();
    run_query(&triggered, &pressed, &any_triggered);
    Check(pressed == 1, "帧2：13 按住（读同一次采样）");
    Check(triggered == 1,
          "★★★ 帧2：同帧同槽两台设备都按下 ⇒ 边沿为真（右摇杆能开 MCM；修复前这里是红的）");
    Check(any_triggered == 1, "帧2：聚合槽（任意设备）也为真");

    // ---- 帧 3：仍然按住 ⇒ 下一帧必须 false（381 的"一帧一次事件"仍在）------------------
    advance_frame();
    run_query(&triggered, &pressed, &any_triggered);
    Check(triggered == 0, "帧3：仍按住 ⇒ 下一帧无 边沿");
    Check(any_triggered == 0, "帧3：聚合槽下一帧也 false");

    // ---- 帧 4 松开；帧 5 再按 ⇒ 又一次边沿（"一次按键只报一次"的完整性）----------------
    g_heldBy33 = 0;
    g_heldBy1 = 0;
    advance_frame();
    run_query(&triggered, &pressed, &any_triggered);
    Check(triggered == 0, "帧4：松开无 边沿");
    g_heldBy33 = (1u << 13);
    g_heldBy1 = (1u << 13);
    advance_frame();
    run_query(&triggered, &pressed, &any_triggered);
    Check(triggered == 1, "帧5：松开后再按 ⇒ 又一次边沿");

    // ---- 按槽聚合是 **OR**（任一设备按下 ⇒ 该槽按住）------------------------------------
    g_heldBy33 = 0;
    g_heldBy1 = 0;
    advance_frame();
    run_query(&triggered, &pressed, &any_triggered);
    // 只有表里第 2 台（设备号 1）按下；设备 33 没按 ⇒ 聚合后槽 1 仍应"按住 + 边沿"。
    g_heldBy1 = (1u << 12);
    g_heldBy33 = 0;
    advance_frame();
    run_query(&triggered, &pressed, &any_triggered);
    {
        // 用同一台设备的另一个号（12）也验证一遍：读 code 12（设备 1）。
        int t12 = 0;
        if (luaL_dostring(state, "captured = { Input.IsButtonTriggered(12, 1),"
                                 " Input.IsButtonPressed(12, 1) }") != LUA_OK) {
            std::printf("FAILED_CHECK script error\n");
            ++failures;
        } else {
            lua_getglobal(state, "captured");
            lua_rawgeti(state, -1, 1);
            t12 = lua_toboolean(state, -1);
            lua_pop(state, 2);
        }
        Check(t12 == 1, "OR 聚合：只有一台设备按下 ⇒ 该槽仍报边沿（不是 AND）");
    }

    // ---- 采样代价的账：每台手柄计划 50 个号（18 按键 + 32 动作），失败为 0 -----------------
    Check(isaac::runtime::g_InputSampleCodes.load() == 50u,
          "每台手柄计划采 50 个号（18 按键 + 32 动作）");
    Check(isaac::runtime::g_InputSampleCalls.load() >= 36u,
          "g_InputSampleCalls 至少含按键侧 2 台 × 18 次（按槽聚合不改查询次数）");
    Check(isaac::runtime::g_InputSampleFailures.load() == 0u, "采样不该失败");

    // ---- ★★ 反向自证：直接对**真实** `InputFrameEdges` 同帧同槽写两次 ⇒ 第二次抹掉边沿。
    //      这条就是旧采样器（每设备一次 SampleRow）的形状 —— 用来证明"把采样器还原成旧写法
    //      本文件必红"这件事有据可循（不是靠运气）。
    {
        LuaRuntime::InputFrameEdges edges{};
        bool released[LuaRuntime::InputFrameEdges::kSlots] = {};
        edges.SampleRow(33, 500, released, nullptr);
        bool pressedBits[LuaRuntime::InputFrameEdges::kSlots] = {};
        pressedBits[13] = true;
        edges.SampleRow(33, 501, pressedBits, nullptr);      // 第一次写：报边沿
        Check(edges.Triggered(13, 33, 501), "反证：第一次写同一槽 ⇒ 有边沿");
        edges.SampleRow(1, 501, pressedBits, nullptr);       // 同帧第二次写同一槽（旧形状）
        Check(!edges.Triggered(13, 33, 501),
              "反证：同帧第二次写把边沿抹成 false（这就是本批的根因；旧采样器每帧都这样）");
    }

    lua_close(state);

    if (failures != 0) {
        std::printf("INPUT_SLOT_COLLISION_CHECKS_FAILED %d\n", failures);
        return 1;
    }
    std::printf("INPUT_SLOT_COLLISION_CHECKS_PASSED\n");
    return 0;
}
'''


def host_compiler() -> str | None:
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


class SlotCollisionBehaviourTests(unittest.TestCase):
    """行为（宿主真跑，端到端）：两台同槽手柄 → 真实 `SampleInputFrame` → 模组侧 `Input.*`。"""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-input-slot-collision-")
        cls.binary = build_lua_harness(
            source_root=SOURCE,
            workdir=Path(cls.temporary.name),
            harness_source=HARNESS,
        )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_same_frame_two_devices_in_one_slot_still_report_the_edge(self):
        result = subprocess.run([str(self.binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("INPUT_SLOT_COLLISION_CHECKS_PASSED", result.stdout)
        self.assertNotIn("FAILED_CHECK", result.stdout)


class SlotCollisionWiringTests(unittest.TestCase):
    """接线可见性（源码级）。**不验行为** —— 这一半只保证"每槽每帧最多写一次"。"""

    @classmethod
    def setUpClass(cls):
        cls.input_api = (LUA_DIR / "input_api.cpp").read_text(encoding="utf-8")

    def _sample_input_frame_source(self) -> str:
        start = self.input_api.index("void SampleInputFrame(")
        end = self.input_api.index("void FrameBoundaryHookEntry(", start)
        return self.input_api[start:end]

    def _device_loop_source(self) -> str:
        sampler = self._sample_input_frame_source()
        start = sampler.index("for (std::size_t index = 0;")
        end = sampler.index("for (std::uint32_t slot = 0;")
        return sampler[start:end]

    def test_device_loop_never_writes_a_row(self):
        """★ 每槽每帧最多写一次：**设备循环里不许出现任何 `SampleRow` 调用**
        （同槽的两台设备必须先在循环里 OR 聚合，循环之后才按槽写）。"""
        loop = self._device_loop_source()
        self.assertNotIn("g_ButtonEdge.SampleRow(", loop)
        self.assertNotIn("g_ActionEdge.SampleRow(", loop)

    def test_each_slot_is_written_exactly_once_per_frame(self):
        """★ 每帧对每个槽最多一次 `SampleRow`：整个采样器里按键/动作各只出现两次调用
        —— 一次在"每槽一次"的刷写循环里（用槽变量 `slot`），一次是聚合槽 `kNsAnyInputDevice`。"""
        sampler = self._sample_input_frame_source()
        self.assertEqual(sampler.count("g_ButtonEdge.SampleRow("), 2)
        self.assertEqual(sampler.count("g_ActionEdge.SampleRow("), 2)
        self.assertIn("g_ButtonEdge.SampleRow(slot,", sampler)
        self.assertIn("g_ActionEdge.SampleRow(slot,", sampler)
        # 刷写循环按 `kSlots` 遍历、并用"本帧是否有设备落进这个槽"的旗标守卫。
        self.assertIn("for (std::uint32_t slot = 0; slot < LuaRuntime::InputFrameEdges::kSlots;",
                      sampler)
        self.assertIn("slotPresent[slot]", sampler)

    def test_aggregation_key_is_the_slot(self):
        """★ 聚合键就是槽号（`deviceId & 31`），与查询侧 `EntryAt` 的取槽方式一致。"""
        sampler = self._sample_input_frame_source()
        self.assertIn("InputFrameEdges::kIndexMask", sampler)
        self.assertIn("slotButtonPressed[slot]", sampler)
        self.assertIn("aggButtonPressed", sampler)

    def test_sample_row_still_takes_a_null_edge(self):
        """★ 判定语义不变：`SampleRow` 第三个实参仍是 `nullptr`（边沿由本类按帧自己差分）。

        ★ 采样器的按键/动作缓冲改成了**按槽聚合**（`slotButtonPressed` / `slotActionPressed`）；
        刷写循环里用局部引用 `buttonPressed` / `actionPressed` 指到"本槽"那一行 —— 这样既有批次的
        源码级门禁（按字面钉 `buttonPressed, nullptr)`）不必被动改。
        """
        sampler = self._sample_input_frame_source()
        self.assertIn("buttonPressed, nullptr)", sampler)
        self.assertIn("actionPressed, nullptr)", sampler)
        self.assertIn("aggButtonPressed, nullptr)", sampler)
        self.assertIn("aggActionPressed, nullptr)", sampler)

    def test_any_device_aggregate_row_is_still_all_devices(self):
        """★ `kNsAnyInputDevice`（`0xFFFFFFFF` ⇒ 槽 31）仍是"任一设备按下"：由各设备逐码 OR。"""
        sampler = self._sample_input_frame_source()
        self.assertIn("g_ButtonEdge.SampleRow(kNsAnyInputDevice", sampler)
        self.assertIn("g_ActionEdge.SampleRow(kNsAnyInputDevice", sampler)
        self.assertIn("aggButtonPressed[code] = aggButtonPressed[code] || buttonPressed[code]",
                      sampler)

    def test_queries_are_still_per_device(self):
        """★ 按槽聚合只改**写入**：查询仍**按设备**逐个问引擎（不是退回读位图）。"""
        sampler = self._sample_input_frame_source()
        self.assertIn("LuaRuntime::InputIsButtonPressedThunk()", sampler)
        self.assertIn("deviceId, nullptr)", sampler)
        self.assertNotIn("kKageInputDeviceKeysCurrentOffset", sampler)
        self.assertNotIn("kKageInputDeviceKeysPreviousOffset", sampler)


if __name__ == "__main__":
    unittest.main()
