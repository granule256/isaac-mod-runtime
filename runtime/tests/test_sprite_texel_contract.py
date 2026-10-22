"""独立 AArch64 汇编接收器核对 GetTexel 的 HFA/x8 ABI，不用同型 C++ 假函数自证。"""
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class SpriteTexelAbiTests(unittest.TestCase):
    @unittest.skipUnless(platform.system() == 'Darwin' and platform.machine() == 'arm64',
                         '独立接收器使用 macOS arm64 汇编')
    def test_real_register_contract(self):
        with tempfile.TemporaryDirectory(prefix='sprite-texel-abi-') as folder:
            folder = Path(folder)
            cpp = folder / 'caller.cpp'
            cpp.write_text(r'''
#include "lua_runtime_state.hpp"
extern "C" LuaRuntime::SpriteTexelColor Receive(void*, LuaRuntime::SpriteTexelVector,
                                                LuaRuntime::SpriteTexelVector, float, int);
int main() {
    LuaRuntime::SpriteGetTexelFn method = &Receive;
    auto color = method(reinterpret_cast<void*>(0x1234), {1.25F, 2.5F}, {4.0F, 8.0F}, 0.75F, 6);
    return color.red == 5.25F && color.green == 10.5F && color.blue == 0.75F && color.alpha == 6.0F ? 0 : 1;
}
''')
            asm = folder / 'receiver.s'
            asm.write_text('''.text
.globl _Receive
.p2align 2
_Receive:
    fadd s0, s0, s2
    fadd s1, s1, s3
    scvtf s5, w1
    stp s0, s1, [x8]
    stp s4, s5, [x8, #8]
    ret
''')
            binary = folder / 'contract'
            command = ['c++', '-std=c++23', '-O3', '-I', str(ROOT / 'runtime/source'),
                       '-I', str(ROOT / 'runtime/source/third_party/lua-5.3.3/src'),
                       str(cpp), str(asm), '-o', str(binary)]
            build = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
