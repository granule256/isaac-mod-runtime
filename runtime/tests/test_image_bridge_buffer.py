"""贴图桥的缓冲区在内存不足时保持有效，转码结果转移时不再复制一整张图。"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DRIVER = r'''
#include "infrastructure/memory/nothrow_bytes.hpp"
#include <cassert>
#include <cstdlib>
#include <new>
#include <utility>
static bool fail_next = false;
static int live = 0;
void* operator new[](std::size_t n, const std::nothrow_t&) noexcept {
    if (fail_next) { fail_next = false; return nullptr; }
    void* p = std::malloc(n); if (p) ++live; return p;
}
void operator delete[](void* p) noexcept { if (p) { --live; std::free(p); } }
int main() {
    using isaac::runtime::memory::NothrowBytes;
    {
        NothrowBytes bytes;
        assert(bytes.data() == nullptr && bytes.size() == 0);
        assert(bytes.Resize(64)); bytes.data()[0] = 0x5a;
        auto* original = bytes.data();
        fail_next = true;
        assert(!bytes.Resize(128));
        assert(bytes.data() == original && bytes.size() == 64 && bytes.data()[0] == 0x5a);
        NothrowBytes moved(std::move(bytes));
        assert(moved.data() == original && bytes.data() == nullptr && bytes.size() == 0);
        NothrowBytes target; assert(target.Resize(8));
        target = std::move(moved);
        assert(live == 1 && target.data() == original && moved.data() == nullptr);
        auto* raw = new (std::nothrow) unsigned char[32];
        auto adopted = NothrowBytes::Adopt(raw, 32);
        assert(adopted.data() == raw && adopted.size() == 32 && live == 2);
        assert(target.Resize(0)); assert(target.data() == nullptr && live == 1);
    }
    assert(live == 0);
}
'''


class ImageBridgeBufferTests(unittest.TestCase):
    def test_failed_allocation_and_owned_transfer(self):
        compiler = shutil.which("clang++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("需要宿主 C++ 编译器")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, binary = directory / "main.cpp", directory / "probe"
            source.write_text(DRIVER)
            compiled = subprocess.run(
                [compiler, "-std=c++20", "-fno-exceptions", "-I", str(ROOT / "runtime/src"),
                 str(source), "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_bridge_does_not_allocate_throwing_vectors(self):
        source = (ROOT / "runtime/source/image_pcx_bridge_hook.cpp").read_text()
        self.assertNotIn("std::vector<", source)
        self.assertIn("NothrowBytes::Adopt", source)


if __name__ == "__main__":
    unittest.main()
