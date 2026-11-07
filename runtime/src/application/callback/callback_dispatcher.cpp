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
std::uint64_t g_NativeFrameCount = 0;
bool g_NativeInputSampled = false;

// 帧边界钩子：默认没有；输入层在会话初始化时装上。
FrameBoundaryHook g_FrameBoundaryHook = nullptr;

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

void NativeFrameClock::BeginNativeFrame() noexcept {
    ++g_NativeFrameCount;
    g_NativeInputSampled = false;
}

void NativeFrameClock::CompleteInputPoll() noexcept {
    if (g_NativeInputSampled) return;
    // Claim before sampling: native action queries can synchronously enter Lua.
    g_NativeInputSampled = true;
    if (g_FrameBoundaryHook != nullptr) g_FrameBoundaryHook(g_NativeFrameCount);
}

void NativeFrameClock::MarkNativeFrame(bool inputPolled) noexcept {
    BeginNativeFrame();
    if (inputPolled) CompleteInputPoll();
}

std::uint64_t NativeFrameClock::Count() noexcept {
    return g_NativeFrameCount;
}

void SetFrameBoundaryHook(FrameBoundaryHook hook) noexcept {
    g_FrameBoundaryHook = hook;
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
    CallbackBatchResult batch{};
    if(invoker_.InvokeBatch(id,CallbackRegistry::kNoCallbackFilter,&batch)) {
        report.invoked=batch.invoked;report.failed=batch.failed;report.skippedFilter=batch.skippedFilter;return report;
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
        CallbackReturn returned{};
        if (!invoker_.InvokeCollecting(*descriptor, &returned).ok()) {
            ++report.failed;
            break; // PC整个_RunCallback保护调用失败，后续登记不继续。
        }
        ++report.invoked;
        if (returned.called && returned.nonNil) break; // 即使调用方丢弃结果，Lua也已短路。
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
    CallbackBatchResult batch{};
    if(invoker_.InvokeBatch(id,filter,&batch)) {
        report.invoked=batch.invoked;report.failed=batch.failed;report.skippedFilter=batch.skippedFilter;return report;
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
        CallbackReturn returned{};
        if (!invoker_.InvokeCollecting(*descriptor, &returned).ok()) {
            ++report.failed;
            break; // PC整个_RunCallback保护调用失败，后续登记不继续。
        }
        ++report.invoked;
        if (returned.called && returned.nonNil) break; // 即使调用方丢弃结果，Lua也已短路。
    }
    return report;
}

CallbackDispatchOutcome CallbackDispatcher::DispatchModifying(CallbackId id, ThreadAffinity current,
                                                             std::int64_t filter) noexcept {
    RecordDispatch(id);
    CallbackDispatchOutcome outcome{};
    CallbackBatchResult batch{};
    if(invoker_.InvokeBatch(id,filter,&batch)) {
        outcome.invoked=batch.invoked;outcome.failed=batch.failed;outcome.skippedFilter=batch.skippedFilter;
        if(batch.failed==0) {
            outcome.hasTable=batch.returned.hasTable;outcome.anyNonNil=batch.returned.nonNil;
            outcome.anyTruthy=batch.returned.truthy;outcome.hasInteger=batch.returned.hasInteger;
            outcome.integer=batch.returned.integer;outcome.hasNumber=batch.returned.hasNumber;
            outcome.number=batch.returned.number;
        }
        return outcome;
    }
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
            break;
        }
        ++outcome.invoked;
        if (!returned.called) {
            continue;
        }
        if ((id == kCallbackPreEntitySpawn || id == kCallbackPreRoomEntitySpawn || id == kCallbackUseItem || id == kCallbackPostPickupSelection) && returned.hasTable) {
            outcome.hasTable = true; // 完整PC bootstrap遇首个非nil即停，空表也短路。
        }
        if (returned.nonNil) {
            outcome.anyNonNil = true;
        }
        if (returned.truthy) {
            outcome.anyTruthy = true;
        }
        // 完整PC_RunCallback只返回第一个非nil；整数转换由Lua保护桥完成。
        if (returned.hasInteger && !outcome.hasInteger) {
            outcome.hasInteger = true;
            outcome.integer = returned.integer;
        }
        // 2026-10-07：数字通道同 `integer` 的口径 —— 第一条胜出
        // （`MC_INPUT_ACTION` 的 `GET_ACTION_VALUE` 覆盖值用）。
        if (returned.hasNumber && !outcome.hasNumber) {
            outcome.hasNumber = true;
            outcome.number = returned.number;
        }
        // PC main.lua的统一规则：包括Input、空表、false、0，均停止其余登记。
        if (returned.nonNil) break;
    }
    return outcome;
}

DispatchReport CallbackDispatcher::DispatchOwner(ModHandle owner, CallbackId id,
                                                 ThreadAffinity current) noexcept {
    // 与 `Dispatch` 同一个口径：数的是"这种回调被派发过几次"，与谁来听、听了几个无关。
    RecordDispatch(id);
    DispatchReport report{};
    CallbackBatchResult batch{};
    if(invoker_.InvokeBatch(id,CallbackRegistry::kNoCallbackFilter,&batch,&owner)) {
        report.invoked=batch.invoked;report.failed=batch.failed;report.skippedFilter=batch.skippedFilter;return report;
    }
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
        CallbackReturn returned{};
        if (!invoker_.InvokeCollecting(*descriptor, &returned).ok()) {
            ++report.failed;
            break; // PC整个_RunCallback保护调用失败，后续登记不继续。
        }
        ++report.invoked;
        if (returned.called && returned.nonNil) break; // 即使调用方丢弃结果，Lua也已短路。
    }
    return report;
}

} // namespace isaac::runtime
