"""生产typedef真实AArch64混合整数/float调用与两个classic字符串引用。"""
import platform
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class StaticEntityMixedAbiTests(unittest.TestCase):
    def test_production_signatures_in_actual_integer_and_float_registers(self):
        if platform.machine() not in {'arm64','aarch64'}:
            self.skipTest('真实寄存器执行需要已有AArch64宿主')
        source=(ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
        names=('EntitySetSpriteFrameFn','EntityTearResetSpriteScaleFn','EntityNpcPlaySoundFn','EntityNpcAnimWalkFrameFn','EntityTearSetScaleFn')
        typedefs='\n'.join(re.search(r'using '+name+r'\s*=\s*[^;]+;',source).group() for name in names)
        layout=re.search(r'struct alignas\(8\) EntityAnimationStringAbi\s*\{[^}]+\};',source).group()
        driver=r'''
#include <cassert>
#include <cstdint>
LAYOUT
TYPEDEFS
extern "C" {
std::uintptr_t capturedSelf{},capturedFirst{},capturedSecond{};
unsigned capturedId{},capturedLoop{};int capturedDelay{},capturedFrame{};
float capturedVolume{},capturedPitch{},capturedThreshold{},capturedScale{};
void NativeFrame(std::uintptr_t,const char*,std::int32_t);
void NativeReset(std::uintptr_t);
void NativeSound(std::uintptr_t,std::uint32_t,float,std::int32_t,bool,float);
void NativeWalk(std::uintptr_t,const EntityAnimationStringAbi*,const EntityAnimationStringAbi*,float);
void NativeScale(std::uintptr_t,float);
}
int main(){
 const char name[]="Frame";EntityAnimationStringAbi h{},v{};
 EntitySetSpriteFrameFn frame=NativeFrame;frame(0x12345,name,-17);
 assert(capturedSelf==0x12345&&capturedFirst==reinterpret_cast<std::uintptr_t>(name)&&capturedFrame==-17);
 EntityTearResetSpriteScaleFn reset=NativeReset;reset(0x9988);assert(capturedSelf==0x9988);
 EntityNpcPlaySoundFn sound=NativeSound;sound(0x54321,0xfffffffeU,0.625F,-3,true,1.25F);
 assert(capturedSelf==0x54321&&capturedId==0xfffffffeU&&capturedVolume==0.625F&&capturedDelay==-3&&capturedLoop==1&&capturedPitch==1.25F);
 EntityNpcAnimWalkFrameFn walk=NativeWalk;walk(0x224466,&h,&v,0.125F);
 assert(capturedSelf==0x224466&&capturedFirst==reinterpret_cast<std::uintptr_t>(&h)&&capturedSecond==reinterpret_cast<std::uintptr_t>(&v)&&capturedThreshold==0.125F);
 static_assert(sizeof(h)==24&&alignof(EntityAnimationStringAbi)==8);
 EntityTearSetScaleFn scale=NativeScale;scale(0x8899,1.5F);assert(capturedSelf==0x8899&&capturedScale==1.5F);
}
'''.replace('LAYOUT',layout).replace('TYPEDEFS',typedefs)
        darwin=platform.system()=='Darwin';prefix='_' if darwin else ''
        def address(register,name):
            return f'adrp {register}, _{name}@PAGE\nadd {register}, {register}, _{name}@PAGEOFF\n' if darwin else f'adrp {register}, {name}\nadd {register}, {register}, :lo12:{name}\n'
        def store(register,name):return address('x9',name)+f'str {register},[x9]\n'
        asm='.text\n'
        specs={'NativeFrame':[('x0','capturedSelf'),('x1','capturedFirst'),('w2','capturedFrame')],
               'NativeReset':[('x0','capturedSelf')],
               'NativeSound':[('x0','capturedSelf'),('w1','capturedId'),('s0','capturedVolume'),('w2','capturedDelay'),('w3','capturedLoop'),('s1','capturedPitch')],
               'NativeWalk':[('x0','capturedSelf'),('x1','capturedFirst'),('x2','capturedSecond'),('s0','capturedThreshold')],
               'NativeScale':[('x0','capturedSelf'),('s0','capturedScale')]}
        for name,fields in specs.items():
            asm+=f'.global {prefix}{name}\n.align 2\n{prefix}{name}:\n'
            asm+=''.join(store(register,field) for register,field in fields)+'ret\n'
        with tempfile.TemporaryDirectory(prefix='isaac-entity-mixed-abi-') as tmp:
            p=Path(tmp);(p/'driver.cpp').write_text(driver);(p/'abi.s').write_text(asm)
            r=subprocess.run(['clang++','-std=c++23','-O2','-Wall','-Wextra','-Werror',str(p/'driver.cpp'),str(p/'abi.s'),'-o',str(p/'driver')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(p/'driver')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
