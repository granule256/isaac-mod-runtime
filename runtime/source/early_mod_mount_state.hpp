#pragma once

#include <cstdint>

// ============================================================================
// "让模组那一层早于引擎第一次读共享路径"这一段的常驻状态面
// ============================================================================
//
// **要补的那一环**：引擎自己在 `Game::Init → Minimap::Init` 里读共享路径
// （`ANM2::Load("gfx/ui/minimap1.anm2")`）；那一刻若无模组挂载点，引擎把**本体那份**
// 读进动画缓存，模组自带的那份永远赢不了（真机：`sh1 = 11`、minimapi 两行红字）。
// 取证：`docs/分析-模组覆盖本体资源那一环该补在哪一刻-20261005.md`。
//
// **两条修法，本状态面横跨它们**（字段就是从两批的做法里长出来的，都保留在这里）：
//
//   * 批次 370（2026-10-05，**已作废**）：在 `ModuleWorker` 里、那段 5 秒 `svcSleepThread`
//     **之前**，由**我们自己的 worker 线程**去"读清单 + 注册挂载点"。⇒ 真机 3/3 崩：
//     那个窗口里游戏模块**还在重定位**（`.rela.plt` 的导入槽尚未填），我们一调引擎的文件 API
//     就 `br x17`（x17 = 一个没加基址的模块内偏移）⇒ `Instruction Abort`。
//     定案见 `docs/分析-早读模组文件为何崩-机制分析-20261005.md`、产物 `dist/crash-20261005-1355/`。
//
//   * 批次 371（2026-10-05，**当前**）：① 早期那一段**只做纯内存的事**（认游戏模块 → 核守卫 →
//     确认落在可执行区间 → 给 `Game::Init` **装入口中继**；不读文件、不调任何引擎函数）；
//     ② **回调里**（游戏线程、`Game::Init` 原函数之前）才"读清单 + 注册挂载点"（复用 370 写好的
//     那套实体 `MountModsBeforeHeavyWork`）。⇒ 引擎调用 `Game::Init` 时重定位早已完成，
//     且我们的回调**按构造**排在 `Minimap::Init` 读那两个 anm2 之前。
//
// **这件状态面回答的问题**（一次读数就能问清"我们赶上引擎没有"）：
//   * 我们自己的线程是在哪一刻进的 worker、哪一刻才开始那 5 秒等待（两数相减 = 前置步骤花了多久）；
//   * 游戏模块在什么时刻被我们认出（0 = 那一步没走到）；
//   * `Game::Init` 的入口中继**装上没有**（`relayInstalledTicks` + `relayInstallFailure`）；
//   * 它**被调了几次**（`relayCallbackFired` ∈ {0, ≥1} 就是那条"赶上了没有"的第一判据）；
//   * 我们一共挂了几次模组挂载点、失败几次、挂完引擎那张表里有没有 `isaac_mods` 前缀。
//
// ## 三条纪律（都不是风格问题）
//
//   1. **必须外部链接、定义必须放在匿名命名空间之外**：读数工具
//      `tools/read_device_state_via_gdb.py` 按符号名直读（放进匿名命名空间的话符号名会变成
//      `_ZN12_GLOBAL__N_1L…` 那一串；门禁 `runtime/tests/test_early_mod_mount.py` 也钉着这一条）；
//   2. **字段顺序即内存顺序，加字段只能往后加**：删字段/插字段会让读数整段错位，
//      而错位在读数里表现为"某几格莫名非 0"，比报错难查得多。
//      ★ **改动必须同步 `tools/read_device_state_via_gdb.py`**（那里有同一条注释）。
//   3. **跨线程可见性**：本结构体的**时间轴/计数大多由我们自己的 worker 线程写**，而
//      `relayCallbackFired` / `callbackFirstFiredTicks` / `mounts*` 由**游戏线程的中继回调**写
//      （370 那版全在 worker 线程；371 起多了一条游戏线程写入方）。**两方写的是不同字段**
//      （不同内存位置）⇒ 不构成数据竞争；读数只在游戏跑起来之后读，此时两边都已落定。
//
// ## 时间戳口径
//
// 全部用 `cntpct_el0`（`isaac::runtime::RuntimePerfTick()`；Tegra X1 上 **19.2 MHz** 的
// **物理**自由运行计数器）取的 **tick**。**不用** `cntvct_el0` / `cntfrq_el0` —— 那两个在 EL0
// 读不到，一执行就崩（批次 085 的真机崩溃；门禁 `test_no_el0_privileged_register_reads` 钉着）。
// 换算：1 ms = 19'200 tick；读数工具按同一个值换算成毫秒。
// **0 = "那一步没有走到"**（不是"发生在 tick 0"）—— 于是"走到哪一步"一眼可见。
namespace isaac::runtime::earlymount {

struct EarlyModMountState {
    // ---- 时间轴（tick，见上面的口径）----
    std::uint64_t workerEnteredTicks;        // [0] worker 线程进入 `ModuleWorker` 的那一刻
    std::uint64_t delayStartTicks;           // [1] 那 5 秒等待**开始**的那一刻（= 前置步骤结束）
    std::uint64_t gameModuleFoundTicks;      // [2] `ScanTargetModule()` 认出游戏模块的那一刻
    std::uint64_t relayInstalledTicks;       // [3] `Game::Init` 入口中继**装成**的那一刻（0 = 没装成）
    std::uint64_t callbackFirstFiredTicks;   // [4] 中继回调**第一次**被引擎调用的那一刻（0 = 从没被调）
    // ---- 计数 ----
    std::uint32_t relayInstallAttempted;     // [5] 走到"装中继"那一步了吗（0 = 没认出模块/没走到）
    std::uint32_t relayInstallFailure;       // [6] `TryInstallEntryRelay` 的失败码（0 = 成功；码表见 relay/entry_relay.hpp）
    std::uint32_t relayCallbackFired;        // [7] 中继回调被调次数（游戏线程每次 `Game::Init` +1）
    std::uint32_t mountsAttempted;           // [8] 回调里 `RegisterMod` 调了几次（0 = 那一次没挂成）
    std::uint32_t mountsFailed;              // [9] 其中返回失败的有几次
    std::uint32_t mountListHadModPrefix;     // [10] 挂完之后读引擎那张表：有 `isaac_mods` 前缀 = 1
    // ★★★ 批次 385（2026-10-06）：**前置步骤里"早装资源类中继"的结果**（两条 =
    //   `ContentGetMountedFilePath` + `Anm2Load`）。
    //
    //   为什么必须让它在读数里可见：第一版早装**静默失败**了（`TryInstallEntryRelayEarly` 返回 false，
    //   按设计不抛错），而读数上只表现为"`ANM2` 中继首次被调仍然很晚（晚 `Game::Init` 6.4 秒）"
    //   ⇒ 白改一轮才发现 —— 起因就是"少了 `RegisterEntryRelayCallbacks()` 那一步
    //   ⇒ 绑定表里 callback 还是空 ⇒ 判定拒绝"。
    //   ⇒ 教训与批次 365 同一条：**没有判据的改动等于没改**（"装上了"与"装失败"必须能分开读）。
    //
    //   背景（定案读数）：`ANM2` 中继首次被调比 `Game::Init` **晚 6.4~6.5 秒**，
    //   而引擎读 `gfx/ui/minimap1.anm2` 就在 `Game::Init` 里 ⇒ 那次读没走我们的中继 ⇒ 模组画红字。
    std::uint32_t earlyResourceRelaysAttempted;  // [11] 试了几条（0 = 没走到 / 没认出模块）
    std::uint32_t earlyResourceRelaysInstalled;  // [12] 真装成几条（**小于 attempted = 早装失败**）
};

//: 状态面本体（**外部链接**，读数工具按符号名读；字段顺序必须与上面结构体一致）。
extern EarlyModMountState g_EarlyMountState;

}  // namespace isaac::runtime::earlymount
