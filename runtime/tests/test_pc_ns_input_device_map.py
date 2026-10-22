"""PC→NS 手柄号映射表（`pc_ns_input_device_map.hpp`）—— 口径逐条钉在宿主上。

为什么要有它：同一个坑踩了三次（嵌入式模组菜单、主菜单自绘入口、MCM 的"按右摇杆开菜单"）——
PC 模组传 `controllerId = 1`（PC 上"第 1 台手柄"），而 Switch 引擎的设备号里那台手柄是 `33`
⇒ 引擎按 `GetId()` 找不到 ⇒ **恒答 false**，不报错、不崩、什么线索都不留。
真机取证见 `dist/gdb-read-20260930-0030-device-table.txt`（设备表只有 `0`(触摸屏) 与 `33`(手柄)）。

本测试用**合成设备表**把口径钉死（不碰引擎、不碰设备）；真值表那张真机表另外对账。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

HARNESS = r'''
#include "pc_ns_input_device_map.hpp"

#include <cstdio>
#include <cstdint>

using isaac::runtime::IsNsTouchscreenEntry;
using isaac::runtime::kNsAnyInputDevice;
using isaac::runtime::MapPcControllerIdToNsInputDevice;
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
        std::printf("FAIL %s（拿到 kind=%d id=0x%x）\n", label, static_cast<int>(target.kind), id);
        ++failures;
    }
}
constexpr NsDeviceTableState kKnown = NsDeviceTableState::Known;
constexpr NsDeviceTableState kUnknown = NsDeviceTableState::Unknown;
}  // namespace

int main() {
    // ① 真机那张表（2026-09-30 实测）：[0(触摸屏), 33(手柄)]。
    {
        const std::uint32_t table[] = {0u, 33u};
        CheckTarget(MapPcControllerIdToNsInputDevice(1, table, 2, kKnown),
                    NsDeviceSelection::Mapped, 33u, "PC 1 ⇒ 真机上那台手柄 33");
        CheckTarget(MapPcControllerIdToNsInputDevice(0, table, 2, kKnown),
                    NsDeviceSelection::NoSuchDevice, 0u, "PC 0 = 键盘 ⇒ 没有这台");
        for (std::int64_t pc = 2; pc <= 4; ++pc) {
            CheckTarget(MapPcControllerIdToNsInputDevice(pc, table, 2, kKnown),
                        NsDeviceSelection::NoSuchDevice, 0u,
                        "只有一台手柄时 PC 2..4 ⇒ 没有这台（PC 上也是 false）");
        }
    }
    // ② 双人：两张手柄都在表里 ⇒ 1、2 分别命中；第 3 台没有。
    {
        const std::uint32_t table[] = {0u, 1u, 33u};
        CheckTarget(MapPcControllerIdToNsInputDevice(1, table, 3, kKnown),
                    NsDeviceSelection::Mapped, 1u, "双人：PC 1 ⇒ 第一台手柄");
        CheckTarget(MapPcControllerIdToNsInputDevice(2, table, 3, kKnown),
                    NsDeviceSelection::Mapped, 33u, "双人：PC 2 ⇒ 第二台手柄");
        CheckTarget(MapPcControllerIdToNsInputDevice(3, table, 3, kKnown),
                    NsDeviceSelection::NoSuchDevice, 0u, "只有两台 ⇒ PC 3 没有这台");
    }
    // ③ 触摸屏的两条判据：表里第 0 项 / 设备号 0，**取或**（任一成立就算触摸屏）。
    {
        Check(IsNsTouchscreenEntry(0, 33u), "表里第 0 项就算触摸屏（构造顺序最先）");
        Check(IsNsTouchscreenEntry(3, 0u), "设备号 0 就算触摸屏");
        Check(!IsNsTouchscreenEntry(1, 33u), "中间那台手柄不算触摸屏");
        // 只有第 0 项这一条成立时（设备号非 0）也要跳过；只有设备号 0 这条成立时（不在第 0 项）
        // 也要跳过。两种极端都由上面两条判据覆盖。
        const std::uint32_t odd_touch[] = {7u, 33u};
        CheckTarget(MapPcControllerIdToNsInputDevice(1, odd_touch, 2, kKnown),
                    NsDeviceSelection::Mapped, 33u, "触摸屏号不是 0 时靠第 0 项跳过它");
    }
    // ④ NS 原生用法原样透传（我们自己的嵌入式菜单传 33 / 0xFFFFFFFF；0..3、32..35 也在这一档）。
    {
        const std::uint32_t table[] = {0u, 33u};
        CheckTarget(MapPcControllerIdToNsInputDevice(33, table, 2, kKnown),
                    NsDeviceSelection::Passthrough, 33u, "33 是 NS 原生设备号 ⇒ 透传");
        CheckTarget(MapPcControllerIdToNsInputDevice(0xFFFFFFFFLL, table, 2, kKnown),
                    NsDeviceSelection::Passthrough, kNsAnyInputDevice, "0xFFFFFFFF ⇒ 透传（任意设备）");
        CheckTarget(MapPcControllerIdToNsInputDevice(34, table, 2, kKnown),
                    NsDeviceSelection::Passthrough, 34u, "34 ⇒ 透传");
    }
    // ⑤ 设备表读不到 ⇒ 1..4 **原样透传**（= 与修之前一致，不做"任意设备"的静默降级，
    //    因为那会在双人局把别人的手柄算成你的）；调用点会把这种"没能翻译"计数。
    {
        CheckTarget(MapPcControllerIdToNsInputDevice(1, nullptr, 0, kUnknown),
                    NsDeviceSelection::Passthrough, 1u, "表读不到 ⇒ 原样透传（不是任意设备）");
        CheckTarget(MapPcControllerIdToNsInputDevice(4, nullptr, 0, kUnknown),
                    NsDeviceSelection::Passthrough, 4u, "1..4 一律原样透传");
        CheckTarget(MapPcControllerIdToNsInputDevice(0, nullptr, 0, kUnknown),
                    NsDeviceSelection::NoSuchDevice, 0u, "键盘档在表读不到时也是没有这台");
        CheckTarget(MapPcControllerIdToNsInputDevice(33, nullptr, 0, kUnknown),
                    NsDeviceSelection::Passthrough, 33u, "NS 原生值照旧");
    }
    // ⑥ 其它边界：负数 = 没有这台；声称"表读到了"但表是空的 = 没有这台（fail-closed）。
    {
        CheckTarget(MapPcControllerIdToNsInputDevice(-1, nullptr, 0, kKnown),
                    NsDeviceSelection::NoSuchDevice, 0u, "负数 ⇒ 没有这台");
        CheckTarget(MapPcControllerIdToNsInputDevice(1, nullptr, 0, kKnown),
                    NsDeviceSelection::NoSuchDevice, 0u, "表空但声称读到了 ⇒ 没有这台");
        const std::uint32_t touch_only[] = {0u};
        CheckTarget(MapPcControllerIdToNsInputDevice(1, touch_only, 1, kKnown),
                    NsDeviceSelection::NoSuchDevice, 0u, "表里只有触摸屏 ⇒ 没有手柄");
    }

    if (failures != 0) { std::printf("PC_NS_INPUT_DEVICE_MAP_CHECKS_FAILED %d\n", failures); return 1; }
    std::printf("PC_NS_INPUT_DEVICE_MAP_CHECKS_PASSED\n");
    return 0;
}
'''


class PcNsInputDeviceMapTests(unittest.TestCase):
    def test_mapping_rule_on_host(self):
        compiler = next((shutil.which(c) for c in ("c++", "clang++", "g++")
                         if shutil.which(c)), None)
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-pc-ns-device-map-") as directory:
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
            self.assertIn("PC_NS_INPUT_DEVICE_MAP_CHECKS_PASSED", run.stdout)


if __name__ == "__main__":
    unittest.main()
