"""门禁（L4 钩子隔离·甲案）：C++ 异常抛出位置的记录设施。

## 背景（用户 2026-09-29 在甲/乙/丙三案中选定"甲"）

`docs/问题记录-画面卡死-20260924.md` 把"画面卡死、音乐还在、没有崩溃报告"的三类嫌疑
（Lua 无保护抛错 / 未捕获 C++ 异常 / 断言）分开的唯一办法是**记下发生的位置**。
批次 099 的 `fatal_forensics.hpp` 只报"`std::terminate` 被调的那一刻"，报不出**异常从哪抛**。
本设施的职责就是补这一半。

**为什么是"甲案"**：只在链接期用 `-Wl,--wrap=__cxa_throw` 重定向**我们模块内部**的调用，
**不导出任何全局同名符号**（`abort` 那个乙案会改变游戏侧同名符号的解析方式，用户选的是甲）。

## 判据

1. **链接层真的有 `--wrap=__cxa_throw`**（少了它就等于设施没接上，且**静默** —— 不报错）。
2. **实现文件在模块构建里**（顶层 `source/*.cpp` 必须显式登记，见 `test_source_program_wrappers`）。
3. **不导出全局同名符号**：实现里不许定义 `__cxa_throw` / `abort` / `std::terminate` 的同名符号。
4. **记录动作是最小的**：不许在抛出路径里分配内存 / 打日志 / 加锁。
5. **读数工具认得它**（符号进了 `SYMS`，否则真机上读不到）。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
COMMON_MK = ROOT / "runtime" / "misc" / "mk" / "common.mk"
IMPLEMENTATION = SOURCE / "throw_forensics.cpp"
READER = ROOT / "tools" / "read_device_state_via_gdb.py"


class ThrowForensicsTests(unittest.TestCase):
    def test_linker_wraps_cxa_throw(self):
        common = COMMON_MK.read_text(encoding="utf-8")
        self.assertIn("-Wl,--wrap=__cxa_throw", common,
                      "链接层必须有 `--wrap=__cxa_throw`，否则抛出位置记录设施根本没接上（且静默）")

    def test_implementation_is_in_module_build(self):
        common = COMMON_MK.read_text(encoding="utf-8")
        self.assertIn("CPPFILES += throw_forensics.cpp", common,
                      "顶层 source/*.cpp 必须显式登记，否则永远不会被编译")

    def test_has_no_program_wrapper(self):
        """★ 踩过的坑（2026-09-29 实测构建失败）：**显式登记与 program 包装不能同时存在**。

        `source/` 顶层文件由 `CPPFILES +=` 显式收；而 `source/program/<同名>.cpp` 那个包装
        会让同一个 TU 再被编一遍 ⇒ 链接期 `multiple definition`。
        `eh_frame_registration.cpp` 是"只显式登记、不写包装"的既有样板，本文件照它。
        """
        wrapper = SOURCE / "program" / "throw_forensics.cpp"
        self.assertFalse(wrapper.exists(),
                         "有了 `CPPFILES +=` 显式登记就不许再加 `source/program/` 包装 —— 两者同时存在会 multiple definition")

    def test_does_not_export_same_named_globals(self):
        """甲案的边界：只做链接期重定向，**不定义** libstdc++/newlib 的同名符号。"""
        text = IMPLEMENTATION.read_text(encoding="utf-8")
        for forbidden in ('void __cxa_throw(', 'void abort(', 'void _ZSt9terminatev('):
            self.assertNotIn(forbidden, text,
                             f"甲案不许定义 {forbidden!r}（那会改变游戏侧同名符号的解析方式）")

    def test_wrapper_records_and_forwards(self):
        text = IMPLEMENTATION.read_text(encoding="utf-8")
        self.assertIn("__wrap___cxa_throw", text)
        self.assertIn("__real___cxa_throw", text,
                      "记录之后必须原样转发给真实现（否则等于把异常吞了）")
        self.assertIn("__builtin_return_address(0)", text,
                      "要记的是**抛出点**，它就是返回地址")

    def test_record_path_stays_minimal(self):
        """抛出路径里不许分配 / 加锁 / 打日志（在异常路径上做这些会再抛）。"""
        text = IMPLEMENTATION.read_text(encoding="utf-8")
        wrapper = text[text.index("__wrap___cxa_throw("):]
        for forbidden in ("new ", "malloc", "std::vector", "mutex", "printf", "std::string"):
            self.assertNotIn(forbidden, wrapper,
                             f"抛出路径里不许出现 {forbidden!r}（不许分配 / 加锁 / 打日志）")

    def test_reader_knows_the_symbols(self):
        reader = READER.read_text(encoding="utf-8")
        self.assertIn("g_throw_forensics", reader, "读数工具必须认得这个符号，否则真机上读不到")
        self.assertIn("throw_forensics", reader)

    def test_reader_actually_prints_the_reading(self):
        """★ 2026-09-29 上卡前发现的缺口：批次 196 只把符号接进了读数工具的**读取列表**、
        **漏了打印那一段** ⇒ 真机验收时"读得到却看不见"，这一项等于没测。

        只接读取、不接输出，与"设施做了、判据没接"是同一种错误 —— 这条门禁把它钉住，
        下一个加诊断量的人会在这里被拦下。"""
        reader = READER.read_text(encoding="utf-8")
        self.assertIn("values.get('throw_forensics')", reader,
                      "读数工具必须把 throw_forensics 打印出来（`values.get('throw_forensics')`），"
                      "否则真机验收时这一段看不见")


if __name__ == "__main__":
    unittest.main()