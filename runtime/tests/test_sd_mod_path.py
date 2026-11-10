"""Compile the actual import-wrapper path mapper with host-only dependencies."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SdModPathTests(unittest.TestCase):
    def test_dot_segments_preserve_filesystem_ownership(self):
        source = (ROOT / 'runtime/src/infrastructure/persistence/sd_storage.cpp').read_text()
        start = source.index('const char* ModPath(')
        end = source.index('\nstd::uint32_t OpenModFile', start)
        driver = r'''
        #include <atomic>
        #include <cstdio>
        #include <cstring>
        #include <cassert>
        std::atomic<bool> g_sdMods{true};
        ''' + source[start:end] + r'''
        int main() {
            char path[768];
            const char* outside="rom:/isaac_mods/../native.bin";
            assert(ModPath(outside,path)==outside);
            assert(std::strcmp(ModPath("rom:/isaac_mods/mods/foo/../bar/main.lua",path),
                               "isaacsd:/isaac_mods/mods/bar/main.lua")==0);
            assert(std::strcmp(ModPath("rom:/isaac_mods/../isaac_mods/mods/a",path),
                               "isaacsd:/isaac_mods/mods/a")==0);
            const char* other="rom:/isaac_mods_extra/file";
            assert(ModPath(other,path)==other);
            g_sdMods=false;
            const char* original="rom:/isaac_mods/mods/a";
            assert(ModPath(original,path)==original);
        }
        '''
        with tempfile.TemporaryDirectory() as tmp:
            cpp = Path(tmp) / 'paths.cpp'; cpp.write_text(driver)
            binary = Path(tmp) / 'paths'
            built = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                                    str(cpp), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
