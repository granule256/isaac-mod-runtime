#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>

#include "interfaces/lua/runtime_perf.hpp"


// `<atomic>` 现在是无条件引入的：缓存自旋锁与派发/开关标志在生产构建里也要用（见下），
// 不再只服务于 `PROBE_BREAK=1` 的计数器。

namespace isaac::runtime {


// ============================================================================
// 引擎内存可读性：每次访问一次系统调用 → 派发作用域内的区间缓存
// ============================================================================
//
// **问题（2026-09-13 卡顿归因）**：`IsEngineMemoryReadable` 原先对每一次引擎字段读取都调用
// `svcQueryMemory`。真机上那是内核入口（系统调用），而 EID 的"物品信息显示"路径每帧要做
// 上千次这种读取：
//
//   * `entity.Type` / `.Variant` / `.SubType` 这类字段访问 = 句柄 vptr 校验 1 次 + 字段读 1 次；
//   * `entity:GetData()` 一次 ≈ 8–11 次（`ResolveRoom` 三级链 + 容器指纹 + 表描述符 + 出生帧），
//     而 EID 的 `getEntityData` 每次调用都要走两遍 `entity:GetData()`；
//   * `Isaac.FindInRadius` 每帧每玩家一次，对活实体表逐元素还要再各校验一次。
//
// PC 上这些是直接读内存，所以同一条 Lua 代码在 PC 上不卡；在 Switch 上系统调用把帧预算吃掉，
// 表现就是"描述一出现就卡"。
//
// **做法**：`svcQueryMemory` 成功时返回的 `MemoryInfo` 描述的是一个**连续且权限一致**的映射
// 区间，所以整个 `[addr, addr + size)` 都能复用那一次结论。调用方（四个 API 族各自那份
// `IsEngineMemoryReadable`，它们已经持有 libnx 的 `MemoryInfo`）在系统调用成功后把区间登记
// 到这里；下一次落在同一区间里的检查直接命中缓存，不再进内核。
//
// **为什么缓存只在一次受管回调派发内有效**：Lua 只在游戏线程的派发里跑，这段时间内没有
// 任何东西会改页表，所以缓存条目不可能过期 —— 过期窗口为零，比"按时间过期"更安全。
// 出了派发（`EngineGuardLeaveDispatch`）就关闭，任何非派发路径（Mod 加载、绑定解析）仍然
// 每次都做真正的系统调用。
//
// **线程归属（2026-09-13 修正）**：上面那句"派发只在游戏线程上跑"只对**写**这一侧成立。
// 读这一侧不是：宿主插件的线程在绑定解析阶段也会走同一段可读性检查（`EngineGuardProbe*`
// 的原子计数器就是为此加的）。所以缓存、派发标志和 A/B 开关都必须是原子的，否则
// "游戏线程 `Insert`/`Clear` + 插件线程 `Covers`"会撕裂读，让 `Covers()` 对并不可读的区间
// 返回 true。这是本文件 2026-09-13 修掉的数据竞争。
//
// **本头文件不引用任何 libnx**：设备侧 4 个 TU 里已经有 `MemoryInfo`/`Perm_R`，而 vendored
// libnx 与 devkitpro libnx 的 `MemoryInfo` 字段顺序不同（`ipc_refcount`/`device_refcount`
// 互换），把 libnx 头拉进同时包含 `<switch.h>` 的编译单元会直接编译失败。所以这里只做
// "缓存 + 计数"，平台细节留在各自 TU 里（本模块只读 `addr`/`size`/`perm` 三个字段，两种
// 布局下逐字相同）。
// 批次 095：条目改成**原子**（8 字节 relaxed/acquire 读写），配合下面的版本号实现
// "读侧无锁、写侧互斥"。原来读侧每次都要拿一次自旋锁（`exchange` + `store` 两次原子写），
// 而每个字段读都要过 1~2 次可读性检查 ⇒ 每帧上千次原子写全花在"读一个只读区间表"上。
struct EngineReadableRegion {
    std::atomic<std::uintptr_t> begin{0};
    std::atomic<std::uintptr_t> end{0};
};

// 一帧里真正会被触及的映射区间很少（模块映像 + 游戏堆 + 少量独立分配），8 个槽位足够；
// 槽位只做轮转覆盖，不做 LRU —— 命中率对淘汰策略不敏感，而简单实现更容易验证。
constexpr std::size_t kEngineReadableRegionCapacity = 8;

struct EngineReadableRegionCache {
    EngineReadableRegion entries[kEngineReadableRegionCapacity]{};
    std::atomic<std::size_t> count{0};
    std::size_t victim{0};
    //: 版本号：**偶数 = 稳定，奇数 = 正在写**。写侧在改动前后各加一次；
    //: 读侧先读版本、扫区间、再读版本 —— 两次不一致（或读到奇数）就当作**未命中**，
    //: 回退到 `svcQueryMemory` 那条慢路径。**代价只是"这一次慢"，永远不会给出"可读"的错答案。**
    mutable std::atomic<std::uint32_t> version{0};

    // 自旋锁：只保护 `entries` / `count` / `victim` 这三个成员。
    //
    // 为什么需要它：缓存本身只在派发作用域内有效，而派发（`DispatchPostUpdate` /
    // `DispatchPostRender`）只在游戏线程上跑；但**读**这一侧不是 —— 宿主插件的线程在绑定解析
    // 阶段也会走同一段可读性检查。于是"游戏线程在 `Insert`/`Clear`、插件线程同时在 `Covers`"
    // 是真实可达的交错，普通成员在这种交错下会被撕裂读，可能让 `Covers()` 对一个并不可读的
    // 区间返回 true，进而让上层去读无效内存。
    //
    // 临界区只有十几条指令，且绝大多数时候没有竞争（读写都在游戏线程上），所以自旋的成本
    // 远低于它省掉的那次 `svcQueryMemory` 内核入口。
    //
    // **必须是 32 位原子，不能用布尔型 `atomic<bool>`**：本项目的 AArch64 `-Oz` 构建下，
    // 布尔型原子的 `load()` 会生成对 PLT 跳板的调用，而该跳板落在可执行文本边界之后，
    // 真机表现为 `Instruction Abort`、PC 恰为 `__text_end__`（见 `docs/问题与解决记录.md`
    // 的「2026-09-04」布尔原子 PLT 一节）。项目统一改用 32 位 `0/1` 原子。
    mutable std::atomic<std::uint32_t> locked{0};

    void Lock() const noexcept {
        while (locked.exchange(1, std::memory_order_acquire)) {
        }
    }

    void Unlock() const noexcept {
        locked.store(0, std::memory_order_release);
    }

    void Clear() noexcept {
        Lock();
        BeginWrite();
        count.store(0, std::memory_order_relaxed);
        victim = 0;
        EndWrite();
        Unlock();
    }

    // `address + length` 必须已经被调用方做过回绕检查。
    //
    // **读侧完全无锁**（批次 095）：版本号前后一致才认这份快照；否则返回 false ⇒ 上层走
    // `svcQueryMemory` 慢路径（正确性不受影响）。写入 `begin`/`end` 用 release 发布，
    // 读用 acquire，配合版本号即可排除"读到半个区间"。
    bool Covers(std::uintptr_t address, std::size_t length) const noexcept {
        if (length == 0) {
            return false;
        }
        const std::uintptr_t end = address + length;
        const std::uint32_t before = version.load(std::memory_order_acquire);
        if ((before & 1U) != 0U) {
            return false;  // 正在写：这一次当作未命中
        }
        const std::size_t snapshot = count.load(std::memory_order_relaxed);
        bool covered = false;
        for (std::size_t index = 0; index < snapshot && index < kEngineReadableRegionCapacity;
             ++index) {
            const std::uintptr_t begin = entries[index].begin.load(std::memory_order_acquire);
            const std::uintptr_t stop = entries[index].end.load(std::memory_order_acquire);
            if (address >= begin && end <= stop) {
                covered = true;
                break;
            }
        }
        if (version.load(std::memory_order_acquire) != before) {
            return false;  // 扫描期间被改过 ⇒ 这份快照不可信
        }
        return covered;
    }

    void Insert(std::uintptr_t begin, std::uintptr_t end) noexcept {
        if (end <= begin) {
            return;
        }
        Lock();
        BeginWrite();
        const std::size_t used = count.load(std::memory_order_relaxed);
        if (used < kEngineReadableRegionCapacity) {
            entries[used].begin.store(begin, std::memory_order_release);
            entries[used].end.store(end, std::memory_order_release);
            count.store(used + 1, std::memory_order_relaxed);
        } else {
            entries[victim].begin.store(begin, std::memory_order_release);
            entries[victim].end.store(end, std::memory_order_release);
            victim = (victim + 1) % kEngineReadableRegionCapacity;
        }
        EndWrite();
        Unlock();
    }

  private:
    void BeginWrite() const noexcept { version.fetch_add(1, std::memory_order_acq_rel); }
    void EndWrite() const noexcept { version.fetch_add(1, std::memory_order_release); }
};

// 整个模块只有一份：与 `api_sequence_probe.hpp` 同例，函数内 `static` 保证单实例。
inline EngineReadableRegionCache& EngineGuardRegionCache() noexcept {
    static EngineReadableRegionCache cache;
    return cache;
}

// **写**这一侧的区间缓存（2026-09-16 新增）。
//
// 为什么要单独一份、而不复用读缓存：两者回答的是不同的问题。"这一页可读"（`Perm_R`）与
// "这一页可写"（`Perm_W`）在真实映射里不是同一件事 —— 模块映像的代码段与只读数据段就是
// 可读不可写。若把读到的可读区间拿来给写路径放行，`Sprite.Scale = 2` 这类赋值就会去写只读页，
// 真机表现为 `Data Abort`。所以两份缓存各记各的，绝不互相查询。
//
// 类型沿用 `EngineReadableRegionCache`（它就是"区间表 + 自旋锁"），只是实例不同；
// 类型名里的 Readable 是历史命名，不值得为它再引入一个逐字相同的新类型。
inline EngineReadableRegionCache& EngineGuardWritableRegionCache() noexcept {
    static EngineReadableRegionCache cache;
    return cache;
}

// 派发作用域标志：只有派发期间才允许用缓存。
//
// 与缓存同因：写侧是游戏线程，读侧可能来自宿主插件的线程，普通 `bool` 会构成数据竞争。
// 用 32 位 `0/1` 原子而不是布尔型 `atomic<bool>`（AArch64 `-Oz` 下会生成越界的 PLT 跳板，
// 见 `EngineReadableRegionCache::locked` 的说明）。
inline std::atomic<std::uint32_t>& EngineGuardDispatchActive() noexcept {
    static std::atomic<std::uint32_t> active{0};
    return active;
}

// A/B 开关：探针构建在同一会话里对照"有缓存/没缓存"。生产构建恒为 1。
inline std::atomic<std::uint32_t>& EngineGuardCacheEnabledFlag() noexcept {
    static std::atomic<std::uint32_t> enabled{1};
    return enabled;
}

inline bool EngineGuardCacheEnabled() noexcept {
    return EngineGuardCacheEnabledFlag().load(std::memory_order_acquire) != 0;
}

inline void EngineGuardSetCacheEnabled(bool enabled) noexcept {
    EngineGuardCacheEnabledFlag().store(enabled ? 1U : 0U, std::memory_order_release);
    // 切换一定要丢掉旧条目：否则"关掉缓存"的那一相还会命中上一相留下的区间。
    EngineGuardRegionCache().Clear();
    EngineGuardWritableRegionCache().Clear();
}

inline void EngineGuardEnterDispatch() noexcept {
    EngineGuardRegionCache().Clear();
    EngineGuardWritableRegionCache().Clear();
    EngineGuardDispatchActive().store(1U, std::memory_order_release);
}

inline void EngineGuardLeaveDispatch() noexcept {
    EngineGuardDispatchActive().store(0U, std::memory_order_release);
    EngineGuardRegionCache().Clear();
    EngineGuardWritableRegionCache().Clear();
}

// 调用点（设备侧）用法：
//
//     if (!EngineGuardRangeUsable(address, length)) return false;
//     if (EngineGuardLookupCached(address, length)) return true;
//     const std::uint64_t start = EngineGuardSyscallBegin();
//     ... svcQueryMemory ...
//     EngineGuardSyscallEnd(start);
//     ... 区间与权限判定通过后 ...
//     EngineGuardRememberReadable(info.addr, info.addr + info.size);
//
// 这些入口在宿主构建里都不会被调用（宿主分支直接返回 true），仍然是普通 inline 函数，
// 所以不引入任何设备侧符号。

// ============================================================================
// 时间戳：只用 `cntpct_el0`（物理计数器），不使用 `svcGetSystemTick()`
// ============================================================================
// 用系统寄存器而不是 libnx 的 `svcGetSystemTick()`，理由与上面同一条：本头文件不能引用
// libnx（vendored 与 devkitpro 的 `MemoryInfo` 布局不同，把 libnx 头拉进已经包含
// `<switch.h>` 的编译单元会直接编译失败）。`mrs` 不需要头文件。
//
// ★★ 寄存器选择是有真机证据的（批次 085）：**`cntvct_el0`（虚拟计数器）在 EL0 会被禁止读**，
// 那条 `mrs` 一执行就崩（参见 `runtime_perf.hpp` 里的报告与偏移）；可读的是 **`cntpct_el0`**——
// Atmosphère 自己的 `TickManagerImpl` 与 libnx 的 `armGetSystemTick()` 用的都是它。
// 非探针构建恒返回 0 —— 计时只在 A/B 探针里用。
inline std::uint64_t EngineGuardTick() noexcept {
#if defined(EXL_PROBE_BREAK) && defined(__aarch64__)
    std::uint64_t value = 0;
    __asm__ __volatile__("mrs %0, cntpct_el0" : "=r"(value));
    return value;
#else
    return 0;
#endif
}

// Tegra X1 上 tick 频率 = 19.2 MHz（Atmosphère 自己也是硬编码这个值）。
constexpr std::uint64_t kEngineGuardFallbackTicksPerSecond = 19200000ULL;

// 频率**不读寄存器**（批次 085 起，连探针构建也不读）：
// `cntfrq_el0` 是"定时器控制"那一组的寄存器，和计数器本身不是同一个开关；我们**没有**它可读的
// 证据，而它的值也从来不需要问（恒 19.2 MHz）。081 曾把这条读放进启动路径并导致真机进不去，
// 当时归因于"`cntfrq_el0` 会陷入、`cntvct_el0` 可读"——后半句已被 085 的真机崩溃推翻，
// 前半句也没有干净证据。既然不需要，就一律不读（门禁按白名单钉住）。
#if defined(EXL_PROBE_BREAK)
inline std::uint64_t EngineGuardTicksPerSecond() noexcept {
    return kEngineGuardFallbackTicksPerSecond;
}
#endif  // EXL_PROBE_BREAK

#if defined(EXL_PROBE_BREAK)
// ---------------------------------------------------------------------------
// 探针计数（只有 `PROBE_BREAK=1` 的构建才累加）
// ---------------------------------------------------------------------------
// `std::atomic` + relaxed：只读路径在游戏线程上，但绑定解析阶段可能由宿主插件的线程
// 触发同一段检查，普通全局会变成数据竞争；relaxed 原子在这个量级上开销可以忽略。
inline std::atomic<std::uint64_t>& EngineGuardProbeAttempts() noexcept {
    static std::atomic<std::uint64_t> value{0};
    return value;
}

inline std::atomic<std::uint64_t>& EngineGuardProbeSyscalls() noexcept {
    static std::atomic<std::uint64_t> value{0};
    return value;
}

inline std::atomic<std::uint64_t>& EngineGuardProbeCacheHits() noexcept {
    static std::atomic<std::uint64_t> value{0};
    return value;
}

inline std::atomic<std::uint64_t>& EngineGuardProbeSyscallTicks() noexcept {
    static std::atomic<std::uint64_t> value{0};
    return value;
}

// 进一次 `svcQueryMemory`：先把调用次数加一，再取起始时间戳；返回时间戳交给 End 收尾。
inline std::uint64_t EngineGuardSyscallBegin() noexcept {
    EngineGuardProbeSyscalls().fetch_add(1, std::memory_order_relaxed);
    return EngineGuardTick();
}

inline void EngineGuardSyscallEnd(std::uint64_t startTick) noexcept {
    const std::uint64_t endTick = EngineGuardTick();
    if (endTick > startTick) {
        EngineGuardProbeSyscallTicks().fetch_add(endTick - startTick, std::memory_order_relaxed);
    }
}
#else
// ★★ 批次 083：生产构建里这一层**什么都不做**（与 081 之前一致）。
//
// 081 曾经在这里加了"常驻性能面"的累加（计数 + 读 `cntvct_el0`），结果真机上**启动就崩**：
// 崩溃报告 PC = 本函数里的那条 `ldxr/stxr`，`Address: 0` —— 代码是通过**数据 GOT 槽**
// 取那几个新全局的地址的（`adrp x0,#0xc8000; ldr x0,[x0,#0x1e0]`，文件里存的是链接期地址
// `0x3511f8`），而运行时那个槽里的值是 0 ⇒ 对 0 做原子加 ⇒ 空指针解引用。
// 与之对照：模块内**本 TU 可见**的全局（例如 `g_LuaErrorHistory`）编译器直接用
// `adrp/add`，不走 GOT，所以从来没问题。
//
// ⇒ 纪律（写在这里，别再踩）：**跨 TU 的新全局不要放进每帧都走的热路径**；
// 要跨 TU 记账就用"普通函数调用"（PLT，不碰数据 GOT），或者把计数器与使用者放进同一个 TU。
// ★★ 批次 084：记账**走函数调用**（PLT），不引用跨 TU 的变量 —— 见 `runtime_perf.hpp` 的约定。
// 批次 081 就是引用了跨 TU 的全局，编译器经数据 GOT 槽取地址，槽里是 0 ⇒ 启动即崩。
inline std::uint64_t EngineGuardSyscallBegin() noexcept {
#if defined(__SWITCH__)
    return RuntimePerfTick();
#else
    return 0;
#endif
}

inline void EngineGuardSyscallEnd(std::uint64_t startTick) noexcept {
#if defined(__SWITCH__)
    const std::uint64_t endTick = RuntimePerfTick();
    IsaacRuntime_PerfNoteSyscall(endTick > startTick ? endTick - startTick : 0);
#else
    static_cast<void>(startTick);
#endif
}
#endif

// 空地址、长度 0、`address + length` 回绕一律不可用。四个 API 族的 `IsEngineMemoryReadable`
// 都先过这一层，宿主上这就是全部的判定（宿主没有 `svcQueryMemory`，测试里的"引擎内存"是
// 本进程 malloc 出来的伪造块，本来就一定可读）。
inline bool EngineGuardRangeUsable(std::uintptr_t address, std::size_t length) noexcept {
    return address != 0 && length != 0 && address <= UINTPTR_MAX - length;
}

inline bool EngineGuardLookupCached(std::uintptr_t address, std::size_t length) noexcept {
#if defined(EXL_PROBE_BREAK)
    EngineGuardProbeAttempts().fetch_add(1, std::memory_order_relaxed);
#endif
    if (EngineGuardDispatchActive().load(std::memory_order_acquire) == 0 || !EngineGuardCacheEnabled() ||
        !EngineGuardRegionCache().Covers(address, length)) {
        return false;
    }
#if defined(EXL_PROBE_BREAK)
    EngineGuardProbeCacheHits().fetch_add(1, std::memory_order_relaxed);
#endif
    return true;
}

inline void EngineGuardRememberReadable(std::uintptr_t begin, std::uintptr_t end) noexcept {
    if (EngineGuardDispatchActive().load(std::memory_order_acquire) != 0 && EngineGuardCacheEnabled()) {
        EngineGuardRegionCache().Insert(begin, end);
    }
}

// 写侧的两个入口与读侧逐条对应，只是查的是另一份缓存。
//
// 调用点（设备侧）用法：
//
//     if (!EngineGuardRangeUsable(address, length)) return false;
//     if (EngineGuardLookupWritable(address, length)) { 直接写 }
//     ... svcQueryMemory ...
//     ... 判定 Perm_W 通过后 ...
//     EngineGuardRememberWritable(info.addr, info.addr + info.size);
inline bool EngineGuardLookupWritable(std::uintptr_t address, std::size_t length) noexcept {
    return EngineGuardDispatchActive().load(std::memory_order_acquire) != 0 && EngineGuardCacheEnabled() &&
           EngineGuardWritableRegionCache().Covers(address, length);
}

inline void EngineGuardRememberWritable(std::uintptr_t begin, std::uintptr_t end) noexcept {
    if (EngineGuardDispatchActive().load(std::memory_order_acquire) != 0 && EngineGuardCacheEnabled()) {
        EngineGuardWritableRegionCache().Insert(begin, end);
    }
}

} // namespace isaac::runtime
