"""Cross-assemble the real internal gateway and verify its unwind frame without changing instructions."""
from pathlib import Path
import re
import platform
import shutil
import struct
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

def sections(raw):
 offset=struct.unpack_from('<Q',raw,0x28)[0]
 stride,count,names=struct.unpack_from('<HHH',raw,0x3a)
 entries=[struct.unpack_from('<IIQQQQIIQQ',raw,offset+i*stride) for i in range(count)]
 item=entries[names];strings=raw[item[4]:item[4]+item[5]]
 return {strings[e[0]:strings.find(b'\0',e[0])].decode():raw[e[4]:e[4]+e[5]] for e in entries}

def uleb(value):
 out=[]
 while value>=128:out.append((value&127)|128);value>>=7
 return bytes(out+[value])

class InternalHookUnwindTests(unittest.TestCase):
 def test_unwind_rules_match_actual_context_and_gateway_stack(self):
  compiler=shutil.which('clang')
  if not compiler:self.skipTest('Clang AArch64 assembler unavailable')
  source=(ROOT/'source/relay/internal_hook_context.s').read_text()
  with tempfile.TemporaryDirectory() as task_dir:
   folder=Path(task_dir);outputs=[]
   for name,text in [('actual',source),('instructions',re.sub(r'^\s*\.cfi_.*$','',source,flags=re.M))]:
    asm=folder/(name+'.s');obj=folder/(name+'.o');asm.write_text(text)
    subprocess.run([compiler,'--target=aarch64-linux-gnu','-c',str(asm),'-o',str(obj)],check=True)
    outputs.append(sections(obj.read_bytes()))
   self.assertEqual(outputs[0]['.text.isaac_internal_hook_context'],outputs[1]['.text.isaac_internal_hook_context'])
   frame=outputs[0].get('.eh_frame',b'')
   self.assertTrue(frame,'Internal callbacks call native code but their assembly frame has no FDE')
   # SP is 0x350 below the game frame: 16-byte gateway save + 0x340 context.
   self.assertIn(b'\x0e'+uleb(0x350),frame)
   # Read the assembler's CIE factor (LLVM uses -4, GNU may use another valid factor).
   pos=frame.index(b'\0',9)+1
   while frame[pos]&128:pos+=1
   pos+=1
   factor=0;shift=0
   while True:
    byte=frame[pos];pos+=1;factor|=(byte&127)<<shift;shift+=7
    if not byte&128:break
   if byte&64:factor-=1<<shift
   self.assertLess(factor,0)
   self.assertIn(b'\x9e'+uleb((-8)//factor),frame)
   for reg in range(19,30):
    offset=0x350-reg*8
    self.assertIn(bytes([0x80+reg])+uleb((-offset)//factor),frame)
   for reg in range(8,16):
    offset=0x350-(0x140+reg*16)
    self.assertIn(b'\x05'+uleb(64+reg)+uleb((-offset)//factor),frame)


 def test_native_exception_crosses_actual_gateway_on_aarch64(self):
  if platform.machine() not in {'arm64','aarch64'}:self.skipTest('AArch64 execution unavailable')
  prefix='_' if platform.system()=='Darwin' else ''
  asm=(ROOT/'source/relay/internal_hook_context.s').read_text()
  if prefix:
   asm=re.sub(r'^\.section.*$','.text',asm,flags=re.M)
   asm=re.sub(r'^\.(?:type|size).*\n','',asm,flags=re.M)
   asm=asm.replace('isaac_internal_hook_context','_isaac_internal_hook_context').replace('isaac_internal_hook_dispatch','_isaac_internal_hook_dispatch')
  asm+='\n.text\n.align 2\n.global '+prefix+'test_gateway\n'+prefix+'test_gateway:\n'
  asm+='    stp x17,x30,[sp,#-16]!\n'
  if prefix:asm+='    adrp x17,_test_binding@PAGE\n    add x17,x17,_test_binding@PAGEOFF\n'
  else:asm+='    adrp x17,test_binding\n    add x17,x17,:lo12:test_binding\n'
  asm+='    b '+prefix+'isaac_internal_hook_context\n'
  callback=r"""
#include "relay/internal_hook.hpp"
extern "C" void NativeThrow();
extern "C" std::uint32_t ThrowFromCallback(isaac::runtime::relay::InternalHookContext&,const void*) noexcept {NativeThrow();return 0;}
"""
  driver=r"""
#include "relay/internal_hook.hpp"
#include <stdexcept>
#include <cassert>
using namespace isaac::runtime::relay;
extern "C" {InternalHookBinding test_binding;void test_gateway();std::uint32_t ThrowFromCallback(InternalHookContext&,const void*) noexcept;}
extern "C" void NativeThrow(){throw std::runtime_error("native exception");}
int main(){
 test_binding.callback=ThrowFromCallback;test_binding.scratch=InternalScratchPolicy::ProvedDeadX16;
 test_binding.resumeCount=1;test_binding.resumes[0]=4;
 try {test_gateway();assert(false);}catch(const std::runtime_error&){return 0;}
}
"""
  with tempfile.TemporaryDirectory() as folder:
   folder=Path(folder);(folder/'context.s').write_text(asm);(folder/'callback.cpp').write_text(callback);(folder/'driver.cpp').write_text(driver)
   flags=['-std=c++20','-O1','-funwind-tables','-I',str(ROOT/'source'),'-I',str(ROOT/'src')]
   subprocess.run(['c++',*flags,'-fno-exceptions','-c',str(folder/'callback.cpp'),'-o',str(folder/'callback.o')],check=True)
   subprocess.run(['c++',*flags,'-fno-exceptions','-c',str(ROOT/'source/relay/internal_hook_dispatch.cpp'),'-o',str(folder/'dispatch.o')],check=True)
   binary=folder/'unwind'
   subprocess.run(['c++',*flags,str(folder/'driver.cpp'),str(folder/'context.s'),str(folder/'callback.o'),str(folder/'dispatch.o'),'-o',str(binary)],check=True)
   result=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
