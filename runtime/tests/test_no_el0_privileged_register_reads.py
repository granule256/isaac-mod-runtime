"""门禁：**EL0 能读的系统寄存器只有白名单里那几个**（批次 082 起，085 改成白名单）。

## 为什么有这条门禁（两次真机崩溃换来的）

1. **批次 081**：为量"EID 描述显示时掉帧"，把"每 tick 多少 Hz"的读放进了启动路径。
   真机上游戏**进不去**。当时的归因是"`cntfrq_el0` 在 EL0 会陷入"，并**顺手写下**
   "`cntvct_el0`（计数器本身）在 EL0 可读（实测可用）"——**后半句是错的**。
2. **批次 085**：常驻性能面重新上机后，游戏在"快进主界面但还没进"处崩。
   报告 `dist/crash-20260919/01789827875_010021c000b6a000.log` 里
   `PC = runtime + 0x1d354`，反汇编那一行正是 **`mrs x3, cntvct_el0`**。
   一条 `mrs` 不访问内存，它唯一会出错的方式就是"**该寄存器在 EL0 被禁止读**"。

⇒ 这条门禁**不能再只盯一个寄存器名**（082 的形态只拦 `cntfrq_el0`，真凶 `cntvct_el0`
从它眼皮底下走过去了）。现在改成**白名单**：我们自己的代码里 `mrs` 只许读下面那几个寄存器，
出现别的就判红，判红信息里附上两次事故的来龙去脉。

## 白名单（每个都要有真机依据）

| 寄存器 | 为什么可以读 |
| --- | --- |
| `cntpct_el0` | **物理**自由运行计数器。Atmosphère 自己的 `TickManagerImpl`（`runtime/source/nn/os/impl/os_tick_manager_impl.os.horizon.hpp`）与 libnx 的 `armGetSystemTick()` 都在 EL0 读它，且它们是真机上天天跑的代码 |
| `tpidrro_el0` | 本模块一直在用（读线程本地存储），真机上跑通过 |
| `ctr_el0` | libnx 的缓存操作指令序列（`runtime/source/lib/nx/arm/cache.s`）在读它，那些函数在真机上被调用过 |

**两个被明确禁止的**（白名单之外，且都有事故背景）：

* `cntvct_el0`（**虚拟**计数器）—— 085 那次真机崩溃就是它；
* `cntfrq_el0`（频率）—— 081 那次事故的嫌疑，而它的值根本不需要问（Tegra X1 恒 19.2 MHz，
  Atmosphère 自己也是硬编码 `TicksPerSecond = 19'200'000`）。

注释里出现寄存器名**不算违规**（本项目的注释就在解释这条教训），只查真正的 `mrs` 指令。
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime"

#: 允许在 EL0 读的系统寄存器（小写比较）。加新的一项必须像上表那样写清真机依据。
ALLOWED = {
    "cntpct_el0": "物理计数器；Atmosphère TickManagerImpl 与 libnx armGetSystemTick 都在 EL0 读",
    "tpidrro_el0": "线程本地存储；本模块一直在用，真机跑通",
    "ctr_el0": "缓存几何；libnx 的 cache.s 在读，真机上被调用过",
}

#: `mrs <Xt>, <systemreg>` —— 只要第二个操作数。
MRS = re.compile(r"\bmrs\s+[^,;]+,\s*([A-Za-z0-9_]+)")

#: 被明确点名过的两个寄存器，判红时用来附上事故说明。
KNOWN_BAD = {
    "cntvct_el0": (
        "虚拟计数器 —— 批次 085 真机崩溃就在这里："
        "`dist/crash-20260919/01789827875_010021c000b6a000.log` 的 `PC = runtime + 0x1d354` "
        "反汇编出来正是 `mrs x3, cntvct_el0`。请改用 `cntpct_el0`"
    ),
    "cntfrq_el0": (
        "频率寄存器 —— 批次 081 把它放进启动路径后真机进不去；值恒为 19.2 MHz，"
        "请直接用常量（`RuntimePerfTicksPerSecond()` / `kEngineGuardFallbackTicksPerSecond`）"
    ),
}

#: 只扫我们自己的代码（vendored 的 exlaunch / third_party 不进这条门禁）。
EXCLUDED_PARTS = {"exlaunch", "third_party"}
SOURCE_SUFFIXES = {".hpp", ".cpp", ".h", ".s", ".S"}


def strip_comments(text: str) -> list[str]:
    """去掉块注释与行注释后按行返回 —— 注释里提寄存器名是允许的。

    只做"够用"的处理：asm 里不会出现 `//`，也不需要照顾字符串里的 `/*`。
    """
    without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return [line.split("//", 1)[0] for line in without_block.splitlines()]


class NoPrivilegedEl0RegisterReads(unittest.TestCase):
    def test_only_whitelisted_system_registers_are_read(self):
        offenders: list[str] = []
        for path in sorted(
            p
            for p in RUNTIME.rglob("*")
            if p.suffix in SOURCE_SUFFIXES and not (EXCLUDED_PARTS & set(p.parts))
        ):
            for index, line in enumerate(strip_comments(path.read_text(encoding="utf-8", errors="replace"))):
                match = MRS.search(line)
                if match is None:
                    continue
                register = match.group(1).lower()
                if register in ALLOWED:
                    continue
                reason = KNOWN_BAD.get(register, "不在白名单里：没有它能在 EL0 读的真机依据")
                offenders.append(
                    f"{path.relative_to(ROOT)}:{index + 1}: {line.strip()}\n    ↳ {register}：{reason}"
                )
        self.assertEqual(
            offenders, [],
            "这些 `mrs` 读了 EL0 读不到的系统寄存器（批次 081/085 两次真机崩溃都由此而来）。\n"
            "白名单：" + "、".join(sorted(ALLOWED)) + "\n" + "\n".join(offenders),
        )

    def test_perf_surface_timestamps_with_the_physical_counter(self):
        """性能面的时间戳只能来自 `cntpct_el0`（防止有人"顺手"改回虚拟计数器）。"""
        text = (RUNTIME / "src" / "interfaces" / "lua" / "runtime_perf.hpp").read_text(encoding="utf-8")
        reads = [m.group(1).lower() for line in strip_comments(text) for m in [MRS.search(line)] if m]
        self.assertEqual(
            reads, ["cntpct_el0"],
            "`runtime_perf.hpp` 里 `RuntimePerfTick()` 必须且只能读 `cntpct_el0`；"
            f"现在读到的是 {reads}（`cntvct_el0` 在 EL0 会被禁止读，批次 085 真机崩溃过）",
        )


if __name__ == "__main__":
    unittest.main()
