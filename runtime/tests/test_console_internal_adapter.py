"""22实际安装适配器：完整控制台函数、实际Print入口和两条冷分支绑定。"""
import unittest,struct
from pathlib import Path
from . import test_internal_hook_adapter as helper
from tools import cold_static_callbacks as c
ROOT=helper.ROOT
class ConsoleInternalAdapterTests(unittest.TestCase):
 def test_full_function_guard_and_both_native_continuations(self):
  nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  pieces=[(0x3d740,nro[0x3d740:0x437b0]),(0x3bfb4,nro[0x3bfb4:0x3bfc4])]
  for src,gate,word in c.CONSOLE_BRANCH_SITES:
   pieces.extend([(src,struct.pack('<I',c.branch(src,gate))),(gate,c.console_branch_gate(src,gate,word))])
  assignments='\n'.join('copy('+hex(o)+',{'+','.join(map(str,raw))+'});'for o,raw in pieces)
  driver=r'''
#include "infrastructure/internal/internal_hook_adapter.hpp"
#include "console_callback_hook.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
using namespace isaac::runtime;
unsigned calls{};std::uintptr_t base{};
namespace isaac::runtime {
std::uint32_t ConsoleUnknownInternalCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
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
InternalHookFailure TryInstallInternalHook(const InternalHookBinding&,const InternalHookSite&,std::uintptr_t){return InternalHookFailure::InvalidPlan;}
InternalHookFailure TryInstallConsoleConditionalHook(const InternalHookBinding& b,const ColdInternalHookSite& s){
 auto* n=static_cast<const ConsoleUnknownBindings*>(b.user);assert(ValidInternalBinding(b)&&b.resumeCount==2&&b.callback==ConsoleUnknownInternalCallback);
 assert(b.resumes[0]==base+0x41d64&&b.resumes[1]==s.source+4);
 assert(s.source==base+(n->compareResult?0x41898:0x41878)&&s.gate==base+(n->compareResult?0x68cd80:0x68cd40));
 assert(reinterpret_cast<std::uintptr_t>(n->print)==base+0x3bfb4);++calls;return InternalHookFailure::None;
}}
int main(){std::vector<unsigned char> image(0x68d000);base=reinterpret_cast<std::uintptr_t>(image.data());
 auto copy=[&](unsigned off,std::initializer_list<unsigned char>b){memcpy(image.data()+off,b.begin(),b.size());};ASSIGNMENTS
 HookTarget t{};t.base=base;t.codeSize=image.size();t.imageSize=image.size();t.buildId=kTargetBuildId;InternalHookAdapter a;
 for(auto off:{0x3d740,0x41874,0x41878,0x41898,0x41d64,0x437ac,0x3bfb4}){image[off]^=1;assert(!a.Install(HookId::ConsoleUnknownLength,t).ok()&&calls==0);image[off]^=1;}
 assert(a.Install(HookId::ConsoleUnknownLength,t).ok()&&calls==1);assert(a.Install(HookId::ConsoleUnknownCompare,t).ok()&&calls==2);
 assert(a.IsInstalled(HookId::ConsoleUnknownLength)&&a.IsInstalled(HookId::ConsoleUnknownCompare));assert(!a.Install(HookId::ConsoleUnknownCompare,t).ok()&&calls==2);
}
'''.replace('ASSIGNMENTS',assignments)
  helper.InternalHookAdapterTests().compile_run(driver,[helper.CPP])
