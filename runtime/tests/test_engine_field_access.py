"""引擎内存访问层（`infrastructure/memory/engine_field_access.hpp` + port 适配器）的宿主行为测试。

## 为什么需要这条门禁

这一层是架构重建阶段 1 的产物（背景见 `docs/架构诊断-框架为什么失效-20260924.md`）：
它把"指针 + 偏移"的算术、对齐检查、可读性调用与取值**收在一个地方**，让功能代码只写"读哪个字段"。

但它在本项目的宿主门禁里**没有别的覆盖渠道**：唯一的使用方 `runtime/source/game_observer.cpp`
不在宿主夹具的源文件清单里（见 `test_support.py` 的 `layered_lua_runtime_sources`）⇒ 那些
"某个 API 在宿主上怎么表现"的用例一律用弱默认桩顶掉观察函数，**碰不到这一层的实现**。
所以这里直接测这一层本身：它是纯逻辑（很薄的平台判定由参数传入），宿主上完全可测。

## 判据（都是"行为"，不是"源码文本"）

1. `RangeUsable`：空地址 / 长度 0 / 回绕一律不可用；
2. `ReadField`：按偏移取值正确；未对齐 / 判定说不可读 / 偏移回绕 一律失败且**不写**出参；
3. `LoadPointer` / `PointerUsable`：槽为空 / 未对齐 / 不可读 ⇒ 失败；槽里是 0 ⇒ 成功但值是 0
   （**"空指针"与"读不到"必须可区分** —— 观察路径靠这个区分决定崩溃报告里的状态码）；
4. `LoadPointerAt`：槽地址由 `base + offset` 算出，回绕要挡住；
5. `FieldAddress`：给出字段地址并确认可读；失败返回 0；
6. `LoadVerified` / `LoadVerifiedAt`：在**已经确认过**的地址上取值，**不再重复问判定**
   （每帧路径靠这条不把 `svcQueryMemory` 调用数翻倍）；越界下标被挡住；
7. `CallUnaryMethod`：把整数 thunk 转成函数指针并调用；
8. **写侧（批次 103）**：`WriteField` / `WriteAt` 先确认**可写**再落值（判定由参数注入，
   **不是**"可读即可写"）；未对齐 / 偏移回绕 / 判定说不可写 / 判定为空一律失败，
   且失败时**一个字节都不落**（与读侧"失败时不写出参"对称）；
9. `GuardedGameMemoryPort`：端口的四个入口都落回本层，且失败路径返回非 Ok。
10. **读一整段时的 C 数组陷阱（批次 106）**：`ReadField` / `ReadAt` / `LoadVerified(At)` 的
    出参是 `T* const&`（引用 ⇒ 不做数组退化），并且各有一个 `= delete` 的 `T (&)[N]` 重载
    ⇒ **把裸 C 数组传进去必须编译不过**（负向用例
    `test_bare_c_array_argument_must_not_compile`）；写 `&数组` 时才整段读取、判定覆盖整段。
    ★ 这条为什么必须是编译期判据：那个误用**运行时完全安静**（模板把 `T` 推成元素类型 ⇒
    只读一个元素、其余留在初值上），真机上表现为"模组页整页纵向偏出视野"，而读数还被同一个
    坏读带偏（显示 `(173.0, 0.0)` —— X 对、Y 成了 0）。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"


def host_compilers() -> tuple[str, str] | None:
    """(C 编译器, C++ 编译器)；缺任何一个就整体 skip，不伪装成通过。"""
    cc = shutil.which("cc")
    if cc is None:
        return None
    for candidate in ("c++", "clang++", "g++"):
        found = shutil.which(candidate)
        if found is not None:
            return cc, found
    return None


HARNESS = r'''
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/memory/game_memory_port_adapter.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>

using isaac::runtime::GuardedGameMemoryPort;
using isaac::runtime::Status;
using isaac::runtime::ThunkCall;
namespace em = isaac::runtime::engine_memory;

namespace {

int g_Failures = 0;

void check(bool condition, const char* name) {
    if (!condition) {
        ++g_Failures;
        std::printf("FIELD_FAIL %s\n", name);
    }
}

// 伪造的"引擎内存"：一块堆内存，只有它被认作可读（宿主没有 `svcQueryMemory`，
// 设备上这一段就是那个调用 —— 本层只负责"什么时候问、问几遍"）。
std::uintptr_t g_Begin = 0;
std::uintptr_t g_End = 0;
unsigned g_Checks = 0;

bool FakeReadable(std::uintptr_t address, std::size_t length) {
    ++g_Checks;
    if (g_Begin == 0 || length == 0 || address > UINTPTR_MAX - length) {
        return false;
    }
    return address >= g_Begin && address + length <= g_End;
}

// 伪造的"可写判定"：**故意与可读区间不一样**（只放行前半段）——
// 这一条就是"可读 ≠ 可写"的行为判据：写只认注进来的这份写判定，不看可读那份。
std::uintptr_t g_WritableBegin = 0;
std::uintptr_t g_WritableEnd = 0;
unsigned g_WritableChecks = 0;

bool FakeWritable(std::uintptr_t address, std::size_t length) {
    ++g_WritableChecks;
    if (g_WritableBegin == 0 || length == 0 || address > UINTPTR_MAX - length) {
        return false;
    }
    return address >= g_WritableBegin && address + length <= g_WritableEnd;
}

// 伪造的"引擎方法"：按 4 个参数算一个可预期的值。
std::uint64_t AddFour(std::uint64_t a, std::uint64_t b, std::uint64_t c, std::uint64_t d) {
    return a + b * 2 + c * 3 + d * 4;
}

// 伪造的"取对象指针、返回 bool"的引擎方法。
bool SentinelMethod(const void* object) {
    std::uint32_t value = 0;
    std::memcpy(&value, object, sizeof(value));
    return value == 0x5A5A5A5AU;
}

} // namespace

int main() {
    // 伪造内存：0x200 字节，地址本身就是我们自己的堆块。
    auto* block = new std::uint8_t[0x200];
    std::memset(block, 0, 0x200);
    g_Begin = reinterpret_cast<std::uintptr_t>(block);
    g_End = g_Begin + 0x200;

    // 1) 区间可用性。
    check(!em::RangeUsable(0, 4), "range-null");
    check(!em::RangeUsable(g_Begin, 0), "range-zero-length");
    check(!em::RangeUsable(static_cast<std::uintptr_t>(-8), 16), "range-wrap");
    check(em::RangeUsable(g_Begin, 8), "range-ok");

    // 2) ReadField：取值 / 未对齐 / 不可读 / 偏移回绕 / 不写出参。
    const std::uint32_t sentinel = 0x11223344U;
    std::memcpy(block + 0x40, &sentinel, sizeof(sentinel));
    std::uint32_t loaded = 0;
    check(em::ReadField(g_Begin, 0x40, &loaded, &FakeReadable), "field-read-ok");
    check(loaded == sentinel, "field-read-value");
    loaded = 0;
    check(!em::ReadField(g_Begin + 1, 0x40, &loaded, &FakeReadable), "field-misaligned-base");
    check(loaded == 0, "field-misaligned-must-not-write");
    check(!em::ReadField(g_End, 0, &loaded, &FakeReadable), "field-unreadable");
    loaded = 0;
    check(!em::ReadField(g_Begin, UINTPTR_MAX, &loaded, &FakeReadable), "field-offset-wrap");
    check(loaded == 0, "field-wrap-must-not-write");
    check(!em::ReadField(g_Begin, 0x40, &loaded, nullptr), "field-null-check-must-fail");

    // 2b) 8 字节字段：`requiredAlignment` 显式传 8（原实现里有些地方就是按 8 判 4 字节字段）。
    loaded = 0;
    check(!em::ReadField(g_Begin + 4, 0x40, &loaded, &FakeReadable, alignof(std::uintptr_t)),
          "field-required-alignment-8");

    // 2c) ★★ 读一整段（批次 106，真机事故换来的）：C 数组**必须**写 `&数组` —— 那时 `T` = `float[2]`
    //     ⇒ `sizeof(T)` = 8 ⇒ 两个 float 一起读、判定也覆盖整段。
    //     （传裸数组会编译不过：出参是 `T* const&` + 一个 `= delete` 的数组重载。
    //      负向判据见 `test_bare_c_array_argument_must_not_compile`。）
    {
        const float pair[2] = {1.5F, -2.5F};
        std::memcpy(block + 0xC0, pair, sizeof(pair));
        float got[2] = {0.0F, 0.0F};
        const unsigned beforeArray = g_Checks;
        check(em::ReadField(g_Begin, 0xC0, &got, &FakeReadable, 0), "field-array-read-ok");
        check(got[0] == 1.5F, "field-array-first");
        check(got[1] == -2.5F, "field-array-second-must-also-be-read");
        check(g_Checks == beforeArray + 1, "field-array-one-check");
        // 判定必须覆盖**整段 8 字节**：把可读区间收到只覆盖前 4 字节 ⇒ 整段读取必须失败，
        // 而且**一个字节都不写**（出参保持在初值上）。
        const std::uintptr_t savedEnd = g_End;
        g_End = g_Begin + 0xC4;
        got[0] = 0.0F;
        got[1] = 0.0F;
        check(!em::ReadField(g_Begin, 0xC0, &got, &FakeReadable, 0), "field-array-needs-whole-span");
        check(got[1] == 0.0F, "field-array-failure-must-not-write");
        g_End = savedEnd;
        // `ReadAt` 的同形写法。
        float gotAt[2] = {0.0F, 0.0F};
        check(em::ReadAt(g_Begin + 0xC0, &gotAt, &FakeReadable), "read-at-array-ok");
        check(gotAt[1] == -2.5F, "read-at-array-second");
    }

    // 3) LoadPointer / PointerUsable：空槽 / 未对齐 / 不可读 / 值为 0。
    const std::uintptr_t target = g_Begin + 0x80;
    std::memcpy(block + 0x10, &target, sizeof(target));
    std::uintptr_t pointer = 0;
    check(em::LoadPointer(g_Begin + 0x10, &pointer, &FakeReadable), "pointer-load-ok");
    check(pointer == target, "pointer-load-value");
    check(!em::LoadPointer(0, &pointer, &FakeReadable), "pointer-null-slot");
    check(!em::LoadPointer(g_Begin + 1, &pointer, &FakeReadable), "pointer-misaligned-slot");
    check(!em::LoadPointer(g_End, &pointer, &FakeReadable), "pointer-unreadable-slot");
    // 槽里是 0：**加载成功但值是 0** —— 调用方据此区分"空"与"读不到"。
    std::uintptr_t zero = 0;
    std::memcpy(block + 0x20, &zero, sizeof(zero));
    check(em::LoadPointer(g_Begin + 0x20, &pointer, &FakeReadable), "pointer-null-value-loads");
    check(pointer == 0, "pointer-null-value-is-zero");
    check(!em::PointerUsable(0, &FakeReadable), "pointer-usable-zero");
    check(!em::PointerUsable(g_Begin + 1, &FakeReadable), "pointer-usable-misaligned");
    check(!em::PointerUsable(g_End, &FakeReadable), "pointer-usable-unreadable");
    check(em::PointerUsable(target, &FakeReadable), "pointer-usable-ok");

    // 4) LoadPointerAt：槽地址 = base + offset，回绕要挡住。
    std::memcpy(block + 0x30, &target, sizeof(target));
    pointer = 0;
    check(em::LoadPointerAt(g_Begin, 0x30, alignof(std::uintptr_t), &pointer, &FakeReadable),
          "pointer-at-ok");
    check(pointer == target, "pointer-at-value");
    check(!em::LoadPointerAt(g_Begin, UINTPTR_MAX, alignof(std::uintptr_t), &pointer, &FakeReadable),
          "pointer-at-wrap");

    // 5) FieldAddress：只解地址不取值；失败返回 0。
    const std::uintptr_t field = em::FieldAddress(g_Begin, 0x40, 4, alignof(std::uint32_t),
                                                  &FakeReadable);
    check(field == g_Begin + 0x40, "field-address-ok");
    check(em::FieldAddress(g_End, 0, 4, 0, &FakeReadable) == 0, "field-address-unreadable");
    check(em::FieldAddress(g_Begin, 0x40, 4, alignof(std::uint32_t), nullptr) == 0,
          "field-address-null-check");

    // 6) LoadVerified：**不重复问判定**（这是每帧路径的关键）。
    const unsigned before = g_Checks;
    std::uint32_t first = 0;
    std::uint32_t second = 0;
    const std::uintptr_t pair = em::FieldAddress(g_Begin, 0x40, 2 * sizeof(std::uint32_t),
                                                 alignof(std::uint32_t), &FakeReadable);
    check(pair != 0, "verified-address-ok");
    check(em::LoadVerified(pair, &first), "verified-load-0");
    check(em::LoadVerifiedAt(pair, 1, &second), "verified-load-1");
    check(first == sentinel, "verified-value-0");
    check(g_Checks == before + 1, "verified-must-not-recheck");
    check(!em::LoadVerified(static_cast<std::uintptr_t>(0), &first), "verified-null-address");
    check(!em::LoadVerifiedAt(pair, UINTPTR_MAX, &first), "verified-index-wrap");

    // 7) CallUnaryMethod：整数 thunk → 函数指针。
    //    `SentinelMethod` 认的是 0x5A5A5A5A（与上面 ReadField 用的 0x11223344 分开写）。
    const std::uint32_t methodSentinel = 0x5A5A5A5AU;
    std::memcpy(block + 0x60, &methodSentinel, sizeof(methodSentinel));
    const auto thunk = reinterpret_cast<std::uintptr_t>(&SentinelMethod);
    check(em::CallUnaryMethod<bool (*)(const void*)>(thunk, g_Begin + 0x60),
          "call-unary-true");
    check(!em::CallUnaryMethod<bool (*)(const void*)>(thunk, g_Begin + 0x64),
          "call-unary-false");
    check(!em::CallUnaryMethod<bool (*)(const void*)>(0, g_Begin), "call-unary-null-thunk");

    // 8) 写侧（批次 103）：先确认**可写**再落值，失败时**一个字节都不落**。
    //    伪造的可写区间**故意只放行前半段**（0x00~0x100；可读区间是整块 0x00~0x200）⇒
    //    这一节的每一条同时也在证明"可读 ≠ 可写"：写只认注入进来的那份**写**判定。
    g_WritableBegin = g_Begin;
    g_WritableEnd = g_Begin + 0x100;
    const std::uint32_t writeValue = 0xAABBCCDDU;
    std::uint32_t readBack = 0;
    check(em::WriteField(g_Begin, 0x80, writeValue, &FakeWritable), "write-field-ok");
    check(em::ReadField(g_Begin, 0x80, &readBack, &FakeReadable), "write-field-readback");
    check(readBack == writeValue, "write-field-value-landed");
    // 可读但**不可写**（0x180 在可读区间里、在可写区间外）：失败，且原值一个字节都不变。
    check(!em::WriteField(g_Begin, 0x180, writeValue, &FakeWritable), "write-field-unwritable");
    check(em::ReadField(g_Begin, 0x180, &readBack, &FakeReadable), "write-unwritable-readback");
    check(readBack == 0, "write-unwritable-must-not-land");
    // 未对齐的 base / 偏移回绕 / 判定为空：一律失败。
    check(!em::WriteField(g_Begin + 1, 0x80, writeValue, &FakeWritable), "write-field-misaligned");
    check(!em::WriteField(g_Begin, UINTPTR_MAX, writeValue, &FakeWritable), "write-field-offset-wrap");
    check(!em::WriteField(g_Begin, 0x80, writeValue, nullptr), "write-field-null-check-must-fail");
    // 显式要求 8 字节对齐（原实现里有些写点对 4 字节字段也按 8 判）。
    check(!em::WriteField(g_Begin + 4, 0x80, static_cast<std::uint32_t>(1), &FakeWritable,
                          alignof(std::uintptr_t)),
          "write-field-required-alignment-8");
    // `WriteAt` = `WriteField(address, 0, …)`：**不查对齐**（地址已在别处算好）。
    const std::uintptr_t oddAddress = g_Begin + 0x89;
    check(em::WriteAt(oddAddress, static_cast<std::uint8_t>(0x5AU), &FakeWritable), "write-at-ok");
    std::uint8_t byte = 0;
    check(em::ReadAt(oddAddress, &byte, &FakeReadable), "write-at-readback");
    check(byte == 0x5AU, "write-at-value-landed");
    check(!em::WriteAt(g_Begin + 0x180, writeValue, &FakeWritable), "write-at-unwritable");
    check(g_WritableChecks > 0, "write-consults-injected-check");

    // 9) 端口适配器：四个入口都落回本层。
    GuardedGameMemoryPort port{&FakeReadable};
    std::uint32_t viaPort = 0;
    check(port.Read(g_Begin + 0x40, &viaPort, sizeof(viaPort)).ok(), "port-read-ok");
    check(viaPort == sentinel, "port-read-value");
    check(!port.Read(g_End, &viaPort, sizeof(viaPort)).ok(), "port-read-unreadable");
    check(!port.Read(g_Begin + 0x40, &viaPort, 0).ok(), "port-read-zero-length");
    std::uint64_t viaPort64 = 0;
    check(port.ReadU64(g_Begin + 0x40, &viaPort64).ok(), "port-read-u64-ok");
    // 0x44 只满足 4 字节对齐 ⇒ 按 8 字节读必须被挡（对齐检查在层里）。
    check(!port.ReadU64(g_Begin + 0x44, &viaPort64).ok(), "port-read-u64-misaligned");
    std::uintptr_t viaPortPointer = 0;
    check(port.ResolvePointer(g_Begin + 0x30, &viaPortPointer).ok(), "port-resolve-ok");
    check(viaPortPointer == target, "port-resolve-value");
    check(!port.ResolvePointer(g_End, &viaPortPointer).ok(), "port-resolve-unreadable");
    ThunkCall call{};
    call.thunk = reinterpret_cast<std::uintptr_t>(&AddFour);
    call.argumentCount = 4;
    call.arguments[0] = 1;
    call.arguments[1] = 2;
    call.arguments[2] = 3;
    call.arguments[3] = 4;
    std::uint64_t callResult = 0;
    check(port.Call(call, &callResult).ok(), "port-call-ok");
    check(callResult == 1 + 2 * 2 + 3 * 3 + 4 * 4, "port-call-value");
    call.thunk = 0;
    check(!port.Call(call, &callResult).ok(), "port-call-null-thunk");
    call.thunk = reinterpret_cast<std::uintptr_t>(&AddFour);
    call.argumentCount = 5;
    check(!port.Call(call, &callResult).ok(), "port-call-too-many-arguments");

    // 未注入判定的端口：一律拒绝（不静默放行 —— 本层不允许"没有守卫的读"）。
    GuardedGameMemoryPort unguarded{nullptr};
    check(!unguarded.Read(g_Begin, &viaPort, sizeof(viaPort)).ok(), "port-without-check-rejects");

    delete[] block;

    if (g_Failures == 0) {
        std::printf("ENGINE_FIELD_ACCESS_OK\n");
    }
    return g_Failures == 0 ? 0 : 1;
}
'''


#: 负向用例的源码：**故意的误用** —— 把裸 C 数组传给取值型 API（批次 105 真机事故的写法）。
#: 它**必须编译不过**：出参是 `T* const&`（引用不做数组退化）+ 一个 `= delete` 的 `T (&)[N]` 重载。
BARE_ARRAY_ARGUMENT_SNIPPET = r'''
#include "infrastructure/memory/engine_field_access.hpp"

#include <cstdint>

static bool FakeCheck(std::uintptr_t, std::size_t) { return true; }

int main() {
    alignas(8) unsigned char buffer[16] = {0};
    float pair[2] = {0.0F, 0.0F};
    // 误用：出参要的是"指针的引用"，传裸数组会被 `= delete` 的重载接住 ⇒ 编译错误。
    (void)isaac::runtime::engine_memory::ReadField(
        reinterpret_cast<std::uintptr_t>(buffer), 0, pair, &FakeCheck, 0);
    return 0;
}
'''


class EngineFieldAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = host_compilers()
        if compilers is None:
            raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
        _, cxx = compilers
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-engine-field-")
        temporary = Path(cls.temporary.name)
        compatibility = temporary / "compatibility"
        compatibility.mkdir()
        (compatibility / "stdfloat").write_text(
            "#pragma once\nnamespace std { using float16_t = float; using float128_t = long double; }\n"
        )
        # 编译旗标单独存一份：正向夹具与下面的"负向编译"用例共用同一套（否则两边口径会漂）。
        cls.compile_flags = [
            cxx, "-std=c++23", "-Wall", "-Wextra", "-Werror",
            "-DEXL_LAYERED_RUNTIME=1",
            "-I", str(compatibility), "-I", str(SOURCE), "-I", str(SOURCE.parent / "src"),
        ]
        harness = temporary / "engine_field_access_harness.cpp"
        harness.write_text(HARNESS.lstrip())
        cls.binary = temporary / "engine_field_access_harness"
        build = subprocess.run(
            cls.compile_flags + [str(harness), "-o", str(cls.binary)],
            text=True, capture_output=True,
        )
        if build.returncode != 0:
            raise AssertionError(build.stdout + build.stderr)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_layer_primitives_and_port_adapter(self):
        result = subprocess.run([str(self.binary)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ENGINE_FIELD_ACCESS_OK", result.stdout)
        self.assertNotIn("FIELD_FAIL", result.stdout)

    def test_bare_c_array_argument_must_not_compile(self):
        """★★ 把裸 C 数组传给取值型 API **必须编译不过**（批次 106 的真机事故判据）。

        为什么这条判据只能是"编译期"：那个误用**运行时完全安静** —— 模板把 `T` 推成元素类型，
        只读 `sizeof(T)` = **一个元素**，其余元素原样留在初值上、判定也只覆盖那一个元素。
        真机现象是"模组页整页纵向偏出视野"，而**读数还被同一个坏读带偏**
        （现场只留下 `(173.0, 0.0)` 这一个指纹：X 对、Y 成了 0）⇒ 事后极难反查到"少读了 4 字节"。

        ⇒ 层用两道保险把它变成编译错误：出参 `T* const&`（引用不做数组退化 ⇒ 数组**匹配不上**
        `T*`）+ 一个 `= delete` 的 `T (&)[N]` 重载。**任何一条被改掉，这条用例就会红。**
        """
        snippet = Path(self.temporary.name) / "bare_c_array_misuse.cpp"
        snippet.write_text(BARE_ARRAY_ARGUMENT_SNIPPET.lstrip())
        build = subprocess.run(
            self.compile_flags + ["-fsyntax-only", str(snippet)],
            text=True, capture_output=True,
        )
        self.assertNotEqual(
            build.returncode, 0,
            "把裸 C 数组直接传给 `ReadField` 竟然编译过了 —— 层里那两道保险"
            "（出参 `T* const&` + `T (&)[N]` 的 `= delete` 重载）是不是被改掉了？"
            "那个写法在真机上只会**静默**少读一段（批次 105 的模组页偏移事故）。")
        output = build.stdout + build.stderr
        self.assertIn("deleted", output,
                      f"编译确实失败了，但报错不像是被删除的重载拦下的（改法变了？）：{output}")


if __name__ == "__main__":
    unittest.main()