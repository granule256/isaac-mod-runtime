"""70真实适配器：完整指纹逐字拒绝、8B空间及固定两续接点。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_internal_hook_adapter as helper
ROOT=Path(__file__).resolve().parents[2]
class ClearAwardAdapterTests(unittest.TestCase):
 def test_native_image_every_byte_and_page_veneer_binding(self):
  nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  raw=nro[0x456810:0x459438];ctor=nro[0x4fd0a0:0x4fd0ac]
  driver=r'''
#include "infrastructure/internal/internal_hook_adapter.hpp"
#include "clear_award_internal_hook.hpp"
#include "trinket_internal_hook.hpp"
#include "room_spawn_internal_hook.hpp"
#include <cassert>
#include <vector>
#include <cstring>
using namespace isaac::runtime;
std::uintptr_t base{};unsigned installs{};
namespace isaac::runtime {
std::uint32_t LevelCurseFirstRandomInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t LevelCurseEvaluateInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t PickupSelectionInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t EntityDestructorRemoveInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}

std::uint32_t ClearAwardInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t RoomFixSpawnCtorInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t TrinketFirstRandomInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t TrinketSelectedInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
}
namespace isaac::runtime::relay {
InternalHookFailure TryInstallPreinstalledInternalHook(const InternalHookBinding&,const ColdInternalHookSite&){return InternalHookFailure::InvalidPlan;}

InternalHookFailure TryInstallInternalHook(const InternalHookBinding& b,const InternalHookSite&s,std::uintptr_t v){
 assert(ValidInternalBinding(b)&&b.callback==ClearAwardInternalCallback&&b.resumeCount==2);
 assert(b.resumes[0]==base+0x45698c&&b.resumes[1]==base+0x458170);
 assert(s.target==base+0x456988&&s.expected==0x940864d2&&s.veneerKind==InternalVeneerKind::Literal8&&s.literalSlot==base+0x68cd68);
 assert(v==base+0x68cdb8);
 auto& native=*static_cast<const ClearAwardNativeBindings*>(b.user);
 assert(reinterpret_cast<std::uintptr_t>(native.constructVector)==base+0x4fd0a0);
 ++installs;return InternalHookFailure::None;
}}
int main(){
 std::vector<unsigned char> image(0x68d000);base=reinterpret_cast<std::uintptr_t>(image.data());
 unsigned char original[]={ORIGINAL};unsigned char ctor[]={CTOR};
 std::memcpy(image.data()+0x456810,original,sizeof(original));std::memcpy(image.data()+0x4fd0a0,ctor,sizeof(ctor));
 HookTarget t{};t.base=base;t.codeSize=image.size();t.imageSize=image.size();
 for(unsigned i=0;i<sizeof(original);++i){
  image[0x456810+i]^=1;InternalHookAdapter a;assert(!a.Install(HookId::RoomClearAward,t).ok()&&!installs);
  image[0x456810+i]^=1;
 }
 for(unsigned i=0;i<sizeof(ctor);++i){
  image[0x4fd0a0+i]^=1;InternalHookAdapter a;assert(!a.Install(HookId::RoomClearAward,t).ok()&&!installs);
  image[0x4fd0a0+i]^=1;
 }
 InternalHookAdapter a;assert(a.Install(HookId::RoomClearAward,t).ok()&&installs==1);
 assert(a.IsInstalled(HookId::RoomClearAward)&&!a.Install(HookId::RoomClearAward,t).ok());
}
'''.replace('ORIGINAL',','.join(str(v) for v in raw)).replace('CTOR',','.join(str(v) for v in ctor))
  helper.InternalHookAdapterTests().compile_run(driver,[ROOT/'runtime/src/infrastructure/internal/internal_hook_adapter.cpp'])
