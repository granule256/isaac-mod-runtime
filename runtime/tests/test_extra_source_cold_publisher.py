"""Produces and validates the public cold indirect BLR publisher."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_cold_internal_publisher import SHIM


ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include "relay/internal_hook.hpp"

#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>

using namespace isaac::runtime::relay;

extern "C" void isaac_internal_hook_context() {}

alignas(4096) static std::array<unsigned char, 4096> image{};

static InternalHookBinding Binding(std::uintptr_t resume) {
    InternalHookBinding binding{};
    binding.callback = +[](InternalHookContext&, const void*) noexcept
        -> std::uint32_t { return 0; };
    binding.scratch = InternalScratchPolicy::ProvedDeadX16;
    binding.resumeCount = 1;
    binding.resumes[0] = resume;
    return binding;
}

int main() {
    const auto base = reinterpret_cast<std::uintptr_t>(image.data());
    const ColdIndirectHookSite site{
        base + 64, base + 128, base + 256, base + 320,
        0xD63F0100U, 8};
    std::array<std::uint8_t, kColdIndirectGateBytes> gate{};
    std::array<std::uint8_t, kColdIndirectSlotBytes> slotImage{};
    std::array<std::uint8_t, kColdIndirectFallbackBytes> fallback{};
    slotImage.fill(0xAA);
    assert(BuildColdIndirectImages(site, gate.data(), slotImage.data(),
                                   fallback.data()));
    const std::array<std::uint8_t, kColdIndirectSlotBytes> zeroSlot{};
    assert(slotImage == zeroSlot);

    const auto binding = Binding(site.source + 4);
    std::uint32_t sourceBranch{};
    assert(BuildInternalBranch(&sourceBranch, site.source, site.gate));
    std::memcpy(image.data() + 64, &sourceBranch, 4);
    std::memcpy(image.data() + 128, gate.data(), gate.size());
    std::memcpy(image.data() + 320, fallback.data(), fallback.size());

    const auto before = image;
    for (unsigned offset : {64u, 128u, 132u, 136u, 320u, 324u}) {
        image[offset] ^= 1;
        assert(TryInstallColdIndirectHook(binding, site) ==
               InternalHookFailure::GuardMismatch);
        image[offset] ^= 1;
    }
    std::uintptr_t dirtySlot = 1;
    std::memcpy(image.data() + 256, &dirtySlot, sizeof(dirtySlot));
    assert(TryInstallColdIndirectHook(binding, site) ==
           InternalHookFailure::VeneerNotEmpty);
    std::memset(image.data() + 256, 0, 8);

    assert(TryInstallColdIndirectHook(binding, site) ==
           InternalHookFailure::None);
    std::uintptr_t gateway{};
    std::memcpy(&gateway, image.data() + 256, sizeof(gateway));
    assert(gateway != 0);
    assert(ColdIndirectReady(site, gateway) == InternalHookFailure::None);
    assert(!std::memcmp(before.data(), image.data(), 256));
    assert(!std::memcmp(before.data() + 264, image.data() + 264,
                        image.size() - 264));
    assert(TryInstallColdIndirectHook(binding, site) ==
           InternalHookFailure::VeneerNotEmpty);

    assert(RollbackColdIndirectHook(site, gateway) ==
           InternalHookFailure::None);
    std::memcpy(&gateway, image.data() + 256, sizeof(gateway));
    assert(gateway == 0);
    assert(ColdIndirectReady(site, 0) == InternalHookFailure::None);

    auto bad = site;
    bad.original = 0xD63F0200U;
    assert(!BuildColdIndirectImages(bad, gate.data(), fallback.data()));
    bad = site;
    bad.targetRegister = 16;
    assert(!BuildColdIndirectImages(bad, gate.data(), fallback.data()));
    auto badBinding = binding;
    badBinding.resumes[0] = site.source + 8;
    assert(TryInstallColdIndirectHook(badBinding, site) ==
           InternalHookFailure::InvalidPlan);
    auto outside = site;
    outside.slot = site.gate + 0x100000;
    assert(!BuildColdIndirectImages(outside, gate.data(), fallback.data()));
}
'''


class ExtraSourceColdPublisherTests(unittest.TestCase):
    def test_guarded_publication_ready_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp)
            (task / "lib/util/sys").mkdir(parents=True)
            (task / "lib/util/sys/jit.hpp").write_text(SHIM)
            (task / "test.cpp").write_text(DRIVER)
            result = subprocess.run(
                [
                    "clang++",
                    "-std=c++23",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(task),
                    "-I",
                    str(ROOT / "runtime/source"),
                    "-I",
                    str(ROOT / "runtime/src"),
                    str(task / "test.cpp"),
                    str(ROOT / "runtime/source/relay/internal_hook.cpp"),
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
