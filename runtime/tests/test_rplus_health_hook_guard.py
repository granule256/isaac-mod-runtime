"""Health API entry guards recognize only authenticated installed hooks."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class HealthHookGuardTests(unittest.TestCase):
    def test_actual_health_guard_uses_registered_hook_verifier(self):
        source = (ROOT / 'runtime/src/interfaces/lua/rplus_health_api.cpp').read_text()
        start = source.index('template<std::size_t N> bool Guard(')
        end = source.index('template<std::size_t N> bool CachedGuard(', start)
        driver = r'''
#include "infrastructure/call/engine_call_access.hpp"
#include <array>
#include <cassert>
#include <cstring>
namespace engine_memory = isaac::runtime::engine_memory;
namespace engine_call = isaac::runtime::engine_call;
GUARD_BODY
static std::uintptr_t address;
static unsigned calls;
static const std::array<std::uint8_t,16> original{1,2,3,4};
static const std::array<std::uint8_t,16> installed{5,6,7,8};
static bool Verify(std::uintptr_t at, const std::uint8_t* expected,
                   std::size_t size, engine_memory::ReadableCheck readable) noexcept {
    ++calls;
    return at==address && size==16 && readable(at,size) &&
        !std::memcmp(expected,original.data(),size) &&
        !std::memcmp(reinterpret_cast<void*>(at),installed.data(),size);
}
int main() {
    alignas(8) std::array<std::uint8_t,64> image{};
    const auto base=reinterpret_cast<std::uintptr_t>(image.data());
    address=base+16;
    std::memcpy(image.data()+16,original.data(),16);
    engine_call::SetInstalledEntryVerifier(Verify);
    assert(Guard(base,16,original) && calls==0);
    std::memcpy(image.data()+16,installed.data(),16);
    assert(Guard(base,16,original) && calls==1);
    image[24]^=1;
    assert(!Guard(base,16,original));
    image[24]^=1;
    engine_call::SetInstalledEntryVerifier(nullptr);
    assert(!Guard(base,16,original));
    assert(!Guard(0,16,original));
}
'''.replace('GUARD_BODY', source[start:end])
        with tempfile.TemporaryDirectory(prefix='health-hook-guard-') as folder:
            folder = Path(folder)
            path = folder / 'driver.cpp'
            path.write_text(driver)
            binary = folder / 'test'
            subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'runtime/src'), '-I', str(ROOT / 'runtime/source'),
                            str(path), '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
