#include "relay/internal_hook.hpp"
#include "lib/util/sys/jit.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <atomic>
#include <cstring>
#include <span>

extern "C" void isaac_internal_hook_context();

namespace isaac::runtime::relay {
namespace {
// 每个gateway独占页首，让8B ADRP+BR无需第三条ADD；16B旧近桩仍按默认形态编码。
JIT_CREATE(InternalHookArena, 0x10000);
constexpr std::size_t kInternalCapacity = 16;
constexpr std::size_t kGatewayStride = 0x1000;
InternalHookBinding s_Bindings[kInternalCapacity]{};
std::size_t s_Next{};
bool s_Ready{}; // 安装器只在安装期单线程使用，回调不读这些变量。
}
InternalHookFailure TryInstallInternalHook(const InternalHookBinding& binding,
    const InternalHookSite& site, std::uintptr_t veneer) {
    using Failure = InternalHookFailure;
    std::uint32_t branch{};
    if (site.veneerKind != InternalVeneerKind::Absolute16 &&
        site.veneerKind != InternalVeneerKind::Page8 &&
        site.veneerKind != InternalVeneerKind::Literal8) return Failure::InvalidPlan;
    const bool literal=site.veneerKind==InternalVeneerKind::Literal8;
    const std::size_t nearBytes = site.veneerKind == InternalVeneerKind::Absolute16 ? 16 : 8;
    if (!ValidInternalBinding(binding) || site.target > UINTPTR_MAX-4 || veneer > UINTPTR_MAX-nearBytes ||
        site.target % 0x1000 + 4 > 0x1000 ||
        veneer % 0x1000 + nearBytes > 0x1000 || !BuildInternalBranch(&branch,site.target,veneer) ||
        (veneer < site.target+4 && site.target < veneer+nearBytes)) return Failure::InvalidPlan;
    if (!SafeInternalBranchSource(site.expected)) return Failure::UnsafeInstruction;
    if(literal && ((site.literalSlot&7) || site.literalSlot>UINTPTR_MAX-8 ||
       (site.literalSlot<site.target+4 && site.target<site.literalSlot+8) ||
       !engine_memory::EngineMemoryReadable(site.literalSlot,8)))return Failure::InvalidPlan;
    std::uint32_t current{};
    std::memcpy(&current,engine_memory::AsObject(site.target),4);
    if (current != site.expected) return Failure::GuardMismatch;
    const std::uint8_t zeros[16]{};
    if (std::memcmp(engine_memory::AsObject(veneer),zeros,nearBytes) != 0) return Failure::VeneerNotEmpty;
    if(literal && std::memcmp(engine_memory::AsObject(site.literalSlot),zeros,8))
        return Failure::VeneerNotEmpty;
    if (s_Next >= kInternalCapacity) return Failure::ArenaExhausted;
    if (!s_Ready) {
        InternalHookArena.Initialize(std::span {impl::InternalHookArena::s_Area});
        s_Ready = true;
    }
    const auto index = s_Next;
    const auto gateway = InternalHookArena.GetRo() + index*kGatewayStride;
    std::uint8_t nearImage[16]{};
    if(literal) {
        if(!BuildInternalLiteralVeneer(nearImage,veneer,site.literalSlot))return Failure::InvalidPlan;
    } else if (site.veneerKind == InternalVeneerKind::Page8) {
        if (!BuildInternalPageVeneer(nearImage,veneer,gateway)) return Failure::InvalidPlan;
    } else {
        BuildInternalVeneer(nearImage,gateway);
    }
    ++s_Next;
    s_Bindings[index] = binding;
    std::uint8_t image[kInternalGatewayBytes];
    BuildInternalGateway(image,engine_memory::AddressOf(&s_Bindings[index]),
        engine_call::AddressOfFunction(&isaac_internal_hook_context));
    std::memcpy(engine_memory::AsObject(InternalHookArena.GetRw()+index*kGatewayStride),image,sizeof(image));
    InternalHookArena.Flush();
    if (std::memcmp(engine_memory::AsObject(gateway),image,sizeof(image)) != 0)
        return Failure::WriteVerifyFailed;
    if(literal) {
        exl::util::RwPages slotPages(site.literalSlot,8);
        auto* slot=static_cast<std::uintptr_t*>(engine_memory::AsObject(slotPages.GetRw()));
        std::uintptr_t empty{};
        if(!__atomic_compare_exchange_n(slot,&empty,gateway,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED))
            return Failure::VeneerNotEmpty;
        slotPages.Flush();
        if(std::memcmp(engine_memory::AsObject(site.literalSlot),&gateway,8))
            return Failure::WriteVerifyFailed;
    }
    exl::util::RwPages nearPages(veneer,nearBytes);
    // RW映射建立后再核完整空区；既有IPS/其它模块的字节绝不覆盖。
    if (std::memcmp(engine_memory::AsObject(veneer),zeros,nearBytes) != 0) return Failure::VeneerNotEmpty;
    std::memcpy(engine_memory::AsObject(nearPages.GetRw()),nearImage,nearBytes);
    nearPages.Flush();
    if (std::memcmp(engine_memory::AsObject(veneer),nearImage,nearBytes) != 0)
        return Failure::WriteVerifyFailed;
    std::atomic_thread_fence(std::memory_order_release);
    exl::util::RwPages entryPages(site.target,4);
    auto* word = static_cast<std::uint32_t*>(engine_memory::AsObject(entryPages.GetRw()));
    std::uint32_t expected = site.expected;
    // 对齐32位CAS，真实写入是单条32位原子store；不是memcpy或逐字节改指令。
    if (!__atomic_compare_exchange_n(word,&expected,branch,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED))
        return Failure::GuardMismatch;
    entryPages.Flush();
#if defined(__aarch64__)
    asm volatile("dsb sy\n\tisb" ::: "memory");
#endif
    std::memcpy(&current,engine_memory::AsObject(site.target),4);
    if (current != branch) {
        expected = branch;
        // 仅允许将自己刚写的B恢复为原BL/B；不覆盖陌生并发改写。已发布近桩不清零。
        const bool restored = __atomic_compare_exchange_n(word,&expected,site.expected,false,
            __ATOMIC_RELEASE,__ATOMIC_RELAXED);
        entryPages.Flush();
#if defined(__aarch64__)
        asm volatile("dsb sy\n\tisb" ::: "memory");
#endif
        std::memcpy(&current,engine_memory::AsObject(site.target),4);
        return restored && current == site.expected ? Failure::WriteVerifyFailed : Failure::RollbackFailed;
    }
    return Failure::None;
}
namespace {
InternalHookFailure PublishColdBinding(const InternalHookBinding& binding,std::uintptr_t slot) {
    using Failure=InternalHookFailure;
    std::uintptr_t current{};
    if (s_Next>=kInternalCapacity) return Failure::ArenaExhausted;
    if (!s_Ready) {InternalHookArena.Initialize(std::span{impl::InternalHookArena::s_Area});s_Ready=true;}
    const auto index=s_Next++;
    const auto gateway=InternalHookArena.GetRo()+index*kGatewayStride;
    s_Bindings[index]=binding;
    std::uint8_t image[kInternalGatewayBytes];
    BuildInternalGateway(image,engine_memory::AddressOf(&s_Bindings[index]),
                         engine_call::AddressOfFunction(&isaac_internal_hook_context));
    std::memcpy(engine_memory::AsObject(InternalHookArena.GetRw()+index*kGatewayStride),image,sizeof(image));
    InternalHookArena.Flush();
    if (std::memcmp(engine_memory::AsObject(gateway),image,sizeof(image))) return Failure::WriteVerifyFailed;
    std::atomic_thread_fence(std::memory_order_release);
    exl::util::RwPages pages(slot,8);
    auto* pointer=static_cast<std::uintptr_t*>(engine_memory::AsObject(pages.GetRw()));
    std::uintptr_t expected{};
    if (!__atomic_compare_exchange_n(pointer,&expected,gateway,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED))
        return Failure::GuardMismatch;
    pages.Flush();
    std::memcpy(&current,engine_memory::AsObject(slot),8);
    if (current!=gateway) {
        expected=gateway;
        const bool restored=__atomic_compare_exchange_n(pointer,&expected,0,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
        pages.Flush();std::memcpy(&current,engine_memory::AsObject(slot),8);
        return restored && current==0?Failure::WriteVerifyFailed:Failure::RollbackFailed;
    }
    return Failure::None;
}
}
InternalHookFailure TryInstallPreinstalledInternalHook(const InternalHookBinding& binding,
                                                       const ColdInternalHookSite& site) {
    using Failure=InternalHookFailure;
    if (!ValidInternalBinding(binding) || site.source==0 || site.gate==0 || (site.gate&7)!=0 ||
        site.source>UINTPTR_MAX-4 || site.gate>UINTPTR_MAX-32 ||
        site.gate%0x1000+32>0x1000 || binding.resumeCount!=1 || binding.resumes[0]!=site.gate+16 ||
        (site.original!=0xF9400309U && site.original!=0x7100A29FU && site.original!=0xB85FC3B4U) ||
        !engine_memory::EngineMemoryReadable(site.source,4) ||
        !engine_memory::EngineMemoryReadable(site.gate,32)) return Failure::InvalidPlan;
    std::uint32_t branch{},resume{};
    if (!BuildInternalBranch(&branch,site.source,site.gate) ||
        !BuildInternalBranch(&resume,site.gate+20,site.source+4)) return Failure::InvalidPlan;
    const std::uint32_t code[6]={0x100000D0,0xC8DFFE10,0xB4000050,0xD61F0200,site.original,resume};
    if (std::memcmp(engine_memory::AsObject(site.source),&branch,4) ||
        std::memcmp(engine_memory::AsObject(site.gate),code,sizeof(code))) return Failure::GuardMismatch;
    const auto slot=site.gate+24;
    std::uintptr_t current{};std::memcpy(&current,engine_memory::AsObject(slot),8);
    if (current!=0) return Failure::VeneerNotEmpty;
    return PublishColdBinding(binding,slot);
}
InternalHookFailure TryInstallConsoleConditionalHook(const InternalHookBinding& binding,const ColdInternalHookSite& site) {
    using Failure=InternalHookFailure;
    if(!ValidInternalBinding(binding) || binding.resumeCount!=2 || site.source==0 || site.gate==0 || (site.gate&7)!=0 ||
       site.source>UINTPTR_MAX-4 || site.gate>UINTPTR_MAX-40 || site.gate%0x1000+40>0x1000 ||
       binding.resumes[1]!=site.source+4 || (site.original!=0x54002761U && site.original!=0x35002660U) ||
       !engine_memory::EngineMemoryReadable(site.source,4) || !engine_memory::EngineMemoryReadable(site.gate,40))return Failure::InvalidPlan;
    std::uint32_t jump{},taken{},fallthrough{};
    if(!BuildInternalBranch(&jump,site.source,site.gate) ||
       !BuildInternalBranch(&taken,site.gate+20,binding.resumes[0]) ||
       !BuildInternalBranch(&fallthrough,site.gate+24,binding.resumes[1]))return Failure::InvalidPlan;
    const std::uint32_t code[8]={0x10000110,0xC8DFFE10,0xB4000050,0xD61F0200,
        site.original==0x54002761U?0x54000040U:0x34000040U,taken,fallthrough,0xD503201F};
    if(std::memcmp(engine_memory::AsObject(site.source),&jump,4) ||
       std::memcmp(engine_memory::AsObject(site.gate),code,sizeof(code)))return Failure::GuardMismatch;
    std::uintptr_t current{};std::memcpy(&current,engine_memory::AsObject(site.gate+32),8);
    if(current)return Failure::VeneerNotEmpty;
    return PublishColdBinding(binding,site.gate+32);
}
} // namespace isaac::runtime::relay
