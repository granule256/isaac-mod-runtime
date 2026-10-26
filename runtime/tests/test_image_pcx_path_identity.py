"""从生产源码取出合成路径关联：同名贴图不能跨目录串图，也不能截断缓存键。"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

class ImagePcxPathIdentityTests(unittest.TestCase):
    def test_full_path_identity_case_separators_and_latest_binding(self):
        cpp = (ROOT / 'runtime/source/image_pcx_bridge_hook.cpp').read_text()
        storage = cpp[cpp.index('constexpr std::size_t kImagePcxSyntheticPathBytes'):cpp.index('// 转码结果缓存')]
        funcs = cpp[cpp.index('bool ImagePcxPathEquals('):cpp.index('// 查缓存：')]
        driver = r'''
#include <atomic>
#include <cstdint>
#include <cstring>
#include <cassert>
#include <string>
#include "infrastructure/resources/small_caches.hpp"
#include "infrastructure/paths/pc_path_semantics.hpp"
STORAGE
FUNCTIONS
static void put(const char* request, const char* png) {
    std::string pcx(png);pcx.replace(pcx.size()-3,3,"pcx");
    ImagePcxRememberPath(pcx.c_str(),png,request);
}
int main() {
    put("gfx/a/skin.pcx", "rom:/mods/a/gfx/skin.png");
    put("gfx/b/skin.pcx", "rom:/mods/b/gfx/skin.png");
    assert(std::strcmp(ImagePcxRingLookup("gfx/a/skin.pcx"), "rom:/mods/a/gfx/skin.png") == 0);
    assert(std::strcmp(ImagePcxRingLookup("GFX\\B\\SKIN.PCX"), "rom:/mods/b/gfx/skin.png") == 0);
    assert(std::strcmp(ImagePcxRingLookup("rom:/mods/b/gfx/skin.pcx"), "rom:/mods/b/gfx/skin.png") == 0);
    assert(ImagePcxRingLookup("gfx/c/skin.pcx") == nullptr);
    put("gfx/a/skin.pcx", "rom:/mods/new/gfx/skin.png");
    assert(std::strcmp(ImagePcxRingLookup("gfx/a/skin.pcx"), "rom:/mods/new/gfx/skin.png") == 0);
    std::string prefix(300, 'x');
    auto a = prefix + "/a/skin.pcx", b = prefix + "/b/skin.pcx";
    auto pa = "rom:/" + prefix + "/a/skin.png", pb = "rom:/" + prefix + "/b/skin.png";
    put(a.c_str(), pa.c_str()); put(b.c_str(), pb.c_str());
    assert(std::strcmp(ImagePcxRingLookup(a.c_str()), pa.c_str()) == 0);
    for (int i = 0; i < 32; ++i) put("gfx/a/skin.pcx", "rom:/mods/new/gfx/skin.png");
    assert(std::strcmp(ImagePcxRingLookup("gfx/a/skin.pcx"), "rom:/mods/new/gfx/skin.png") == 0);
}
'''.replace('STORAGE', storage).replace('FUNCTIONS', funcs)
        if 'requestPath[' in storage: driver = '#define FULL_PATH_RECORD\n' + driver
        compiler = shutil.which('clang++') or shutil.which('g++')
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as td:
            source, binary = Path(td)/'main.cpp', Path(td)/'probe'
            source.write_text(driver)
            result = subprocess.run([compiler, '-std=c++20', '-fno-exceptions', '-I', str(ROOT/'runtime/src'), str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == '__main__': unittest.main()
