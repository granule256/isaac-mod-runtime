#include "infrastructure/internal/use_item_hook_installer.hpp"
#include "use_item_internal_hook.hpp"
#include "use_item_boundary_layout.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
namespace isaac::runtime {
extern "C" {UseItemBoundaryInstallState g_UseItemBoundaryInstallState{};}
bool TryInstallUseItemNativeBoundaries(const HookTarget& target) noexcept{
 auto& state=g_UseItemBoundaryInstallState;
 if(state.base)return state.base==target.base&&state.installed==7&&state.failure==0;
 if(!target.base||target.buildId!=use_item_boundary::kBuildId||target.codeSize<0x68CF00||
    target.base>UINTPTR_MAX-target.codeSize||
    !engine_memory::EngineMemoryReadable(target.base+use_item_boundary::kFunction,use_item_boundary::kLength)||
    !engine_memory::EngineMemoryReadable(target.base+0x68CE00,0x20)||
    !engine_memory::EngineMemoryReadable(target.base+0x672020,16)||
    !engine_memory::EngineMemoryReadable(target.base+0x678870,16)||
    !engine_memory::EngineMemoryReadable(target.base+0x68CE60,0xA0)||
    !use_item_boundary::ImageMatches(static_cast<const std::uint8_t*>(engine_memory::AsObject(target.base)),target.codeSize)){
  state.failure=static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);return false;
 }
 // 所有原生代码先完整验证，再发布任一槽。发布后的不可变binding与gateway保留到进程退出。
 static constexpr UseItemNativeBoundaryBinding views[]={{false,false},{false,false},{false,true},{true,false},{true,false}};
 state.base=target.base;
 for(std::size_t i=0;i<use_item_boundary::kSites.size();++i){
  const auto& site=use_item_boundary::kSites[i];relay::InternalHookBinding binding{};
  binding.callback=UseItemNativeBoundaryCallback;binding.user=&views[i];binding.resumeCount=1;
  binding.resumes[0]=target.base+site.gate+16;binding.scratch=relay::InternalScratchPolicy::ProvedDeadX16;
  const auto failure=relay::TryInstallPreinstalledInternalHook(binding,
    {target.base+site.source,target.base+site.gate,site.original});
  if(failure!=relay::InternalHookFailure::None){state.failure=static_cast<std::uint32_t>(failure);return false;}
  ++state.installed;
 }
 static UseItemAnimationEventBinding events[2]{};
 for(std::size_t i=0;i<use_item_boundary::kAnimationSites.size();++i){
  const auto& site=use_item_boundary::kAnimationSites[i];
  events[i]={target.base+site.plt,target.base+site.source+4,
    i==0?UseItemAnimationEvent::TammyLaser:UseItemAnimationEvent::FlipReplace};
  relay::InternalHookBinding binding{};
  binding.callback=UseItemAnimationEventCallback;binding.user=&events[i];binding.resumeCount=1;
  binding.resumes[0]=events[i].resume;binding.scratch=relay::InternalScratchPolicy::ProvedDeadX16;
  const auto failure=relay::TryInstallInternalHook(binding,
    {target.base+site.source,site.original},target.base+site.veneer);
  if(failure!=relay::InternalHookFailure::None){state.failure=static_cast<std::uint32_t>(failure);return false;}
  ++state.installed;
 }
 state.failure=0;return true;
}
}
