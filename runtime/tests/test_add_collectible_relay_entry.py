"""AddCollectible must use the registered native relay, not only the raw entry."""
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

DRIVER = r'''
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {
constexpr std::uintptr_t kEntityPlayerAddCollectibleOffset = 0;
constexpr std::uint32_t kEntityPlayerAddCollectibleEntryWord = 0xD10443FFU;
constexpr std::uintptr_t kBase = 0x100000;

std::uint32_t g_EntryWord = kEntityPlayerAddCollectibleEntryWord;
bool g_InstalledVerifierMatches = false;

std::uintptr_t EngineModuleBase() noexcept { return kBase; }
bool IsEngineMemoryReadable(std::uintptr_t address, std::size_t size) noexcept {
    return address == kBase && size == sizeof(std::uint32_t);
}
template <typename T>
bool ReadEngine(std::uintptr_t, T* value) noexcept {
    std::memcpy(value, &g_EntryWord, sizeof(T));
    return true;
}
[[maybe_unused]] bool EngineEntryWordMatches(std::uintptr_t, std::uint32_t expected) noexcept {
    return g_EntryWord == expected || g_InstalledVerifierMatches;
}

@BODY@
}  // namespace

int main() {
    g_EntryWord = kEntityPlayerAddCollectibleEntryWord;
    g_InstalledVerifierMatches = false;
    if (AddCollectibleMethod() != kBase) {
        std::fputs("original entry was rejected\n", stderr);
        return 1;
    }

    g_EntryWord = 0x58000050U;  // The native AddCollectible relay overwrites the entry.
    g_InstalledVerifierMatches = true;
    if (AddCollectibleMethod() != kBase) {
        std::fputs("registered relay entry was rejected\n", stderr);
        return 2;
    }

    g_InstalledVerifierMatches = false;
    if (AddCollectibleMethod() != 0) {
        std::fputs("unknown patched entry was accepted\n", stderr);
        return 3;
    }
    return 0;
}
'''


class AddCollectibleRelayEntryTests(unittest.TestCase):
    def test_registered_native_relay_entry_is_callable(self):
        source = (ROOT / "runtime/src/interfaces/lua/isaac_api.cpp").read_text()
        start = source.index("std::uintptr_t AddCollectibleMethod() noexcept {")
        body = source[start:source.index("\n}", start) + 2]
        with tempfile.TemporaryDirectory(prefix="add-collectible-relay-") as folder:
            path = Path(folder) / "test.cpp"
            path.write_text(DRIVER.replace("@BODY@", body))
            binary = Path(folder) / "test"
            built = subprocess.run(
                ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(path), "-o", str(binary)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
