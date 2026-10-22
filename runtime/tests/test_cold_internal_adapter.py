"""生产内部适配器：完整两个原函数、cold门/原指令与首Random目标核验。"""
import struct,unittest
from pathlib import Path
from . import test_internal_hook_adapter as helper
from tools.cold_static_callbacks import gate_image,branch
ROOT=helper.ROOT
DRIVER=r'''
#include "infrastructure/internal/internal_hook_adapter.hpp"
#include "cold_callbacks_internal_hook.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
using namespace isaac::runtime;
std::uintptr_t base{};unsigned first{},cold{};
namespace isaac::runtime {
std::uint32_t RoomFixSpawnCtorInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t ClearAwardInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t TrinketFirstRandomInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t TrinketSelectedInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t EntityDestructorRemoveInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t LevelCurseFirstRandomInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t LevelCurseEvaluateInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t PickupSelectionInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
}
namespace isaac::runtime::relay {
InternalHookFailure TryInstallInternalHook(const InternalHookBinding& b,const InternalHookSite& s,std::uintptr_t v){
 assert(b.callback==LevelCurseFirstRandomInternalCallback&&b.resumes[0]==base+0x3e0b38&&s.target==base+0x3e0b34&&v==base+0x68cf98&&s.veneerKind==InternalVeneerKind::Literal8&&s.literalSlot==base+0x68cd70);
 auto* n=static_cast<const ColdCallbackNativeBindings*>(b.user);assert(reinterpret_cast<std::uintptr_t>(n->random)==base+0x66fe30);
 unsigned word{};assert(BuildInternalBranch(&word,s.target,v));std::memcpy(reinterpret_cast<void*>(s.target),&word,4);++first;return InternalHookFailure::None;
}
InternalHookFailure TryInstallPreinstalledInternalHook(const InternalHookBinding& b,const ColdInternalHookSite& s){
 bool pickup=b.callback==PickupSelectionInternalCallback;assert(pickup||b.callback==LevelCurseEvaluateInternalCallback);
 bool special=s.source==base+0x269d08;
 assert(s.source==base+(pickup?(special?0x269d08:0x269d50):0x3e0c88)&&s.gate==base+(pickup?(special?0x68cd00:0x68cde0):0x68cdc0));
 assert(s.original==(pickup?(special?0xb85fc3b4:0x7100a29f):0xf9400309)&&b.resumes[0]==s.gate+16);++cold;return InternalHookFailure::None;
}}
int main(){
 std::vector<unsigned char> image(0x68d000);base=reinterpret_cast<std::uintptr_t>(image.data());
 auto copy=[&](unsigned off,std::initializer_list<unsigned char> bytes){std::memcpy(image.data()+off,bytes.begin(),bytes.size());};
 ORIGINALS
 unsigned w{};w=0xf9400309;std::memcpy(image.data()+0x3e0c88,&w,4);
 HookTarget t{};t.base=base;t.codeSize=image.size();t.imageSize=image.size();t.buildId=kTargetBuildId;InternalHookAdapter a;
 assert(!a.Install(HookId::LevelCurseFirstRandom,t).ok()&&first==0); // 缺cold IPS绝不先改BL。
 copy(0x3e0c88,{CURSE_SOURCE});copy(0x269d50,{PICKUP_SOURCE});copy(0x269d08,{SPECIAL_SOURCE});
 for(auto spec:{std::array<unsigned,3>{0x3e0688,0x1088,0},std::array<unsigned,3>{0x269594,0x13e8,1}}){
  auto id=spec[2]?HookId::PickupSelection:HookId::LevelCurseEvaluation;
  for(unsigned i=0;i<spec[1];++i){image[spec[0]+i]^=1;assert(!a.Install(id,t).ok()&&cold==0);image[spec[0]+i]^=1;}
 }
 for(unsigned gate:{0x68cdc0,0x68cde0,0x68cd00})for(unsigned i=0;i<24;++i){image[gate+i]^=1;assert(!a.Install(gate==0x68cdc0?HookId::LevelCurseEvaluation:gate==0x68cd00?HookId::PickupSelectionSpecial:HookId::PickupSelection,t).ok()&&cold==0);image[gate+i]^=1;}
 for(unsigned i=0;i<16;++i){image[0x66fe30+i]^=1;assert(!a.Install(HookId::LevelCurseFirstRandom,t).ok()&&first==0);image[0x66fe30+i]^=1;}
 assert(a.Install(HookId::LevelCurseFirstRandom,t).ok()&&first==1);
 assert(a.Install(HookId::LevelCurseEvaluation,t).ok()&&cold==1);
 assert(a.Install(HookId::PickupSelection,t).ok()&&cold==2);
 assert(a.IsInstalled(HookId::LevelCurseEvaluation)&&a.IsInstalled(HookId::PickupSelection));
 assert(!a.Install(HookId::PickupSelection,t).ok()&&cold==2);
 assert(a.Install(HookId::PickupSelectionSpecial,t).ok()&&cold==3);
}
'''
class ColdInternalAdapterTests(unittest.TestCase):
 def test_full_original_functions_gate_and_original_random(self):
  n=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  def init(o,b):return f'copy(0x{o:x},{{'+','.join(map(str,b))+'});'
  originals='\n'.join([init(0x3e0688,n[0x3e0688:0x3e1710]),init(0x269594,n[0x269594:0x26a97c]),init(0x66fe30,n[0x66fe30:0x66fe40]),init(0x68cdc0,gate_image(0x3e0c88,0x68cdc0,0xf9400309)),init(0x68cde0,gate_image(0x269d50,0x68cde0,0x7100a29f)),init(0x68cd00,gate_image(0x269d08,0x68cd00,0xb85fc3b4))])
  driver=DRIVER.replace('ORIGINALS',originals).replace('CURSE_SOURCE',','.join(map(str,struct.pack('<I',branch(0x3e0c88,0x68cdc0))))).replace('PICKUP_SOURCE',','.join(map(str,struct.pack('<I',branch(0x269d50,0x68cde0)))))
  driver=driver.replace('SPECIAL_SOURCE',','.join(map(str,struct.pack('<I',branch(0x269d08,0x68cd00)))))
  helper.InternalHookAdapterTests().compile_run(driver,[helper.CPP])
