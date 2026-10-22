#pragma once

#include "relay/entry_relay.hpp"
#include <cstddef>
#include <cstdint>

namespace isaac::runtime::relay {

// 中段不适用函数入口的IP0/IP1规则。此实现只允许调用方逐续接点证明x16死值，
// 决不把“caller-saved”当作“内部边界可以覆盖”的证明。
enum class InternalScratchPolicy : std::uint32_t { Unproved = 0, ProvedDeadX16 = 1 };
struct alignas(16) InternalVectorRegister { std::uint64_t low, high; };
struct alignas(16) InternalHookContext {
    std::uint64_t x[31]; // x16不存在原值（入口绝对跳转已覆盖），必须证明死值。
    std::uint64_t originalSp;
    std::uint64_t nzcv, fpcr, fpsr;
    std::uint64_t continuation;
    std::uintptr_t binding;
    std::uint64_t reserved[3];
    InternalVectorRegister q[32];
};
static_assert(offsetof(InternalHookContext, originalSp) == 0xF8);
static_assert(offsetof(InternalHookContext, nzcv) == 0x100);
static_assert(offsetof(InternalHookContext, continuation) == 0x118);
static_assert(offsetof(InternalHookContext, binding) == 0x120);
static_assert(offsetof(InternalHookContext, q) == 0x140);
static_assert(sizeof(InternalHookContext) == 0x340);

using InternalCallback = std::uint32_t (*)(InternalHookContext&, const void*) noexcept;
struct InternalHookBinding {
    InternalCallback callback{};
    const void* user{};
    std::uintptr_t resumes[4]{};
    std::uint32_t resumeCount{};
    InternalScratchPolicy scratch{InternalScratchPolicy::Unproved};
};
constexpr bool ValidInternalBinding(const InternalHookBinding& binding) {
    if (binding.callback == nullptr || binding.scratch != InternalScratchPolicy::ProvedDeadX16 ||
        binding.resumeCount == 0 || binding.resumeCount > 4) return false;
    for (std::uint32_t i = 0; i < binding.resumeCount; ++i)
        if (binding.resumes[i] == 0 || (binding.resumes[i] & 3) != 0) return false;
    return true;
}

// ARMv8允许并发替换集合中，本安装器只接受B/BL→B；CMP/MOV等一律拒绝。
constexpr bool SafeInternalBranchSource(std::uint32_t word) {
    return (word & 0x7C000000U) == 0x14000000U;
}
constexpr bool BuildInternalBranch(std::uint32_t* out, std::uintptr_t source,
                                   std::uintptr_t destination) {
    if (out == nullptr || source == 0 || destination == 0 || ((source|destination)&3) != 0)
        return false;
    std::int64_t delta{};
    if (destination >= source) {
        if (destination-source > 0x7FFFFFC) return false;
        delta = static_cast<std::int64_t>(destination-source);
    } else {
        if (source-destination > 0x8000000) return false;
        delta = -static_cast<std::int64_t>(source-destination);
    }
    *out = 0x14000000U | (static_cast<std::uint32_t>(delta/4)&0x03FFFFFFU);
    return true;
}
constexpr void BuildInternalVeneer(std::uint8_t* out, std::uintptr_t gateway) {
    StoreLittleEndianWord(out, EncodeLdrLiteral(16,8));
    StoreLittleEndianWord(out+4, EncodeBr(16));
    StoreLittleEndianDoubleWord(out+8,gateway);
}

// 8B近桩仅跳到页首gateway；signed21页ADRP覆盖±4GiB，不截断不猜地址。
constexpr bool BuildInternalPageVeneer(std::uint8_t* out, std::uintptr_t source,
                                       std::uintptr_t gateway) {
    if (out == nullptr || source == 0 || gateway == 0 || (source & 3) != 0 ||
        (gateway & 0xFFF) != 0) return false;
    const auto sourcePage = source >> 12;
    const auto targetPage = gateway >> 12;
    std::int64_t delta{};
    if (targetPage >= sourcePage) {
        if (targetPage-sourcePage > 0xFFFFF) return false;
        delta = static_cast<std::int64_t>(targetPage-sourcePage);
    } else {
        if (sourcePage-targetPage > 0x100000) return false;
        delta = -static_cast<std::int64_t>(sourcePage-targetPage);
    }
    const auto imm = static_cast<std::uint32_t>(delta) & 0x1FFFFFU;
    StoreLittleEndianWord(out, 0x90000010U | ((imm & 3U) << 29) | ((imm >> 2) << 5));
    StoreLittleEndianWord(out+4, EncodeBr(16));
    return true;
}

// 两条指令从NRO内独立8B槽取完整目标指针；只要求槽在LDR literal的±1MiB内。
constexpr bool BuildInternalLiteralVeneer(std::uint8_t* out,std::uintptr_t source,
                                        std::uintptr_t slot) {
    if(!out||!source||!slot||(source&3)||(slot&7)||
       source>UINTPTR_MAX-8||slot>UINTPTR_MAX-8||
       (source<slot+8&&slot<source+8))return false;
    std::int64_t delta{};
    if(slot>=source){if(slot-source>0xFFFFC)return false;delta=slot-source;}
    else {if(source-slot>0x100000)return false;delta=-static_cast<std::int64_t>(source-slot);}
    const auto imm=static_cast<std::uint32_t>(delta/4)&0x7FFFFU;
    StoreLittleEndianWord(out,0x58000010U|(imm<<5));
    StoreLittleEndianWord(out+4,EncodeBr(16));return true;
}

constexpr std::size_t kInternalGatewayBytes = 32;
constexpr void BuildInternalGateway(std::uint8_t* out, std::uintptr_t binding,
                                    std::uintptr_t common) {
    // 先保存x17和原LR；之后才借用x17装绑定、x16装公共汇编入口。
    StoreLittleEndianWord(out, 0xA9BF7BF1u); // stp x17,x30,[sp,#-16]!
    StoreLittleEndianWord(out + 4, EncodeLdrLiteral(17, 12));
    StoreLittleEndianWord(out + 8, EncodeLdrLiteral(16, 16));
    StoreLittleEndianWord(out + 12, EncodeBr(16));
    StoreLittleEndianDoubleWord(out + 16, binding);
    StoreLittleEndianDoubleWord(out + 24, common);
}

enum class InternalVeneerKind : std::uint32_t { Absolute16 = 0, Page8 = 1, Literal8 = 2 };
struct InternalHookSite {
    std::uintptr_t target{};
    std::uint32_t expected{}; // 必须为已有的B或BL，仅原子替换该4字节。
    InternalVeneerKind veneerKind{InternalVeneerKind::Absolute16};
    std::uintptr_t literalSlot{}; // Literal8使用；发布后不回收，不与代码或其他中继共用。
};
enum class InternalHookFailure : std::uint32_t {
    None, InvalidPlan, GuardMismatch, ArenaExhausted, WriteVerifyFailed, RollbackFailed,
    UnsafeInstruction, VeneerNotEmpty
};
// 安装期单线程调用；先核空近接桩、发布不可变绑定/gateway/近桩，再CAS替换一条B/BL。
// 入口失败只原子恢复原B/BL；已发布桩与绑定永不回收，保障已进入的线程仍能执行。
InternalHookFailure TryInstallInternalHook(const InternalHookBinding& binding,
    const InternalHookSite& site, std::uintptr_t veneer);

// 源B与原指令重放块在NRO加载前由IPS安装；运行时只发布gate+24的8B指针。
struct ColdInternalHookSite {
    std::uintptr_t source{}, gate{};
    std::uint32_t original{};
};
InternalHookFailure TryInstallPreinstalledInternalHook(const InternalHookBinding&,
                                                      const ColdInternalHookSite&);
// 两条Console未知命令条件分支。加载前已拆成反条件+B+B，只发布gate+32槽。
InternalHookFailure TryInstallConsoleConditionalHook(const InternalHookBinding&,
                                                     const ColdInternalHookSite&);

} // namespace isaac::runtime::relay
