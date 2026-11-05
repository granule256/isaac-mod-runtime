#include "infrastructure/gotslot/restart_input_hook.hpp"
#include "infrastructure/gotslot/restart_input_guards.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/restart_input_chord.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
#include "lib/util/sys/rw_pages.hpp"

#include <atomic>
#include <cstring>

namespace isaac::runtime {
namespace {
std::atomic<std::uintptr_t> s_RestartInputBase{};
// Game::ProcessInput evaluates one short-circuit conjunction on the game thread.
// The first query resolves its logical action; the remaining three consume it.
bool s_RestartHeld{};
using ButtonQuery = bool (*)(void*, std::uint32_t, std::uint32_t, void*);

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

bool QueryNativeRestartInput(std::uintptr_t caller, void* manager, std::uint32_t button,
                             std::uint32_t controller, void* out) noexcept {
    const auto base = s_RestartInputBase.load(std::memory_order_acquire);
    if (!base) __builtin_trap();
    const auto original = engine_call::AsFunction<ButtonQuery>(base + kKageIsButtonPressedOffset);
    // Only the four verified Game::ProcessInput call sites represent restart.
    // All other raw consumers retain their physical-button semantics.
    if (caller == base + 0x351678) {
        bool held = true;
        for (const auto component : kNativeRestartButtons) {
            if (!original(manager, component, controller, out)) { held = false; break; }
        }
        const auto outcome = LuaRuntime::DispatchLogicalInputAction(kLuaRestartAction, 0, 0);
        s_RestartHeld = outcome.overridden ? outcome.boolean : held;
        return s_RestartHeld;
    }
    if (caller == base + 0x351694 || caller == base + 0x3516b0 || caller == base + 0x3516cc)
        return s_RestartHeld;
    return original(manager, button, controller, out);
}

extern "C" __attribute__((noinline)) bool IsaacModRuntime_RestartInputIntercept(
        void* manager, std::uint32_t button, std::uint32_t controller, void* out) {
    const auto caller = reinterpret_cast<std::uintptr_t>(
        __builtin_extract_return_addr(__builtin_return_address(0)));
    return QueryNativeRestartInput(caller, manager, button, controller, out);
}

Status InstallNativeRestartInputHook(const HookTarget& target) noexcept {
    using namespace restart_input;
    if (target.buildId != kTargetBuildId ||
        !Guard(target, kKageIsButtonPressedOffset, kKageIsButtonPressedExpectedBytes) ||
        !Guard(target, kButtonPlt, kButtonPltBytes) ||
        !Guard(target, kChordContext, kChordContextBytes) ||
        !Window(target, kButtonGot, sizeof(std::uintptr_t)) || ((target.base + kButtonGot) & 7U))
        return Status{StatusCode::Rejected};
    const auto address = target.base + kButtonGot;
    auto expected = __atomic_load_n(static_cast<const std::uintptr_t*>(
        engine_memory::AsObject(address)), __ATOMIC_ACQUIRE);
    if (expected != target.base + kKageIsButtonPressedOffset &&
        expected != target.base + kPltResolverOffset) return Status{StatusCode::Rejected};
    const auto previous = s_RestartInputBase.load(std::memory_order_acquire);
    if (previous && previous != target.base) return Status{StatusCode::Rejected};
    s_RestartInputBase.store(target.base, std::memory_order_release);
    const auto replacement = engine_call::AddressOfFunction(&IsaacModRuntime_RestartInputIntercept);
    bool changed{};
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
