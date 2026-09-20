#include "application/callback/callback_dispatcher.hpp"

namespace isaac::runtime {

// 计数表与代数放在命名空间作用域（不是匿名命名空间）：设备读数工具按符号名取偏移，
// 理由见头文件。定义在头里声明、这里落地。
std::atomic<std::uint32_t> g_CallbackDispatchCounts[kCallbackDispatchCounterCount]{};
std::atomic<std::uint32_t> g_LastDispatchedCallbackId{kNoCallbackDispatched};
std::atomic<std::uint32_t> g_CallbackDispatchGeneration{0};

namespace {

// 只有游戏线程会走派发路径（与 `g_PostUpdateDispatchCount` 同一条约定），所以用
// relaxed 就够；读数工具在别的线程上读这几个字，取值语义上是"某个已经发生过的时刻的快照"，
// 不需要跨量的先后关系。
void RecordDispatch(CallbackId id) noexcept {
    if (id < kCallbackDispatchCounterCount) {
        g_CallbackDispatchCounts[id].fetch_add(1, std::memory_order_relaxed);
    }
    g_LastDispatchedCallbackId.store(id, std::memory_order_relaxed);
}

// 单线程派发路径上的普通全局：只有游戏线程会调用 `Dispatch`，所以既不需要锁，也不能用
// `thread_local`（本项目在真机上已被 `thread_local` 坑过一次，见 `lua_runtime.cpp` 的注释）。
std::uint64_t g_PostUpdateDispatchCount = 0;

} // namespace

void ResetCallbackDispatchCounters() noexcept {
    for (std::size_t index = 0; index < kCallbackDispatchCounterCount; ++index) {
        g_CallbackDispatchCounts[index].store(0, std::memory_order_relaxed);
    }
    g_LastDispatchedCallbackId.store(kNoCallbackDispatched, std::memory_order_relaxed);
    // 代数只增不减：它是"这是第几次 Lua 会话"的凭证，归零就失去区分能力。
    g_CallbackDispatchGeneration.fetch_add(1, std::memory_order_relaxed);
}

std::uint32_t CallbackDispatchGeneration() noexcept {
    return g_CallbackDispatchGeneration.load(std::memory_order_relaxed);
}

void ManagedFrameClock::MarkPostUpdateDispatch() noexcept {
    ++g_PostUpdateDispatchCount;
}

void ManagedFrameClock::Reset() noexcept {
    g_PostUpdateDispatchCount = 0;
}

std::uint64_t ManagedFrameClock::Count() noexcept {
    return g_PostUpdateDispatchCount;
}

DispatchReport CallbackDispatcher::Dispatch(CallbackId id, ThreadAffinity current) noexcept {
    // 计数在最前面：即使一种回调一条登记都没有（遍历为空），"引擎确实到了这个时机"这件事
    // 仍然要被记下来 —— 那正是区分"事件没送到"与"送到了没人听"的唯一依据。
    RecordDispatch(id);
    DispatchReport report{};
    if (id == kCallbackPostUpdate) {
        // 每个 update 恰好一次：这是 `Isaac.GetFrameCount()` 的唯一累加点。
        ManagedFrameClock::MarkPostUpdateDispatch();
    }
    // 顺序按**优先级升序 + 同优先级登记顺序**（见 `CollectCallOrder` 的注释）。
    std::uint8_t order[kCallbackDispatchOrderCapacity];
    const std::size_t total = CollectCallOrder(registry_, id, false, ModHandle{}, current,
                                              FilterMode::Ignore,
                                              CallbackRegistry::kNoCallbackFilter, order,
                                              &report.skippedAffinity, &report.skippedFilter);
    for (std::size_t position = 0; position < total; ++position) {
        const CallbackDescriptor* descriptor = registry_.AtIndex(order[position]);
        if (descriptor == nullptr) {
            continue;
        }
        if (invoker_.Invoke(*descriptor).ok()) {
            ++report.invoked;
        } else {
            ++report.failed;
        }
    }
    return report;
}

DispatchReport CallbackDispatcher::DispatchFiltered(CallbackId id, ThreadAffinity current,
                                                   std::int64_t filter) noexcept {
    RecordDispatch(id);
    DispatchReport report{};
    if (id == kCallbackPostUpdate) {
        ManagedFrameClock::MarkPostUpdateDispatch();
    }
    // 过滤器与描述符的平行关系按**全表下标**定义（`CallbackRegistry::FilterAt`），
    // 所以收集也在全表上走；顺序同样按优先级（见 `CollectCallOrder`）。
    std::uint8_t order[kCallbackDispatchOrderCapacity];
    const std::size_t total = CollectCallOrder(registry_, id, false, ModHandle{}, current,
                                              FilterMode::Apply, filter, order,
                                              &report.skippedAffinity, &report.skippedFilter);
    for (std::size_t position = 0; position < total; ++position) {
        const CallbackDescriptor* descriptor = registry_.AtIndex(order[position]);
        if (descriptor == nullptr) {
            continue;
        }
        if (invoker_.Invoke(*descriptor).ok()) {
            ++report.invoked;
        } else {
            ++report.failed;
        }
    }
    return report;
}

CallbackDispatchOutcome CallbackDispatcher::DispatchModifying(CallbackId id, ThreadAffinity current,
                                                             std::int64_t filter) noexcept {
    RecordDispatch(id);
    CallbackDispatchOutcome outcome{};
    // 全表遍历的理由同 `DispatchFiltered`（过滤器按全表下标与描述符平行）；
    // 顺序同样按**优先级升序 + 同优先级登记顺序**（见 `CollectCallOrder`）。
    std::uint8_t order[kCallbackDispatchOrderCapacity];
    const std::size_t total = CollectCallOrder(registry_, id, false, ModHandle{}, current,
                                              FilterMode::Apply, filter, order,
                                              &outcome.skippedAffinity, &outcome.skippedFilter);
    for (std::size_t position = 0; position < total; ++position) {
        const CallbackDescriptor* descriptor = registry_.AtIndex(order[position]);
        if (descriptor == nullptr) {
            continue;
        }
        CallbackReturn returned{};
        if (!invoker_.InvokeCollecting(*descriptor, &returned).ok()) {
            ++outcome.failed;
            continue;
        }
        ++outcome.invoked;
        if (!returned.called) {
            continue;
        }
        if (returned.nonNil) {
            outcome.anyNonNil = true;
        }
        if (returned.truthy) {
            outcome.anyTruthy = true;
        }
        // "第一条胜出"：`MC_POST_GET_COLLECTIBLE` 的文档写明"返回的值**不会**更新后续回调
        // 看到的 SelectedCollectible"⇒ 后续回调拿到的仍是同一个原值，因此后一条的返回值
        // 不会覆盖前一条。写成"第一条胜出"与那个语义一致（且不会让最后一条默默赢）。
        if (returned.hasInteger && !outcome.hasInteger) {
            outcome.hasInteger = true;
            outcome.integer = returned.integer;
        }
    }
    return outcome;
}

DispatchReport CallbackDispatcher::DispatchOwner(ModHandle owner, CallbackId id,
                                                 ThreadAffinity current) noexcept {
    // 与 `Dispatch` 同一个口径：数的是"这种回调被派发过几次"，与谁来听、听了几个无关。
    RecordDispatch(id);
    DispatchReport report{};
    // 与其它入口同一套顺序（优先级升序 + 同优先级登记顺序），只是多一个属主条件。
    std::uint8_t order[kCallbackDispatchOrderCapacity];
    const std::size_t total = CollectCallOrder(registry_, id, true, owner, current,
                                              FilterMode::Ignore,
                                              CallbackRegistry::kNoCallbackFilter, order,
                                              &report.skippedAffinity, &report.skippedFilter);
    for (std::size_t position = 0; position < total; ++position) {
        const CallbackDescriptor* descriptor = registry_.AtIndex(order[position]);
        if (descriptor == nullptr) {
            continue;
        }
        if (invoker_.Invoke(*descriptor).ok()) {
            ++report.invoked;
        } else {
            ++report.failed;
        }
    }
    return report;
}

} // namespace isaac::runtime
