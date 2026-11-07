#pragma once

// 常驻性能计数：记录 Lua 回调、API 调用、内存查询和分配的耗时。
// 设备侧使用 cntpct_el0；宿主构建的计时值为零。

#include <cstddef>
#include <cstdint>

#if defined(__SWITCH__) && defined(__aarch64__)
#define ISAAC_RUNTIME_PERF_TIMING 1
#endif


// 热路径计数器保存在定义它的编译单元，跨单元通过函数更新。
// 避免直接引用数据 GOT 槽；外部诊断工具仍可通过导出符号读取计数。
extern "C" {
// 记一次引擎内存查询（`svcQueryMemory`）的耗时（tick）；0 表示不计时（宿主构建）。
void IsaacRuntime_PerfNoteSyscall(std::uint64_t ticks);

// 量具的自校准：返回"读一次 `cntpct_el0` 要多少 tick"（1 µs = 19.2 tick）。
//
// 为什么必须有：我们所有耗时都是拿两条 `mrs cntpct_el0` 夹出来的，而每个接口处理器也各读两次。
// 如果这个寄存器在 Switch 上不像看上去那么便宜（例如被陷入模拟），那我们量到的一部分就是
// 量具自身的代价，"谁慢谁快"的结论会整体走样。做法不需要外部时钟：连着读三次，
// 用它们自己算 `(c2 - c0) / 2`。
[[nodiscard]] std::uint64_t IsaacRuntime_PerfTickCostTicks();

// 记一次 API 调用的耗时。`startTick` 是调用方在进入处理器时取的
// `RuntimePerfTick()`；收尾的那一次读在定义侧做（`lua_runtime.cpp`），
// 这样调用点只有"取一次 + 报告一次"，宿主构建下两次都是 0 ⇒ 一个桶都不会建。
//
// `key` 由 `RuntimePerfApiBucketKey()` 算（接口 id + "是否只算引擎调用那一段"）。
// 为什么必须走函数调用：API 处理器住在别的编译单元，跨 TU 记账只能调函数（PLT），
// 直接引用那个数组会走数据 GOT —— 那正是 081 启动崩溃的形状（见上文）。
void IsaacRuntime_PerfNoteApiCall(std::uint64_t key, std::uint64_t startTick);
}

namespace isaac::runtime {

// 时间戳：读 `cntpct_el0`（物理自由运行计数器，Tegra X1 上 19.2 MHz）。
// 非设备构建恒 0 ⇒ 下面所有累加都是"加 0"，不改变任何行为。
//
// 2026-09-19真机崩溃 —— 这里原来是 `cntvct_el0`（虚拟计数器），一执行就崩：
// 报告 `dist/crash-20260919/01789827875_010021c000b6a000.log` 里 `PC = runtime + 0x1d354`，
// 反汇编那一行正是 `mrs x3, cntvct_el0`（守卫 `IsEngineMemoryReadable` 内联展开后的首次读数）。
// 一条 `mrs` 不访问内存，它唯一会出错的方式就是"该寄存器在 EL0 被禁止读"。
//
// 平台自己怎么读时间：Atmosphère 的 `TickManagerImpl`（`runtime/source/nn/os/impl/
// os_tick_manager_impl.os.horizon.hpp:31`）与 libnx 的 `armGetSystemTick()`（`arm/counter.h`）
// 读的都是 `cntpct_el0`，没有一个读 `cntvct_el0`。原因是这两个寄存器由不同的开关控制
// （`CNTKCTL_EL1` 的 `EL0PCTEN` / `EL0VCTEN`）—— Horizon 只放开了物理那一个。
// ⇒ 纪律：计数器只用 `cntpct_el0`，门禁 `test_no_el0_privileged_register_reads` 按白名单钉住。
[[nodiscard]] inline std::uint64_t RuntimePerfTick() noexcept {
#if defined(ISAAC_RUNTIME_PERF_TIMING)
    std::uint64_t value = 0;
    __asm__ __volatile__("mrs %0, cntpct_el0" : "=r"(value));
    return value;
#else
    return 0;
#endif
}

// 每秒多少个 tick。固定用 Tegra X1 的 19.2 MHz，不去读 `cntfrq_el0`。
//
// 频率不需要问寄存器：Tegra X1 上恒为 19.2 MHz（Atmosphère 自己也是硬编码
// `TicksPerSecond = 19'200'000`），读数工具按同一个值换算。
//
// 历史（保留作过程记录）：把"读频率"放进启动路径后真机进不去，082 归因于
// `cntfrq_el0` 在 EL0 会陷入，并顺手写下"`cntvct_el0` 在 EL0 可读（实测可用）"——
// 后半句是错的，085 的真机崩溃证明恰好相反（见上）。081/082 那次崩溃点其实在守卫开头的
// 跨 TU 原子加（083 修），`cntvct` 这个坑一直被挡在前面才没暴露。
[[nodiscard]] inline std::uint64_t RuntimePerfTicksPerSecond() noexcept {
    return 19200000ULL;
}

// ============================================================================
// 按"事件 id + 属主模组"分开的回调耗时桶
// ============================================================================
//
// **为什么要有它**：084/085 的性能面只能回答"回调一共花了多久"——真机实测出来是
// "物品旁边占主线程 22.3%、走开 2.2%"——**但答不出是哪一个回调**。而当时每帧约有 11 次回调
// ⇒ 11 个嫌疑人，不分开就只能继续猜。
//
// 键（见 `RuntimePerfCallbackKey`）就是 `CallbackDescriptor` 头 8 字节的结构化解读，
// 与错误环境里的归属打包是**同一套**：低 32 位 = 事件 id；bit32..47 = `owner.index`；
// bit48..63 = `owner.generation`。按属主也分开，是因为同一个事件 id 可能被多个模组注册
// （EID 与 GoodTrip 都挂 `MC_POST_RENDER`），只按 id 分就答不出"谁贵"。
//
// 安全形状与 085 同源：数组由**定义它的那个 TU**直接寻址（不碰数据 GOT）、不读任何
// EL0 读不到的寄存器、记账只走普通函数调用。
struct RuntimePerfCallbackBucket {
    std::uint64_t key;       // 见 `RuntimePerfCallbackKey`
    std::uint64_t count;     // 0 = 这个槽没被用过（读数工具据此跳过空槽）
    std::uint64_t ticks;     // 累计 tick（19.2 tick = 1 µs）
    std::uint64_t maxTicks;  // 最慢那一次
    // 耗时分布。平均值会被少数极慢的样本整个带偏（我们撞过 95 ms 的尖刺），
    // 只看"平均"分不清"每帧都慢"和"少数几帧特别慢"——而这两种情况的处置完全不同。
    // 四档：`< 250 µs` / `< 1 ms` / `< 5 ms` / `>= 5 ms`。
    std::uint32_t bins[4];
};

// 直方图前三档的上界（tick；19.2 tick = 1 µs ⇒ 19 200 tick = 1 ms），第四档是"不低于最后一档上界"。
//
// 修掉一个 1000 倍的量具 bug：原来后两档写的是 `1 * 19200000` 与
// `5 * 19200000`（那是 1 秒 / 5 秒，因为 19 200 000 tick = 1 s）⇒ 任何"毫秒级"的样本都掉进
// 第二档，`<5ms` 与 `>=5ms` 永远显示 0%。真机上就是这么骗了我们一整轮：
// EID 的 `MC_POST_RENDER` 桶里 `count=5146 / ticks=597083402（≈31 s）/ max=675232（35 ms）`，
// 而 bins 写着 `[1979, 3167, 0, 0]`（"没有一次超过 1 ms"）—— 两者自相矛盾，
// 差点据此得出"它其实不慢"的错结论。（纪律：读数自相矛盾时先查量具。）
inline constexpr std::uint64_t kRuntimePerfBinBounds[3] = {
    250ULL * 19200ULL / 1000ULL,  // 250 µs = 4 800 tick
    1ULL * 19200ULL,              // 1 ms   = 19 200 tick（原写成 19200000 = 1 秒）
    5ULL * 19200ULL,              // 5 ms   = 96 000 tick（原写成 96000000 = 5 秒）
};

// 把一次样本记进直方图（纯函数，宿主可测）。
inline void RecordRuntimePerfBin(std::uint32_t* bins, std::uint64_t spentTicks) noexcept {
    if (bins == nullptr) {
        return;
    }
    for (std::size_t index = 0; index < 3; ++index) {
        if (spentTicks < kRuntimePerfBinBounds[index]) {
            bins[index] += 1;
            return;
        }
    }
    bins[3] += 1;
}

// 桶的个数与每项字节数。读数工具按 `PERF_BUCKET_COUNT × PERF_BUCKET_BYTES` 整块读它们，
// 改这里必须同步 `tools/read_device_state_via_gdb.py` 的同名常量 ——
// 门禁 `runtime/tests/test_perf_callback_buckets.py` 会核对两边一致。
inline constexpr std::size_t kRuntimePerfBucketCount = 64;
inline constexpr std::size_t kRuntimePerfBucketBytes = sizeof(RuntimePerfCallbackBucket);

// 把 `CallbackDescriptor` 的 id 与属主打包成一个键（与错误历史里的 `#N 代M` 同一套口径）。
[[nodiscard]] constexpr std::uint64_t RuntimePerfCallbackKey(
    std::uint32_t id, std::uint16_t ownerIndex, std::uint16_t ownerGeneration) noexcept {
    return static_cast<std::uint64_t>(id)
         | (static_cast<std::uint64_t>(ownerIndex) << 32)
         | (static_cast<std::uint64_t>(ownerGeneration) << 48);
}

// 记一次回调样本：同键累加、顺手更新"最慢一次"；表满时只把溢出次数加一。
// 返回 true 表示这一笔落进了某个桶。
//
// 写成纯函数（只碰传进来的数组）：设备侧由 `lua_runtime.cpp` 把它的数组传进来，
// 宿主门禁直接拿一份栈上数组断言"合并同键 / 取最大 / 表满溢出"三件事 ——
// 这样这些行为有真测试，而不是只靠读代码。
[[nodiscard]] inline bool RecordRuntimePerfCallbackSample(
    RuntimePerfCallbackBucket* buckets, std::size_t capacity,
    std::uint64_t key, std::uint64_t spent, std::uint64_t* overflow) noexcept {
    // 散列探测取代线性扫描。原来每次记账都从第 0 个槽开始逐项比较，
    // 而 API 桶已经扩到 512 个 ⇒ 每次接口调用都可能比较几百次（每帧 646 次调用）。
    // 现在按 key 散列到起点、最多探测 8 次；失败才退回一次完整扫描（正确性不变）。
    // 这个前置守卫不能删：`capacity == 0` 时下一行要取模（除以 0 直接崩；
    //   门禁里"空表不崩"那条用例就是钉它的）。
    if (buckets == nullptr || capacity == 0) {
        return false;
    }
    constexpr std::size_t kProbeLimit = 8;
    const std::size_t start = static_cast<std::size_t>(
        (key * 0x9E3779B97F4A7C15ULL) >> 32) % capacity;
    for (std::size_t step = 0; step < kProbeLimit; ++step) {
        RuntimePerfCallbackBucket& bucket = buckets[(start + step) % capacity];
        if (bucket.count != 0) {
            if (bucket.key == key) {
                bucket.count += 1;
                bucket.ticks += spent;
                RecordRuntimePerfBin(bucket.bins, spent);
                if (spent > bucket.maxTicks) {
                    bucket.maxTicks = spent;
                }
                return true;
            }
            continue;
        }
        // 探测到空槽 ⇒ 这个 key 一定还没进过表：直接在这里落一个新桶。
        bucket.key = key;
        bucket.count = 1;
        bucket.ticks = spent;
        bucket.maxTicks = spent;
        bucket.bins[0] = bucket.bins[1] = bucket.bins[2] = bucket.bins[3] = 0;
        RecordRuntimePerfBin(bucket.bins, spent);
        return true;
    }
    // 探测窗口内没找到：退回一次完整扫描（保证"同一个 key 不会被记两次"）。
    RuntimePerfCallbackBucket* spare = nullptr;
    for (std::size_t index = 0; index < capacity; ++index) {
        RuntimePerfCallbackBucket& bucket = buckets[index];
        if (bucket.count != 0) {
            if (bucket.key == key) {
                bucket.count += 1;
                bucket.ticks += spent;
                RecordRuntimePerfBin(bucket.bins, spent);
                if (spent > bucket.maxTicks) {
                    bucket.maxTicks = spent;
                }
                return true;
            }
            continue;
        }
        if (spare == nullptr) {
            spare = &bucket;
        }
    }
    if (spare == nullptr) {
        if (overflow != nullptr) {
            *overflow += 1;
        }
        return false;
    }
    spare->key = key;
    spare->count = 1;
    spare->ticks = spent;
    spare->maxTicks = spent;
    spare->bins[0] = spare->bins[1] = spare->bins[2] = spare->bins[3] = 0;
    RecordRuntimePerfBin(spare->bins, spent);
    return true;
}

// ============================================================================
// 按 API 接口 分开的耗时桶
// ============================================================================
//
// **为什么还要这一层**：086 把耗时分到了"哪个回调"，真机现场是
// `MC_POST_RENDER [#3 代1]`（EID）物品旁边 1516 µs/帧、走开 256 µs/帧，
// 而**不画任何东西时它仍然要 256 µs** ⇒ 剩下的必须往下分一层：
//   (a) **引擎**每次画字的固定开销（我们改不了，只能少画）、
//   (b) **我们 handler** 的每次调用开销（能优化）、
//   (c) EID 每帧调用的实体查询（`FindInRadius`/`FindByType` 要遍历房间里所有实体，
//       逐字段读都过内存守卫 —— 也在我们这一侧，能优化）。
//
// 键 = 接口 id，另加一个**高位标记**表示"这一笔只算**引擎调用那一段**"（见下），
// 这样 "handler 总耗时 − 引擎调用耗时 = 我们自己的开销" 可以直接算出来，不用再猜。
//
// 桶的存储与 086 的回调桶是**两张独立的表**（回调数量少、API 调用量大，混在一起会把回调挤掉）。
// 2026-09-20：32 个槽远远不够 —— 093 把中央包装铺到全部接口之后，
// 真机上溢出 267 万次（也就是说大多数调用根本没进表，"所有接口一共多少"这个关键问题
// 反而答不出来）。接口 id 有几百个（含保留段），因此扩到 512。
inline constexpr std::size_t kRuntimePerfApiBucketCount = 512;

// ============================================================================
// 内部运算 / 元表处理器用的保留 id 段
// ============================================================================
//
// 这些不是 catalog 里的"接口"（没有 `owner:name`），但它们是**热路径**：
// 实体上的每一次字段读取与每一次方法查找都要过 `Entity.__index`，
// `Vector` 的每次加减/取长度都要过它自己的元表。给它们保留一段 id，
// 读数里就能和普通接口一起排序 —— 谁贵一眼看到。
// 读数工具里有一张同名表（`INTERNAL_API_NAMES`），门禁核对两边的名字与序号。
inline constexpr std::uint32_t kPerfInternalIdBase = 0xFF000000U;
inline constexpr std::uint32_t kPerfInternalIdEntityIndex = kPerfInternalIdBase + 1U;
inline constexpr std::uint32_t kPerfInternalIdEntityPlayerIndex = kPerfInternalIdBase + 2U;
inline constexpr std::uint32_t kPerfInternalIdEntityPickupIndex = kPerfInternalIdBase + 3U;
inline constexpr std::uint32_t kPerfInternalIdVectorIndex = kPerfInternalIdBase + 4U;
inline constexpr std::uint32_t kPerfInternalIdVectorNewIndex = kPerfInternalIdBase + 5U;
inline constexpr std::uint32_t kPerfInternalIdVectorAdd = kPerfInternalIdBase + 6U;
inline constexpr std::uint32_t kPerfInternalIdVectorSub = kPerfInternalIdBase + 7U;
inline constexpr std::uint32_t kPerfInternalIdVectorMul = kPerfInternalIdBase + 8U;
inline constexpr std::uint32_t kPerfInternalIdVectorDiv = kPerfInternalIdBase + 9U;
inline constexpr std::uint32_t kPerfInternalIdVectorUnaryMinus = kPerfInternalIdBase + 10U;
inline constexpr std::uint32_t kPerfInternalIdVectorEqual = kPerfInternalIdBase + 11U;
inline constexpr std::uint32_t kPerfInternalIdVectorToString = kPerfInternalIdBase + 12U;
inline constexpr std::uint32_t kPerfInternalIdVectorCall = kPerfInternalIdBase + 13U;
inline constexpr std::uint32_t kPerfInternalIdColorIndex = kPerfInternalIdBase + 14U;
inline constexpr std::uint32_t kPerfInternalIdEntityRefCall = kPerfInternalIdBase + 17U;

// 键的高位标记：置上表示"这一笔是引擎调用内部那一段"，不是整个处理器。
inline constexpr std::uint64_t kRuntimePerfApiEngineTag = 1ULL << 32;

[[nodiscard]] constexpr std::uint64_t RuntimePerfApiBucketKey(
    std::uint32_t id, bool insideEngineCall = false) noexcept {
    return static_cast<std::uint64_t>(id) | (insideEngineCall ? kRuntimePerfApiEngineTag : 0ULL);
}

// 进入 API 处理器时取一次 tick、离开时记一笔。
//
// 用 RAII 的原因：共享处理器（字段行 / 引擎方法行 / 字体绘制）有十几条 `return`，
// 每条都写一遍收尾既啰嗦又容易漏。用析构函数只需在函数开头放一行。
//
// ⚠️ `luaL_error` 走 `longjmp`，析构不会被调用 —— 出错那一路不会记账。
// 这是可接受的：出错路径本来就罕见，而"报错把这条路径摘掉"之后更该看的是错误历史。
struct ApiCallPerfGuard {
    std::uint64_t key;
    std::uint64_t start;

    explicit ApiCallPerfGuard(std::uint64_t key_) noexcept
        : key(key_), start(RuntimePerfTick()) {}

    ~ApiCallPerfGuard() noexcept {
        IsaacRuntime_PerfNoteApiCall(key, start);
    }

    ApiCallPerfGuard(const ApiCallPerfGuard&) = delete;
    ApiCallPerfGuard& operator=(const ApiCallPerfGuard&) = delete;
};

} // namespace isaac::runtime
