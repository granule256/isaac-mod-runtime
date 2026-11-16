#include "program/custom_item_pool_native.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lib/util/sys/jit.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <atomic>
#include <cstring>
#include <iterator>
#include <span>

extern "C" void isaac_internal_hook_context();

namespace isaac::runtime::custom_item_pool_native {
namespace {

constexpr std::uintptr_t kInitialSource = 0x3C6698;
constexpr std::uint32_t kInitialOriginal = 0x9B285AF7U;
constexpr std::uintptr_t kInitialGate = 0xA96F4;
constexpr std::uintptr_t kInitialFallback = 0x6C44;
constexpr std::uintptr_t kInitialSlot = 0x6CC8;

constexpr std::uintptr_t kChaosSource = 0x3C66EC;
constexpr std::uint32_t kChaosOriginal = 0x9B285817U;
constexpr std::uintptr_t kChaosGate = 0x12E4;
constexpr std::uintptr_t kChaosFallback = 0x357A4;
constexpr std::uintptr_t kChaosSlot = 0x18A18;
static_assert((kInitialSlot & 7) == 0 && (kChaosSlot & 7) == 0);

struct ColdSite {
    PoolAccessSite access;
    std::uintptr_t source;
    std::uint32_t original;
    std::uintptr_t gate;
    std::uintptr_t fallback;
    std::uintptr_t slot;
};

constexpr ColdSite kSites[] = {
    {PoolAccessSite::Initial, kInitialSource, kInitialOriginal, kInitialGate,
     kInitialFallback, kInitialSlot},
    {PoolAccessSite::ChaosRepick, kChaosSource, kChaosOriginal, kChaosGate,
     kChaosFallback, kChaosSlot},
};

struct SiteBinding {
    PoolAccessSite access;
};

constexpr SiteBinding kSiteBindings[] = {
    {PoolAccessSite::Initial},
    {PoolAccessSite::ChaosRepick},
};

std::atomic<std::uintptr_t> g_base{0};
relay::InternalHookBinding g_bindings[std::size(kSites)]{};

JIT_CREATE(CustomItemPoolNativeArena, 0x1000);

std::uint32_t CustomItemPoolInternalCallback(
    relay::InternalHookContext& context, const void* user) noexcept {
    const auto* binding = static_cast<const SiteBinding*>(user);
    if (binding == nullptr || !ApplyPoolSubstitutionForHook(context, binding->access)) {
        __builtin_trap();
    }
    return 0;
}

bool AddressValid(const HookTarget& target, std::uintptr_t offset,
                  std::size_t size) noexcept {
    return target.base != 0 && offset <= target.codeSize &&
           size <= target.codeSize - offset &&
           target.base <= UINTPTR_MAX - offset - size &&
           engine_memory::EngineMemoryReadable(target.base + offset, size);
}

bool BuildColdImages(const ColdSite& site, std::uint8_t* gate,
                     std::uint8_t* fallback) noexcept {
    if (gate == nullptr || fallback == nullptr || (site.slot & 7) != 0) {
        return false;
    }
    const std::int64_t slotDelta =
        static_cast<std::int64_t>(site.slot) -
        static_cast<std::int64_t>(site.gate);
    const std::int64_t fallbackDelta =
        static_cast<std::int64_t>(site.fallback) -
        static_cast<std::int64_t>(site.gate + 4);
    if (slotDelta < -0x100000 || slotDelta > 0xFFFFC ||
        fallbackDelta < -0x100000 || fallbackDelta > 0xFFFFC) {
        return false;
    }
    relay::StoreLittleEndianWord(
        gate, relay::EncodeLdrLiteral(16, static_cast<std::int32_t>(slotDelta)));
    relay::StoreLittleEndianWord(
        gate + 4,
        relay::EncodeCbz(16, static_cast<std::int32_t>(fallbackDelta)));
    relay::StoreLittleEndianWord(gate + 8, relay::EncodeBr(16));

    relay::StoreLittleEndianWord(fallback, site.original);
    std::uint32_t resume{};
    if (!relay::BuildInternalBranch(&resume, site.fallback + 4, site.source + 4)) {
        return false;
    }
    relay::StoreLittleEndianWord(fallback + 4, resume);
    return true;
}

bool ColdImagesMatch(const HookTarget& target, const ColdSite& site) noexcept {
    if (!AddressValid(target, site.source, 4) ||
        !AddressValid(target, site.gate, 12) ||
        !AddressValid(target, site.fallback, 8) ||
        !AddressValid(target, site.slot, 8)) {
        return false;
    }
    std::uint32_t source{};
    if (!relay::BuildInternalBranch(&source, target.base + site.source,
                                    target.base + site.gate)) {
        return false;
    }
    std::uint8_t gate[12]{};
    std::uint8_t fallback[8]{};
    if (!BuildColdImages(site, gate, fallback) ||
        std::memcmp(engine_memory::AsObject(target.base + site.source), &source, 4) ||
        std::memcmp(engine_memory::AsObject(target.base + site.gate), gate,
                    sizeof(gate)) ||
        std::memcmp(engine_memory::AsObject(target.base + site.fallback), fallback,
                    sizeof(fallback))) {
        return false;
    }
    std::uintptr_t slot{};
    std::memcpy(&slot, engine_memory::AsObject(target.base + site.slot),
                sizeof(slot));
    return slot == 0;
}

bool ExchangeSlot(std::uintptr_t slot, std::uintptr_t expected,
                  std::uintptr_t replacement) noexcept {
    if (slot == 0 || (slot & 7) != 0) return false;
    exl::util::RwPages pages(slot, 8);
    auto* pointer = static_cast<std::uintptr_t*>(
        engine_memory::AsObject(pages.GetRw()));
    if (!__atomic_compare_exchange_n(pointer, &expected, replacement, false,
                                     __ATOMIC_RELEASE, __ATOMIC_RELAXED)) {
        return false;
    }
    pages.Flush();
    std::uintptr_t actual{};
    std::memcpy(&actual, engine_memory::AsObject(slot), sizeof(actual));
    return actual == replacement;
}

}  // namespace

Status InstallCustomItemPoolNativeHooks(const HookTarget& target) noexcept {
    if (target.buildId != kTargetBuildId) {
        return Status{StatusCode::Rejected};
    }
    const auto previous = g_base.load(std::memory_order_acquire);
    if (previous != 0) {
        return previous == target.base ? Status::Ok()
                                       : Status{StatusCode::Rejected};
    }
    for (const ColdSite& site : kSites) {
        if (!ColdImagesMatch(target, site)) {
            return Status{StatusCode::Rejected};
        }
    }

    CustomItemPoolNativeArena.Initialize(
        std::span{impl::CustomItemPoolNativeArena::s_Area});
    for (std::size_t index = 0; index < std::size(kSites); ++index) {
        g_bindings[index] = {};
        g_bindings[index].callback = &CustomItemPoolInternalCallback;
        g_bindings[index].user = &kSiteBindings[index];
        g_bindings[index].resumeCount = 1;
        g_bindings[index].resumes[0] = target.base + kSites[index].source + 4;
        g_bindings[index].scratch = relay::InternalScratchPolicy::ProvedDeadX16;

        const auto gateway = CustomItemPoolNativeArena.GetRo() + index * 0x20;
        std::uint8_t image[relay::kInternalGatewayBytes]{};
        relay::BuildInternalGateway(
            image, engine_memory::AddressOf(&g_bindings[index]),
            engine_call::AddressOfFunction(&isaac_internal_hook_context));
        std::memcpy(
            engine_memory::AsObject(CustomItemPoolNativeArena.GetRw() +
                                    index * 0x20),
            image, sizeof(image));
        CustomItemPoolNativeArena.Flush();
        if (std::memcmp(engine_memory::AsObject(gateway), image, sizeof(image))) {
            return Status{StatusCode::Rejected};
        }
    }
    for (std::size_t index = 0; index < std::size(kSites); ++index) {
        const auto gateway = CustomItemPoolNativeArena.GetRo() + index * 0x20;
        if (!ExchangeSlot(target.base + kSites[index].slot, 0, gateway)) {
            // Undo only pointers still owned by this installation attempt.
            for (std::size_t undo = 0; undo <= index; ++undo)
                static_cast<void>(ExchangeSlot(target.base + kSites[undo].slot,
                    CustomItemPoolNativeArena.GetRo() + undo * 0x20, 0));
            return Status{StatusCode::Rejected};
        }
    }
    g_base.store(target.base, std::memory_order_release);
    g_ready.store(1, std::memory_order_release);
    return Status::Ok();
}

}  // namespace isaac::runtime::custom_item_pool_native
