#pragma once

#include "application/callback/callback_invoker.hpp"
#include "application/callback/callback_registry.hpp"
#include "domain/callback/callback_descriptor.hpp"
#include "domain/runtime/thread_affinity.hpp"

#include <atomic>
#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

struct DispatchReport {
    std::uint32_t invoked{0};
    std::uint32_t failed{0};
    std::uint32_t skippedAffinity{0};
};

// --- 派发计数（环境面地基 · 回调面）--------------------------------------------
//
// 为什么要有它：设备侧原来只能看出"某种回调登记了没有""它有没有派发点"，看不出
// **到底被派发过几次**。于是"事件根本没送到"与"送到了但模组自己没干活"在真机上长得
// 一模一样 —— 2026-09-17 查套装进度恒 `(0/3)` 时就在这两者之间来回猜了好几轮。
//
// 计数为什么放在**派发器的唯一入口**、而不是各个派发点旁边：派发点是"一种回调一处"，
// 埋点要改 N 个地方，以后新接一条回调极容易忘；而 `Dispatch` / `DispatchOwner` 是所有
// 派发的必经之路，在这里累加等价于"每接一条新回调**自动**被数到"。
//
// 下标就是 PC `ModCallbacks` 的数值（0..`kCallbackMaximumId`），与给 Lua 的枚举表一一对应，
// 所以真机读数可以直接说"第 N 种回调被派发过 M 次"，不需要再翻译。

//: 计数表的长度。PC 表到 73，所以下标 0..73 都合法。
inline constexpr std::size_t kCallbackDispatchCounterCount =
    static_cast<std::size_t>(kCallbackMaximumId) + 1;

//: 还没派发过任何回调时，"最后一次派发的回调 id"的取值。
inline constexpr std::uint32_t kNoCallbackDispatched = 0xFFFFFFFFU;

// 这张表、以及下面这两个标量**故意**定义在 `isaac::runtime` 命名空间下（不是匿名
// 命名空间）：设备读数工具（`tools/read_device_state_via_gdb.py`）按**符号名**取偏移，
// 匿名命名空间的名字带 `_ZN..12_GLOBAL__N_1L..` 前缀，换个编译器就可能漂。
extern std::atomic<std::uint32_t> g_CallbackDispatchCounts[kCallbackDispatchCounterCount];
extern std::atomic<std::uint32_t> g_LastDispatchedCallbackId;
//: 会话代数：每次新的 Lua 会话开始时 +1。读数工具用它区分"这是本次加载的计数"
//: 与"上一条命留下的残值"—— 模块在两次开局之间并不重启，没有这个数就分不清两者。
//: 做成全局（而不是只放在函数里）是因为设备侧要**按地址读**它。
extern std::atomic<std::uint32_t> g_CallbackDispatchGeneration;

[[nodiscard]] std::uint32_t CallbackDispatchGeneration() noexcept;

// 新的 Lua 会话开始时归零（由 `RegisterIsaacApi` 的会话初始化调用，与
// `ManagedFrameClock::Reset()` 同一时机、同一口径）。
void ResetCallbackDispatchCounters() noexcept;

// `Isaac.GetFrameCount()` 的帧计数真源。
//
// 生产路径里 `LuaRuntime::DispatchPostUpdate()` 每个游戏 update 调用一次
// `CallbackDispatcher::Dispatch(kCallbackPostUpdate, ...)`，所以"派发过多少次
// MC_POST_UPDATE"就是"自本次加载以来过了多少帧"。计数器放在派发层而不是 Lua 层，是因为
// 只有一个地方派发该阶段：把累加放在派发入口，就等于每个 update 恰好加一次，不需要新线程、
// 不需要任何时钟；宿主测试也可以直接调用 `LuaRuntime::DispatchPostUpdate()` 观察它递增。
//
// 这是**近似**：它数的是 Runtime 的 update 派发次数，不是引擎自己的游戏内计时器
// （引擎时钟偏移尚未定位，见 `isaac_api.cpp` 的 `Isaac.GetTime`）。
class ManagedFrameClock {
public:
    // 每次派发 MC_POST_UPDATE 时调用一次（dispatch 单线程路径，无锁）。
    static void MarkPostUpdateDispatch() noexcept;

    // 新的 Lua 会话开始时归零，保证计数是"自本次加载以来"的帧数。
    static void Reset() noexcept;

    [[nodiscard]] static std::uint64_t Count() noexcept;
};

// Synchronous dispatch for one callback id. One Mod's failure never stops the
// others, and a callback registered for another thread is skipped rather than
// run in the wrong context.
class CallbackDispatcher {
public:
    CallbackDispatcher(const CallbackRegistry& registry, ICallbackInvoker& invoker) noexcept
        : registry_(registry), invoker_(invoker) {}

    // Dispatching `kCallbackPostUpdate` advances `ManagedFrameClock` by one, so
    // this entry point is also the frame tick the `Isaac` facade reads.
    [[nodiscard]] DispatchReport Dispatch(CallbackId id, ThreadAffinity current) noexcept;
    [[nodiscard]] DispatchReport DispatchOwner(ModHandle owner, CallbackId id,
                                               ThreadAffinity current) noexcept;

private:
    [[nodiscard]] static bool AffinityMatches(ThreadAffinity declared,
                                              ThreadAffinity current) noexcept {
        // `current == Any` means the caller cannot name its context, so no
        // restriction is applied; otherwise the declared affinity must match.
        return current == ThreadAffinity::Any || declared == ThreadAffinity::Any ||
               declared == current;
    }

    const CallbackRegistry& registry_;
    ICallbackInvoker& invoker_;
};

} // namespace isaac::runtime
