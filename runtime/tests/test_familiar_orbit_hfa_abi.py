"""用生产中实际POD/typedef执行AArch64：x0 this、x1引用、s0/s1返回且不写x8。"""
import platform
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class FamiliarOrbitHfaABITests(unittest.TestCase):
    def test_actual_pointer_arguments_and_two_float_hfa_return(self):
        if platform.machine() not in {'arm64','aarch64'}:
            self.skipTest('真实HFA执行需要已有AArch64宿主')
        source=(ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
        begin=source.index('struct EngineVector2Abi {');end=source.index('};',begin)+2
        layout=source[begin:end]
        typedef=re.search(r'using EntityFamiliarGetOrbitPositionFn\s*=\s*[^;]+;',source).group(0)
        driver=r'''
#include <cstddef>
#include <cstdint>
#include <cassert>
#include <type_traits>
LAYOUT
TYPEDEF
extern "C" {
std::uintptr_t abiSelf{};
std::uintptr_t abiPosition{};
float abiOut[2]{};
std::uint64_t abiFence=0x1122334455667788ULL;
EngineVector2Abi NativeOrbit(std::uintptr_t,const EngineVector2Abi*);
void CaptureCppProvider(std::uintptr_t,const EngineVector2Abi*);
EngineVector2Abi CppProvider(std::uintptr_t self,const EngineVector2Abi* position){
 assert(self==0xabc123&&position->x==12.5F&&position->y==-7.75F);
 return {position->x+1.5F,position->y-3.75F};
}
}
int main(){
 static_assert(sizeof(EngineVector2Abi)==8&&alignof(EngineVector2Abi)==4);
 static_assert(std::is_standard_layout_v<EngineVector2Abi>&&std::is_trivially_copyable_v<EngineVector2Abi>);
 EngineVector2Abi input{12.5F,-7.75F};
 EntityFamiliarGetOrbitPositionFn fn=NativeOrbit;
 auto result=fn(0xabc123,&input);
 assert(abiSelf==0xabc123&&abiPosition==reinterpret_cast<std::uintptr_t>(&input));
 assert(result.x==14.0F&&result.y==-11.5F&&input.x==12.5F&&input.y==-7.75F);
 CaptureCppProvider(0xabc123,&input);
 assert(abiOut[0]==14.0F&&abiOut[1]==-11.5F&&abiFence==0x1122334455667788ULL);
}
'''.replace('LAYOUT',layout).replace('TYPEDEF',typedef)
        darwin=platform.system()=='Darwin';prefix='_' if darwin else ''
        def address(register,name):
            if darwin:return f'adrp {register}, _{name}@PAGE\nadd {register}, {register}, _{name}@PAGEOFF\n'
            return f'adrp {register}, {name}\nadd {register}, {register}, :lo12:{name}\n'
        asm=f'.text\n.global {prefix}NativeOrbit\n.align 2\n{prefix}NativeOrbit:\n'
        asm+=address('x9','abiSelf')+'str x0,[x9]\n'+address('x9','abiPosition')+'str x1,[x9]\n'
        asm+='ldp s2,s3,[x1]\nfmov s4,#1.5\nfmov s5,#3.75\nfadd s0,s2,s4\nfsub s1,s3,s5\nret\n'
        asm+=f'.global {prefix}CaptureCppProvider\n.align 2\n{prefix}CaptureCppProvider:\nstp x29,x30,[sp,#-16]!\n'
        asm+=address('x8','abiFence')+f'bl {prefix}CppProvider\n'+address('x9','abiOut')+'stp s0,s1,[x9]\nldp x29,x30,[sp],#16\nret\n'
        with tempfile.TemporaryDirectory(prefix='isaac-orbit-hfa-') as tmp:
            p=Path(tmp);(p/'driver.cpp').write_text(driver);(p/'abi.s').write_text(asm);binary=p/'driver'
            r=subprocess.run(['clang++','-std=c++23','-O2','-Wall','-Wextra','-Werror',str(p/'driver.cpp'),str(p/'abi.s'),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
