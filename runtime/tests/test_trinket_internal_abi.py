"""真实 AArch64 双钩上下文：原帧、DontAdvance、续接清理与部分安装。"""
import platform
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import HARNESS_COMPILE_FLAGS

ROOT=Path(__file__).resolve().parents[2]

DRIVER=r'''
#include "trinket_internal_hook.hpp"
#include <array>
#include <cassert>
#include <cstring>
using namespace isaac::runtime;
using namespace isaac::runtime::relay;
extern "C" {
InternalHookBinding firstBinding{},selectedBinding{};
unsigned firstEnabled=1,secondEnabled=1;
unsigned TestCaller(void*,bool);
void FirstResume();void GoldenResume();void CleanupResume();
void GoldCtor(void*);void GoldDtor(void*);void OtherDtor(void*);
}
alignas(16) static std::array<unsigned char,0x900> pool{},nested{};
alignas(16) static unsigned char manager[64]{};
static std::uintptr_t managerAddress=reinterpret_cast<std::uintptr_t>(manager);
static std::uintptr_t managerVariable=reinterpret_cast<std::uintptr_t>(&managerAddress);
static unsigned randoms=0,unlocks=0,ctors=0,goldDtors=0,otherDtors=0,dispatches=0;
static unsigned replacement=0;static bool golden=false,dont=false,nesting=false,inNested=false;
static unsigned Seed(const void* p){unsigned s;std::memcpy(&s,p,4);return s;}
static void SetSeed(void* p,unsigned s){std::memcpy(p,&s,4);}
extern "C" unsigned Random(void* rng,unsigned maximum){
 assert(maximum==13);++randoms;SetSeed(rng,Seed(rng)+1);return 7;
}
static bool Unlocked(const void* pgd,unsigned achievement){
 assert(pgd==manager+0x18&&achievement==617);++unlocks;return golden;
}
extern "C" bool ReplayUnlocked(){return Unlocked(manager+0x18,617);}
extern "C" void GoldCtor(void*){++ctors;}
extern "C" void GoldDtor(void*){++goldDtors;}
extern "C" void OtherDtor(void*){++otherDtors;}
namespace LuaRuntime {
std::uint32_t DispatchGetTrinket(std::int32_t selected,const std::array<std::uint8_t,16>& state){
 ++dispatches;assert(selected==41);
 assert(Seed(state.data())==(inNested?200U:(dont?100U:101U)));
 assert(state.data()!=pool.data()+0x8d4&&state.data()!=nested.data()+0x8d4);
 if(nesting&&!inNested){
  inNested=true;assert(TestCaller(nested.data(),true)==replacement);inNested=false;
  assert(Seed(state.data())==(dont?100U:101U));
 }
 return replacement;
}
}
int main(){
 TrinketNativeBindings native{Random,Unlocked,reinterpret_cast<std::uintptr_t>(&managerVariable)};
 firstBinding.callback=TrinketFirstRandomInternalCallback;firstBinding.user=&native;
 firstBinding.resumeCount=1;firstBinding.resumes[0]=reinterpret_cast<std::uintptr_t>(&FirstResume);
 firstBinding.scratch=InternalScratchPolicy::ProvedDeadX16;
 selectedBinding.callback=TrinketSelectedInternalCallback;selectedBinding.user=&native;
 selectedBinding.resumeCount=2;selectedBinding.resumes[0]=reinterpret_cast<std::uintptr_t>(&GoldenResume);
 selectedBinding.resumes[1]=reinterpret_cast<std::uintptr_t>(&CleanupResume);
 selectedBinding.scratch=InternalScratchPolicy::ProvedDeadX16;
 for(bool d:{false,true})for(unsigned override:{0U,47U,0xffffffffU})for(bool gold:{false,true}){
  dont=d;replacement=override;golden=gold;firstEnabled=secondEnabled=1;nesting=false;
  randoms=unlocks=ctors=goldDtors=otherDtors=dispatches=0;
  SetSeed(pool.data()+0x8d4,100);SetSeed(nested.data()+0x8d4,200);
  const auto result=TestCaller(pool.data(),dont);
  assert(result==(override?override:(gold?0x8029U:41U)));
  assert(Seed(pool.data()+0x8d4)==(dont?100U:101U));
  assert(randoms==1&&dispatches==1&&unlocks==(override?0U:1U));
  assert(ctors==(!override&&gold?1U:0U)&&goldDtors==ctors&&otherDtors==2);
 }
 for(unsigned mode:{0U,1U})for(bool d:{false,true}){
  dont=d;replacement=47;golden=true;nesting=false;firstEnabled=mode;secondEnabled=1-mode;
  randoms=unlocks=ctors=goldDtors=otherDtors=dispatches=0;SetSeed(pool.data()+0x8d4,100);
  assert(TestCaller(pool.data(),dont)==0x8029&&randoms==1&&unlocks==1&&ctors==1&&goldDtors==1&&otherDtors==2&&dispatches==0);
  assert(Seed(pool.data()+0x8d4)==(dont?100U:101U));
 }
 firstEnabled=secondEnabled=1;dont=false;replacement=47;golden=true;nesting=true;
 randoms=unlocks=ctors=goldDtors=otherDtors=dispatches=0;
 SetSeed(pool.data()+0x8d4,100);SetSeed(nested.data()+0x8d4,200);
 assert(TestCaller(pool.data(),false)==47&&randoms==2&&dispatches==2&&otherDtors==4&&unlocks==0);
 assert(Seed(pool.data()+0x8d4)==101&&Seed(nested.data()+0x8d4)==200);
}
'''

class TrinketInternalABITests(unittest.TestCase):
    def test_actual_register_tagging_cleanup_and_nested_calls(self):
        if platform.machine() not in {'arm64','aarch64'}:
            self.skipTest('需要已有 AArch64 宿主才能执行真实汇编')
        darwin=platform.system()=='Darwin'
        prefix='_' if darwin else ''
        def label(name):return prefix+name
        def address(register,name):
            if darwin:return f'adrp {register}, _{name}@PAGE\nadd {register}, {register}, _{name}@PAGEOFF\n'
            return f'adrp {register}, {name}\nadd {register}, {register}, :lo12:{name}\n'
        context=(ROOT/'runtime/source/relay/internal_hook_context.s').read_text()
        if darwin:
            context=re.sub(r'^\.section.*$', '.text',context,flags=re.M)
            context=re.sub(r'^\.(?:type|size).*\n','',context,flags=re.M)
            context=context.replace('isaac_internal_hook_context','_isaac_internal_hook_context').replace('isaac_internal_hook_dispatch','_isaac_internal_hook_dispatch')
        asm=f'.text\n.global {label("TestCaller")}\n.align 2\n{label("TestCaller")}:\n'
        asm+='sub sp,sp,#0x20\nstp x20,x21,[sp]\nstr x30,[sp,#0x10]\nmov x20,#0xdec\nmov x21,#0xbeef\n'
        asm+=f'bl {label("TestGetTrinket")}\ncmp x20,#0xdec\nb.ne Bad\nmov x8,#0xbeef\ncmp x21,x8\nb.ne Bad\n'
        asm+='ldp x20,x21,[sp]\nldr x30,[sp,#0x10]\nadd sp,sp,#0x20\nret\nBad:\nbrk #0\n'
        asm+=f'.align 2\n{label("TestGetTrinket")}:\nsub sp,sp,#0x90\nstp x29,x30,[sp,#0x30]\nadd x29,sp,#0x30\n'
        for start in (28,26,24,22,20):asm+=f'stp x{start},x{start-1},[sp,#{0x40+(28-start)*8}]\n' if start in (28,26) else ''
        # 与原函数保存形状相同：28/27,26/25,24/23,22/21,20/19。
        asm+='stp x24,x23,[sp,#0x60]\nstp x22,x21,[sp,#0x70]\nstp x20,x19,[sp,#0x80]\n'
        asm+='mov x20,x0\nmov w21,w1\nadd x8,x20,#0x8d4\nldp x9,x10,[x8]\nstp x9,x10,[x29,#-0x10]\ntst w21,#1\nsub x9,x29,#0x10\ncsel x19,x9,x8,ne\nmov x0,x19\nmov w1,#13\n'
        asm+=address('x8','firstEnabled')+'ldr w8,[x8]\ncbz w8,OriginalRandom\nb FirstGateway\nOriginalRandom:\n'
        asm+=f'bl {label("Random")}\nb {label("FirstResume")}\n.global {label("FirstResume")}\n{label("FirstResume")}:\n'
        asm+='cmp w0,#7\nb.ne Bad\nmov w20,#41\n'
        asm+=address('x8','secondEnabled')+'ldr w8,[x8]\ncbz w8,OriginalUnlocked\nb SelectedGateway\nOriginalUnlocked:\nbl '+label('ReplayUnlocked')+'\nb '+label('GoldenResume')+'\n'
        asm+=f'.global {label("GoldenResume")}\n{label("GoldenResume")}:\ncbz w0,{label("CleanupResume")}\nmov x0,sp\nbl {label("GoldCtor")}\nmov x0,sp\nbl {label("GoldDtor")}\norr w20,w20,#0x8000\n'
        asm+=f'.global {label("CleanupResume")}\n{label("CleanupResume")}:\nadd x0,sp,#0x10\nbl {label("OtherDtor")}\nsub x0,x29,#0x10\nbl {label("OtherDtor")}\nmov w0,w20\n'
        for start,off in [(20,0x80),(22,0x70),(24,0x60),(26,0x50),(28,0x40)]:
            other=19 if start==20 else (21 if start==22 else start-1)
            asm+=f'ldp x{start},x{other},[sp,#{off}]\n'
        asm+='ldp x29,x30,[sp,#0x30]\nadd sp,sp,#0x90\nret\n'
        for name,binding in [('FirstGateway','firstBinding'),('SelectedGateway','selectedBinding')]:
            asm+=f'.align 3\n{name}:\nstp x17,x30,[sp,#-16]!\n'+address('x17',binding)+address('x16','isaac_internal_hook_context')+'br x16\n'
        with tempfile.TemporaryDirectory(prefix='isaac-trinket-abi-') as tmp:
            p=Path(tmp);(p/'stdfloat').write_text('#pragma once\nnamespace std {using float16_t=float;using float128_t=long double;}\n')
            (p/'driver.cpp').write_text(DRIVER);(p/'context.s').write_text(context+asm)
            exe=p/'driver'
            r=subprocess.run(['clang++',*HARNESS_COMPILE_FLAGS,'-O2','-I',str(p),
                '-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'driver.cpp'),
                '-I',str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),
                str(p/'context.s'),str(ROOT/'runtime/source/trinket_internal_hook.cpp'),
                str(ROOT/'runtime/source/relay/internal_hook_dispatch.cpp'),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
