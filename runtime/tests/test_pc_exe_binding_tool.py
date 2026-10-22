"""门禁：`tools/pc_exe_binding.py`（批次 320，2026-10-03）—— PC 侧"按名字找绑定函数"的**两道校验**。

## 这一批修的是什么

这个工具的核心配方是「`push <函数VA>; push <名字VA>` 成对出现 ⇒ 读名字那条 push 前面那一条」。
但名表里**并不是每一处都成对**（不同 DLC 版本、别的表混在同一片区域），而工具原来
**无条件**读"前 4 字节"，于是产出**移位的假行**：

* `Remove` ⇒ 报出 `0xCC48300`（数据区的垃圾，根本不是代码地址）；
* `Explode` ⇒ 报出 `0x6A0000`（落在 .text 里，但那儿的字节反汇编出来是乱的 ⇒ 不是函数开头）。

★ 这类假行**最坏的地方是它看起来很真**：批次 319 查虚函数时，正是它把方向带偏过一次
（`Remove` 报了个垃圾地址 ⇒ 只能另写脚本按"名字串 VA → `push` 前一条"手工复核）。

## 本批加的两道校验（这条门禁钉住它们）

1. **前一条必须真的是 `push imm32`**（`site - 5` 处是 `0x68`；表里 push 是 5 字节）；
2. **读出来的值必须落在某个段里**（不在任何段 ⇒ 显式跳过）。

两条都不满足时**显式打印"跳过"并说明**，不猜、不静默给一个数。

## 已知仍做不到的（别指望它）

* **判不了"这个地址是不是函数开头"** —— x86 没有符号表，`0x6A0000` 那种"落在 .text 里但
  不是函数"的情况要在**反汇编时人眼认**（读的时候要认得出 `ret`/`int3` 填充）。
  本批只挡掉"落在段外"这一档，`Explode` 那种就是**挡不掉**的一档 —— 所以门禁里对它的断言是
  "不许出现垃圾地址"，而不是"必须找到一个绑定"。
* 同一个名字出现多次（不同版本的表）⇒ 工具**把全部命中都列出来**，由人按反汇编内容判断。
"""

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "pc_exe_binding.py"
EXE = ROOT / "The Binding of Isaac Rebirth" / "isaac-ng.exe"

#: `名字 → 绑定函数 VA`（都是本项目已经手工复核过、写在 `runtime_constants.hpp` 或存档里的）。
#: ★ 每一条都能在下面找到出处：
#:   * `GetDropRNG` `0x412390` —— `lea eax,[ecx+0x334]`（批次 316）；
#:   * `Kill` `0x8604FD`（`jmp [eax+0x24]`）/ `Update` `0x860520`（`jmp [eax+0xc]`）/
#:     `IsBoss` `0x86051B`（`jmp [eax+0x48]`）/ `Remove` `0x860511`（`jmp [eax+0x28]`）
#:     —— 四条都在 `0x8604E0` 起的虚调用跳板表里（批次 319）；
#:   * `IsEnemy` `0x684620` —— **不在**跳板表里的普通函数（批次 319 的反面对照）。
KNOWN_BINDINGS = {
    "GetDropRNG": "0x412390",
    "Kill": "0x8604FD",
    "Update": "0x860520",
    "IsBoss": "0x86051B",
    "Remove": "0x860511",
    "IsEnemy": "0x684620",
}

#: 曾经被工具当成"绑定函数"的垃圾地址（数据区/非函数）—— 现在不许再出现。
BOGUS_ADDRESSES = ("0xCC48300", "0x16A0000", "0x1F4", "0x7E8")


def run_tool(name: str) -> str:
    result = subprocess.run([sys.executable, str(TOOL), name], text=True, capture_output=True,
                            cwd=ROOT)
    return result.stdout + result.stderr


class PcExeBindingToolTests(unittest.TestCase):
    def setUp(self):
        if not EXE.is_file():
            self.skipTest(f"缺少用户提供的 exe：{EXE}")

    def test_known_bindings_are_found(self):
        """六条已复核过的绑定都要报出来，且带上段名（`.text`）。"""
        for name, expected in KNOWN_BINDINGS.items():
            with self.subTest(name=name):
                out = run_tool(name)
                self.assertIn(f"绑定函数 VA {expected}", out,
                              f"{name} 应当报出 {expected}：\n{out}")

    def test_bogus_addresses_are_never_reported(self):
        """★★ 本批的核心：名表错位读出来的垃圾地址**不许**再被当成绑定函数。

        `Explode` 是实测过的那一例（4 处引用全都"不成对"）；`Remove` 那一例现在能正确落到
        `0x860511`（改动前报的是 `0xCC48300`）。
        """
        for name in ("Explode", "Remove", "Spawn"):
            with self.subTest(name=name):
                out = run_tool(name)
                for bogus in BOGUS_ADDRESSES:
                    self.assertNotIn(f"绑定函数 VA {bogus}", out,
                                     f"{name} 报出了垃圾地址 {bogus}：\n{out}")

    def test_uncoupled_entries_are_explained_instead_of_guessed(self):
        """不满足校验的命中要**显式说"跳过"**（不是静默丢掉、也不是硬给一个数）。"""
        out = run_tool("Explode")
        self.assertIn("跳过", out, out)

    def test_every_reported_binding_lives_in_a_section(self):
        """每一条报出来的绑定都必须带段名（= 它真的落在某个段里）。"""
        for name in ("GetDropRNG", "Update", "Kill"):
            with self.subTest(name=name):
                out = run_tool(name)
                for line in out.splitlines():
                    if "绑定函数 VA" in line:
                        self.assertRegex(line, r"\[\.\w+\]",
                                         f"这一行没带段名：{line}")

    def test_unknown_name_is_reported(self):
        """名字拼错 ⇒ 报错（不是静默空输出）。"""
        result = subprocess.run([sys.executable, str(TOOL), "NoSuchApiNameForSure"],
                                text=True, capture_output=True, cwd=ROOT)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("没有逐字等于", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
