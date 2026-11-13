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
constexpr bool BuildStatHudColdImages(const ColdInternalHookSite& site,
    std::uintptr_t fallback,std::uint8_t* gate,std::uint8_t* replay) {
    if(!gate||!replay||site.source<24||!site.gate||!fallback||
       (site.source&3)||(site.gate&7)||(fallback&3)||
       site.source>UINTPTR_MAX-16||site.gate>UINTPTR_MAX-24||fallback>UINTPTR_MAX-12||
       (site.original!=0x54FFFF40U&&site.original!=0x54FFFF43U))return false;
    const auto from=site.gate+4;
    std::int64_t delta{};
    if(fallback>=from){if(fallback-from>0xFFFFC)return false;delta=fallback-from;}
    else {if(from-fallback>0x100000)return false;delta=-static_cast<std::int64_t>(from-fallback);}
    std::uint32_t taken{},fallthrough{};
    if(!BuildInternalBranch(&taken,fallback+4,site.source-24)||
       !BuildInternalBranch(&fallthrough,fallback+8,site.source+4))return false;
    StoreLittleEndianWord(gate,0x58000090U);
    StoreLittleEndianWord(gate+4,0xB4000010U|((static_cast<std::uint32_t>(delta/4)&0x7FFFFU)<<5));
    StoreLittleEndianWord(gate+8,EncodeBr(16));
    StoreLittleEndianWord(gate+12,0xD503201FU);
    StoreLittleEndianDoubleWord(gate+16,0);
    StoreLittleEndianWord(replay,0x54000040U|((site.original&15U)^1U));
    StoreLittleEndianWord(replay+4,taken);
    StoreLittleEndianWord(replay+8,fallthrough);
    return true;
}
InternalHookFailure TryInstallStatHudColdHook(const InternalHookBinding&,
    const ColdInternalHookSite&,std::uintptr_t fallback);
InternalHookFailure TryInstallPreinstalledInternalHook(const InternalHookBinding&,
                                                      const ColdInternalHookSite&);
// 两条Console未知命令条件分支。加载前已拆成反条件+B+B，只发布gate+32槽。
InternalHookFailure TryInstallConsoleConditionalHook(const InternalHookBinding&,
                                                     const ColdInternalHookSite&);

// Indirect cold gate for a dynamic `blr xN` call site.
//
// The preinstalled source word is `B gate`; the gate pointer slot is zero until
// runtime publication. With a null slot, fallback sets x30 to source+4 and
// branches through the original BLR register, exactly preserving the original
// call's return address and target. The gate may only use x16 because the
// caller must prove x16 dead at the site.
inline constexpr std::size_t kColdIndirectGateBytes = 12;
inline constexpr std::size_t kColdIndirectSlotBytes = 8;
inline constexpr std::size_t kColdIndirectFallbackBytes = 8;
struct ColdIndirectHookSite {
    std::uintptr_t source{}, gate{}, slot{}, fallback{};
    std::uint32_t original{};
    std::uint32_t targetRegister{};
};

constexpr bool BuildColdIndirectImages(const ColdIndirectHookSite& site,
                                       std::uint8_t* gate,
                                       std::uint8_t* fallback) {
    if (gate == nullptr || fallback == nullptr || site.source == 0 ||
        site.gate == 0 || site.slot == 0 || site.fallback == 0 ||
        (site.source & 3) != 0 || (site.gate & 3) != 0 ||
        (site.slot & 7) != 0 || (site.fallback & 3) != 0 ||
        site.source > UINTPTR_MAX - 4 ||
        site.gate > UINTPTR_MAX - kColdIndirectGateBytes ||
        site.slot > UINTPTR_MAX - kColdIndirectSlotBytes ||
        site.fallback > UINTPTR_MAX - kColdIndirectFallbackBytes) {
        return false;
    }
    if (site.targetRegister > 30 || site.targetRegister == 16 ||
        site.targetRegister == 30 ||
        site.original !=
            (0xD63F0000U | (site.targetRegister << 5))) {
        return false;
    }

    const auto ranges = [&site](std::size_t index, std::uintptr_t* begin,
                                std::uintptr_t* end) {
        switch (index) {
            case 0: *begin = site.source; *end = site.source + 4; return true;
            case 1: *begin = site.gate; *end = site.gate + kColdIndirectGateBytes; return true;
            case 2: *begin = site.slot; *end = site.slot + kColdIndirectSlotBytes; return true;
            case 3: *begin = site.fallback; *end = site.fallback + kColdIndirectFallbackBytes; return true;
            default: return false;
        }
    };
    std::uintptr_t begins[4]{}, ends[4]{};
    for (std::size_t i = 0; i < 4; ++i) {
        if (!ranges(i, &begins[i], &ends[i])) return false;
    }
    for (std::size_t i = 1; i < 4; ++i) {
        const auto begin = begins[i];
        const auto end = ends[i];
        std::size_t j = i;
        while (j > 0 && begins[j - 1] > begin) {
            begins[j] = begins[j - 1];
            ends[j] = ends[j - 1];
            --j;
        }
        begins[j] = begin;
        ends[j] = end;
    }
    for (std::size_t i = 1; i < 4; ++i) {
        if (ends[i - 1] > begins[i]) return false;
    }

    const auto signed_delta = [](std::uintptr_t from, std::uintptr_t to,
                                 std::int64_t* delta) {
        if (delta == nullptr || ((from | to) & 3) != 0) return false;
        if (to >= from) {
            if (to - from > 0xFFFFCU) return false;
            *delta = static_cast<std::int64_t>(to - from);
        } else {
            if (from - to > 0x100000U) return false;
            *delta = -static_cast<std::int64_t>(from - to);
        }
        return true;
    };
    std::int64_t slotDelta{}, fallbackDelta{}, resumeDelta{};
    if (!signed_delta(site.gate, site.slot, &slotDelta) ||
        !signed_delta(site.gate + 4, site.fallback, &fallbackDelta) ||
        !signed_delta(site.fallback, site.source + 4, &resumeDelta)) {
        return false;
    }
    std::uint32_t sourceBranch{};
    if (!BuildInternalBranch(&sourceBranch, site.source, site.gate)) {
        return false;
    }

    StoreLittleEndianWord(
        gate, EncodeLdrLiteral(16, static_cast<std::int32_t>(slotDelta)));
    StoreLittleEndianWord(
        gate + 4, EncodeCbz(16, static_cast<std::int32_t>(fallbackDelta)));
    StoreLittleEndianWord(gate + 8, EncodeBr(16));
    StoreLittleEndianWord(
        fallback, EncodeAdr(30, static_cast<std::int32_t>(resumeDelta)));
    StoreLittleEndianWord(fallback + 4, EncodeBr(site.targetRegister));
    return true;
}
constexpr bool BuildColdIndirectImages(const ColdIndirectHookSite& site,
                                       std::uint8_t* gate, std::uint8_t* slot,
                                       std::uint8_t* fallback) {
    if (slot == nullptr ||
        !BuildColdIndirectImages(site, gate, fallback)) {
        return false;
    }
    for (std::size_t i = 0; i < kColdIndirectSlotBytes; ++i) slot[i] = 0;
    return true;
}

InternalHookFailure TryInstallColdIndirectHook(
    const InternalHookBinding&, const ColdIndirectHookSite&);
InternalHookFailure ColdIndirectReady(const ColdIndirectHookSite&,
                                      std::uintptr_t expectedGateway);
InternalHookFailure RollbackColdIndirectHook(const ColdIndirectHookSite&,
                                             std::uintptr_t expectedGateway);

} // namespace isaac::runtime::relay
