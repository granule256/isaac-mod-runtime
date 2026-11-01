#include "input_poll_hook.hpp"
#include "input_poll_guards.hpp"
#include "runtime_constants.hpp"
#include "application/callback/callback_dispatcher.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lib/util/sys/rw_pages.hpp"

#include <atomic>
#include <cstring>

namespace isaac::runtime {
namespace {
std::atomic<std::uintptr_t> s_InputPollOriginal{};

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
           !std::memcmp(engine_memory::AsObject(target.base + offset), bytes.data(), N);
}
} // namespace

extern "C" void IsaacModRuntime_NativeInputPollIntercept(void* manager) {
    const auto original = s_InputPollOriginal.load(std::memory_order_acquire);
    if (!original) __builtin_trap();
    engine_call::AsFunction<NativeInputPollFn>(original)(manager);
    NativeFrameClock::CompleteInputPoll();
}

Status InstallNativeInputPollHook(const HookTarget& target) noexcept {
    if (target.buildId != kTargetBuildId ||
        !Guard(target, input_poll::kPollOffset, input_poll::kPollBytes) ||
        !Guard(target, input_poll::kPltOffset, input_poll::kPltBytes) ||
        !Window(target, input_poll::kGotOffset, sizeof(std::uintptr_t)) ||
        ((target.base + input_poll::kGotOffset) & 7)) return Status{StatusCode::Rejected};

    const auto address = target.base + input_poll::kGotOffset;
    auto expected = __atomic_load_n(static_cast<const std::uintptr_t*>(
        engine_memory::AsObject(address)), __ATOMIC_ACQUIRE);
    const auto original = target.base + input_poll::kPollOffset;
    if (expected != original && expected != target.base + kPltResolverOffset)
        return Status{StatusCode::Rejected};
    const auto previous = s_InputPollOriginal.load(std::memory_order_acquire);
    if (previous && previous != original) return Status{StatusCode::Rejected};

    // Publish the callable target before exposing the intercept through the GOT.
    s_InputPollOriginal.store(original, std::memory_order_release);
    const auto replacement = engine_call::AddressOfFunction(&IsaacModRuntime_NativeInputPollIntercept);
    bool changed = false;
    if (engine_memory::EngineMemoryWritable(address, sizeof(std::uintptr_t))) {
        changed = __atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(address)),
            &expected, replacement, false, __ATOMIC_RELEASE, __ATOMIC_RELAXED);
    } else {
        exl::util::RwPages pages(address, sizeof(std::uintptr_t));
        changed = __atomic_compare_exchange_n(static_cast<std::uintptr_t*>(engine_memory::AsObject(pages.GetRw())),
            &expected, replacement, false, __ATOMIC_RELEASE, __ATOMIC_RELAXED);
        pages.Flush();
    }
    return changed ? Status::Ok() : Status{StatusCode::Rejected};
}
} // namespace isaac::runtime
