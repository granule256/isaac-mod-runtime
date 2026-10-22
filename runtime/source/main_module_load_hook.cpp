#include "main_module_load_hook.hpp"
#include "main_module_load_guards.hpp"
#include "runtime_constants.hpp"
#include "interfaces/lua/runtime_perf.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <atomic>
#include <cstring>
namespace isaac::runtime {
MainModuleLoadObserverState g_MainModuleLoadObserverState{};
namespace {
std::atomic<std::uint32_t> g_PreparationReady{};
MainModuleLoadBindings g_Bindings{};
bool IsTargetImage(std::uintptr_t image)noexcept {
    std::uint32_t magic{};
    std::array<std::uint8_t,32> id{};
    if(!engine_memory::ReadField(image,0x10,&magic,engine_memory::EngineMemoryReadable)||magic!=0x304f524e)
        return false;
    return engine_memory::ReadField(image,0x40,&id,engine_memory::EngineMemoryReadable)&&id==kTargetBuildId;
}
bool Contains(std::uintptr_t base,std::size_t bytes,std::uintptr_t offset,std::size_t n)noexcept {
    return base&&offset<=bytes&&n<=bytes-offset&&base<=UINTPTR_MAX-bytes;
}
}
bool MainModuleLoadPreparationReady()noexcept {
    return g_PreparationReady.load(std::memory_order_acquire)!=0;
}
std::uint32_t MainModuleLoadInternalCallback(relay::InternalHookContext& context,const void* opaque)noexcept {
    const auto& native=*static_cast<const MainModuleLoadBindings*>(opaque);
    auto& state=g_MainModuleLoadObserverState;
    ++state.calls;
    if(!state.firstCallbackTicks)state.firstCallbackTicks=RuntimePerfTick();
    // 原始文件缓冲可能在加载后改变映射；只在原调用前核NRO头和固定BuildID。
    const bool target=IsTargetImage(context.x[1]);
    const auto result=native.originalPlt(engine_memory::AsObject(context.x[0]),
        engine_memory::AsObject(context.x[1]),engine_memory::AsObject(context.x[2]),
        static_cast<std::size_t>(context.x[3]),static_cast<int>(context.x[4]));
    context.x[0]=result;
    context.x[30]=native.resume; // 复现被替换BL本应写入的LR，结果随后由Main原生检查消费。
    state.lastLoadResult=result;
    if(result!=0){++state.loadFailures;return 0;}
    if(!target)return 0;
    ++state.targetCalls;
    if(!MainModuleLoadPreparationReady()&&native.prepare&&native.prepare()){
        state.prepared=1;state.preparedTicks=RuntimePerfTick();
        g_PreparationReady.store(1,std::memory_order_release);
    }
    return 0;
}
bool InstallMainModuleLoadObserver(std::uintptr_t mainBase,std::size_t textBytes,
                                  PrepareLoadedModuleFn prepare)noexcept {
    using namespace main_module_load;
    auto& state=g_MainModuleLoadObserverState;
    if(state.installed)return state.mainBase==mainBase;
    state.installAttempted=1;
    if(!prepare||!Contains(mainBase,textBytes,kCallOffset-16,kCallGuard.size())||
       !Contains(mainBase,textBytes,kPltOffset,kPltGuard.size())||
       !Contains(mainBase,textBytes,kVeneerOffset,16)){
        state.installFailure=static_cast<std::uint32_t>(relay::InternalHookFailure::InvalidPlan);return false;
    }
    if(!engine_memory::EngineMemoryReadable(mainBase+kCallOffset-16,kCallGuard.size())||
       !engine_memory::EngineMemoryReadable(mainBase+kPltOffset,kPltGuard.size())||
       std::memcmp(engine_memory::AsObject(mainBase+kCallOffset-16),kCallGuard.data(),kCallGuard.size())||
       std::memcmp(engine_memory::AsObject(mainBase+kPltOffset),kPltGuard.data(),kPltGuard.size())){
        state.installFailure=static_cast<std::uint32_t>(relay::InternalHookFailure::GuardMismatch);return false;
    }
    // 不覆写Main的GOT；PLT仍实时调用SaltyNX/SDK当前的真实加载器链。
    g_Bindings={engine_call::AsFunction<MainLoadModuleFn>(mainBase+kPltOffset),prepare,mainBase+kCallOffset+4};
    relay::InternalHookBinding binding{};
    binding.callback=MainModuleLoadInternalCallback;binding.user=&g_Bindings;
    binding.resumeCount=1;binding.resumes[0]=g_Bindings.resume;
    binding.scratch=relay::InternalScratchPolicy::ProvedDeadX16;
    const relay::InternalHookSite site{mainBase+kCallOffset,kExpectedBl};
    const auto failure=relay::TryInstallInternalHook(binding,site,mainBase+kVeneerOffset);
    state.installFailure=static_cast<std::uint32_t>(failure);
    if(failure!=relay::InternalHookFailure::None)return false;
    state.mainBase=mainBase;state.originalPlt=mainBase+kPltOffset;
    state.installedTicks=RuntimePerfTick();state.installed=1;return true;
}
}
