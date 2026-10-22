"""真实AArch64执行22两种条件，null/active均保内建分支、寄存器及NZCV。"""
import platform,re,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class ConsoleBranchArmTests(unittest.TestCase):
 def test_null_and_active_real_context(self):
  if platform.machine() not in ('arm64','aarch64'):self.skipTest('需要已有AArch64宿主')
  darwin=platform.system()=='Darwin';prefix='_' if darwin else ''
  context=(ROOT/'runtime/source/relay/internal_hook_context.s').read_text()
  if darwin:
   context=re.sub(r'^\.section.*$','.text',context,flags=re.M);context=re.sub(r'^\.(?:type|size).*\n','',context,flags=re.M)
   context=context.replace('isaac_internal_hook_context','_isaac_internal_hook_context').replace('isaac_internal_hook_dispatch','_isaac_internal_hook_dispatch')
  context+=f'''
.text
.global {prefix}InvokeConsoleBranch
.align 2
{prefix}InvokeConsoleBranch:
stp x28,x29,[sp,#-32]!
str x30,[sp,#16]
mov x9,x0
mov x29,x1
mov x0,x2
cmp w3,#4
blr x9
ldr x30,[sp,#16]
ldp x28,x29,[sp],#32
ret
'''
  driver=r'''
#include "console_callback_hook.hpp"
#include <cassert>
#include <cstring>
#include <sys/mman.h>
#include <pthread.h>
using namespace isaac::runtime;
extern "C" void isaac_internal_hook_context();
struct Output{std::uint64_t value,flags;};
extern "C" Output InvokeConsoleBranch(void*,void*,std::uint64_t,std::uint32_t);
static unsigned calls{};
namespace LuaRuntime {void DispatchExecuteCommand(const ConsoleCommandView& v)noexcept{assert(v.count==1);++calls;}}
int main(){
 auto* mem=static_cast<unsigned char*>(mmap(nullptr,4096,PROT_READ|PROT_WRITE|PROT_EXEC,MAP_PRIVATE|MAP_ANON|JITFLAG,-1,0));assert(mem!=MAP_FAILED);
 auto base=reinterpret_cast<std::uintptr_t>(mem),source=base+64,gate=base+128,gateway=base+256;
 alignas(16)unsigned char frame[64]{},token[24]{};auto begin=reinterpret_cast<std::uintptr_t>(token),end=begin+24;
 memcpy(frame,&begin,8);memcpy(frame+8,&end,8);
 for(unsigned compare=0;compare<2;++compare){
  WRITE_OFF memset(mem,0,4096);
  unsigned branch{},taken{},fallthrough{};assert(relay::BuildInternalBranch(&branch,source,gate));
  assert(relay::BuildInternalBranch(&taken,gate+20,base+400));assert(relay::BuildInternalBranch(&fallthrough,gate+24,source+4));
  memcpy(mem+64,&branch,4);
  const unsigned builtin[]={0xd2800280,0xd53b4201,0xd65f03c0},unknown[]={0xd2800140,0xd53b4201,0xd65f03c0};
  memcpy(mem+68,builtin,12);memcpy(mem+400,unknown,12);
  const unsigned code[]={0x10000110,0xc8dffe10,0xb4000050,0xd61f0200,compare?0x34000040U:0x54000040U,taken,fallthrough,0xd503201f};memcpy(mem+128,code,32);
  ConsoleUnknownBindings native{compare!=0,nullptr};relay::InternalHookBinding b{};
  b.callback=ConsoleUnknownInternalCallback;b.user=&native;b.resumeCount=2;b.resumes[0]=base+400;b.resumes[1]=source+4;b.scratch=relay::InternalScratchPolicy::ProvedDeadX16;
  relay::BuildInternalGateway(mem+256,reinterpret_cast<std::uintptr_t>(&b),reinterpret_cast<std::uintptr_t>(&isaac_internal_hook_context));
  __builtin___clear_cache(reinterpret_cast<char*>(mem),reinterpret_cast<char*>(mem+4096));WRITE_ON
  for(unsigned active=0;active<2;++active){
   if(active){WRITE_OFF __atomic_store_n(reinterpret_cast<std::uintptr_t*>(mem+160),gateway,__ATOMIC_RELEASE);WRITE_ON}
   for(unsigned unknownPath=0;unknownPath<2;++unknownPath){calls=0;auto got=InvokeConsoleBranch(mem+64,frame+48,compare?unknownPath:123,compare?4:4+unknownPath);
    assert(got.value==(unknownPath?10:20));assert(calls==(active&&unknownPath?1:0));
    assert((got.flags&0xf0000000ULL)==(!compare&&unknownPath?0x20000000ULL:0x60000000ULL));
   }
  }
 }
 munmap(mem,4096);
}
'''.replace('JITFLAG','MAP_JIT' if darwin else '0').replace('WRITE_OFF','pthread_jit_write_protect_np(0);' if darwin else '').replace('WRITE_ON','pthread_jit_write_protect_np(1);' if darwin else '')
  with tempfile.TemporaryDirectory(prefix='isaac-console-arm-')as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(driver);(p/'context.s').write_text(context)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(p/'context.s'),str(ROOT/'runtime/source/relay/internal_hook_dispatch.cpp'),str(ROOT/'runtime/source/console_callback_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
