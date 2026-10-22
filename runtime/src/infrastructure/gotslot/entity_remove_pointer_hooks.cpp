#include "entity_remove_hook.hpp"
#include "entity_remove_slots.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include <atomic>
#include <cstring>

namespace isaac::runtime {
namespace {
std::atomic<std::uintptr_t> s_OriginalRemove{};
std::atomic<std::uintptr_t> s_RemoveModuleBase{};
std::uintptr_t LoadPointer(const void*,std::uintptr_t address) {
    return __atomic_load_n(static_cast<const std::uintptr_t*>(engine_memory::AsObject(address)),__ATOMIC_ACQUIRE);
}
bool ComparePointer(void*,std::uintptr_t address,std::uintptr_t expected,std::uintptr_t replacement) {
    if (engine_memory::EngineMemoryWritable(address,sizeof(std::uintptr_t))) {
        return __atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(address)),
            &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
    }
    exl::util::RwPages pages(address,sizeof(std::uintptr_t));
    const bool changed=__atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(pages.GetRw())),
        &expected,replacement,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
    pages.Flush();
    return changed;
}
bool Window(const HookTarget& target,std::uintptr_t offset,std::size_t size) {
    const auto limit=target.imageSize!=0?target.imageSize:target.codeSize;
    return target.base!=0 && offset<=limit && size<=limit-offset &&
        target.base<=UINTPTR_MAX-offset-size && engine_memory::EngineMemoryReadable(target.base+offset,size);
}
}
extern "C" void IsaacModRuntime_EntityRemovePointerIntercept(void* entity) {
    const auto original=s_OriginalRemove.load(std::memory_order_acquire);
    if (original==0) __builtin_trap();
    EntityRemoveNativeBindings native{};
    native.remove=engine_call::AsFunction<EntityRemoveNativeBindings::BaseRemove>(original);
    RunEntityRemoveIntercept(&native,entity);
}
Status InstallEntityRemovePointerHooks(const HookTarget& target) noexcept {
    if (target.buildId!=kTargetBuildId || !Window(target,kEntityRemoveOffset,28))
        return Status{StatusCode::Rejected};
    constexpr std::uint8_t original[28]={
        0x08,0x0C,0x47,0x39,0x1F,0x08,0x07,0x39,0x48,0,0,0x34,0xC0,3,0x5F,0xD6,
        0x28,0,0x80,0x52,0x08,0x0C,0x07,0x39,0xC0,3,0x5F,0xD6,
    };
    if (std::memcmp(engine_memory::AsObject(target.base+kEntityRemoveOffset),original,sizeof(original)))
        return Status{StatusCode::Rejected};
    std::array<std::uintptr_t,11> sites{},expected{};
    for (std::size_t i=0;i<sites.size();++i) {
        const auto offset=kEntityRemovePointerOffsets[i];
        if (!Window(target,offset,sizeof(std::uintptr_t)) || ((target.base+offset)&7)!=0)
            return Status{StatusCode::Rejected};
        sites[i]=target.base+offset;
        expected[i]=LoadPointer(nullptr,sites[i]);
        if (expected[i]!=target.base+kEntityRemoveOffset &&
            !(i==sites.size()-1 && expected[i]==target.base+kPltResolverOffset))
            return Status{StatusCode::Rejected};
    }
    const auto previous=s_RemoveModuleBase.load(std::memory_order_acquire);
    if (previous!=0 && previous!=target.base) return Status{StatusCode::Rejected};
    if (previous==0) {
        // 任何函数指针可被另一个线程读到之前，原函数已不可变发布。
        s_OriginalRemove.store(target.base+kEntityRemoveOffset,std::memory_order_release);
        s_RemoveModuleBase.store(target.base,std::memory_order_release);
    }
    const EntityPointerIo io{nullptr,LoadPointer,ComparePointer};
    const auto failure=InstallEntityPointerPlan(io,sites,expected,
        engine_call::AddressOfFunction(&IsaacModRuntime_EntityRemovePointerIntercept));
    return failure==EntityPointerFailure::None?Status::Ok():Status{StatusCode::Rejected};
}
}
