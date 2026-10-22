#include "interfaces/lua/rplus_options.hpp"
#include "lua_runtime.hpp"
#include <cstdio>
#include "application/shader/shader_pipeline.hpp"
#include "interfaces/lua/rplus_content_names.hpp"
#include "mod_unload_hook.hpp"
#include "mod_unload_guards.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include <atomic>
#include <cstring>
namespace LuaRuntime {
bool IsOnGameThread() noexcept;
bool UnloadManifestMods() noexcept;
}
namespace isaac::runtime {
namespace {
constexpr std::uintptr_t kSlot=0xAA4E80;
std::atomic<std::uintptr_t> s_Original{},s_Base{};
bool s_Unloading{}; // 仅已确认游戏线程读写；其它线程不读取它。
bool Window(const HookTarget& target,std::uintptr_t offset,std::size_t length) {
    const auto limit=target.imageSize?target.imageSize:target.codeSize;
    return target.base && offset<=limit && length<=limit-offset &&
        target.base<=UINTPTR_MAX-offset-length && engine_memory::EngineMemoryReadable(target.base+offset,length);
}
}
extern "C" void IsaacModRuntime_ModUnloadIntercept(void* self) {
    const auto original=s_Original.load(std::memory_order_acquire);
    if(!original)__builtin_trap();
    const bool managed=LuaRuntime::IsOnGameThread();
    if(managed && s_Unloading)return; // 73里递归Reset不能释放正在卸载的同一资源两遍。
    if(managed){s_Unloading=true;static_cast<void>(LuaRuntime::UnloadManifestMods());}
    // 73观察者仍可查询尚未释放的真实配置；观察结束后再清缓存。
    if(managed){
        const auto options=FlushRuntimeOptions();
        if(!options.ok()&&options.code()!=StatusCode::Unsupported){
            char message[96];const auto n=std::snprintf(message,sizeof(message),"runtime options unload save failed: %u",static_cast<unsigned>(options.code()));
            if(n>0)LuaRuntime::RecordLuaErrorText(message,static_cast<std::size_t>(n));
        }
    }
    UnloadShaderPrograms();
    ClearRuntimeContentNames();
    engine_call::AsFunction<void(*)(void*)>(original)(self);
    if(managed)s_Unloading=false;
}
Status InstallModUnloadPointerHook(const HookTarget& target) noexcept {
    if(target.buildId!=kTargetBuildId || !Window(target,mod_unload::kOffset,mod_unload::kFunctionBytes.size()) ||
        !Window(target,mod_unload::kPlt,16) || !Window(target,kSlot,8) || ((target.base+kSlot)&7))return Status{StatusCode::Rejected};
    if(std::memcmp(engine_memory::AsObject(target.base+mod_unload::kOffset),mod_unload::kFunctionBytes.data(),mod_unload::kFunctionBytes.size()) ||
       std::memcmp(engine_memory::AsObject(target.base+mod_unload::kPlt),mod_unload::kPltBytes.data(),16))return Status{StatusCode::Rejected};
    auto* slot=static_cast<std::uintptr_t*>(engine_memory::AsObject(target.base+kSlot));
    auto expected=__atomic_load_n(slot,__ATOMIC_ACQUIRE);
    if(expected!=target.base+mod_unload::kOffset && expected!=target.base+kPltResolverOffset)return Status{StatusCode::Rejected};
    const auto previous=s_Base.load(std::memory_order_acquire);
    if(previous && previous!=target.base)return Status{StatusCode::Rejected};
    if(!previous){s_Original.store(target.base+mod_unload::kOffset,std::memory_order_release);s_Base.store(target.base,std::memory_order_release);}
    const auto callback=engine_call::AddressOfFunction(&IsaacModRuntime_ModUnloadIntercept);
    exl::util::RwPages page(target.base+kSlot,8);
    auto* writable=static_cast<std::uintptr_t*>(engine_memory::AsObject(page.GetRw()));
    if(!__atomic_compare_exchange_n(writable,&expected,callback,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED))return Status{StatusCode::Rejected};
    page.Flush();
    if(__atomic_load_n(slot,__ATOMIC_ACQUIRE)!=callback) {
        auto ours=callback;__atomic_compare_exchange_n(writable,&ours,expected,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);page.Flush();
        return Status{StatusCode::Rejected};
    }
    return Status::Ok();
}
}
