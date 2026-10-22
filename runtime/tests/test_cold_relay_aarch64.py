"""真实AArch64执行原32B cold门：null/active、LDR/CMP、完整gateway/context续接。"""
import platform,re,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class ColdRelayHardwareTests(unittest.TestCase):
 def test_null_and_active_original_instruction_and_flags(self):
  if platform.machine() not in ('arm64','aarch64'):self.skipTest('需要已有AArch64宿主')
  darwin=platform.system()=='Darwin';prefix='_' if darwin else ''
  context=(ROOT/'runtime/source/relay/internal_hook_context.s').read_text()
  if darwin:
   context=re.sub(r'^\.section.*$','.text',context,flags=re.M);context=re.sub(r'^\.(?:type|size).*\n','',context,flags=re.M)
   context=context.replace('isaac_internal_hook_context','_isaac_internal_hook_context').replace('isaac_internal_hook_dispatch','_isaac_internal_hook_dispatch')
  entry=f'''
.text
.global {prefix}InvokeCold
.align 2
{prefix}InvokeCold:
stp x20,x24,[sp,#-32]!
stp x29,x30,[sp,#16]
mov x24,x1
mov x29,x1
mov x20,x2
blr x0
ldp x20,x24,[sp]
ldp x29,x30,[sp,#16]
add sp,sp,#32
ret
'''
  driver=r'''
#include "relay/internal_hook.hpp"
#include <cassert>
#include <cstdint>
#include <cstring>
#include <sys/mman.h>
#include <pthread.h>
using namespace isaac::runtime::relay;
extern "C" void isaac_internal_hook_context();
struct Output{std::uint64_t value,flags;};
extern "C" Output InvokeCold(void*,void*,std::uint64_t);
static unsigned mode{};static unsigned calls{};static std::uint64_t stored=0x12345678;
static unsigned callback(InternalHookContext& ctx,const void*)noexcept{
 ++calls;if(mode==1)ctx.x[20]=40;else if(mode==2)*reinterpret_cast<unsigned*>(ctx.x[29]-4)=40;else stored=0xabcdef01;return 0;
}
int main(){
 constexpr unsigned jitflag=JITFLAG;
 auto* memory=static_cast<unsigned char*>(mmap(nullptr,4096,PROT_READ|PROT_WRITE|PROT_EXEC,MAP_PRIVATE|MAP_ANON|jitflag,-1,0));assert(memory!=MAP_FAILED);
 auto base=reinterpret_cast<std::uintptr_t>(memory);auto source=base+64,gate=base+128,gateway=base+192;
 alignas(16)unsigned char frame[32]{};
 for(mode=0;mode<3;++mode){
  WRITE_OFF
  std::memset(memory,0,4096);std::uint32_t jump{},back{};assert(BuildInternalBranch(&jump,source,gate));assert(BuildInternalBranch(&back,gate+20,source+4));
  std::memcpy(memory+64,&jump,4);
  // resume: MOV x0,x9 / MRS x1,NZCV / RET。
  const unsigned resume[]={mode==2?0xaa1403e0U:0xaa0903e0U,0xd53b4201,0xd65f03c0};std::memcpy(memory+68,resume,sizeof(resume));
  const unsigned original=mode==1?0x7100a29f:mode==2?0xb85fc3b4:0xf9400309;
  const unsigned code[]={0x100000d0,0xc8dffe10,0xb4000050,0xd61f0200,original,back};std::memcpy(memory+128,code,sizeof(code));
  InternalHookBinding binding{};binding.callback=callback;binding.resumes[0]=gate+16;binding.resumeCount=1;binding.scratch=InternalScratchPolicy::ProvedDeadX16;
  BuildInternalGateway(memory+192,reinterpret_cast<std::uintptr_t>(&binding),reinterpret_cast<std::uintptr_t>(&isaac_internal_hook_context));
  __builtin___clear_cache(reinterpret_cast<char*>(memory),reinterpret_cast<char*>(memory+4096));WRITE_ON
  calls=0;stored=0x12345678;unsigned initial=10;std::memcpy(frame+12,&initial,4);
  auto* input=mode==2?static_cast<void*>(frame+16):static_cast<void*>(&stored);auto zero=InvokeCold(memory+64,input,20);assert(calls==0);
  if(mode==1)assert((zero.flags&0xf0000000)==0x80000000);else assert(zero.value==(mode==2?10:0x12345678));
  WRITE_OFF __atomic_store_n(reinterpret_cast<std::uintptr_t*>(memory+152),gateway,__ATOMIC_RELEASE);WRITE_ON
  auto active=InvokeCold(memory+64,input,20);assert(calls==1);
  if(mode==1)assert((active.flags&0xf0000000)==0x60000000);else assert(active.value==(mode==2?40:0xabcdef01));
 }
 munmap(memory,4096);
}
'''.replace('JITFLAG','MAP_JIT' if darwin else '0').replace('WRITE_OFF','pthread_jit_write_protect_np(0);' if darwin else '').replace('WRITE_ON','pthread_jit_write_protect_np(1);' if darwin else '')
  with tempfile.TemporaryDirectory(prefix='isaac-cold-arm-') as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(driver);(p/'context.s').write_text(context+entry)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(p/'context.s'),str(ROOT/'runtime/source/relay/internal_hook_dispatch.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
