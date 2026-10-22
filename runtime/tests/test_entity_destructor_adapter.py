"""真实D2逐字指纹、8字节近桩、原RNG析构目标和唯一续接点。"""
import unittest
from pathlib import Path
from . import test_internal_hook_adapter as adapter_fixture
ROOT, CPP = adapter_fixture.ROOT, adapter_fixture.CPP

class EntityDestructorAdapterTests(unittest.TestCase):
    def test_full_original_dtor_guard_and_native_binding(self):
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        original=nro[0x589bc:0x58be4]
        driver=r'''
#include "infrastructure/internal/internal_hook_adapter.hpp"
#include "entity_remove_hook.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
using namespace isaac::runtime;
std::uintptr_t base{};unsigned installs{};
namespace isaac::runtime {
std::uint32_t LevelCurseFirstRandomInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t LevelCurseEvaluateInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t PickupSelectionInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}

std::uint32_t RoomFixSpawnCtorInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t ClearAwardInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t TrinketFirstRandomInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t TrinketSelectedInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t EntityDestructorRemoveInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
}
namespace isaac::runtime::relay {
InternalHookFailure TryInstallPreinstalledInternalHook(const InternalHookBinding&,const ColdInternalHookSite&){return InternalHookFailure::InvalidPlan;}

InternalHookFailure TryInstallInternalHook(const InternalHookBinding& b,const InternalHookSite& s,std::uintptr_t v){
 assert(ValidInternalBinding(b)&&b.callback==EntityDestructorRemoveInternalCallback);
 assert(b.resumeCount==1&&b.resumes[0]==base+0x58a04);
 assert(b.scratch==InternalScratchPolicy::ProvedDeadX16);
 assert(s.target==base+0x58a00&&s.expected==0x94185d10&&s.veneerKind==InternalVeneerKind::Literal8&&s.literalSlot==base+0x68cd78);
 assert(v==base+0x68cda8);
 auto* n=static_cast<const EntityRemoveNativeBindings*>(b.user);
 assert(!n->remove&&reinterpret_cast<std::uintptr_t>(n->destroyRng)==base+0x44e3bc);
 ++installs;return InternalHookFailure::None;
}}
int main(){
 std::vector<unsigned char> image(0x68d000);base=reinterpret_cast<std::uintptr_t>(image.data());
 unsigned char raw[]={ORIGINAL};std::memcpy(image.data()+0x589bc,raw,sizeof(raw));
 std::memcpy(image.data()+0x44e3bc,kEntityDestructorRngDestroyExpectedBytes.data(),4);
 HookTarget t{};t.base=base;t.codeSize=image.size();t.imageSize=image.size();
 InternalHookAdapter a;
 for(unsigned i=0;i<sizeof(raw);++i){image[0x589bc+i]^=1;assert(!a.Install(HookId::EntityDestructorRemove,t).ok()&&installs==0);image[0x589bc+i]^=1;}
 for(unsigned i=0;i<4;++i){image[0x44e3bc+i]^=1;assert(!a.Install(HookId::EntityDestructorRemove,t).ok()&&installs==0);image[0x44e3bc+i]^=1;}
 auto shortTarget=t;shortTarget.codeSize=0x68cdaf;
 assert(!a.Install(HookId::EntityDestructorRemove,shortTarget).ok()&&installs==0);
 assert(a.Install(HookId::EntityDestructorRemove,t).ok()&&installs==1);
 assert(a.IsInstalled(HookId::EntityDestructorRemove)&&!a.IsInstalled(HookId::RoomClearAward));
 assert(!a.Install(HookId::EntityDestructorRemove,t).ok()&&installs==1);
}
'''.replace('ORIGINAL',','.join(map(str,original)))
        adapter_fixture.InternalHookAdapterTests().compile_run(driver,[CPP])
