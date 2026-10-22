"""66 实际适配器：完整原函数/PLT守卫、两点分别安装、部分失败。"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DRIVER=r'''
#include "infrastructure/internal/internal_hook_adapter.hpp"
#include "trinket_internal_hook.hpp"
#include "trinket_internal_guards.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
using namespace isaac::runtime;
static std::uintptr_t base{};static unsigned installs{};static bool fail{};
namespace isaac::runtime {
std::uint32_t LevelCurseFirstRandomInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t LevelCurseEvaluateInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t PickupSelectionInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t EntityDestructorRemoveInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}

unsigned RoomFixSpawnCtorInternalCallback(relay::InternalHookContext&,const void*) noexcept{return 0;}
unsigned TrinketFirstRandomInternalCallback(relay::InternalHookContext&,const void*) noexcept{return 0;}
unsigned TrinketSelectedInternalCallback(relay::InternalHookContext&,const void*) noexcept{return 0;}
unsigned ClearAwardInternalCallback(relay::InternalHookContext&,const void*) noexcept{return 0;}
}
namespace isaac::runtime::relay {
InternalHookFailure TryInstallPreinstalledInternalHook(const InternalHookBinding&,const ColdInternalHookSite&){return InternalHookFailure::InvalidPlan;}

InternalHookFailure TryInstallInternalHook(const InternalHookBinding& b,const InternalHookSite& s,std::uintptr_t v){
 ++installs;assert(ValidInternalBinding(b));
 const bool first=b.callback==TrinketFirstRandomInternalCallback;
 assert(first||b.callback==TrinketSelectedInternalCallback);
 assert(b.resumeCount==(first?1U:2U)&&b.resumes[0]==base+(first?kTrinketFirstResumeOffset:kTrinketGoldenResumeOffset));
 if(!first)assert(b.resumes[1]==base+kTrinketCleanupResumeOffset);
 assert(s.target==base+(first?kTrinketFirstRandomHookOffset:kTrinketSelectedHookOffset));
 assert(s.expected==(first?kTrinketFirstRandomExpectedWord:kTrinketSelectedExpectedWord));
 assert(v==base+(first?kTrinketFirstVeneerOffset:kTrinketSelectedVeneerOffset));
 auto& n=*static_cast<const TrinketNativeBindings*>(b.user);
 assert(reinterpret_cast<std::uintptr_t>(n.random)==base+0x66fe30&&reinterpret_cast<std::uintptr_t>(n.unlocked)==base+0x670e70);
 assert(n.managerGotSlot==base+kTrinketManagerGotSlotOffset);
 if(fail)return InternalHookFailure::WriteVerifyFailed;
 unsigned branch{};assert(BuildInternalBranch(&branch,s.target,v));
 std::memcpy(reinterpret_cast<void*>(s.target),&branch,4);
 return InternalHookFailure::None;
}
}
int main(){
 std::vector<unsigned char> image(0x68d000);base=reinterpret_cast<std::uintptr_t>(image.data());
 auto reset=[&](){std::memset(image.data(),0,image.size());
  std::memcpy(image.data()+kTrinketGetFunctionOffset,trinket::kOriginalFunction.data(),trinket::kOriginalFunction.size());
  for(auto& g:trinket::kNativeGuards)std::memcpy(image.data()+g.offset,g.bytes.data(),g.bytes.size());
 };
 HookTarget target{};target.base=base;target.codeSize=image.size();target.imageSize=image.size();
 reset();InternalHookAdapter probe;
 for(unsigned site:{kTrinketFirstRandomHookOffset,kTrinketSelectedHookOffset}){
  const auto id=site==kTrinketFirstRandomHookOffset?HookId::ItemPoolTrinketFirstRandom:HookId::ItemPoolTrinketSelected;
  for(unsigned i=0;i<trinket::kOriginalFunction.size();++i){
   image[kTrinketGetFunctionOffset+i]^=1;
   assert(!probe.Install(id,target).ok()&&installs==0&&!probe.IsInstalled(id));
   image[kTrinketGetFunctionOffset+i]^=1;
  }
  for(const auto& g:trinket::kNativeGuards)for(unsigned i=0;i<g.bytes.size();++i){
   image[g.offset+i]^=1;assert(!probe.Install(id,target).ok()&&installs==0);image[g.offset+i]^=1;
  }
 }
 for(bool first:{false,true}){
  reset();InternalHookAdapter a;installs=0;fail=false;
  const auto id=first?HookId::ItemPoolTrinketFirstRandom:HookId::ItemPoolTrinketSelected;
  const auto other=first?HookId::ItemPoolTrinketSelected:HookId::ItemPoolTrinketFirstRandom;
  assert(a.Install(id,target).ok()&&installs==1&&a.IsInstalled(id)&&!a.IsInstalled(other));
  assert(a.Install(id,target).code()==StatusCode::InvalidState&&installs==1);
  fail=true;assert(!a.Install(other,target).ok()&&a.IsInstalled(id)&&!a.IsInstalled(other)&&installs==2);
  fail=false;assert(a.Install(other,target).ok()&&a.IsInstalled(id)&&a.IsInstalled(other)&&installs==3);
 }
 reset();installs=0;InternalHookAdapter small;auto shortImage=target;shortImage.codeSize=kTrinketSelectedVeneerOffset+15;
 assert(!small.Install(HookId::ItemPoolTrinketSelected,shortImage).ok()&&installs==0);
}
'''

class TrinketInternalInstallerTests(unittest.TestCase):
    def test_full_function_fingerprint_matches_original_nro(self):
        nro=next(ROOT.glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro'))
        import re
        text=(ROOT/'runtime/source/trinket_internal_guards.hpp').read_text()
        body=text[text.index('kOriginalFunction = {'):text.index('};')]
        data=bytes(int(x,16) for x in re.findall(r'0x([0-9A-F]{2})',body))
        self.assertEqual(len(data),0x2e0)
        self.assertEqual(nro.read_bytes()[0x3c7600:0x3c78e0],data)

    def test_real_adapter_rejects_all_guard_bytes_and_retains_partial_installs(self):
        with tempfile.TemporaryDirectory(prefix='isaac-trinket-installer-') as tmp:
            p=Path(tmp);(p/'driver.cpp').write_text(DRIVER);exe=p/'driver'
            r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'driver.cpp'),
                str(ROOT/'runtime/src/infrastructure/internal/internal_hook_adapter.cpp'),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
