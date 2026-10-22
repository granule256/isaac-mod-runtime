"""批次 407：**同一台物理手柄对多个 PC 手柄号答 true** —— 映射结果按槽去重。

## 病根（真机探针定案，别再重新论证）

中文版 MCM 的"按右摇杆开菜单"判定（`modconfig.lua:2172-2181`）是：

```lua
for i = 0, 4 do
    if keyboardToggled or (openMenuController > -1 and Input.IsButtonTriggered(openMenuController, i)) then
        pressingNonRebindableKey = true
        pressedToggleMenu = true
        if not configMenuInPopup then
            ModConfigMenu.ToggleConfigMenu()   -- ★ 命中一次就 toggle 一次
        end
    end
end
```

真机探针（与 MCM 同一条回调、同一时点）读出 `IsButtonTriggered(13, 1)` 与 `IsButtonTriggered(13, 2)`
**同时为 true**（屏上锁存值 `U[1,2] R[1,2]`）⇒ 循环**命中两次** ⇒ 同一帧里
`ToggleConfigMenu()` **两次（先开、再立刻关）** ⇒ 屏幕上什么都没有、也没有声音。
独立佐证：`Seeds:AddSeedEffect` 计数 = 18（只在 `OpenConfigMenu()` 里）⇒ `OpenConfigMenu()` 真跑了 18 次、
每次都被立刻关掉。

为什么是 `i=1` 与 `i=2` 同时真：真机设备表里**同一台物理手柄**出现了两个设备号 ——
引擎手柄号 = `NpadId + 1`（候选表 `{0..7,32}`）⇒ 设备号 ∈ {1..8, 33..40}；`1` 与 `33` 相差 **32**
⇒ `1 & 31 == 33 & 31 == 1`，**落进同一个槽**（"槽撞位"是批次 406 修的另一面）。

## 修法（批次 407，最小）

新增一个**纯的去重包装** `MapPcControllerIdToNsInputDeviceDeduped`（在 `pc_ns_input_device_map.hpp`）：

* `i` 映射到的设备号若与**更小的某个 `i`** 映射到的设备号**落进同一个槽**（`设备号 & 31` 相同）
  ⇒ 本档返回 `NoSuchDevice`（"这一档不存在" ⇒ 调用方拿 `false`，与 PC 上"第 k 台手柄没插"同形）；
* 判据是**同槽**，不是"同物理"：真的插了两台**不同**手柄（如 `1`、`2`）时它们**不同槽** ⇒ 仍各自
  命中（**不砍玩家 2**，PC 语义保留）；**也别**简化成"永远只允许 `i=1`"。
* 底层纯函数 `MapPcControllerIdToNsInputDevice` 的口径**不变**（只做"`i` ⇒ 第 `i` 台手柄"）；
  去重是**查询层**的一条策略，`ResolveInputDevice*` 用包装函数 —— 动作侧共用同一入口 ⇒ 一并受益。

## 本文件的门禁（先红后绿）

1. **同槽别名去重**：表 `{0,1,33}`（真机形状）⇒ `i=1` 命中、`i=2` 返回 `NoSuchDevice`；
   且 `for i = 0, 4` 里**恰好只有一次命中**。★ **把去重关掉时这条必红**（`i=2` 会命中 ⇒ 两次）。
2. **不同槽的两台真手柄仍各自命中**：表 `{0,1,2}` ⇒ `i=1`、`i=2` 都命中（别把玩家 2 砍掉）。
3. `i=0`（键盘档）仍 `NoSuchDevice`；`-1` 仍 `NoSuchDevice`；`0xFFFFFFFF` / `33` 仍原样透传。
4. 批次 406 的"**每槽每帧最多一次 `SampleRow`**"仍绿（源码级）：采样器里按键/动作各只两次调用、
   第三个实参仍 `nullptr`、按 `slot` 刷写。另有**接线**断言：`ResolveInputDeviceQuiet` 走的是
   去重版包装函数（六条按键/动作处理器共用它）。

★ 为什么去重放在**包装函数**而不是直接改纯 `Map`：`Map` 的口径被 `test_pc_ns_input_device_map.py`
逐条钉住（含 `{0,1,33}` ⇒ `i=2` 仍能翻到第 2 台那条）—— 那条门禁的文件名含 `input`、被本批的
硬约束禁止改动，且"纯换算 vs 查询层策略"分层更清楚。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
SRC = ROOT / "runtime" / "src"
LUA_DIR = SRC / "interfaces" / "lua"

HARNESS = r'''
#include "pc_ns_input_device_map.hpp"

#include <cstdio>
#include <cstdint>

using isaac::runtime::kNsAnyInputDevice;
using isaac::runtime::kNsInputDeviceSlotMask;
using isaac::runtime::MapPcControllerIdToNsInputDevice;
using isaac::runtime::MapPcControllerIdToNsInputDeviceDeduped;
using isaac::runtime::NsDeviceSelection;
using isaac::runtime::NsDeviceTableState;
using isaac::runtime::NsDeviceTarget;

namespace {
int failures = 0;
void Check(bool condition, const char* label) {
    if (!condition) { std::printf("FAIL %s\n", label); ++failures; }
}
void CheckTarget(const NsDeviceTarget& target, NsDeviceSelection kind, std::uint32_t id,
                 const char* label) {
    if (target.kind != kind || target.device_id != id) {
        std::printf("FAIL %s（拿到 kind=%d id=0x%x）\n", label, static_cast<int>(target.kind),
                    target.device_id);
        ++failures;
    }
}
constexpr NsDeviceTableState kKnown = NsDeviceTableState::Known;
constexpr NsDeviceTableState kUnknown = NsDeviceTableState::Unknown;

// "命中" = 调用方会拿到 true（去重版只会把 Mapped 降成 NoSuchDevice；Passthrough 只在"表读不到"）。
bool Hits(std::int64_t pc, const std::uint32_t* table, std::size_t count) {
    return MapPcControllerIdToNsInputDeviceDeduped(pc, table, count, kKnown).kind ==
           NsDeviceSelection::Mapped;
}
}  // namespace

int main() {
    // ① 同槽别名去重（真机形状：设备号 1 与 33 相差 32 ⇒ 同槽 1）。
    {
        const std::uint32_t table[] = {0u, 1u, 33u};
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(1, table, 3, kKnown),
                    NsDeviceSelection::Mapped, 1u, "① PC 1 仍命中第一台手柄");
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(2, table, 3, kKnown),
                    NsDeviceSelection::NoSuchDevice, 0u,
                    "①★ PC 2 = 第一台的别名（同槽 1）⇒ NoSuchDevice（答 false）");
        int hits = 0;
        for (std::int64_t pc = 0; pc <= 4; ++pc) {
            if (Hits(pc, table, 3)) { ++hits; }
        }
        Check(hits == 1, "①★ for i=0,4 里恰好只有一次命中（MCM 只会 toggle 一次）");
    }
    // ①b 表里顺序反过来（先 33 后 1）也恰好一次命中：命中的是表里**更早**的那台。
    {
        const std::uint32_t table[] = {0u, 33u, 1u};
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(1, table, 3, kKnown),
                    NsDeviceSelection::Mapped, 33u, "①b 先 33：PC 1 ⇒ 设备 33");
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(2, table, 3, kKnown),
                    NsDeviceSelection::NoSuchDevice, 0u, "①b 后 1 是同槽别名 ⇒ NoSuchDevice");
        int hits = 0;
        for (std::int64_t pc = 0; pc <= 4; ++pc) {
            if (Hits(pc, table, 3)) { ++hits; }
        }
        Check(hits == 1, "①b 恰好一次命中（与表里顺序无关）");
    }
    // ①c 去重是**按槽**、不是"只允许 i=1"：别名之后再放一台**不同槽**的真手柄（2）⇒ 它仍命中。
    {
        const std::uint32_t table[] = {0u, 1u, 33u, 2u};
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(1, table, 4, kKnown),
                    NsDeviceSelection::Mapped, 1u, "①c PC 1 ⇒ 设备 1");
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(2, table, 4, kKnown),
                    NsDeviceSelection::NoSuchDevice, 0u, "①c PC 2 = 同槽别名 ⇒ NoSuchDevice");
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(3, table, 4, kKnown),
                    NsDeviceSelection::Mapped, 2u,
                    "①c★ 表里另一台**不同槽**的手柄（2）仍命中（没砍玩家 2）");
    }
    // ② 不同槽的两台真手柄**各自命中**（别把玩家 2 砍掉）。
    {
        const std::uint32_t table[] = {0u, 1u, 2u};
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(1, table, 3, kKnown),
                    NsDeviceSelection::Mapped, 1u, "② PC 1 ⇒ 设备 1");
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(2, table, 3, kKnown),
                    NsDeviceSelection::Mapped, 2u,
                    "②★ PC 2 ⇒ 设备 2（不同槽，玩家 2 保留）");
        int hits = 0;
        for (std::int64_t pc = 0; pc <= 4; ++pc) {
            if (Hits(pc, table, 3)) { ++hits; }
        }
        Check(hits == 2, "② 恰好两次命中（i=1、i=2）");
    }
    // ②b 单手柄时 2..4 仍是"没有这台"（PC 上也是 false）。
    {
        const std::uint32_t table[] = {0u, 33u};
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(1, table, 2, kKnown),
                    NsDeviceSelection::Mapped, 33u, "②b 单手柄（33）命中");
        for (std::int64_t pc = 2; pc <= 4; ++pc) {
            CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(pc, table, 2, kKnown),
                        NsDeviceSelection::NoSuchDevice, 0u, "②b 单手柄时 PC 2..4 没有这台");
        }
    }
    // ③ 键盘档 / 负数 / 透传 语义不变（去重只作用在"翻到某台手柄"的档上）。
    {
        const std::uint32_t table[] = {0u, 33u};
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(0, table, 2, kKnown),
                    NsDeviceSelection::NoSuchDevice, 0u, "③ PC 0 = 键盘 ⇒ 没有这台");
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(-1, nullptr, 0, kKnown),
                    NsDeviceSelection::NoSuchDevice, 0u, "③ 负数 ⇒ 没有这台");
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(0xFFFFFFFFLL, table, 2, kKnown),
                    NsDeviceSelection::Passthrough, kNsAnyInputDevice, "③ 0xFFFFFFFF ⇒ 透传（任意设备）");
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(33, table, 2, kKnown),
                    NsDeviceSelection::Passthrough, 33u, "③ 33 ⇒ 透传（NS 原生设备号）");
    }
    // ④ 表读不到（Unknown）⇒ i=1..4 仍原样透传，**不做**去重（去重的输入是设备表）。
    {
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(2, nullptr, 0, kUnknown),
                    NsDeviceSelection::Passthrough, 2u, "④ 表读不到 ⇒ i=2 原样透传（不去重）");
        CheckTarget(MapPcControllerIdToNsInputDeviceDeduped(0, nullptr, 0, kUnknown),
                    NsDeviceSelection::NoSuchDevice, 0u, "④ 键盘档在表读不到时也是没有这台");
    }
    // ⑤ 底层纯函数的口径**没变**（被 test_pc_ns_input_device_map.py 钉住）：`{0,1,33}` ⇒ i=2 仍能翻到。
    {
        const std::uint32_t table[] = {0u, 1u, 33u};
        CheckTarget(MapPcControllerIdToNsInputDevice(2, table, 3, kKnown),
                    NsDeviceSelection::Mapped, 33u,
                    "⑤ 纯 Map 不变：i=2 ⇒ 33（去重在包装层，分层清楚）");
    }
    // ⑥ 槽掩码与 `InputFrameEdges::kIndexMask` 同口径（31）。
    Check(kNsInputDeviceSlotMask == 31u, "⑥ 槽掩码 = 31（与边沿表入槽方式一致）");

    if (failures != 0) {
        std::printf("INPUT_PAD_ALIAS_DEDUPE_CHECKS_FAILED %d\n", failures);
        return 1;
    }
    std::printf("INPUT_PAD_ALIAS_DEDUPE_CHECKS_PASSED\n");
    return 0;
}
'''


def host_compiler() -> str | None:
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return None


class PadAliasDedupeBehaviourTests(unittest.TestCase):
    """行为（宿主真跑）：去重包装函数 `MapPcControllerIdToNsInputDeviceDeduped` 的口径逐条钉死。"""

    def test_alias_dedupe_on_host(self):
        compiler = host_compiler()
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-pad-alias-dedupe-") as directory:
            workdir = Path(directory)
            source = workdir / "harness.cpp"
            source.write_text(HARNESS.lstrip(), encoding="utf-8")
            binary = workdir / "harness"
            build = subprocess.run(
                [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE),
                 str(source), "-o", str(binary)],
                text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("INPUT_PAD_ALIAS_DEDUPE_CHECKS_PASSED", run.stdout)
            self.assertNotIn("FAIL ", run.stdout)


class PadAliasDedupeWiringTests(unittest.TestCase):
    """接线可见性（源码级）：去重包装被查询层用上，且批次 406 的"每槽一次"没回退。"""

    @classmethod
    def setUpClass(cls):
        cls.header = (SOURCE / "pc_ns_input_device_map.hpp").read_text(encoding="utf-8")
        cls.input_api = (LUA_DIR / "input_api.cpp").read_text(encoding="utf-8")

    def test_dedupe_wrapper_exists_and_uses_the_slot_mask(self):
        self.assertIn("MapPcControllerIdToNsInputDeviceDeduped", self.header)
        self.assertIn("kNsInputDeviceSlotMask = 31u", self.header)
        self.assertIn("target.device_id & kNsInputDeviceSlotMask", self.header)
        # 纯函数仍在（去重是包装层、不是替换）。
        self.assertIn("MapPcControllerIdToNsInputDevice(", self.header)

    def test_resolve_uses_the_deduped_wrapper(self):
        """★ 六条按键/动作处理器共用的解析入口必须走**去重**版。"""
        start = self.input_api.index("ResolvedInputDevice ResolveInputDeviceQuiet(")
        end = self.input_api.index("ResolvedInputDevice ResolveInputDevice(", start)
        resolved = self.input_api[start:end]
        self.assertIn("MapPcControllerIdToNsInputDeviceDeduped(", resolved)
        self.assertNotIn("MapPcControllerIdToNsInputDevice(\n", resolved)

    def test_batch406_per_slot_single_write_still_holds(self):
        """★ 批次 406 的"每槽每帧最多一次 `SampleRow`"不许回退。"""
        start = self.input_api.index("void SampleInputFrame(")
        end = self.input_api.index("void FrameBoundaryHookEntry(", start)
        sampler = self.input_api[start:end]
        self.assertEqual(sampler.count("g_ButtonEdge.SampleRow("), 2)
        self.assertEqual(sampler.count("g_ActionEdge.SampleRow("), 2)
        self.assertIn("g_ButtonEdge.SampleRow(slot,", sampler)
        self.assertIn("slotPresent[slot]", sampler)
        # 第三个实参仍是 `nullptr`（`Triggered` 仍纯读）。
        self.assertIn("buttonPressed, nullptr)", sampler)
        self.assertIn("actionPressed, nullptr)", sampler)
        self.assertIn("aggActionPressed, nullptr)", sampler)


if __name__ == "__main__":
    unittest.main()
