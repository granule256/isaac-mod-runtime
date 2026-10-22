#pragma once
#include "relay/internal_hook.hpp"
namespace isaac::runtime {
using MainLoadModuleFn=std::uint32_t(*)(void*,const void*,void*,std::size_t,int);
using PrepareLoadedModuleFn=bool(*)()noexcept;
struct MainModuleLoadBindings {
    MainLoadModuleFn originalPlt{};
    PrepareLoadedModuleFn prepare{};
    std::uintptr_t resume{};
};
struct MainModuleLoadObserverState {
    std::uint32_t installAttempted{},installed{},installFailure{},calls{};
    std::uint32_t targetCalls{},loadFailures{},lastLoadResult{},prepared{};
    std::uint64_t installedTicks{},firstCallbackTicks{},preparedTicks{};
    std::uintptr_t mainBase{},originalPlt{};
};
extern MainModuleLoadObserverState g_MainModuleLoadObserverState;
bool InstallMainModuleLoadObserver(std::uintptr_t mainBase,std::size_t textBytes,
                                  PrepareLoadedModuleFn prepare)noexcept;
bool MainModuleLoadPreparationReady()noexcept;
std::uint32_t MainModuleLoadInternalCallback(relay::InternalHookContext&,const void*)noexcept;
}
