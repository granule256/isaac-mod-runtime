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
    //: 因为过滤器对不上而没被调用（`DispatchFiltered` 才有非零值）。
    std::uint32_t skippedFilter{0};
};

// --- "可改返回值"派发的结果 --------------------------------------------------
//
// PC 上有一族回调的返回值会影响引擎接下来的行为（`MC_PRE_USE_ITEM` 返回 true 就取消这次使用、
// `MC_PRE_PICKUP_COLLISION` 返回 true 就不算碰上、`MC_PRE_GET_COLLECTIBLE` 返回整数就替换道具）。
// 这一族必须**逐条收集**再汇总，所以结果不能只有 invoked/failed。
//
// 汇总口径（PC 的 `ModCallbacks.md`）：
//   * `anyTruthy` —— 任一条返回 true。`MC_PRE_*` 的"拦"约定就是它；
//   * `hasInteger` / `integer` —— 道具池按最后一个有效整数覆盖，实参仍保持原值。
//     输入等其他回调按各自契约汇总，不能由“实参不更新”推导“第一条胜出”。
//   * `anyNonNil` —— 任一条返回过非 nil。用来实现"`MC_PRE_GET_COLLECTIBLE` 返回了非 nil
//     ⇒ 跳过 `MC_POST_GET_COLLECTIBLE`"（同一份文档）。
struct CallbackDispatchOutcome {
    bool hasTable{false};
    std::uint32_t invoked{0};
    std::uint32_t failed{0};
    std::uint32_t skippedAffinity{0};
    std::uint32_t skippedFilter{0};
    bool anyNonNil{false};
    bool anyTruthy{false};
    bool hasInteger{false};
    std::int64_t integer{0};
    //: ★ 2026-10-07（批次 390）：**第一条**返回数字的登记的值（口径同 `integer` —— 第一条胜出）。
    //: 为 `MC_INPUT_ACTION` 的 `GET_ACTION_VALUE` 加（覆盖值是 0.0~1.0 的 float）。
    bool hasNumber{false};
    double number{0.0};

    [[nodiscard]] constexpr bool blocked() const noexcept { return anyTruthy; }
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
//
//: 帧边界钩子：每次 `MC_POST_UPDATE` 推进帧号（`ManagedFrameClock::MarkPostUpdateDispatch`）
//: **之后**调用一次，参数 = 新的帧号。默认没有钩子（空指针）。
//:
//: 为什么要有它（批次 381，2026-10-06）：`Input.IsButtonTriggered` / `IsActionTriggered` 的
//: 边沿必须"绑在引擎帧上"——每帧固定时刻采一次、只在那一帧有效（PC 契约 `Input.md:75/107`）。
//: 采样点必须落在"帧号自增之后、回调派发之前"，否则模组在 `MC_POST_UPDATE` 里看不到本帧边沿。
//: 用函数指针钩子（而不是在这里直接调输入层）：`callback_dispatcher` 属于 application 层，
//: 直接调 `interfaces/lua` 会形成反向依赖；钩子由输入层在会话初始化时装一次。
using FrameBoundaryHook = void (*)(std::uint64_t frame) noexcept;

//: 装帧边界钩子（传 nullptr = 卸掉）。会话初始化时由输入层调用，幂等。
void SetFrameBoundaryHook(FrameBoundaryHook hook) noexcept;

class ManagedFrameClock {
public:
    // 每次派发 MC_POST_UPDATE 时调用一次（dispatch 单线程路径，无锁）。
    static void MarkPostUpdateDispatch() noexcept;

    // 新的 Lua 会话开始时归零，保证计数是"自本次加载以来"的帧数。
    static void Reset() noexcept;

    [[nodiscard]] static std::uint64_t Count() noexcept;
};

//: 这一轮要不要**按登记时声明的过滤器**筛（与"调用点说不出过滤值"是两件事，见 `DispatchFiltered`）。
enum class FilterMode : std::uint8_t {
    //: 不筛（`Dispatch` / `DispatchOwner`）：带过滤器的登记照常调用 —— 与改动前完全一致。
    Ignore,
    //: 按过滤器筛（`DispatchFiltered` / `DispatchModifying`）。
    Apply,
};

//: 派发顺序缓冲的容量 = 登记表容量：**永远不会不够**（下标能用 `uint8_t` 表示，下面 `static_assert` 钉住）。
inline constexpr std::size_t kCallbackDispatchOrderCapacity = CallbackRegistry::kCapacity;
static_assert(CallbackRegistry::kCapacity <= 256,
              "派发顺序缓冲用 uint8_t 存下标；容量一旦超过 256 就要改缓冲的元素类型");

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

    // 与 `Dispatch` 相同，但**按过滤器筛**：只有"没带过滤器"或"过滤器恰好等于 `filter`"的
    // 登记会被调用。
    //
    // 为什么保留一个不筛的 `Dispatch`：PC 的 `ModCallbacks.md` 里大多数回调的"可选实参"是 `-`
    // （根本没有过滤语义），而 `Mod:AddCallback` 在那些 id 上传第三个实参是无意义的。对它们
    // 用不筛的路径 = 与改动前完全一致，既不会把"无效过滤参数"变成静默不派发，也不必让每个
    // 派发点都去关心"这个 id 在 PC 上有没有过滤语义"。
    [[nodiscard]] DispatchReport DispatchFiltered(CallbackId id, ThreadAffinity current,
                                                 std::int64_t filter) noexcept;

    // 派发"返回值会影响引擎行为"的那一族回调，并**读回返回值**。
    // 见 `CallbackDispatchOutcome` 的汇总口径。`filter` 语义同 `DispatchFiltered`。
    [[nodiscard]] CallbackDispatchOutcome DispatchModifying(CallbackId id, ThreadAffinity current,
                                                            std::int64_t filter) noexcept;

private:
    //: 收集"这一轮要调用的登记下标"，按 **优先级升序** 排好；同优先级保持登记顺序（稳定排序）。
    //: 返回条数；调用方按 `order[0..count)` 依次取 `AtIndex()` 调用。
    //:
    //: ★ 为什么写在头里内联（而不是 `.cpp` 里的自由函数）：① 它要用私有的 `AffinityMatches`；
    //: ② 门禁 `test_callback_dispatch_counters` 按"**类名限定的函数定义**"数派发入口 ——
    //: 再多一个 `CallbackDispatcher::` 的 `.cpp` 定义会让那条门禁判红（那种红要同步改门禁，
    //: 不是把入口数搞乱）。内联在这里既不进那份名单，也不改变那四个入口的语义。
    //:
    //: ★ 排序为什么是"升序 + 稳定"：PC 的 `CallbackPriority` 是
    //: `IMPORTANT=-200 / EARLY=-100 / DEFAULT=0 / LATE=100`，**数值越小越早执行**；
    //: 同优先级之间 PC 保持登记顺序（这本来也是我们的旧行为，改动只在"有优先级声明时"生效）。
    [[nodiscard]] static std::size_t CollectCallOrder(
        const CallbackRegistry& registry, CallbackId id, bool hasOwner, ModHandle owner,
        ThreadAffinity current, FilterMode filterMode, std::int64_t filter,
        std::uint8_t* order, std::uint32_t* skippedAffinity,
        std::uint32_t* skippedFilter) noexcept {
        std::size_t count = 0;
        for (std::size_t position = 0; position < registry.Count(); ++position) {
            const std::size_t index = registry.DispatchIndexAt(position);
            const CallbackDescriptor* descriptor = registry.AtIndex(index);
            if (descriptor == nullptr || descriptor->id != id) {
                continue;
            }
            if (hasOwner && descriptor->owner != owner) {
                continue;
            }
            if (filterMode == FilterMode::Apply) {
                const std::int64_t declared = registry.FilterAt(index);
                if (declared != CallbackRegistry::kNoCallbackFilter &&
                    filter != CallbackRegistry::kNoCallbackFilter &&
                    declared != -1 && filter != -1 && declared != filter) {
                    if (skippedFilter != nullptr) {
                        ++(*skippedFilter);
                    }
                    continue;
                }
            }
            if (!AffinityMatches(descriptor->affinity, current)) {
                if (skippedAffinity != nullptr) {
                    ++(*skippedAffinity);
                }
                continue;
            }
            order[count++] = static_cast<std::uint8_t>(index);
        }
        // 使用登记时的顺序后再过滤；删除或NaN都不能触发重新排序。
        return count;
    }

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
