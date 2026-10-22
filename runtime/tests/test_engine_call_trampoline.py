"""门禁：**通用引擎调用跳板**（`runtime/src/interfaces/lua/engine_call_trampoline.s`）。

## 为什么有这条门禁（2026-09-19 批次 055）

数据行机制（`test_engine_method_rows.py`）此前只能覆盖共享处理器里**写死的那几种 C++ 签名**，
换一种参数表就要再写一个 `case` ⇒ "加 API 又要花代码段"。跳板把"装参数"从编译期签名变成
运行期动作：调用方把整数/指针/布尔放进一个数组、浮点放进另一个数组，跳板按 AAPCS64 装进
`x0..x7` 与 `d0..d7` 再 `blr`。于是往后的签名组合只花数据行。

**这条测试是跳板唯一的直接证据**：跳板是汇编、又只在真机上用，没有它就只能靠"真机上没出问题"
来推断。做法是在宿主机（Apple Silicon / aarch64 Linux）上编译**真实实现**，用一批签名各异的
假引擎方法按 ABI 调进去，逐条核对"被调函数看到的参数"与"跳板回填的返回值"。

## 断言口径

1. 接收者进 `x0`，整数/指针参数**按声明顺序**填 `x1` 往上；
2. 浮点参数**独立计数**填 `d0` 往上（不占 `x` 寄存器）——这是 AAPCS64 最容易写错的一条；
3. 返回值：整数/指针在 `x0`、浮点在 `d0`，两个格子都要被回填；
4. 跳板自己保存并恢复 `x19/x20`（它用这两个寄存器跨过 `blr` 保存两个回填指针）——
   用一个**故意不保存就写坏 `x19/x20`** 的假方法核对：跳板仍然要把结果写回调用方给的地址。

宿主机不是 aarch64 或没有 C++ 编译器时 **skip**（并打印原因），绝不伪装成通过。
"""

import os
import platform
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LUA_DIR = ROOT / "runtime" / "src" / "interfaces" / "lua"
TRAMPOLINE_ASM = LUA_DIR / "engine_call_trampoline.s"

AARCH64_MACHINES = {"arm64", "aarch64"}

DRIVER = r"""
#include "interfaces/lua/engine_call_trampoline.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>


// 假引擎方法观察到的参数（volatile 防止被优化掉）。
static volatile std::uint64_t g_self;
static volatile std::uint64_t g_ints[4];
static volatile double g_floats[4];
static volatile int g_calls;

extern "C" {

__attribute__((noinline)) void FakeVoid0(std::uint64_t self) {
    g_self = self;
    g_calls = g_calls + 1;
}

__attribute__((noinline)) std::uint64_t FakeInts3(std::uint64_t self, std::uint64_t a,
                                                  std::uint64_t b, std::uint64_t c) {
    g_self = self;
    g_ints[0] = a;
    g_ints[1] = b;
    g_ints[2] = c;
    g_calls = g_calls + 1;
    return self + a + b + c;
}

__attribute__((noinline)) void FakeMixed(std::uint64_t self, std::int32_t a, double f,
                                         std::uint64_t p, std::int32_t c) {
    g_self = self;
    g_ints[0] = static_cast<std::uint64_t>(static_cast<std::int64_t>(a));
    g_ints[1] = p;
    g_ints[2] = static_cast<std::uint64_t>(static_cast<std::int64_t>(c));
    g_floats[0] = f;
    g_calls = g_calls + 1;
}

__attribute__((noinline)) double FakeDouble(std::uint64_t self, std::int32_t a, double f) {
    g_self = self;
    g_ints[0] = static_cast<std::uint64_t>(static_cast<std::int64_t>(a));
    g_floats[0] = f;
    g_calls = g_calls + 1;
    return f * 2.0 + static_cast<double>(a);
}

//: ★★ 批次 338（2026-10-04）新加的两个"**按 f32** 的假引擎方法"。
//:
//: 为什么必须加：以前这里只测过 **`double`** 形参（`FakeMixed` / `FakeDouble`），于是
//: 「共享处理器把 Lua 数值 `static_cast<double>` 塞进槽、跳板整 8 字节装进 `d0`」这条**错的**
//: 实现一路绿灯 —— 而引擎里浮点形参的 mangled 末位是 **`f` = `float`**，
//: AAPCS64 下它占 `sN` = `dN` 的**低 32 位** ⇒ 引擎读到的是那个 double 的**低半**（常见就是 0）。
static volatile float g_float_arg;

__attribute__((noinline)) void FakeFloatArg(std::uint64_t self, std::int32_t a, float f,
                                            std::uint64_t p) {
    g_self = self;
    g_ints[0] = static_cast<std::uint64_t>(static_cast<std::int64_t>(a));
    g_ints[1] = p;
    g_float_arg = f;
    g_calls = g_calls + 1;
}

__attribute__((noinline)) float FakeFloatRet(std::uint64_t self) {
    g_self = self;
    g_calls = g_calls + 1;
    return 6.25F;
}

//: 往跳板的浮点槽里装一个 **f32**（低 32 位 = f32 位型、高 32 位 0）——
//: 这就是 `isaac_api.cpp` 的 `EngineFloatArgument()` 做的事。
static double AsFloatSlot(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    const std::uint64_t wide = bits;
    double storage = 0.0;
    std::memcpy(&storage, &wide, sizeof(storage));
    return storage;
}

// 敌意被调函数：**故意不保存**就写坏 x19/x20（真实引擎函数不会这么干，
// 但"跳板自己有没有保存"只有用这种函数才测得出来）。
__attribute__((naked)) std::uint64_t FakeClobbers(std::uint64_t) {
    __asm__ volatile(
        "mov x19, #0x1234\n\t"
        "mov x20, #0x5678\n\t"
        "mov x0, #0x99\n\t"
        "ret\n\t");
}

}  // extern "C"

int main() {
    alignas(16) std::uint64_t ints[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    alignas(16) double floats[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    std::uint64_t xr = 0;
    double dr = 0;

    // 1) 无参数：只有接收者。
    g_calls = 0;
    ints[0] = 0xAAAA;
    EngineCallTrampoline(reinterpret_cast<std::uintptr_t>(&FakeVoid0), ints, floats, &xr, &dr);
    std::printf("void0_self=%llx\n", (unsigned long long)g_self);
    std::printf("void0_calls=%d\n", g_calls);

    // 2) 三个整数参数：x1..x3，返回值在 x0。
    g_calls = 0;
    ints[0] = 0x1000;
    ints[1] = 0x0100;
    ints[2] = 0x0010;
    ints[3] = 0x0001;
    EngineCallTrampoline(reinterpret_cast<std::uintptr_t>(&FakeInts3), ints, floats, &xr, &dr);
    std::printf("ints3_self=%llx\n", (unsigned long long)g_self);
    std::printf("ints3_a=%llx\n", (unsigned long long)g_ints[0]);
    std::printf("ints3_b=%llx\n", (unsigned long long)g_ints[1]);
    std::printf("ints3_c=%llx\n", (unsigned long long)g_ints[2]);
    std::printf("ints3_ret=%llx\n", (unsigned long long)xr);

    // 3) 混合签名：i32、double、指针、i32 ⇒ 整数/指针进 x1..x3，double 独立进 d0。
    g_calls = 0;
    ints[0] = 0x2000;              // 接收者
    ints[1] = 7;                   // a
    ints[2] = 0x7100ABCD;          // p
    ints[3] = 9;                   // c
    floats[0] = 1.5;               // f
    EngineCallTrampoline(reinterpret_cast<std::uintptr_t>(&FakeMixed), ints, floats, &xr, &dr);
    std::printf("mixed_self=%llx\n", (unsigned long long)g_self);
    std::printf("mixed_a=%lld\n", (long long)g_ints[0]);
    std::printf("mixed_p=%llx\n", (unsigned long long)g_ints[1]);
    std::printf("mixed_c=%lld\n", (long long)g_ints[2]);
    std::printf("mixed_f=%.3f\n", g_floats[0]);

    // 4) 浮点返回值：d0 回填。
    g_calls = 0;
    ints[0] = 0x3000;
    ints[1] = 3;
    floats[0] = 2.25;
    EngineCallTrampoline(reinterpret_cast<std::uintptr_t>(&FakeDouble), ints, floats, &xr, &dr);
    std::printf("double_ret=%.3f\n", dr);
    std::printf("seen_a=%lld\n", (long long)g_ints[0]);
    std::printf("seen_f=%.3f\n", g_floats[0]);

    // 6) ★★ 批次 338：**`float` 形参** —— 槽里必须是 f32 位型（低 32 位），整数参数继续走 x1..x3。
    g_calls = 0;
    ints[0] = 0x5000;                 // 接收者
    ints[1] = 11;                     // a
    ints[2] = 0x7100CAFE;             // p
    floats[0] = AsFloatSlot(12.5F);   // f（**按 f32 装**）
    EngineCallTrampoline(reinterpret_cast<std::uintptr_t>(&FakeFloatArg), ints, floats, &xr, &dr);
    std::printf("floatarg_self=%llx\n", (unsigned long long)g_self);
    std::printf("floatarg_a=%lld\n", (long long)g_ints[0]);
    std::printf("floatarg_p=%llx\n", (unsigned long long)g_ints[1]);
    std::printf("floatarg_seen=%.4f\n", static_cast<double>(g_float_arg));

    // 7) ★★ 批次 338：**`float` 返回值** —— 引擎在 `s0` 回，我们读 `d0` 的**低 32 位**。
    g_calls = 0;
    xr = 0;
    dr = 0;
    ints[0] = 0x6000;
    EngineCallTrampoline(reinterpret_cast<std::uintptr_t>(&FakeFloatRet), ints, floats, &xr, &dr);
    {
        // ★ 必须用 memcpy 取**位型**：`static_cast<std::uint64_t>(dr)` 取的是**数值**
        //   （而 `dr` 里装的是位型拼出来的极小 double ⇒ 转出来是 0）—— 这正是本条要防的那类错误。
        std::uint64_t wide = 0;
        std::memcpy(&wide, &dr, sizeof(wide));
        const std::uint32_t bits = static_cast<std::uint32_t>(wide);
        float asFloat = 0.0F;
        std::memcpy(&asFloat, &bits, sizeof(asFloat));
        std::printf("floatret_raw_low32=%.4f\n", static_cast<double>(asFloat));
    }

    // 5) 寄存器纪律：被调函数把 x19/x20 写坏，跳板仍要把结果写回调用方给的地址。
    g_calls = 0;
    xr = 0;
    dr = 0;
    ints[0] = 0x4000;
    EngineCallTrampoline(reinterpret_cast<std::uintptr_t>(&FakeClobbers), ints, floats, &xr, &dr);
    std::printf("clobber_ret=%llx\n", (unsigned long long)xr);
    std::printf("clobber_dr=%.1f\n", dr);
    return 0;
}
"""


def find_compiler():
    for candidate in (os.environ.get("CXX"), "clang++", "g++"):
        if candidate and shutil.which(candidate):
            return shutil.which(candidate)
    return None


class EngineCallTrampolineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if platform.machine().lower() not in AARCH64_MACHINES:
            raise unittest.SkipTest(f"跳板是 AArch64 汇编，本机是 {platform.machine()}")
        cls.compiler = find_compiler()
        if cls.compiler is None:
            raise unittest.SkipTest("宿主机没有可用的 C++ 编译器（clang++/g++）")
        cls.temporary = tempfile.TemporaryDirectory(prefix="trampoline-")
        driver = Path(cls.temporary.name) / "driver.cpp"
        driver.write_text(DRIVER, encoding="utf-8")
        binary = Path(cls.temporary.name) / "driver"
        command = [
            cls.compiler, "-std=c++23", "-O1", "-Wall", "-Werror",
            f"-I{ROOT / 'runtime' / 'src'}", "-o", str(binary), str(driver),
            # 跳板的真实现是**汇编**（设备工具链是 devkitA64 的 GCC，它不支持 AArch64 上的
            # `__attribute__((naked))`）。devkitPro 用 `-x assembler-with-cpp` 汇编 `.s`，
            # 所以文件里的 `#if defined(__APPLE__)` 在这里同样要生效。
            "-x", "assembler-with-cpp", str(TRAMPOLINE_ASM),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError(f"编译失败：\n{result.stdout}\n{result.stderr}")
        cls.execution = subprocess.run([str(binary)], capture_output=True, text=True)
        cls.values = {}
        for line in cls.execution.stdout.splitlines():
            if "=" in line:
                key, _, payload = line.partition("=")
                cls.values[key.strip()] = payload.strip()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_driver_ran(self):
        self.assertEqual(self.execution.returncode, 0,
                         self.execution.stdout + self.execution.stderr)
        self.assertTrue(self.values, self.execution.stdout + self.execution.stderr)

    def test_receiver_lands_in_x0(self):
        self.assertEqual(self.values["void0_self"], "aaaa")
        self.assertEqual(self.values["void0_calls"], "1")
        self.assertEqual(self.values["ints3_self"], "1000")

    def test_integer_arguments_fill_x1_upwards(self):
        self.assertEqual(self.values["ints3_a"], "100")
        self.assertEqual(self.values["ints3_b"], "10")
        self.assertEqual(self.values["ints3_c"], "1")
        # 返回值在 x0 回填：0x1000 + 0x100 + 0x10 + 0x1
        self.assertEqual(self.values["ints3_ret"], "1111")

    def test_float_arguments_use_a_separate_register_file(self):
        """混合签名里 `double` 走 `d0`，**不占** `x` 寄存器 —— AAPCS64 最容易写错的一条。"""
        self.assertEqual(self.values["mixed_self"], "2000")
        self.assertEqual(self.values["mixed_a"], "7")
        self.assertEqual(self.values["mixed_p"], "7100abcd")
        self.assertEqual(self.values["mixed_c"], "9")
        self.assertEqual(self.values["mixed_f"], "1.500")

    def test_float_result_is_captured_from_d0(self):
        # f * 2 + a = 2.25 * 2 + 3 = 7.5
        self.assertEqual(self.values["double_ret"], "7.500")
        self.assertEqual(self.values["seen_a"], "3")
        self.assertEqual(self.values["seen_f"], "2.250")

    def test_float_arguments_land_in_the_low_32_bits_of_d(self):
        """★★ 批次 338 的核心判据：**`float` 形参看的是 `d0` 的低 32 位**。

        槽里放 f32 位型时，引擎（假方法）读到的就是那个 `float`。
        ★ 这条以前不存在 —— 本文件只测过 `double`，于是"把 Lua 数值 `static_cast<double>`
        塞进槽"这个错实现一直是绿的（`0.0f` 会被当成"没传参"）。
        """
        self.assertEqual(self.values["floatarg_self"], "5000")
        self.assertEqual(self.values["floatarg_a"], "11")
        self.assertEqual(self.values["floatarg_p"], "7100cafe")
        self.assertEqual(self.values["floatarg_seen"], "12.5000")

    def test_float_result_is_read_from_the_low_32_bits(self):
        """★★ 返回侧同理：引擎在 `s0` 回 `float` ⇒ 我们读 `d0` 的低 32 位。"""
        self.assertEqual(self.values["floatret_raw_low32"], "6.2500")

    def test_trampoline_survives_a_callee_that_wrecks_callee_saved_registers(self):
        """假方法不保存就写坏 `x19/x20`：跳板必须已经把这两个回填指针存在自己的栈帧上。"""
        self.assertEqual(self.values["clobber_ret"], "99")


if __name__ == "__main__":
    unittest.main()
