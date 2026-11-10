#include "infrastructure/internal/speed_cache_hook_installer.hpp"
#include "cold_callbacks_internal_hook.hpp"
#include "speed_cache_boundary_layout.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
namespace isaac::runtime {
extern "C" {SpeedCacheBoundaryInstallState g_SpeedCacheBoundaryInstallState{};}
bool TryInstallSpeedCacheBoundary(const HookTarget& target) noexcept {
 // Stage109's frozen restart diagnostic owns CF40; never publish both users.
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
 static_cast<void>(target);return false;
#else
 namespace layout=speed_cache_boundary;
 auto& state=g_SpeedCacheBoundaryInstallState;
 if(state.base)return state.base==target.base&&state.installed==1&&state.failure==0;
 if(!target.base||target.buildId!=layout::kBuildId||target.codeSize<layout::kGate+32||
    target.base>UINTPTR_MAX-target.codeSize||
    !engine_memory::EngineMemoryReadable(target.base+0x40,layout::kBuildId.size())||
    !engine_memory::EngineMemoryReadable(target.base+layout::kFunction,layout::kLength)||
    !engine_memory::EngineMemoryReadable(target.base+layout::kGate,32)||
    !layout::ImageMatches(static_cast<const std::uint8_t*>(engine_memory::AsObject(target.base)),target.codeSize)){
  state.failure=static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);return false;
 }
 relay::InternalHookBinding binding{};
 binding.callback=SpeedCacheInternalCallback;
 binding.resumes[0]=target.base+layout::kGate+16;binding.resumeCount=1;
 binding.scratch=relay::InternalScratchPolicy::ProvedDeadX16;
 state.base=target.base;
 const auto failure=relay::TryInstallPreinstalledInternalHook(binding,
     {target.base+layout::kSource,target.base+layout::kGate,layout::kOriginal});
 state.failure=static_cast<std::uint32_t>(failure);
 if(failure!=relay::InternalHookFailure::None)return false;
 state.installed=1;return true;
#endif
}
}
