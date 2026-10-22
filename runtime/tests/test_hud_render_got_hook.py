"""编译生产HUD GOT安装器及typed拦截体，拒绝缺槽/守卫不符并保持原生一次。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from .test_collision_relay_behavior import function
ROOT=Path(__file__).resolve().parents[2]
class HudRenderGotTests(unittest.TestCase):
 def test_actual_installer_and_interceptor(self):
  code=(ROOT/'runtime/source/hook_manager.cpp').read_text()
  self.assertTrue('RenderPresentRelayInstallResult TryInstallHudRenderGotSlot(' in code,'缺少HUD原生调用点的GOT安装器')
  a=code.index('RenderPresentRelayInstallResult TryInstallHudRenderGotSlot(')
  b=code.index("{",a);depth=1;i=b+1
  while depth:
   depth+=(code[i]=="{")-(code[i]=="}");i+=1
  installer=code[a:i]
  constants=(ROOT/'runtime/source/runtime_constants.hpp').read_text()
  names=['kHudRenderOffset','kHudRenderExpectedBytes','kHudRenderStubOffset','kHudRenderStubExpectedBytes','kHudRenderGotSlotOffset','kPltResolverOffset']
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
#include "domain/runtime/render_frame_coordinator.hpp"
isaac::runtime::RenderFrameCoordinator g_RenderFrameCoordinator;
static int hudCalls=0,modCalls=0;
void DispatchModPostRender(void* manager){assert(manager==reinterpret_cast<void*>(0x9999));++modCalls;}
std::atomic<uintptr_t> g_HudRenderGotSlotTarget{0};
INTERCEPTOR
INSTALLER
static void original(void* p){assert(p==reinterpret_cast<void*>(0x1234));++hudCalls;}
int main(){
 using R=RenderPresentRelayInstallResult;
 std::vector<u8> image(0xAA4000);
 TargetModule m{reinterpret_cast<uintptr_t>(image.data()),image.size(),0x700000,kTargetBuildId};
 mappedSlot=m.base+kHudRenderGotSlotOffset;
 auto* slot=reinterpret_cast<uintptr_t*>(mappedSlot);
 auto reset=[&]{std::memcpy(image.data()+kHudRenderOffset,kHudRenderExpectedBytes.data(),16);
 std::memcpy(image.data()+kHudRenderStubOffset,kHudRenderStubExpectedBytes.data(),16);
 *slot=m.base+kHudRenderOffset;rx=true;query=true;perms=Perm_R|Perm_W;writable=true;};
 reset();auto saved=m.buildId;m.buildId={};assert(TryInstallHudRenderGotSlot(m)==R::GotSlotTargetMismatch);m.buildId=saved;
 reset();rx=false;assert(TryInstallHudRenderGotSlot(m)==R::GotSlotTargetMismatch);
 reset();image[kHudRenderOffset]^=1;assert(TryInstallHudRenderGotSlot(m)==R::GotSlotTargetMismatch);
 reset();image[kHudRenderStubOffset]^=1;assert(TryInstallHudRenderGotSlot(m)==R::GotSlotTargetMismatch);
 reset();query=false;assert(TryInstallHudRenderGotSlot(m)==R::GotSlotUnavailable);
 reset();perms=0;assert(TryInstallHudRenderGotSlot(m)==R::GotSlotUnavailable);
 reset();*slot=0x777;assert(TryInstallHudRenderGotSlot(m)==R::GotSlotTargetMismatch&&*slot==0x777);
 reset();assert(TryInstallHudRenderGotSlot(m)==R::Success&&g_HudRenderGotSlotTarget==m.base+kHudRenderOffset);
 assert(*slot==reinterpret_cast<uintptr_t>(&IsaacModRuntime_HudRenderGotSlotIntercept));
 reset();*slot=m.base+kPltResolverOffset;writable=false;assert(TryInstallHudRenderGotSlot(m)==R::Success);
 reset();auto size=m.size;m.size=kHudRenderGotSlotOffset+7;assert(TryInstallHudRenderGotSlot(m)==R::GotSlotTargetMismatch);m.size=size;
 g_HudRenderGotSlotTarget=reinterpret_cast<uintptr_t>(&original);
 IsaacModRuntime_HudRenderGotSlotIntercept(reinterpret_cast<void*>(0x1234));assert(hudCalls==1&&modCalls==0);
 {isaac::runtime::RenderFrameScope frame(g_RenderFrameCoordinator,reinterpret_cast<void*>(0x9999));
  IsaacModRuntime_HudRenderGotSlotIntercept(reinterpret_cast<void*>(0x1234));assert(hudCalls==2&&modCalls==1);
  IsaacModRuntime_HudRenderGotSlotIntercept(reinterpret_cast<void*>(0x1234));assert(hudCalls==3&&modCalls==1);}
 IsaacModRuntime_HudRenderGotSlotIntercept(reinterpret_cast<void*>(0x1234));assert(hudCalls==4&&modCalls==1);
}
'''.replace('CONSTANTS',defs).replace('INTERCEPTOR',function(code,'IsaacModRuntime_HudRenderGotSlotIntercept')).replace('INSTALLER',installer)
  with tempfile.TemporaryDirectory() as td:
   source,binary=Path(td)/'main.cpp',Path(td)/'probe';source.write_text(driver)
   r=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),str(source),'-o',str(binary)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':unittest.main()
