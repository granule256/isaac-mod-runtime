#pragma once

#include "ports/hook_port.hpp"
#include "program/custom_item_pool.hpp"
#include "relay/internal_hook.hpp"

#include <atomic>
#include <cstdint>

namespace isaac::runtime::custom_item_pool_native {

enum class PoolAccessSite : std::uint8_t {
    Initial = 0,
    ChaosRepick = 1,
};

struct ContextFrame {
    void* itemPool;
    std::uint32_t poolId;
    std::uint32_t reserved;
    custom_item_pool::NativePoolEntry* entry;
    ContextFrame* previous;
};

// The ordinary game thread is the only GetCollectible caller. Linked frames
// preserve nested Lua calls without using the project's unsafe thread_local.
inline ContextFrame* g_activeFrame = nullptr;
inline std::atomic<std::uint32_t> g_ready{0};

struct ScopedPoolContext {
    ScopedPoolContext() noexcept = default;
    ScopedPoolContext(void* itemPool, std::uint32_t poolId,
                      custom_item_pool::NativePoolEntry* entry) noexcept {
        Activate(itemPool, poolId, entry);
    }
    ~ScopedPoolContext() {
        if (active_ && g_activeFrame == &frame_) {
            g_activeFrame = frame_.previous;
        }
    }
    void Activate(void* itemPool, std::uint32_t poolId,
                  custom_item_pool::NativePoolEntry* entry) noexcept {
        if (active_) {
            return;
        }
        frame_.itemPool = itemPool;
        frame_.poolId = poolId;
        frame_.entry = entry;
        frame_.previous = g_activeFrame;
        g_activeFrame = &frame_;
        active_ = true;
    }

    ScopedPoolContext(const ScopedPoolContext&) = delete;
    ScopedPoolContext& operator=(const ScopedPoolContext&) = delete;

private:
    ContextFrame frame_{};
    bool active_{};
};

// Used by the two cold-hook callbacks. The ordinary game thread is the only
// caller of GetCollectible; the linked frames preserve nested Lua calls.
[[nodiscard]] inline bool ApplyPoolSubstitutionForHook(
    relay::InternalHookContext& context, PoolAccessSite site) noexcept {
    constexpr std::uintptr_t kItemPoolStride = 0x48;
    const std::uint64_t poolIdRaw =
        site == PoolAccessSite::Initial ? context.x[23] : context.x[0];
    const std::uint32_t poolId = static_cast<std::uint32_t>(poolIdRaw);
    const std::uintptr_t itemPool = context.x[22];

    if (g_activeFrame != nullptr &&
        g_activeFrame->itemPool == reinterpret_cast<void*>(itemPool) &&
        g_activeFrame->poolId == poolId) {
        context.x[23] = reinterpret_cast<std::uintptr_t>(g_activeFrame->entry);
        return true;
    }
    if (poolId >= isaac::runtime::xml_data::kFirstCustomItemPoolId) {
        return false;
    }
    if (itemPool > UINTPTR_MAX -
                        static_cast<std::uintptr_t>(poolId) * kItemPoolStride) {
        return false;
    }
    context.x[23] =
        itemPool + static_cast<std::uintptr_t>(poolId) * kItemPoolStride;
    return true;
}

[[nodiscard]] inline bool Ready() noexcept {
    return g_ready.load(std::memory_order_acquire) != 0;
}

// Called by the runtime hook owner after the fixed module image is available.
#if defined(__SWITCH__)
[[nodiscard]] Status InstallCustomItemPoolNativeHooks(
    const HookTarget& target) noexcept;
#else
[[nodiscard]] inline Status InstallCustomItemPoolNativeHooks(
    const HookTarget&) noexcept {
    return Status{StatusCode::Unsupported};
}
#endif

#if !defined(__SWITCH__)
inline void SetHostReadyForTests(bool ready) noexcept {
    g_ready.store(ready ? 1U : 0U, std::memory_order_release);
}
#endif

}  // namespace isaac::runtime::custom_item_pool_native
