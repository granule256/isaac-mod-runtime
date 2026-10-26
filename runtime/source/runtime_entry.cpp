#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 6 || EXL_DIAGNOSTIC_STAGE == 7 || EXL_DIAGNOSTIC_STAGE == 8 || EXL_DIAGNOSTIC_STAGE == 9 || EXL_DIAGNOSTIC_STAGE == 11 || EXL_DIAGNOSTIC_STAGE == 12 || EXL_DIAGNOSTIC_STAGE == 13 || EXL_DIAGNOSTIC_STAGE == 14 || EXL_DIAGNOSTIC_STAGE == 15 || EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17 || EXL_DIAGNOSTIC_STAGE == 45 || EXL_DIAGNOSTIC_STAGE == 48 || EXL_DIAGNOSTIC_STAGE == 88 || EXL_DIAGNOSTIC_STAGE == 89 || EXL_DIAGNOSTIC_STAGE == 102 || EXL_DIAGNOSTIC_STAGE == 104 || EXL_DIAGNOSTIC_STAGE == 108 || EXL_DIAGNOSTIC_STAGE == 109 || EXL_DIAGNOSTIC_STAGE == 110 || EXL_DIAGNOSTIC_STAGE == 112 || EXL_DIAGNOSTIC_STAGE == 118 || EXL_DIAGNOSTIC_STAGE == 127 || EXL_DIAGNOSTIC_STAGE == 128

#include "main_module_load_hook.hpp"
#include "lib/util/sys/modules.hpp"
#include "lib.hpp"

#include "module_finder.hpp"
#include "hook_manager.hpp"
// 批次 370：提前挂载那一段的状态面，以及"读一个 GOT 槽"要用的引擎内存访问层
// （`engine_memory::ReadAt` —— 不新增裸 `reinterpret_cast`，见门禁
// `test_no_new_raw_engine_access`）。
#include "early_mod_mount_state.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
// 批次 370：挂完之后"读一次引擎那张挂载点表"的入口（读法与 8 字节元素口径都在那个 TU 里，
// 2026-10-05 用反汇编 + 设备实测定案 —— 不在这里再抄一份）。
#include "anm2_load_override_hook.hpp"
// 批次 371（2026-10-05）：① 在早期那一段装 `Game::Init` 的零占洞入口中继；② 回调里把"回退入口"
// 当函数调（走引擎调用层，不新增裸 `reinterpret_cast` —— 与既有的 `engine_memory::ReadAt` 同一条理由）。
#include "relay/entry_relay.hpp"
// 批次 385（2026-10-06）：把"资源类"两条入口中继**提前装**的能力（`TryInstallEntryRelayEarly`）。
// 它必须与"装 `Game::Init` 入口中继"同处一个窗口（worker 的前置步骤）—— 理由见本文件
// `RunEarlyModMountPrelude` 里的第 ④ 段（真机读数：不提前装 ⇒ 引擎最初那次读读不到模组那份）。
#include "infrastructure/relay/entry_relay_hook_adapter.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "fatal_forensics.hpp"
#include "lua_runtime.hpp"
#include "interfaces/lua/os_api.hpp"
#include "manager_update_hook_audit.hpp"
#include "persistence_event_journal.hpp"
#include "runtime_constants.hpp"
#include "runtime_state.hpp"
#include "test_run_observer.hpp"
#if defined(EXL_LAYERED_RUNTIME)
#include "bootstrap/runtime_bootstrap.hpp"
#include "saltynx_self_journal.hpp"
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
#include "stage14_diagnostic.hpp"
#endif

#include "lib/nx/kernel/svc.h"
#include "lib/nx/kernel/virtmem.h"

#include <atomic>
#include <cstring>

namespace {
std::atomic<RuntimeState> g_RuntimeState{RuntimeState::Cold};
enum class StartupStatus : u32 {
    TitleOk,
    TitleQueryFailed,
    TitleMismatch,
};
std::atomic<StartupStatus> g_StartupStatus{StartupStatus::TitleQueryFailed};
alignas(0x1000) u8 g_WorkerStack[0x4000];
Handle g_WorkerHandle = INVALID_HANDLE;

#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 6
constexpr u32 kStartupProbeStage6RuntimeStateRecorded = 1U << 0;
constexpr u32 kStartupProbeStage6HookInitialized = 1U << 1;
constexpr u32 kStartupProbeStage6TitleOk = 1U << 2;
constexpr u32 kStartupProbeStage6ThreadCreated = 1U << 3;
constexpr u32 kStartupProbeStage6WorkerDispatched = 1U << 4;
std::atomic<u32> g_StartupProbeStage6Gates{0};

extern "C" NORETURN void ReportStartupProbeWorkerGate(u32 gates);

void MarkStartupProbeStage6Gate(u32 gate) {
    g_StartupProbeStage6Gates.fetch_or(gate, std::memory_order_release);
}

NORETURN void StartupProbeWorker(void*) {
    MarkStartupProbeStage6Gate(kStartupProbeStage6WorkerDispatched);
    ReportStartupProbeWorkerGate(
        g_StartupProbeStage6Gates.load(std::memory_order_acquire));
}
#endif

#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 7
constexpr u32 kStartupProbeStage7RuntimeStateRecorded = 1U << 0;
constexpr u32 kStartupProbeStage7HookInitialized = 1U << 1;
constexpr u32 kStartupProbeStage7TitleOk = 1U << 2;
constexpr u32 kStartupProbeStage7ThreadCreated = 1U << 3;
constexpr u32 kStartupProbeStage7WorkerDispatched = 1U << 4;
std::atomic<u32> g_StartupProbeStage7Gates{0};

extern "C" NORETURN void ReportStartupProbeWorkerGate(u32 gates);
extern "C" void RunStartupProbeStage7WorkerGate(u32 gates);

void MarkStartupProbeStage7Gate(u32 gate) {
    g_StartupProbeStage7Gates.fetch_or(gate, std::memory_order_release);
}
#endif

#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
constexpr u32 kStartupProbeStage8WorkerEntered = 1U << 0;
constexpr u32 kStartupProbeStage8TitleOk = 1U << 1;
constexpr u32 kStartupProbeStage8ScanStarted = 1U << 2;
constexpr u32 kStartupProbeStage8ModuleFound = 1U << 3;
constexpr u32 kStartupProbeStage8InstallSucceeded = 1U << 4;
constexpr u32 kStartupProbeStage8LuaInitialized = 1U << 5;
std::atomic<u32> g_StartupProbeStage8Gates{0};

extern "C" void RunStartupProbeStage8WorkerGate(u32 gates);

void MarkStartupProbeStage8Gate(u32 gate) {
    g_StartupProbeStage8Gates.fetch_or(gate, std::memory_order_release);
}

NORETURN void ReportStartupProbeStage8Gates() {
    TestRunObserver::Mark(TestRunObserver::State::FinalReportEntered,
                          g_StartupProbeStage8Gates.load(std::memory_order_acquire));
    RunStartupProbeStage8WorkerGate(
        g_StartupProbeStage8Gates.load(std::memory_order_acquire));
    UNREACHABLE;
}
#endif

#if !defined(EXL_DIAGNOSTIC_STAGE) && defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || \
     (EXL_STARTUP_PROBE_STAGE != 6 && EXL_STARTUP_PROBE_STAGE != 8))
constexpr u32 kManagerHookAuditSampleLimit = 300;
#endif

#if !defined(EXL_DIAGNOSTIC_STAGE) && defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || \
     (EXL_STARTUP_PROBE_STAGE != 6 && EXL_STARTUP_PROBE_STAGE != 8))
// ISAAC_PI: default manifest/Update hook installation failed before any callback can run.
constexpr u64 kTraceDefaultInstallFailureMagic = 0x49534141435F5049ULL;

NORETURN void ReportTraceDefaultInstallFailure(DefaultManifestInstallResult result) {
    svcBreak(BreakReason_User, kTraceDefaultInstallFailureMagic, static_cast<u32>(result));
    svcExitProcess();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
constexpr u64 kStage15FailureMagic = 0x49534141435F5246ULL;

NORETURN void ReportStage15Failure(u32 status) {
    svcBreak(BreakReason_User, kStage15FailureMagic, (15ULL << 32) | status);
    svcExitProcess();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
constexpr u64 kStage16FailureMagic = 0x49534141435F4D46ULL;

NORETURN void ReportStage16Failure(u32 status) {
    svcBreak(BreakReason_User, kStage16FailureMagic, (16ULL << 32) | status);
    svcExitProcess();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
constexpr u64 kStage17FailureMagic = 0x49534141435F4D46ULL;

NORETURN void ReportStage17Failure(u32 status) {
    svcBreak(BreakReason_User, kStage17FailureMagic, (17ULL << 32) | status);
    svcExitProcess();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
constexpr u64 kStage45FailureMagic = 0x49534141435F4D46ULL;

NORETURN void ReportStage45Failure(u32 status) {
    svcBreak(BreakReason_User, kStage45FailureMagic, (45ULL << 32) | status);
    svcExitProcess();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48
constexpr u64 kStage48FailureMagic = 0x49534141435F4D46ULL;

NORETURN void ReportStage48Failure(u32 status) {
    svcBreak(BreakReason_User, kStage48FailureMagic, (48ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
constexpr u64 kStage88FailureMagic = 0x49534141435F4946ULL;

NORETURN void ReportStage88Failure(u32 status) {
    svcBreak(BreakReason_User, kStage88FailureMagic, (88ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
constexpr u64 kStage89FailureMagic = 0x49534141435F4946ULL;

NORETURN void ReportStage89Failure(u32 status) {
    svcBreak(BreakReason_User, kStage89FailureMagic, (89ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
constexpr u64 kStage102FailureMagic = 0x49534141435F4346ULL;

NORETURN void ReportStage102Failure(u32 status) {
    svcBreak(BreakReason_User, kStage102FailureMagic, (102ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
constexpr u64 kStage104FailureMagic = 0x49534141435F4B46ULL;

NORETURN void ReportStage104Failure(u32 status) {
    svcBreak(BreakReason_User, kStage104FailureMagic, (104ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
constexpr u64 kStage108FailureMagic = 0x49534141435F4C46ULL;

NORETURN void ReportStage108Failure(u32 status) {
    svcBreak(BreakReason_User, kStage108FailureMagic, (108ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
constexpr u64 kStage109FailureMagic = 0x49534141435F5246ULL;

NORETURN void ReportStage109Failure(u32 status) {
    svcBreak(BreakReason_User, kStage109FailureMagic, (109ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
constexpr u64 kStage127FailureMagic = 0x49534141435F5346ULL;

NORETURN void ReportStage127Failure(u32 status) {
    svcBreak(BreakReason_User, kStage127FailureMagic, (127ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
constexpr u64 kStage128FailureMagic = 0x49534141435F5346ULL;

NORETURN void ReportStage128Failure(u32 status) {
    svcBreak(BreakReason_User, kStage128FailureMagic, (128ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
constexpr u64 kStage110FailureMagic = 0x49534141435F5346ULL;

NORETURN void ReportStage110Failure(u32 status) {
    svcBreak(BreakReason_User, kStage110FailureMagic, (110ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 112
constexpr u64 kStage112FailureMagic = 0x49534141435F4446ULL;

NORETURN void ReportStage112Failure(u32 status) {
    svcBreak(BreakReason_User, kStage112FailureMagic, (112ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
constexpr u64 kStage118FailureMagic = 0x49534141435F4646ULL;

NORETURN void ReportStage118Failure(u32 status) {
    svcBreak(BreakReason_User, kStage118FailureMagic, (118ULL << 32) | status);
    svcExitProcess();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 7
constexpr u64 kStage7FailureMagic = 0x49534141435F4C46ULL;

NORETURN void ReportStage7Failure(u32 status) {
    svcBreak(BreakReason_User, kStage7FailureMagic, (7ULL << 32) | status);
    svcExitProcess();
}

NORETURN void ReportStage7LuaInitializationFailure(LuaRuntime::LuaInitResult result) {
    switch (result) {
    case LuaRuntime::LuaInitResult::StateCreateFailed:
        ReportStage7Failure(1);
    case LuaRuntime::LuaInitResult::RuntimePreparationMemoryFailed:
        ReportStage7Failure(LuaRuntime::PreparationFailureDetail());
    case LuaRuntime::LuaInitResult::RuntimePreparationFailed:
        ReportStage7Failure(LuaRuntime::PreparationFailureDetail());
    case LuaRuntime::LuaInitResult::ScriptLoadFailed:
        ReportStage7Failure(2);
    case LuaRuntime::LuaInitResult::ScriptRunFailed:
        ReportStage7Failure(3);
    case LuaRuntime::LuaInitResult::MissingPostUpdateCallback:
        ReportStage7Failure(4);
    case LuaRuntime::LuaInitResult::Success:
        UNREACHABLE;
    }
    UNREACHABLE;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
constexpr u64 kStage8FailureMagic = 0x49534141434D464CULL;

NORETURN void ReportStage8Failure(u32 status) {
    svcBreak(BreakReason_User, kStage8FailureMagic, (8ULL << 32) | status);
    svcExitProcess();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
constexpr u64 kStage9FailureMagic = 0x495341414352464CULL;

NORETURN void ReportStage9Failure(u32 status) {
    svcBreak(BreakReason_User, kStage9FailureMagic, (9ULL << 32) | status);
    svcExitProcess();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
NORETURN void ReportStage11Failure(u32 status) {
    svcBreak(BreakReason_User, 0x495341414346464CULL, (11ULL << 32) | status);
    svcExitProcess();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
NORETURN void ReportStage12Failure(u32 status) {
    svcBreak(BreakReason_User, 0x4953414143454C46ULL, (12ULL << 32) | status);
    svcExitProcess();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
constexpr u64 kStage14FailureMagic = 0x49534141435F4746ULL;

NORETURN void ReportStage14Failure(Stage14Diagnostic::Stage14Failure failure) {
    svcBreak(BreakReason_User, kStage14FailureMagic,
             (14ULL << 32) | static_cast<u32>(failure));
    svcExitProcess();
}

NORETURN void ReportStage14LuaInitializationFailure(LuaRuntime::LuaInitResult result) {
    if (result == LuaRuntime::LuaInitResult::Success) {
        UNREACHABLE;
    }
    ReportStage14Failure(Stage14Diagnostic::Stage14Failure::LuaInitializationFailed);
}
#endif

void CloseWorkerHandle() {
    if (g_WorkerHandle != INVALID_HANDLE) {
        svcCloseHandle(g_WorkerHandle);
        g_WorkerHandle = INVALID_HANDLE;
    }
}

void SetRuntimeState(const RuntimeContext& context) {
    const RuntimeState current = g_RuntimeState.load(std::memory_order_acquire);
    g_RuntimeState.store(Step(current, context), std::memory_order_release);
}

// 加载完成后的纯内存准备定义在worker后；生产从Main加载钩调用，诊断形状保持原入口。
#if !defined(EXL_DIAGNOSTIC_STAGE)
bool PrepareEarlyResourcesAfterLoad() noexcept;
#endif

// 批次 371（2026-10-05）：`Game::Init` 入口中继的回调。定义在本 TU 末尾的**全局作用域**
// （`extern "C"` ⇒ 外部链接，也就不会因为"只在下面那段里被取过地址"而报 `-Wunused-function`）。
// 提前准备要把这个回调交给入口中继，故先声明。
extern "C" void EntryRelayGameInitCallback(void* self);

#if !defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 6
void ModuleWorker(void*) {
    // 只记录worker时间；资源准备由真实LoadModule完成通知负责，避免定时轮询漏过目标。
    isaac::runtime::earlymount::g_EarlyMountState.workerEnteredTicks = isaac::runtime::RuntimePerfTick();
    // 那 5 秒等待**开始**的那一刻（= 上面那段前置步骤结束）。与 `workerEnteredTicks` 相减
    // 就是"我们为自己的前置步骤花了多久"（读数工具按 19.2 MHz 换算成毫秒）。
    isaac::runtime::earlymount::g_EarlyMountState.delayStartTicks =
        isaac::runtime::RuntimePerfTick();
    // 把"我们自己的启动期动作"（扫内存找游戏模块、装挂点、自校验、读模组文件）推迟到
    // "系统装载游戏本体模块"那个窗口之后再开始。默认 0：`EXL_WORKER_STARTUP_DELAY_SECONDS`
    // 未定义时下面是编译期常量 0，整个分支被优化掉 —— 生产形状与门禁都不变；
    // 真机实验包由 `WORKER_STARTUP_DELAY_SECONDS=5` 打开（0 以外的取值经 Makefile 校验）。
    // 为什么等在这里而不是入口：入口被游戏**同步等待**，在入口等等于给开机加秒数。
    // 背景、实测数字与代价见 `docs/问题与解决记录.md` 2026-09-16 续十六 与 `docs/改动日志-20260916.md`。
    if (kWorkerStartupDelayNanoseconds > 0) {
        svcSleepThread(kWorkerStartupDelayNanoseconds);
    }
#if defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
    PersistenceEventJournal::MarkAndFlush(
        PersistenceEventJournal::Event::WorkerEntered);
#endif
    TestRunObserver::Mark(TestRunObserver::State::ModuleWorkerEntered);
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 7
    MarkStartupProbeStage7Gate(kStartupProbeStage7WorkerDispatched);
    RunStartupProbeStage7WorkerGate(
        g_StartupProbeStage7Gates.load(std::memory_order_acquire));
#endif
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
    MarkStartupProbeStage8Gate(kStartupProbeStage8WorkerEntered);
#endif
#if !defined(EXL_DIAGNOSTIC_STAGE) && defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 8)
    ManagerUpdateHookAudit::RecordWorkerState(ManagerUpdateHookAudit::WorkerState::Started, 0);
    ManagerUpdateHookAudit::Flush();
#endif
    const StartupStatus startup = g_StartupStatus.load(std::memory_order_acquire);
    TestRunObserver::Mark(TestRunObserver::State::TitleStateRead,
                          static_cast<std::uint32_t>(startup));
    if (startup != StartupStatus::TitleOk) {
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
        ReportStartupProbeStage8Gates();
#else
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
        ReportStage6Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
        ReportStage8Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
        ReportStage9Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
        ReportStage11Failure(3);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
        ReportStage12Failure(3);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
        ReportStage13Failure(3);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
        ReportStage14Failure(Stage14Diagnostic::Stage14Failure::StartupFailed);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
        ReportStage15Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
        ReportStage16Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
        ReportStage17Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
        ReportStage45Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
        ReportStage88Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
        ReportStage89Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
        ReportStage102Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
        ReportStage104Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
        ReportStage108Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
        ReportStage109Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
        ReportStage110Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 112
        ReportStage112Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
        ReportStage118Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
        ReportStage127Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
        ReportStage128Failure(1);
#endif
        svcExitThread();
#endif
    }
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
    MarkStartupProbeStage8Gate(kStartupProbeStage8TitleOk);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && \
    (EXL_DIAGNOSTIC_STAGE == 11 || EXL_DIAGNOSTIC_STAGE == 12 || EXL_DIAGNOSTIC_STAGE == 13)
    bool stage11CandidateSeen = false;
#endif
#if !defined(EXL_DIAGNOSTIC_STAGE) && defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 8)
    ManagerUpdateHookAudit::RecordWorkerState(ManagerUpdateHookAudit::WorkerState::Scanning, 0);
#endif
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
    MarkStartupProbeStage8Gate(kStartupProbeStage8ScanStarted);
#endif
    for (u32 attempt = 0; attempt < kTargetModuleScanAttemptLimit; ++attempt) {
#if !defined(EXL_DIAGNOSTIC_STAGE) && defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 8)
        ManagerUpdateHookAudit::RecordScanAttempt(attempt + 1);
        ManagerUpdateHookAudit::Flush();
#endif
        TestRunObserver::Mark(TestRunObserver::State::ModuleScanEntered, attempt + 1);
#if !defined(EXL_DIAGNOSTIC_STAGE)
        // 目标加载和早期资源挂点完成后才进入常规安装，避免与加载线程并发发布中继。
        if (!isaac::runtime::MainModuleLoadPreparationReady()) {
            svcSleepThread(kTargetModuleScanIntervalNanoseconds);
            continue;
        }
#endif
        const TargetModuleScanResult scan = ScanTargetModule();
        TestRunObserver::Mark(TestRunObserver::State::ModuleScanReturned,
                              static_cast<std::uint32_t>(scan.status));
        if (scan.status == TargetModuleScanStatus::BuildMismatch && scan.module.has_value()) {
            SetRuntimeState({.buildMismatch = true});
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
            ReportStartupProbeStage8Gates();
#else
#if !defined(EXL_DIAGNOSTIC_STAGE) && defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 8)
            ManagerUpdateHookAudit::RecordWorkerState(ManagerUpdateHookAudit::WorkerState::BuildMismatch, 0);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
            ReportStage6Failure(3);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
            ReportStage8Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
            ReportStage9Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
            ReportStage11Failure(4);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
            ReportStage12Failure(4);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
            ReportStage13Failure(4);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
            ReportStage14Failure(Stage14Diagnostic::Stage14Failure::InstallFailed);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
            ReportStage15Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
            ReportStage16Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
            ReportStage17Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
            ReportStage45Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
            ReportStage88Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
            ReportStage89Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
            ReportStage102Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
            ReportStage104Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
            ReportStage108Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
            ReportStage109Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
            ReportStage110Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 112
            ReportStage112Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
            ReportStage118Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
            ReportStage127Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
            ReportStage128Failure(1);
#endif
            svcExitThread();
#endif
        }
        if (scan.status == TargetModuleScanStatus::Found && scan.module.has_value()) {
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
            MarkStartupProbeStage8Gate(kStartupProbeStage8ModuleFound);
#endif
#if !defined(EXL_DIAGNOSTIC_STAGE) && defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 8)
            ManagerUpdateHookAudit::RecordWorkerState(ManagerUpdateHookAudit::WorkerState::Found, 0);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
            const Stage11InstallResult install = TryInstallRomfsSentinelDiagnostic(*scan.module);
            if (install == Stage11InstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
                svcExitThread();
            } else {
                stage11CandidateSeen = true;
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
            const Stage12InstallResult install = TryInstallRomfsLuaDiagnostic(*scan.module);
            if (install == Stage12InstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
                svcExitThread();
            } else {
                stage11CandidateSeen = true;
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
            const Stage13InstallResult install = TryInstallManifestRequireDiagnostic(*scan.module);
            if (install == Stage13InstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
                svcExitThread();
            } else {
                stage11CandidateSeen = true;
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
            const LoadConfigsResetDiagnosticInstallResult install =
                TryInstallManagerLoadConfigsResetDiagnostic(*scan.module);
            if (install == LoadConfigsResetDiagnosticInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                switch (install) {
                case LoadConfigsResetDiagnosticInstallResult::LoadConfigsInstructionOrRelayMismatch:
                case LoadConfigsResetDiagnosticInstallResult::RelaySlotNotEmpty:
                case LoadConfigsResetDiagnosticInstallResult::RelayPublishFailed:
                    ReportStage9Failure(2);
                case LoadConfigsResetDiagnosticInstallResult::ResetInstructionOrMappingMismatch:
                    ReportStage9Failure(3);
                case LoadConfigsResetDiagnosticInstallResult::Success:
                    UNREACHABLE;
                }
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
            const LoadConfigsDiagnosticInstallResult install =
                TryInstallManagerLoadConfigsDiagnostic(*scan.module);
            if (install == LoadConfigsDiagnosticInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                switch (install) {
                case LoadConfigsDiagnosticInstallResult::InstructionOrRelayMismatch:
                    ReportStage8Failure(2);
                case LoadConfigsDiagnosticInstallResult::RelaySlotNotEmpty:
                case LoadConfigsDiagnosticInstallResult::RelayPublishFailed:
                    ReportStage8Failure(3);
                case LoadConfigsDiagnosticInstallResult::Success:
                    UNREACHABLE;
                }
            }
#else
#if !defined(EXL_DIAGNOSTIC_STAGE)
            // Render and collectible interception are optional capabilities. The
            // Update hook is the only prerequisite for loading a manifest Mod;
            // missing optional IPS patches must not disable generic callbacks.
            // The layered build installs all three through HookInstallService
            // inside TryInstallDefaultManifestMod, so it must not install the
            // optional hooks twice.
#if !defined(EXL_LAYERED_RUNTIME)
            static_cast<void>(TryInstallManagerRenderHook(*scan.module));
            static_cast<void>(TryInstallPreGetCollectibleRelay(*scan.module));
#endif
            TestRunObserver::Mark(TestRunObserver::State::ManifestInstallEntered);
            const DefaultManifestInstallResult install = TryInstallDefaultManifestMod(*scan.module);
            TestRunObserver::Mark(TestRunObserver::State::ManifestInstallReturned,
                                  static_cast<std::uint32_t>(install));
            if (install == DefaultManifestInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
                MarkStartupProbeStage8Gate(kStartupProbeStage8InstallSucceeded);
                AllowDefaultManifestInitialization();
#endif
#if defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 8)
                ManagerUpdateHookAudit::RecordWorkerState(
                    ManagerUpdateHookAudit::WorkerState::InstallSuccess, 0);
                for (u32 sample = 1; sample < kManagerHookAuditSampleLimit; ++sample) {
                    svcSleepThread(kTargetModuleScanIntervalNanoseconds);
                    const bool finalSample = sample + 1 == kManagerHookAuditSampleLimit;
                    ManagerUpdateHookAudit::Sample(finalSample);
                    ManagerUpdateHookAudit::Flush();
                }
#endif
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
                ReportStartupProbeStage8Gates();
#else
#if defined(EXL_PERSISTENCE_TRACE)
                ManagerUpdateHookAudit::RecordWorkerState(
                    ManagerUpdateHookAudit::WorkerState::InstallFailure, static_cast<u32>(install));
#if !defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
                ReportTraceDefaultInstallFailure(install);
#endif
#endif
#if defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
                PersistenceEventJournal::Mark(
                    PersistenceEventJournal::Event::CallbackFailed,
                    PersistenceEventJournal::Operation::None,
                    static_cast<u32>(install));
                PersistenceEventJournal::FlushBounded();
#endif
#endif
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
            const Stage118InstallResult install =
                TryInstallStage118ManagedFileWriteDiagnostic(*scan.module);
            if (install == Stage118InstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                ReportStage118Failure(static_cast<u32>(install));
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
            const Stage127SaveLoadInstallResult install = TryInstallStage127SaveLoadDiagnostic(*scan.module);
            if (install == Stage127SaveLoadInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                ReportStage127Failure(static_cast<u32>(install));
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
            const Stage128SaveDataManagerInstallResult install =
                TryInstallStage128SaveDataManagerDiagnostic(*scan.module);
            if (install == Stage128SaveDataManagerInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                ReportStage128Failure(static_cast<u32>(install));
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
            const Stage102ChangeRoomInstallResult install =
                TryInstallStage102ChangeRoomDiagnostic(*scan.module);
            if (install == Stage102ChangeRoomInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                ReportStage102Failure(static_cast<u32>(install));
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
            const Stage104RoomKeyInstallResult install =
                TryInstallStage104RoomKeyDiagnostic(*scan.module);
            if (install == Stage104RoomKeyInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                ReportStage104Failure(static_cast<u32>(install));
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 112
            const Stage112DescriptorReentryInstallResult install =
                TryInstallStage112DescriptorReentryDiagnostic(*scan.module);
            if (install == Stage112DescriptorReentryInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                ReportStage112Failure(static_cast<u32>(install));
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
            const Stage108LifecycleInstallResult install =
                TryInstallStage108LifecycleDiagnostic(*scan.module);
            if (install == Stage108LifecycleInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                ReportStage108Failure(static_cast<u32>(install));
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
            const Stage109RestartInstallResult install = TryInstallStage109RestartDiagnostic(*scan.module);
            if (install == Stage109RestartInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                ReportStage109Failure(static_cast<u32>(install));
            }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
            const Stage110ChangeRoomInstallResult roomInstall = TryInstallStage110ChangeRoomDiagnostic(*scan.module);
            if (roomInstall != Stage110ChangeRoomInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                ReportStage110Failure(static_cast<u32>(roomInstall));
            }
            const Stage110LifecycleInstallResult lifecycleInstall = TryInstallStage110LifecycleDiagnostic(*scan.module);
            if (lifecycleInstall == Stage110LifecycleInstallResult::Success) {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                ReportStage110Failure(0x10u | static_cast<u32>(lifecycleInstall));
            }
#else
            const HookInstallResult install = TryInstallManagerUpdateHook(*scan.module);
            if (install == HookInstallResult::Success) {
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48
                const auto stage48Install = TryInstallStage48MusicReplayProbe(*scan.module);
                if (stage48Install != Stage48MusicReplayProbeInstallResult::Success) {
                    SetRuntimeState({.moduleFound = true, .hookAttempted = true});
                    ReportStage48Failure(static_cast<u32>(stage48Install));
                }
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 15 || EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17 || EXL_DIAGNOSTIC_STAGE == 45 || EXL_DIAGNOSTIC_STAGE == 48)
                if (TryInstallManagerRenderHook(*scan.module) != RenderHookInstallResult::Success) {
                    SetRuntimeState({.moduleFound = true, .hookAttempted = true});
#if EXL_DIAGNOSTIC_STAGE == 15
                    ReportStage15Failure(1);
#elif EXL_DIAGNOSTIC_STAGE == 16
                    ReportStage16Failure(1);
#elif EXL_DIAGNOSTIC_STAGE == 17
                    ReportStage17Failure(1);
#elif EXL_DIAGNOSTIC_STAGE == 45
                    ReportStage45Failure(1);
#else
                    ReportStage48Failure(1);
#endif
                }
#endif
                SetRuntimeState({.moduleFound = true, .hookAttempted = true, .hookSucceeded = true});
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 7 || EXL_DIAGNOSTIC_STAGE == 14 || EXL_DIAGNOSTIC_STAGE == 15 || EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17 || EXL_DIAGNOSTIC_STAGE == 45 || EXL_DIAGNOSTIC_STAGE == 48
                TestRunObserver::Mark(TestRunObserver::State::LuaInitializeEntered);
                const LuaRuntime::LuaInitResult luaResult = LuaRuntime::Initialize();
                TestRunObserver::Mark(TestRunObserver::State::LuaInitializeReturned,
                                      static_cast<std::uint32_t>(luaResult));
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
                if (luaResult != LuaRuntime::LuaInitResult::Success) {
                    ReportStartupProbeStage8Gates();
                }
                MarkStartupProbeStage8Gate(kStartupProbeStage8LuaInitialized);
                ReportStartupProbeStage8Gates();
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 7
                if (luaResult != LuaRuntime::LuaInitResult::Success) {
                    ReportStage7LuaInitializationFailure(luaResult);
                }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
                if (luaResult != LuaRuntime::LuaInitResult::Success) {
                    ReportStage14LuaInitializationFailure(luaResult);
                }
                MarkStage14DiagnosticReady();
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
                if (luaResult != LuaRuntime::LuaInitResult::Success) {
                    ReportStage15Failure(2);
                }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
                if (luaResult != LuaRuntime::LuaInitResult::Success) {
                    ReportStage16Failure(2);
                }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
                if (luaResult != LuaRuntime::LuaInitResult::Success) {
                    ReportStage17Failure(2);
                }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
                if (luaResult != LuaRuntime::LuaInitResult::Success) {
                    ReportStage45Failure(2);
                }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48
                if (luaResult != LuaRuntime::LuaInitResult::Success) {
                    ReportStage48Failure(2);
                }
#else
                static_cast<void>(luaResult);
#endif
#endif
            } else {
                SetRuntimeState({.moduleFound = true, .hookAttempted = true});
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
                if (install == HookInstallResult::InstructionMismatch) {
                    ReportStage6Failure(4);
                }
                switch (install) {
                case HookInstallResult::RelayPatchMismatch:
                    ReportStage6Failure(15);
                case HookInstallResult::RelaySlotNotEmpty:
                    ReportStage6Failure(16);
                case HookInstallResult::RelayPublishFailed:
                    ReportStage6Failure(17);
                case HookInstallResult::GameOwnerSlotMismatch:
                    ReportStage6Failure(37);
                case HookInstallResult::GameOwnerSlotPublishFailed:
                    ReportStage6Failure(38);
                case HookInstallResult::GameIsPausedThunkMismatch:
                    ReportStage6Failure(43);
                case HookInstallResult::GameIsPausedThunkPublishFailed:
                    ReportStage6Failure(44);
                case HookInstallResult::Success:
                case HookInstallResult::InstructionMismatch:
                    UNREACHABLE;
                }
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
                ReportStage14Failure(Stage14Diagnostic::Stage14Failure::InstallFailed);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
                ReportStage15Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
                ReportStage16Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
                ReportStage17Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
                ReportStage45Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
                if (install == HookInstallResult::ManagerIsActionTriggeredMismatch) {
                    ReportStage88Failure(2);
                }
                if (install == HookInstallResult::Stage88GameBindingsMismatch) {
                    ReportStage88Failure(3);
                }
                ReportStage88Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
                if (install == HookInstallResult::ManagerIsActionTriggeredMismatch) {
                    ReportStage89Failure(2);
                }
                if (install == HookInstallResult::Stage89GameBindingsMismatch) {
                    ReportStage89Failure(3);
                }
                ReportStage89Failure(1);
#endif
            }
#endif
#endif
#if !defined(EXL_DIAGNOSTIC_STAGE) || \
    (EXL_DIAGNOSTIC_STAGE != 11 && EXL_DIAGNOSTIC_STAGE != 12 && EXL_DIAGNOSTIC_STAGE != 13)
            svcExitThread();
#endif
        }
        if (attempt + 1 < kTargetModuleScanAttemptLimit) {
            svcSleepThread(kTargetModuleScanIntervalNanoseconds);
        }
    }
    SetRuntimeState({.fatalFailure = true});
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
    ReportStartupProbeStage8Gates();
#else
#if !defined(EXL_DIAGNOSTIC_STAGE) && defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 8)
    ManagerUpdateHookAudit::RecordWorkerState(ManagerUpdateHookAudit::WorkerState::TimedOut, 0);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
    ReportStage6Failure(2);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
    ReportStage8Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
    ReportStage9Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
    ReportStage11Failure(stage11CandidateSeen ? 9 : 6);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
    ReportStage12Failure(stage11CandidateSeen ? 9 : 6);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
    ReportStage13Failure(stage11CandidateSeen ? 9 : 6);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
    ReportStage14Failure(Stage14Diagnostic::Stage14Failure::ModuleNotFound);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
    ReportStage15Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
    ReportStage16Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
    ReportStage17Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
    ReportStage45Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
    ReportStage88Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
    ReportStage89Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
    ReportStage102Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
    ReportStage104Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
    ReportStage108Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
    ReportStage109Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
    ReportStage118Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
    ReportStage127Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
    ReportStage128Failure(1);
#endif
#endif
    svcExitThread();
}

// ---------------------------------------------------------------------------
// 批次 371（2026-10-05）：`Game::Init` 入口中继要用的两个**跨线程**小格子
// ---------------------------------------------------------------------------
// 为什么在这里（不跟状态面放一起）：它们必须在 `RunEarlyModMountPrelude` **之前**可见，
// 而那个函数的定义就排在下面；放到本 TU 末尾的匿名命名空间里会看不到。
//
// ★ 线程归属（写在这里，免得后来者以为可以随便用）：`g_GameInitFallbackEntry` 由**我们自己的
//   worker 线程**在装中继成功时写、由**游戏线程**的回调读 ⇒ 原子量；`g_GameInitMountGate` 只被
//   游戏线程的回调撞（exchange），原子是为了"只做一次"这条性质本身，而不是因为有两个写者。
namespace {
//: 回退入口（`TryInstallEntryRelay` 公布的那个"跑原函数"的地址）。
//: 用 u64 而不是"bool 的原子特化"与类型无关 —— 项目有一条门禁
//:   ★ 批次 385（2026-10-06）：这句注释原来**逐字写着那个类型名**，而门禁
//:   `test_manager_update_hook_audit.py::test_runtime_source_contains_no_bool_atomics`
//:   是"全文搜字符串"（**注释也算**）⇒ 它把这句注释本身判成了违规。
//:   这里改成描述性说法，**语义一字未变**。
//: （`test_runtime_source_contains_no_bool_atomics`）禁止 runtime 源码里出现 bool 原子量。
std::atomic<std::uintptr_t> g_GameInitFallbackEntry{0};
//: "那一步已经有人做过了吗"的闸门（0 = 没做过、1 = 做过了）。
//: 实验 A 用不到它（那一版回调里什么都不做）；**实验 B 用它保证"读清单只读一次"**。
//: 371 那一版用它保证"挂载只挂一次"。
constexpr std::uint32_t kGameInitMountGateOpen = 1;
std::atomic<std::uint32_t> g_GameInitMountGate{0};
}  // namespace

// 2026-10-20：由Main实际LoadModule完成通知进入，早于调用者继续执行NRO。
// 只装Game::Init和既有ContentGetMountedFilePath中继；不在加载器内读模组文件，
// 不提前启用曾导致PauseScreen空图的ANM2中继。原两秒轮询及其证据保留在本轮source-before。
#if !defined(EXL_DIAGNOSTIC_STAGE)
bool PrepareEarlyResourcesAfterLoad() noexcept {
    auto& state = isaac::runtime::earlymount::g_EarlyMountState;
    // SDK/SaltyNX的实际LoadModule已成功返回，游戏NRO已完成映射与绑定。
    const auto scan = ScanTargetModule();
    if (scan.status != TargetModuleScanStatus::Found || !scan.module) return false;
    const auto& module = scan.module;
    state.gameModuleFoundTicks = isaac::runtime::RuntimePerfTick();

    // ② 纯内存核靶点：对齐 + 落在模块的 `.text` 里 + 那一页**现在是可执行的**。
    //    ★ 最后一条不是可选的：`TryInstallEntryRelay` 第一步就 `memcpy` 读目标入口那 16 字节
    //      做守卫比对；地址若还没映射/不可执行，**读它本身就是崩溃**（不是"守卫不符"那种可控失败）。
    const std::uintptr_t target = module->base + kGameInitEntryFileOffset;
    if (kGameInitEntryFileOffset % 4 != 0 ||
        !module->Contains(target, kGameInitEntryExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(target, kGameInitEntryExpectedBytes.size())) {
        state.relayInstallAttempted = 1;
        // 0xFFFFFFFE 是本段自定义的哨兵："走到了装中继这一步，但靶点本身不可挂"
        // （与 `relay::EntryRelayFailure` 的码区分开 —— 那个码表里没有这一种）。
        state.relayInstallFailure = 0xFFFFFFFEu;
        return false;
    }

    // ③ 装入口中继。只改写游戏模块 `.text` 的 16 字节 + 写我们模块自己的竞技场；
    //    **不读文件、不调任何引擎函数**（这正是 370 崩掉的那件事，见本段上面的说明）。
    state.relayInstallAttempted = 1;
    std::uintptr_t fallbackEntry = 0;
    const bool installed = isaac::runtime::relay::TryInstallEntryRelayWithPublisher(
        target, kGameInitEntryExpectedBytes.data(),
        isaac::runtime::engine_call::AddressOfFunction(&EntryRelayGameInitCallback),
        +[](std::uintptr_t original,void* opaque) noexcept {
            static_cast<std::atomic<std::uintptr_t>*>(opaque)->store(original,std::memory_order_release);
            return true;
        }, &g_GameInitFallbackEntry, &fallbackEntry);
    // ★ 回退入口**先于入口改写**公布（`TryInstallEntryRelay` 内部纪律："回调可达 ⇒ 原函数入口
    //   一定有效"）⇒ 这里无论装成没成都先把它收下；回调那边只在真正被调到时才会用到它。
    // 实际回调消费的g_GameInitFallbackEntry由publisher在入口改写前发布。
    state.relayInstallFailure = installed ? 0u : isaac::runtime::relay::LastFailure();
    if (installed) {
        state.relayInstalledTicks = isaac::runtime::RuntimePerfTick();
    }

    // ④ ★★★ 批次 385（2026-10-06）：**把"资源类"那两条入口中继也在这里装上**。
    //
    // ## 为什么必须在这一刻（真机读数定案，见
    //    `docs/分析-红字根因-模组覆盖是事后修正而PC是启动期前置-20261006.md` §9）
    //
    //   * `ANM2::Load` 中继"首次被调用"比 `Game::Init` **晚 6.5 秒**（tick 实测：
    //     4,131,309,069 vs 4,006,329,802）；
    //   * 而引擎读 `gfx/ui/minimap1.anm2` 就在 `Game::Init` 里（`Game::Init+0x340`
    //     → `Minimap::Init` → `ANM2::Load`）⇒ **那次读没走我们的中继**
    //     ⇒ 引擎按本体解析 ⇒ 本体那份被钉进它自己的动画缓存 ⇒ 之后我们答得再对也改不掉
    //     ⇒ 模组（minimapi）画红字；
    //   * 那条 6.5 秒 ≈ **worker 那 5 秒等待 + 之后装 21 个挂点/启动状态机的时间** —— 完全对得上。
    //
    // ## 为什么在这里装是安全的
    //
    //   * 370 崩的那一次是"**在这个窗口里读文件 / 调引擎 API**"（模块还在重定位 ⇒ `Instruction Abort`）；
    //     而"装入口中继"= **纯内存 + 改写目标入口 16 字节**，`EvaluateEntryRelayBinding` 只读模块内存；
    //     ⇒ 本段**依旧不读文件、不调任何引擎函数**。
    //   * 装不上就照旧（退回"晚装"的旧行为），**不抛错、不半装**。
    //
    // ## 与后面那套生产安装的关系
    //
    //   ★ 它必须**跳过**这两条 —— 由 `hook_manager.cpp` 的 `ShouldSkipHook` 里
    //     `EntryRelayInstalledEarly(id)` 让开。**同一入口装两次必然 `EntryMismatch`**
    //     （入口中继靠改写入口 16 字节工作，见那段注释）。
    {
        // ★★★ 批次 385：**先把回调接进绑定表** —— 这一步不能省（2026-10-06 15:49 的真机读数换来的）。
        //
        //   `EvaluateEntryRelayBinding` 会检查 `binding.callback != nullptr`，而
        //   `RegisterEntryRelayCallbacks()` 原本是在**生产安装流程**里才调的（= worker 那 5 秒等待
        //   结束之后）⇒ 少了这一行，下面两条早装会**静默失败**（返回 false、按设计不抛错），
        //   读数上只表现为"`ANM2` 中继首次被调仍然很晚（晚 `Game::Init` 6.4 秒）" —— 第一版就是这么
        //   白改的。它是**纯内存**的赋值、幂等；生产那边再调一次无害。
        isaac::runtime::RegisterEntryRelayCallbacks();
        const isaac::runtime::HookTarget hookTarget{
            module->base, module->textSize, module->size, module->buildId};
        std::uintptr_t earlyEntry = 0;
        // ★★★ 批次 387（2026-10-06 夜）：**二分第一步 —— 只早装一条**。
        //
        // 为什么（批次 386 的教训）：386 把**两条一起**早装 ⇒ 启动即崩在 `PauseScreen::Init`
        // （取图拿到空指针 ⇒ `strb wzr,[x0,#0x7c]` ⇒ Data Abort at 0x7c；见
        // `docs/崩溃分析-20261006-1555-PauseScreenInit空指针-早装资源中继.md`）。
        // 而 385（同样的代码，只是"早装静默失败"= 根本没生效）**不崩** ⇒ **"早装真的生效"就是崩因**，
        // 但**不知道是两条里的哪一条**（也可能是"两条一起才崩"）。
        //
        // ⇒ 本批**一次只动一个变量**：先只早装 `ContentGetMountedFilePath`（它拦"所有路径解析"、
        //   覆盖面最大、最可疑），把 `Anm2Load` 退回"晚装"。
        //   判据：
        //     * **不崩** ⇒ 肇事的是另一条（下一步单独查 `Anm2Load`），而且红字那条线也据此重排；
        //     * **崩** ⇒ 就是这一条 ⇒ 下一步查它"答坏了什么"——**重点怀疑"它把引擎指向了不存在的文件"**：
        //       我们的候选存在性判断用的是"按挂载点前缀拼路径"（`GetMountedFilePath`）、
        //       **不检查文件是否真的存在**，而 PC 用的是**真的去开文件**（`FileSystem::Open @0x963120`）。
        //       （同文档 §7.2；这一环本身也是"与 PC 不一致"的一处偏离。）
        //   ★ 读数里 `earlyResourceRelaysAttempted/Installed` 应显示 **1 / 1**（只试一条、只成一条）。
        for (const isaac::runtime::HookId id : {isaac::runtime::HookId::ContentGetMountedFilePath}) {
            ++state.earlyResourceRelaysAttempted;
            if (isaac::runtime::TryInstallEntryRelayEarly(id, hookTarget, &earlyEntry)) {
                ++state.earlyResourceRelaysInstalled;
            }
        }
    }
    return installed && state.earlyResourceRelaysInstalled == 1;
}
#endif
#endif

}

// ============================================================================
// "让模组那一层早于引擎第一次读共享路径"这一段的状态面**本体**
// ============================================================================
//
// ★ **外部链接、定义在匿名命名空间之外**（读数工具 `tools/read_device_state_via_gdb.py`
//   按符号名直读；放进上面的匿名命名空间会让符号名变成 `_ZN12_GLOBAL__N_1L…`，
//   而且门禁 `runtime/tests/test_early_mod_mount.py` 就钉着这一条）。
// ★ 字段顺序即内存顺序，**改动必须同步 `tools/read_device_state_via_gdb.py`**
//   （契约与每一格的语义写在 `early_mod_mount_state.hpp`，两边必须一起改）。
// ★ 写入只发生在本 TU ⇒ 不跨 TU 走数据 GOT（批次 081/084 的纪律：跨 TU 的热路径记账一律
//   走函数调用，见 `runtime_perf.hpp`）。370 起写入方是 `RunEarlyModMountPrelude`（worker 线程）；
//   371 起多了游戏线程的回调 `EntryRelayGameInitCallback` —— 它写的是**另外几格**
//   （回调计数 / 挂载计数），与 worker 那几格是不同内存位置，见头文件的"跨线程可见性"一节。
namespace isaac::runtime::earlymount {
EarlyModMountState g_EarlyMountState{};
}  // namespace isaac::runtime::earlymount

// ============================================================================
// 批次 371（2026-10-05）：`Game::Init` 入口中继的**回调**（游戏线程）
// ============================================================================
//
// 形状 = 目标函数的 ABI：`Game::Init()` 是无参成员函数 ⇒ **x0 = this**。入口桩是**尾调用**
// （`br x16`），所以这里 `ret` 直接回到游戏调用方；要跑原函数得自己调回退入口。
//
// **"读清单 + 挂挂载点"真正发生的地方**（370 把它放在我们自己的 worker 线程 ⇒ 撞上模块重定位
// 窗口 ⇒ 3/3 崩）。此刻引擎已经跑起来、重定位早已完成；而且本回调**按构造**排在
// `Game::Init + 0x340` 那次 `Minimap::Init → ANM2::Load("gfx/ui/minimap1.anm2")` **之前**
// ⇒ 模组那一层在引擎第一次读之前就存在 —— 这正是 PC 的形态，于是**不需要任何"事后作废"**
// （那条路已被批次 368 的真机崩溃证伪）。
//
// ★★★ **更正（批次 383，2026-10-06）**：上面这几行写于批次 371，当时回调里做的是"**读清单 + 挂载**"。
//   批次 372 的拆因实验把回调里的事拆成两半试，**实验 B（只读清单、一个字节都不碰引擎）干净**
//   ⇒ 那之后生产回调**就一直留着实验 B 的形态**。批次 378 换机制时，把"发布可重定向的模组根"
//   加进了 `MountModsBeforeHeavyWork`（纯内存），**但回调仍然调"只读清单"那个入口**
//   ⇒ ★ **"发布"这一步被漏在了后面**，上面那句"模组那一层在引擎第一次读之前就存在"**不再成立**。
//   后果（真机读数 `dist/gdb-read-20261006-1423-redtext.txt`）：引擎先按本体层把
//   `gfx/ui/minimap1.anm2` 读进它的动画缓存（按键存条目）⇒ 之后 `Sprite:Load` 命中缓存、连路径都不问
//   （757 次中继里只有 134 次问到解析器）⇒ minimapi 的 `IsBadLoad()` 读到 13 帧 ⇒ 画红字。
//   **批次 383 把回调改回"读清单 + 发布"**（`MountModsBeforeHeavyWork`）⇒ 这句注释重新成立。
//   逐条证据：`docs/分析-红字根因-模组覆盖是事后修正而PC是启动期前置-20261006.md`。
//
// 已知窗口（如实写，不粉饰）：本回调写 `g_DefaultManifestBindings` / 清单批次缓冲这一组全局，
// 而 worker 线程在 5 秒后装钩子时（`TryInstallDefaultManifestMod`）也写同一组。两者的取值都来自
// 同一份 `GameFileReader::VerifyBindings`（同一个模块 ⇒ 同样的字节），且时序上本回调（`Game::Init`
// 是**开机早期**的调用，早于那 5 秒）在前、worker 在后。**这与 370 已经接受的同级别窗口一致**
// （370 是"worker 写、游戏线程读"），本批没有把它放大；要彻底消除得给那一组全局加锁，属于
// `hook_manager.cpp` 的改动范围，不在本批。
#if !defined(EXL_DIAGNOSTIC_STAGE)
extern "C" void EntryRelayGameInitCallback(void* self) {
    using isaac::runtime::earlymount::g_EarlyMountState;
    // 这一格只在游戏线程写（`Game::Init` 由引擎自己的调用链同步调起）⇒ 与 worker 线程那几格
    // 是**不同内存位置**，不构成数据竞争。
    ++g_EarlyMountState.relayCallbackFired;
    if (g_EarlyMountState.callbackFirstFiredTicks == 0) {
        g_EarlyMountState.callbackFirstFiredTicks = isaac::runtime::RuntimePerfTick();
    }

    // ============================================================================
    // ★★ 实验 B（2026-10-05）：**只读清单、一个字节都不碰引擎**
    // ============================================================================
    //
    // **为什么要拆**：371（回调里"读清单 + 挂挂载点"）上卡后的真机表现是
    // **引擎没有音乐** ⇒ 渲染族那道闸门（`g_DefaultCallbackGate`）整局不开 ⇒ `MC_POST_RENDER`
    // 与所有 `*_RENDER` 一次都不派发 ⇒ EID 这类画在屏幕上的模组全无效果。
    // 而 371 的代码**一行都没碰渲染/音频**（`git log -G` 逐符号检索为空）⇒ 只剩"我们在
    // `Game::Init` 里面动了引擎"这条**间接**路。于是把 371 的两条差异拆开，**一卡一个变量**：
    //
    //   * **实验 A（上一卡）**：只装中继，回调里**连清单都不读** ⇒ 真机**干净**
    //     （屏幕上的探针文字照常画 ⇒ 渲染族正常）⇒ 元凶在"回调里做的那件事"。
    //   * **实验 B（本卡）**：回调里**只读清单**（`ResolveAll`，会**读文件**），
    //     但**不 `RegisterMod`、不调引擎挂载接口、不写任何引擎内存**。
    //   * （若 B 也干净：把"读文件"再拆成"读清单"与"扫目录"；若 B 坏：危害就在"在
    //     `Game::Init` 里面读文件"这一半，371 的整条思路要重做。）
    //
    // **判据**（一卡一读，用 KELI-NX 平台截图/读内存，不用调试桩）：引擎**有没有音乐**
    // （它决定渲染族闸门开不开 ⇒ 屏幕上那批探针文字画不画）。
    //
    // 371 原来那一版（"读清单 + 挂 9 个模组目录"）留档在下面，**不编译**：
    //   const EarlyModMountOutcome outcome = MountModsBeforeHeavyWork(*scan.module);
    //   g_EarlyMountState.mountsAttempted = outcome.mountsAttempted;
    //   g_EarlyMountState.mountsFailed = outcome.mountsFailed;
    //   if (outcome.attempted) {
    //       g_EarlyMountState.mountListHadModPrefix =
    //           isaac::runtime::bridge::EngineMountPointListHasModPrefix(*scan.module) ? 1u : 0u;
    //   }
    if (g_GameInitMountGate.exchange(kGameInitMountGateOpen, std::memory_order_acq_rel) == 0) {
        const TargetModuleScanResult scan = ScanTargetModule();
        if (scan.status == TargetModuleScanStatus::Found && scan.module.has_value()) {
            // ★★★ 批次 383（2026-10-06）：**从"只读清单"改成"读清单 + 发布重定向名单"**。
            //
            // 为什么（根因，逐条证据见
            // `docs/分析-红字根因-模组覆盖是事后修正而PC是启动期前置-20261006.md`）：
            // 引擎的动画缓存**按键存条目** ⇒ "谁先读到哪一份，那份就被钉住"。批次 380 上卡后的真机读数：
            // `ANM2::Load` 中继被调 757 次、只有 134 次真的问到路径解析，而"作废旧条目"恒 0
            //（唯一的事后手段在批次 368 崩过、369 起被禁用）⇒ **发布晚一步就等于永远改不回来**。
            // 而这一刀**按构造**排在 `Game::Init+0x340` 的 `Minimap::Init` 之前（见上面那段注释）
            // ⇒ 在这里发布 = 引擎第一次读之前模组那层就在 = **PC 的形态**。
            //
            // 与上一版（`ReadManifestOnlyForExperiment`）的差别**只有最后一步**：
            // `PublishModResourceRedirectList`（纯内存数组 + 释放屏障）。读文件那半
            //（`VerifyBindings` + `ResolveAll` + `Discover`）逐条相同 ⇒ 372 实验 B"这个窗口里读文件干净"
            // 的结论照旧成立；371"没音乐"的元凶（`AddMountPoint` 抢 `content/music.xml`）也不在
            //（重定向规则只管 `resources-dlc3/` 与 `resources/`）。
            const EarlyModMountOutcome outcome = MountModsBeforeHeavyWork(*scan.module);
            g_EarlyMountState.mountsAttempted = outcome.mountsAttempted;
            g_EarlyMountState.mountsFailed = outcome.mountsFailed;
            // 378 之后引擎的挂载点表里不再有模组前缀 ⇒ 这一格**结构性为 0**（字段保留：读数工具按偏移读它）。
            g_EarlyMountState.mountListHadModPrefix = 0;
        }
    }

    // 跑原函数（入口中继契约：回调自己决定几时调回退入口）。
    // ★ 没有回退入口就**什么都不做** —— 绝不假装跑过原函数（与 ANM2 那条中继同一口径）。
    //   实际上装成功的中继不会出现这种情况：`TryInstallEntryRelay` 保证"回调可达 ⇒ 回退入口有效"。
    const auto original = isaac::runtime::engine_call::AsFunction<void (*)(void*)>(
        g_GameInitFallbackEntry.load(std::memory_order_acquire));
    if (original != nullptr) {
        original(self);
    }
}
#endif

#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
extern "C" NORETURN void ReportStartupProbeStage8ManifestResult(bool initialized, u32) {
    MarkStartupProbeStage8Gate(kStartupProbeStage8InstallSucceeded);
    if (initialized) {
        MarkStartupProbeStage8Gate(kStartupProbeStage8LuaInitialized);
    }
    ReportStartupProbeStage8Gates();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
namespace {
constexpr u64 kStage6FailureMagic = 0x49534141435F4946ULL;
}

NORETURN void ReportStage6Failure(u32 status) {
    svcBreak(BreakReason_User, kStage6FailureMagic, (6ULL << 32) | status);
    svcExitProcess();
}
#endif

#if defined(EXL_STARTUP_PROBE_STAGE)
extern "C" void RunStartupProbeExlMainGate();
#endif

#if defined(EXL_LAYERED_RUNTIME)
// Third arming point for the diagnostics journal, and the earliest one. It can only
// succeed when the host plugin has already registered the file table, which is exactly
// the case this call exists to cover: the plugin may load before the game reaches its
// first Manager update, and the port now reads the table live, so a later attempt
// succeeds even if this one runs too early. Hidden visibility keeps the call direct.
extern "C" __attribute__((visibility("hidden"))) void IsaacModRuntime_TryAttachDiagnostics();
// Records "this copy of the module reached its entry" so a plugin can tell which copy it
// is talking to. Kept hidden: it is called only from here.
extern "C" __attribute__((visibility("hidden"))) void IsaacModRuntime_PublishRuntimeSelf(std::uintptr_t);
#endif

extern "C" void exl_main(void*, void*) {
    // First statement of the entry: the calling thread gets a libc thread pointer if it
    // has none. devkitA64 dereferences `[tpidrro_el0 + 0x1f8]` on every thread-pointer
    // read, the host plugin's own code included, and a game thread leaves that slot
    // zeroed.
    // 两个调用都只存在于分层构建的 SaltyNX 桥里（`saltynx_runtime_bridge.cpp` 的非分层副本
    // 是空 TU），所以必须与声明一起守卫 —— 未加守卫的非分层/诊断构建会报未声明（2026-09-13 修）。
#if defined(EXL_LAYERED_RUNTIME)
    IsaacModRuntime_EnsureThreadTls();
    IsaacModRuntime_PublishRuntimeSelf(reinterpret_cast<std::uintptr_t>(&exl_main));
#endif
    // 批次 099（2026-09-24）：装「未捕获 C++ 异常」的留证兜底（见 `fatal_forensics.hpp` 的文件头）。
    // 为什么放在入口这么早：装完之后**任何时刻**的未捕获异常都会留下一份崩溃报告；
    // 在那之前只会得到"画面卡死、音乐还在、连报告都没有"那种现场（2026-09-24 的真机现象）。
    // ★ 它不改游戏逻辑，只在真死之前先 `svcBreak` 把寄存器交出去。
    isaac::runtime::forensics::InstallAbortForensics();
#if defined(EXL_LAYERED_RUNTIME) && !defined(EXL_DIAGNOSTIC_STAGE)
    isaac::runtime::InitializeOsClock();
#endif
    // 2026-09-16：这里原有的 `svcSleepThread(15'000'000'000ULL)` 已删除（实验 E1，提交 `38b761b2` 加的）。
    // 入口是被游戏**同步等待**的 ⇒ 在入口等 = 直接给开机加秒数，而崩溃只是整体后移（记录续十六 §二）。
    // 要把"我们自己的启动期动作"挪出装载窗口，等的地方是 `ModuleWorker` 开头（见下面那个函数）。
    TestRunObserver::Mark(TestRunObserver::State::ExlMainEntered);
#if defined(EXL_LAYERED_RUNTIME)
    // Layered entry: the Composition Root records the entry boundary before the
    // legacy startup path runs. Control flow, addresses and side effects stay
    // exactly as they are in the non-layered build.
    static_cast<void>(isaac::runtime::RuntimeBootstrap::Start());
    IsaacModRuntime_TryAttachDiagnostics();
#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_FILEIO
    // First self-journal record of this session, written from the entry itself: it proves this
    // copy reached `exl_main` and reports whether the registered file table is visible here.
    // Probe builds only: the route it uses is measured dead on hardware (2026-09-11).
    //
    // 由 `PROBE_BREAK_FILEIO` 单独控制：这是探针包里最早、也是唯一在 `exl_main` 入口就走
    // 失效文件路由的调用点（2026-09-13 二分定位探针包启动故障）。
    IsaacModRuntime_WriteSelfJournal(isaac::runtime::kSelfJournalExlMainMarker);
#endif
#endif
#if defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
    PersistenceEventJournal::MarkAndFlush(
        PersistenceEventJournal::Event::RuntimeEntered);
#endif
#if defined(EXL_STARTUP_PROBE_STAGE)
    RunStartupProbeExlMainGate();
#endif
#if !defined(EXL_DIAGNOSTIC_STAGE) && defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 8)
    ManagerUpdateHookAudit::RecordWorkerState(
        ManagerUpdateHookAudit::WorkerState::RuntimeEntered, 0);
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 6
    MarkStartupProbeStage6Gate(kStartupProbeStage6RuntimeStateRecorded);
#elif defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 7
    MarkStartupProbeStage7Gate(kStartupProbeStage7RuntimeStateRecorded);
#endif
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 6 || EXL_DIAGNOSTIC_STAGE == 7 || EXL_DIAGNOSTIC_STAGE == 8 || EXL_DIAGNOSTIC_STAGE == 9 || EXL_DIAGNOSTIC_STAGE == 11 || EXL_DIAGNOSTIC_STAGE == 12 || EXL_DIAGNOSTIC_STAGE == 13 || EXL_DIAGNOSTIC_STAGE == 14 || EXL_DIAGNOSTIC_STAGE == 15 || EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17 || EXL_DIAGNOSTIC_STAGE == 45 || EXL_DIAGNOSTIC_STAGE == 48 || EXL_DIAGNOSTIC_STAGE == 88 || EXL_DIAGNOSTIC_STAGE == 89 || EXL_DIAGNOSTIC_STAGE == 102 || EXL_DIAGNOSTIC_STAGE == 104 || EXL_DIAGNOSTIC_STAGE == 108 || EXL_DIAGNOSTIC_STAGE == 109 || EXL_DIAGNOSTIC_STAGE == 110 || EXL_DIAGNOSTIC_STAGE == 112 || EXL_DIAGNOSTIC_STAGE == 118 || EXL_DIAGNOSTIC_STAGE == 127 || EXL_DIAGNOSTIC_STAGE == 128)
    exl::util::impl::InitMemLayout();
    virtmemSetup();
#endif
    exl::hook::Initialize();
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 6
    MarkStartupProbeStage6Gate(kStartupProbeStage6HookInitialized);
#elif defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 7
    MarkStartupProbeStage7Gate(kStartupProbeStage7HookInitialized);
#endif
    u64 programId = 0;
    if (R_FAILED(svcGetInfo(&programId, InfoType_ProgramId, CUR_PROCESS_HANDLE, 0))) {
        g_StartupStatus.store(StartupStatus::TitleQueryFailed, std::memory_order_release);
        SetRuntimeState({.fatalFailure = true});
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
        ReportStage6Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
        ReportStage8Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
        ReportStage9Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
        ReportStage11Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
        ReportStage12Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
        ReportStage13Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
        ReportStage14Failure(Stage14Diagnostic::Stage14Failure::StartupFailed);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
        ReportStage15Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
        ReportStage16Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
        ReportStage17Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
        ReportStage45Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
        ReportStage88Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
        ReportStage89Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
        ReportStage102Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
        ReportStage104Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
        ReportStage108Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
        ReportStage109Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
        ReportStage110Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 112
        ReportStage112Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
        ReportStage118Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
        ReportStage127Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
        ReportStage128Failure(1);
#endif
    } else if (programId != kTargetTitleId) {
        g_StartupStatus.store(StartupStatus::TitleMismatch, std::memory_order_release);
        SetRuntimeState({.titleChecked = true, .titleOk = false});
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
        ReportStage6Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
        ReportStage8Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
        ReportStage9Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
        ReportStage11Failure(2);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
        ReportStage12Failure(2);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
        ReportStage13Failure(2);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
        ReportStage14Failure(Stage14Diagnostic::Stage14Failure::StartupFailed);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
        ReportStage15Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
        ReportStage16Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
        ReportStage17Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
        ReportStage45Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
        ReportStage88Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
        ReportStage89Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
        ReportStage102Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
        ReportStage104Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
        ReportStage108Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
        ReportStage109Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
        ReportStage110Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 112
        ReportStage112Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
        ReportStage118Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
        ReportStage127Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
        ReportStage128Failure(1);
#endif
    } else {
        g_StartupStatus.store(StartupStatus::TitleOk, std::memory_order_release);
        SetRuntimeState({.titleChecked = true, .titleOk = true});
#if !defined(EXL_DIAGNOSTIC_STAGE)
        const auto& main = exl::util::GetMainModuleInfo();
        static_cast<void>(isaac::runtime::InstallMainModuleLoadObserver(
            main.m_Text.m_Start, main.m_Text.m_Size, PrepareEarlyResourcesAfterLoad));
#endif

#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 6
        MarkStartupProbeStage6Gate(kStartupProbeStage6TitleOk);
#elif defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 7
        MarkStartupProbeStage7Gate(kStartupProbeStage7TitleOk);
#endif
}
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 6
    void* workerEntry = reinterpret_cast<void*>(&StartupProbeWorker);
#else
    void* workerEntry = reinterpret_cast<void*>(&ModuleWorker);
#endif
    const Result createResult = svcCreateThread(&g_WorkerHandle, workerEntry, nullptr,
                                                g_WorkerStack + sizeof(g_WorkerStack), 0x3A, 2);
#if !defined(EXL_DIAGNOSTIC_STAGE) && defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 8)
    if (R_FAILED(createResult)) {
        ManagerUpdateHookAudit::RecordWorkerState(
            ManagerUpdateHookAudit::WorkerState::ThreadCreateFailed,
            static_cast<u32>(createResult));
    }
#endif
    if (R_FAILED(createResult)) {
        SetRuntimeState({.fatalFailure = true});
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 7
        ReportStartupProbeWorkerGate(
            g_StartupProbeStage7Gates.load(std::memory_order_acquire));
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
        ReportStage6Failure(7);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
        ReportStage8Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
        ReportStage9Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
        ReportStage11Failure(7);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
        ReportStage12Failure(7);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
        ReportStage13Failure(7);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
        ReportStage14Failure(Stage14Diagnostic::Stage14Failure::WorkerFailed);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
        ReportStage15Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
        ReportStage16Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
        ReportStage17Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
        ReportStage45Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
        ReportStage88Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
        ReportStage89Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
        ReportStage102Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
        ReportStage104Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
        ReportStage108Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
        ReportStage109Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
        ReportStage110Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 112
        ReportStage112Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
        ReportStage118Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
        ReportStage127Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
        ReportStage128Failure(1);
#endif
        return;
    }
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 6
    MarkStartupProbeStage6Gate(kStartupProbeStage6ThreadCreated);
#elif defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 7
    MarkStartupProbeStage7Gate(kStartupProbeStage7ThreadCreated);
#endif
    const Result startResult = svcStartThread(g_WorkerHandle);
#if !defined(EXL_DIAGNOSTIC_STAGE) && defined(EXL_PERSISTENCE_TRACE) && \
    (!defined(EXL_STARTUP_PROBE_STAGE) || EXL_STARTUP_PROBE_STAGE != 8)
    if (R_FAILED(startResult)) {
        ManagerUpdateHookAudit::RecordWorkerState(
            ManagerUpdateHookAudit::WorkerState::ThreadStartFailed,
            static_cast<u32>(startResult));
    }
#endif
    if (R_FAILED(startResult)) {
        SetRuntimeState({.fatalFailure = true});
        CloseWorkerHandle();
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 7
        ReportStartupProbeWorkerGate(
            g_StartupProbeStage7Gates.load(std::memory_order_acquire));
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
        ReportStage6Failure(7);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
        ReportStage8Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
        ReportStage9Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
        ReportStage11Failure(8);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
        ReportStage12Failure(8);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
        ReportStage13Failure(8);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
        ReportStage14Failure(Stage14Diagnostic::Stage14Failure::WorkerFailed);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
        ReportStage15Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
        ReportStage16Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
        ReportStage17Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
        ReportStage45Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
        ReportStage88Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
        ReportStage89Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
        ReportStage102Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
        ReportStage104Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
        ReportStage108Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
        ReportStage109Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
        ReportStage110Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 112
        ReportStage112Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
        ReportStage118Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
        ReportStage127Failure(1);
#elif defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
        ReportStage128Failure(1);
#endif
        return;
    }
    CloseWorkerHandle();
}

extern "C" NORETURN void exl_exception_entry() {
    EXL_ABORT("isaac-runtime-probe exception");
}

#endif
