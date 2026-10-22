"""编译生产GOT安装器与拦截体，故障注入验证指纹、映射、陌生指针和转发。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from .test_collision_relay_behavior import function
ROOT=Path(__file__).resolve().parents[2]
class NpcAiGotTests(unittest.TestCase):
 def test_actual_installer_and_interceptor(self):
  code=(ROOT/'runtime/source/hook_manager.cpp').read_text()
  a=code.index('RenderPresentRelayInstallResult TryInstallNpcUpdateAiGotSlot(')
  b=code.index("{",a);depth=1;i=b+1
  while depth:
   depth+=(code[i]=="{")-(code[i]=="}");i+=1
  installer=code[a:i]
  constants=(ROOT/'runtime/source/runtime_constants.hpp').read_text()
  names=['kNpcUpdateAiOffset','kNpcUpdateAiExpectedBytes','kNpcUpdateAiStubOffset','kNpcUpdateAiStubExpectedBytes','kNpcUpdateAiGotSlotOffset','kPltResolverOffset']
  defs='\n'.join(re.search(r'inline constexpr [^;]+\b'+n+r'\b[^;]*;',constants).group(0) for n in names)
  driver=r'''
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
using u8=unsigned char;using u32=std::uint32_t;
CONSTANTS
static constexpr std::array<u8,32> kTargetBuildId={1};
struct TargetModule {uintptr_t base;std::size_t size,textSize;std::array<u8,32> buildId;
 bool Contains(uintptr_t a,std::size_t n)const{return a>=base && n<=textSize && a-base<=textSize-n;}};
enum class RenderPresentRelayInstallResult {Success,GotSlotTargetMismatch,GotSlotUnavailable,GotSlotWriteFailed};
constexpr unsigned Perm_R=1,Perm_W=2;
struct MemoryInfo{uintptr_t addr;std::size_t size;unsigned perm;};
static bool rx=true,query=true,writable=true;
static uintptr_t mappedSlot=0;
static unsigned perms=Perm_R|Perm_W;
int svcQueryMemory(MemoryInfo* i,u32*,uintptr_t){i->addr=mappedSlot;i->size=8;i->perm=perms;return query?0:1;}
#define R_FAILED(x) ((x)!=0)
bool PageIsWritable(uintptr_t){return writable;}
bool IsMappedRxModuleCodeWindow(uintptr_t,std::size_t){return rx;}
uintptr_t target_address(uintptr_t b,uintptr_t o){return b+o;}
bool verify_bytes(const u8* a,const u8* b,std::size_t n){return std::memcmp(a,b,n)==0;}
namespace exl::util {class RwPages {uintptr_t p;public:RwPages(uintptr_t a,std::size_t):p(a){} uintptr_t GetRw(){return p;}void Flush(){}};}
namespace isaac::runtime {
 bool ReadEntityIdentity(uintptr_t,std::uint32_t* t,std::uint32_t* v){*t=123;*v=456;return true;}
}
static bool skip=false;static int aiCalls=0,preCalls=0;
namespace LuaRuntime {bool DispatchPreNpcUpdate(uintptr_t,std::int32_t t){assert(t==123);++preCalls;return skip;}}
std::atomic<uintptr_t> g_NpcUpdateAiGotSlotTarget{0};
INTERCEPTOR
INSTALLER
static void original(void* p){assert(p==reinterpret_cast<void*>(0x1234));++aiCalls;}
int main(){
 using R=RenderPresentRelayInstallResult;
 std::vector<u8> image(0xAA1000);
 TargetModule m{reinterpret_cast<uintptr_t>(image.data()),image.size(),0x700000,kTargetBuildId};
 mappedSlot=m.base+kNpcUpdateAiGotSlotOffset;
 auto* slot=reinterpret_cast<uintptr_t*>(mappedSlot);
 auto reset=[&]{std::memcpy(image.data()+kNpcUpdateAiOffset,kNpcUpdateAiExpectedBytes.data(),16);
 std::memcpy(image.data()+kNpcUpdateAiStubOffset,kNpcUpdateAiStubExpectedBytes.data(),16);
 *slot=m.base+kNpcUpdateAiOffset;rx=true;query=true;perms=Perm_R|Perm_W;writable=true;};
 reset();auto saved=m.buildId;m.buildId={};assert(TryInstallNpcUpdateAiGotSlot(m)==R::GotSlotTargetMismatch);m.buildId=saved;
 reset();rx=false;assert(TryInstallNpcUpdateAiGotSlot(m)==R::GotSlotTargetMismatch);
 reset();image[kNpcUpdateAiOffset]^=1;assert(TryInstallNpcUpdateAiGotSlot(m)==R::GotSlotTargetMismatch);
 reset();image[kNpcUpdateAiStubOffset]^=1;assert(TryInstallNpcUpdateAiGotSlot(m)==R::GotSlotTargetMismatch);
 reset();query=false;assert(TryInstallNpcUpdateAiGotSlot(m)==R::GotSlotUnavailable);
 reset();perms=0;assert(TryInstallNpcUpdateAiGotSlot(m)==R::GotSlotUnavailable);
 reset();*slot=0x777;assert(TryInstallNpcUpdateAiGotSlot(m)==R::GotSlotTargetMismatch&&*slot==0x777);
 reset();assert(TryInstallNpcUpdateAiGotSlot(m)==R::Success&&g_NpcUpdateAiGotSlotTarget==m.base+kNpcUpdateAiOffset);
 assert(*slot==reinterpret_cast<uintptr_t>(&IsaacModRuntime_NpcUpdateAiGotSlotIntercept));
 reset();*slot=m.base+kPltResolverOffset;writable=false;assert(TryInstallNpcUpdateAiGotSlot(m)==R::Success);
 reset();auto size=m.size;m.size=kNpcUpdateAiGotSlotOffset+7;assert(TryInstallNpcUpdateAiGotSlot(m)==R::GotSlotTargetMismatch);m.size=size;
 g_NpcUpdateAiGotSlotTarget=reinterpret_cast<uintptr_t>(&original);
 IsaacModRuntime_NpcUpdateAiGotSlotIntercept(reinterpret_cast<void*>(0x1234));assert(aiCalls==1&&preCalls==1);
 skip=true;IsaacModRuntime_NpcUpdateAiGotSlotIntercept(reinterpret_cast<void*>(0x1234));assert(aiCalls==1&&preCalls==2);
 skip=false;IsaacModRuntime_NpcUpdateAiGotSlotIntercept(reinterpret_cast<void*>(0x1234));assert(aiCalls==2&&preCalls==3);
}
'''.replace('CONSTANTS',defs).replace('INTERCEPTOR',function(code,'IsaacModRuntime_NpcUpdateAiGotSlotIntercept')).replace('INSTALLER',installer)
  with tempfile.TemporaryDirectory() as td:
   source,binary=Path(td)/'main.cpp',Path(td)/'probe';source.write_text(driver)
   r=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':unittest.main()
