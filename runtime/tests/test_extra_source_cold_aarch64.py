"""Execute the cold indirect BLR gate on an available AArch64 host."""

import platform
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


DRIVER = r'''
#include "relay/internal_hook.hpp"

#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <sys/mman.h>

#if defined(__APPLE__)
#include <pthread.h>
#endif

using namespace isaac::runtime::relay;

static std::uintptr_t gSource;
static std::uintptr_t gOriginal;
static std::uintptr_t gResume;

extern "C" std::uint64_t InvokeNull(
    void* source, void* callee, std::uint64_t expectedResume,
    std::uint64_t expectedCallee);
extern "C" std::uint64_t InvokeActive(void* source, void* callee);

static void Write(std::uint8_t* memory, std::uintptr_t address,
                  const void* source, std::size_t size) {
    static_cast<void>(memory);
    std::memcpy(reinterpret_cast<void*>(address), source, size);
}

int main() {
    constexpr std::uint32_t kMoveX0FromX30 = 0xAA1E03E0U;
    constexpr std::uint32_t kMoveX1FromX8 = 0xAA0803E1U;
    constexpr std::uint32_t kMoveX0One = 0xD2800020U;
    constexpr std::uint32_t kMoveX1Two = 0xD2800041U;
    constexpr std::uint32_t kRet = 0xD65F03C0U;
    constexpr std::uint32_t kBrX10 = 0xD61F0140U;

#if defined(__APPLE__)
    constexpr int kMapFlags = MAP_PRIVATE | MAP_ANON | MAP_JIT;
#else
    constexpr int kMapFlags = MAP_PRIVATE | MAP_ANON;
#endif
    auto* memory = static_cast<std::uint8_t*>(
        mmap(nullptr, 4096, PROT_READ | PROT_WRITE | PROT_EXEC,
             kMapFlags, -1, 0));
    assert(memory != MAP_FAILED);
    const auto base = reinterpret_cast<std::uintptr_t>(memory);
    const ColdIndirectHookSite site{
        base + 64, base + 128, base + 256, base + 320,
        0xD63F0100U, 8};
    std::array<std::uint8_t, kColdIndirectGateBytes> gate{};
    std::array<std::uint8_t, kColdIndirectFallbackBytes> fallback{};
    assert(BuildColdIndirectImages(site, gate.data(), fallback.data()));

#if defined(__APPLE__)
    pthread_jit_write_protect_np(0);
#endif
    std::uint32_t sourceBranch{};
    assert(BuildInternalBranch(&sourceBranch, site.source, site.gate));
    Write(memory, site.source, &sourceBranch, sizeof(sourceBranch));
    Write(memory, site.source + 4, &kBrX10, sizeof(kBrX10));
    Write(memory, site.gate, gate.data(), gate.size());
    Write(memory, site.fallback, fallback.data(), fallback.size());

    const auto original = base + 384;
    const auto sourceAddress = site.source;
    gSource = sourceAddress;
    gOriginal = original;
    gResume = sourceAddress + 4;
    Write(memory, original, &kMoveX0FromX30, sizeof(kMoveX0FromX30));
    Write(memory, original + 4, &kMoveX1FromX8, sizeof(kMoveX1FromX8));
    Write(memory, original + 8, &kRet, sizeof(kRet));

    const auto gateway = base + 448;
    Write(memory, gateway, &kMoveX0One, sizeof(kMoveX0One));
    Write(memory, gateway + 4, &kMoveX1Two, sizeof(kMoveX1Two));
    Write(memory, gateway + 8, &kRet, sizeof(kRet));
    __builtin___clear_cache(reinterpret_cast<char*>(memory),
                            reinterpret_cast<char*>(memory + 4096));
#if defined(__APPLE__)
    pthread_jit_write_protect_np(1);
#endif
    std::uint64_t slot = 0;
#if defined(__APPLE__)
    pthread_jit_write_protect_np(0);
#endif
    Write(memory, site.slot, &slot, sizeof(slot));
#if defined(__APPLE__)
    pthread_jit_write_protect_np(1);
#endif
    const auto nullResult = InvokeNull(
        reinterpret_cast<void*>(gSource),
        reinterpret_cast<void*>(gOriginal), gResume, gOriginal);
    assert(nullResult == 0);

#if defined(__APPLE__)
    pthread_jit_write_protect_np(0);
#endif
    slot = gateway;
    Write(memory, site.slot, &slot, sizeof(slot));
#if defined(__APPLE__)
    pthread_jit_write_protect_np(1);
#endif
    const auto activeResult = InvokeActive(
        reinterpret_cast<void*>(gSource),
        reinterpret_cast<void*>(gOriginal));
    assert(activeResult == 0);

    munmap(memory, 4096);
}
'''


ASSEMBLY = r'''
.text
.global {prefix}InvokeNull
.align 2
{prefix}InvokeNull:
stp x29, x30, [sp, #-48]!
stp x19, x20, [sp, #16]
mov x29, sp
mov x8, x1
mov x19, x2
mov x20, x3
adr x10, .Lnull_return
blr x0
.Lnull_return:
subs x0, x0, x19
b.ne 1f
subs x1, x1, x20
b.ne 2f
mov x0, #0
b 3f
1:
mov x0, #1
b 3f
2:
mov x0, #2
3:
ldp x19, x20, [sp, #16]
ldp x29, x30, [sp], #48
ret

.global {prefix}InvokeActive
.align 2
{prefix}InvokeActive:
stp x29, x30, [sp, #-32]!
mov x29, sp
mov x8, x1
adr x10, .Lactive_return
blr x0
.Lactive_return:
subs x0, x0, #1
b.ne 1f
subs x1, x1, #2
b.ne 1f
mov x0, #0
b 2f
1:
mov x0, #1
2:
ldp x29, x30, [sp], #32
ret
'''


class ExtraSourceColdAArch64Tests(unittest.TestCase):
    def test_null_and_active_gate_preserve_blr_contract(self):
        if platform.machine() not in ("arm64", "aarch64"):
            self.skipTest("needs an AArch64 host")
        prefix = "_" if platform.system() == "Darwin" else ""
        with tempfile.TemporaryDirectory(prefix="isaac-cold-bler-") as tmp:
            task = Path(tmp)
            (task / "test.cpp").write_text(DRIVER)
            (task / "entry.s").write_text(
                ASSEMBLY.format(prefix=prefix)
            )
            result = subprocess.run(
                [
                    "clang++",
                    "-std=c++23",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(ROOT / "runtime/source"),
                    str(task / "test.cpp"),
                    str(task / "entry.s"),
                    "-o",
                    str(task / "test"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(
                [str(task / "test")], capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
