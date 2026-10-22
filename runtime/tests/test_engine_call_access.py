"""引擎调用层（`infrastructure/call/engine_call_access.hpp`）的宿主行为测试。

## 为什么需要这条门禁

这一层是架构重建的第一步里**最后一层缺失的基础设施**（背景见
`docs/架构诊断-框架为什么失效-20260924.md` 第七节）：在它之前，"把地址变成能调的引擎函数"
在每个调用点各自写一遍（算基址 + 偏移、逐字节核对、`reinterpret_cast<签名>`）。
模组页（`runtime/source/mod_menu_native.cpp`）一处就有 20 个这样的点。

它在本项目的宿主门禁里**没有别的覆盖渠道**：唯一的消费方 `mod_menu_native.cpp` 不在宿主夹具的
源文件清单里（见 `test_support.py`）⇒ 那些"模组页怎么显示"的用例一律用桩顶掉，碰不到这一层。
所以这里直接测这一层：它是纯逻辑（平台判定由参数注入），宿主上完全可测。

## 判据（都是"行为"，不是"源码文本"）

1. `EntryWithinImage`：偏移越界 / 映像比序言还短 / 序言跨出映像末尾 ⇒ 不可用；
2. `ResolveEntryAddress`：三条判据（范围 / 可读 / **16 字节逐字节相等**）任一不成立 ⇒ 失败，
   且**不写**出参（调用方拿到的仍是自己的初值）；
3. **序言要比满 16 字节**：只改第 15 个字节也必须判不通过（"偏移落在别的函数头上"正是这种形态）；
4. **只问判定一次**：读整段用一次 `ReadAt`（逐字节读会把 `svcQueryMemory` 的调用数乘 16，
   在每帧路径上是有代价的）；
5. `AsFunction`：`0` ⇒ `nullptr`；非零 ⇒ 转换后**真的可调用**（用真函数做往返验证）；
6. `ResolveFunction`：解析通过时给出**正好是 `base + offset`** 的可调用指针，不通过时给 `nullptr`；
7. **编译期负向判据**：`AsFunction` 只接受函数指针类型 —— 传别的类型**必须编译不过**
   （这层错了不会报错、只会调到一个坏地址上，所以要在编译期拦）。
8. **第二种形状（批次 112）：地址已经算好时的字节核对** —— `VerifyEntryBytes`（可读判定注入 +
   逐字节相等，问判定只问一次）/ `BytesMatchAt` / `ValueMatchesAt`：通过 ⇒ 真；改中间一个字节
   ⇒ 假；判据不通过、参数为空、整数溢出长度 ⇒ 一律假。
   `BytesMatchAt` / `ValueMatchesAt` 只比较**不再问判定**（它们拿的是刚被核对过的地址，
   与 L1 的 `LoadVerifiedAt` 同一条纪律）。
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
#include "infrastructure/call/engine_call_access.hpp"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace ec = isaac::runtime::engine_call;
namespace em = isaac::runtime::engine_memory;

namespace {

int g_Failures = 0;

void check(bool condition, const char* name) {
    if (!condition) {
        ++g_Failures;
        std::printf("CALL_FAIL %s\n", name);
    }
}

// 伪造的"引擎映像"：一块堆内存，只有它被认作可读（宿主没有 `svcQueryMemory`，
// 设备上那一步就是这个调用 —— 本层只负责"什么时候问、问几遍"）。
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

// "真的可调用"的往返验证用它（伪造的映像里放不了机器码）。
std::uint32_t g_Calls = 0;
std::uint64_t AddPair(std::uint64_t a, std::uint64_t b) {
    ++g_Calls;
    return a + b;
}

} // namespace

int main() {
    // 伪造映像：0x200 字节。
    auto* image = new std::uint8_t[0x200];
    std::memset(image, 0, 0x200);
    g_Begin = reinterpret_cast<std::uintptr_t>(image);
    g_End = g_Begin + 0x200;

    // 在 0x40 处放一段"入口序言"，常量就照它抄 —— 逐字节相等是这一层的主判据。
    std::array<std::uint8_t, ec::kEntryPrologueBytes> expected{};
    for (std::size_t i = 0; i < expected.size(); ++i) {
        expected[i] = static_cast<std::uint8_t>(0xA0 + i);
    }
    std::memcpy(image + 0x40, expected.data(), expected.size());

    // 1) 范围判据。
    check(!ec::EntryWithinImage(g_Begin, 0x200, 0x200 - 8, 16), "image-offset-runs-past-end");
    check(!ec::EntryWithinImage(g_Begin, 8, 0, 16), "image-smaller-than-prologue");
    check(!ec::EntryWithinImage(g_Begin, 0x200, UINTPTR_MAX, 16), "image-offset-wrap");
    check(!ec::EntryWithinImage(g_Begin, 0x200, 0x40, 0), "image-zero-prologue");
    check(ec::EntryWithinImage(g_Begin, 0x200, 0x40, 16), "image-ok");
    check(ec::EntryWithinImage(g_Begin, 0x200, 0x200 - 16, 16), "image-last-legal-offset");

    // 2) 解析成功：地址正好是 base + offset，且**只问判定一次**。
    std::uintptr_t address = 0xBEEF;
    const unsigned beforeOk = g_Checks;
    check(ec::ResolveEntryAddress(g_Begin, 0x200, 0x40, expected, &address, &FakeReadable),
          "resolve-ok");
    check(address == g_Begin + 0x40, "resolve-address-is-base-plus-offset");
    check(g_Checks == beforeOk + 1, "resolve-reads-the-span-in-one-check");

    // 3) 序言**要比满 16 字节**：只改最后一个字节也必须不通过（"偏移落到别的函数头上"的形态）。
    std::array<std::uint8_t, ec::kEntryPrologueBytes> offByOne = expected;
    offByOne[ec::kEntryPrologueBytes - 1] = static_cast<std::uint8_t>(offByOne[15] + 1);
    address = 0xBEEF;
    check(!ec::ResolveEntryAddress(g_Begin, 0x200, 0x40, offByOne, &address, &FakeReadable),
          "resolve-compares-all-16-bytes");
    check(address == 0xBEEF, "resolve-mismatch-must-not-write-out");

    // 4) 失败路径一律**不写**出参：范围外 / 不可读 / 判定为空 / 出参为空。
    address = 0xBEEF;
    check(!ec::ResolveEntryAddress(g_Begin, 0x200, 0x1F8, expected, &address, &FakeReadable),
          "resolve-offset-past-end-fails");
    check(address == 0xBEEF, "resolve-range-failure-must-not-write-out");
    // 把可读区间的末尾收到序言起点之前 ⇒ 整段读不到。
    const std::uintptr_t savedEnd = g_End;
    g_End = g_Begin + 0x40;
    address = 0xBEEF;
    check(!ec::ResolveEntryAddress(g_Begin, 0x200, 0x40, expected, &address, &FakeReadable),
          "resolve-unreadable-fails");
    check(address == 0xBEEF, "resolve-unreadable-must-not-write-out");
    g_End = savedEnd;
    check(!ec::ResolveEntryAddress(g_Begin, 0x200, 0x40, expected, &address, nullptr),
          "resolve-null-check-fails");
    check(!ec::ResolveEntryAddress(g_Begin, 0x200, 0x40, expected, nullptr, &FakeReadable),
          "resolve-null-out-fails");

    // 5) AsFunction：0 ⇒ nullptr（绝不给出"看起来能调"的坏地址）。
    using AddFn = std::uint64_t (*)(std::uint64_t, std::uint64_t);
    check(ec::AsFunction<AddFn>(0) == nullptr, "as-function-zero-is-null");

    // 6) ResolveFunction：给出的指针**真的可调用**，且正好是 base + offset。
    //    伪造的映像里放不了机器码，所以这里用"真函数的地址"当映像里的那个入口：
    //    把它的地址塞进映像的 0x40 处不可能（那 16 字节是序言，不是地址）——
    //    因此分两步验：解析给出地址、AsFunction 让地址可调用。
    check(ec::AddressOfFunction(static_cast<AddFn>(nullptr)) == 0, "function-address-null-is-zero");
    AddFn direct = ec::AsFunction<AddFn>(ec::AddressOfFunction(&AddPair));
    check(direct != nullptr, "as-function-roundtrip-not-null");
    if (direct != nullptr) {
        check(direct(2, 3) == 5, "as-function-roundtrip-callable");
        check(g_Calls == 1, "as-function-really-called");
    }

    // 7) ResolveFunction 的两条：通过 ⇒ 非空且等于 base + offset；不通过 ⇒ 空。
    //    这里用"把真函数放进伪造映像"的办法：把真函数地址写在映像里没用（解析给的是地址本身，
    //    不是从映像里取出来的），所以只判**地址相等**这一条；"可调用"由上面那条覆盖。
    {
        // 令映像 0x80 处的 16 字节等于 expected ⇒ 解析通过。
        std::memcpy(image + 0x80, expected.data(), expected.size());
        const auto resolved = ec::ResolveFunction<AddFn>(g_Begin, 0x200, 0x80, expected,
                                                        &FakeReadable);
        check(resolved != nullptr, "resolve-function-ok");
        check(reinterpret_cast<std::uintptr_t>(resolved) == g_Begin + 0x80,
              "resolve-function-address-is-base-plus-offset");
        // 序言不符 ⇒ 空指针（不是"随便给一个地址试试"）。
        std::memset(image + 0x80, 0, expected.size());
        const auto refused = ec::ResolveFunction<AddFn>(g_Begin, 0x200, 0x80, expected,
                                                       &FakeReadable);
        check(refused == nullptr, "resolve-function-mismatch-is-null");
        // 注入的判定为空 ⇒ 一律拒绝（本层不允许"没有守卫的解析"）。
        check(ec::ResolveFunction<AddFn>(g_Begin, 0x200, 0x40, expected, nullptr) == nullptr,
              "resolve-function-without-check-rejects");
    }

    // 8) 第二种形状（批次 112）：地址**已经算好**时的字节核对。
    //    8a) `VerifyEntryBytes` 通过 ⇒ 真；只改中间一个字节 ⇒ 假（逐字节都要比）。
    std::uint8_t expectedWord[4] = {0x11, 0x22, 0x33, 0x44};
    std::memcpy(image + 0xC0, expectedWord, sizeof(expectedWord));
    const unsigned beforeVerify = g_Checks;
    check(ec::VerifyEntryBytes(g_Begin + 0xC0, expectedWord, sizeof(expectedWord), &FakeReadable),
          "verify-entry-bytes-ok");
    check(g_Checks == beforeVerify + 1, "verify-entry-bytes-checks-the-span-once");
    std::uint8_t offByOneWord[4] = {0x11, 0x22, 0x33, 0x45};
    check(!ec::VerifyEntryBytes(g_Begin + 0xC0, offByOneWord, sizeof(offByOneWord), &FakeReadable),
          "verify-entry-bytes-compares-every-byte");
    //    8b) 判据不通过 / 参数为空 ⇒ 一律假（绝不"没核对过就当通过"）。
    check(!ec::VerifyEntryBytes(g_Begin + 0xC0, expectedWord, sizeof(expectedWord), nullptr),
          "verify-entry-bytes-without-check-rejects");
    check(!ec::VerifyEntryBytes(0, expectedWord, sizeof(expectedWord), &FakeReadable),
          "verify-entry-bytes-null-address-rejects");
    check(!ec::VerifyEntryBytes(g_Begin + 0xC0, nullptr, sizeof(expectedWord), &FakeReadable),
          "verify-entry-bytes-null-expected-rejects");
    check(!ec::VerifyEntryBytes(g_Begin + 0xC0, expectedWord, 0, &FakeReadable),
          "verify-entry-bytes-zero-size-rejects");
    // 长度会让 `address + size` 回绕 ⇒ 连读都不必读，直接假。
    check(!ec::VerifyEntryBytes(g_Begin + 0xC0, expectedWord, UINTPTR_MAX, &FakeReadable),
          "verify-entry-bytes-length-wrap-rejects");
    const std::uintptr_t savedEndVerify = g_End;
    g_End = g_Begin + 0xC0;
    check(!ec::VerifyEntryBytes(g_Begin + 0xC0, expectedWord, sizeof(expectedWord), &FakeReadable),
          "verify-entry-bytes-unreadable-rejects");
    g_End = savedEndVerify;
    //    8c) `BytesMatchAt` / `ValueMatchesAt`：在**已核对过**的地址上比较，只比较、不再问判定。
    check(ec::BytesMatchAt(g_Begin + 0xC0, expectedWord, sizeof(expectedWord)),
          "bytes-match-at-ok");
    check(!ec::BytesMatchAt(g_Begin + 0xC0, offByOneWord, sizeof(offByOneWord)),
          "bytes-match-at-mismatch");
    check(!ec::BytesMatchAt(0, expectedWord, sizeof(expectedWord)), "bytes-match-at-null-rejects");
    const std::uint32_t stubWord = 0x58000050u;
    std::memcpy(image + 0xD0, &stubWord, sizeof(stubWord));
    check(ec::ValueMatchesAt(g_Begin + 0xD0, stubWord), "value-match-at-ok");
    check(!ec::ValueMatchesAt(g_Begin + 0xD0, stubWord + 1u), "value-match-at-mismatch");
    check(!ec::ValueMatchesAt(0, stubWord), "value-match-at-null-rejects");

    delete[] image;

    if (g_Failures == 0) {
        std::printf("ENGINE_CALL_ACCESS_OK\n");
    }
    return g_Failures == 0 ? 0 : 1;
}
'''


#: 负向用例的源码：`AsFunction` **只接受函数指针类型** —— 传别的类型必须编译不过。
#: 为什么不靠运行时：这个转换错了不会报错，只会调到一个坏地址上（真机就是跳到别处改引擎状态）。
NOT_A_FUNCTION_POINTER_SNIPPET = r'''
#include "infrastructure/call/engine_call_access.hpp"

#include <cstdint>

int main() {
    // 误用：把整数类型当签名传给 AsFunction（那会得到"看起来能调的东西"）。
    (void)isaac::runtime::engine_call::AsFunction<std::uint64_t>(0x1234);
    return 0;
}
'''


class EngineCallAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compilers = host_compilers()
        if compilers is None:
            raise unittest.SkipTest("需要宿主 C/C++ 编译器（本用例不需要 docker）")
        _, cxx = compilers
        cls.temporary = tempfile.TemporaryDirectory(prefix="isaac-engine-call-")
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
        harness = temporary / "engine_call_access_harness.cpp"
        harness.write_text(HARNESS.lstrip())
        cls.binary = temporary / "engine_call_access_harness"
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

    def test_layer_resolves_only_after_all_three_judgements(self):
        result = subprocess.run([str(self.binary)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ENGINE_CALL_ACCESS_OK", result.stdout)
        self.assertNotIn("CALL_FAIL", result.stdout)

    def test_non_function_pointer_must_not_compile(self):
        """`AsFunction` 只接受函数指针 —— 传别的类型必须编译不过。

        为什么这条判据只能是"编译期"：这个转换**本身不可核对**，错了不会报错、也不会崩在这里，
        而是"调到一个别的地方"（真机上就是去改引擎的别的状态，事后极难反查）。
        ⇒ 层里用 `static_assert` 把它变成编译错误；**任何一条被改掉，这条用例就会红。**
        """
        snippet = Path(self.temporary.name) / "not_a_function_pointer.cpp"
        snippet.write_text(NOT_A_FUNCTION_POINTER_SNIPPET.lstrip())
        build = subprocess.run(
            self.compile_flags + ["-fsyntax-only", str(snippet)],
            text=True, capture_output=True,
        )
        self.assertNotEqual(
            build.returncode, 0,
            "把非函数指针类型传给 `AsFunction` 竟然编译过了 —— 层里的 `static_assert` 是不是被去掉了？"
            "那个写法在真机上会得到一个看起来能调、其实指向未知位置的东西。")
        output = build.stdout + build.stderr
        self.assertIn("函数指针", output,
                      f"编译确实失败了，但报错不像是被那条 `static_assert` 拦下的（改法变了？）：{output}")

    def test_object_pointer_cannot_be_published_as_a_callback(self):
        snippet = Path(self.temporary.name) / "object_is_not_callback.cpp"
        snippet.write_text('#include "infrastructure/call/engine_call_access.hpp"\n'
                           'int main(){int object=0;return isaac::runtime::engine_call::'
                           'AddressOfFunction(&object)==0;}\n')
        build = subprocess.run(self.compile_flags + ["-fsyntax-only", str(snippet)],
                               text=True, capture_output=True)
        self.assertNotEqual(build.returncode, 0)
        self.assertIn("函数指针", build.stdout + build.stderr)


if __name__ == "__main__":
    unittest.main()
