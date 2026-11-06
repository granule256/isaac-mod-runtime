#include "mod_itempool_hook.hpp"
#include "mod_itempool_guards.hpp"
#include "mod_menu_native.hpp"
#include "runtime_constants.hpp"
#include "application/mod/mod_itempool_loading.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include <atomic>
#include <cstring>

namespace isaac::runtime {
namespace {
std::atomic<std::uintptr_t> s_Base{};
bool Window(const HookTarget& t,std::uintptr_t offset,std::size_t size) {
    const auto limit=t.imageSize?t.imageSize:t.codeSize;
    return t.base && offset<=limit && size<=limit-offset &&
        t.base<=UINTPTR_MAX-offset-size &&
        engine_memory::EngineMemoryReadable(t.base+offset,size);
}
template<std::size_t N>
bool Guard(const HookTarget& t,std::uintptr_t offset,const std::array<std::uint8_t,N>& bytes) {
    return Window(t,offset,N) &&
        !std::memcmp(engine_memory::AsObject(t.base+offset),bytes.data(),N);
}
}

extern "C" void IsaacModRuntime_ModItemPoolPointerIntercept(void* pool,const char* path,bool append) {
    const auto base=s_Base.load(std::memory_order_acquire);
    if(!base)__builtin_trap();
    const ModItemPoolBindings native{
        engine_call::AsFunction<ModItemPoolBindings::Load>(base+mod_itempools::kLoadOffset),
        &modmenu::LoadEngineModItemPools};
    LoadItemPoolsWithMods(native,pool,path,append);
}

Status InstallModItemPoolPointerHook(const HookTarget& t) noexcept {
    if(t.buildId!=kTargetBuildId ||
       !Guard(t,mod_itempools::kLoadOffset,mod_itempools::kLoadBytes) ||
       !Guard(t,mod_itempools::kUpdateOffset,mod_itempools::kUpdateBytes) ||
       !Guard(t,mod_itempools::kPltOffset,mod_itempools::kPltBytes) ||
       !Window(t,mod_itempools::kGotOffset,8) ||
       ((t.base+mod_itempools::kGotOffset)&7))return Status{StatusCode::Rejected};
    const auto address=t.base+mod_itempools::kGotOffset;
    auto* slot=static_cast<std::uintptr_t*>(engine_memory::AsObject(address));
    auto expected=__atomic_load_n(slot,__ATOMIC_ACQUIRE);
    if(expected!=t.base+mod_itempools::kLoadOffset &&
       expected!=t.base+kPltResolverOffset)return Status{StatusCode::Rejected};
    const auto previous=s_Base.load(std::memory_order_acquire);
    if(previous && previous!=t.base)return Status{StatusCode::Rejected};
    s_Base.store(t.base,std::memory_order_release);
    const auto replacement=engine_call::AddressOfFunction(&IsaacModRuntime_ModItemPoolPointerIntercept);
    bool changed=false;
    if(engine_memory::EngineMemoryWritable(address,8))
        changed=__atomic_compare_exchange_n(slot,&expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
    else {
        exl::util::RwPages pages(address,8);
        changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(pages.GetRw())),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
        pages.Flush();
    }
    return changed?Status::Ok():Status{StatusCode::Rejected};
}
}
