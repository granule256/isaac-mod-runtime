#include "card_hook.hpp"
#include "card_guards.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include <atomic>
#include <cstring>
namespace isaac::runtime {
namespace {
std::atomic<std::uintptr_t> s_CardBase{};
bool Window(const HookTarget& t,std::uintptr_t offset,std::size_t size) {
    const auto limit=t.imageSize?t.imageSize:t.codeSize;
    return t.base && offset<=limit && size<=limit-offset && t.base<=UINTPTR_MAX-offset-size &&
        engine_memory::EngineMemoryReadable(t.base+offset,size);
}
template<std::size_t N> bool Guard(const HookTarget& t,std::uintptr_t offset,const std::array<std::uint8_t,N>& bytes) {
    return Window(t,offset,N)&&!std::memcmp(engine_memory::AsObject(t.base+offset),bytes.data(),N);
}
}
extern "C" std::uint32_t IsaacModRuntime_CardPointerIntercept(const void* pool,std::uint32_t seed,
    bool playing,bool runes,bool onlyRunes) {
    const auto base=s_CardBase.load(std::memory_order_acquire);
    if(!base)__builtin_trap();
    CardNativeBindings native{};
    native.getCard=engine_call::AsFunction<CardNativeBindings::GetCard>(base+card::kBasicOffset);
    native.construct=engine_call::AsFunction<CardNativeBindings::Construct>(base+card::kCtorOffset);
    native.destroy=engine_call::AsFunction<CardNativeBindings::Destroy>(base+card::kDtorOffset);
    return RunCardIntercept(&native,pool,seed,playing,runes,onlyRunes);
}
CardNativeBindings::GetCard ResolveCardApiEntry(std::uintptr_t moduleBase) noexcept {
    if(!moduleBase || s_CardBase.load(std::memory_order_acquire)!=moduleBase ||
       moduleBase>UINTPTR_MAX-card::kGotOffset-sizeof(std::uintptr_t) ||
       !engine_memory::EngineMemoryReadable(moduleBase+card::kGotOffset,sizeof(std::uintptr_t)))
        return nullptr;
    const auto target=__atomic_load_n(static_cast<const std::uintptr_t*>(
        engine_memory::AsObject(moduleBase+card::kGotOffset)),__ATOMIC_ACQUIRE);
    if(target!=engine_call::AddressOfFunction(&IsaacModRuntime_CardPointerIntercept))return nullptr;
    return &IsaacModRuntime_CardPointerIntercept;
}
Status InstallCardPointerHook(const HookTarget& t) noexcept {
    if(t.buildId!=kTargetBuildId || !Guard(t,card::kBasicOffset,card::kBasicBytes) ||
        !Guard(t,card::kPltOffset,card::kPltBytes) || !Guard(t,card::kCtorOffset,card::kCtorBytes) ||
        !Guard(t,card::kDtorOffset,card::kDtorBytes) || !Guard(t,card::kShiftsOffset,card::kShiftsBytes) ||
        !Window(t,card::kGotOffset,8) || ((t.base+card::kGotOffset)&7))return Status{StatusCode::Rejected};
    const auto address=t.base+card::kGotOffset;
    auto expected=__atomic_load_n(static_cast<const std::uintptr_t*>(engine_memory::AsObject(address)),__ATOMIC_ACQUIRE);
    if(expected!=t.base+card::kBasicOffset&&expected!=t.base+kPltResolverOffset)return Status{StatusCode::Rejected};
    const auto previous=s_CardBase.load(std::memory_order_acquire);
    if(previous&&previous!=t.base)return Status{StatusCode::Rejected};
    // 原入口在release CAS前发布；拦截只替换一个64位指针槽。
    s_CardBase.store(t.base,std::memory_order_release);
    const auto replacement=engine_call::AddressOfFunction(&IsaacModRuntime_CardPointerIntercept);
    bool changed=false;
    if(engine_memory::EngineMemoryWritable(address,8))
        changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(address)),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
    else {
        exl::util::RwPages pages(address,8);
        changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(pages.GetRw())),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);pages.Flush();
    }
    return changed?Status::Ok():Status{StatusCode::Rejected};
}
}
