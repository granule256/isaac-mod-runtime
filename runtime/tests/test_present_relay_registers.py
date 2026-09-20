"""门禁：`Present` 的 GOT 槽转发桩必须**保存并还原全部参数寄存器**。

## 为什么要有它

这条 GOT 槽被 **43 处调用共用**（见 `runtime_constants.hpp` 的 `kManagerPresentStubOffset`
一带注释），所以转发桩不能假设"实参只在 `x0`~`x7`"：

* 2026-09-17 之前的实现是一个 C 函数，靠 `x0`~`x7` 收参数再转发 ——
  浮点/向量实参（`v0`~`v7`）一进我们代码就被编译器破坏，间接结果寄存器 `x8` 同样不保证；
* `docs/开发规范.md` 第 11 条明确要求这类"调用回调后继续执行原函数"的 AArch64 转发
  **逐项验证被保存的寄存器**；
* 而 09-17 悬而未决的那个崩溃（"模组全关时主界面停 ~10 秒崩 / 退出对局必崩"）里，
  这个桩是头号嫌疑 —— 它是五个可选挂点里唯一"由我们用 C 代码替游戏转发参数"的。

所以门禁把要求写成可核对的判据：**存了哪些、还原了哪些、怎么跳回去**。

同时钉住"桩必须是非静态全局符号"（安装时要把它的地址写进 GOT 槽）。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK_MANAGER = ROOT / "runtime" / "source" / "hook_manager.cpp"

STUB_SYMBOL = "IsaacModRuntime_PresentGotSlotIntercept"

#: 进入时必须保存、退出前必须还原的参数寄存器（通用 + 向量 + 返回地址）。
GENERAL_PAIRS = [("x0", "x1"), ("x2", "x3"), ("x4", "x5"), ("x6", "x7")]
VECTOR_PAIRS = [("q0", "q1"), ("q2", "q3"), ("q4", "q5"), ("q6", "q7")]


def stub_body(source: str) -> str:
    """取出 asm 桩那段字符串（从 `.globl <符号>` 到 `.size`）。"""
    begin = source.find(f'.globl {STUB_SYMBOL}')
    if begin < 0:
        raise AssertionError(f"hook_manager.cpp 里找不到 {STUB_SYMBOL} 的汇编桩")
    end = source.find(f'.size {STUB_SYMBOL}', begin)
    if end < 0:
        raise AssertionError("汇编桩没有以 .size 收尾")
    return source[begin:end]


class PresentRelayRegisterTests(unittest.TestCase):
    def test_stub_saves_and_restores_every_argument_register(self):
        source = HOOK_MANAGER.read_text(encoding="utf-8")
        body = stub_body(source)
        # 取"操作码 → 内存操作数"之间的寄存器列表：`stp x0, x1, [sp, #0x00]` ⇒ ("stp", "x0, x1")
        operations = re.findall(r"\b(stp|ldp|str|ldr)\s+(.+?)\s*,\s*\[", body)

        saved = {(op, regs.strip()) for op, regs in operations}
        for first, second in GENERAL_PAIRS:
            for op in ("stp", "ldp"):
                self.assertIn((op, f"{first}, {second}"), saved,
                              f"{op} {first},{second} 缺失（通用参数寄存器必须存/还原）")
        for op in ("str", "ldr"):
            self.assertIn((op, "x8"), saved, f"{op} x8 缺失（间接结果寄存器）")
            self.assertIn((op, "x30"), saved, f"{op} x30 缺失（返回地址）")
        for first, second in VECTOR_PAIRS:
            for op in ("stp", "ldp"):
                self.assertIn((op, f"{first}, {second}"), saved,
                              f"{op} {first},{second} 缺失（向量参数寄存器必须存/还原）")

    def production_source(self) -> str:
        """把**只用于对照**的 `EXL_LEGACY_PRESENT_FORWARDER` 区块剥掉，只留正式路径。

        为什么必须剥：那个区块里保留着"用 C 按 x0~x7 重建调用"的旧形态（2026-09-17 加，
        用于单变量对照）。它包在开关里、默认不参与编译；但本门禁检查的是**正式形状**。
        """
        source = HOOK_MANAGER.read_text(encoding="utf-8")
        begin = source.find("#if defined(EXL_LEGACY_PRESENT_FORWARDER)")
        if begin < 0:
            return source
        end = source.find("#else", begin)
        if end < 0:
            raise AssertionError("对照区块没有 #else（形状不对，无法定位正式路径）")
        # 保留 #else 之后的**正式路径**（asm 桩在里面），只丢掉对照形态。
        return source[:begin] + source[end + len("#else"):]

    def test_legacy_comparison_block_stays_guarded(self):
        """对照代码必须**包在开关里**（默认 0 = 不参与编译），不许裸露在正式路径上。"""
        source = HOOK_MANAGER.read_text(encoding="utf-8")
        begin = source.find("#if defined(EXL_LEGACY_PRESENT_FORWARDER)")
        self.assertGreaterEqual(begin, 0, "找不到对照区块的开关守卫")
        block = source[begin:]
        self.assertIn("#else", block, "对照区块必须有 #else（正式形状放在 #else 里）")
        self.assertIn("#endif", block, "对照区块必须有 #endif")
        legacy_part = block[: block.index("#else")]
        self.assertIn("PresentFn", legacy_part, "对照区块里应当就是旧的 C 转发形态")

    def test_stub_does_not_reconstruct_a_call(self):
        source = self.production_source()
        body = stub_body(source)
        # 必须尾跳（br），不能"调过去再回来"（bl）—— 尾跳才能让 Present 直接返回原调用点。
        self.assertIn("br x9", body, "桩必须用 `br` 尾跳到真正的 Present")
        self.assertNotIn("bl x9", body, "桩不可以用 `bl` 调用 Present（那会多压一层返回地址）")
        # 正式路径里不该再出现"按 x0..x7 重建调用"的 C 侧函数类型。
        self.assertNotIn("PresentFn", source,
                         "正式路径不该出现按 x0..x7 重建 Present 调用的函数类型"
                         "（对照区块已剥掉；若这里是红的，说明旧形态漏进了正式路径）")

    def test_stack_frame_is_16_byte_aligned(self):
        source = HOOK_MANAGER.read_text(encoding="utf-8")
        body = stub_body(source)
        adjusts = re.findall(r"(sub|add) sp, sp, #(0x[0-9a-fA-F]+|\d+)", body)
        self.assertEqual(len(adjusts), 2, f"栈调整应当恰好一对（sub + add），实际 {adjusts}")
        values = {int(value, 0) for _, value in adjusts}
        self.assertEqual(len(values), 1, f"进出栈的调整量必须一致，实际 {adjusts}")
        size = values.pop()
        self.assertEqual(size % 16, 0, f"栈调整 {size:#x} 不是 16 的倍数（AAPCS 要求 SP 对齐）")
        # 至少要装得下 x0~x8（9×8）+ q0~q7（8×16）+ LR（8）
        self.assertGreaterEqual(size, 9 * 8 + 8 * 16 + 8, "栈帧装不下要保存的寄存器")

    def test_symbol_is_global_and_addressable(self):
        source = HOOK_MANAGER.read_text(encoding="utf-8")
        body = stub_body(source)
        self.assertIn(f".globl {STUB_SYMBOL}", body, "桩必须是全局符号（安装时要取它的地址）")
        self.assertIn("&" + STUB_SYMBOL, source, "安装代码必须取这个符号的地址写进 GOT 槽")
        # 桩本身只声明、不定义（定义在汇编里），避免 C++ 再生成一份体。
        declaration = re.search(
            rf'extern "C" void {STUB_SYMBOL}\(void\);', source
        )
        self.assertIsNotNone(declaration, "桩应当只有 `extern \"C\" void f(void);` 这样一条声明")


if __name__ == "__main__":
    unittest.main()
