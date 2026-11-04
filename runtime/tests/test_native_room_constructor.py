"""A reused native Room allocation must not inherit a saved-game header as its descriptor."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#if __has_include("native_room_constructor.hpp")
#include "native_room_constructor.hpp"
#else
namespace isaac::runtime {
template<class Constructor>
void ConstructNativeRoom(std::uintptr_t room, const Constructor& original) { original(room); }
}
#endif
int main() {
    alignas(8) std::array<unsigned char, 0x80> bytes;
    bytes.fill(0xa5);
    const std::uintptr_t header = 0x0036343130525347ULL;
    std::memcpy(bytes.data() + 8, &header, sizeof(header));
    const auto address = reinterpret_cast<std::uintptr_t>(bytes.data());
    bool called = false;
    isaac::runtime::ConstructNativeRoom(address, [&](std::uintptr_t room) {
        assert(room == address);
        std::uintptr_t descriptor;
        std::memcpy(&descriptor, bytes.data() + 8, sizeof(descriptor));
        assert(descriptor == 0 && "new Room inherited a saved-game header as descriptor");
        for (unsigned i = 0; i < bytes.size(); ++i)
            if (i < 8 || i >= 16) assert(bytes[i] == 0xa5);
        // A constructor that supplies its own descriptor must retain that value.
        const std::uintptr_t nativeDescriptor = 0x12345678;
        std::memcpy(bytes.data() + 8, &nativeDescriptor, sizeof(nativeDescriptor));
        called = true;
    });
    std::uintptr_t descriptor;
    std::memcpy(&descriptor, bytes.data() + 8, sizeof(descriptor));
    assert(called && descriptor == 0x12345678);
}
'''


class NativeRoomConstructorTests(unittest.TestCase):
    def test_reused_allocation_initializes_only_descriptor_before_native_constructor(self):
        with tempfile.TemporaryDirectory(prefix='isaac-room-constructor-') as directory:
            source = Path(directory) / 'main.cpp'
            binary = Path(directory) / 'test'
            source.write_text(DRIVER)
            compile_result = subprocess.run([
                shutil.which('clang++') or 'c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'runtime/source'), '-I', str(ROOT / 'runtime/src'),
                str(source), '-o', str(binary),
            ], capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
