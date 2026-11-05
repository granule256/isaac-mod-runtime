#include "entity_init_hook.hpp"
#include "ports/hook_port.hpp"
#include "native_init_slots.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"
#include <atomic>
#include <cstring>

namespace isaac::runtime {
namespace {
std::atomic<std::uintptr_t> s_ModuleBases[3]{};

bool Window(const HookTarget& target, std::uintptr_t offset, std::size_t size) noexcept {
    const auto limit = target.imageSize != 0 ? target.imageSize : target.codeSize;
    return target.base != 0 && offset <= limit && size <= limit - offset &&
        target.base <= UINTPTR_MAX - offset - size &&
        engine_memory::EngineMemoryReadable(target.base + offset, size);
}
template<std::size_t N>
bool Guard(const HookTarget& target, std::uintptr_t offset, const std::array<u8, N>& bytes) noexcept {
    return offset <= target.codeSize && N <= target.codeSize - offset &&
        Window(target, offset, N) &&
        std::memcmp(engine_memory::AsObject(target.base + offset), bytes.data(), N) == 0;
}
std::uintptr_t LoadPointer(const void*, std::uintptr_t address) {
    return __atomic_load_n(static_cast<const std::uintptr_t*>(engine_memory::AsObject(address)), __ATOMIC_ACQUIRE);
}
bool ComparePointer(void*, std::uintptr_t address, std::uintptr_t expected, std::uintptr_t replacement) {
    if (engine_memory::EngineMemoryWritable(address, sizeof(std::uintptr_t)))
        return __atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(address)),
            &expected, replacement, false, __ATOMIC_RELEASE, __ATOMIC_RELAXED);
    exl::util::RwPages pages(address, sizeof(std::uintptr_t));
    const bool changed = __atomic_compare_exchange_n(
        static_cast<std::uintptr_t*>(engine_memory::AsObject(pages.GetRw())),
        &expected, replacement, false, __ATOMIC_RELEASE, __ATOMIC_RELAXED);
    pages.Flush();
    return changed;
}
constexpr std::uintptr_t InitOffset(NativeEntityInitKind kind) noexcept {
    switch (kind) {
        case NativeEntityInitKind::Base: return kNativeEntityInitOffset;
        case NativeEntityInitKind::Tear: return kNativeTearInitOffset;
        case NativeEntityInitKind::Effect: return kNativeEffectInitOffset;
    }
    return 0;
}
template<NativeEntityInitKind Kind>
void InitIntercept(void* entity, std::uint32_t type, std::uint32_t variant,
    std::uint32_t subtype, std::uint32_t seed) {
    const auto base = s_ModuleBases[static_cast<unsigned>(Kind)].load(std::memory_order_acquire);
    if (base == 0) __builtin_trap();
    const EntityInitNativeBindings native{
        engine_call::AsFunction<EntityInitNativeBindings::Init>(base + InitOffset(Kind))};
    RunNativeEntityInit(&native, Kind, entity, type, variant, subtype, seed);
}
template<NativeEntityInitKind Kind, std::size_t N>
Status Install(const HookTarget& target, const std::array<std::uintptr_t, N>& offsets) noexcept {
    std::array<std::uintptr_t, N> sites{}, expected{};
    for (std::size_t i = 0; i < N; ++i) {
        if (!Window(target, offsets[i], sizeof(std::uintptr_t)) || ((target.base + offsets[i]) & 7) != 0)
            return Status{StatusCode::Rejected};
        sites[i] = target.base + offsets[i];
        expected[i] = LoadPointer(nullptr, sites[i]);
        const bool unresolvedGot = Kind == NativeEntityInitKind::Base &&
            offsets[i] == kNativeEntityInitGotOffset && expected[i] == target.base + kPltResolverOffset;
        if (expected[i] != target.base + InitOffset(Kind) && !unresolvedGot)
            return Status{StatusCode::Rejected};
    }
    auto& published = s_ModuleBases[static_cast<unsigned>(Kind)];
    auto previous = published.load(std::memory_order_acquire);
    if (previous != 0 && previous != target.base) return Status{StatusCode::Rejected};
    // Original addresses must be visible before any observer can call a slot.
    if (previous == 0 && !published.compare_exchange_strong(previous, target.base,
        std::memory_order_release, std::memory_order_acquire) && previous != target.base)
        return Status{StatusCode::Rejected};
    const NativeInitSlotIo io{nullptr, LoadPointer, ComparePointer};
    const auto result = InstallNativeInitSlotPlan(io, sites, expected,
        engine_call::AddressOfFunction(&InitIntercept<Kind>));
    return result == NativeInitSlotFailure::None ? Status::Ok() : Status{StatusCode::Rejected};
}
}

Status InstallEntityInitPointerHooks(HookId id, const HookTarget& target) noexcept {
    if (target.buildId != kTargetBuildId) return Status{StatusCode::Rejected};
    switch (id) {
        case HookId::EntityInit:
            if (!Guard(target, kNativeEntityInitOffset, kNativeEntityInitExpectedBytes) ||
                !Guard(target, kNativeEntityInitPltOffset, kNativeEntityInitPltExpectedBytes))
                return Status{StatusCode::Rejected};
            return Install<NativeEntityInitKind::Base>(target,
                std::array{kNativeEntityInitVtableSlotOffset, kNativeEntityInitGotOffset});
        case HookId::EntityTearInit:
            if (!Guard(target, kNativeTearInitOffset, kNativeTearInitExpectedBytes))
                return Status{StatusCode::Rejected};
            return Install<NativeEntityInitKind::Tear>(target, std::array{kNativeTearInitVtableSlotOffset});
        case HookId::EntityEffectInit:
            if (!Guard(target, kNativeEffectInitOffset, kNativeEffectInitExpectedBytes))
                return Status{StatusCode::Rejected};
            return Install<NativeEntityInitKind::Effect>(target, std::array{kNativeEffectInitVtableSlotOffset});
        default: return Status{StatusCode::InvalidArgument};
    }
}
}
