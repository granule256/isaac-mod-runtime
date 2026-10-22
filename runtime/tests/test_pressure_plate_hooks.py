"""原生压力板析构完整指纹/两个续接点，及真实清理先于RNG析构的调用顺序。"""
import unittest
from pathlib import Path
from . import test_internal_hook_adapter as helper
ROOT=helper.ROOT;CPP=helper.CPP
class PressurePlateHookTests(unittest.TestCase):
 def test_native_destructors_guard_and_branch_binding(self):
  driver=r'''
#include "infrastructure/internal/internal_hook_adapter.hpp"
#include "pressure_plate_animation_hook.hpp"
#include "pressure_plate_internal_guards.hpp"
#include <cassert>
#include <vector>
#include <cstring>
using namespace isaac::runtime;
std::uintptr_t base{};unsigned installs{},mask{};
namespace isaac::runtime {
#define STUB(N) std::uint32_t N(relay::InternalHookContext&,const void*)noexcept{return 0;}
STUB(LevelCurseFirstRandomInternalCallback) STUB(LevelCurseEvaluateInternalCallback)
STUB(PickupSelectionInternalCallback) STUB(EntityDestructorRemoveInternalCallback)
STUB(ClearAwardInternalCallback) STUB(RoomFixSpawnCtorInternalCallback)
STUB(TrinketFirstRandomInternalCallback) STUB(TrinketSelectedInternalCallback)
STUB(PressurePlateDestructorInternalCallback)
void MarkPressurePlateDestructorHookInstalled(bool deleting)noexcept{mask|=deleting?2:1;}
}
namespace isaac::runtime::relay {
InternalHookFailure TryInstallPreinstalledInternalHook(const InternalHookBinding&,const ColdInternalHookSite&){return InternalHookFailure::InvalidPlan;}
InternalHookFailure TryInstallInternalHook(const InternalHookBinding&b,const InternalHookSite&s,std::uintptr_t v){
 bool deleting=s.target==base+0x38f2d4;
 assert(s.target==base+(deleting?0x38f2d4:0x38f294));assert(s.expected==(deleting?0x940b82dbU:0x940b82ebU));
 assert(s.veneerKind==InternalVeneerKind::Absolute16&&v==base+(deleting?0x68cd30:0x68cd20));
 assert(ValidInternalBinding(b)&&b.callback==PressurePlateDestructorInternalCallback&&b.resumeCount==1&&b.resumes[0]==s.target+4);
 auto*n=static_cast<const PressurePlateNativeBindings*>(b.user);assert(reinterpret_cast<std::uintptr_t>(n->destroyRng)==base+0x66fe40);
 ++installs;return InternalHookFailure::None;
}}
int main(){std::vector<unsigned char> image(0x68d000);base=reinterpret_cast<std::uintptr_t>(image.data());
 std::memcpy(image.data()+0x38f270,pressure_plate::kDestructorOriginal.data(),pressure_plate::kDestructorOriginal.size());
 std::memcpy(image.data()+0x38f2b0,pressure_plate::kDeletingOriginal.data(),pressure_plate::kDeletingOriginal.size());
 std::memcpy(image.data()+0x66fe40,pressure_plate::kRngDestroyPlt.data(),16);
 HookTarget t{};t.base=base;t.codeSize=image.size();t.imageSize=image.size();
 for(auto id:{HookId::PressurePlateDestructor,HookId::PressurePlateDeletingDestructor}){
  auto offset=id==HookId::PressurePlateDestructor?0x38f270:0x38f2b0;
  auto size=id==HookId::PressurePlateDestructor?pressure_plate::kDestructorOriginal.size():pressure_plate::kDeletingOriginal.size();
  for(unsigned i=0;i<size;++i){image[offset+i]^=1;InternalHookAdapter a;auto prior=installs;assert(!a.Install(id,t).ok()&&installs==prior);image[offset+i]^=1;}
 }
 InternalHookAdapter a;assert(a.Install(HookId::PressurePlateDestructor,t).ok()&&installs==1&&mask==1);
 assert(a.Install(HookId::PressurePlateDeletingDestructor,t).ok()&&installs==2&&mask==3);
 assert(!a.Install(HookId::PressurePlateDestructor,t).ok());
}
'''
  helper.InternalHookAdapterTests().compile_run(driver,[CPP])
 def test_real_callback_replays_rng_destruction_after_pin_cleanup(self):
  driver=r'''
#include "pressure_plate_animation_hook.hpp"
#include "infrastructure/relay/entry_relay_binding.hpp"
#include <cassert>
unsigned sequence{};
namespace LuaRuntime {void DispatchPressurePlateAnimationPinEvent(std::uintptr_t grid,bool before)noexcept{assert(sequence==0&&grid==0x12340&&before);++sequence;}}
namespace isaac::runtime {std::uintptr_t EntryRelayFallbackEntry(HookId)noexcept{return 0;}}
void Destroy(std::uintptr_t rng){assert(sequence==1&&rng==0x12640);++sequence;}
int main(){isaac::runtime::relay::InternalHookContext ctx{};ctx.x[19]=0x12340;ctx.x[0]=0x12640;auto prior=ctx;
 isaac::runtime::PressurePlateNativeBindings b{Destroy};assert(isaac::runtime::PressurePlateDestructorInternalCallback(ctx,&b)==0&&sequence==2);
 assert(ctx.x[19]==prior.x[19]&&ctx.x[0]==prior.x[0]);
 assert(!isaac::runtime::PressurePlateDestructorHooksReady());isaac::runtime::MarkPressurePlateDestructorHookInstalled(false);assert(!isaac::runtime::PressurePlateDestructorHooksReady());isaac::runtime::MarkPressurePlateDestructorHookInstalled(true);assert(isaac::runtime::PressurePlateDestructorHooksReady());
}
'''
  helper.InternalHookAdapterTests().compile_run(driver,[ROOT/'runtime/source/pressure_plate_animation_hook.cpp'])
