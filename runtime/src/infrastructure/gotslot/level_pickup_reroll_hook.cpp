#include "infrastructure/gotslot/level_pickup_reroll_hook.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/minimap_pickup_cache.hpp"
#include "runtime_constants.hpp"
#include "lib/util/sys/rw_pages.hpp"

#include <atomic>
#include <cstring>

namespace isaac::runtime {
namespace {
std::atomic<std::uintptr_t> s_PickupsBase{};
std::atomic<std::uintptr_t> s_CollectiblesBase{};

bool Window(const HookTarget& target, std::uintptr_t offset, std::size_t size) {
    const auto limit = target.imageSize ? target.imageSize : target.codeSize;
    return target.base && offset <= limit && size <= limit - offset &&
           target.base <= UINTPTR_MAX - offset - size &&
           engine_memory::EngineMemoryReadable(target.base + offset, size);
}

template<std::size_t N>
bool Guard(const HookTarget& target, std::uintptr_t offset,
           const std::array<std::uint8_t, N>& bytes) {
    return Window(target, offset, N) &&
           std::memcmp(engine_memory::AsObject(target.base + offset), bytes.data(), N) == 0;
}
} // namespace

extern "C" void IsaacModRuntime_LevelPickupsRerollIntercept(void* game, std::uint32_t seed) {
    const auto base = s_PickupsBase.load(std::memory_order_acquire);
    if (!base) __builtin_trap();
    engine_call::AsFunction<void(*)(void*, std::uint32_t)>(
        base + kApi200GameRerollLevelPickupsOffset)(game, seed);
    NoteMinimapPickupReroll(MinimapPickupReroll::Pickups);
}

extern "C" void IsaacModRuntime_LevelCollectiblesRerollIntercept(void* game) {
    const auto base = s_CollectiblesBase.load(std::memory_order_acquire);
    if (!base) __builtin_trap();
    engine_call::AsFunction<void(*)(void*)>(
        base + kApi200GameRerollLevelCollectiblesOffset)(game);
    NoteMinimapPickupReroll(MinimapPickupReroll::Collectibles);
}

Status InstallLevelPickupRerollPointerHook(HookId id, const HookTarget& target) noexcept {
    using namespace level_pickup_reroll;
    const bool pickups = id == HookId::GameRerollLevelPickups;
    if (!pickups && id != HookId::GameRerollLevelCollectibles)
        return Status{StatusCode::Rejected};
    const auto entry = pickups ? kApi200GameRerollLevelPickupsOffset :
                                 kApi200GameRerollLevelCollectiblesOffset;
    const auto plt = pickups ? kPickupsPltOffset : kCollectiblesPltOffset;
    const auto got = pickups ? kPickupsGotOffset : kCollectiblesGotOffset;
    const auto& entryBytes = pickups ? kApi200GameRerollLevelPickupsExpectedBytes :
                                      kApi200GameRerollLevelCollectiblesExpectedBytes;
    const auto& pltBytes = pickups ? kPickupsPltBytes : kCollectiblesPltBytes;
    if (target.buildId != kTargetBuildId || !Guard(target, entry, entryBytes) ||
        !Guard(target, plt, pltBytes) || !Window(target, got, sizeof(std::uintptr_t)) ||
        ((target.base + got) & 7U))
        return Status{StatusCode::Rejected};

    const auto address = target.base + got;
    auto expected = __atomic_load_n(static_cast<const std::uintptr_t*>(
        engine_memory::AsObject(address)), __ATOMIC_ACQUIRE);
    if (expected != target.base + entry && expected != target.base + kPltResolverOffset)
        return Status{StatusCode::Rejected};
    auto& installedBase = pickups ? s_PickupsBase : s_CollectiblesBase;
    const auto previous = installedBase.load(std::memory_order_acquire);
    if (previous && previous != target.base) return Status{StatusCode::Rejected};

    // Publish the untouched original entry before exposing the intercept pointer.
    installedBase.store(target.base, std::memory_order_release);
    const auto replacement = pickups ?
        engine_call::AddressOfFunction(&IsaacModRuntime_LevelPickupsRerollIntercept) :
        engine_call::AddressOfFunction(&IsaacModRuntime_LevelCollectiblesRerollIntercept);
    bool changed = false;
    if (engine_memory::EngineMemoryWritable(address, sizeof(std::uintptr_t))) {
        changed = __atomic_compare_exchange_n(static_cast<std::uintptr_t*>(
            engine_memory::AsObject(address)), &expected, replacement, false,
            __ATOMIC_RELEASE, __ATOMIC_RELAXED);
    } else {
        exl::util::RwPages pages(address, sizeof(std::uintptr_t));
        changed = __atomic_compare_exchange_n(static_cast<std::uintptr_t*>(
            engine_memory::AsObject(pages.GetRw())), &expected, replacement, false,
            __ATOMIC_RELEASE, __ATOMIC_RELAXED);
        pages.Flush();
    }
    return changed ? Status::Ok() : Status{StatusCode::Rejected};
}
} // namespace isaac::runtime
