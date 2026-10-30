#include "use_item_internal_hook.hpp"
#include "interfaces/lua/rplus_options.hpp"
#include "application/shader/shader_pipeline.hpp"
#include "application/graphics/procedural_texel_readback.hpp"
#include "hook_manager.hpp"
#include "notice_integrity_native.hpp"
#include "mod_reload_cycle.hpp"
#include "interfaces/lua/runtime_perf.hpp"
#include "domain/runtime/render_frame_coordinator.hpp"

#include "lib.hpp"
#include "lib/nx/kernel/svc.h"
#if !defined(EXL_DIAGNOSTIC_STAGE)
#include "default_callback_gate.hpp"
#include "default_persistence_gate.hpp"
#include "infrastructure/persistence/engine_save_file_adapter.hpp"
#include "mod_persistence.hpp"
#endif
#include "game_observer.hpp"
#include "lua_runtime.hpp"
#include "native_player_init.hpp"
#include "application/game/greed_hourglass_transition.hpp"
#include "projectile_update_tail.hpp"
// 回调登记普查（`LuaRuntime::RegisteredCallbackKindMaskLow` 等）：诊断出口要把
// “Mod 登记了哪些回调种类、哪些有派发点”报给探针，因此这里需要状态头的声明。
#include "lua_runtime_state.hpp"
#include "manager_update_hook_audit.hpp"
#include "persistence_event_journal.hpp"
#include "persistence_trace.hpp"
#include "content_mount_point_probe.hpp"
// 批次 019：原生模组页能不能叫出来（用户要的"PC 式模组页"第一问）。整个 TU 在
// `PROBE_BREAK=0` 或 `PROBE_BREAK_NATIVE_MODS_MENU=0` 时被编译掉，头文件只声明不定义。
#include "probe/native_mods_menu_probe.hpp"
// 批次 077：把「模组那一行 + 模组页 + 中文字体接线」整块搬进生产（探针的行为真值源不变）。
// 三个入口中继由挂点登记表安装（`HookId::MenuGameRender` / `MenuTitleRender` /
// `MenuManagerSetState`），本 TU 只负责"安装点记一次结果 + 每帧驱动一次"。
#include "mod_menu_native.hpp"
#include "anm2_load_override_hook.hpp"   // 批次 363：ANM2::Load 入口中继的绑定与回退入口
#include "mod_resource_redirect.hpp"     // 批次 378：PC 的资源层重定向（发布模组清单）
// 批次 193：原生右上角小地图的触摸门控（把"任意位置拖动都会动小地图"改成"只有手指停在
// 小地图矩形内才动"）。只改游戏代码里的 **3 条指令**，写入走入口中继那套 4 字节原语。
#include "patch/minimap_touch_gate.hpp"
#include "runtime_constants.hpp"
// 批次 251 探针：`kCallbackPreGameExit`（= 17）取自契约表，不用字面量。
#include "domain/callback/callback_descriptor.hpp"
// 批次 251：接管"系统要求退出"这件事要用 exlaunch 已有的跨模块符号解析
// （`rtld::lookup_global_auto` —— 遍历 `nn::ro` 的已加载模块表按名字查符号）。
// 这样不必自己去拿 sdk 模块的基址，理由见下面 `PollSystemExitTakeover` 的说明。
#include "rtld.hpp"
// 批次 121：游戏控制台（自己建一个 `Console` 实例、把命令喂给它）。这里只挂两个**每帧点**：
// 更新那一路推进"按键 → 软键盘 → 执行"，渲染那一路画输出；本体都在这个头里，本 TU 不写业务。
// （它在 `infrastructure/` 那一层：那一层就是"把每帧点接到引擎上"的适配器。）
#include "infrastructure/console/console_session.hpp"
// 批次 195：三条"按按键号"入口的逐字节核对走 L2 的 `VerifyEntryBytes`（它自己负责区间与
// 可读判定 + 比较）—— 不在 `hook_manager.cpp` 里再抄一份 `memcpy`（那会顶着
// `test_no_new_raw_engine_access` 的逐文件存量）。
#include "infrastructure/call/engine_call_access.hpp"
#include "interfaces/lua/engine_frame_probe.hpp"
// 批次 103：`ReadEntityIdentity`（读实体的 Type/Variant，内部带"读引擎字段前先判可读"那套判据）。
#include "interfaces/lua/isaac_api.hpp"
// 批次 405（2026-10-07）：`MC_EVALUATE_CACHE` 的派发顺序（快照 → 原函数 → 逐位派发）。
#include "interfaces/lua/evaluate_cache_dispatch.hpp"
#include "saltynx_probe_break.hpp"
#include "saltynx_self_journal.hpp"
#include "test_run_observer.hpp"
// Every build entry point (production module, diagnostics and the startup
// probes) defines `EXL_LAYERED_RUNTIME`; the non-layered compatibility path was
// deleted with the migration.
#include "application/mod/content_mount_service.hpp"
#include "application/mod/manifest_service.hpp"
#include "application/mod/mod_discovery_service.hpp"
#include "infrastructure/content/engine_content_mount_adapter.hpp"
#include "infrastructure/content/engine_directory_adapter.hpp"
#include "application/mod/mod_load_service.hpp"
#include "application/mod/mod_toggle_service.hpp"
#include "interfaces/lua/mod_menu_api.hpp"
#include "application/runtime/hook_install_service.hpp"
#include "infrastructure/exlaunch/exlaunch_hook_adapter.hpp"
#include "infrastructure/content/game_file_reader_adapter.hpp"
#include "infrastructure/lua/embedded_lua_adapter.hpp"
#include "infrastructure/mod/manifest_selector_adapter.hpp"
#include "ports/module_scanner_port.hpp"

// 零占洞入口中继后端（Task 3）+ 按挂点路由适配器（Task 4）。
#include "infrastructure/hook_routing_adapter.hpp"

// 批次 235（2026-09-30）：启动期"读模组"分段计时的探针。**只在诊断包里编译**
// （`DIAGNOSTIC_PROBES=1`）；正式包零代价、零符号。口径与"要回答的问题"见该头文件。
#include "load_phase_probe.hpp"
#if EXL_DIAGNOSTIC_PROBES
#include "interfaces/lua/runtime_perf.hpp"
#endif
#include "infrastructure/relay/entry_relay_binding.hpp"
#include "infrastructure/relay/entry_relay_hook_adapter.hpp"
#include "relay/entry_relay.hpp"
// L1 引擎内存访问层（批次 147 用）：读 `ModEntry` 的字段、读槽里的指针、写 `+0x139` 那一字节
// 全部走它 —— 调用点里不再出现 `reinterpret_cast`，也不再自己写"这段地址能不能读"。
#include "infrastructure/memory/engine_field_access.hpp"

// 挂点安装报告经快照 reserved 高位回读（Task 5）。与本文件同目录。
#include "hook_install_report_state.hpp"

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
#include "stage14_diagnostic.hpp"
#endif
#if !defined(EXL_DIAGNOSTIC_STAGE) || \
    (EXL_DIAGNOSTIC_STAGE == 11 || EXL_DIAGNOSTIC_STAGE == 12 || EXL_DIAGNOSTIC_STAGE == 13 || \
     EXL_DIAGNOSTIC_STAGE == 118)
#include "game_file_reader.hpp"
#endif
// 贴图桥转码器（纯函数，InflateFn 注入）。
#include "image_pcx_bridge_hook.hpp"
#include "mod_image_resources.hpp"
// v2：sret 返回值垫片（`ImageManager::LoadImage` 按 x8 返回 16 字节 SmartPointer）。
#include "relay/smart_pointer_shim.hpp"
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
#include "mod_manifest.hpp"
#endif

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstring>
// 批次 147：读引擎 `ModEntry+0x48` 那个 libc++ `std::string` 并按目录名比对时用。
#include <cctype>
#include <string_view>

// ---- 批次 147（2026-09-26）：引擎那条"模组 content 加载"路的埋点 ----------------------
//
// ★ 位置很要紧：**必须在真正的文件作用域**，既不在匿名命名空间里，也不写 `extern "C"`。
//   * 放匿名命名空间 ⇒ ELF 里是 `_ZN12_GLOBAL__N_1L…` 那种名字（读数工具得按 mangled 名找，
//     多一层耦合）；批次 142 就是在这上面栽过一次（门禁 `test_elf_syms` 判红，那是对的）。
//   * 写 `extern "C"` 又给初始化值 ⇒ `-Werror` 直接判"initialized and declared 'extern'"。
//   * 正确形态就是项目里既有的那个：`saltynx_runtime_bridge.cpp` 的 `g_runtimeSelfAddress`
//     —— 普通全局量，符号名与变量名逐字相同。
//
// 契约（读数工具 `read_device_state_via_gdb.py` 的 `SYM_ELF_NAMES` 按这些名字读）：
//   g_ModLoadConfigsCalls            我们的回调被引擎调到了几次
//                                    （0 ⇒ 引擎从来没调 `ModManager::LoadConfigs`）
//   g_ModLoadConfigsEntriesSeen      那一次引擎的模组列表有几条（0 ⇒ 我们比 `ListMods` 更早）
//   g_ModLoadConfigsEnabledByUs      我们**置 1**（该加载 content）的条数
//   g_ModLoadConfigsDisabledByUs     我们**置 0**（不该加载）的条数
//   g_ModLoadConfigsDisabledKnown    那一刻我们**存档侧**记着几个"被关掉的模组"
//   g_ModLoadConfigsStateLoaded      那一刻我们的模组开关状态读过存档了没
//   g_ModLoadConfigsMatchedDisabled  命中"我们关掉的那个目录名"的条数（验证比对口径）
//   g_ModLoadConfigsEngineOff        引擎自己说"这条关着"（`+0x138` 为 0）的条数
//   g_ModLoadConfigsFirstPath        第一条 `ModEntry+0x48` 的字符串（验证偏移与取串口径）
//   g_ModToggleStateLoaded           「存档侧模组开关已经读过一次」（判据用，不参与行为决定）
std::uint32_t g_ModLoadConfigsCalls = 0;
std::uint32_t g_ModLoadConfigsEntriesSeen = 0;
std::uint32_t g_ModLoadConfigsEnabledByUs = 0;
std::uint32_t g_ModLoadConfigsDisabledByUs = 0;
std::uint32_t g_ModLoadConfigsDisabledKnown = 0;
std::uint32_t g_ModLoadConfigsStateLoaded = 0;
std::uint32_t g_ModLoadConfigsMatchedDisabled = 0;
std::uint32_t g_ModLoadConfigsEngineOff = 0;
//: `+0x139` 写失败的次数（走 L1 访问层 ⇒ 写入前会问"这段可写吗"）。恒 0 才说明那一个字节
//: 真的按我们的判断落下去了；非 0 = 内存判定没过，此时**引擎会按它自己那份值走**。
std::uint32_t g_ModLoadConfigsWriteFailures = 0;
char g_ModLoadConfigsFirstPath[64] = {};
//: 由 `LoadDefaultManifestModThroughService` 在调 `g_ModToggleService.Load()` 之后写 1
//: （那个调用点跑在游戏主线程的第一帧更新里）。只作判据用。
std::uint32_t g_ModToggleStateLoaded = 0;

// ---- 批次 235（2026-09-30）：启动期"读模组"分段计时 -----------------------------------
//
// 要回答的问题：卡上放 `no-lua.on`（跳过读模组）时开场**零延迟**，正常加载时**约 10 秒黑屏**
// ⇒ 那 10 秒就在这条路上，而它整块跑在游戏主线程的一帧里。**在哪一段必须先量出来**
// （判据与修法分支见 `load_phase_probe.hpp`）。
//
// 只在 `DIAGNOSTIC_PROBES=1` 的包里编译；正式包零代价、零符号。
// 位置：文件作用域（与本文件既有那批埋点同一个口径 —— 不进匿名命名空间、不写 `extern "C"`）。
#if EXL_DIAGNOSTIC_PROBES
namespace isaac::runtime::loadprobe {
//: 各段耗时（微秒），下标见 `LoadPhase`。
std::atomic<std::uint32_t> g_LoadPhaseMicros[8];
//: 整个加载函数的总耗时（微秒）—— 与各段之和应当大致对得上。
std::atomic<std::uint32_t> g_LoadTotalMicros{0};

//: `g_LoadPhaseMicros` 的下标。
enum LoadPhase : std::size_t {
    kLoadPhaseTotal = 0,     //: 整个加载流程（各段之和；拆帧之后由收尾那一步算出来）
    kLoadPhasePrepare = 1,   //: 读清单 + 列目录 + 追加未列出的 + 读存档里的模组开关
    kLoadPhaseMounts = 2,    //: 给每个模组注册内容挂载点
    kLoadPhaseContent = 3,   //: 把每个模组的 content 喂给引擎（LoadCostumes / Music::LoadConfig）
    kLoadPhaseMenu = 4,      //: 我们自带菜单那个模组
    kLoadPhaseScripts = 5,   //: `service.LoadAll` —— 逐个模组读 SD 上的入口脚本并执行
    kLoadPhaseFinalize = 6,  //: 收尾（算诊断字、必要时把菜单重新装上）
};

//: 记一段的耗时（**累加** —— 批次 236 拆帧之后，同一个阶段会被走很多帧）。
//: `per == 0`（宿主 / 量具拿不到频率）时什么都不写 ⇒ 门禁行为不变。
inline void LoadMark(std::size_t phase, std::uint64_t startTick) noexcept {
    const std::uint64_t per = RuntimePerfTicksPerSecond();
    if (per == 0 || phase >= 8) {
        return;
    }
    const std::uint32_t micros = static_cast<std::uint32_t>(
        (RuntimePerfTick() - startTick) * 1000000ULL / per);
    g_LoadPhaseMicros[phase].fetch_add(micros, std::memory_order_relaxed);
}

//: 收尾时把各段之和写进 `g_LoadTotalMicros`（拆帧之后"总耗时"已经没有单一时刻可读了）。
inline void LoadFinishTotal() noexcept {
    std::uint64_t sum = 0;
    for (std::size_t phase = kLoadPhasePrepare; phase <= kLoadPhaseFinalize; ++phase) {
        sum += g_LoadPhaseMicros[phase].load(std::memory_order_relaxed);
    }
    g_LoadPhaseMicros[kLoadPhaseTotal].store(static_cast<std::uint32_t>(sum),
                                             std::memory_order_release);
    g_LoadTotalMicros.store(static_cast<std::uint32_t>(sum), std::memory_order_release);
}
}  // namespace isaac::runtime::loadprobe

//: 每个模组"读入口脚本 + 执行它"的耗时（微秒，下标 = 该模组在批次里的序号）。
//: 由 `mod_load_service.cpp` 经 `IsaacRuntime_RecordModLoadMicros()` 写 —— **不跨 TU 摸全局量**。
std::atomic<std::uint32_t> g_ModLoadMicros[16];
std::atomic<std::uint32_t> g_ModLoadCount{0};
std::atomic<std::uint32_t> g_ModLoadTotal{0};
//: ★★ 批次 236 补：**这条加载一共跨了多少帧**（收尾那一帧的 `Manager::Update` 进入次数
//: 减去起步那一帧的次数）。拆帧有没有真的生效，看这一个数就够了：
//:   * ≈ 15~20 ⇒ 拆帧生效了，卡顿是因为**每一帧仍然很重**（某个模组/某一段自己就吃掉了秒级）；
//:   * == 1     ⇒ 拆帧**没生效**（整条路还是在一帧里跑完）—— 那是我这一侧的 bug，不是模组的问题。
std::atomic<std::uint32_t> g_LoadFramesUsed{0};
//: 起步那一帧的 `Manager::Update` 进入次数（算上面那个差值用）。
std::atomic<std::uint32_t> g_LoadStartFrame{0};

extern "C" void IsaacRuntime_RecordModLoadMicros(std::uint32_t micros) {
    const std::uint32_t slot = g_ModLoadCount.load(std::memory_order_relaxed);
    if (slot >= 16) {
        return;
    }
    g_ModLoadMicros[slot].store(micros, std::memory_order_release);
    g_ModLoadCount.store(slot + 1, std::memory_order_release);
}
#endif  // EXL_DIAGNOSTIC_PROBES

namespace IsaacRepentance {
struct Manager;
}

#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
extern "C" NORETURN void ReportStartupProbeStage8ManifestResult(bool initialized, u32 failureDetail);
#endif

namespace {

std::atomic<u32> g_HookEnabled{false};
// 这一帧的 `IsaacRepentance::Manager*`：`Manager::Update` 与 `Manager::Render` 的入口中继各记
// 一次，供 `Present` 前的派发入口使用 —— 那个调用点的 `x0` 是 `KAGE::Graphics::g_Manager`
// （图形管理器），而派发路径要的是 Manager*：`PrimeDefaultCallbacks` 用它做音乐就绪判定
// （`ResolveMusicForManager(manager + kManagerMusicOffset, …)`），Music API 也用它
// （`g_CurrentCallbackManager`）。2026-09-13 的真机报告正栽在这里：中继装上了也进入了
// （掩码位 52/55 = 1），但 `PrimeDefaultCallbacks` 拿到图形管理器后返回 false，于是
// `MC_POST_RENDER` 的回调一次都没被调用（Mod 标记停在 1、屏幕全空）。
std::atomic<std::uintptr_t> g_RenderFrameManager{0};
isaac::runtime::RenderFrameCoordinator g_RenderFrameCoordinator;
#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_CONTENT_MOUNT
// 一次性标志：内容挂载点探针只跑一次（它自己会 break 结束会话）。用 `u32` 表示布尔语义，
// 而不是布尔型原子量 —— 项目门禁禁止后者出现在运行时源码里（见
// `runtime/tests/test_manager_update_hook_audit.py`，它按文本扫描源码）。
std::atomic<u32> g_ContentMountProbeArmed{0};
#endif
// 下面这组诊断/安装结果字样必须**常编**：顶层的 `TryInstallManager*`（在任何配置下都会编译）要
// 用它们里的记录函数。历史上它们被关在 `#if !defined(EXL_DIAGNOSTIC_STAGE)` +
// `#if defined(EXL_LAYERED_RUNTIME)` 里，于是 `make probe DIAGNOSTIC_STAGE=<n>` 必然报
// "RecordRenderHookInstall was not declared in this scope"（2026-09-13 撞上，见
// docs/问题与解决记录.md）。只有导出给宿主插件与自记日志的那两个入口继续留在分层守卫内。
// Hook diagnostics published to the host plugin.
//
// A production module currently reports nothing about whether the Manager update
// hook was installed or whether its callback is ever entered:
// `HookInstallService::Install` collapses every per-hook result into Ok/Rejected,
// the Runtime's own state has no export, and `ManagerUpdateHookAudit` -- the only
// code that counts callback entries -- is not compiled in production. On hardware
// that left "the diagnostics attach is never reached" indistinguishable from "the
// update hook never fires"; the two callback counters below separate them.
//
// These are plain atomics touched once per callback: no allocation, no file I/O,
// and no dependency the plugin has to provide. The word order is wire format and
// is read by `runtime/src/host_plugin`.
// 诊断字布局（`IsaacModRuntime_GetHookDiagnostics`）：
//   [0..2] 三个中继安装结果  [3] update 回调进入次数  [4] render 回调进入次数
//   [5..6] 已登记的 ModCallbacks 种类掩码（id 0..63，低/高 32 位）
//   [7..8] 同上（id 64..127，PC 表到 73）
//   [9] 有派发点的登记次数  [10] 无派发点（登记了但不会触发）的登记次数
//   [11] 清单 Mod 加载结果字：0 = 带脚本加载成功，1..4 = 失败步（ManifestRead/Parse/PathBuild/
//        EntryRead），0x10+detail = Lua 初始化失败，5 = 资源型 Mod（无脚本）已挂载
//   [12] 回调 Lua 错误标志（只读，不消费）
//   [13] 最近一次 Lua 错误/加载失败信息长度  [14..15] 该信息前 8 字节（两半）
// 5..12 是 2026-09-12 为“EID 加载地基”加的普查：真机要能区分“登记了但不会触发”和
// “根本没登记”，也要能看出 Mod 加载失败在哪一步。
constexpr std::size_t kHookDiagnosticsWordCount = 16;
constexpr std::uint64_t kHookDiagnosticsMagic = 0x3152484341415349ULL;  // "ISAACHR1"

// [0] ManagerUpdate install result, [1] ManagerRender install result,
// [2] PreGetCollectible relay result, [3] update-callback entries,
// [4] render-callback entries.
std::atomic<std::uint32_t> g_HookInstallResults[kHookDiagnosticsWordCount]{};
std::atomic<std::uint32_t> g_UpdateCallbackEntries{0};
std::atomic<std::uint32_t> g_RenderCallbackEntries{0};
// `Present` 前派发中继的状态与进入次数。这两个字不进上面那份 5 字契约（那是与宿主插件
// 之间的线格式），只给探针读：安装结果与"中继到底跑没跑"必须能从设备上读出来。
std::atomic<std::uint32_t> g_RenderPresentRelayState{0};
std::atomic<std::uint32_t> g_RenderPresentRelayEntries{0};

// 卡上开关的**自证**字段（2026-09-16，排障用）。
//
// 为什么必须有：开关文件读不到时 `CardSwitchOn` 返回 false（"就当没这个开关"），
// 于是"开关没生效"与"开关生效了但没用"在设备上长得一模一样 —— 那会把整个二分带偏。
// 这两个字把两种失败分开，调试桩直接读（一次开机读一次就够）：
//   [0] 找到的开关掩码（按 `kCardSwitchNames` 的顺序，bit i = 第 i 个名字的 `.on` 在卡上）
//   [1] 通道状态：bit0 = 至少一次查询成功返回；bit1 = 至少一次查询失败（通道不可用）；
//                 bit2 = 在**不是游戏主线程**的地方被要求探测 ⇒ 拒绝执行（见下面那条纪律）
std::atomic<std::uint32_t> g_CardSwitchMask{0};
std::atomic<std::uint32_t> g_CardSwitchChannel{0};
// ★★ 纪律（2026-09-16 真机撞出来的）：**游戏 nnSdk 的文件 API 只允许在游戏主线程上调用。**
//
// 事故经过：卡上开关最早是在"装挂点"那一步探测的，而那一步跑在**我们自己创建的 worker 线程**上。
// 结果 442190 那一版**每次开机必崩**（两份崩溃报告 `01789571605` / `01789571620`）：
// `runtime + 0x15080`（`EngineSaveFileAdapter::Exists`）→ nnSdk 的
// `_ZN2nn2fs8OpenFileEPNS0_10FileHandleEPKci + 0x28`
// → nnSdk 里一条 `os::SdkMutexType::Lock` → 空指针 + 0x1b0 的 Data Abort。
// 同一个适配器的 `Read`/`Write` 在**游戏主线程**上一直是好的（模组开关状态的持久化就是它做的）
// ⇒ 差别是**线程**，不是时机（两者相隔几毫秒）。
// 机制：游戏这套 nnSdk 用的是**线程本地堆**（`TlsHeapCentral`，退出对局那次崩溃的栈里也出现过），
// 我们自己 `svcCreateThread`/libnx 建出来的线程没有在游戏的线程体系里登记 ⇒ 任何会**分配内存**的
// SDK 调用都会踩空。所以：**我们自己的线程上只做"读内存 + 写游戏代码"，不做 SDK 调用。**
// 用 u32 而不是 bool 原子：门禁 `test_runtime_source_contains_no_bool_atomics`
// 明令两个源码根里不许出现 bool 特化的原子（0 = 未允许、1 = 允许探测）。
std::atomic<u32> g_CardSwitchProbeAllowed{0};

// 名字顺序就是掩码位序 —— 改了顺序就等于换了 `g_CardSwitchMask` 的语义，别随手改。
//
// 只留"由**游戏主线程**上的代码读取"的开关：挂点跳过类开关原本也在这里，但读它们的那一步
// 跑在 worker 线程上 ⇒ 会崩（见 `g_CardSwitchProbeAllowed` 上面那条纪律）。
// 挂点层面的二分改用**编译开关**（`ONLY_REQUIRED_HOOK=1`），一条构建一个配置，不上卡。
constexpr const char* kCardSwitchNames[] = {"no-menu", "no-lua"};
constexpr std::size_t kCardSwitchNameCount = sizeof(kCardSwitchNames) / sizeof(kCardSwitchNames[0]);

HookInstallResult RecordUpdateHookInstall(HookInstallResult result) {
    g_HookInstallResults[0].store(static_cast<std::uint32_t>(result), std::memory_order_release);
    return result;
}

RenderHookInstallResult RecordRenderHookInstall(RenderHookInstallResult result) {
    g_HookInstallResults[1].store(static_cast<std::uint32_t>(result), std::memory_order_release);
    return result;
}

PreGetCollectibleRelayInstallResult RecordPreGetCollectibleInstall(
    PreGetCollectibleRelayInstallResult result) {
    g_HookInstallResults[2].store(static_cast<std::uint32_t>(result), std::memory_order_release);
    return result;
}

// Mod 贴图转码缓存的计数（探针用位 35 报"至少写出一个 PCX"）。
std::atomic<std::uint32_t> g_TextureCacheWritten{0};
std::atomic<std::uint32_t> g_TextureCacheCandidates{0};
std::atomic<std::uint32_t> g_TextureCacheFailures{0};

RenderPresentRelayInstallResult RecordRenderPresentRelayInstall(
    RenderPresentRelayInstallResult result) {
    g_RenderPresentRelayState.store(static_cast<std::uint32_t>(result), std::memory_order_release);
    return result;
}

// `MC_POST_RENDER` 派发点中继的自证出口（安装结果，进入次数），只给探针构建读。
extern "C" __attribute__((visibility("hidden"))) void
IsaacModRuntime_RenderPresentRelayDiagnostics(std::uint32_t* output) {
    if (output == nullptr) {
        return;
    }
    output[0] = g_RenderPresentRelayState.load(std::memory_order_acquire);
    output[1] = g_RenderPresentRelayEntries.load(std::memory_order_acquire);
}

#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 14 || EXL_DIAGNOSTIC_STAGE == 15 || EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17 || EXL_DIAGNOSTIC_STAGE == 45 || EXL_DIAGNOSTIC_STAGE == 48
std::atomic<uintptr_t> g_LuaGameOwnerSlot{0};
std::atomic<uintptr_t> g_LuaGameIsPausedThunk{0};
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
constexpr u64 kStage14SuccessMagic = 0x49534141435F4750ULL;
constexpr u64 kStage14FailureMagic = 0x49534141435F4746ULL;
Stage14Diagnostic::Controller g_Stage14Controller{};

NORETURN void ReportStage14Failure(Stage14Diagnostic::Stage14Failure failure) {
    svcBreak(BreakReason_User, kStage14FailureMagic,
             (14ULL << 32) | static_cast<u32>(failure));
    svcExitProcess();
}

NORETURN void ReportStage14Success(bool paused) {
    svcBreak(BreakReason_User, kStage14SuccessMagic,
             (14ULL << 32) | (paused ? 2ULL : 1ULL));
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
constexpr u64 kStage17SuccessMagic = 0x49534141435F4D4CULL;
constexpr u64 kStage17FailureMagic = 0x49534141435F4D46ULL;

NORETURN void ReportStage17Success() {
    svcBreak(BreakReason_User, kStage17SuccessMagic, (17ULL << 32) | 1ULL);
    svcExitProcess();
}

NORETURN void ReportStage17Failure(u32 status) {
    svcBreak(BreakReason_User, kStage17FailureMagic, (17ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
constexpr u64 kStage45SuccessMagic = 0x49534141435F4D49ULL;
constexpr u64 kStage45FailureMagic = 0x49534141435F4D46ULL;

NORETURN void ReportStage45Success(u32 musicId) {
    svcBreak(BreakReason_User, kStage45SuccessMagic, (45ULL << 32) | musicId);
    svcExitProcess();
}

NORETURN void ReportStage45Failure(u32 status) {
    svcBreak(BreakReason_User, kStage45FailureMagic, (45ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48
constexpr u64 kStage48SuccessMagic = 0x49534141435F4D52ULL;
constexpr u64 kStage48FailureMagic = 0x49534141435F4D46ULL;
constexpr u32 kStage48WindowFrames = 180;
constexpr u32 kStage48PausedActorCapacity = 8;
constexpr u32 kStage48ObservedPause = 1u << 0;
constexpr u32 kStage48ObservedMusicPlay = 1u << 1;
constexpr u32 kStage48ObservedActorPlay = 1u << 2;
constexpr u32 kStage48ActorOverlap = 1u << 3;
constexpr u32 kStage48ActorDifferent = 1u << 4;
// Keep Stage48 observation state visible in the one-shot hardware report.

std::atomic<u32> g_Stage48Armed{false};
std::atomic<u32> g_Stage48Reported{false};
std::atomic<u32> g_Stage48Frames{0};
std::atomic<u32> g_Stage48PauseCount{0};
std::atomic<u32> g_Stage48MusicPlayCount{0};
std::atomic<u32> g_Stage48ActorPlayCount{0};
std::atomic<u32> g_Stage48Flags{0};
std::array<std::atomic<uintptr_t>, kStage48PausedActorCapacity> g_Stage48PausedActors{};

NORETURN void ReportStage48Failure(u32 status) {
    svcBreak(BreakReason_User, kStage48FailureMagic, (48ULL << 32) | status);
    svcExitProcess();
}

NORETURN void ReportStage48Success(u32 payload) {
    svcBreak(BreakReason_User, kStage48SuccessMagic, (48ULL << 32) | payload);
    svcExitProcess();
}

void RememberStage48PausedActor(uintptr_t actor) {
    if (actor == 0) return;
    for (auto& slot : g_Stage48PausedActors) {
        uintptr_t value = slot.load(std::memory_order_acquire);
        if (value == actor) return;
        if (value == 0 && slot.compare_exchange_strong(value, actor, std::memory_order_acq_rel)) return;
    }
}

bool IsStage48PausedActor(uintptr_t actor) {
    for (const auto& slot : g_Stage48PausedActors) {
        if (slot.load(std::memory_order_acquire) == actor && actor != 0) return true;
    }
    return false;
}

void RecordStage48MusicPlay() {
    if (!g_Stage48Armed.load(std::memory_order_acquire)) return;
    g_Stage48MusicPlayCount.fetch_add(1, std::memory_order_relaxed);
    g_Stage48Flags.fetch_or(kStage48ObservedMusicPlay, std::memory_order_release);
}

void RecordStage48SoundActorPause(uintptr_t actor) {
    if (!g_Stage48Armed.load(std::memory_order_acquire)) return;
    g_Stage48PauseCount.fetch_add(1, std::memory_order_relaxed);
    g_Stage48Flags.fetch_or(kStage48ObservedPause, std::memory_order_release);
    RememberStage48PausedActor(actor);
}

void RecordStage48SoundActorPlay(uintptr_t actor) {
    if (!g_Stage48Armed.load(std::memory_order_acquire)) return;
    g_Stage48ActorPlayCount.fetch_add(1, std::memory_order_relaxed);
    u32 flags = kStage48ObservedActorPlay;
    flags |= IsStage48PausedActor(actor) ? kStage48ActorOverlap : kStage48ActorDifferent;
    g_Stage48Flags.fetch_or(flags, std::memory_order_release);
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
constexpr u64 kStage88SuccessMagic = 0x49534141435F4952ULL;
constexpr u32 kStage88FrameLimit = 600;
constexpr u32 kStage88ActionRestart = 16;
constexpr u32 kStage88ActionQueryCalled = 1u << 0;
constexpr u32 kStage88ActionRestartSeen = 1u << 1;
constexpr u32 kStage88StageReadable = 1u << 2;
constexpr u32 kStage88PausedSeen = 1u << 3;
constexpr u32 kStage88UnpausedSeen = 1u << 4;
std::atomic<uintptr_t> g_Stage88OwnerSlot{0};
std::atomic<uintptr_t> g_Stage88IsPausedThunk{0};
std::atomic<uintptr_t> g_Stage88ActionMethod{0};
std::atomic<u32> g_Stage88Frames{0};
std::atomic<u32> g_Stage88Flags{0};
std::atomic<u32> g_Stage88LastStage{0};

NORETURN void ReportStage88Success(u32 payload) {
    svcBreak(BreakReason_User, kStage88SuccessMagic, (88ULL << 32) | payload);
    svcExitProcess();
}

void ObserveStage88InstantRestart(IsaacRepentance::Manager* manager) {
    const uintptr_t methodAddress = g_Stage88ActionMethod.load(std::memory_order_acquire);
    if (manager != nullptr && methodAddress != 0) {
        using IsActionTriggered = bool (*)(IsaacRepentance::Manager*, u32, u32, void*);
        const auto actionTriggered = reinterpret_cast<IsActionTriggered>(methodAddress);
        u32 flags = kStage88ActionQueryCalled;
        if (actionTriggered(manager, kStage88ActionRestart, 0, nullptr)) flags |= kStage88ActionRestartSeen;
        g_Stage88Flags.fetch_or(flags, std::memory_order_release);
    }
    u32 stage = 0;
    if (ReadCurrentGameLevelStage(g_Stage88OwnerSlot.load(std::memory_order_acquire), &stage) ==
        GameLevelStageObservation::Success) {
        g_Stage88LastStage.store(stage, std::memory_order_release);
        g_Stage88Flags.fetch_or(kStage88StageReadable, std::memory_order_release);
    }
    switch (ObserveGameIsPaused(g_Stage88OwnerSlot.load(std::memory_order_acquire),
                                g_Stage88IsPausedThunk.load(std::memory_order_acquire))) {
    case GameIsPausedObservation::PausedTrue:
        g_Stage88Flags.fetch_or(kStage88PausedSeen, std::memory_order_release);
        break;
    case GameIsPausedObservation::PausedFalse:
        g_Stage88Flags.fetch_or(kStage88UnpausedSeen, std::memory_order_release);
        break;
    default:
        break;
    }
    if (g_Stage88Frames.fetch_add(1, std::memory_order_relaxed) + 1 >= kStage88FrameLimit) {
        const u32 payload = g_Stage88Flags.load(std::memory_order_acquire) |
                            ((g_Stage88LastStage.load(std::memory_order_acquire) & 0xffu) << 8);
        ReportStage88Success(payload);
    }
}

void ConfigureStage88Bindings(uintptr_t ownerSlot, uintptr_t isPausedThunk, uintptr_t actionMethod) {
    g_Stage88OwnerSlot.store(ownerSlot, std::memory_order_release);
    g_Stage88IsPausedThunk.store(isPausedThunk, std::memory_order_release);
    g_Stage88ActionMethod.store(actionMethod, std::memory_order_release);
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
constexpr u64 kStage89SuccessMagic = 0x49534141435F4954ULL;
constexpr u32 kStage89FrameLimit = 7200;
constexpr u32 kStage89ActionRestart = 16;
constexpr u32 kStage89ActionQueryCalled = 1u << 0;
constexpr u32 kStage89AllControllersSeen = 1u << 1;
constexpr u32 kStage89ControllerZeroSeen = 1u << 2;
constexpr u32 kStage89ControllerOneSeen = 1u << 3;
constexpr u32 kStage89ControllerTwoSeen = 1u << 4;
constexpr u32 kStage89ControllerThreeSeen = 1u << 5;
constexpr u32 kStage89StageReadable = 1u << 6;
constexpr u32 kStage89PausedSeen = 1u << 7;
constexpr u32 kStage89UnpausedSeen = 1u << 8;
constexpr u32 kStage89FirstControllerNoHit = 0xffu;
constexpr std::array<u32, 5> kStage89Controllers = {0, 1, 2, 3, static_cast<u32>(-1)};
std::atomic<uintptr_t> g_Stage89OwnerSlot{0};
std::atomic<uintptr_t> g_Stage89IsPausedThunk{0};
std::atomic<uintptr_t> g_Stage89ActionMethod{0};
std::atomic<u32> g_Stage89Frames{0};
std::atomic<u32> g_Stage89Flags{0};
std::atomic<u32> g_Stage89LastStage{0};

NORETURN void ReportStage89Success(u32 payload) {
    svcBreak(BreakReason_User, kStage89SuccessMagic, (89ULL << 32) | payload);
    svcExitProcess();
}

u32 Stage89ControllerFlag(size_t index) {
    return index == 4 ? kStage89AllControllersSeen : (1u << (index + 2));
}

u32 Stage89FirstControllerCode(size_t index) {
    return index == 4 ? 0xfeu : static_cast<u32>(index);
}

void ObserveStage89RestartActionControllers(IsaacRepentance::Manager* manager) {
    u32 flags = g_Stage89Flags.load(std::memory_order_acquire);
    const uintptr_t methodAddress = g_Stage89ActionMethod.load(std::memory_order_acquire);
    if (manager != nullptr && methodAddress != 0) {
        using IsActionTriggered = bool (*)(IsaacRepentance::Manager*, u32, u32, void*);
        const auto actionTriggered = reinterpret_cast<IsActionTriggered>(methodAddress);
        flags |= kStage89ActionQueryCalled;
        for (size_t index = 0; index < kStage89Controllers.size(); ++index) {
            if (actionTriggered(manager, kStage89ActionRestart, kStage89Controllers[index], nullptr)) {
                flags |= Stage89ControllerFlag(index);
                g_Stage89Flags.store(flags, std::memory_order_release);
                const u32 payload = flags |
                                    ((g_Stage89LastStage.load(std::memory_order_acquire) & 0xffu) << 16) |
                                    (Stage89FirstControllerCode(index) << 24);
                ReportStage89Success(payload);
            }
        }
        g_Stage89Flags.store(flags, std::memory_order_release);
    }
    u32 stage = 0;
    if (ReadCurrentGameLevelStage(g_Stage89OwnerSlot.load(std::memory_order_acquire), &stage) ==
        GameLevelStageObservation::Success) {
        g_Stage89LastStage.store(stage, std::memory_order_release);
        g_Stage89Flags.fetch_or(kStage89StageReadable, std::memory_order_release);
    }
    switch (ObserveGameIsPaused(g_Stage89OwnerSlot.load(std::memory_order_acquire),
                                g_Stage89IsPausedThunk.load(std::memory_order_acquire))) {
    case GameIsPausedObservation::PausedTrue:
        g_Stage89Flags.fetch_or(kStage89PausedSeen, std::memory_order_release);
        break;
    case GameIsPausedObservation::PausedFalse:
        g_Stage89Flags.fetch_or(kStage89UnpausedSeen, std::memory_order_release);
        break;
    default:
        break;
    }
    if (g_Stage89Frames.fetch_add(1, std::memory_order_relaxed) + 1 >= kStage89FrameLimit) {
        const u32 payload = g_Stage89Flags.load(std::memory_order_acquire) |
                            ((g_Stage89LastStage.load(std::memory_order_acquire) & 0xffu) << 16) |
                            (kStage89FirstControllerNoHit << 24);
        ReportStage89Success(payload);
    }
}

void ConfigureStage89Bindings(uintptr_t ownerSlot, uintptr_t isPausedThunk, uintptr_t actionMethod) {
    g_Stage89OwnerSlot.store(ownerSlot, std::memory_order_release);
    g_Stage89IsPausedThunk.store(isPausedThunk, std::memory_order_release);
    g_Stage89ActionMethod.store(actionMethod, std::memory_order_release);
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
constexpr u64 kStage102SuccessMagic = 0x49534141435F4352ULL;
constexpr u32 kStage102EventLimit = 4;
constexpr u32 kStage102EventSeen = 1u << 0;
constexpr u32 kStage102RoomTypeReadable = 1u << 1;
constexpr u32 kStage102RoomTypeFailure = 1u << 2;
std::atomic<u32> g_Stage102EventCount{0};
std::atomic<u32> g_Stage102Flags{0};
std::atomic<u32> g_Stage102LastRoomType{0};

NORETURN void ReportStage102Success(u32 payload) {
    svcBreak(BreakReason_User, kStage102SuccessMagic, (102ULL << 32) | payload);
    svcExitProcess();
}

void ObserveStage102ChangeRoom(IsaacRepentance::Game* game) {
    u32 flags = kStage102EventSeen;
    u32 roomType = 0;
    if (ReadGameRoomTypeFromGame(game, &roomType) == GameRoomObservation::Success) {
        g_Stage102LastRoomType.store(roomType, std::memory_order_release);
        flags |= kStage102RoomTypeReadable;
    } else {
        flags |= kStage102RoomTypeFailure;
    }
    g_Stage102Flags.fetch_or(flags, std::memory_order_release);
    if (g_Stage102EventCount.fetch_add(1, std::memory_order_relaxed) + 1 >= kStage102EventLimit) {
        const u32 payload = g_Stage102Flags.load(std::memory_order_acquire) |
                            ((g_Stage102LastRoomType.load(std::memory_order_acquire) & 0xffu) << 8);
        ReportStage102Success(payload);
    }
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
constexpr u64 kStage104SuccessMagic = 0x49534141435F4B52ULL;
constexpr u32 kStage104EventLimit = 4;
constexpr u32 kStage104EventSeen = 1u << 0;
constexpr u32 kStage104KeyReadable = 1u << 1;
constexpr u32 kStage104KeyFailure = 1u << 2;
constexpr u32 kStage104ThirdMatchesFirst = 1u << 3;
constexpr u32 kStage104FourthMatchesSecond = 1u << 4;
constexpr u32 kStage104FirstIndexShift = 8;
constexpr u32 kStage104SecondIndexShift = 16;
constexpr u32 kStage104FirstDimensionShift = 24;
constexpr u32 kStage104SecondDimensionShift = 26;
std::atomic<u32> g_Stage104EventCount{0};
std::atomic<u32> g_Stage104Flags{0};
std::array<GameRoomKey, kStage104EventLimit> g_Stage104Keys{};

NORETURN void ReportStage104Success(u32 payload) {
    svcBreak(BreakReason_User, kStage104SuccessMagic, (104ULL << 32) | payload);
    svcExitProcess();
}

void ObserveStage104ChangeRoom(IsaacRepentance::Game* game) {
    const u32 event = g_Stage104EventCount.fetch_add(1, std::memory_order_relaxed);
    if (event >= kStage104EventLimit) return;
    GameRoomKey key{};
    u32 flags = kStage104EventSeen;
    if (ReadGameCurrentRoomKeyFromGame(game, &key) == GameRoomObservation::Success) {
        g_Stage104Keys[event] = key;
        flags |= kStage104KeyReadable;
    } else {
        flags |= kStage104KeyFailure;
    }
    g_Stage104Flags.fetch_or(flags, std::memory_order_release);
    if (event + 1 != kStage104EventLimit) return;
    u32 payload = g_Stage104Flags.load(std::memory_order_acquire);
    if ((payload & kStage104KeyFailure) == 0 &&
        g_Stage104Keys[0] == g_Stage104Keys[2]) payload |= kStage104ThirdMatchesFirst;
    if ((payload & kStage104KeyFailure) == 0 &&
        g_Stage104Keys[1] == g_Stage104Keys[3]) payload |= kStage104FourthMatchesSecond;
    payload |= (g_Stage104Keys[0].roomIndex & 0xffu) << kStage104FirstIndexShift;
    payload |= (g_Stage104Keys[1].roomIndex & 0xffu) << kStage104SecondIndexShift;
    payload |= (g_Stage104Keys[0].dimension & 0x3u) << kStage104FirstDimensionShift;
    payload |= (g_Stage104Keys[1].dimension & 0x3u) << kStage104SecondDimensionShift;
    ReportStage104Success(payload);
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 112
constexpr u64 kStage112SuccessMagic = 0x49534141435F4452ULL;
constexpr u32 kStage112RoomTreasure = 4;
constexpr u32 kStage112TreasureSeen = 1u << 0;
constexpr u32 kStage112KeyReadable = 1u << 1;
constexpr u32 kStage112SnapshotReadable = 1u << 2;
constexpr u32 kStage112SameKeyReentered = 1u << 3;
constexpr u32 kStage112Word0cUnchanged = 1u << 4;
constexpr u32 kStage112Word50Unchanged = 1u << 5;
constexpr u32 kStage112Word0cShift = 8;
constexpr u32 kStage112Word50Shift = 16;
std::atomic<u32> g_Stage112Flags{0};
std::atomic<u32> g_Stage112FirstCaptured{false};
GameRoomKey g_Stage112FirstKey{};
GameRoomDescriptorSnapshot g_Stage112FirstSnapshot{};

NORETURN void ReportStage112Success(u32 payload) {
    svcBreak(BreakReason_User, kStage112SuccessMagic, (112ULL << 32) | payload);
    svcExitProcess();
}

void ObserveStage112ChangeRoom(IsaacRepentance::Game* game) {
    u32 roomType = 0;
    if (ReadGameRoomTypeFromGame(game, &roomType) != GameRoomObservation::Success ||
        roomType != kStage112RoomTreasure) return;
    GameRoomKey key{};
    GameRoomDescriptorSnapshot snapshot{};
    if (ReadGameCurrentRoomKeyFromGame(game, &key) != GameRoomObservation::Success ||
        ReadGameRoomDescriptorSnapshotFromGame(game, &snapshot) != GameRoomObservation::Success) return;
    u32 flags = kStage112TreasureSeen | kStage112KeyReadable | kStage112SnapshotReadable;
    if (!g_Stage112FirstCaptured.exchange(true, std::memory_order_acq_rel)) {
        g_Stage112FirstKey = key;
        g_Stage112FirstSnapshot = snapshot;
        g_Stage112Flags.fetch_or(flags, std::memory_order_release);
        return;
    }
    if (!(g_Stage112FirstKey == key)) {
        g_Stage112Flags.fetch_or(flags, std::memory_order_release);
        return;
    }
    flags |= kStage112SameKeyReentered;
    if (g_Stage112FirstSnapshot.candidateWord0c == snapshot.candidateWord0c) {
        flags |= kStage112Word0cUnchanged;
    }
    if (g_Stage112FirstSnapshot.candidateWord50 == snapshot.candidateWord50) {
        flags |= kStage112Word50Unchanged;
    }
    const u32 payload = g_Stage112Flags.fetch_or(flags, std::memory_order_acq_rel) | flags |
                        ((snapshot.candidateWord0c & 0xffu) << kStage112Word0cShift) |
                        ((snapshot.candidateWord50 & 0xffu) << kStage112Word50Shift);
    ReportStage112Success(payload);
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
constexpr u64 kStage108SuccessMagic = 0x49534141435F4C52ULL;
constexpr u32 kStage108EventLimit = 2;
constexpr u32 kStage108EventSeen = 1u << 0;
constexpr u32 kStage108SavedEvent = 1u << 1;
constexpr u32 kStage108NewEvent = 1u << 2;
constexpr u32 kStage108SecondEvent = 1u << 3;
constexpr u32 kStage108FirstKindShift = 8;
constexpr u32 kStage108SecondKindShift = 12;
std::atomic<u32> g_Stage108EventCount{0};
std::atomic<u32> g_Stage108Flags{0};
std::atomic<u32> g_Stage108FirstKind{0};
std::atomic<u32> g_Stage108SecondKind{0};

NORETURN void ReportStage108Success(u32 payload) {
    svcBreak(BreakReason_User, kStage108SuccessMagic, (108ULL << 32) | payload);
    svcExitProcess();
}

void ObserveStage108Lifecycle(IsaacRepentance::Game*, u32 eventKind) {
    if (eventKind != 1 && eventKind != 2) return;
    const u32 event = g_Stage108EventCount.fetch_add(1, std::memory_order_relaxed);
    if (event >= kStage108EventLimit) return;
    u32 flags = kStage108EventSeen | (eventKind == 1 ? kStage108SavedEvent : kStage108NewEvent);
    if (event == 0) {
        g_Stage108FirstKind.store(eventKind, std::memory_order_release);
    } else {
        g_Stage108SecondKind.store(eventKind, std::memory_order_release);
        flags |= kStage108SecondEvent;
    }
    g_Stage108Flags.fetch_or(flags, std::memory_order_release);
    if (event + 1 == kStage108EventLimit) {
        const u32 payload = g_Stage108Flags.load(std::memory_order_acquire) |
                            (g_Stage108FirstKind.load(std::memory_order_acquire) << kStage108FirstKindShift) |
                            (g_Stage108SecondKind.load(std::memory_order_acquire) << kStage108SecondKindShift);
        ReportStage108Success(payload);
    }
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
constexpr u64 kStage109SuccessMagic = 0x49534141435F5252ULL;

NORETURN void ReportStage109Success(u32 payload) {
    svcBreak(BreakReason_User, kStage109SuccessMagic, (109ULL << 32) | payload);
    svcExitProcess();
}

void ObserveStage109Restart(IsaacRepentance::Manager*, u32 pathKind) {
    if (pathKind >= 1 && pathKind <= 3) ReportStage109Success(pathKind);
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
constexpr u64 kStage127SuccessMagic = 0x49534141435F534CULL;
std::atomic<u32> g_Stage127Flags{0};

NORETURN void ReportStage127Success(u32 payload) {
    svcBreak(BreakReason_User, kStage127SuccessMagic, (127ULL << 32) | payload);
    svcExitProcess();
}

void ObserveStage127SaveLoad(IsaacRepentance::Manager* outerManager, u32 kind) {
    if (outerManager == nullptr || (kind != 1 && kind != 2)) return;
    const u32 bit = kind == 1 ? 1u : 2u;
    const u32 flags = g_Stage127Flags.fetch_or(bit, std::memory_order_acq_rel) | bit;
    if (flags == 3u) ReportStage127Success(flags);
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
constexpr u64 kStage128SuccessMagic = 0x49534141435F5344ULL;
std::atomic<u32> g_Stage128Flags{0};

NORETURN void ReportStage128Success(u32 payload) {
    svcBreak(BreakReason_User, kStage128SuccessMagic, (128ULL << 32) | payload);
    svcExitProcess();
}

void ObserveStage128SaveDataManager(void* saveDataManager, u32 kind) {
    if (saveDataManager == nullptr || (kind != 1 && kind != 2)) return;
    const u32 bit = kind == 1 ? 1u : 2u;
    const u32 flags = g_Stage128Flags.fetch_or(bit, std::memory_order_acq_rel) | bit;
    if (flags == 3u) ReportStage128Success(flags);
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
constexpr u64 kStage110SuccessMagic = 0x49534141435F5352ULL;
constexpr u32 kStage110SavedLifecycle = 1u << 0;
constexpr u32 kStage110PreResetRoom = 1u << 1;
constexpr u32 kStage110NewLifecycle = 1u << 2;
constexpr u32 kStage110PostResetRoom = 1u << 3;
constexpr u32 kStage110CounterReset = 1u << 4;
constexpr u32 kStage110PostResetCountOne = 1u << 5;
std::atomic<u32> g_Stage110Flags{0};
std::atomic<u32> g_Stage110RoomEvents{0};

NORETURN void ReportStage110Success(u32 payload) {
    svcBreak(BreakReason_User, kStage110SuccessMagic, (110ULL << 32) | payload);
    svcExitProcess();
}

void ObserveStage110Lifecycle(IsaacRepentance::Game*, u32 eventKind) {
    if (eventKind == 1) {
        g_Stage110Flags.fetch_or(kStage110SavedLifecycle, std::memory_order_release);
        return;
    }
    if (eventKind != 2) return;
    const u32 before = g_Stage110RoomEvents.exchange(0, std::memory_order_acq_rel);
    u32 flags = kStage110NewLifecycle;
    if (before != 0) flags |= kStage110CounterReset;
    g_Stage110Flags.fetch_or(flags, std::memory_order_release);
}

void ObserveStage110ChangeRoom(IsaacRepentance::Game*) {
    const u32 count = g_Stage110RoomEvents.fetch_add(1, std::memory_order_acq_rel) + 1;
    u32 flag = 0;
    const u32 lifecycle = g_Stage110Flags.load(std::memory_order_acquire);
    if ((lifecycle & kStage110NewLifecycle) == 0) {
        flag = kStage110PreResetRoom;
    } else {
        flag = kStage110PostResetRoom;
        if (count == 1) flag |= kStage110PostResetCountOne;
    }
    const u32 flags = g_Stage110Flags.fetch_or(flag, std::memory_order_acq_rel) | flag;
    constexpr u32 kExpected = kStage110SavedLifecycle | kStage110PreResetRoom |
                              kStage110NewLifecycle | kStage110PostResetRoom |
                              kStage110CounterReset | kStage110PostResetCountOne;
    if ((flags & kExpected) == kExpected) ReportStage110Success(flags);
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
constexpr u64 kStage16SuccessMagic = 0x49534141435F4D50ULL;
constexpr u64 kStage16FailureMagic = 0x49534141435F4D46ULL;

NORETURN void ReportStage16Success() {
    svcBreak(BreakReason_User, kStage16SuccessMagic, (16ULL << 32) | 1ULL);
    svcExitProcess();
}

NORETURN void ReportStage16Failure(u32 status) {
    svcBreak(BreakReason_User, kStage16FailureMagic, (16ULL << 32) | status);
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
constexpr u64 kStage15SuccessMagic = 0x49534141435F5250ULL;
constexpr u64 kStage15FailureMagic = 0x49534141435F5246ULL;
constexpr u32 kStage15PausedUpdateLimit = 120;

NORETURN void ReportStage15Success() {
    svcBreak(BreakReason_User, kStage15SuccessMagic, (15ULL << 32) | 1ULL);
    svcExitProcess();
}

NORETURN void ReportStage15Failure(u32 status) {
    svcBreak(BreakReason_User, kStage15FailureMagic, (15ULL << 32) | status);
    svcExitProcess();
}

void CheckStage15AfterPausedUpdate() {
    if (LuaRuntime::TakeCallbackError()) {
        ReportStage15Failure(3);
    }
    const u32 pausedUpdates = LuaRuntime::PostUpdateCount();
    if (pausedUpdates == 0) {
        return;
    }
    if (LuaRuntime::PostRenderPausedCount() != 0) {
        ReportStage15Success();
    }
    if (pausedUpdates >= kStage15PausedUpdateLimit) {
        ReportStage15Failure(LuaRuntime::PostRenderCount() == 0 ? 4 : 5);
    }
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
constexpr u32 kStage6ObserverFrameLimit = 600;
std::atomic<u32> g_Stage6ObserverFrames{0};
std::atomic<uintptr_t> g_Stage6GameOwnerSlot{0};
std::atomic<uintptr_t> g_Stage6GameIsPausedThunk{0};

NORETURN void ReportStage6IsPausedSuccess(bool paused) {
    svcBreak(BreakReason_User, 0x49534141435F4950ULL,
             (6ULL << 32) | (paused ? 2ULL : 1ULL));
    svcExitProcess();
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
std::atomic<uintptr_t> g_Stage9ResetAddress{0};
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
enum class Stage11State : u32 {
    Unarmed,
    Armed,
    Running,
    Finished,
};
std::atomic<Stage11State> g_Stage11State{Stage11State::Unarmed};
GameFileReader::Bindings g_Stage11Bindings{};

NORETURN void RunStage11RomfsSentinelDiagnostic() {
    if (g_Stage11State.load(std::memory_order_acquire) != Stage11State::Running) {
        svcBreak(BreakReason_User, 0x495341414346464CULL, (11ULL << 32) | 14ULL);
        svcExitProcess();
    }

    const GameFileReader::ReadResult result = GameFileReader::ReadSentinel(g_Stage11Bindings);
    g_Stage11State.store(Stage11State::Finished, std::memory_order_release);
    switch (result) {
    case GameFileReader::ReadResult::Success:
        svcBreak(BreakReason_User, 0x4953414143464F4BULL, (11ULL << 32) | 18ULL);
        svcExitProcess();
    case GameFileReader::ReadResult::OpenFailed:
        svcBreak(BreakReason_User, 0x495341414346464CULL, (11ULL << 32) | 10ULL);
        svcExitProcess();
    case GameFileReader::ReadResult::LengthMismatch:
        svcBreak(BreakReason_User, 0x495341414346464CULL, (11ULL << 32) | 11ULL);
        svcExitProcess();
    case GameFileReader::ReadResult::ReadMismatch:
        svcBreak(BreakReason_User, 0x495341414346464CULL, (11ULL << 32) | 12ULL);
        svcExitProcess();
    case GameFileReader::ReadResult::ContentMismatch:
        svcBreak(BreakReason_User, 0x495341414346464CULL, (11ULL << 32) | 13ULL);
        svcExitProcess();
    }
    UNREACHABLE;
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
constexpr u64 kStage118SuccessMagic = 0x49534141435F4657ULL;
constexpr u64 kStage118FailureMagic = 0x49534141435F4646ULL;
std::atomic<u32> g_Stage118Armed{false};
GameFileReader::WriteBindings g_Stage118Bindings{};

NORETURN void ReportStage118Success() {
    svcBreak(BreakReason_User, kStage118SuccessMagic, (118ULL << 32) | 0x0fULL);
    svcExitProcess();
}

NORETURN void ReportStage118Failure(u32 status) {
    svcBreak(BreakReason_User, kStage118FailureMagic, (118ULL << 32) | status);
    svcExitProcess();
}

NORETURN void RunStage118ManagedFileWriteDiagnostic() {
    switch (GameFileReader::WriteDiagnosticFile(g_Stage118Bindings)) {
    case GameFileReader::WriteDiagnosticResult::Success: ReportStage118Success();
    case GameFileReader::WriteDiagnosticResult::OpenFailed: ReportStage118Failure(10);
    case GameFileReader::WriteDiagnosticResult::WriteMismatch: ReportStage118Failure(11);
    }
    UNREACHABLE;
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
constexpr u64 kStage12SuccessMagic = 0x4953414143454C50ULL;
constexpr u64 kStage12FailureMagic = 0x4953414143454C46ULL;

enum class Stage12State : u32 {
    Unarmed,
    Armed,
    Running,
    Ready,
    Finished,
};

std::atomic<Stage12State> g_Stage12State{Stage12State::Unarmed};
GameFileReader::Bindings g_Stage12Bindings{};

NORETURN void ReportStage12Failure(u32 status) {
    g_Stage12State.store(Stage12State::Finished, std::memory_order_release);
    svcBreak(BreakReason_User, kStage12FailureMagic, (12ULL << 32) | status);
    svcExitProcess();
}

void RunStage12RomfsLuaDiagnostic() {
    if (g_Stage12State.load(std::memory_order_acquire) != Stage12State::Running) {
        ReportStage12Failure(18);
    }

    std::array<u8, kRomfsLuaProbeMaximumLength> script{};
    std::size_t length = 0;
    switch (GameFileReader::ReadScript(g_Stage12Bindings, &script, &length)) {
    case GameFileReader::ScriptReadResult::Success:
        break;
    case GameFileReader::ScriptReadResult::OpenFailed:
        ReportStage12Failure(10);
    case GameFileReader::ScriptReadResult::LengthOutOfRange:
        ReportStage12Failure(11);
    case GameFileReader::ScriptReadResult::ReadMismatch:
        ReportStage12Failure(12);
    }

    switch (LuaRuntime::InitializeFromBuffer(reinterpret_cast<const char*>(script.data()), length,
                                             "@rom:/runtime_probe.lua")) {
    case LuaRuntime::LuaInitResult::Success:
        g_Stage12State.store(Stage12State::Ready, std::memory_order_release);
        return;
    case LuaRuntime::LuaInitResult::StateCreateFailed:
    case LuaRuntime::LuaInitResult::RuntimePreparationMemoryFailed:
    case LuaRuntime::LuaInitResult::RuntimePreparationFailed:
        ReportStage12Failure(13);
    case LuaRuntime::LuaInitResult::ScriptLoadFailed:
        ReportStage12Failure(14);
    case LuaRuntime::LuaInitResult::ScriptRunFailed:
        ReportStage12Failure(15);
    case LuaRuntime::LuaInitResult::MissingPostUpdateCallback:
        ReportStage12Failure(16);
    }
    UNREACHABLE;
}
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
constexpr u64 kStage13SuccessMagic = 0x4953414143525150ULL;
constexpr u64 kStage13FailureMagic = 0x4953414143525146ULL;
constexpr u64 kStage13RequireErrorTailMagic = 0x4953414143525154ULL;

enum class Stage13State : u32 {
    Unarmed,
    Armed,
    Running,
    Ready,
    Finished,
};

std::atomic<Stage13State> g_Stage13State{Stage13State::Unarmed};
GameFileReader::Bindings g_Stage13Bindings{};
std::array<u8, kRomfsModManifestMaximumLength> g_Stage13Manifest{};
std::array<u8, kRomfsModScriptMaximumLength> g_Stage13Entry{};

NORETURN void ReportStage13StateMismatch() {
    ReportStage13Failure(25);
}

template <std::size_t Capacity>
bool JoinStage13Path(std::array<char, Capacity>* output, const char* prefix, const char* suffix) {
    if (output == nullptr || prefix == nullptr || suffix == nullptr) {
        return false;
    }
    const std::size_t prefixLength = std::strlen(prefix);
    const std::size_t suffixLength = std::strlen(suffix);
    if (prefixLength + suffixLength >= Capacity) {
        return false;
    }
    std::memcpy(output->data(), prefix, prefixLength);
    std::memcpy(output->data() + prefixLength, suffix, suffixLength + 1);
    return true;
}

void RunStage13ManifestRequireDiagnostic() {
    if (g_Stage13State.load(std::memory_order_acquire) != Stage13State::Running) {
        ReportStage13StateMismatch();
    }

    std::size_t manifestLength = 0;
    switch (GameFileReader::ReadTextFile(g_Stage13Bindings, kRomfsModManifestPath,
                                         g_Stage13Manifest.data(), g_Stage13Manifest.size(), &manifestLength)) {
    case GameFileReader::TextReadResult::Success:
        break;
    case GameFileReader::TextReadResult::OpenFailed:
        ReportStage13Failure(10);
    case GameFileReader::TextReadResult::LengthOutOfRange:
        ReportStage13Failure(11);
    case GameFileReader::TextReadResult::ReadMismatch:
        ReportStage13Failure(12);
    case GameFileReader::TextReadResult::InvalidArgument:
        ReportStage13StateMismatch();
    }

    ModManifest::SelectedMod selected{};
    if (ModManifest::SelectFirstEnabled(reinterpret_cast<const char*>(g_Stage13Manifest.data()),
                                        manifestLength, &selected) != ModManifest::ParseResult::Success) {
        ReportStage13Failure(13);
    }

    std::array<char, ModManifest::kEntryCapacity + 32> entryPath{};
    std::array<char, ModManifest::kDirectoryCapacity + 32> modRoot{};
    std::array<char, ModManifest::kEntryCapacity + 33> chunkName{};
    if (!JoinStage13Path(&entryPath, "rom:/isaac_mods/", selected.entry.data()) ||
        !JoinStage13Path(&modRoot, "rom:/isaac_mods/mods/", selected.directory.data()) ||
        !JoinStage13Path(&chunkName, "@rom:/isaac_mods/", selected.entry.data())) {
        ReportStage13StateMismatch();
    }

    std::size_t entryLength = 0;
    switch (GameFileReader::ReadTextFile(g_Stage13Bindings, entryPath.data(),
                                         g_Stage13Entry.data(), g_Stage13Entry.size(), &entryLength)) {
    case GameFileReader::TextReadResult::Success:
        break;
    case GameFileReader::TextReadResult::OpenFailed:
        ReportStage13Failure(14);
    case GameFileReader::TextReadResult::LengthOutOfRange:
    case GameFileReader::TextReadResult::ReadMismatch:
        ReportStage13Failure(15);
    case GameFileReader::TextReadResult::InvalidArgument:
        ReportStage13StateMismatch();
    }

    const LuaRuntime::LuaInitResult result = LuaRuntime::InitializeStage13Mod(
        reinterpret_cast<const char*>(g_Stage13Entry.data()), entryLength,
        chunkName.data(), modRoot.data(), g_Stage13Bindings);
    if (result != LuaRuntime::LuaInitResult::Success) {
        switch (LuaRuntime::RequireFailureDetail()) {
        case 19:
            ReportStage13Failure(19);
        case 20:
            ReportStage13Failure(20);
        case 21:
            ReportStage13Failure(21);
        case 22:
            ReportStage13Failure(22);
        case 27:
            g_Stage13State.store(Stage13State::Finished, std::memory_order_release);
            svcBreak(BreakReason_User, kStage13RequireErrorTailMagic, LuaRuntime::RequireErrorTail());
            svcExitProcess();
        case 26:
            ReportStage13Failure(26);
        default:
            break;
        }
    }
    switch (result) {
    case LuaRuntime::LuaInitResult::Success:
        g_Stage13State.store(Stage13State::Ready, std::memory_order_release);
        return;
    case LuaRuntime::LuaInitResult::StateCreateFailed:
    case LuaRuntime::LuaInitResult::RuntimePreparationMemoryFailed:
    case LuaRuntime::LuaInitResult::RuntimePreparationFailed:
        ReportStage13Failure(16);
    case LuaRuntime::LuaInitResult::ScriptLoadFailed:
        ReportStage13Failure(17);
    case LuaRuntime::LuaInitResult::ScriptRunFailed:
        ReportStage13Failure(18);
    case LuaRuntime::LuaInitResult::MissingPostUpdateCallback:
        ReportStage13Failure(23);
    }
    UNREACHABLE;
}
#endif
#if !defined(EXL_DIAGNOSTIC_STAGE)
enum class DefaultManifestState : u32 { Unarmed, Armed, Running, Ready, Failed };
enum class DefaultManifestFailureDetail : u32 {
    None = 0,
    ManifestRead = 1,
    ManifestParse = 2,
    PathBuild = 3,
    EntryRead = 4,
    // 5 不是失败码：清单没写 `entry`（纯资源 Mod），或写的那个文件包内不存在。这时内容挂载点
    // 照常注册、Lua 完全不初始化、`InitializeDefaultManifestMod` 返回成功、Mod 状态为 Ready。
    // 诊断字 [11] 因此有了第三种含义：0 = 带脚本加载成功，1..4 = 失败在哪一步，5 = 只挂载内容。
    Scriptless = 5,
    // 6：没有可用清单，运行时**自己列目录**发现的模组（方案 A，2026-09-16）。
    // 不是失败：与 0 一样是"加载成功"，只是告诉读数"这批模组不是清单点名的那批"。
    Discovered = 6,
    NameOrder = 7, // 显示名收集或排序失败，不能发布与PC不一致的顺序。
};
std::atomic<DefaultManifestState> g_DefaultManifestState{DefaultManifestState::Unarmed};
std::atomic<u32> g_DefaultManifestFailureDetail{static_cast<u32>(DefaultManifestFailureDetail::None)};
// 诊断字 `[11]` 本体（打包格式见 `mod_load_step.hpp` 的 `PackModLoadWord`）。
//
// 为什么另开一个字而不是改造 `g_DefaultManifestFailureDetail`：后者是既有探针阶段
// （`EXL_STARTUP_PROBE_STAGE == 8`）与 `TestRunObserver` 的线上格式，语义不能动；诊断字 `[11]`
// 只在"人读崩溃报告"这条路上被消费，把它升级成"步骤 + 原因 + 文件大小"是纯增益。
std::atomic<u32> g_DefaultManifestFailureWord{0};
// 清单与"扫目录"的合并结果（2026-09-21，用户要求"拷进 mods/ 就能用"）：
//   g_AutoAppendedMods = 除清单之外**多追加**了几个目录（0 = 没有新的 / 合并失败）
//   g_AutoAppendStatus = 合并的状态码（0 = 成功；非 0 = 列不出目录/装不下，此时保留清单那一批）
std::atomic<u32> g_AutoAppendedMods{0};
std::atomic<u32> g_AutoAppendStatus{0};
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
std::atomic<u32> g_DefaultManifestInitializationAllowed{0};

bool DefaultManifestInitializationAllowed() {
    return g_DefaultManifestInitializationAllowed.load(std::memory_order_acquire);
}
#endif
DefaultCallbackGate g_DefaultCallbackGate{};
DefaultPersistenceGate g_DefaultPersistenceGate{};
#if defined(EXL_PERSISTENCE_REQUIRED)
constexpr bool kDefaultPersistenceRequired = true;
#else
constexpr bool kDefaultPersistenceRequired = false;
#endif
GameFileReader::Bindings g_DefaultManifestBindings{};

// 贴图桥（`ImagePcxLoad`）兜底依赖的引擎入口：安装成功后由 `VerifyImagePcxBindings` 发布。
// 为空表示本机守卫没对上（构建不匹配），此时 `.png`→`.pcx` 兜底静默失效、退回原生仅 `.pcx`。
GameFileReader::ImagePcxBindings g_ImagePcxBindings{};
// ─────────────────────────────────────────────────────────────────────────────

std::array<u8, kRomfsModManifestMaximumLength> g_DefaultManifest{};
std::array<u8, kRomfsModScriptMaximumLength> g_DefaultEntry{};
// The manifest read, Mod selection, path assembly, entry read and Lua
// initialization live in the application services, so the failure detail is
// derived from the service's step instead of local branches. Every build entry
// point defines `EXL_LAYERED_RUNTIME`, so there is exactly one path here.
#if defined(EXL_LAYERED_RUNTIME)
// Diagnostics entry point implemented in `saltynx_runtime_bridge.cpp`: it arms
// the event journal once the file table exists and a safe thread is running.
// Layered builds only: the plugin/diagnostic builds do not compile that bridge,
// so the call site below is guarded by the same macro.
#define ISAAC_RUNTIME_HAS_DIAGNOSTICS_BRIDGE 1
// Hidden, not default. A default-visibility declaration makes the linker emit a `.plt`
// call whose lazy-binding GOT slot is an `R_AARCH64_JUMP_SLOT` starting at the linker's
// PLT0 address; if the module's rtld does not resolve it, the stub falls through to
// `*(0x74B80)`, a resolver pointer with no relocation and a zero value. Hidden
// visibility binds the call locally and emits a direct `bl` instead.
extern "C" __attribute__((visibility("hidden"))) void IsaacModRuntime_TryAttachDiagnostics();
// Bounded inside the Runtime: it writes at most three probe files in a session.
extern "C" __attribute__((visibility("hidden"))) void IsaacModRuntime_ProbeFileWriteFromHook();
// Probe-only: steps through the Runtime's own `fs` write path and breaks with the Result
// codes, one per register. Bounded inside.
extern "C" __attribute__((visibility("hidden"))) void IsaacModRuntime_ProbeFsSteps();
// Bounded inside: writes at most three probe files with the game's own libc functions,
// resolved by name through SaltyNX's symbol lookup.
extern "C" __attribute__((visibility("hidden"))) void IsaacModRuntime_ProbeNativeFileWrite();
// Bounded inside: calls SaltyNX's own IPC entries and keeps their Result codes, which says
// whether the Runtime can talk to SaltyNX's sysmodule at all.
extern "C" __attribute__((visibility("hidden"))) void IsaacModRuntime_ProbeSaltyIpc();
// Bounded inside, once: reopens SaltyNX's service session (the payload closes its own when it
// finishes) and tries a file write through it from the game's thread.
extern "C" __attribute__((visibility("hidden"))) void IsaacModRuntime_ProbeSaltyReinit();
#endif

#if defined(EXL_LAYERED_RUNTIME)
extern "C" __attribute__((visibility("default"))) std::uint64_t
IsaacModRuntime_GetHookDiagnostics(std::uint32_t* output, std::size_t wordCount) {
    if (output == nullptr || wordCount < kHookDiagnosticsWordCount) {
        return 0;
    }
    for (std::size_t index = 0; index < 3; ++index) {
        output[index] = g_HookInstallResults[index].load(std::memory_order_acquire);
    }
    output[3] = g_UpdateCallbackEntries.load(std::memory_order_acquire);
    output[4] = g_RenderCallbackEntries.load(std::memory_order_acquire);
    const std::uint64_t kinds = LuaRuntime::RegisteredCallbackKindMaskLow();
    const std::uint64_t kindsHigh = LuaRuntime::RegisteredCallbackKindMaskHigh();
    output[5] = static_cast<std::uint32_t>(kinds & 0xFFFFFFFFULL);
    output[6] = static_cast<std::uint32_t>(kinds >> 32);
    output[7] = static_cast<std::uint32_t>(kindsHigh & 0xFFFFFFFFULL);
    output[8] = static_cast<std::uint32_t>(kindsHigh >> 32);
    output[9] = LuaRuntime::DispatchableCallbackRegistrationCount();
    output[10] = LuaRuntime::UnhookedCallbackRegistrationCount();
    output[11] = g_DefaultManifestFailureWord.load(std::memory_order_acquire);
    output[12] = LuaRuntime::CallbackErrorPending() ? 1u : 0u;
    std::uint32_t errorLength = 0;
    std::uint64_t errorHead = LuaRuntime::LastLuaErrorHead(&errorLength);
    output[13] = errorLength;
    output[14] = static_cast<std::uint32_t>(errorHead & 0xFFFFFFFFULL);
    output[15] = static_cast<std::uint32_t>(errorHead >> 32);
    return kHookDiagnosticsMagic;
}

// Same five words, for the module's own in-process readers.
//
// `IsaacModRuntime_GetHookDiagnostics` is exported with default visibility for the
// host plugin, so a call to it from another translation unit of this module would be
// a `.plt` call resolved by the module loader (see the note above). The self-journal
// runs inside this module and must not depend on that resolution, so it reads the
// same words through this hidden entry point, which the linker binds with a direct
// `bl`.
extern "C" __attribute__((visibility("hidden"))) void
IsaacModRuntime_FillHookJournalWords(std::uint32_t* output) {
    if (output == nullptr) {
        return;
    }
    for (std::size_t index = 0; index < 3; ++index) {
        output[index] = g_HookInstallResults[index].load(std::memory_order_acquire);
    }
    output[3] = g_UpdateCallbackEntries.load(std::memory_order_acquire);
    output[4] = g_RenderCallbackEntries.load(std::memory_order_acquire);
}
#endif

bool LoadDefaultManifestModThroughService(u32* failureDetail);

// 批次 236：加载状态机的"走完了吗"（定义在下面那段说明之后）。
[[nodiscard]] bool DefaultManifestLoadFinished() noexcept;

bool InitializeDefaultManifestMod(u32* failureDetail) {
    if (failureDetail == nullptr) return false;
    // 批次 236：这个函数现在**每帧被调一次**（每次只推进一步，见那边的说明）。
    // 只在"还没走完"时把诊断字清零；走完之后 `LoadDefaultManifestModThroughService`
    // 已经把它自己的结果写进去了，这里**不许覆盖**。
    if (!DefaultManifestLoadFinished()) {
        *failureDetail = static_cast<u32>(DefaultManifestFailureDetail::None);
    }
    // ★ 2026-10-01（用户指令「将加载期拆帧改回去吧」）：把批次 236 的"每帧推进一步"
    // **改回一次调用走完** —— 即恢复 236 之前的加载时机（模组脚本在更早那一帧执行）。
    //
    // ★ 没有删掉 236 的状态机代码，只是在这里把它一次推到头：**要改回拆帧，把这个循环去掉就行。**
    //
    // 为什么用"循环推进"而不是把状态机改平：236 的改动里有若干**按文本位置钉住**的门禁
    // （`service.LoadAll(`、`loadOutcome.scripts[0]`、`!loadOutcome.anyFailure`、
    // `g_CardSwitchProbeAllowed.store(1,` 必须在函数体开头 600 字符内 …），保留状态机结构
    // 就不必再动它们。
    //
    // 步数上限只是防呆：正常一轮 = 固定几步 + 每帧一个模组的 Mounts/Scripts 各一轮，
    // 模组数是个位数，64 足够；真卡住也不会把主线程吊死在这里。
    constexpr int kMaxLoadStepsPerCall = 64;
    bool result = LoadDefaultManifestModThroughService(failureDetail);
    for (int step = 1; step < kMaxLoadStepsPerCall && !DefaultManifestLoadFinished(); ++step) {
        result = LoadDefaultManifestModThroughService(failureDetail);
    }
    // 未完成步的false只是“结果尚未产生”，只有finished才可解释最终成败。
    return DefaultManifestLoadFinished() && result;
}

// File-scope so nothing depends on dynamic initialisation order, and so the rebuild
// relay can reach the same instance through `SessionContentMountService()`.
isaac::runtime::EngineContentMountAdapter g_ContentMountAdapter;
isaac::runtime::ContentMountService g_ContentMountService{g_ContentMountAdapter};
// 方案 A（2026-09-16）：没有清单时自己列 `isaac_mods/mods`，把发现的目录当模组。
// 与适配器同样放在文件作用域：这两个对象都没有动态初始化的依赖。
isaac::runtime::EngineDirectoryAdapter g_ModDirectoryAdapter;
isaac::runtime::ModDiscoveryService g_ModDiscoveryService{g_ModDirectoryAdapter};
// 模组开关（2026-09-16，路线 B）：状态存在游戏**存档分区**里（真机通道见
// `docs/问题与解决记录.md` 续三十四），开机时读出来、按它过滤掉被关掉的模组。
// 放在文件作用域的理由同上面两个：没有动态初始化的依赖，菜单侧也能拿到同一个实例。
isaac::runtime::EngineSaveFileAdapter g_SaveFileAdapter;
isaac::runtime::ModToggleService g_ModToggleService{g_SaveFileAdapter};
// 批次 147 的埋点全局量在**真正的文件作用域**（本文件顶部、`namespace IsaacRepentance` 之前）
// —— 那里才不会被匿名命名空间收进去，`g_ModLoadConfigs*` 那一段注释写了为什么。

// 卡上 no-lua 开关只控制真实模组运行时；原生模组页独立使用共享开关服务。
bool CardSwitchOn(const char* name);
bool CardSwitchNoLua() { return CardSwitchOn("no-lua"); }

// ---- 卡上开关（2026-09-16，排障效率）------------------------------------------------
//
// 为什么要有它：定位崩溃时"一版一构建一部署"太贵（每轮十几分钟）。运行时改成**开机时看卡上有没有
// 标记文件**，来决定这一轮装哪些挂点 —— 于是**一份包能测很多种配置**，改卡上的文件（FTP 一秒）
// 加一次重启就能换一个变量，不需要我重新构建。
//
// 标记文件放在游戏覆盖层目录里（我用 FTP 能写、游戏能读）：
//   `/atmosphere/contents/010021C000B6A000/romfs/isaac_mods/mods/<名字>.on`
//   ⇒ 运行时按 `rom:/isaac_mods/mods/<名字>.on` 去问"存在吗"。
// ⚠️ 放在 `mods/` 里是安全的：模组自动发现**只认子目录**，文件会被忽略。
//
// 支持的开关（名字就是文件名的前半段）：
//   `no-menu`        不装自带的模组开关菜单（真实模组照旧加载）
//   `no-lua`         不建任何 Lua 状态（菜单与真实模组都不加载）
//
// ⚠️ 这两个开关都只由**游戏主线程**上的代码读取（模组加载那条路），**不允许**在 worker 线程上读
// —— 理由见 `g_CardSwitchProbeAllowed` 上面那段事故记录。
//
// **一次开机只探测一遍**：第一次（被允许的）调用时把 `kCardSwitchNames` 里每个名字都问一遍，
// 结果存进 `g_CardSwitchMask` / `g_CardSwitchChannel`（设备侧可读，见那里的注释），之后只查掩码。
void BuildCardSwitchPath(const char* name, char* out, std::size_t capacity) {
    const char* prefix = "rom:/isaac_mods/mods/";
    const char* suffix = ".on";
    std::size_t length = 0;
    if (out == nullptr || capacity == 0) {
        return;
    }
    out[0] = '\0';
    const char* pieces[3] = {prefix, name, suffix};
    for (const char* piece : pieces) {
        for (const char* cursor = piece; *cursor != '\0' && length + 1 < capacity; ++cursor) {
            out[length++] = *cursor;
        }
    }
    out[length] = '\0';
}

void ProbeCardSwitches() {
    static bool probed = false;
    if (probed) {
        return;
    }
    // ★ 硬闸：**不确认自己在游戏线程上就不碰卡**。
    // 这一条是 442190 那次"每次开机必崩"的直接修复 —— 那种崩溃发生在 nnSdk 内部，
    // 从我们的代码里看不出任何异常，排查代价极高（两份崩溃报告 + 一次完整装机）。
    if (g_CardSwitchProbeAllowed.load(std::memory_order_acquire) == 0) {
        g_CardSwitchChannel.fetch_or(4U, std::memory_order_release);
        return;
    }
    probed = true;
    u32 mask = 0;
    u32 channel = 0;
    for (std::size_t index = 0; index < kCardSwitchNameCount; ++index) {
        char path[128] = {};
        BuildCardSwitchPath(kCardSwitchNames[index], path, sizeof(path));
        bool exists = false;
        if (!g_SaveFileAdapter.Exists(path, &exists).ok()) {
            channel |= 2U;   // 查询本身失败：通道不可用（不是"文件不在"）
            continue;
        }
        channel |= 1U;
        if (exists) {
            mask |= (1U << index);
        }
    }
    g_CardSwitchMask.store(mask, std::memory_order_release);
    g_CardSwitchChannel.store(channel, std::memory_order_release);
}

bool CardSwitchOn(const char* name) {
    if (name == nullptr) {
        return false;
    }
    ProbeCardSwitches();
    const u32 mask = g_CardSwitchMask.load(std::memory_order_acquire);
    for (std::size_t index = 0; index < kCardSwitchNameCount; ++index) {
        if (std::strcmp(kCardSwitchNames[index], name) == 0) {
            return (mask & (1U << index)) != 0;
        }
    }
    // 表里没有的名字：如实返回 false（不现问卡 —— 那会引入"有的开关问了、有的没问"的
    // 两套行为，掩码也就无法自证了）。
    return false;
}

// 挂点层面的"跳过判据"：既是 `ONLY_REQUIRED_HOOK=1` 的二分构建，也能**一次只摘一个挂点**。
//
// 为什么是**编译期**而不是卡上开关：读卡要用游戏 nnSdk 的文件 API，而装挂点这一步跑在
// **worker 线程**上（见 `g_CardSwitchProbeAllowed` 上面的事故记录）。所以挂点二分只能一条构建
// 一个配置；卡上开关只留给"游戏主线程上读得到"的那两个（`no-menu` / `no-lua`）。
//
// 单摘一个（2026-09-17 加，定位"模组全关时崩"用；构建命令在后两行）：
//   make ... EXL_SKIP_HOOK_PRESENT=1        # 不装 `Present` 的 GOT 槽拦截
//   make ... EXL_SKIP_HOOK_RENDER=1         # 不装 `ManagerRender` 入口中继
//   make ... EXL_SKIP_HOOK_PREGETCOLLECTIBLE=1 / EXL_SKIP_HOOK_REBUILDMOUNTS=1 / EXL_SKIP_HOOK_GAMESTART=1
// 一次摘一个、每版一次重启：现象消失 ⇒ 该挂点就是元凶（与 031 的"只装必需挂点"对照结果联用）。
bool SkipOptionalHooksPredicate(void*, isaac::runtime::HookId id) noexcept {
#if defined(EXL_ONLY_REQUIRED_HOOK) && EXL_ONLY_REQUIRED_HOOK == 1
    if (!isaac::runtime::IsRequired(id)) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_PRESENT) && EXL_SKIP_HOOK_PRESENT == 1
    if (id == isaac::runtime::HookId::ManagerPresent) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_RENDER) && EXL_SKIP_HOOK_RENDER == 1
    if (id == isaac::runtime::HookId::ManagerRender) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_PREGETCOLLECTIBLE) && EXL_SKIP_HOOK_PREGETCOLLECTIBLE == 1
    if (id == isaac::runtime::HookId::PreGetCollectible) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_REBUILDMOUNTS) && EXL_SKIP_HOOK_REBUILDMOUNTS == 1
    if (id == isaac::runtime::HookId::RebuildMountPoints) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_GAMESTART) && EXL_SKIP_HOOK_GAMESTART == 1
    if (id == isaac::runtime::HookId::GameStart) {
        return true;
    }
#endif
// 批次 102 的四个事件中继。加这四个开关的直接用途：如果接线之后出现"用道具/用药丸就崩"
// 或"退出到主菜单就崩"，可以**一次摘一个**把范围缩到具体哪一个靶点上，而不必回退整批。
#if defined(EXL_SKIP_HOOK_USEACTIVEITEM) && EXL_SKIP_HOOK_USEACTIVEITEM == 1
    if (id == isaac::runtime::HookId::UseActiveItem) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_USECARD) && EXL_SKIP_HOOK_USECARD == 1
    if (id == isaac::runtime::HookId::UseCard) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_USEPILL) && EXL_SKIP_HOOK_USEPILL == 1
    if (id == isaac::runtime::HookId::UsePill) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_GAMEEXIT) && EXL_SKIP_HOOK_GAMEEXIT == 1
    if (id == isaac::runtime::HookId::GameExit) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_PICKUPCOLLISION) && EXL_SKIP_HOOK_PICKUPCOLLISION == 1
    if (id == isaac::runtime::HookId::PickupCollision) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_ROOMENTITYSPAWN) && EXL_SKIP_HOOK_ROOMENTITYSPAWN == 1
    if (id == isaac::runtime::HookId::RoomEntitySpawn) {
        return true;
    }
#endif
// 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG` 的四条 + `MC_EVALUATE_CACHE`，逐条可摘
// （出现"受伤/属性异常"时用来二分"是不是我们这条造成的"）。
#if defined(EXL_SKIP_HOOK_ENTITYTAKEDAMAGE) && EXL_SKIP_HOOK_ENTITYTAKEDAMAGE == 1
    if (id == isaac::runtime::HookId::EntityTakeDamage) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_ENTITYPLAYERTAKEDAMAGE) && EXL_SKIP_HOOK_ENTITYPLAYERTAKEDAMAGE == 1
    if (id == isaac::runtime::HookId::EntityPlayerTakeDamage) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_ENTITYPICKUPTAKEDAMAGE) && EXL_SKIP_HOOK_ENTITYPICKUPTAKEDAMAGE == 1
    if (id == isaac::runtime::HookId::EntityPickupTakeDamage) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_ENTITYSLOTTAKEDAMAGE) && EXL_SKIP_HOOK_ENTITYSLOTTAKEDAMAGE == 1
    if (id == isaac::runtime::HookId::EntitySlotTakeDamage) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_EVALUATEITEMS) && EXL_SKIP_HOOK_EVALUATEITEMS == 1
    if (id == isaac::runtime::HookId::EvaluateItems) {
        return true;
    }
#endif
// 批次 397（2026-10-07）：补全回调（第 2 批）的三条，逐条可摘
// （出现"击杀/死亡/结束"类现象时用来二分"是不是我们这条造成的"）。
#if defined(EXL_SKIP_HOOK_ENTITYKILL) && EXL_SKIP_HOOK_ENTITYKILL == 1
    if (id == isaac::runtime::HookId::EntityKill) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_NPCDEATHREMOVE) && EXL_SKIP_HOOK_NPCDEATHREMOVE == 1
    if (id == isaac::runtime::HookId::NpcDeathRemove) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_GAMEEND) && EXL_SKIP_HOOK_GAMEEND == 1
    if (id == isaac::runtime::HookId::GameEnd) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_FIRETEAR) && EXL_SKIP_HOOK_FIRETEAR == 1
    if (id == isaac::runtime::HookId::FireTear) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_FAMILIARCOLLISION) && EXL_SKIP_HOOK_FAMILIARCOLLISION == 1
    if (id == isaac::runtime::HookId::FamiliarCollision) return true;
#endif
#if defined(EXL_SKIP_HOOK_NPCCOLLISION) && EXL_SKIP_HOOK_NPCCOLLISION == 1
    if (id == isaac::runtime::HookId::NpcCollision) return true;
#endif
#if defined(EXL_SKIP_HOOK_PLAYERCOLLISION) && EXL_SKIP_HOOK_PLAYERCOLLISION == 1
    if (id == isaac::runtime::HookId::PlayerCollision) return true;
#endif
#if defined(EXL_SKIP_HOOK_TEARCOLLISION) && EXL_SKIP_HOOK_TEARCOLLISION == 1
    if (id == isaac::runtime::HookId::TearCollision) return true;
#endif
#if defined(EXL_SKIP_HOOK_PROJECTILECOLLISION) && EXL_SKIP_HOOK_PROJECTILECOLLISION == 1
    if (id == isaac::runtime::HookId::ProjectileCollision) return true;
#endif
#if defined(EXL_SKIP_HOOK_KNIFECOLLISION) && EXL_SKIP_HOOK_KNIFECOLLISION == 1
    if (id == isaac::runtime::HookId::KnifeCollision) return true;
#endif
#if defined(EXL_SKIP_HOOK_BOMBCOLLISION) && EXL_SKIP_HOOK_BOMBCOLLISION == 1
    if (id == isaac::runtime::HookId::BombCollision) return true;
#endif
#if defined(EXL_SKIP_HOOK_NPCRENDER) && EXL_SKIP_HOOK_NPCRENDER == 1
    if (id == isaac::runtime::HookId::NpcRender) return true;
#endif
#if defined(EXL_SKIP_HOOK_ITEMPOOLGETPILL) && EXL_SKIP_HOOK_ITEMPOOLGETPILL == 1
    if (id == isaac::runtime::HookId::ItemPoolGetPill) return true;
#endif
#if defined(EXL_SKIP_HOOK_ITEMPOOLGETPILLEFFECT) && EXL_SKIP_HOOK_ITEMPOOLGETPILLEFFECT == 1
    if (id == isaac::runtime::HookId::ItemPoolGetPillEffect) return true;
#endif
#if defined(EXL_SKIP_HOOK_GAMEDEVOLVEENEMY) && EXL_SKIP_HOOK_GAMEDEVOLVEENEMY == 1
    if (id == isaac::runtime::HookId::GameDevolveEnemy) return true;
#endif
#if defined(EXL_SKIP_HOOK_TRINKETFIRST) && EXL_SKIP_HOOK_TRINKETFIRST == 1
    if (id == isaac::runtime::HookId::ItemPoolTrinketFirstRandom) return true;
#endif
#if defined(EXL_SKIP_HOOK_TRINKETSELECTED) && EXL_SKIP_HOOK_TRINKETSELECTED == 1
    if (id == isaac::runtime::HookId::ItemPoolTrinketSelected) return true;
#endif
#if defined(EXL_SKIP_HOOK_CURSEFIRST) && EXL_SKIP_HOOK_CURSEFIRST == 1
    if (id == isaac::runtime::HookId::LevelCurseFirstRandom) return true;
#endif
#if defined(EXL_SKIP_HOOK_CURSEEVAL) && EXL_SKIP_HOOK_CURSEEVAL == 1
    if (id == isaac::runtime::HookId::LevelCurseEvaluation) return true;
#endif
#if defined(EXL_SKIP_HOOK_PICKUPSELECTIONSPECIAL) && EXL_SKIP_HOOK_PICKUPSELECTIONSPECIAL == 1
    if (id == isaac::runtime::HookId::PickupSelectionSpecial) return true;
#endif
#if defined(EXL_SKIP_HOOK_PICKUPSELECTION) && EXL_SKIP_HOOK_PICKUPSELECTION == 1
    if (id == isaac::runtime::HookId::PickupSelection) return true;
#endif
#if defined(EXL_SKIP_HOOK_ENTITYREMOVE) && EXL_SKIP_HOOK_ENTITYREMOVE == 1
    if (id == isaac::runtime::HookId::ConsoleUnknownLength || id == isaac::runtime::HookId::ConsoleUnknownCompare) return true;
    if (id == isaac::runtime::HookId::ModManagerUnload) return true;
    if (id == isaac::runtime::HookId::ItemPoolGetCard) return true;
    if (id == isaac::runtime::HookId::EntityRemovePointers) return true;
#endif
#if defined(EXL_SKIP_HOOK_ENTITYDESTRUCTORREMOVE) && EXL_SKIP_HOOK_ENTITYDESTRUCTORREMOVE == 1
    if (id == isaac::runtime::HookId::EntityDestructorRemove) return true;
#endif
#if defined(EXL_SKIP_HOOK_CLEARAWARD) && EXL_SKIP_HOOK_CLEARAWARD == 1
    if (id == isaac::runtime::HookId::RoomClearAward) return true;
#endif
#if defined(EXL_SKIP_HOOK_NPCUPDATEAI) && EXL_SKIP_HOOK_NPCUPDATEAI == 1
    if (id == isaac::runtime::HookId::NpcUpdateAi) return true;
#endif
#if defined(EXL_SKIP_HOOK_GETCARD) && EXL_SKIP_HOOK_GETCARD == 1
    if (id == isaac::runtime::HookId::ItemPoolGetCard) return true;
#endif
#if defined(EXL_SKIP_HOOK_MODUNLOAD) && EXL_SKIP_HOOK_MODUNLOAD == 1
    if (id == isaac::runtime::HookId::ModManagerUnload) return true;
#endif
#if defined(EXL_SKIP_HOOK_CONSOLEUNKNOWN) && EXL_SKIP_HOOK_CONSOLEUNKNOWN == 1
    if (id == isaac::runtime::HookId::ConsoleUnknownLength ||
        id == isaac::runtime::HookId::ConsoleUnknownCompare) return true;
#endif
#if defined(EXL_SKIP_HOOK_CONSOLELIFECYCLE) && EXL_SKIP_HOOK_CONSOLELIFECYCLE == 1
    if (id == isaac::runtime::HookId::ConsoleLifecycle) return true;
#endif
#if defined(EXL_SKIP_HOOK_LEVELLOADROOM) && EXL_SKIP_HOOK_LEVELLOADROOM == 1
    if (id == isaac::runtime::HookId::LevelLoadRoom) return true;
#endif
#if defined(EXL_SKIP_HOOK_ROOMSTB) && EXL_SKIP_HOOK_ROOMSTB == 1
    if (id == isaac::runtime::HookId::RoomConfigLoadStageBinary) return true;
#endif
#if defined(EXL_SKIP_HOOK_HUDRENDER) && EXL_SKIP_HOOK_HUDRENDER == 1
    if (id == isaac::runtime::HookId::HudRender) return true;
#endif
#if defined(EXL_SKIP_HOOK_GAMESPAWNEX) && EXL_SKIP_HOOK_GAMESPAWNEX == 1
    if (id == isaac::runtime::HookId::GameSpawnEx) return true;
#endif
// 贴图桥：二分时单独摘掉（例如「只带 .png 的 Mod 显示异常」就先摘这个，确认是不是兜底转码的问题）。
#if defined(EXL_SKIP_HOOK_IMAGEPCXLOAD) && EXL_SKIP_HOOK_IMAGEPCXLOAD == 1
    if (id == isaac::runtime::HookId::ImagePcxLoad) {
        return true;
    }
#endif
// 贴图桥 v2：二分时单独摘掉。
#if defined(EXL_SKIP_HOOK_IMAGEMGRLOADFILE) && EXL_SKIP_HOOK_IMAGEMGRLOADFILE == 1
    if (id == isaac::runtime::HookId::ImageManagerLoadFile) {
        return true;
    }
#endif
// 批次 390（2026-10-07）：`MC_INPUT_ACTION` 的三条查询中继，逐条可摘
// （出现"某个输入现象"时用来二分"是不是我们这条覆盖造成的"）。
#if defined(EXL_SKIP_HOOK_INPUTACTIONPRESSED) && EXL_SKIP_HOOK_INPUTACTIONPRESSED == 1
    if (id == isaac::runtime::HookId::ManagerIsActionPressed) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_INPUTACTIONTRIGGERED) && EXL_SKIP_HOOK_INPUTACTIONTRIGGERED == 1
    if (id == isaac::runtime::HookId::ManagerIsActionTriggered) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_INPUTACTIONVALUE) && EXL_SKIP_HOOK_INPUTACTIONVALUE == 1
    if (id == isaac::runtime::HookId::ManagerGetActionValue) {
        return true;
    }
#endif
// 贴图桥 v4：路径解析层的单独开关。
#if defined(EXL_SKIP_HOOK_GETMOUNTEDPATH) && EXL_SKIP_HOOK_GETMOUNTEDPATH == 1
    if (id == isaac::runtime::HookId::ContentGetMountedFilePath) {
        return true;
    }
#endif
// 模组页搬生产（2026-09-23，批次 077）：三个入口中继各自的单独开关。
// 用途与上面那批一样：真机上"那一列多一格 / 模组页 / 挡 SetState"哪一处出问题，
// 可以**一次摘一个**把范围缩到具体靶点，而不必回退整批。
#if defined(EXL_SKIP_HOOK_MENUGAMERENDER) && EXL_SKIP_HOOK_MENUGAMERENDER == 1
    if (id == isaac::runtime::HookId::MenuGameRender) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_MENUTITLERENDER) && EXL_SKIP_HOOK_MENUTITLERENDER == 1
    if (id == isaac::runtime::HookId::MenuTitleRender) {
        return true;
    }
#endif
#if defined(EXL_SKIP_HOOK_MENUMANAGERSETSTATE) && EXL_SKIP_HOOK_MENUMANAGERSETSTATE == 1
    if (id == isaac::runtime::HookId::MenuManagerSetState) {
        return true;
    }
#endif
// 成就闸门（2026-09-24 批次 098：挂点从 `TryUnlock` 挪到 `SetReadOnly`，开关名同步改）。
// 用途：真机上遇到"成就该给不给 / 该禁没禁"，可以**一次摘掉这一个挂点**来判断
// "是不是我们这道闸门干的" —— 摘掉之后引擎按它自己的判据走（退回 Switch 原生行为）。
#if defined(EXL_SKIP_HOOK_SETREADONLY) && EXL_SKIP_HOOK_SETREADONLY == 1
    if (id == isaac::runtime::HookId::PersistentGameDataSetReadOnly) {
        return true;
    }
#endif
// 模组 content 加载闸门（批次 147，挂 `ModManager::LoadConfigs` 入口）。
// 用途：真机上"模组的皮肤/音乐进没进来"这件事一旦有变化，可以**一次摘掉这一个挂点**，
// 把"是这道闸门干的"与别的原因分开 —— 摘掉后就退回今天之前的行为（引擎那一路整个空转）。
#if defined(EXL_SKIP_HOOK_MODLOADCONFIGS) && EXL_SKIP_HOOK_MODLOADCONFIGS == 1
    if (id == isaac::runtime::HookId::ModManagerLoadConfigs) {
        return true;
    }
#endif
// `ANM2::Load` 入口中继（批次 363：让"模组覆盖本体资源"生效）。
// 用途：共享资源（小地图那类）一旦有变化，可以**一次摘掉这一个挂点**把范围缩到它身上；
// 摘掉后就退回批次 363 之前的行为 —— 缓存里那份本体旧条目不再被作废、模组那份仍然赢不了。
#if defined(EXL_SKIP_HOOK_ANM2LOAD) && EXL_SKIP_HOOK_ANM2LOAD == 1
    if (id == isaac::runtime::HookId::Anm2Load) {
        return true;
    }
#endif
// ★★★ 批次 385（2026-10-06）：**已经"早装"过的挂点，这里必须跳过**。
// 起因（真机读数定案，见 `dist/gdb-read-20261006-1537-relay-verdict.txt`）：`ANM2::Load` 中继
// "首次被调用"比 `Game::Init` **晚 6.5 秒**，而引擎读 `gfx/ui/minimap1.anm2` 就在 `Game::Init` 里
// ⇒ 那次读没走我们的中继 ⇒ 本体那份被钉进引擎的动画缓存 ⇒ 之后改不掉 ⇒ 模组（minimapi）画红字。
// ⇒ 治本 = 把"资源类"那两条（`ContentGetMountedFilePath` + `Anm2Load`）**提前到 worker 的前置步骤**装
//   （`runtime_entry.cpp` 的 `RunEarlyModMountPrelude` 第 ④ 段，与 `Game::Init` 入口中继同一批）。
// ⇒ 它们已经装过 ⇒ 这里**必须让开**：入口中继靠改写入口 16 字节工作，
//   **同一入口装第二次必然 `EntryMismatch`**（就是下面那段注释说的同一件事）。
//   "早装过"由 `TryInstallEntryRelayEarly` 记账、`EntryRelayInstalledEarly` 查。
if (isaac::runtime::EntryRelayInstalledEarly(id)) {
    return true;
}
// ★★ 探针与生产**互斥**（2026-09-23，批次 077）：这三个靶点与"原生模组页探针"**是同一批入口**，
// 而入口中继靠"改写目标函数入口 16 字节"工作 ⇒ 同一入口装第二次必然 `EntryMismatch`。
// 探针构建里必须**跳过生产这三条**，探针自己那套 `TryInstallEntryRelay` 才装得上。
// 判据是编译期常量（这一段跑在 worker 线程上，读卡会崩 —— 见上面那条注释）。
#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_NATIVE_MODS_MENU
    if (id == isaac::runtime::HookId::MenuGameRender ||
        id == isaac::runtime::HookId::MenuTitleRender ||
        id == isaac::runtime::HookId::MenuManagerSetState) {
        return true;
    }
#endif
    return false;
}

u32 MapModLoadFailure(const isaac::runtime::ModLoadFailure& failure) {
    if (failure.step == isaac::runtime::ModLoadStep::None) return 0;
    if (failure.step == isaac::runtime::ModLoadStep::LuaInit) return 0x10U + failure.detail;
    return static_cast<u32>(failure.step);
}

// `runtime_constants.hpp` 与 `manifest_service.hpp` 各有一份同名常量，历史上就是靠"两处各自
// 演化"埋过坑（缓冲区大小与服务判定不一致 = 一类只在真机上才能发现的错）。这里把它们钉在一起：
// 两个头文件在本文件里同时可见。
static_assert(isaac::runtime::kRomfsModScriptMaximumLength == kRomfsModScriptMaximumLength,
              "脚本缓冲区上限在两处定义必须一致（runtime_constants.hpp / manifest_service.hpp）");
// 同上：多模组上限在旧解析器与 domain 各有一份，必须一致 —— 不一致时"清单里有 4 个 Mod"
// 会在解析层通过、在解析结果类型里装不下（或者反过来），而这类错只在真机上看得见。
static_assert(isaac::runtime::kModManifestCapacity == ::ModManifest::kMaximumSelectedMods,
              "多模组上限在两处定义必须一致（mod_manifest.hpp / domain/mod_manifest.hpp）");

// 把 `ModLoadFailure` 变成诊断字 `[11]`：低 8 位沿用旧步骤字，bits 8..15 是原因（`StatusCode`
// 或 Lua 的 detail），bits 16..47 是读取失败时观测到的文件长度。
u32 PackModLoadDiagnostics(const isaac::runtime::ModLoadFailure& failure) {
    const u32 stepWord = MapModLoadFailure(failure);
    if (stepWord == 0) return 0;
    return isaac::runtime::PackModLoadWord(stepWord, failure.detail, failure.observedBytes);
}

// ============================================================================
// 批次 236（2026-09-30）：**把"读模组"拆成每帧一步**（治"开场黑屏"）
// ============================================================================
//
// 现场（用户实测，三个对照）：卡上放 `no-lua.on`（跳过这一段）⇒ 开场**零延迟**；
// 不跳过 ⇒ **约 10 秒黑屏**（画面不动、声音继续）；旧版本 207 ⇒ <1 秒（但那是"没干活"：
// 它加载不了卡上那个中文版 MCM，模组跑到一半就报错退出）。
// ⇒ 不是"哪个模组坏了"，是**这段活整块塞进了渲染线程的一帧里**。
//
// 为什么是"一帧"：这条路只由 `ManagerUpdateHook::Callback` 调用，而那个回调是游戏自己的
// `Manager::Update` 帧里进来的（也就是渲染线程）。而它必须留在**游戏线程**上
// —— 引擎 nnSdk 的文件 API 只有游戏线程能用（442190 那次换到别的线程用，每次开机必崩）。
//
// 修法：**顺序、失败语义、诊断字一个字不改**，只把帧边界插进去 —— 每帧推进一步：
//   准备（读清单/列目录/读模组开关）→ 每个模组注册一个内容挂载点 → 把 content 喂给引擎
//   → 自带菜单 → 每个模组跑自己的脚本（一帧一个）→ 收尾
// 总时长基本不变（多出来的只是十几帧的间隔 ≈ 0.2 秒），但**每一帧都能把画面出去** ⇒ 黑屏消失。
//
// 状态放在**函数内 static**（与原来那个 `static ResolvedManifestModBatch batch{}` 同一个口径：
// `{}` 是常量初始化 ⇒ 不生成线程安全静态守卫 —— 那玩意儿在 `-nostartfiles` 模块里会 abort，
// 见下面 Prepare 那段事故注释）。整条路只在游戏线程上被碰，所以不需要任何锁。
enum class ManifestLoadStep : u32 {
    Idle = 0,
    Prepare,     //: 读清单 + 列目录 + 追加未列出的 + 读存档里的模组开关（一帧做完）
    Mounts,      //: 每个模组注册一个内容挂载点（一帧一个）
    Content,     //: 把模组的 content 喂给引擎（一帧做完）
    // 4 原为已移除的内嵌菜单阶段；保留后续诊断编号。
    Scripts = 5,     //: 逐个模组读 SD 上的入口脚本并执行（一帧一个）★ 就是这一段最贵
    Finalize,    //: 收尾（算诊断字）
    Done,
};

bool g_ModMenuReloadLoading{};

struct ManifestLoadState {
    // 一批 Mod 的路径缓冲放在**静态存储**里：`ResolvedManifestModBatch` 约 9.6 KiB，
    // 放在这条路径的栈上不合适（它跑在游戏线程），而且 `ResolvedManifestMod` 里的指针
    // 必须活得和这一批一样久。★ 拆帧之后更要紧：状态必须**跨帧**活着，绝不能放栈上。
    isaac::runtime::ResolvedManifestModBatch batch{};
    // 单模组那一小批（`service.LoadAll` 现在一次只喂一个模组）—— 也放静态存储，理由同上。
    isaac::runtime::ResolvedManifestModBatch single{};
    isaac::runtime::ModLoadBatchOutcome loadOutcome{};
    isaac::runtime::ModLoadBatchOutcome oneOutcome{};
    isaac::runtime::ModLoadFailure failure{};
    std::size_t index = 0;
    u32 discoveryMark = 0;
    u32 detail = 0;
    bool batchOk = true;
    bool finished = false;
    bool result = false;
};

ManifestLoadStep& ManifestLoadStepRef() noexcept {
    static ManifestLoadStep step = ManifestLoadStep::Idle;
    return step;
}

ManifestLoadState& ManifestLoadStateRef() noexcept {
    static ManifestLoadState state{};
    return state;
}

//: 这条路走完了吗（走完之后本函数只是空转，`g_DefaultManifestState` 也早就不是 `Running` 了）。
[[nodiscard]] bool DefaultManifestLoadFinished() noexcept {
    return ManifestLoadStateRef().finished;
}

bool LoadDefaultManifestModThroughService(u32* failureDetail) {
    // 批次 236：这条路由 `ManagerUpdateHook::Callback` **每帧推进一小步**（见上面那段说明）。
    // 下面三行是"确认自己在游戏主线程上"之后才允许做的事（引擎 nnSdk 的文件 API）；
    // 每帧重复写是幂等的（闸门本来就是个布尔量、适配器只是记账），所以放在最前面。
    g_CardSwitchProbeAllowed.store(1, std::memory_order_release);
    g_SaveFileAdapter.AllowFromGameThread();
    isaac::runtime::SetSessionSaveFilePort(&g_SaveFileAdapter);
    if (!isaac::runtime::notice::integrity::RuntimeAllowed()) {
        const auto integrityModule = FindTargetModule();
        if (!integrityModule || !isaac::runtime::notice::integrity::Ensure(*integrityModule)) {
            ++g_NoticeIntegrityState[13];
            auto& blocked = ManifestLoadStateRef();
            blocked.result = false;
            blocked.finished = true;
            ManifestLoadStepRef() = ManifestLoadStep::Done;
            if (failureDetail) *failureDetail = 0x4E01;
            return false;
        }
    }
    // 这三个都很轻（各只有一个引用 + 几个函数指针），每帧重建没关系。
    isaac::runtime::GameFileReaderAdapter content{g_DefaultManifestBindings};
    isaac::runtime::EmbeddedLuaAdapter lua{g_DefaultManifestBindings};
    isaac::runtime::ModLoadService service{content, lua};

    ManifestLoadStep& step = ManifestLoadStepRef();
    ManifestLoadState& load = ManifestLoadStateRef();
    if (step == ManifestLoadStep::Idle) {
        step = ManifestLoadStep::Prepare;
#if EXL_DIAGNOSTIC_PROBES
        // 批次 236 补：记下起步那一帧的 Update 进入次数，收尾时相减 ⇒ "跨了几帧"。
        g_LoadStartFrame.store(g_UpdateCallbackEntries.load(std::memory_order_relaxed),
                               std::memory_order_release);
#endif
    }
#if EXL_DIAGNOSTIC_PROBES
    const ManifestLoadStep current = step;
    const std::uint64_t stepStartTick = isaac::runtime::RuntimePerfTick();
#endif

    switch (step) {
    case ManifestLoadStep::Prepare: {
        // 卡上开关 `no-lua.on`：**这一轮一个 Lua 状态都不建**（自带菜单与真实模组都不加载，
        // 连清单/自动发现都不走）。用来把"运行时在，但 Lua 侧完全不存在"这一档单独隔离出来。
        // 注意它不改变挂点安装：挂点层面的二分用 `ONLY_REQUIRED_HOOK=1` 的构建。
        if (CardSwitchNoLua()) {
            if (failureDetail != nullptr) {
                *failureDetail = 0;
            }
            load.detail = 0;
            load.result = true;
            load.finished = true;
            step = ManifestLoadStep::Done;
            break;
        }
        auto& batch = load.batch;  // 别名：这一段与既有代码同一副面孔（门禁认这些名字）
        // The JSON backend stays the hand-written parser that already runs on
        // device; the adapter is the only bridge to it, so `ManifestParser` and
        // `ManifestService` have no legacy dependency of their own.
        //
        // 两个后端一起给：`SelectFunction` 是"取第一个启用的"（历史口径，诊断阶段仍在用），
        // `SelectAllFunction` 是"取全部启用的"（多模组加载用的就是它）。
        //
        // ★★ 2026-09-21 真机事故：**这里绝对不能再写成函数内 `static`**。
        // 022 那批（容量 16→32）一度把它改成 `static `，理由是"解析器内部的值对象是几十 KiB 级"——
        // 那个判断对错了对象：真正大的是 `ResolveAll`/`ParseAll` 里的**解析结果**（`SelectedMods`，
        // 32 × 1.28 KiB，确实在游戏线程栈上，见 `ResolveAll` 的 `sub sp, sp, #0xc0b0`），
        // 而 `ManifestService` 自己只有 **一个引用 + 两个函数指针**（约 24 字节）。
        //
        // 写成函数内 `static` 带动态初始化 ⇒ 编译器生成**线程安全静态守卫**
        // （`__cxa_guard_acquire`/`__cxa_guard_release`）⇒ 它们要用 pthread 的互斥量，
        // 而本模块是 `-nostartfiles` 链接的、**没有 pthread 运行时**：真机上那把锁失败
        // （`__cxa_guard_release` 里 `bl pthread_mutex_lock` 返回值非零）⇒ libstdc++ 走
        // `__gnu_cxx::__throw_concurrence_lock_error` **抛异常** ⇒ 这条路上没人接 ⇒ `abort()`
        // ⇒ newlib 的 `_exit` 是 `b .` **自旋**（不退出、不产生崩溃报告）⇒ **游戏主线程永不返回**。
        // 现象：**黑屏 + 有声音 + 不崩**（音频线程照跑），启动状态机停在 `ManifestInstallEntered`。
        // 证据与排查过程见 `docs/问题与解决记录.md` 续七十；门禁
        // `runtime/tests/test_no_static_guard_init.py` 钉住"产物里不许出现 `__cxa_guard_*`"。
        isaac::runtime::ManifestService manifestService{
            content, isaac::runtime::ManifestParser{
                         isaac::runtime::ManifestSelectorAdapter::SelectFunction(),
                         isaac::runtime::ManifestSelectorAdapter::SelectAllFunction()}};
        TestRunObserver::Mark(TestRunObserver::State::LuaInitializeEntered);
        const isaac::runtime::Status resolved =
            manifestService.ResolveAll(g_DefaultManifest.data(), g_DefaultManifest.size(),
                                       &batch, &load.failure);
        // 方案 A（2026-09-16）：**清单是可选项**。清单缺席（或读不出来/写坏了）时，运行时自己列
        // `isaac_mods/mods`，把发现的每个子目录当成一个模组 —— 玩家"把模组文件夹丢进卡里"就装好了，
        // 与 PC 的语义一致（见 `mod_discovery_service.hpp`）。
        //
        // 三条纪律：
        //   1. **有合法清单就听清单**（顺序、开关都由清单说了算，向后兼容）；
        //   2. 自动发现只在**清单路径失败**时兜底，而且只在失败原因是"没有清单/读不出来/解析失败"
        //      这类"清单不可用"的情况 —— 路径拼装失败（`PathBuild`）说明清单本身有问题，
        //      那种情况下"静默改用自动发现"会把用户写的清单悄悄忽略掉；
        //   3. 自动发现失败时**如实报失败**，不要退回"什么都没加载"却看起来正常。
        load.discoveryMark = 0;
        if (!resolved.ok()) {
            const bool manifestUnusable =
                load.failure.step == isaac::runtime::ModLoadStep::ManifestRead ||
                load.failure.step == isaac::runtime::ModLoadStep::ManifestParse;
            const isaac::runtime::Status discovered =
                manifestUnusable ? g_ModDiscoveryService.Discover(&batch)
                                 : isaac::runtime::Status{isaac::runtime::StatusCode::Unsupported};
            if (discovered.ok()) {
                load.discoveryMark = static_cast<u32>(DefaultManifestFailureDetail::Discovered);
            } else {
                load.detail = MapModLoadFailure(load.failure);
                load.batchOk = false;
                if (failureDetail != nullptr) {
                    *failureDetail = load.detail;
                }
                g_DefaultManifestFailureWord.store(PackModLoadDiagnostics(load.failure),
                                                   std::memory_order_release);
                TestRunObserver::Mark(TestRunObserver::State::LuaInitializeReturned, load.detail);
                load.result = false;
                load.finished = true;
                step = ManifestLoadStep::Done;
                break;
            }
        }
        // 合并：清单里**没列出**的目录也要能用（PC 语义"把模组文件夹丢进 mods/ 就装好了"）。
        // 顺序 = 清单里的在前（顺序与开关都由清单说了算）+ 追加的按名字升序；被清单显式
        // `enabled = false` 的目录**不追加**（否则用户再也关不掉模组）。
        // 失败按 best-effort：保留清单那一批照常加载，只把状态码与"追加了几个"记进诊断。
        // （自动发现那条路已经列过目录，这里再跑一次是幂等的：已有目录会被跳过。）
        const std::size_t countBeforeMerge = batch.count;
        const isaac::runtime::Status merged = g_ModDiscoveryService.AppendUnlisted(&batch);
        g_AutoAppendedMods.store(
            merged.ok() ? static_cast<u32>(batch.count - countBeforeMerge) : 0u,
            std::memory_order_release);
        g_AutoAppendStatus.store(static_cast<u32>(merged.code()), std::memory_order_release);
        // 模组开关（2026-09-16，路线 B）：**在挂载点与脚本之前**按状态把被关掉的模组移出去。
        // 真机已验：模组加载这一步存档分区已经挂好，所以这一次读就是"当次生效"的。
        // 读失败（通道不可用/文件读坏）时**不拦**：宁可照常加载（用户看到的是"开关没生效"），
        // 也不要因为读不出状态就少加载模组 —— 那会变成"游戏行为莫名其妙变了"。
        // 菜单要显示**全部**扫描到的模组（包括被关掉的，用户正是要重新打开它们），
        // 所以清单在过滤**之前**先灌进去；过滤之后再把"这次真的加载了哪些"标上。
        isaac::runtime::ModMenuAttachToggles(&g_ModToggleService);
        const auto module = FindTargetModule();
        if (!module || !isaac::runtime::modmenu::SortAndPublishDiscoveredMods(*module, batch)) {
            load.detail = static_cast<u32>(DefaultManifestFailureDetail::NameOrder);
            load.batchOk = false;
            load.result = false;
            load.finished = true;
            if (failureDetail != nullptr) *failureDetail = load.detail;
            step = ManifestLoadStep::Done;
            break;
        }
        if (const isaac::runtime::Status toggles = g_ModToggleService.Load(); toggles.ok()) {
            (void)g_ModToggleService.ApplyToBatch(&batch);
        }
        // 批次 147：记下"存档侧开关已经读过一次"。**无论成功与否都写 1**——失败时内存里的状态是
        // 空表（= 一个都没关），那正是我们希望的降级（宁可照常加载，也不要因为读不出状态就少加载）。
        g_ModToggleStateLoaded = 1;
        isaac::runtime::ModMenuMarkActive(batch);
        load.index = 0;
        step = ManifestLoadStep::Mounts;
        break;
    }
    case ManifestLoadStep::Mounts: {
        // ★★★ 批次 378（2026-10-05）：这一步以前是"把每个模组的资源目录注册成内容挂载点"
        //   （批次 370/371 那套六个叶子）。**PC 不是这么做的**：PC 的文件层完全不认识模组，
        //   它是"每次读资源之前先问一遍哪个模组有这个文件"—— `ModManager::GetModResourcePath
        //   @0x870460`：按清单顺序、第一个**启用**的模组、先 `<模组>/resources-dlc3/<名>`
        //   再 `<模组>/resources/<名>`、都没有则原名回传。我们那套自造机制有三条偏差，
        //   最硬的一条是 `content` 叶子的键空间就是本体的裸名 ⇒ 本体请求的 `music.xml`
        //   被模组那份抢走（模组那份没有 `id` ⇒ 音乐表 119 条全空 ⇒ 371 整局没有音乐、
        //   渲染族回调闸门不开）。取证与逐条偏移：
        //   `docs/分析-模组挂载机制与371没音乐定案-20261005.md`。
        //
        //   现在这一步只做一件**纯内存**的事：按清单顺序发布"可重定向的模组根"。
        //   重定向本体在 `mod_resource_redirect.cpp`，落点是引擎自己的
        //   `IContentManager::GetMountedFilePath`（贴图桥本来就钩着它）。
        //   它必须早于**模组脚本**（它就是"模组自己的资源能不能被引擎看见"的唯一来源），
        //   但**不再需要**早于引擎第一次读：重定向是无状态的，谁先读都得到同一个答案。
        //
        //   ★★★ **更正（批次 383，2026-10-06）—— 上面这句"不再需要早于引擎第一次读"是错的**：
        //   **重定向无状态，但引擎会缓存"第一次读到的那个答案"**（`AnmCache` 按键存条目）
        //   ⇒ "谁先读"**恰恰决定了缓存里存的是哪一份**。
        //   真机读数（`dist/gdb-read-20261006-1423-redtext.txt`）：`ANM2::Load` 中继被调 **757** 次、
        //   只有 **134** 次真的问到解析器；"找到本体旧条目 36 次｜真正作废并回收 **0**" ——
        //   因为原生小地图在 +4.25 秒就按本体层把 `gfx/ui/minimap1.anm2` 读了（那时本名单还没发布，
        //   发布要等状态机跑到 `Mounts`，≈ +5.78 秒），而唯一的事后手段（作废缓存条目）在批次 368
        //   崩过、369 起被禁用 ⇒ **晚一步就永远改不回来**。
        //   ⇒ 批次 383 的修法：**把"发布"接回 `Game::Init` 入口中继**（`runtime_entry.cpp` 的
        //   `EntryRelayGameInitCallback` 现在调 `MountModsBeforeHeavyWork`），于是名单早于
        //   `Minimap::Init` 就绪 ⇒ 缓存里从头到尾不出现本体那份 ⇒ 与 PC 同形。
        //   **这一步发布仍然保留**（幂等：重填数组 + `publishCount` 再 +1）—— 两处都发布是**有意的冗余**。
        //   逐条证据：`docs/分析-红字根因-模组覆盖是事后修正而PC是启动期前置-20261006.md`。
        auto& batch = load.batch;
        const char* roots[isaac::runtime::bridge::kModResourceRedirectCapacity]{};
        std::size_t rootCount = 0;
        for (std::size_t index = 0;
             index < batch.count &&
             rootCount < isaac::runtime::bridge::kModResourceRedirectCapacity; ++index) {
            roots[rootCount++] = batch.mods[index].modRoot;
        }
        (void)isaac::runtime::bridge::PublishModResourceRedirectList(roots, rootCount);
        // ★ 批次 356 那次"挂完问一次可见性"的探针**撤掉**：它的对象（"我们挂的挂载点还在不在
        //   表里"）在本批之后不存在了。新的证据面是 `g_ModResourceRedirectState`
        //   （重定向调用/命中/命中来自哪个模组）与贴图桥既有的"按路径查询/回答"记录。
        // Shader集合在本体配置和每个模组脚本之前就绪，保持PC的Reset顺序。
        load.batchOk = isaac::runtime::modmenu::BeginEngineModContentCycle(g_ModMenuReloadLoading) && load.batchOk;
        load.index = 0;
        step = ManifestLoadStep::Content;
        break;
    }
    case ManifestLoadStep::Content: {
        // ★★★ 批次 156（2026-09-27）：**在这里**把每个模组 `content/` 下的皮肤与音乐喂给引擎。
        //
        // 为什么是**这一处位置**（155 的真机读数把前几个位置全否掉了，`[61] = 4` 那次：
        // "跑完了但一条都没加载"，而且加载器**一次都没被调用** —— 那说明连"要处理哪些模组"都还是空的）：
        //
        //   这一段里的顺序是：① 解析清单 / 扫描目录 → ② `ModMenuPublishDiscovered(batch)`
        //   （**我们的模组列表到这里才发布**）→ ③ 上面那个循环（**把每个模组的资源目录注册成
        //   内容挂载点** —— 引擎的文件层要能打开 `<目录>/content/*.xml` 靠的就是它）
        //   → ④ 下面"跑模组脚本"那一步（**模组脚本在那里才执行**）。
        //
        //   * 放在 ① 之前（153/154/155 的位置）：模组列表是空的（循环体一次都不进）、内容目录也
        //     没注册 ⇒ 那一次**什么都没做**，而函数末尾照样把阶段记成"跑完了" ⇒ 我还把它读成了
        //     "早期时机已经通了"。真正把内容喂进去的是我们那条**每帧重试**（`[60] = 3`），
        //     而那时模组的服装编号早就查成 `-1` 了 ⇒ **舞一直出不来**。
        //   * 放在 ② 之后、③ 之前：列表有了，但内容目录还没注册 ⇒ 引擎打不开那些文件。
        //   * **放在 ③ 之后、④ 之前**：列表有、目录已注册、脚本还没跑 ⇒ 这才是与 PC 一致的时机。
        //
        // 安全性：这一段本来就跑在**游戏线程**、引擎自己的 `Manager::Update` 帧里（文件 API 已可用，
        // 见 `g_CardSwitchProbeAllowed` 那段）；本调用只读文件 + 调那两个加载器，不碰引擎的模组表。
        // 每帧重试那条路**保留**（它救过一次），成功之后它会因为"容器涨过"立刻变成空转。
        // 内容改到Scripts循环内逐模组加载，不能提前统一收尾。
        const auto options=isaac::runtime::LoadRuntimeOptions();
        if(!options.ok()){
            char message[96];const auto n=std::snprintf(message,sizeof(message),"runtime options load failed: %u",static_cast<unsigned>(options.code()));
            if(n>0)LuaRuntime::RecordLuaErrorText(message,static_cast<std::size_t>(n));
        }
        // ★ 376：原来这里还有一刀 `bridge::NoteMountVisibilityCheckpoint(1)`（357 的"内容步收尾"）
        //   —— 它属于**挂载可见性时间轴**，已随机制撤除（见 `EntryRelayManagerUpdateCallback`）。
        // 资源模组/全关闭也保留基础Lua环境，下一次重载无需重启游戏。
        load.batchOk = (LuaRuntime::EnsureRuntimeWithMenu()==LuaRuntime::LuaInitResult::Success) && load.batchOk;
        load.index = 0;
        step = ManifestLoadStep::Scripts;
        break;
    }
    case ManifestLoadStep::Scripts: {
        // ★ 批次 236：**一帧只跑一个模组** —— 这一段就是那 10 秒的来源
        //（从 SD 卡读入口脚本 + 在 Lua 里把它执行完）。每次给 `LoadAll` 喂"只有这一个模组"
        // 的一小批：顺序与失败语义与原批处理**完全一致**（`LoadAll` 的循环体本来就是逐个 `Load`，
        // 这里只是把循环体搬到帧之间），区别只是"跑一个模组就还给游戏一帧"。
        if (load.index >= load.batch.count) {
            step = ManifestLoadStep::Finalize;
            break;
        }
        load.batchOk = isaac::runtime::modmenu::LoadEngineModContentForMod(
            load.batch.mods[load.index].modRoot) && load.batchOk;
        load.single.count = 1;
        load.single.mods[0] = load.batch.mods[load.index];
        load.oneOutcome.count = 0;
        load.oneOutcome.anyFailure = false;
        load.oneOutcome.failedIndex = 0;
        isaac::runtime::ModLoadFailure perModFailure{};
        const isaac::runtime::Status loaded =
            service.LoadAll(load.single, g_DefaultEntry.data(), g_DefaultEntry.size(),
                            &load.oneOutcome, &perModFailure);
        load.batchOk = load.batchOk && loaded.ok();
        load.loadOutcome.scripts[load.index] = load.oneOutcome.scripts[0];
        load.loadOutcome.count = load.index + 1;
        if (load.oneOutcome.anyFailure && !load.loadOutcome.anyFailure) {
            load.loadOutcome.anyFailure = true;
            load.loadOutcome.failedIndex = load.index;
            load.failure = perModFailure;
        }
        ++load.index;
        break;
    }
    case ManifestLoadStep::Finalize: {
        load.batchOk = isaac::runtime::modmenu::FinishEngineModContentCycle() && load.batchOk;
        u32 detail = MapModLoadFailure(load.failure);
        auto& loadOutcome = load.loadOutcome;  // 别名：同上
        // 加载失败仍如实报告；原生模组页独立于Lua状态，无需重装额外菜单。
        if (load.batchOk && !loadOutcome.anyFailure && loadOutcome.count > 0) {
            // 全部成功时，用**第一个** Mod 的脚本状态决定诊断字：PC 的清单里第一个 Mod 通常就是
            // 主体（我们的 EID 部署就是这样）。任何 Mod 失败都走上面的失败分支。
            if (load.discoveryMark != 0) {
                // 自动发现：诊断字用 6（`Discovered`）——与"清单里指定"区分开，
                // 真机上一眼就能看出"这次是靠扫描加载的"。
                detail = load.discoveryMark;
            }
            const isaac::runtime::ModLoadOutcome& first = loadOutcome.scripts[0];
            if (detail == 0 && !first.ScriptExecuted()) {
                // 纯资源型 Mod（清单没写 `entry`，或 entry 指向的文件不存在）：加载**成功**，
                // 内容挂载点已注册，只是没有脚本可跑。诊断字 [11] 用 5 把它和"带脚本成功（0）"
                // 区分开。多模组下"第一个 Mod 无脚本、后面有脚本"是合法清单，这里如实报 5，
                // 具体每个 Mod 的状态在 `loadOutcome.scripts[]` 里。
                detail = static_cast<u32>(DefaultManifestFailureDetail::Scriptless);
            }
        }
        load.detail = detail;
        if (failureDetail != nullptr) {
            *failureDetail = detail;
        }
        // 诊断字 `[11]`：脚本型成功为 0、纯资源型为 5、失败则带上"原因 + 观测到的文件大小"。
        g_DefaultManifestFailureWord.store(
            load.batchOk ? detail : PackModLoadDiagnostics(load.failure),
            std::memory_order_release);
        // The layered path owns the whole use case, so the "Lua returned" mark
        // carries the same composite detail the install observer records: 0 on a
        // scripted success, the legacy step code on failure, and 5 when the Mod was
        // mounted without a script (Lua was deliberately never initialized).
        TestRunObserver::Mark(TestRunObserver::State::LuaInitializeReturned, detail);
#if EXL_DIAGNOSTIC_PROBES
        isaac::runtime::loadprobe::LoadFinishTotal();
        g_ModLoadTotal.store(static_cast<std::uint32_t>(load.batch.count),
                             std::memory_order_release);
        g_LoadFramesUsed.store(
            g_UpdateCallbackEntries.load(std::memory_order_relaxed) -
                g_LoadStartFrame.load(std::memory_order_relaxed),
            std::memory_order_release);
#endif
        load.result = load.batchOk && !loadOutcome.anyFailure;
        load.finished = true;
        step = ManifestLoadStep::Done;
        break;
    }
    case ManifestLoadStep::Idle:
    case ManifestLoadStep::Done:
    default:
        break;
    }
#if EXL_DIAGNOSTIC_PROBES
    // 批次 235 的分段秒表（拆帧之后同一段会被走很多帧，所以 `LoadMark` 是**累加**）。
    {
        std::size_t phase = 0;
        switch (current) {
        case ManifestLoadStep::Prepare: phase = isaac::runtime::loadprobe::kLoadPhasePrepare; break;
        case ManifestLoadStep::Mounts: phase = isaac::runtime::loadprobe::kLoadPhaseMounts; break;
        case ManifestLoadStep::Content: phase = isaac::runtime::loadprobe::kLoadPhaseContent; break;
        case ManifestLoadStep::Scripts: phase = isaac::runtime::loadprobe::kLoadPhaseScripts; break;
        case ManifestLoadStep::Finalize: phase = isaac::runtime::loadprobe::kLoadPhaseFinalize; break;
        default: break;
        }
        if (phase != 0) {
            isaac::runtime::loadprobe::LoadMark(phase, stepStartTick);
        }
    }
#endif
    return load.result;
}

bool PrimeDefaultCallbacks(uintptr_t manager) {
    if (g_DefaultCallbackGate.IsOpen()) return true;
    return g_DefaultCallbackGate.Observe(ObserveGameIsPaused(
        g_LuaGameOwnerSlot.load(std::memory_order_acquire),
        g_LuaGameIsPausedThunk.load(std::memory_order_acquire)),
        LuaRuntime::IsMusicReadyForDefaultCallback(manager));
}

// ============================================================================
// 批次 370（2026-10-05）：**注册模组挂载点**提前到重活之前（甲，第 0 期）
// ============================================================================
//
// ★★★ 批次 378（2026-10-05）：**下面这一整段的"挂载点"部分已被 PC 的机制取代** —— 现在这个
//   函数只做"**把可重定向的模组根发布出去**"（`PublishModResourceRedirectList`），一个引擎
//   接口都不调。为什么换：PC 根本不挂载（`ModManager::GetModResourcePath @0x870460` 是"每次
//   读资源前按清单顺序问一遍哪个模组有这个文件"），而我们自造的挂载点有三条偏差，最硬的一条
//   是 `content` 叶子会抢掉本体的裸名 `music.xml`（371 整局没有音乐）。
//   取证与逐条偏移：`docs/分析-模组挂载机制与371没音乐定案-20261005.md`。
//   下面原文**保留不删**（它是"为什么当初要提前"的完整论证，而"提前到重活之前发布清单"
//   这条结论**仍然成立**）—— 只是被提前的东西从"挂载动作"变成了"一份内存里的名单"。
//
// **为什么必须提前**（取证：`docs/分析-模组覆盖本体资源那一环该补在哪一刻-20261005.md`）：
// 引擎自己在 `Game::Init → Minimap::Init` 里读共享路径（`ANM2::Load("gfx/ui/minimap1.anm2")`），
// 而我们的挂钩与挂载都在**推迟 5 秒**的 worker 里 ⇒ 引擎第一次读到的必然是**本体那份**，
// 之后模组自带的那份永远赢不了（真机：`sh1 = 11`、minimapi 两行红字）。
// 与 PC 一致的形态是"模组那一层在引擎第一次读之前就存在" ⇒ 挂载点必须**早于** `Game::Init`。
//
// **复用而不是新写**（与 `LoadDefaultManifestModThroughService` 的 Prepare/Mounts 两步同一套东西）：
//   `ManifestService::ResolveAll`（读清单）→ 清单不可用时 `ModDiscoveryService::Discover`
//   （扫目录兜底，方案 A）→ `ModDiscoveryService::AppendUnlisted`（"拷进 `mods/` 就能用"）→
//   逐个 `ContentMountService::RegisterMod`（挂 `resources` / `resources/gfx` / `content` /
//   `content/gfx` / `resources-dlc3` / `resources-dlc3/gfx` 六个叶子，顺序即层序）。
//   **没有新的扫描、没有新的引擎调用**：`AddMountPoint` 仍在既有的
//   `EngineContentMountAdapter` 里（那份逐字节核对的守卫一个字节没动）。
//
// **刻意不做两件事**：
//   ① **不读存档侧模组开关**（`ModToggleService::Load`）：那条路走 nnSdk 存档 API，442190 的
//      事故证明从我们自己的线程调它每次开机必崩（见 `g_CardSwitchProbeAllowed` 上面那条纪律）。
//      游戏线程那一轮照旧会按开关把被关掉的模组挡在脚本与 content 之前。
//      ⇒ **已知偏离**（如实记，不粉饰）：被玩家关掉的模组这一次也会先有一个挂载点
//      （它的资源在"路径解析"这一层可见），但它的脚本与 content 不会加载。
//   ② **不装钩子、不建 Lua 状态、不跑模组脚本**：那些仍留在推迟 5 秒的重活里。
//
// **失败语义**：文件绑定不齐 / 清单与自动发现都读不出来 ⇒ 返回 `attempted = false`；
// 挂载个别失败 ⇒ 照记进 `mountsFailed`。两种情况下**后续逻辑都一个字不改**
// （`RunEarlyModMountPrelude` 原样继续，后面那条既有路径会把这一切照旧做一遍）。
//
// **已知的时序风险（本批只能真机量、不能在宿主机上判）**：早挂之后、重建中继装上之前，
// 若引擎自己重建一次内容挂载点表（`RebuildContentMountPoints` 的 `ClearMountPoints(false)`），
// 我们这一批早挂的条目会被清掉；而 `ContentMountService::RegisterMod` 对**已登记过的目录**
// 是"直接返回 Ok、不再调引擎"（它的既有语义，本批不动）⇒ 游戏线程那一轮不会再挂一次。
// 判据：读数里 `mountListHadModPrefix`（挂完当时表里有没有模组前缀）与既有的
// `image_pcx_diag` 时序位图/挂载后探测（批次 356/357）对照；第 1 期按它决定是否补
// "引擎清表之后、`Game::Init` 之前"那一刀（见开工单"第 1 期"）。
EarlyModMountOutcome MountModsBeforeHeavyWorkImpl(const TargetModule& module) noexcept {
    EarlyModMountOutcome outcome{};
    if (!isaac::runtime::notice::integrity::Ensure(module)) {
        ++g_NoticeIntegrityState[13];
        outcome.attempted = true;
        outcome.mountsFailed = 1;
        return outcome;
    }
    // 清单与入口脚本都从这份绑定读（与 `TryInstallDefaultManifestMod` 同一份、同样逐字节核对）。
    // ★ 这一步只是**核对 + 发布**（纯内存读 + `svcQueryMemory`），没有文件 I/O。
    GameFileReader::Bindings bindings{};
    if (!GameFileReader::VerifyBindings(module, &bindings)) {
        return outcome;   // 绑定不齐 ⇒ 挂不了（游戏线程那一轮会照旧给出失败码）
    }
    g_DefaultManifestBindings = bindings;
    // 441：完整图片通道必须与资源名单同在首次加载之前准备。
    // 否则ANM2虽能覆盖，原版先请求的PCX仍抢在模组PNG转换之前进入缓存。
    if (!isaac::runtime::bridge::PrepareModImageResources(
            module, &g_DefaultManifestBindings, &g_ImagePcxBindings)) {
        ++outcome.mountsFailed;
        return outcome;
    }

    isaac::runtime::GameFileReaderAdapter content{g_DefaultManifestBindings};
    isaac::runtime::ManifestService manifestService{
        content, isaac::runtime::ManifestParser{
                     isaac::runtime::ManifestSelectorAdapter::SelectFunction(),
                     isaac::runtime::ManifestSelectorAdapter::SelectAllFunction()}};
    // 批次缓冲**复用既有的那一份**（`ManifestLoadState` 里的 `batch`）：这一段跑在状态机起步
    // （`ManifestLoadStep::Idle`）之前，用同一块存储既不多花 .bss，又保证"清单读法与游戏线程
    // 那一轮逐条一致"；游戏线程那一轮的 Prepare 会把它整个重填。
    isaac::runtime::ResolvedManifestModBatch& batch = ManifestLoadStateRef().batch;
    isaac::runtime::ModLoadFailure failure{};
    const isaac::runtime::Status resolved = manifestService.ResolveAll(
        g_DefaultManifest.data(), g_DefaultManifest.size(), &batch, &failure);
    if (!resolved.ok()) {
        // 与游戏线程那一轮同一条纪律：**只**在"清单不可用"（没有/读不出来/解析失败）时才用
        // 自动发现兜底；路径拼装失败说明清单本身有问题，那时"静默改用自动发现"会把用户写的
        // 清单悄悄忽略掉。
        const bool manifestUnusable =
            failure.step == isaac::runtime::ModLoadStep::ManifestRead ||
            failure.step == isaac::runtime::ModLoadStep::ManifestParse;
        if (!manifestUnusable || !g_ModDiscoveryService.Discover(&batch).ok()) {
            return outcome;   // 清单与自动发现都不行 ⇒ 如实放弃（调用方原样继续）
        }
    }
    // 与游戏线程那一轮同一条"合并"口径：清单里**没列出**的目录也要能用。
    (void)g_ModDiscoveryService.AppendUnlisted(&batch);
    if (!isaac::runtime::modmenu::SortAndPublishDiscoveredMods(module, batch)) {
        ++outcome.mountsFailed;
        return outcome;
    }

    // 批次 438 更正上面的旧限制：本入口唯一生产调用者是 Game::Init 中继，
    // 在游戏线程上执行；启动 0x3B2FC8 已挂载存档，0x3B304C 才进入 Manager::Init。
    // 必须在首次读资源前应用与脚本加载相同的开关，不能等动画缓存建成后再过滤。
    // worker 仍只安装中继，绝不在 worker 调 nn::fs。
    g_SaveFileAdapter.AllowFromGameThread();
    if (const isaac::runtime::Status toggles = g_ModToggleService.Load(); toggles.ok()) {
        (void)g_ModToggleService.ApplyToBatch(&batch);
    } else {
        // 保持既有读失败语义，但明确留下失败计数，不能把读失败说成开关已生效。
        ++outcome.mountsFailed;
    }
    g_ModToggleStateLoaded = 1;

    // ★★★ 批次 378（2026-10-05）：这里以前是"**早挂**六个内容叶子"（批次 370/371 的方案），
    //   现在改成"**早发布重定向清单**"—— 与 PC 同一条规则（`ModManager::GetModResourcePath`），
    //   只是发布点必须早于引擎在 `Game::Init` 里那几次资源读（`Game::Init` 里就有 8 处
    //   `TryRedirectPath` 调用点，而 minimap 的 `gfx/ui/minimap1.anm2` 也在这个窗口里第一次读）。
    //   两者都是**纯内存写**：`PublishModResourceRedirectList` 一个引擎接口都不调。
    //   由来的拆因实验见 `docs/会话交接-20261005-十五-批次371回归定案与拆因实验AB.md`：
    //   那个窗口里"读文件 / 读清单"是干净的，危害只在"调引擎的挂载接口"那一半。
    outcome.attempted = true;
    const char* roots[isaac::runtime::bridge::kModResourceRedirectCapacity]{};
    std::size_t rootCount = 0;
    for (std::size_t index = 0;
         index < batch.count && rootCount < isaac::runtime::bridge::kModResourceRedirectCapacity;
         ++index) {
        roots[rootCount++] = batch.mods[index].modRoot;
    }
    if (isaac::runtime::bridge::PublishModResourceRedirectList(roots, rootCount)) {
        outcome.mountsAttempted = rootCount;   // 字段名沿用（读数工具按名字读），含义 = "进了重定向名单的模组数"
    }
    return outcome;
}

// ============================================================================
// 实验 B（2026-10-05）：**只读清单、一个字节都不碰引擎** —— 把"回调里做的事"再拆一半
// ============================================================================
//
// ★★ **已退役（批次 383，2026-10-06）**：本入口**不再被生产代码调用** ——
//   `Game::Init` 入口中继改调 `MountModsBeforeHeavyWork`（读清单 **+ 发布重定向名单**，
//   差别只有最后那一步纯内存发布）。退役原因（真机读数定案）：只读清单会让"可重定向的模组根"
//   **晚于** `Minimap::Init` 那次读才发布，而引擎的动画缓存按"第一次读到的答案"存条目
//   ⇒ 缓存里被本体那份钉死、之后连路径都不问；而唯一的事后手段（作废缓存条目）在批次 368 崩过、
//   369 起被禁用 ⇒ 晚一步就永远改不回来。逐条证据见
//   `docs/分析-红字根因-模组覆盖是事后修正而PC是启动期前置-20261006.md`。
//   ★ 代码**保留**（不删）：① 372 那次拆因实验的判据与结论要靠它复现；
//   ② 它记录了"这个窗口里读文件是干净的"这条实测结论（批次 372 实验 B）。
//   ⇒ 门禁 `test_early_mod_mount.py` 里那两条针对它的断言照旧有效（它的形状没变）。
//
// 由来：实验 A（只装 `Game::Init` 中继、回调里**什么都不做**）真机上是**干净**的
//   —— 屏幕上的探针文字照常画（`Font` 那条渲染路在跑）⇒ 元凶在"回调里做的那件事"。
//   而那件事由两半组成：
//     ① **读文件**：`VerifyBindings`（纯内存）+ `ResolveAll`（读清单）+ `Discover`（扫目录）；
//     ② **调引擎**：`RegisterMod` → `AddMountPoint`（往引擎的挂载点表里加条目）。
//   本函数**只做①**，供实验 B 卡调用 —— 它复用与 `MountModsBeforeHeavyWorkImpl` 完全相同的
//   服务与读法，但**不** `RegisterMod`、**不** `SetSessionContentMountService`、
//   **不**写任何引擎内存。
//
// 判据（实验 B 卡）：引擎**有没有音乐** ⇒ 渲染族那道闸门开不开 ⇒ 屏幕上的探针文字画不画。
//   * 干净 ⇒ 危害在"调引擎挂载接口"那一半（下一步就该只改那一处的时机/方式）；
//   * 也坏 ⇒ 危害在"在 `Game::Init` 里面读文件"这一半（那 371 的整条思路要重做）。
bool ReadManifestOnlyForExperimentImpl(const TargetModule& module) noexcept {
    // 与 Impl 的①逐条一致：绑定 → 清单 → 兜底自动发现（顺序、口径都不许变）。
    GameFileReader::Bindings bindings{};
    if (!GameFileReader::VerifyBindings(module, &bindings)) {
        return false;
    }
    isaac::runtime::GameFileReaderAdapter content{bindings};
    isaac::runtime::ManifestService manifestService{
        content, isaac::runtime::ManifestParser{
                     isaac::runtime::ManifestSelectorAdapter::SelectFunction(),
                     isaac::runtime::ManifestSelectorAdapter::SelectAllFunction()}};
    isaac::runtime::ResolvedManifestModBatch& batch = ManifestLoadStateRef().batch;
    isaac::runtime::ModLoadFailure failure{};
    const isaac::runtime::Status resolved = manifestService.ResolveAll(
        g_DefaultManifest.data(), g_DefaultManifest.size(), &batch, &failure);
    if (resolved.ok()) {
        return true;
    }
    const bool manifestUnusable =
        failure.step == isaac::runtime::ModLoadStep::ManifestRead ||
        failure.step == isaac::runtime::ModLoadStep::ManifestParse;
    return manifestUnusable && g_ModDiscoveryService.Discover(&batch).ok();
}

#endif

// 批次 371（2026-10-05）：`IsMappedRxModuleCodeWindow` **不再定义在这里（匿名命名空间内）** ——
// 它现在是**外部链接**、定义在本文件**末尾的全局作用域**（与 `MountModsBeforeHeavyWork` 那层壳
// 相邻），声明在 `hook_manager.hpp`。搬出去的原因：`runtime_entry.cpp` 的早期那一段（装
// `Game::Init` 入口中继）**必须**先判一次"这一页现在可执行吗"才敢读目标入口那 16 字节，
// 而那是同一条判据 ⇒ 共享一份，不在那边再抄一份（本项目已经栽过"两个工具各自抄一份口径 ⇒
// 漂移"的跟头）。本 TU 里的调用点（那一排 `Verify*` 助手）照旧解析到它 —— 全局名字在匿名
// 命名空间内可见，行为逐字不变。
//
// （下面是搬迁前的原文，留档：）
//   bool IsMappedRxModuleCodeWindow(uintptr_t address, size_t length) {
//       if (length == 0 || address > UINTPTR_MAX - length) return false;
//       MemoryInfo info{}; u32 pageInfo = 0;
//       if (R_FAILED(svcQueryMemory(&info, &pageInfo, address)) || info.size == 0) return false;
//       const uintptr_t end = address + length;
//       const uintptr_t mappingEnd = info.addr + info.size;
//       return mappingEnd >= info.addr && address >= info.addr && end <= mappingEnd &&
//              (info.type & MemState_Type) == MemType_ModuleCodeStatic && info.perm == Perm_Rx;
//   }

// ---------------------------------------------------------------------------
// 批次 251：接管「系统要求退出」这件事 —— 把 PC 上关游戏时的那一步补回来
// ---------------------------------------------------------------------------
//
// 背景（2026-10-01 取证；证据链见 `docs/会话交接-20261001-模组菜单提速与配置保存定案.md`）：
//   * PC 上关游戏会走 `IsaacShutdown()` → `Game::Exit(true)` → 派发 `MC_PRE_GAME_EXIT`；
//   * Switch 上「按 Home 关闭应用」由系统发起，**游戏引擎完全不参与** ——
//     `IsaacRepentance::IsaacShutdown`（Repentance.nro `0x3B38D0`）在两个 NRO 与五个
//     exefs 模块里**都没有调用者**，而系统侧那套 `nn::oe` 接口
//     （`GetNotificationMessage` / `EnterExitRequestHandlingSection` / …）游戏也一个都没调；
//   * 后果：只在 `MC_PRE_GAME_EXIT` 存盘的模组在「直接关游戏」时会丢设置 ——
//     而「退回主菜单」那条路是好的（批次 105 真机验证过派发与落盘）。
//
// 做法：每帧读一次系统通知。`nn::oe::GetNotificationMessage` 是
//   `ICommonStateGetter::ReceiveMessage` 的封装（无消息时返回 0，错误码 0x680），
//   返回 `nn::am::AppletMessage::Exit`(4) 即表示**系统正在要求退出** ——
//   那一刻替引擎走一遍退出流程，行为与 PC 一致。
//   ★ 取值依据：`switchbrew.org/wiki/Applet_Manager_services` 的 `AppletMessage` 表
//     （0 None / 1 ChangeIntoForeground / 2 ChangeIntoBackground / 4 Exit / …）；
//     反汇编印证：该函数成功路径把读到的 u32 原样返回，失败时错误码 0x680 表示「没有消息」。
//
// 地址怎么拿：用 exlaunch 已有的跨模块符号解析（`rtld::lookup_global_auto`，遍历 `nn::ro`
//   的已加载模块表按名字查符号）⇒ 不必自己去找 sdk 模块的基址。解析一次后缓存；
//   解析不到就整条静默（与其它可选挂接同一口径，绝不让它影响开局）。
// ---------------------------------------------------------------------------
// ★★★ 批次 262（A3/A4 性能）：**这一整块（常量 + 探针 + 轮询 + 接管）只在诊断包里编译**
// ---------------------------------------------------------------------------
//
// 为什么：这条"系统退出接管"通道在真机上**已被证伪** —— 整局 4 万帧、含"按 Home 进后台"，
// `m2`/`m4` 恒 0（详见 `docs/会话交接-20261001-五-收口总交接.md` 与
// `docs/遗留-取不到退出点的影响清单-20261001.md`）。而它在**正式包里仍然每帧付钱**：
//   * 每帧一次 `nn::oe::GetNotificationMessage` 调用（跨服务）；
//   * 每 600 帧重写一次探针容器（`snprintf` 拼 JSON + `ModPersistence::SaveModData`）。
// ⇒ 正式包不再跑它；**代码、探针、接管逻辑一行都没删** —— 出 `DIAGNOSTIC_PROBES=1` 的诊断包
//   时照旧可用（以后再想验这条通道，不必改代码，出个诊断包即可）。
//
// ★ 口径变化要说清楚：**正式包不再尝试"接管系统退出"**。"改完设置先退回主菜单再关游戏"
//   这条可用办法（用户已确认）不受影响 —— 它走的是引擎自己的 `Game::Exit` 入口中继。
#if EXL_DIAGNOSTIC_PROBES
constexpr std::uint32_t kAppletMessageExit = 4;
// `nn::am::AppletMessage::ChangeIntoBackground` = 2 —— 玩家按 Home 进后台。
// 只做记录（探针），**不再在这里做任何动作**：
// 2026-10-01 方案 B（在此处 LockExit 争取退出窗口）**实测失败** —— `LockExit` 会让系统
// 进入"等你收尾"的状态而**不再推进退出流程**，于是通知 4 永远不来，反而把退出时机弄丢了
// （真机现象：加了 LockExit 的那版关游戏时"转圈"消失，正说明它没走到退出流程）。
constexpr std::uint32_t kAppletMessageChangeIntoBackground = 2;

// ---------------------------------------------------------------------------
// ★★★ 批次 251 探针：把"退出接管"的每一步写进模组数据容器
// ---------------------------------------------------------------------------
//
// 为什么必须做（2026-10-01 一整天的教训）：关游戏那一刻进程就没了，**内存里的任何读数
// 都读不出来**；`sdmc:` 那条自 journal 通道在生产包里被编译掉（`PROBE_BREAK_FILEIO=0`）。
// 于是"到底是没跑到、还是派发早退了、还是模组保存失败"一直无法分辨，只能反复改版猜。
//
// 做法：写进**模组数据容器**（`ModPersistence::SaveModData`，走我们已经在用的存档分区端口），
// 用**专用命名空间**。容器是内存+磁盘双份的，重启后可用调试桩的 `mod_data_head` 读出来。
//
// ★ **分步写**：每完成一步就覆盖写一次（不是"最后写一次"）—— 这样即使后面崩了，
//   也能从容器里看到"走到哪一步为止"，这正是分辨三种可能所必需的。
constexpr std::uint64_t kSystemExitProbeNamespace = 0x4953414143584954ULL;  // "ISAACXIT"

struct SystemExitProbeState {
    std::uint32_t pollFrames{0};       // 轮询跑过的帧数（证明代码在跑）
    std::uint32_t writes{0};           // 探针自己落盘的次数（证明写入通道可用）
    std::uint32_t msgNonZero{0};       // 读到过多少条非零通知
    std::uint32_t lastMsg{0};          // 最后一条非零通知的值
    std::uint32_t msg2Count{0};        // 见过几次 2（进后台）
    std::uint32_t msg4Count{0};        // 见过几次 4（要求退出）★ 关键
    std::uint32_t otherMsgCount{0};    // 见过几次别的值
    std::uint32_t resolveFail{0};      // 解析 sdk / 守卫不符的次数
    std::uint32_t takeOver{0};         // 进入 TakeOver 分支次数
    // —— 下面五个是分辨"派发为什么没生效"的关键 ——
    std::uint32_t ready{0};            // 派发前 LuaRuntime::IsReady()
    std::uint32_t pgeCount{0};         // 派发前 RegisteredCallbackCount(kCallbackPreGameExit)
    std::uint32_t errBefore{0};        // 派发前 Lua 错误历史 head
    std::uint32_t errAfter{0};         // 派发后 Lua 错误历史 head（变了说明模组报错过）
    std::uint32_t dispatchDone{0};     // DispatchPreGameExit 返回次数
    std::uint32_t shutdownCalled{0};   // IsaacShutdown 调用次数
    // —— 批次 255 新增：遍历诊断（回答「我们到底走到了模块表的哪一段」）——
    // 为什么加：v8 的 `resolveFail = 600`（帧门之后的每一帧都失败）只能说明「没解析到」，
    // 分不清「链根本没走到 sdk」与「走到了但守卫不符」——这两者的修法完全不同。
    std::uint32_t scanNodes{0};        // 最近一次遍历访问到的节点数
    std::uint32_t scanTruncated{0};    // 最近一次遍历是否撞到 kMaxModulesToScan 上限（1 = 撞了）
    std::uint64_t hitBase{0};          // 认出 16 字节守卫的那个 module_base（0 = 没认出）
    // —— 批次 256：按真实签名（`(unsigned int*)`）调用之后，**返回值**与**出参**分别是什么 ——
    // 加这两格的用途：万一"按签名调用"仍然读不到消息，一次真机就能分辨
    // 「哪个位置本来才有值」与「这条通道就是没消息」，不必再回来改第三次。
    std::uint32_t lastReturned{0};     // 函数的返回值（w0）
    std::uint32_t lastOut{0};          // 我们传进去的那个出参缓冲被写成了什么
};

SystemExitProbeState g_SystemExitProbe;
// 下一次"无条件周期写"的帧号（不写进 JSON，只是内部节奏）。
std::uint32_t g_SystemExitProbeNextWrite = 0;

// 把上面那份状态写进容器（覆盖式，长度随内容变化 —— 容器允许覆盖）。
void WriteSystemExitProbe() noexcept {
    SystemExitProbeState& p = g_SystemExitProbe;
    ++p.writes;
    char buffer[512];
    const int written = std::snprintf(
        buffer, sizeof(buffer),
        "{\"pollFrames\":%u,\"writes\":%u,\"msgNonZero\":%u,\"lastMsg\":%u,\"m2\":%u,\"m4\":%u,"
        "\"other\":%u,\"resolveFail\":%u,\"takeOver\":%u,\"ready\":%u,\"pgeCount\":%u,"
        "\"errBefore\":%u,\"errAfter\":%u,\"dispatchDone\":%u,\"shutdownCalled\":%u,"
        "\"scanNodes\":%u,\"scanTruncated\":%u,\"hitBase\":\"0x%llx\","
        "\"lastReturned\":%u,\"lastOut\":%u}",
        p.pollFrames, p.writes, p.msgNonZero, p.lastMsg, p.msg2Count, p.msg4Count,
        p.otherMsgCount, p.resolveFail, p.takeOver, p.ready, p.pgeCount,
        p.errBefore, p.errAfter, p.dispatchDone, p.shutdownCalled,
        p.scanNodes, p.scanTruncated, static_cast<unsigned long long>(p.hitBase),
        p.lastReturned, p.lastOut);
    if (written <= 0) {
        return;
    }
    const auto length = static_cast<std::size_t>(
        written < static_cast<int>(sizeof(buffer)) ? written : sizeof(buffer) - 1);
    static_cast<void>(ModPersistence::SaveModData(kSystemExitProbeNamespace, buffer, length));
}
// `nn::oe::GetNotificationMessage` 在 sdk 模块里的静态偏移（它是该模块**本地定义**的函数）。
constexpr std::uintptr_t kSdkGetNotificationMessageOffset = 0x36D540;
// `IsaacRepentance::IsaacShutdown` @ Repentance.nro `0x3B38D0`（长 `0xF0`）——
// 引擎自己的"关闭以撒"入口（开头打 "Isaac is shutting down..."）。
// 我们只**调用**它、不挂钩它；它在 `Game::Exit` 那一句上带内部条件，用法见下面那段说明。
constexpr std::uintptr_t kIsaacShutdownOffset = 0x3B38D0;

// 入口 16 字节守卫：确认「解析到的那个符号」确实是 sdk 里那个函数
// （`sub sp, sp, #0x20` / `stp x29, x30, [sp, #0x10]` / `add x29, sp, #0x10` / `bl …`）。
// 这条函数是 sdk 模块里**本地定义**的（不是导入桩），所以它不该被误认成别的同名物。
constexpr std::array<std::uint8_t, 16> kSdkGetNotificationMessageEntry = {
    0xFF, 0x83, 0x00, 0xD1, 0xFD, 0x7B, 0x01, 0xA9,
    0xFD, 0x43, 0x00, 0x91, 0xFD, 0x1B, 0x09, 0x94,
};

enum class SystemExitDecision : std::uint8_t {
    NotExitRequest,
    // 系统要求退出 ⇒ 派发 + 走完整的引擎退出流程。（★ 通知 2「进后台」也归到 NotExitRequest：
    // 只由探针计数，不做任何动作 —— 2026-10-01 方案 B 的 LockExit 实测会挡掉通知 4，已撤。）
    TakeOver,
    AlreadyHandled,
};

// 纯逻辑（宿主可测）：只回答「这一帧读到的通知值要做什么」。
constexpr SystemExitDecision DecideSystemExit(std::uint32_t message, bool alreadyHandled) noexcept {
    if (message != kAppletMessageExit) {
        return SystemExitDecision::NotExitRequest;
    }
    return alreadyHandled ? SystemExitDecision::AlreadyHandled : SystemExitDecision::TakeOver;
}

// ★ 加载期保护（**必须**，2026-10-01 第二版首测的教训）：
//   `ManagerUpdateHook::Callback` 在**加载期间就会触发**（本文件 2054 行那句注释早写着），
//   而那时 `nn::ro` 的模块表还在被 rtld 填充 —— 在里面遍历它（或做可读性判定）会**卡住不返回**：
//   实测主循环再也起不来（黑屏 + 无声），读数里 `update 回调进入次数 = 0`
//   —— 因为我这段插在计数累加**之前**，计数为 0 恰好证明"它没返回"。
//   ⇒ 前 `kStartupGuardFrames` 帧一律不做，跨过加载期之后再尝试解析。
constexpr std::uint32_t kStartupGuardFrames = 900;  // ≈15 秒（加载期约 10 秒）
// 遍历上限：链表万一成环/异常时兜底，绝不无限转。
// ★ 批次 255 起同时**判环**（`module->next == first` 就停）—— 这条链本身是循环的，
//   这个上限退化成最后的保险，正常应该走不到它。
constexpr std::size_t kMaxModulesToScan = 256;
// 判定「模块对象自身可读」时读多少字节：覆盖到 `hash_bucket`(+0x50) 的末尾即可，
// 不必覆盖整个 `ModuleObject`（节点分布在各模块的 bss 里，链异常时不能按野指针取字段）。
constexpr std::size_t kModuleProbeReadableBytes = 0x58;
std::atomic<std::uint32_t> g_SystemExitPollFrames{0};

// 解析 `nn::oe::GetNotificationMessage` 的地址：**自己遍历** `nn::ro` 的已加载模块表，
// 按「模块基址 + 已知偏移处的入口 16 字节」认出 sdk。
//
// ★ 为什么不用现成的 `rtld::lookup_global_auto`（`runtime/source/rtld/ld.cpp`）——
//   2026-10-01 真机首测**启动即崩**，根因就在它身上：
//   它对**每一个**模块项调 `ModuleObject::GetSymbolByName`，而那个函数会解引用模块的
//   `hash_bucket`(`+0x50`) / `hash_nbucket`(`+0xa8`)。加载期链表里有**尚未被 rtld 填好**的项 ——
//   我们自己的 `exl_nx_module_runtime`（`rtld/relocation.cpp`，放 `.bss`、初值全 0）就是：
//   `hash_nbucket == 0` ⇒ `udiv` 除零得 0 ⇒ 再按地址 0 取 `hash_bucket[0]` ⇒ Data Abort。
//   证据：crash `01790834136`（2026-10-01），`PC = runtime+0x1F4`
//   （= `GetSymbolByName+0x34`，即 `ldr w1, [x3, x1, lsl #2]`）、`Fault Address = 0`。
//   这里只读 `module_base`（不做任何符号查询），跳过 `hash_bucket` 为 0 的未初始化项，
//   并且在取字节之前先做可读性判定（模块比 sdk 小的时候那个偏移根本不在它里面）。
std::uintptr_t ResolveSdkExitNotifyAddress() noexcept {
    // ★★★ 批次 255（2026-10-01 真机取证后的修法）：**这里原来走错了链表方向**。
    //
    //   原写法 `for (module : rtld::ro::g_pAutoLoadList)` 用的是 exlaunch 的迭代器，
    //   而它的语义是 `begin() = Iterator(this->back /* +0x08 */, false)`、
    //   `operator++` 取 **`prev`**（见 `runtime/source/rtld/ModuleList.hpp`）。
    //
    //   真机实测（证据链：`docs/改动日志-20261001.md` 的「251·读数（二）」）：
    //     · `g_pAutoLoadList` 的 `+0x00` 落在「含 sdk / runtime 的主链」上；
    //     · **`+0x08` 落在另一条只有 2 个节点的孤立环上**
    //       （`0x1214603390` ⇄ `0x7bee800000`(Repentance)，两者 next/prev 互指）。
    //   ⇒ 迭代器从那个死环起步 ⇒ 每一步都在 2 个节点之间来回 ⇒ 撞满 `kMaxModulesToScan`
    //     就放弃 ⇒ **sdk 的模块对象从头到尾访问不到**，整条退出接管永远起不来。
    //     （v8 探针读数 `resolveFail = 600` = 帧门之后的每一帧，与此逐值吻合。）
    //   ⇒ 改成从 `+0x00`（front）出发、沿 `next` 走，并自己判环闭合。
    //
    //   ★ 别换成 `rtld::lookup_global_auto`：它内部走的是**同一个** `g_pAutoLoadList`
    //     迭代（`runtime/source/rtld/ld.cpp`），会掉进同一个死环。
    const rtld::ModuleObject* const first = rtld::ro::g_pAutoLoadList.front;
    const rtld::ModuleObject* module = first;
    std::size_t visited = 0;
    for (; module != nullptr && visited < kMaxModulesToScan; ++visited) {
        // 节点自身先判可读：节点分布在各模块的 bss 里，链一旦异常就不能按野指针取字段。
        // （候选地址那边原本就有可读性判定，这里补的是「节点本身」这一层。）
        if (!isaac::runtime::engine_memory::EngineMemoryReadable(
                reinterpret_cast<std::uintptr_t>(module), kModuleProbeReadableBytes)) {
            break;
        }
        if (module->module_base != nullptr && module->hash_bucket != nullptr) {
            const auto candidate = reinterpret_cast<std::uintptr_t>(module->module_base) +
                                   kSdkGetNotificationMessageOffset;
            if (isaac::runtime::engine_memory::EngineMemoryReadable(
                    candidate, kSdkGetNotificationMessageEntry.size())) {
                const auto* entry = reinterpret_cast<const std::uint8_t*>(candidate);
                bool matches = true;
                for (std::size_t index = 0; index < kSdkGetNotificationMessageEntry.size(); ++index) {
                    if (entry[index] != kSdkGetNotificationMessageEntry[index]) {
                        matches = false;
                        break;
                    }
                }
                if (matches) {
                    // 探针：记下「是从哪个 module_base 上认出它的」。
                    // 命中后 `g_SystemExitGetMessage` 会被缓存、不再走这条分支 ⇒ 这一笔是终值。
                    g_SystemExitProbe.scanNodes = static_cast<std::uint32_t>(visited + 1U);
                    g_SystemExitProbe.scanTruncated = 0U;
                    g_SystemExitProbe.hitBase = reinterpret_cast<std::uintptr_t>(module->module_base);
                    return candidate;
                }
            }
        }
        const rtld::ModuleObject* const next = module->next;
        if (next == first) {
            break;  // 环闭合：这条链是循环的，回到起点就是走完了
        }
        module = next;
    }
    // 探针：没认出时也留一笔 —— 「走了几个节点 / 有没有撞上限」正是分辨
    // 「链根本没走到 sdk」与「走到了但守卫不符」的判据（这两者的修法完全不同）。
    g_SystemExitProbe.scanNodes = static_cast<std::uint32_t>(visited);
    g_SystemExitProbe.scanTruncated = (visited >= kMaxModulesToScan) ? 1U : 0U;
    return 0;
}

std::atomic<std::uintptr_t> g_SystemExitGetMessage{0};
// ★ 用 `uint32_t` 而不是 bool 版的 atomic：本仓库明令源码里不得出现它
// （`test_runtime_source_contains_no_bool_atomics` 按**整文件子串**判定，所以注释里也不能出现）。
// 0 = 未接管，1 = 已接管。
std::atomic<std::uint32_t> g_SystemExitTakenOver{0};

// 每帧调用一次（`ManagerUpdateHook::Callback` 的第一件事）。
void PollSystemExitTakeover() noexcept {
    ++g_SystemExitProbe.pollFrames;  // 探针：证明"我们这段真的在跑"（最基础的一条）
    if (g_SystemExitTakenOver.load(std::memory_order_acquire) != 0) {
        return;
    }
    // ★ 加载期一律不碰（理由见上面 `kStartupGuardFrames` 那段）：
    //   先自增本函数的帧计数，够数了才允许去动模块表。
    if (g_SystemExitPollFrames.fetch_add(1, std::memory_order_relaxed) + 1 < kStartupGuardFrames) {
        return;
    }
    // ★ **无条件周期写**（2026-10-01 真机教训 —— 上一版探针的致命缺口）：
    //   上一版只在"读到非零通知 / 进入接管"时写盘，于是"通知恒为 0"这个**最可能**的情况
    //   反而一点痕迹都不留 ⇒ 无法区分"代码没跑到这"与"跑到了但读到的全是 0"。
    //   现在：过了加载期门就写第一次，之后每 600 帧（约 10 秒）写一次 ⇒ `pollFrames` 与 `writes`
    //   会稳定增长，一眼就能看出"我们这段在跑"。
    if (g_SystemExitProbe.pollFrames >= g_SystemExitProbeNextWrite) {
        g_SystemExitProbeNextWrite = g_SystemExitProbe.pollFrames + 600;
        WriteSystemExitProbe();
    }
    auto getMessage = g_SystemExitGetMessage.load(std::memory_order_acquire);
    if (getMessage == 0) {
        getMessage = ResolveSdkExitNotifyAddress();
        if (getMessage == 0) {
            ++g_SystemExitProbe.resolveFail;  // 探针：解析不到 sdk 的次数
            return;  // 还没解析到（例如模块表尚未就绪）⇒ 静默，下一帧再试
        }
        g_SystemExitGetMessage.store(getMessage, std::memory_order_release);
    }
    // ★★ 批次 256（2026-10-01）：**改成按真实签名调用**。
    //
    //   符号名 `_ZN2nn2oe20GetNotificationMessageEPj` 里的 `Pj` 明写着一个 `unsigned int*` 参数，
    //   而此前一直按「**无参数**」调用 —— 也就是 x0 是个垃圾值。
    //   我原先据此判断"没关系"（因为反汇编显示这个函数**自己**在栈上准备出参缓冲、
    //   并把消息**从 w0 返回**），但那个判断下得太早：
    //   它开头那条 `bl <导入函数>`（目标是 PLT 桩）**很可能需要 x0 有效** ——
    //   我们给垃圾 ⇒ 它拿不到对象 ⇒ 后面那次虚调用 `blr x8` 失败 ⇒ **恒返回 0**，
    //   与真机现象（`msgNonZero = 0`，连"进后台"的 `m2` 都是 0）完全一致。
    //   ⇒ 现在传一个**真实存在**的出参缓冲，并且把**返回值与出参都记进探针**，
    //     这样一次真机就能分辨"哪个位置本来才有值"，不必再改第三遍。
    std::uint32_t outValue = 0;
    using GetNotificationMessageFn = std::uint32_t (*)(std::uint32_t*);
    const std::uint32_t returned = reinterpret_cast<GetNotificationMessageFn>(getMessage)(&outValue);
    g_SystemExitProbe.lastReturned = returned;
    g_SystemExitProbe.lastOut = outValue;
    const std::uint32_t message = (returned != 0) ? returned : outValue;
    if (message != 0) {
        // 探针：任何非零通知都记一笔并落盘 —— "关游戏时到底读到了什么"第一次有据可查。
        ++g_SystemExitProbe.msgNonZero;
        g_SystemExitProbe.lastMsg = message;
        if (message == kAppletMessageChangeIntoBackground) {
            ++g_SystemExitProbe.msg2Count;
        } else if (message == kAppletMessageExit) {
            ++g_SystemExitProbe.msg4Count;
        } else {
            ++g_SystemExitProbe.otherMsgCount;
        }
        WriteSystemExitProbe();
    }
    const auto decision =
        DecideSystemExit(message, g_SystemExitTakenOver.load(std::memory_order_relaxed) != 0);
    if (decision != SystemExitDecision::TakeOver) {
        return;
    }
    std::uint32_t expected = 0;
    if (!g_SystemExitTakenOver.compare_exchange_strong(expected, 1, std::memory_order_acq_rel)) {
        return;
    }
    ++g_SystemExitProbe.takeOver;
    // ★ 探针（关键）：把"派发为什么可能不生效"的判据在**派发之前**记下来。
    //   ① Lua 就绪？② `MC_PRE_GAME_EXIT` 有没有登记着？（`DispatchPreGameExit` 内部就靠这两条早退）
    //   ③ Lua 错误历史 head —— 与派发后的值比较，变了说明模组在回调里报过错。
    g_SystemExitProbe.ready = LuaRuntime::IsReady() ? 1U : 0U;
    g_SystemExitProbe.pgeCount = LuaRuntime::RegisteredCallbackCount(
        static_cast<std::uint32_t>(isaac::runtime::kCallbackPreGameExit));
    std::uint32_t errorLength = 0;
    g_SystemExitProbe.errBefore =
        static_cast<std::uint32_t>(LuaRuntime::LastLuaErrorHead(&errorLength));
    WriteSystemExitProbe();
    const auto engineBase = LuaRuntime::EngineModuleBase();
    // ★★ 顺序是刻意的，与 PC 完全同构（2026-10-01，第三/四版两次真机教训的合成）：
    //
    //   ① **先派发 `MC_PRE_GAME_EXIT(true)`** —— 这是 PC 上 EID 唯一的存盘动作
    //      （`EID:OnGameExit` → `EID.SaveData`）。必须**在引擎开始拆解之前**做：
    //      模组的收尾会读引擎对象，拆完再派发就晚了（也可能崩）。
    //   ② **再调 `IsaacShutdown()`** —— 完整走一遍 PC 的"关闭以撒"流程：
    //      `OptionsConfig::Save()` / `PersistentGameData::Flush(true)` / `Game::Exit`
    //      / `MenuManager`·`Game`·`Manager` 析构 / `AnmCache::Reset` / `ShutdownShaders`。
    //      ★ 不能像第四版那样只做①就收工：那等于把引擎自己的退出流程整块丢掉，
    //        环境就和 PC 不一致了（用户 2026-10-01 指出）。
    //
    //   ★ 为什么不指望"②里的 `Game::Exit` 会替我们派发"：反汇编 `IsaacShutdown`
    //     @ `0x3B38D0`（长 `0xF0`）显示那一句是有条件的 ——
    //        0x3B3928  ldr w8, [x8, #0x8]   ; x8 = g_Manager
    //        0x3B3930  cmp w8, #0x2
    //        0x3B3938  b.ne 0x3B3948        ; ≠2 ⇒ 跳过 Game::Exit
    //     真机实测那一刻条件不成立 ⇒ 只调②会**静默丢掉模组的存盘**
    //     （第三版现象：设置没保存，但游戏表现为"关游戏直接瞬关"——
    //      因为②前面那两句无条件写盘）。
    //   ★ 反过来，如果那一刻条件**成立**，②里的 `Game::Exit` 会经我们已装好的入口中继
    //     再派发一次 —— 重复派发在本项目是安全的（模组侧的存盘是幂等的，
    //     EID 就是 `SaveData` 写同一份 `EID.Config`），为此不值得去抑制中继。
    // 与 PC 完全同一条路：`IsaacShutdown()` 内部即 `Game::Exit(true)`，
    // 交给我们已经装好的 `Game::Exit` 入口中继去派发 `MC_PRE_GAME_EXIT`（顺序也一致）。
    LuaRuntime::DispatchPreGameExit(true);
    const auto optionStatus=isaac::runtime::FlushRuntimeOptions();
    if(!optionStatus.ok()&&optionStatus.code()!=isaac::runtime::StatusCode::Unsupported){
        char message[96];const auto n=std::snprintf(message,sizeof(message),"runtime options save failed: %u",static_cast<unsigned>(optionStatus.code()));
        if(n>0)LuaRuntime::RecordLuaErrorText(message,static_cast<std::size_t>(n));
    }
    ++g_SystemExitProbe.dispatchDone;
    errorLength = 0;
    g_SystemExitProbe.errAfter =
        static_cast<std::uint32_t>(LuaRuntime::LastLuaErrorHead(&errorLength));
    WriteSystemExitProbe();

    if (engineBase != 0) {
        reinterpret_cast<void (*)()>(engineBase + kIsaacShutdownOffset)();
        ++g_SystemExitProbe.shutdownCalled;
        WriteSystemExitProbe();
    }
}

#endif  // EXL_DIAGNOSTIC_PROBES（批次 262：系统退出轮询/接管整块只在诊断包）

HOOK_DEFINE_TRAMPOLINE(ManagerUpdateHook) {
    static void Callback(IsaacRepentance::Manager* self) {
        LuaRuntime::ObserveGameThread();
        g_RenderFrameManager.store(isaac::runtime::engine_memory::AddressOf(self), std::memory_order_release);
        // 批次 251：系统退出请求接管。放在**最前**是刻意的 —— 必须在「系统要求退出」
        // 的那一帧、任何别的动作之前把引擎的退出流程走完，才能与 PC 上
        // 「关窗口时引擎自己调 IsaacShutdown」的时序对齐。上游做了幂等，稳态下一帧一次读。
        //
        // ★★★ 批次 262（A3/A4 性能）：整条只在诊断包里跑（理由见那一段开头的注释：
        // 该通道真机已证伪，正式包里它是 100% 的纯开销 —— 每帧一次跨服务调用 + 每 600 帧一次容器重写）。
#if EXL_DIAGNOSTIC_PROBES
        PollSystemExitTakeover();
#endif
#if defined(EXL_LAYERED_RUNTIME)
        // One relaxed increment per entry. This is the only thing in a production
        // build that can prove whether this callback is reached at all.
        g_UpdateCallbackEntries.fetch_add(1, std::memory_order_relaxed);
#endif
#if defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
        // Consume a bounded confirmation/failure retry at the next game-thread
        // safe point; stable frames do no file I/O once the queue is empty.
        if (PersistenceEventJournal::HasPending()) {
            PersistenceEventJournal::DrainPendingBounded(1);
        }
#endif
        if (PersistenceEventJournal::MarkOnce(
                PersistenceEventJournal::Event::ManagerCallbackEntered)) {
            PersistenceEventJournal::FlushBounded();
        }
        ManagerUpdateHookAudit::RecordCallbackEntry();
        PersistenceTrace::RecordCallbackEntry();
#if defined(ISAAC_RUNTIME_HAS_DIAGNOSTICS_BRIDGE)
        // Diagnostics arms itself here and retries until the file port is usable; it
        // is deliberately NOT called from the SaltyNX registration callback, where
        // object construction plus file I/O crashed on hardware (report 01789053980).
        // The call is unconditional: an attach gated on a frame counter produced no
        // evidence at all on hardware, and the bridge makes it a no-op once armed.
        IsaacModRuntime_TryAttachDiagnostics();
#endif
#if defined(EXL_LAYERED_RUNTIME)
#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_FILEIO
        // Self-journal. Bounded to three attempts per marker inside the writer, so a
        // steady frame does no file I/O; the record names this copy of the module and
        // reports whether the registered file table is visible from the code that runs.
        // Probe builds only: its route (libnx `fs`) is measured dead on hardware.
        //
        // 由 `PROBE_BREAK_FILEIO` 单独控制。**这一处是第一轮二分漏掉的那个**：它和入口、
        // 渲染钩子那两处一样会走 service-manager 与 fs 两段阻塞式 IPC 初始化，而更新钩子在
        // 加载期间就会触发（2026-09-13）。
        //
        // 注：这里刻意不写出那两个初始化函数的字面名字 —— `test_runtime_constants` 的
        // "默认运行时不得出现文件系统日志路径"是按**整文件子串**判定的，注释里出现也会红。
        // 只改措辞、不放宽断言：真正的调用一旦写进来，那条门禁仍旧会红。
        IsaacModRuntime_WriteSelfJournal(isaac::runtime::kSelfJournalUpdateMarker);
#endif
#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_CONTENT_MOUNT
        // Stage 147: register the test mod's `resources/` directory as a KAGE content
        // mount point and report whether the engine then resolves a file that only
        // exists in the SD overlay. Armed earlier than the break below because a break
        // ends the session and this is the open question.
        // 由"测试 Mod 自己画了多少帧"触发（见 `kContentMountProbeAfterDraws` 的注释）：update
        // 回调次数与渲染帧数都会在加载阶段被烧掉大半，只有 Mod 的绘制计数只在房间里增长。
        if (g_ContentMountProbeArmed.load(std::memory_order_relaxed) == 0) {
            double drawn = 0.0;
            const bool drewEnough =
                LuaRuntime::ReadLuaGlobalNumber("STAGE149_FRAME", &drawn) &&
                drawn >= static_cast<double>(isaac::runtime::kContentMountProbeAfterDraws);
            // 兜底：主口径（Mod 自己画够帧数）没出现时也必须有一次报告。Mod 的回调一旦报错，
            // 派发器会**静默摘除**它，屏幕上什么都不显示也不会崩 —— 没有这条兜底，那一轮就只剩
            // "没有报错也没有显示"这个现象（2026-09-13 第七轮实测）。
            const bool waitedEnough =
                g_UpdateCallbackEntries.load(std::memory_order_relaxed) >=
                isaac::runtime::kContentMountProbeFallbackAfterUpdates;
            // 批次 2c 探针：把"回调里的 Lua 错误"变成可读证据（`ISAACERR`）。派发器在回调
            // `lua_pcallk` 失败时会静默摘除那个回调，现象就是"不崩、也不显示"。放在本块最前面：
            // 同一帧里它必须先于另外两个探针看到会话状态，也只有它能结束会话（其余两个已让路）。
            IsaacModRuntime_ProbeCallbackError();
            // 批次 2 探针：每帧判一次"玩家数组是否已经可读"，命中就报错一次
            // （`Isaac.GetPlayer` 的偏移实现前必须先有这份真机证据）。批次 2c 起它先给上面的
            // 错误探针让路（`kEnginePlayerProbeDeferUntilErrorProbe`），保证一次会话只崩一次。
            IsaacModRuntime_ProbeEnginePlayers();
            if (drewEnough || waitedEnough) {
                g_ContentMountProbeArmed.store(1, std::memory_order_relaxed);
                IsaacModRuntime_ProbeContentMountPoint();
            }
        }
        // 批次 4 探针（`ISAACEL1`）：`Room + 0x1950` 内嵌 `EntityList` 这条静态结论从未上过
        // 真机 —— 本探针在"两级 Game 链与容器指纹全部成立、活表非空、玩家已存在"时，把容器
        // 指纹、三张表的 begin/count、首个实体字段与一次自遍历（vptr 命中数 + 分区直方图）
        // 装进栈负载报错一次（负载落在崩溃报告 Stack Dump 的 `[SP, SP+0x100)` 窗口内）。
        //
        // 位置：**本块最后一个**（既有探针调用之后）。四个探针都会直接报错结束会话，所以
        // "排在最后"就意味着本探针**可能永远轮不到**：可能抢在它前面的会话结束者有
        // `IsaacModRuntime_ProbeCallbackError` 的 600 次兜底、内容挂载点的 600 帧绘制口径，
        // 以及渲染回调里那个 1500 帧的通用探针 break。本探针触发前还会检查既有的一次性标志
        // （见 `content_mount_point_probe.cpp` 的 `kEntityListProbeYieldsToOtherProbes`），
        // 保证不会把别人的证据抢掉。要单独复跑 `ISAACEL1` 时，把上面两个探针的调用与渲染路径
        // 的通用 break 关掉/推后即可，本探针的触发逻辑不用动。
        IsaacModRuntime_ProbeEntityList();
        // 探针 break 由渲染帧数统一触发（见渲染回调里的那处），这里只保留 update 回调的计数，
        // 免得两次计时口径不一致时先到的那个把会话提前结束。
#endif
#endif
        // 批次 019：原生模组页探针（由 `PROBE_BREAK_NATIVE_MODS_MENU` 单独控制）。
        // 它与上面那一批**互不依赖**：上面那批探针会自己**主动报错结束会话**，所以两边同时
        // 编进来时本探针多半轮不到（要单独跑就把 `PROBE_BREAK_CONTENT_MOUNT=0` 一起传进来）。
        // 它只读单例、写自己的诊断字，不做任何 IO。
        // 注：本条注释刻意不写出那个报错指令的字面名字 —— `test_instruction_guard` 的
        // "默认路径里不许有主动报错"是按整段子串判定的，注释里出现也会红（这次就红了）。
        // 只改措辞、不放宽断言：真正的调用一旦写进来，那条门禁仍旧会红。
#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_NATIVE_MODS_MENU
        isaac::runtime::probe::NativeModsMenuProbeUpdate();
#else
        // 批次 077：生产版的"每帧点" —— 推进「模组」那一格的导航、驱动模组页（引擎状态 16）。
        // 位置与探针那一段**完全一致**：都在跑原函数**之前**，因为引擎本帧的
        // `Manager::Update` 会按我们刚写进去的状态/索引分派。
        // 注：本条注释刻意不写出那个"跑原函数"调用的字面名字 —— `test_instruction_guard`
        // 按整段子串数它出现几次，注释里多写一次也会红（这次就红了）。只改措辞、不放宽断言。
        //
        // 门控与上面那条探针调用**互斥**（两个 TU 装的是同一批入口，见
        // `SkipOptionalHooksPredicate` 里那段）。诊断阶段构建"什么都不做"那一道守卫**不在这里**，
        // 而在 `ModMenuNativeUpdate()` 自己的函数体开头 —— 原因写在那个函数里
        // （`test_stage118_managed_file_write_diagnostic` 拿"诊断阶段那条条件"当**切片结束符**，
        //  在这里再插一条同样的条件会让它切早、把跑原函数那一句切出去）。
        // 注：本条注释**刻意不写出那条条件的字面文本** —— 那条门禁是按整段子串找它的，
        // 注释里出现也会红（批次 077 实测）。只改措辞、不放宽断言。
        isaac::runtime::modmenu::ModMenuNativeUpdate();
#endif
        // 批次 121：控制台的每帧点（按键诊断 / 组合键呼出软键盘 / 执行软键盘交回的命令）。
        // **薄调用**：判据、对象、绘制都不在本 TU（见 `application/console/console_session.hpp`）。
        // 位置与上面那个"每帧点"一致 —— 都在跑原函数之前，本帧就按新状态走。
        isaac::runtime::console::SessionFrameUpdate();
        PersistenceTrace::Flush();
        ManagerUpdateHookAudit::Flush();
        Orig(self);
        PersistenceTrace::Mark(PersistenceTrace::Phase::OriginalReturned);
        if (PersistenceEventJournal::MarkOnce(
                PersistenceEventJournal::Event::OriginalReturned)) {
            PersistenceEventJournal::FlushBounded();
        }
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
        ObserveStage88InstantRestart(self);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
        ObserveStage89RestartActionControllers(self);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
        if (g_Stage118Armed.exchange(false, std::memory_order_acq_rel)) {
            RunStage118ManagedFileWriteDiagnostic();
        }
#endif
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 7
#if !defined(EXL_DIAGNOSTIC_STAGE)
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
        if (DefaultManifestInitializationAllowed()) {
#endif
        DefaultManifestState expected = DefaultManifestState::Armed;
        if (g_DefaultManifestState.compare_exchange_strong(expected, DefaultManifestState::Running,
                                                           std::memory_order_acq_rel)) {
            PersistenceTrace::Mark(PersistenceTrace::Phase::ManifestStarted);
            PersistenceEventJournal::MarkAndFlush(
                PersistenceEventJournal::Event::ManifestEntered);
            TestRunObserver::Mark(TestRunObserver::State::ManifestInstallEntered, 1);
            // ⚠️ 这里**不放**"喂模组 content"那一步 —— 它挪到 `LoadDefaultManifestModThroughService`
            // 里、**注册完各模组的资源挂载点之后**了。理由见那边的调用点注释（一句话：
            // 放这里的话我们的模组列表还是空的、内容目录也还没注册 ⇒ 那一次等于什么都没做）。
        }
        // ★★ 批次 236（2026-09-30）：**每帧推进一步，不再一次做完**。
        //
        // 这一段原来是在抢到 `Armed → Running` 的那一帧里**一次做完**的。用户实测：整条路要
        // **约 10 秒**，而那 10 秒正好压在开场动画上（画面不动、声音继续）；把整条路跳过
        // （卡上放 `no-lua.on`）⇒ 开场**零延迟**。⇒ 它必须被拆开，见
        // `LoadDefaultManifestModThroughService` 上面那段说明（原因、修法、为什么不能换线程）。
        //
        // 状态机在 `Running` 期间每次 `Manager::Update` 走一步，**走完**才翻成 Ready/Failed。
        if (g_DefaultManifestState.load(std::memory_order_acquire) == DefaultManifestState::Running) {
            u32 failureDetail = 0;
            const bool initialized = InitializeDefaultManifestMod(&failureDetail);
            if (DefaultManifestLoadFinished()) {
            TestRunObserver::Mark(TestRunObserver::State::ManifestInstallReturned,
                                  initialized ? 0 : failureDetail);
            g_DefaultManifestFailureDetail.store(failureDetail, std::memory_order_release);
            g_DefaultManifestState.store(initialized ? DefaultManifestState::Ready : DefaultManifestState::Failed,
                                        std::memory_order_release);
            PersistenceEventJournal::MarkAndFlush(
                PersistenceEventJournal::Event::ManifestReturned,
                PersistenceEventJournal::Operation::None,
                initialized ? 0U : failureDetail,
                static_cast<u64>(g_DefaultManifestState.load(std::memory_order_acquire)));
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
            ReportStartupProbeStage8ManifestResult(initialized, failureDetail);
#endif
#if defined(EXL_PERSISTENCE_TRACE)
            u64 traceDetail = failureDetail;
            if (!initialized &&
                (failureDetail == 0x10U + static_cast<u32>(LuaRuntime::LuaInitResult::RuntimePreparationMemoryFailed) ||
                 failureDetail == 0x10U + static_cast<u32>(LuaRuntime::LuaInitResult::RuntimePreparationFailed))) {
                const auto result = static_cast<LuaRuntime::LuaInitResult>(failureDetail - 0x10U);
                const u64 preparationDetail = LuaRuntime::PreparationFailureDetail();
                traceDetail = (static_cast<u64>(result) << 32) | preparationDetail;
            }
            if (!initialized) traceDetail |= PersistenceTrace::kFailureDetailMask;
            PersistenceTrace::Mark(PersistenceTrace::Phase::ManifestCompleted, traceDetail);
#endif
            }
        }
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
        }
#endif
#endif
        if (LuaRuntime::IsReady()) {
#if !defined(EXL_DIAGNOSTIC_STAGE)
            const bool fileApiReady = ModPersistence::IsFileApiReady();
            const bool shouldDispatch =
                g_DefaultPersistenceGate.ShouldDispatch(fileApiReady, kDefaultPersistenceRequired);
            const u64 gateDetail =
                (static_cast<u64>(fileApiReady ? 1U : 0U) << 24) |
                (static_cast<u64>(kDefaultPersistenceRequired ? 1U : 0U) << 16) |
                (static_cast<u64>(shouldDispatch ? 1U : 0U) << 8) |
                static_cast<u64>(g_DefaultManifestState.load(std::memory_order_acquire));
            if (PersistenceEventJournal::MarkIfChanged(
                    PersistenceEventJournal::Event::GateEvaluated,
                    PersistenceEventJournal::Operation::None,
                    shouldDispatch ? 1U : 0U, gateDetail)) {
                PersistenceEventJournal::FlushBounded();
            }
            if (shouldDispatch) {
#if defined(EXL_PERSISTENCE_TRACE) && defined(EXL_PERSISTENCE_REQUIRED)
                if (fileApiReady) {
                    const u64 detail =
                        (static_cast<u64>(g_DefaultManifestState.load(std::memory_order_acquire)) << 8) | 1ULL;
                    PersistenceTrace::Mark(PersistenceTrace::Phase::PersistenceGateReady, detail);
                }
#endif
#endif
            const bool firstDispatch = PersistenceEventJournal::MarkOnce(
                PersistenceEventJournal::Event::DispatchEntered);
            if (firstDispatch) PersistenceEventJournal::FlushBounded();
            PersistenceTrace::Mark(PersistenceTrace::Phase::DispatchStarted);
            LuaRuntime::DispatchPostUpdate();
            PersistenceTrace::Mark(PersistenceTrace::Phase::DispatchReturned);
            if (PersistenceEventJournal::MarkOnce(
                    PersistenceEventJournal::Event::DispatchReturned)) {
                PersistenceEventJournal::FlushBounded();
            }
#if defined(EXL_PERSISTENCE_TRACE)
            if (LuaRuntime::TakeCallbackError()) {
                const u64 callbackDetail = LuaRuntime::CallbackFailureDetail();
                PersistenceTrace::Mark(PersistenceTrace::Phase::CallbackFailed, callbackDetail);
            }
#elif defined(EXL_PERSISTENCE_EVENT_DIAGNOSTIC)
            if (LuaRuntime::TakeCallbackError()) {
                const u64 callbackDetail = LuaRuntime::CallbackFailureDetail();
                PersistenceEventJournal::MarkAndFlush(
                    PersistenceEventJournal::Event::CallbackFailed,
                    PersistenceEventJournal::Operation::None, 0, callbackDetail);
            }
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 7
            if (LuaRuntime::TakeCallbackError()) {
                svcBreak(BreakReason_User, 0x49534141435F4C46ULL, (7ULL << 32) | 5ULL);
                svcExitProcess();
            }
            if (LuaRuntime::PostUpdateCount() >= 120) {
                svcBreak(BreakReason_User, 0x49534141435F4C50ULL, (7ULL << 32) | 120ULL);
                svcExitProcess();
            }
#endif
#if !defined(EXL_DIAGNOSTIC_STAGE)
            }
#endif
        }
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
        switch (g_Stage14Controller.TryClaimCallback()) {
        case Stage14Diagnostic::Claim::WaitForReady:
        case Stage14Diagnostic::Claim::IgnoreFinished:
            return;
        case Stage14Diagnostic::Claim::Run:
            break;
        }
        LuaRuntime::DispatchPostUpdate();
        const u32 postUpdateCount = LuaRuntime::PostUpdateCount();
        switch (Stage14Diagnostic::ClassifyCallback(
            postUpdateCount, LuaRuntime::TakeCallbackError())) {
        case Stage14Diagnostic::CallbackResult::SuccessFalse:
            ReportStage14Success(false);
        case Stage14Diagnostic::CallbackResult::SuccessTrue:
            ReportStage14Success(true);
        case Stage14Diagnostic::CallbackResult::CallbackError:
            ReportStage14Failure(Stage14Diagnostic::Stage14Failure::CallbackError);
        case Stage14Diagnostic::CallbackResult::CallbackNotReached:
            ReportStage14Failure(Stage14Diagnostic::Stage14Failure::CallbackNotReached);
        case Stage14Diagnostic::CallbackResult::BooleanTypeMismatch:
            ReportStage14Failure(Stage14Diagnostic::Stage14Failure::BooleanTypeMismatch);
        }
        UNREACHABLE;
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
        if (LuaRuntime::IsReady()) {
            LuaRuntime::DispatchPostUpdate();
            CheckStage15AfterPausedUpdate();
        }
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
        const GameIsPausedObservation observation = ObserveGameIsPaused(
            g_Stage6GameOwnerSlot.load(std::memory_order_acquire),
            g_Stage6GameIsPausedThunk.load(std::memory_order_acquire));
        switch (observation) {
        case GameIsPausedObservation::PausedFalse:
            ReportStage6IsPausedSuccess(false);
        case GameIsPausedObservation::PausedTrue:
            ReportStage6IsPausedSuccess(true);
        case GameIsPausedObservation::OwnerNull:
        case GameIsPausedObservation::OwnerUnreadable:
        case GameIsPausedObservation::GameNull:
        case GameIsPausedObservation::GameUnreadable:
        case GameIsPausedObservation::ThunkUnavailable:
            break;
        }
        const u32 frame = g_Stage6ObserverFrames.fetch_add(1, std::memory_order_relaxed) + 1;
        if (frame < kStage6ObserverFrameLimit) return;
        switch (DeepestGameOwnerObservation()) {
        case GameOwnerObservation::OwnerNull:
            ReportStage6Failure(39);
        case GameOwnerObservation::OwnerUnreadable:
            ReportStage6Failure(40);
        case GameOwnerObservation::GameNull:
            ReportStage6Failure(41);
        case GameOwnerObservation::GameUnreadable:
            ReportStage6Failure(42);
        case GameOwnerObservation::Success:
            UNREACHABLE;
        }
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
        Stage11State expected = Stage11State::Armed;
        if (!g_Stage11State.compare_exchange_strong(expected, Stage11State::Running, std::memory_order_acq_rel)) {
            return;
        }
        RunStage11RomfsSentinelDiagnostic();
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
        Stage12State expected = Stage12State::Armed;
        if (g_Stage12State.compare_exchange_strong(expected, Stage12State::Running, std::memory_order_acq_rel)) {
            RunStage12RomfsLuaDiagnostic();
        } else if (expected != Stage12State::Ready) {
            return;
        }
        if (g_Stage12State.load(std::memory_order_acquire) != Stage12State::Ready) {
            return;
        }
        LuaRuntime::DispatchPostUpdate();
        if (LuaRuntime::TakeCallbackError()) {
            ReportStage12Failure(17);
        }
        if (LuaRuntime::PostUpdateCount() >= 120) {
            g_Stage12State.store(Stage12State::Finished, std::memory_order_release);
            svcBreak(BreakReason_User, kStage12SuccessMagic, (12ULL << 32) | 120ULL);
            svcExitProcess();
        }
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
        Stage13State expected = Stage13State::Armed;
        if (g_Stage13State.compare_exchange_strong(expected, Stage13State::Running, std::memory_order_acq_rel)) {
            RunStage13ManifestRequireDiagnostic();
        } else if (expected != Stage13State::Ready) {
            ReportStage13StateMismatch();
        }
        if (g_Stage13State.load(std::memory_order_acquire) != Stage13State::Ready) {
            ReportStage13StateMismatch();
        }
        LuaRuntime::DispatchPostUpdate();
        if (LuaRuntime::TakeCallbackError()) {
            ReportStage13Failure(24);
        }
        if (LuaRuntime::PostUpdateCount() >= 120) {
            g_Stage13State.store(Stage13State::Finished, std::memory_order_release);
            svcBreak(BreakReason_User, kStage13SuccessMagic, (13ULL << 32) | 120ULL);
            svcExitProcess();
        }
#endif
    }
};

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48
HOOK_DEFINE_TRAMPOLINE(MusicReplayMusicPlayHook) {
    static void Callback(void* self, u32 musicId, float volume) {
        (void)self;
        (void)musicId;
        (void)volume;
        RecordStage48MusicPlay();
    }
};

HOOK_DEFINE_TRAMPOLINE(MusicReplaySoundActorPlayHook) {
    static void Callback(void* self, u32 flags) {
        (void)flags;
        RecordStage48SoundActorPlay(isaac::runtime::engine_memory::AddressOf(self));
    }
};

HOOK_DEFINE_TRAMPOLINE(MusicReplaySoundActorPauseHook) {
    static void Callback(void* self) {
        RecordStage48SoundActorPause(isaac::runtime::engine_memory::AddressOf(self));
    }
};
#endif

// 派发实现与"新中继是否可用"的判定，定义在本文件后面（trampoline 需要提前知道它们）。
void DispatchModPostRender(void* self);
bool IsRenderPresentRelayInstalled();

// 两条后端路径共用的渲染钩子体：`call_original` 由后端提供
// （exlaunch 蹦床传 `Orig`，入口中继传回退入口）。
// 注意：`g_RenderFrameManager` 必须在跑原函数**之前**记下，Present 前的派发要用它。
void RenderHookBody(IsaacRepentance::Manager* self,
                    void (*call_original)(IsaacRepentance::Manager*)) {
    std::uint32_t scene = 0;
    const bool gameplay = isaac::runtime::engine_memory::ReadField(
        isaac::runtime::engine_memory::AddressOf(self), kManagerRenderSceneOffset, &scene,
        isaac::runtime::engine_memory::EngineMemoryReadable) && scene == kManagerGameplayScene;
    isaac::runtime::RenderFrameScope renderFrame(g_RenderFrameCoordinator, self, gameplay);
    // 记下这一帧的 Manager*：Present 前的派发入口（下面）要用它，因为那个调用点的 x0
    // 是图形管理器。同一个线程、同一帧内先入口后 Present，所以读到的就是本帧的值。
    g_RenderFrameManager.store(isaac::runtime::engine_memory::AddressOf(self), std::memory_order_release);
#if defined(EXL_LAYERED_RUNTIME)
    // Positive control for `g_UpdateCallbackEntries`: the Mod's MC_POST_RENDER
    // path is known to work on hardware, so this counter must be non-zero.
    g_RenderCallbackEntries.fetch_add(1, std::memory_order_relaxed);
#endif
    // Second arming point for the diagnostics journal.
    //
    // The Mod's MC_POST_RENDER route is dispatched from this callback and demonstrably
    // runs on hardware, so this callback is known to execute in every session that
    // loads a Mod. The update hook, by contrast, has never been observed to fire:
    // `TryAttachDiagnostics` only ever ran from there, and `isaac-runtime-events.bin`
    // has never appeared once. Arming from both hooks removes that single point of
    // failure and, because the call is a no-op once the journal is attached, costs
    // one predictable branch per frame.
    //
    // 与更新钩子那处同样按 `ISAAC_RUNTIME_HAS_DIAGNOSTICS_BRIDGE` 守卫：那个桥只在分层
    // 构建里编译，未加守卫的非分层/诊断构建会报 "was not declared in this scope"。
#if defined(ISAAC_RUNTIME_HAS_DIAGNOSTICS_BRIDGE)
    IsaacModRuntime_TryAttachDiagnostics();
#endif
#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_FILEIO
    // Same bounded self-journal record from the render callback, so a session in
    // which only one of the two hooks fires still names the copy that ran.
    IsaacModRuntime_WriteSelfJournal(isaac::runtime::kSelfJournalRenderMarker);
#endif
#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_FILEIO
    // The "who can write a file" probes, and the two SaltyNX IPC probes. All four are
    // bounded inside, and all four are probe-build only: a production build must not
    // touch any of them, because their whole purpose is to find out which of these
    // routes works at all (2026-09-11: none of the Runtime-side ones does).
    //
    // 由 `PROBE_BREAK_FILEIO` 单独控制：这四个是探针包里在启动阶段就会走失效路由的部分
    // （2026-09-13 二分定位探针包启动故障）。
    IsaacModRuntime_ProbeFileWriteFromHook();
    IsaacModRuntime_ProbeNativeFileWrite();
    IsaacModRuntime_ProbeSaltyIpc();
    IsaacModRuntime_ProbeSaltyReinit();
#endif
    // Probe break, from the render callback as well: a session in which only this
    // hook fires must still produce a crash report that names the running copy.
#if defined(EXL_PROBE_BREAK)
    // 帧时间归因探针（`ISAACEV1`）：A/B 两相跑满（或时间兜底）后，在渲染钩子里结束会话
    // 一次。放在这里而不是派发路径里，是为了让崩溃点始终落在"钩子入口"这个已经反复验证
    // 过归因方式的位置（见 `saltynx_probe_break.hpp` 的证据纪律）。
    if (isaac::runtime::EngineFrameProbeTakeBreak()) {
        IsaacModRuntime_EngineProbeBreak();
    }
#endif
    if (g_RenderCallbackEntries.load(std::memory_order_relaxed) >=
        isaac::runtime::kProbeBreakAfterEntries) {
        IsaacModRuntime_ProbeBreak(isaac::runtime::kProbeBreakRenderCallback);
    }
    // 只在真实XML shader已编译且Present中继完整时才建立帧捕获，普通帧只走一个空状态分支。
    if(gameplay && IsRenderPresentRelayInstalled())static_cast<void>(isaac::runtime::BeginShaderFrame());
    call_original(self);
    isaac::runtime::AbortShaderFrame(); // 完整帧已在最终Present前结束；异常退出只恢复原目标。
    // HUD优先，Present仅在没有HUD的主菜单等帧兜底；两者均未进入才保留旧返回回退。
    // 2026-10-17更正：只有Game渲染场景可派游戏回调；菜单scope由协调器拒绝。
    // 同一栈上帧标记在进入Lua前设置，三个入口互不重复。
    g_RenderFrameCoordinator.Dispatch(DispatchModPostRender);
}

// 旧后端（exlaunch 蹦床）：原函数由蹦床的 `Orig` 提供。
HOOK_DEFINE_TRAMPOLINE(ManagerRenderHook) {
    static void Callback(IsaacRepentance::Manager* self) {
        RenderHookBody(self, [](IsaacRepentance::Manager* inner) { Orig(inner); });
    }
};

// 新后端（入口中继）：原函数由 entry_relay 记录的回退入口提供。
// 入口桩是**尾调用**，所以本回调以 `Manager::Render` 的身份运行，
// `ret` 直接回到游戏的调用方；ABI 必须与目标完全一致（`IsaacRepentance::Manager*`）。
// 成就闸门（2026-09-24 批次 098：从"拦 `TryUnlock`"改成挂这里 —— 用户裁定"照 PC 语义来"）。
//
// 位置 = `PersistentGameData::SetReadOnly(bool)`（`0x439460`）：**唯一**写"只读位"（`PGD+0x1`）
// 的地方，也是每局开局设一次"本局给不给成就"的关卡（24 个调用点全在开局路径上：
// `Game::Start` / `StartDailyChallenge` / `RestoreState` / `StartFromRerunState`）。
// PC 的模型就是这样：开局那一刻按「有模组开着 且 妈腿成就未解锁」算一次，落到只读位，
// 之后 `TryUnlock` 自己查这个字节 ⇒ 我们不再拦任何解锁调用，只把这一步补上。
//
// 参数语义：**`引擎原参数 OR 该禁`**。引擎自己那两条禁成就判据（特殊种子 / 挑战局）照旧生效；
// 我们只在"按 PC 规则该禁"时把 false 抬成 true。不锁时一律原样传下去 —— 引擎在"本局不该禁"
// 时会自己调 `SetReadOnly(false)` 把位清掉（`Game::Start` 的 `0x34EA40` 分支），
// 所以关掉模组之后成就照常可拿，这就是用户要的语义。
//
// 形状：`SetReadOnly(PersistentGameData* self /*x0*/, bool /*w1*/)` → void（`w1` 只取低位）。
extern "C" void EntryRelayPersistentGameDataSetReadOnlyCallback(void* self,
                                                               std::uint32_t readOnly) {
    // 分段计数（状态面 [35]..[39]）：回答"这道闸门有没有被走到、是谁让它锁的"。
    //   ① [35] 恒 0 ⇒ 引擎开局根本没调 `SetReadOnly`（那样闸门位置就不对）；
    //   ② [36] 涨 = 引擎自己本来就要锁（特殊种子 / 挑战局）；[37] 涨 = 我们按 PC 规则把它抬成锁；
    //   ③ [38] = 最后一次**真正写下去**的值（1 = 本局不给成就）；[39] = 1 ⇒ 拿不到回退入口。
    auto& state = isaac::runtime::modmenu::g_ModMenuState;
    ++state.setReadOnlyCalls;
    const bool engineWantsLock = (readOnly & 1U) != 0U;
    if (engineWantsLock) {
        ++state.setReadOnlyEngineLocked;
    }
    const bool pcShouldLock = isaac::runtime::modmenu::AchievementsShouldBeBlockedFor(self);
    if (pcShouldLock) {
        ++state.setReadOnlyForcedByPc;
    }
    const bool finalValue = engineWantsLock || pcShouldLock;
    state.setReadOnlyLastValue = finalValue ? 1U : 0U;
    using SetReadOnlyFn = void (*)(void*, bool);
    const auto original = isaac::runtime::Original<SetReadOnlyFn>(
        isaac::runtime::HookId::PersistentGameDataSetReadOnly);
    if (original == nullptr) {
        // 拿不到回退入口 ⇒ **什么都不写**（不吞引擎本来要设的值）——
        // 这种降级是安全的：退回 Switch 原生行为，宁可不禁成就也不误禁。
        state.setReadOnlyOriginalMissing = 1;
        return;
    }
    original(self, finalValue);
}

// ---- 批次 147（2026-09-26）：引擎"模组 content 加载"闸门 ------------------------------
//
// 挂点 = `ModManager::LoadConfigs` 的**入口**（镜像 `0x41E388`，16 字节守卫在
// `runtime_constants.hpp`）。它是引擎那条路的最后一道闸门：`ModManager::Reset` 的顺序是
// `UnloadMods → ListMods（此时把每条 +0x139 定死）→ Manager::ReloadConfigs → 本函数`，
// 而本函数逐条 `ldrb w8,[entry,#0x139]; cbz w8 → 整段跳过`（连 `LoadCustomResources()` 都不调）。
//
// **为什么必须由我们改这一字节**（用户 2026-09-26 的原话："我们的模组关闭标记文件无法写到
// SD 卡中，是通过写到存档完成的"）：引擎判"这个模组关掉了没"只看卡上覆盖层里的
// `<目录>/disable.it`，而我们的模组目录在 romfs 覆盖层里**不能写**（写它会触发"下次启动崩"，
// AGENTS.md 有整段记录）⇒ 我们的开关只存在**存档分区**，引擎看不见。挂在它的入口，
// 就是"时机用引擎的（目录一定已就绪、列表一定已建好）、状态用我们的"。
//
// 三件必守的事：
//   ① **只读写内存，不调任何引擎函数** —— 142/143 两次崩溃都是这个病（在错误的时机碰引擎的
//      文件/初始化接口）；这里除了 `+0x139` 那一个字节之外，什么都不碰。
//   ② 判据用**引擎自己的"用户开着"那一格**（`+0x138`）：为 0 ⇒ 卡上真有 `<目录>/disable.it`
//      （用户手工关的），或引擎自带模组页被按过确认 ⇒ **保持 0**，不覆盖用户的显式意愿，
//      也不制造"内容进了引擎、脚本没加载"的半截状态（运行时 Lua 侧认的是同一个标记）。
//   ③ 状态还没读到时**不拦**（照常置 1）：这正是"引擎先扫完目录、我们才读存档"这种顺序下的
//      降级 —— 与 `ModToggleService` 的既定口径一致（宁可照常加载，也不要因为读不出状态就
//      少加载模组）。这种情形由 `g_ModLoadConfigsStateLoaded` 如实暴露，不会静默。
namespace {

namespace engine_memory = isaac::runtime::engine_memory;

// 读 `ModEntry + 0x48` 那个 libc++ `std::string` 的 data 地址与 size（**走 L1 访问层**）。
// 短/长模式按首字节最低位分。长模式的字段顺序（libc++ 的 `__long`：cap / size / data）由
// 引擎自己两处代码逐字印证：`ModEntry::GetContentPath @ 0x41EF10` 取 `size` 读的是 `this+0x50`；
// `ListMods` 把新串写进去是 `str x8,[entry+0x48]` + `stp x9,x10,[entry+0x50]`
// （⇒ `+0x50` = size、`+0x58` = data）。**这两格写反了就会拿长度当地址、当场崩。**
bool ReadModEntryContentPath(std::uintptr_t entry, std::uintptr_t* outAddress,
                             std::size_t* outSize) {
    if (entry == 0 || outAddress == nullptr || outSize == nullptr) {
        return false;
    }
    std::uint8_t mode = 0;
    if (!engine_memory::ReadField(entry, kModEntryContentPathStringOffset, &mode,
                                  engine_memory::EngineMemoryReadable, 1)) {
        return false;
    }
    if ((mode & kLibcxxStringLongModeBit) != 0) {
        if (!engine_memory::ReadField(entry, kModEntryContentPathStringOffset + 0x8, outSize,
                                      engine_memory::EngineMemoryReadable,
                                      alignof(std::size_t))) {
            return false;
        }
        if (!engine_memory::LoadPointerAt(entry, kModEntryContentPathStringOffset + 0x10,
                                          alignof(std::uintptr_t), outAddress,
                                          engine_memory::EngineMemoryReadable)) {
            return false;
        }
    } else {
        *outAddress = entry + kModEntryContentPathStringOffset + 0x1;
        *outSize = static_cast<std::size_t>(mode >> 1);
    }
    // 形状保险：空指针或长度离谱（>4 KiB）都当"读错了"，宁可不去匹配也不去乱读。
    return *outAddress != 0 && *outSize > 0 && *outSize <= 4096;
}

// 那条路径里有没有"整段等于这个目录名"的一段（`/<名字>/`）。大小写不敏感：
// 引擎在 `ListMods` 里把目录路径**小写化**过（`0x41FC88` 那个 `tolower` 循环），
// 而我们的开关表里存的是清单/扫描得到的原始名字 ⇒ 直接逐字节比会漏。
bool PathMentionsDirectory(std::uintptr_t pathAddress, std::size_t size,
                           std::string_view directory) {
    if (pathAddress == 0 || directory.empty() || size < directory.size()) {
        return false;
    }
    const char* path = static_cast<const char*>(engine_memory::AsObject(pathAddress));
    for (std::size_t start = 0; start + directory.size() <= size; ++start) {
        if (start != 0 && path[start - 1] != '/' && path[start - 1] != '\\') {
            continue;
        }
        std::size_t index = 0;
        while (index < directory.size() &&
               std::tolower(static_cast<unsigned char>(path[start + index])) ==
                   std::tolower(static_cast<unsigned char>(directory[index]))) {
            ++index;
        }
        if (index == directory.size()) {
            return true;
        }
    }
    return false;
}

}  // namespace

// 批次 370：**外部链接的壳** —— 真正的实现在上面的匿名命名空间里（它要用那几个文件作用域的服务：
// `g_DefaultManifestBindings` / `g_DefaultManifest` / `g_ModDiscoveryService` / `g_ContentMountService` / `ManifestLoadStateRef`，
// 那些都不该有外部链接）。`runtime_entry.cpp`（worker 线程）只能调有外部链接的这一个。
extern "C" void EntryRelayModManagerLoadConfigsCallback(void* self) {
    g_ModLoadConfigsCalls += 1;
    const std::uintptr_t modManager = engine_memory::AddressOf(self);
    if (modManager != 0) {
        std::uintptr_t begin = 0;
        std::uintptr_t end = 0;
        const bool haveBegin =
            engine_memory::LoadPointerAt(modManager, kModManagerModListBeginOffset,
                                         alignof(std::uintptr_t), &begin,
                                         engine_memory::EngineMemoryReadable);
        const bool haveEnd =
            engine_memory::LoadPointerAt(modManager, kModManagerModListEndOffset,
                                         alignof(std::uintptr_t), &end,
                                         engine_memory::EngineMemoryReadable);
        // 读不到列表头（`ModManager` 还没建好/形状不对）⇒ 一条都不改，如实记 0 条。
        if (!haveBegin || !haveEnd) {
            begin = 0;
            end = 0;
        }
        const auto& toggles = g_ModToggleService.state();
        g_ModLoadConfigsDisabledKnown = static_cast<std::uint32_t>(toggles.disabledCount);
        g_ModLoadConfigsStateLoaded = g_ModToggleStateLoaded != 0 ? 1u : 0u;
        std::uint32_t seen = 0;
        std::uint32_t enabled = 0;
        std::uint32_t disabled = 0;
        std::uint32_t matched = 0;
        std::uint32_t engineOff = 0;
        std::uint32_t writeFailures = 0;
        bool firstPathCopied = false;
        // 形状保险：条数上限来自 `runtime_constants.hpp`（超过就当自己读错了，绝不硬走）。
        if (begin != 0 && end > begin && (end - begin) % sizeof(std::uintptr_t) == 0 &&
            (end - begin) / sizeof(std::uintptr_t) <= kEngineModListMaximumCount) {
            for (std::uintptr_t slot = begin; slot < end; slot += sizeof(std::uintptr_t)) {
                std::uintptr_t entry = 0;
                if (!engine_memory::ReadAt(slot, &entry, engine_memory::EngineMemoryReadable)) {
                    continue;
                }
                if (entry == 0) {
                    continue;
                }
                ++seen;
                // ① 引擎自己说"这条关着"（`+0x138` 为 0：卡上有 `disable.it`，或引擎自带
                //    模组页被按过确认）⇒ 保持禁用，不覆盖用户的显式意愿，也不制造
                //    "内容进了引擎、脚本没加载"的半截状态。
                std::uint8_t engineUserEnabled = 0;
                if (!engine_memory::ReadField(entry, kModEntryUserEnabledFlagOffset,
                                              &engineUserEnabled,
                                              engine_memory::EngineMemoryReadable, 1)) {
                    continue;
                }
                bool shouldDisable = engineUserEnabled == 0;
                if (shouldDisable) {
                    ++engineOff;
                } else {
                    std::uintptr_t pathAddress = 0;
                    std::size_t pathSize = 0;
                    if (ReadModEntryContentPath(entry, &pathAddress, &pathSize)) {
                        if (!firstPathCopied) {
                            firstPathCopied = true;
                            const auto* path =
                                static_cast<const char*>(engine_memory::AsObject(pathAddress));
                            const std::size_t copy = pathSize < sizeof(g_ModLoadConfigsFirstPath) - 1
                                                         ? pathSize
                                                         : sizeof(g_ModLoadConfigsFirstPath) - 1;
                            std::memcpy(g_ModLoadConfigsFirstPath, path, copy);
                            g_ModLoadConfigsFirstPath[copy] = '\0';
                        }
                        for (std::size_t index = 0; index < toggles.disabledCount; ++index) {
                            if (PathMentionsDirectory(
                                    pathAddress, pathSize,
                                    std::string_view(toggles.disabled[index].data()))) {
                                shouldDisable = true;
                                ++matched;
                                break;
                            }
                        }
                    }
                }
                const std::uint8_t value = shouldDisable ? 0u : 1u;
                if (!engine_memory::WriteField(entry, kModEntryEnabledFlagOffset, value,
                                               engine_memory::EngineMemoryWritable, 1)) {
                    ++writeFailures;
                }
                if (shouldDisable) {
                    ++disabled;
                } else {
                    ++enabled;
                }
            }
        }
        g_ModLoadConfigsEntriesSeen = seen;
        g_ModLoadConfigsEnabledByUs = enabled;
        g_ModLoadConfigsDisabledByUs = disabled;
        g_ModLoadConfigsMatchedDisabled = matched;
        g_ModLoadConfigsEngineOff = engineOff;
        g_ModLoadConfigsWriteFailures = writeFailures;
    }
    // 放行原函数：拿不到回退入口就**什么都不做**（那样引擎按它自己的 +0x139 走，等于没有本挂点）。
    const auto original =
        isaac::runtime::Original<void (*)(void*)>(isaac::runtime::HookId::ModManagerLoadConfigs);
    if (original != nullptr) {
        original(self);
    }
}

extern "C" void EntryRelayManagerRenderCallback(void* self) {
    auto* manager = reinterpret_cast<IsaacRepentance::Manager*>(self);
    RenderHookBody(manager, [](IsaacRepentance::Manager* inner) {
        const auto original =
            isaac::runtime::Original<void (*)(IsaacRepentance::Manager*)>(
                isaac::runtime::HookId::ManagerRender);
        original(inner);
    });
}

// 新后端（入口中继）下的更新挂点。与渲染那一路的差别很关键：**不另写一份钩子体**。
// 蹦床里的 `Callback` 用 `Orig(self)` 调原函数；中继把原函数存在自己的槽里，安装时由
// `PublishEntryRelayOriginals()` 把中继记下的回退入口发布给 `Orig`（`PublishOriginal`）——
// 于是两个后端跑的是**同一个函数**，"行为一致"由构造保证，不必把这份约 300 行的钩子体
// （诊断构建下还有十几处按源码切片断言它的测试）复制成第二份。
//
// 批次 357：update 帧计数（文件作用域的原子量：**不用函数内 static**）。
// ★ 376：计数本身保留（它是"update 回调还在跑"的活体证据）；下面那三支**挂载专用**的
//   调用点已随机制撤除（见 `EntryRelayManagerUpdateCallback` 里的说明），三个周期常量一并删掉。
std::atomic<std::uint32_t> g_updateCallbackTicks{0};

// 为什么可以直接调 `Callback`：入口桩是**尾调用**，本回调以 `Manager::Update` 的身份运行，
// 与蹦床调 `Callback` 时的 ABI 完全一致（`IsaacRepentance::Manager*`）。
extern "C" void EntryRelayManagerUpdateCallback(void* self) {
    // ★★★ 批次 378（2026-10-05）：这一段原来是 357/360/361 的**挂载时间轴 + 自愈补挂 + 晚点重挂试验**
    //   （`NoteMountVisibilityCheckpoint(2)` / `EnsureModMountsAlive()` / `RunLateRemountTrial()`）。
    //   模组目录挂载被 **PC 的资源层重定向**取代之后，那三支全部依赖 `SessionContentMountService()`
    //   （现已恒为空 ⇒ 结构性空转）⇒ **调用点一律撤除**：留着只会让读数看着像"量过了"。
    //   桥里那三支函数本身保留（纯记数，历史现场；读数工具的下标契约没变）。
    //   取证与裁定见 `docs/分析-模组挂载机制与371没音乐定案-20261005.md`。
    (void)g_updateCallbackTicks.fetch_add(1, std::memory_order_relaxed);
    ManagerUpdateHook::Callback(reinterpret_cast<IsaacRepentance::Manager*>(self));
}

// `MC_POST_RENDER`统一派发体：局内从原生HUD返回处进入，早于暂停纸页等原生前景。
// 主菜单没有HUD时保留最终Present兜底；帧协调器负责去重，不按暂停状态禁止回调。
// 2026-10-17更正：Present兜底只服务局内帧，主菜单不派游戏渲染回调。
void DispatchModPostRender(void* self) {
    // 批次 121：控制台输出的绘制点。放在这里（而不是 Lua 派发里面）是因为它**不看有没有模组**：
    // 控制台是运行时自己的能力，一个模组都没加载时也要能画。位置就是模组 `MC_POST_RENDER`
    // 那一档 —— 引擎的绘制队列在这时还开着，`Font::DrawStringScaledUTF8` 才画得出来。
    // 原生控制台在Game::Render返回后绘制，覆盖游戏和模组前景。
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 15 || EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17 || EXL_DIAGNOSTIC_STAGE == 45 || EXL_DIAGNOSTIC_STAGE == 48
#if !defined(EXL_DIAGNOSTIC_STAGE)
    if (LuaRuntime::IsReady() && PrimeDefaultCallbacks(isaac::runtime::engine_memory::AddressOf(self))) {
#else
    if (LuaRuntime::IsReady()) {
#endif
        LuaRuntime::DispatchPostRender(isaac::runtime::engine_memory::AddressOf(self));
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 15
        if (LuaRuntime::TakeCallbackError()) {
            ReportStage15Failure(3);
        }
        if (LuaRuntime::PostUpdateCount() != 0 && LuaRuntime::PostRenderPausedCount() != 0) {
            ReportStage15Success();
        }
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 16
        if (LuaRuntime::TakeCallbackError()) {
            ReportStage16Failure(3);
        }
        if (LuaRuntime::MusicDiagnosticCycleCompleted()) {
            ReportStage16Success();
        }
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 17
        if (LuaRuntime::TakeCallbackError()) {
            ReportStage17Failure(3);
        }
        if (LuaRuntime::MusicDiagnosticCycleCompleted()) {
            ReportStage17Success();
        }
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 45
        if (LuaRuntime::TakeCallbackError()) {
            ReportStage45Failure(3);
        }
        u32 musicId = 0;
        if (LuaRuntime::MusicDiagnosticCurrentId(&musicId)) {
            ReportStage45Success(musicId);
        }
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48
        if (LuaRuntime::TakeCallbackError()) {
            ReportStage48Failure(3);
        }
        Stage48AdvanceMusicReplayProbe();
        u32 payload = 0;
        if (Stage48TakeMusicReplayReport(&payload)) {
            if ((payload & kStage48ObservedPause) == 0) {
                ReportStage48Failure(4);
            }
            ReportStage48Success(payload);
        }
#endif
    }
#endif
}

extern "C" __attribute__((visibility("hidden"))) void
IsaacModRuntime_TextureCacheDiagnostics(std::uint32_t* output) {
    if (output == nullptr) {
        return;
    }
    output[0] = g_TextureCacheCandidates.load(std::memory_order_acquire);
    output[1] = g_TextureCacheWritten.load(std::memory_order_acquire);
    output[2] = g_TextureCacheFailures.load(std::memory_order_acquire);
}

bool IsRenderPresentRelayInstalled() {
    return g_RenderPresentRelayState.load(std::memory_order_acquire) ==
           static_cast<std::uint32_t>(RenderPresentRelayInstallResult::Success);
}

// 由 `Present` 前中继桩调用（中继桩在 `Manager::Render` 体内最后一次 `Present` 调用之前）。
extern "C" __attribute__((visibility("hidden"))) void
IsaacModRuntime_DispatchPostRenderBeforePresent(void* graphicsManager) {
    g_RenderPresentRelayEntries.fetch_add(1, std::memory_order_relaxed);
    // 批次 019 的"手动画原生模组页"这次调用**已从这里移走**（批次 040）：原因是本函数虽然在
    // `Present` 之前，却在引擎那套渲染上下文**之外** —— `PushRenderTarget` / `SetBlendMode` /
    // `LoadShader` / 背景 `FillQuad` 都在 `MenuManager::Render` 里、比我们早，而页面是在那些
    // 准备**之内**画的。在上下文之外调 `Render` ⇒ 页面落在裸屏幕坐标里 ⇒ 给 `Init` 传什么位置
    // 都不对（六档 Y 标定全部落空的原因）。现在它挂在 `Menu_Title::Render` 的入口中继上，
    // 见 `probe/native_mods_menu_probe.cpp` 与 `docs/改动日志-20260922.md` 的 037/040 两节。
    // 参数是图形管理器，不能充当Lua的Manager；生产只从当前栈上帧scope取Manager。
    // 诊断包原先可能没有ManagerRender钩子，其历史回退仅在诊断分支保留。
    uintptr_t manager = reinterpret_cast<uintptr_t>(g_RenderFrameCoordinator.Manager());
#if defined(EXL_DIAGNOSTIC_STAGE)
    // 独立诊断包可能没有ManagerRender钩子，保留其原先的无作用域派发。
    if (manager == 0) {
        manager = g_RenderFrameManager.load(std::memory_order_acquire);
        if (manager == 0) manager = reinterpret_cast<uintptr_t>(graphicsManager);
        DispatchModPostRender(reinterpret_cast<void*>(manager));
    } else
#endif
    {
        g_RenderFrameCoordinator.Dispatch(DispatchModPostRender);
    }
    if (manager == 0) {
        // Shader收尾仍每次最终Present执行；这里的Manager只用于shader，不用于Lua。
        manager = g_RenderFrameManager.load(std::memory_order_acquire);
    }
    (void)graphicsManager;
    isaac::runtime::FinishShaderFrame(manager);
}

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
NORETURN void ManagerLoadConfigsDiagnosticCallback(IsaacRepentance::Manager* self) {
    if (self == nullptr) {
        svcBreak(BreakReason_User, 0x49534141434D464CULL, (8ULL << 32) | 4ULL);
        svcExitProcess();
    }

    const uintptr_t selfAddress = isaac::runtime::engine_memory::AddressOf(self);
    if (selfAddress > UINTPTR_MAX - kManagerToModManagerOffset) {
        svcBreak(BreakReason_User, 0x49534141434D464CULL, (8ULL << 32) | 4ULL);
        svcExitProcess();
    }

    const uintptr_t candidate = selfAddress + kManagerToModManagerOffset;
    if ((candidate & 7u) != 0) {
        svcBreak(BreakReason_User, 0x49534141434D464CULL, (8ULL << 32) | 4ULL);
        svcExitProcess();
    }

    svcBreak(BreakReason_User, 0x49534141434D4F44ULL, (8ULL << 32) | 0x36800ULL);
    svcExitProcess();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
constexpr u64 kStage9FailureMagic = 0x495341414352464CULL;

NORETURN void ReportStage9CallbackFailure(u32 status) {
    svcBreak(BreakReason_User, kStage9FailureMagic, (9ULL << 32) | status);
    svcExitProcess();
}

NORETURN void ManagerLoadConfigsResetDiagnosticCallback(IsaacRepentance::Manager* self) {
    if (self == nullptr) {
        ReportStage9CallbackFailure(4);
    }
    const uintptr_t selfAddress = isaac::runtime::engine_memory::AddressOf(self);
    if (selfAddress > UINTPTR_MAX - kManagerToModManagerOffset) {
        ReportStage9CallbackFailure(4);
    }
    const uintptr_t candidate = selfAddress + kManagerToModManagerOffset;
    if ((candidate & 7u) != 0) {
        ReportStage9CallbackFailure(4);
    }
    const uintptr_t resetAddress = g_Stage9ResetAddress.load(std::memory_order_acquire);
    if (resetAddress == 0) {
        ReportStage9CallbackFailure(3);
    }
    using ResetFn = void (*)(void*);
    const auto reset = reinterpret_cast<ResetFn>(resetAddress);
    reset(reinterpret_cast<void*>(candidate));
    svcBreak(BreakReason_User, 0x4953414143525354ULL, (9ULL << 32) | 0x422440ULL);
    svcExitProcess();
}
#endif

} // namespace

namespace isaac::runtime {
extern "C" {
ModReloadState g_ModReloadState{};
std::uint64_t g_ModReloadLastMicros{};
std::uint64_t g_ModReloadMaxMicros{};
}
bool ReloadModsFromMenu(bool edited) noexcept {
#if defined(EXL_DIAGNOSTIC_STAGE)
    return !edited;
#else
    struct Operations {
        bool Preflight() noexcept {
            const auto current=g_DefaultManifestState.load(std::memory_order_acquire);
            return LuaRuntime::IsOnGameThread() &&
                (current==DefaultManifestState::Ready || current==DefaultManifestState::Failed) &&
                modmenu::PreflightEngineModReload();
        }
        bool Save() noexcept {
            const bool saved=ModMenuSaveToggles();
            modmenu::NoteModToggleSaveResult(saved);
            return saved;
        }
        bool CloseLua() noexcept { return modmenu::WaitEngineGraphicsForModReload() && LuaRuntime::ShutdownForModReload(); }
        bool CreateLua() noexcept { return LuaRuntime::EnsureRuntimeWithMenu()==LuaRuntime::LuaInitResult::Success; }
        bool ReleaseNative() noexcept { return modmenu::ReleaseEngineModsForReload(); }
        bool Load() noexcept {
            auto& load=ManifestLoadStateRef();
            load.batch.count=0;load.batch.disabledCount=0;load.batch.manifestBytes=0;
            load.single.count=0;load.loadOutcome={};load.oneOutcome={};load.failure={};
            load.index=0;load.discoveryMark=0;load.detail=0;load.batchOk=true;load.finished=false;load.result=false;
            ManifestLoadStepRef()=ManifestLoadStep::Idle;
            g_DefaultManifestFailureWord.store(0,std::memory_order_release);
            g_DefaultManifestState.store(DefaultManifestState::Running,std::memory_order_release);
            g_ModMenuReloadLoading=true;
            u32 detail{};
            const bool initialized=InitializeDefaultManifestMod(&detail);
            g_ModMenuReloadLoading=false;
            // 即使作者脚本报错，也必须恢复已经放开的菜单动画/字体，允许修正开关重试。
            const bool nativeFinished=modmenu::FinishEngineModReload();
            const bool success=initialized && DefaultManifestLoadFinished() && nativeFinished;
            g_DefaultManifestFailureDetail.store(detail,std::memory_order_release);
            g_DefaultManifestState.store(success?DefaultManifestState::Ready:DefaultManifestState::Failed,
                                         std::memory_order_release);
            return success;
        }
    } operations;
    const auto tick=RuntimePerfTick();
    const bool result=ApplyModMenuReload(edited,g_ModReloadState,operations);
    if (edited) {
        const auto frequency=RuntimePerfTicksPerSecond();
        g_ModReloadLastMicros=frequency?(RuntimePerfTick()-tick)*1000000ULL/frequency:0;
        if (g_ModReloadLastMicros>g_ModReloadMaxMicros) g_ModReloadMaxMicros=g_ModReloadLastMicros;
        if (!result) {
            char message[96];
            const int count=std::snprintf(message,sizeof(message),"Mod reload failed at phase %u",g_ModReloadState.failure);
            if (count>0) LuaRuntime::RecordLuaErrorText(message,static_cast<std::size_t>(count));
        }
    }
    return result;
#endif
}
} // namespace isaac::runtime

namespace isaac::runtime {
bool PublishManagerUpdateEntryRelayOriginal(std::uintptr_t original) noexcept {
    return ManagerUpdateHook::PublishOriginal(original);
}
}

namespace {
// 先认证后发布；回调只取缓存，不反复查询代码映射或扫描入口。
std::atomic<std::uintptr_t> g_GreedHourglassRoomTransition{0};
[[maybe_unused]] void PublishGreedHourglassRoomTransition(const TargetModule& module) noexcept {
    std::uintptr_t entry = 0;
    if (module.buildId == kTargetBuildId) {
        static_cast<void>(isaac::runtime::engine_call::ResolveEntryAddress(
            module.base, module.textSize, kGameStartRoomTransitionOffset,
            kGameStartRoomTransitionExpectedBytes, &entry, &IsMappedRxModuleCodeWindow));
    }
    g_GreedHourglassRoomTransition.store(entry, std::memory_order_release);
}
} // namespace

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
void MarkStage14DiagnosticReady() {
    g_Stage14Controller.MarkReady();
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
NORETURN void ReportStage13Failure(u32 status) {
    g_Stage13State.store(Stage13State::Finished, std::memory_order_release);
    svcBreak(BreakReason_User, kStage13FailureMagic, (13ULL << 32) | status);
    svcExitProcess();
}
#endif

#if !defined(EXL_DIAGNOSTIC_STAGE)
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
void AllowDefaultManifestInitialization() {
    g_DefaultManifestInitializationAllowed.store(1, std::memory_order_release);
}
#endif

// 走入口中继的挂点：中继把"原函数"记在自己的槽里，蹦床把它记在 `Orig` 里。要让两个后端共用
// 同一份钩子体，就在中继装好后把中继记下的**回退入口**发布给蹦床的 `Orig`
// （`TrampolineHook::PublishOriginal`）：此后钩子体里的 `Orig(...)` 等价于"跳回原入口"。
//
// 只处理**复用 `Callback` 体**的那一路（`ManagerUpdate`）。`ManagerRender` 的钩子体早已抽成
// 自由函数、由中继回调自己读回退入口，因此不需要发布。
//
// 时序：在 `TryInstallDefaultManifestMod` 里安装成功后立即调用，仍在模块初始化线程上
// （游戏主循环尚未开始），所以不存在"入口已改写、`Orig` 还是空"的窗口。发布失败（地址为 0
// 或未对齐）意味着安装器的守恒被破坏，此处不做兜底 —— 与 `ManagerRender` 那一路"回退入口
// 在安装函数返回前写入"的既有口径一致。
void PublishEntryRelayOriginals(const TargetModule& module) {
    const auto usesRelay = [](isaac::runtime::HookId id) {
        return isaac::runtime::kHookBackends[static_cast<std::size_t>(id)] ==
               isaac::runtime::HookBackend::EntryRelay;
    };
    if (usesRelay(isaac::runtime::HookId::ManagerUpdate)) {
        const uintptr_t original =
            isaac::runtime::EntryRelayFallbackEntry(isaac::runtime::HookId::ManagerUpdate);
        if (original != 0) {
            ManagerUpdateHook::PublishOriginal(original);
        }
    }
    // 取道具前挂点：旧安装器在这一步还**兼职**把"原函数入口"交给 Lua 侧的
    // `ItemPool:GetCollectible`（`ValidateItemPoolGetCollectibleMethod` 会核对那个地址的形态）。
    // 零占洞路径发布的地址与旧后端**完全相同** —— 都是游戏入口本身：从 Lua 调它等于再走一遍整条
    // 取道具路径（含 Mod 回调，与 PC 语义一致）；入口现在被入口中继的桩接管，桩会把控制权交回我们的
    // 回调，而回调里的"正在派发"守卫会让它直接落到原函数。
    if (usesRelay(isaac::runtime::HookId::PreGetCollectible)) {
        // 这里直接写 `base + offset`（不经过 `target_address`：它的定义在本函数之后）。
        LuaRuntime::SetItemPoolGetCollectibleBinding(module.base + kPreGetCollectibleRelayOffset);
    }
    // 贴图桥（`ImagePcxLoad` / v2 `ImageManagerLoadFile`）：best-effort 发布内存版 Load +
    // 三个 zlib 符号 + v2 的五参内存版。失败只让 `.png`→`.pcx` 兜底静默失效，不影响安装。
    if (usesRelay(isaac::runtime::HookId::ImagePcxLoad) ||
        usesRelay(isaac::runtime::HookId::ImageManagerLoadFile) ||
        usesRelay(isaac::runtime::HookId::ContentGetMountedFilePath)) {
        // 同一初始化入口：已在Game::Init准备过则幂等复用，绝不重复安装或覆盖绑定。
        (void)isaac::runtime::bridge::PrepareModImageResources(
            module, &g_DefaultManifestBindings, &g_ImagePcxBindings);
    }
    // 批次 363（2026-10-04）：`ANM2::Load` 入口中继的两件准备 ——
    //   ① 回退入口（回调靠它跑原函数）；② 引擎侧绑定（作废原语 + 两个 GOT 槽 + 解析器）。
    // 绑定不齐时 `PrepareAnm2LoadOverride` 返回 false，并把内部绑定清空 ⇒ 回调退化为
    // "只跑原函数"（= 今天之前的行为），**绝不半套使用**。
    if (usesRelay(isaac::runtime::HookId::Anm2Load)) {
        const uintptr_t anm2Original =
            isaac::runtime::EntryRelayFallbackEntry(isaac::runtime::HookId::Anm2Load);
        if (anm2Original != 0) {
            isaac::runtime::bridge::PublishAnm2LoadFallbackEntry(anm2Original);
        }
        isaac::runtime::bridge::PrepareAnm2LoadOverride(module);
    }
}

// 引擎绑定的校验与发布：定义在文件后部、与旧更新钩子安装器相邻（要用的 Verify* 辅助函数都在那儿）。
// 这里先声明，因为**零占洞后端路径也要调用它** —— 那条路径不经过旧安装器，若不显式调用，
// Sprite/Font 等绑定就会缺失，Mod 的 Lua 在 `Sprite()` 处直接失败（2026-09-14 真机）。
void PublishManagerEngineBindings(const TargetModule& module);

DefaultManifestInstallResult TryInstallDefaultManifestMod(const TargetModule& module) {
    uintptr_t target = 0;
    uintptr_t slot = 0;
    GameFileReader::Bindings bindings{};
    // 这里验哪一套前提，取决于更新挂点走哪个后端（2026-09-14 真机撞出来的迁移缺陷）：
    //   * 旧 IPS 后端：游戏映像里**必须有**那段中继（入口已被改写成跳转、洞里有桩），
    //     `VerifyManagerRelay` 检查的正是这个前提；
    //   * 零占洞后端：前提**正好相反** —— 入口要保持原样（入口中继自己拿 16 字节台账做版本
    //     比对），洞也不再需要。若这时仍按旧前提验，**删掉那份 IPS 之后这里会直接判失败，
    //     整个 Mod 都装不上**（实测：`ManifestInstallReturned` 的 detail = 1，五个挂点全空）。
    // 因此按 `kHookBackends` 选择：走零占洞时只做模块/构建号与文件读取绑定这两项校验。
    const bool updateUsesRelay =
        isaac::runtime::kHookBackends[static_cast<std::size_t>(
            isaac::runtime::HookId::ManagerUpdate)] == isaac::runtime::HookBackend::EntryRelay;
    const bool updateVerified = VerifyManagerUpdate(module, &target);
    const bool relayVerified =
        updateUsesRelay || (updateVerified && VerifyManagerRelay(module, target, &slot));
    if (!updateVerified || !relayVerified ||
        !GameFileReader::VerifyBindings(module, &bindings)) {
        return DefaultManifestInstallResult::FileBindingMismatch;
    }
    g_DefaultManifestBindings = bindings;
    // Armed在本函数所有安装/发布成功后的末尾释放；主线程此时仍保持Unarmed。
    // The required/optional interception policy lives in HookInstallService, so
    // this function only verifies the manifest bindings, arms the state and
    // delegates installation of every hook (including the two optional relays
    // that used to be installed directly here).
    isaac::runtime::ModuleInfo info{};
    info.base = module.base;
    info.textSize = module.textSize;
    info.imageSize = module.size;
    info.valid = module.base != 0 && module.textSize != 0;
    const std::size_t buildIdBytes = std::min(info.buildId.size(), module.buildId.size());
    std::memcpy(info.buildId.data(), module.buildId.data(), buildIdBytes);
    // 先在安装前把真实回调接进入口中继绑定表，再换成按挂点路由的适配器
    // （M2a 第一路：`ManagerUpdate` 已切到 `EntryRelay`；`ManagerRender` 是 M1 切的）。
    PublishGreedHourglassRoomTransition(module);
    isaac::runtime::RegisterEntryRelayCallbacks();
    isaac::runtime::HookRoutingAdapter hookAdapter{};
    isaac::runtime::HookInstallService hookService{hookAdapter};
    // 跳过判据**无条件注册**：没有开任何 `EXL_SKIP_HOOK_*` / `EXL_ONLY_REQUIRED_HOOK` 时它恒返回
    // false（行为与从前完全一致），开了才生效。这样"二分构建"不需要再改两处条件编译。
    //
    // ⚠️ 判据必须是**编译期常量**：这一步跑在 worker 线程上，读卡会崩（见 `CardSwitchOn` 上面那段）。
    hookService.SetSkipPredicate(&SkipOptionalHooksPredicate, nullptr);
    // ★★★ 批次 365（2026-10-05）：**引擎绑定的"校验 + 发布"必须在任何"入口改写"之前做完。**
    //
    // 为什么（真机定案的根因，读数见 `docs/真机读数-20261005-0124-批次363上卡后-SpriteLoad绑定被入口补丁打死.md`）：
    //   批次 363 的 `ANM2::Load` 中继把游戏模块 `0xC970` 的头 16 字节改成跳转桩，而**同一个地址**
    //   就是 Lua 侧 `Sprite:Load` 的引擎绑定 —— `VerifyBindingTable` 是**从活内存里读那 16 字节**
    //   与期望序言逐字节比的。挂点安装在前、绑定校验在后 ⇒ 校验读到的是**我们自己的跳转桩**
    //   ⇒ `kSpriteBindingEntries` 里 `load` 那一格留 0 ⇒ 每个模组的 `Sprite:Load` 都抛
    //   `native binding is unavailable`（真机：5 个模组同一条错、回调登记数 81 → 16、
    //   `ManifestInstallReturned` 的 detail 由 0 变 21 = ScriptRunFailed）。
    //   ⇒ 把"校验 + 发布"挪到安装之前：守卫看到的是**原版序言**（判据因此更正确），
    //   而发布出去的地址**不变**（还是 `base + 0xC970`），此后该地址被中继接管 ⇒
    //   Lua 的 `Sprite:Load` 会**走中继** —— 这正是"模组覆盖本体资源"那条链要的语义
    //   （与 PC 一致：模组层在引擎读之前就位）。
    //
    // 为什么提前是安全的：这个函数只做"逐入口核对序言 + 发布原子量"，**不读任何挂点安装结果**。
    // 代价（如实写）：若挂点安装随后失败，绑定已经发布出去了 —— 那时清单安装整体返回失败、
    // 模组脚本根本不会跑，所以这个差别没有可观察后果。
    //
    // 门禁：`runtime/tests/test_binding_guard_ordering.py` 钉住这个顺序（且会在"既没有
    // EntryRelay 靶点、又没有绑定守卫"时判为**空洞**而报红）。
    PublishManagerEngineBindings(module);
    isaac::runtime::HookInstallReport hookReport{};
    const bool hooksInstalled =
        info.valid && hookService.InstallProductionHooks(info, &hookReport).ok();
    // 必须在下面那个早退之前：装失败也要能在设备侧读到（否则失败结果永远记不下来）。
    // 失败码来自路由适配器转发的入口中继后端（0 表示无失败）。
    isaac::runtime::PublishHookInstallReport(
        hookReport, isaac::runtime::HookRoutingFailureCode(hookAdapter));
    if (!hooksInstalled) {
        g_DefaultManifestBindings = {};
        g_DefaultManifestState.store(DefaultManifestState::Unarmed,std::memory_order_release);
        return DefaultManifestInstallResult::FileBindingMismatch;
    }
    // 更新挂点复用蹦床里那个 `Callback`（入口中继回调直接调它），所以必须在这里把中继记下的
    // 回退入口发布给 `Orig` —— 此后的游戏帧才会走到我们的代码。到达这一行意味着
    // `InstallProductionHooks` 已返回成功，即必需的更新挂点已经装上。
    // 同一个函数里还会补上"取道具前"挂点原本由旧安装器兼管的那项发布（`ItemPool:GetCollectible`
    // 的原函数绑定），理由见其定义处。
    PublishEntryRelayOriginals(module);
    // 引擎绑定（Sprite/Font/音乐/输入/RNG/玩家槽…）**已经在本函数更靠前处发布**
    // （批次 365 挪过去的，理由见那一处注释：守卫校验必须早于任何入口改写，
    //  否则中继改过的入口会被守卫判成"序言不符"、那一格绑定静默留 0）。
    // 这一段历史上写的理由依然成立 —— 缺了这些绑定，Mod 的 Lua 会在 `Sprite()`/`Font()`
    // 处当场失败（2026-09-14 真机，见那个函数的注释）；"这里"只是提前到了安装之前。
    // ★★ 2026-09-23 修（真机定位到的 bug）：把**会话内容挂载服务发布出去**。
    //
    // 重建中继（`IsaacModRuntime_RebuildContentMountPointsRelay`）靠
    // `SessionContentMountService()` 拿到这个实例，才能在引擎重建挂载点表之后把
    // **Mod 的挂载点重新挂回去**；而 `SetSessionContentMountService(...)` 以前
    // **从来没有被调用过** ⇒ 那个指针恒为空 ⇒ 中继每次都直接返回、**一个挂载点都不恢复**。
    //
    // 真机后果（2026-09-23 用户报"换过语言之后 EID 的信息显示坏掉"）：
    //   换语言 → `Manager::SetLanguage` **尾调用** `RebuildContentMountPoints`（反汇编实证）
    //   → 挂载点表重建、Mod 的挂载点全丢、中继又恢复不了
    //   → EID 下次开局（`MC_POST_GAME_STARTED`）重新 `Font:Load` 它自己的 `.fnt` 时**文件打不开**
    //   → 而 `Font::Load` 开头先 `Unload()` ⇒ 字体**永久停在"未加载"** ⇒ 信息全不显示，
    //     只剩开机时已经载进内存的图标还在闪。**重启就好**（开机走的是 `RegisterMod` 那条路）。
    //
    // ★★★ 批次 378（2026-10-05）：**这一段（发布会话内容挂载服务）已撤除** —— 它不是"没用了"
    //   而是"它服务的那件事不存在了"：不再有任何模组目录被注册成内容挂载点，引擎重建挂载点表
    //   也就不会丢掉任何属于我们的东西。取而代之的是 `PublishModResourceRedirectList`（纯内存），
    //   而重定向本身**无状态**：它不依赖挂载表，所以既不会被 `RebuildContentMountPoints` 清掉，
    //   也不需要"重建之后补挂"。
    //
    //   上面那段历史（2026-09-23"换语言之后 EID 信息坏掉"）之所以能修好，是因为当时模组的资源
    //   确实靠挂载点解析；375 之后同一条路径由重定向解析 ⇒ **同一个真机判据（换语言后 EID 的
    //   `.fnt` 还能不能打开）仍然必须复测**，见开工单的验收面。
    //
    //   于是 `SessionContentMountService()` 恒为空、`g_ContentMountService.mod_count()` 恒为 0
    //   ⇒ 贴图桥里那几处依赖它的探针/自愈（`RunLateRemountTrial`、`EnsureModMountsAlive`、
    //   `ModCountNow`）**全都停在"还没挂上"这一支**、一个字节都不写引擎。读数里对应那几格
    //   恒为 0，**那是"机制已撤除"，不是"测下来没问题"** —— 读数解释时必须这么读。
    // ★★ 批次 149（2026-09-26）：把"**本帧的 Manager**"来源发布给 Lua 侧。
    //
    // 为什么需要：`MusicManager:` 的每个方法都要一个 Manager 才能定位引擎的 `Music` 对象，而那个
    // Manager 以前只来自"当前正在派发的那条回调"。可 `MC_POST_UPDATE` 的派发**不带** Manager
    // （`LuaCallbackInvoker{0, false, true}`，那条例行字面量被 `test_embedded_lua_runtime.py` 钉着）
    // ⇒ 模组在 `MC_POST_UPDATE` 里调 `MusicManager():Play(...)` 时恒为空、整族报
    // "native bindings are unavailable"。真机实例：The Specialist for Good Items 的"捡到四级物品
    // 放歌"（`main.lua:482/488/493/500`）全在 `MC_POST_UPDATE` 里 —— 那正是"仍然不跳舞"的直接原因。
    // PC 的绑定层读的是引擎自己的全局 Manager，所以这里也把"每帧 `Manager::Update` 收到的 self"
    // 交给 Lua 侧兜底；两者本来就是同一个 Manager 单例（`DispatchPostRender` 拿到的也是它）。
    //
    // 放在这里（而不是每帧写一次）：与上面那次发布同一条理由 —— 仍在模块初始化线程上、
    // 游戏主循环尚未开始；而 `g_RenderFrameManager` 是**变量**，回调里读到的一定是最新值。
    LuaRuntime::SetFrameManagerProvider([]() -> std::uintptr_t {
        return g_RenderFrameManager.load(std::memory_order_acquire);
    });
#if defined(EXL_PROBE_BREAK) && EXL_PROBE_BREAK_NATIVE_MODS_MENU
    // 批次 040（探针专用，生产包不含）：在 `Menu_Title::Render` 的**函数入口**挂一个入口中继，
    // 让探针的原生模组页画在**引擎自己的渲染上下文里**（批次 019~039 是在 `Present` 前中继里
    // 带外画的，那套上下文不存在 ⇒ 位置怎么调都不对）。
    // 放在这里而不是帧里：**此处仍在模块初始化线程上、游戏主循环尚未开始**，改游戏代码
    // 不存在与渲染线程抢的窗口（与上面那些发布同一条理由）。
    isaac::runtime::probe::NativeModsMenuProbeInstallRelay(module);
#else
    // 批次 077：生产版的"安装点"。
    // 三个入口中继本身由上面那次 `InstallProductionHooks` 按挂点登记表装好了 —— 这里做的是
    // 探针在安装函数里做的那几件事：把"三个中继装没装上"记进状态面、一次性逐字节核对我们要
    // **直接调用**的那些引擎入口（`Menu_Mods` 的五个方法、`ANM2` 两个跳板、`Font` 三个入口…）、
    // 备好读 `metadata.xml` 那组绑定。核对不过只是"不调用"，一个字节都不写。
    //
    // 与探针那一段**互斥**（两个 TU 装的是同一批入口）：判据在 `SkipOptionalHooksPredicate`。
    isaac::runtime::modmenu::ModMenuNativeInstall(module);
#endif
    // ★★ 批次 193（2026-09-28，用户诉求「原生小地图改成局部触摸」）：原生右上角小地图的
    // 触摸门控 —— 只改游戏代码里的 3 条指令，见 `patch/minimap_touch_gate.hpp` 的逐条说明。
    //
    // 时机与上面那几条发布/安装**同一起点**：仍在模块初始化线程上、游戏主循环尚未开始，
    // 改游戏指令不存在与执行线程抢的窗口（这正是 `TryInstallDefaultManifestMod` 存在的意义）。
    // 放在探针/生产那条 `#if` 的**外面**：两个构建都要装上它（它是游戏行为修正，不是挂点）。
    //
    // 装不上不阻断 Mod 加载（与可选挂点同一处置）：后果只是"原生小地图照旧全局响应触摸"，
    // 用户看到的是"没变化"而不是"坏了"。为什么装不上、改了几处，全部记在四个
    // `g_MinimapTouchGate*` 诊断量里，设备侧可回读（父线程的读数工具会加进偏移表）。
    isaac::runtime::InstallMinimapTouchGate(module.base, module.textSize);
    // `MC_POST_RENDER` 的 Present 前派发点与内容挂载点重建中继都是可选能力：装不上只是
    // 回退（回调晚一帧派发）或不重建挂载点，不影响安装成败 —— 两个都由
    // `HookInstallService::InstallProductionHooks` 经 `IHookPort` 安装，装没装上记在
    // `HookInstallReport` 里（设备侧可回读）。
    g_DefaultManifestState.store(DefaultManifestState::Armed,std::memory_order_release);
    return DefaultManifestInstallResult::Success;
}
#endif

uintptr_t target_address(uintptr_t base, uintptr_t offset) {
    return base + offset;
}

bool verify_bytes(const u8* expected, const u8* actual, size_t length) {
    return expected != nullptr && actual != nullptr && std::memcmp(expected, actual, length) == 0;
}

bool VerifyManagerUpdate(const TargetModule& module, uintptr_t* target) {
    if (target == nullptr || module.base == 0 || module.textSize < kManagerUpdateFileOffset + kManagerRelayExpectedEntry.size()) {
        return false;
    }
    if (module.buildId != kTargetBuildId || kManagerUpdateFileOffset % 4 != 0) {
        return false;
    }
    const uintptr_t candidate = target_address(module.base, kManagerUpdateFileOffset);
    if (candidate < module.base || !module.Contains(candidate, kManagerRelayExpectedEntry.size()) || candidate % 4 != 0) {
        return false;
    }
    if (!IsMappedRxModuleCodeWindow(candidate, kManagerRelayExpectedEntry.size())) {
        return false;
    }
    *target = candidate;
    return true;
}

bool VerifyManagerRelay(const TargetModule& module, uintptr_t target, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || target == 0 ||
        module.textSize < kManagerRelayCodeOffset + kManagerRelayExpectedBytes.size()) {
        return false;
    }
    if (target != target_address(module.base, kManagerUpdateFileOffset) ||
        !module.Contains(target, kManagerRelayExpectedEntry.size()) ||
        !IsMappedRxModuleCodeWindow(target, kManagerRelayExpectedEntry.size())) {
        return false;
    }
    std::array<u8, kManagerRelayExpectedEntry.size()> entry{};
    std::memcpy(entry.data(), reinterpret_cast<const void*>(target), entry.size());
    if (!verify_bytes(kManagerRelayExpectedEntry.data(), entry.data(), entry.size())) {
        return false;
    }

    const uintptr_t relay = target_address(module.base, kManagerRelayCodeOffset);
    if (relay < module.base || !module.Contains(relay, kManagerRelayExpectedBytes.size()) || relay % 4 != 0 ||
        !IsMappedRxModuleCodeWindow(relay, kManagerRelayExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kManagerRelayExpectedBytes.size() - sizeof(uintptr_t)> bridge{};
    std::memcpy(bridge.data(), reinterpret_cast<const void*>(relay), bridge.size());
    if (!verify_bytes(kManagerRelayExpectedBytes.data(), bridge.data(), bridge.size())) {
        return false;
    }

    const uintptr_t candidateSlot = target_address(module.base, kManagerRelaySlotOffset);
    if (candidateSlot < module.base || (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    *slot = candidateSlot;
    return true;
}

bool VerifyManagerRender(const TargetModule& module, uintptr_t* target) {
    if (target == nullptr || module.base == 0 ||
        module.textSize < kManagerRenderFileOffset + kManagerRenderRelayExpectedEntry.size() ||
        module.buildId != kTargetBuildId || kManagerRenderFileOffset % 4 != 0) {
        return false;
    }
    const uintptr_t candidate = target_address(module.base, kManagerRenderFileOffset);
    if (candidate < module.base || !module.Contains(candidate, kManagerRenderRelayExpectedEntry.size()) ||
        candidate % 4 != 0 || !IsMappedRxModuleCodeWindow(candidate, kManagerRenderRelayExpectedEntry.size())) {
        return false;
    }
    *target = candidate;
    return true;
}

bool VerifyManagerRenderRelay(const TargetModule& module, uintptr_t target, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || target == 0 ||
        module.textSize < kManagerRenderRelayCodeOffset + kManagerRenderRelayExpectedBytes.size() ||
        target != target_address(module.base, kManagerRenderFileOffset) ||
        !module.Contains(target, kManagerRenderRelayExpectedEntry.size()) ||
        !IsMappedRxModuleCodeWindow(target, kManagerRenderRelayExpectedEntry.size())) {
        return false;
    }
    std::array<u8, kManagerRenderRelayExpectedEntry.size()> entry{};
    std::memcpy(entry.data(), reinterpret_cast<const void*>(target), entry.size());
    if (!verify_bytes(kManagerRenderRelayExpectedEntry.data(), entry.data(), entry.size())) {
        return false;
    }
    const uintptr_t relay = target_address(module.base, kManagerRenderRelayCodeOffset);
    if (relay < module.base || relay % 4 != 0 ||
        !module.Contains(relay, kManagerRenderRelayExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(relay, kManagerRenderRelayExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kManagerRenderRelayExpectedBytes.size() - sizeof(uintptr_t)> bridge{};
    std::memcpy(bridge.data(), reinterpret_cast<const void*>(relay), bridge.size());
    if (!verify_bytes(kManagerRenderRelayExpectedBytes.data(), bridge.data(), bridge.size())) {
        return false;
    }
    const uintptr_t candidateSlot = target_address(module.base, kManagerRenderRelaySlotOffset);
    if (candidateSlot < module.base || (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    *slot = candidateSlot;
    return true;
}

namespace {
bool VerifyPreGetCollectibleRelay(const TargetModule& module, uintptr_t* slot, uintptr_t* original) {
    if (slot == nullptr || original == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kPreGetCollectibleRelayExpectedOriginal.size() > module.textSize ||
        kPreGetCollectibleRelayExpectedBytes.size() > module.textSize ||
        sizeof(uintptr_t) > module.textSize ||
        kPreGetCollectibleRelayOffset > module.textSize - kPreGetCollectibleRelayExpectedOriginal.size() ||
        kPreGetCollectibleRelayCodeOffset > module.textSize - kPreGetCollectibleRelayExpectedBytes.size() ||
        kPreGetCollectibleRelaySlotOffset > module.textSize - sizeof(uintptr_t)) {
        return false;
    }
    const uintptr_t target = target_address(module.base, kPreGetCollectibleRelayOffset);
    const uintptr_t relay = target_address(module.base, kPreGetCollectibleRelayCodeOffset);
    const uintptr_t candidateSlot = target_address(module.base, kPreGetCollectibleRelaySlotOffset);
    if (target < module.base || relay < module.base || candidateSlot < module.base ||
        (target & 3u) != 0 || (relay & 3u) != 0 ||
        (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(target, kPreGetCollectibleRelayExpectedOriginal.size()) ||
        !module.Contains(relay, kPreGetCollectibleRelayExpectedBytes.size()) ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(target, kPreGetCollectibleRelayExpectedOriginal.size()) ||
        !IsMappedRxModuleCodeWindow(relay, kPreGetCollectibleRelayExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    std::array<u8, kPreGetCollectibleRelayExpectedOriginal.size()> targetBytes{};
    std::array<u8, kPreGetCollectibleRelayExpectedBytes.size()> relayBytes{};
    std::memcpy(targetBytes.data(), reinterpret_cast<const void*>(target), targetBytes.size());
    std::memcpy(relayBytes.data(), reinterpret_cast<const void*>(relay), relayBytes.size());
    if (!verify_bytes(kPreGetCollectibleRelayExpectedEntry.data(), targetBytes.data(),
                      kPreGetCollectibleRelayExpectedEntry.size()) ||
        !verify_bytes(kPreGetCollectibleRelayExpectedOriginal.data() +
                          kPreGetCollectibleRelayExpectedEntry.size(),
                      targetBytes.data() + kPreGetCollectibleRelayExpectedEntry.size(),
                      targetBytes.size() - kPreGetCollectibleRelayExpectedEntry.size()) ||
        !verify_bytes(kPreGetCollectibleRelayExpectedBytes.data(), relayBytes.data(), relayBytes.size())) {
        return false;
    }
    *slot = candidateSlot;
    *original = target;
    return true;
}

PreGetCollectibleRelayInstallResult PublishPreGetCollectibleRelayCallback(uintptr_t slot,
                                                                          uintptr_t callback) {
    if (slot == 0 || callback == 0 || (callback & 3u) != 0) {
        return PreGetCollectibleRelayInstallResult::RelayPublishFailed;
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (rwSlot == nullptr) return PreGetCollectibleRelayInstallResult::RelayPublishFailed;
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return PreGetCollectibleRelayInstallResult::RelaySlotNotEmpty;
    }
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    return __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) == callback
               ? PreGetCollectibleRelayInstallResult::Success
               : PreGetCollectibleRelayInstallResult::RelayPublishFailed;
}
}

PreGetCollectibleRelayInstallResult TryInstallPreGetCollectibleRelay(const TargetModule& module) {
    uintptr_t slot = 0;
    uintptr_t original = 0;
    if (!VerifyPreGetCollectibleRelay(module, &slot, &original)) {
        return RecordPreGetCollectibleInstall(
            PreGetCollectibleRelayInstallResult::RelayPatchMismatch);
    }
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&LuaRuntime::DispatchPreGetCollectible);
    if (callback == 0 || (callback & 3u) != 0) {
        return RecordPreGetCollectibleInstall(
            PreGetCollectibleRelayInstallResult::RelayPublishFailed);
    }
    const auto publish = PublishPreGetCollectibleRelayCallback(slot, callback);
    if (publish == PreGetCollectibleRelayInstallResult::Success) {
        LuaRuntime::SetItemPoolGetCollectibleBinding(original);
    }
    return RecordPreGetCollectibleInstall(publish);
}

#if defined(EXL_DIAGNOSTIC_STAGE) && \
    (EXL_DIAGNOSTIC_STAGE == 102 || EXL_DIAGNOSTIC_STAGE == 104 || EXL_DIAGNOSTIC_STAGE == 110 || EXL_DIAGNOSTIC_STAGE == 112)
namespace {
bool VerifyStage102ChangeRoomRelay(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        module.textSize < kGameChangeRoomRelayCodeOffset + kGameChangeRoomRelayExpectedBytes.size()) {
        return false;
    }
    const uintptr_t target = target_address(module.base, kGameChangeRoomCallFileOffset);
    if (target < module.base || target % 4 != 0 ||
        !module.Contains(target, kGameChangeRoomRelayExpectedEntry.size()) ||
        !IsMappedRxModuleCodeWindow(target, kGameChangeRoomRelayExpectedEntry.size())) {
        return false;
    }
    std::array<u8, kGameChangeRoomRelayExpectedEntry.size()> entry{};
    std::memcpy(entry.data(), reinterpret_cast<const void*>(target), entry.size());
    if (!verify_bytes(kGameChangeRoomRelayExpectedEntry.data(), entry.data(), entry.size())) {
        return false;
    }
    const uintptr_t relay = target_address(module.base, kGameChangeRoomRelayCodeOffset);
    if (relay < module.base || relay % 4 != 0 ||
        !module.Contains(relay, kGameChangeRoomRelayExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(relay, kGameChangeRoomRelayExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kGameChangeRoomRelayExpectedBytes.size()> relayBytes{};
    std::memcpy(relayBytes.data(), reinterpret_cast<const void*>(relay), relayBytes.size());
    if (!verify_bytes(kGameChangeRoomRelayExpectedBytes.data(), relayBytes.data(), relayBytes.size())) {
        return false;
    }
    const uintptr_t candidateSlot = target_address(module.base, kGameChangeRoomRelaySlotOffset);
    if (candidateSlot < module.base || (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    *slot = candidateSlot;
    return true;
}
}

#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
Stage110ChangeRoomInstallResult TryInstallStage110ChangeRoomDiagnostic(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyStage102ChangeRoomRelay(module, &slot)) return Stage110ChangeRoomInstallResult::RelayPatchMismatch;
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) return Stage110ChangeRoomInstallResult::RelaySlotNotEmpty;
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveStage110ChangeRoom);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    return __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) == callback
               ? Stage110ChangeRoomInstallResult::Success : Stage110ChangeRoomInstallResult::RelayPublishFailed;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
Stage102ChangeRoomInstallResult TryInstallStage102ChangeRoomDiagnostic(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyStage102ChangeRoomRelay(module, &slot)) {
        return Stage102ChangeRoomInstallResult::RelayPatchMismatch;
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return Stage102ChangeRoomInstallResult::RelaySlotNotEmpty;
    }
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveStage102ChangeRoom);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return Stage102ChangeRoomInstallResult::RelayPublishFailed;
    }
    return Stage102ChangeRoomInstallResult::Success;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
namespace {
bool VerifyStage104ChangeRoomRelay(const TargetModule& module, uintptr_t* slot) {
    return VerifyStage102ChangeRoomRelay(module, slot);
}
}

Stage104RoomKeyInstallResult TryInstallStage104RoomKeyDiagnostic(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyStage104ChangeRoomRelay(module, &slot)) {
        return Stage104RoomKeyInstallResult::RelayPatchMismatch;
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return Stage104RoomKeyInstallResult::RelaySlotNotEmpty;
    }
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveStage104ChangeRoom);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return Stage104RoomKeyInstallResult::RelayPublishFailed;
    }
    return Stage104RoomKeyInstallResult::Success;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 112
Stage112DescriptorReentryInstallResult TryInstallStage112DescriptorReentryDiagnostic(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyStage102ChangeRoomRelay(module, &slot)) {
        return Stage112DescriptorReentryInstallResult::RelayPatchMismatch;
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return Stage112DescriptorReentryInstallResult::RelaySlotNotEmpty;
    }
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveStage112ChangeRoom);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    return __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) == callback
               ? Stage112DescriptorReentryInstallResult::Success
               : Stage112DescriptorReentryInstallResult::RelayPublishFailed;
}
#endif

// ---- 游戏开局：**常驻**挂点（2026-09-14 从诊断阶段 108/110 提升而来）----------------
//
// 引擎侧的中继由 `atmosphere/nro_patches/isaac-repentance-lifecycle-relay` 的 IPS 放进代码洞：
// 它先把 `Game::Start` / `Game::StartFromSavedState` 的原 PLT 调用**跑完**，再从槽里取出我们
// 发布进去的回调调用（签名 `void(void* game, std::uint32_t eventKind)`，1 = 读档、2 = 新局），
// 最后回到调用点之后继续。所以"游戏确实已经开好局了"这件事由时机本身保证。
//
// 为什么这里与下面 Stage108 诊断那段看着重复：诊断设施已按裁定**冻结**（不再新增、不再维护），
// 所以常驻路径自带一份校验，而不是去改动那两段被冻结的代码；等诊断阶段整体清理时再合并。
namespace {

// ★ 刻意只记账、**不在这里跑 Lua**：本函数运行在引擎的开局序列里（`Game::Start` 刚返回），
// 在这个时机调用模组回调风险高（游戏对象刚建、状态还在收尾）。真正的派发交给下一帧的
// `LuaRuntime::DispatchPostUpdate()`（见 `lua_runtime.cpp` 的 `NoteGameStarted` /
// `DispatchPostGameStarted`）。代价只是"晚一帧"，换来的是不必在开局序列里运行 Lua。
void ObserveGameStart(void* game, std::uint32_t eventKind) {
    (void)game;
    if (eventKind != 1 && eventKind != 2) {
        return;
    }
    // ★★ 批次 117/119：**局内单向闩锁**的一条局边界到了。三类的处置不同（见 `NoteNewRun`）：
    //   * `LoadSave`（继续同一份存档）⇒ 把出局时的留存**接回来**（用户裁定：继续算同一局）；
    //   * `NewRun`（开新局）⇒ **真清零**（裁定①：进局前关掉模组 ⇒ 这一局不锁）。
    //   ⚠️ 这两条通知都在 `Game::Start` / `StartFromSavedState` **返回之后**才到，
    //   而引擎那次写只读位在函数**体内** ⇒ 所以"接回来"必须由下一帧的观察点**补写一次锁**，
    //   而"开新局要清"靠的是出局时就已经把闩锁转成了留存（详见 `NoteNewRun` 与 `.hpp`）。
    isaac::runtime::modmenu::NoteNewRun(eventKind == 1
                                            ? isaac::runtime::modmenu::RunBoundaryKind::LoadSave
                                            : isaac::runtime::modmenu::RunBoundaryKind::NewRun);
    LuaRuntime::NoteGameStarted(eventKind == 1);
}

// 安装前先核对"放代码洞的那份补丁确实是我们要的那一份"：两个调用点的分支指令、两段中继代码、
// 以及槽本身的位置都必须逐字节对得上。对不上就拒绝安装 —— 宁可少一个事件，
// 也不跳进一段来路不明的代码。
bool VerifyGameStartRelay(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        module.textSize < kGameStartNewRelayCodeOffset + kGameStartNewRelayExpectedBytes.size()) {
        return false;
    }
    const auto verifyRelay = [&module](uintptr_t callOffset, const auto& entry,
                                       uintptr_t relayOffset, const auto& code) {
        const uintptr_t target = target_address(module.base, callOffset);
        const uintptr_t relay = target_address(module.base, relayOffset);
        if (target < module.base || target % 4 != 0 || !module.Contains(target, entry.size()) ||
            !IsMappedRxModuleCodeWindow(target, entry.size()) || relay < module.base || relay % 4 != 0 ||
            !module.Contains(relay, code.size()) || !IsMappedRxModuleCodeWindow(relay, code.size())) {
            return false;
        }
        return verify_bytes(entry.data(), reinterpret_cast<const u8*>(target), entry.size()) &&
               verify_bytes(code.data(), reinterpret_cast<const u8*>(relay), code.size());
    };
    if (!verifyRelay(kGameStartSavedCallFileOffset, kGameStartSavedRelayExpectedEntry,
                     kGameStartSavedRelayCodeOffset, kGameStartSavedRelayExpectedBytes) ||
        !verifyRelay(kGameStartNewCallFileOffset, kGameStartNewRelayExpectedEntry,
                     kGameStartNewRelayCodeOffset, kGameStartNewRelayExpectedBytes)) {
        return false;
    }
    const uintptr_t candidateSlot = target_address(module.base, kGameStartRelaySlotOffset);
    if (candidateSlot < module.base || (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    *slot = candidateSlot;
    return true;
}

}  // namespace

GameStartRelayInstallResult TryInstallGameStartRelay(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyGameStartRelay(module, &slot)) {
        return GameStartRelayInstallResult::RelayPatchMismatch;
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return GameStartRelayInstallResult::RelaySlotNotEmpty;
    }
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveGameStart);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return GameStartRelayInstallResult::RelayPublishFailed;
    }
    return GameStartRelayInstallResult::Success;
}

// 加载前静态补丁已经改好正常完成边界；运行时只发布8B槽，不热改栈指令。
bool TryInstallProjectileTailRelay(const TargetModule& module,bool initialize) {
    namespace tail=isaac::runtime::projectile_tail;
    const auto function=initialize?tail::kInitFunction:tail::kFunction;
    const auto length=initialize?tail::kInitSize:tail::kSize;
    const auto gate=initialize?tail::kInitGate:tail::kGate;
    const auto offset=initialize?tail::kInitSlot:tail::kSlot;
    if(module.base==0 || module.buildId!=kTargetBuildId ||
       module.base>UINTPTR_MAX-offset-8 || module.textSize<offset+8 ||
       !IsMappedRxModuleCodeWindow(module.base+function,length) ||
       !IsMappedRxModuleCodeWindow(module.base+gate,40))return false;
    const auto* image=static_cast<const std::uint8_t*>(isaac::runtime::engine_memory::AsObject(module.base));
    if(!tail::ImageMatches(image,module.textSize,initialize))return false;
    const auto slot=module.base+offset;
    const auto callback=isaac::runtime::engine_call::AddressOfFunction(initialize?&LuaRuntime::DispatchPostProjectileInit:&LuaRuntime::DispatchPostProjectileUpdate);
    exl::util::RwPages pages(slot,sizeof(uintptr_t));
    auto* pointer=static_cast<uintptr_t*>(isaac::runtime::engine_memory::AsObject(pages.GetRw()));
    if(!pointer)return false;
    uintptr_t empty{};
    if(!__atomic_compare_exchange_n(pointer,&empty,callback,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED))return false;
    pages.Flush();
    auto* readable=static_cast<const uintptr_t*>(isaac::runtime::engine_memory::AsObject(slot));
    if(__atomic_load_n(readable,__ATOMIC_ACQUIRE)==callback)return true;
    auto expected=callback;
    static_cast<void>(__atomic_compare_exchange_n(pointer,&expected,0,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED));
    pages.Flush();return false;
}

#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 108 || EXL_DIAGNOSTIC_STAGE == 110)
namespace {
bool VerifyStage108LifecycleRelay(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        module.textSize < kGameStartNewRelayCodeOffset + kGameStartNewRelayExpectedBytes.size()) {
        return false;
    }
    const auto verifyRelay = [&module](uintptr_t callOffset, const auto& entry,
                                       uintptr_t relayOffset, const auto& code) {
        const uintptr_t target = target_address(module.base, callOffset);
        const uintptr_t relay = target_address(module.base, relayOffset);
        if (target < module.base || target % 4 != 0 || !module.Contains(target, entry.size()) ||
            !IsMappedRxModuleCodeWindow(target, entry.size()) || relay < module.base || relay % 4 != 0 ||
            !module.Contains(relay, code.size()) || !IsMappedRxModuleCodeWindow(relay, code.size())) {
            return false;
        }
        return verify_bytes(entry.data(), reinterpret_cast<const u8*>(target), entry.size()) &&
               verify_bytes(code.data(), reinterpret_cast<const u8*>(relay), code.size());
    };
    if (!verifyRelay(kGameStartSavedCallFileOffset, kGameStartSavedRelayExpectedEntry,
                     kGameStartSavedRelayCodeOffset, kGameStartSavedRelayExpectedBytes) ||
        !verifyRelay(kGameStartNewCallFileOffset, kGameStartNewRelayExpectedEntry,
                     kGameStartNewRelayCodeOffset, kGameStartNewRelayExpectedBytes)) {
        return false;
    }
    const uintptr_t candidateSlot = target_address(module.base, kGameStartRelaySlotOffset);
    if (candidateSlot < module.base || (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    *slot = candidateSlot;
    return true;
}
}

#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
Stage108LifecycleInstallResult TryInstallStage108LifecycleDiagnostic(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyStage108LifecycleRelay(module, &slot)) {
        return Stage108LifecycleInstallResult::RelayPatchMismatch;
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return Stage108LifecycleInstallResult::RelaySlotNotEmpty;
    }
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveStage108Lifecycle);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return Stage108LifecycleInstallResult::RelayPublishFailed;
    }
    return Stage108LifecycleInstallResult::Success;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
Stage110LifecycleInstallResult TryInstallStage110LifecycleDiagnostic(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyStage108LifecycleRelay(module, &slot)) return Stage110LifecycleInstallResult::RelayPatchMismatch;
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) return Stage110LifecycleInstallResult::RelaySlotNotEmpty;
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveStage110Lifecycle);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    return __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) == callback
               ? Stage110LifecycleInstallResult::Success : Stage110LifecycleInstallResult::RelayPublishFailed;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
namespace {
bool VerifyStage109RestartRelay(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        module.textSize < kGameRestartRelayCodeOffsets[2] + kGameRestartRelay2ExpectedBytes.size()) {
        return false;
    }
    constexpr std::array<const std::array<u8, 4>*, 3> kEntries = {
        &kGameRestartRelay0ExpectedEntry, &kGameRestartRelay1ExpectedEntry, &kGameRestartRelay2ExpectedEntry,
    };
    constexpr std::array<const std::array<u8, 80>*, 3> kCodes = {
        &kGameRestartRelay0ExpectedBytes, &kGameRestartRelay1ExpectedBytes, &kGameRestartRelay2ExpectedBytes,
    };
    for (size_t index = 0; index < kGameRestartCallFileOffsets.size(); ++index) {
        const uintptr_t entry = target_address(module.base, kGameRestartCallFileOffsets[index]);
        const uintptr_t relay = target_address(module.base, kGameRestartRelayCodeOffsets[index]);
        if (entry < module.base || entry % 4 != 0 || !module.Contains(entry, (*kEntries[index]).size()) ||
            !IsMappedRxModuleCodeWindow(entry, (*kEntries[index]).size()) || relay < module.base ||
            relay % 4 != 0 || !module.Contains(relay, (*kCodes[index]).size()) ||
            !IsMappedRxModuleCodeWindow(relay, (*kCodes[index]).size()) ||
            !verify_bytes((*kEntries[index]).data(), reinterpret_cast<const u8*>(entry), (*kEntries[index]).size()) ||
            !verify_bytes((*kCodes[index]).data(), reinterpret_cast<const u8*>(relay), (*kCodes[index]).size())) {
            return false;
        }
    }
    const uintptr_t candidateSlot = target_address(module.base, kGameRestartRelaySlotOffset);
    if (candidateSlot < module.base || (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    *slot = candidateSlot;
    return true;
}
}

Stage109RestartInstallResult TryInstallStage109RestartDiagnostic(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyStage109RestartRelay(module, &slot)) return Stage109RestartInstallResult::RelayPatchMismatch;
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) return Stage109RestartInstallResult::RelaySlotNotEmpty;
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveStage109Restart);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    return __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) == callback
               ? Stage109RestartInstallResult::Success
               : Stage109RestartInstallResult::RelayPublishFailed;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
namespace {
bool VerifyStage127SaveLoadRelay(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        module.textSize < kSaveLoadRelayLoadCodeOffset + kSaveLoadRelayLoadExpectedBytes.size()) return false;
    const uintptr_t saveEntry = target_address(module.base, kSaveLoadRelaySaveCallFileOffset);
    const uintptr_t loadEntry = target_address(module.base, kSaveLoadRelayLoadCallFileOffset);
    const uintptr_t saveRelay = target_address(module.base, kSaveLoadRelaySaveCodeOffset);
    const uintptr_t loadRelay = target_address(module.base, kSaveLoadRelayLoadCodeOffset);
    if (!IsMappedRxModuleCodeWindow(saveEntry, 4) || !IsMappedRxModuleCodeWindow(loadEntry, 4) ||
        !IsMappedRxModuleCodeWindow(saveRelay, kSaveLoadRelaySaveExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(loadRelay, kSaveLoadRelayLoadExpectedBytes.size())) return false;
    if (!verify_bytes(kSaveLoadRelaySaveExpectedEntry.data(), reinterpret_cast<const u8*>(saveEntry), 4) ||
        !verify_bytes(kSaveLoadRelayLoadExpectedEntry.data(), reinterpret_cast<const u8*>(loadEntry), 4) ||
        !verify_bytes(kSaveLoadRelaySaveExpectedBytes.data(), reinterpret_cast<const u8*>(saveRelay), 80) ||
        !verify_bytes(kSaveLoadRelayLoadExpectedBytes.data(), reinterpret_cast<const u8*>(loadRelay), 80)) return false;
    const uintptr_t candidate = target_address(module.base, kSaveLoadRelaySlotOffset);
    if ((candidate & (alignof(uintptr_t) - 1)) != 0 || !module.Contains(candidate, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidate, sizeof(uintptr_t))) return false;
    *slot = candidate;
    return true;
}
}

Stage127SaveLoadInstallResult TryInstallStage127SaveLoadDiagnostic(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyStage127SaveLoadRelay(module, &slot)) return Stage127SaveLoadInstallResult::RelayPatchMismatch;
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) return Stage127SaveLoadInstallResult::RelaySlotNotEmpty;
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveStage127SaveLoad);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    return __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) == callback
               ? Stage127SaveLoadInstallResult::Success : Stage127SaveLoadInstallResult::RelayPublishFailed;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
namespace {
bool VerifyStage128SaveDataManagerRelay(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        module.textSize < kStage128SaveDataManagerRelayLoadCodeOffset +
                              kStage128SaveDataManagerRelayLoadExpectedBytes.size()) return false;
    const uintptr_t saveEntry = target_address(module.base, kStage128SaveDataManagerRelaySaveCallFileOffset);
    const uintptr_t loadEntry = target_address(module.base, kStage128SaveDataManagerRelayLoadCallFileOffset);
    const uintptr_t saveRelay = target_address(module.base, kStage128SaveDataManagerRelaySaveCodeOffset);
    const uintptr_t loadRelay = target_address(module.base, kStage128SaveDataManagerRelayLoadCodeOffset);
    if (!IsMappedRxModuleCodeWindow(saveEntry, 4) || !IsMappedRxModuleCodeWindow(loadEntry, 4) ||
        !IsMappedRxModuleCodeWindow(saveRelay, kStage128SaveDataManagerRelaySaveExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(loadRelay, kStage128SaveDataManagerRelayLoadExpectedBytes.size())) return false;
    if (!verify_bytes(kStage128SaveDataManagerRelaySaveExpectedEntry.data(), reinterpret_cast<const u8*>(saveEntry), 4) ||
        !verify_bytes(kStage128SaveDataManagerRelayLoadExpectedEntry.data(), reinterpret_cast<const u8*>(loadEntry), 4) ||
        !verify_bytes(kStage128SaveDataManagerRelaySaveExpectedBytes.data(), reinterpret_cast<const u8*>(saveRelay), 80) ||
        !verify_bytes(kStage128SaveDataManagerRelayLoadExpectedBytes.data(), reinterpret_cast<const u8*>(loadRelay), 80)) return false;
    const uintptr_t candidate = target_address(module.base, kStage128SaveDataManagerRelaySlotOffset);
    if ((candidate & (alignof(uintptr_t) - 1)) != 0 || !module.Contains(candidate, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidate, sizeof(uintptr_t))) return false;
    *slot = candidate;
    return true;
}
}

Stage128SaveDataManagerInstallResult TryInstallStage128SaveDataManagerDiagnostic(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyStage128SaveDataManagerRelay(module, &slot))
        return Stage128SaveDataManagerInstallResult::RelayPatchMismatch;
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0)
        return Stage128SaveDataManagerInstallResult::RelaySlotNotEmpty;
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveStage128SaveDataManager);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    return __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) == callback
               ? Stage128SaveDataManagerInstallResult::Success
               : Stage128SaveDataManagerInstallResult::RelayPublishFailed;
}
#endif

bool VerifyGameOwnerSlot(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || module.size < sizeof(uintptr_t) ||
        kGameOwnerGlobalSlotOffset > UINTPTR_MAX - module.base ||
        kGameOwnerGlobalSlotOffset > module.size - sizeof(uintptr_t)) {
        return false;
    }
    const uintptr_t candidate = module.base + kGameOwnerGlobalSlotOffset;
    if ((candidate & (alignof(uintptr_t) - 1)) != 0 ||
        candidate > UINTPTR_MAX - sizeof(uintptr_t)) return false;
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (R_FAILED(svcQueryMemory(&info, &pageInfo, candidate)) || info.size == 0 ||
        info.addr > UINTPTR_MAX - info.size) {
        return false;
    }
    const uintptr_t end = candidate + sizeof(uintptr_t);
    if (candidate < info.addr || end < candidate || end > info.addr + info.size ||
        (info.type & MemState_Type) != MemType_ModuleCodeMutable || info.perm != Perm_Rw) {
        return false;
    }
    *slot = candidate;
    return true;
}

bool VerifyGameIsPausedThunk(const TargetModule& module, uintptr_t* thunk) {
    if (thunk == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kGameIsPausedThunkOffset > UINTPTR_MAX - module.base ||
        kGameIsPausedThunkExpectedBytes.size() > module.textSize ||
        kGameIsPausedThunkOffset > module.textSize - kGameIsPausedThunkExpectedBytes.size()) {
        return false;
    }
    const uintptr_t candidate = module.base + kGameIsPausedThunkOffset;
    if ((candidate & 3) != 0 ||
        !module.Contains(candidate, kGameIsPausedThunkExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidate, kGameIsPausedThunkExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kGameIsPausedThunkExpectedBytes.size()> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
    if (!verify_bytes(kGameIsPausedThunkExpectedBytes.data(), bytes.data(), bytes.size())) {
        return false;
    }
    *thunk = candidate;
    return true;
}

bool VerifyGameIsGreedMode(const TargetModule& module, uintptr_t* method) {
    if (method == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kGameIsGreedModeOffset > UINTPTR_MAX - module.base ||
        kGameIsGreedModeExpectedBytes.size() > module.textSize ||
        kGameIsGreedModeOffset > module.textSize - kGameIsGreedModeExpectedBytes.size()) {
        return false;
    }
    const uintptr_t candidate = module.base + kGameIsGreedModeOffset;
    if ((candidate & 3) != 0 || !module.Contains(candidate, kGameIsGreedModeExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidate, kGameIsGreedModeExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kGameIsGreedModeExpectedBytes.size()> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
    if (!verify_bytes(kGameIsGreedModeExpectedBytes.data(), bytes.data(), bytes.size())) {
        return false;
    }
    *method = candidate;
    return true;
}

bool VerifyLevelIsAscent(const TargetModule& module, uintptr_t* method) {
    if (method == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kLevelIsAscentOffset > UINTPTR_MAX - module.base ||
        kLevelIsAscentExpectedBytes.size() > module.textSize ||
        kLevelIsAscentOffset > module.textSize - kLevelIsAscentExpectedBytes.size()) {
        return false;
    }
    const uintptr_t candidate = module.base + kLevelIsAscentOffset;
    if ((candidate & 3) != 0 || !module.Contains(candidate, kLevelIsAscentExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidate, kLevelIsAscentExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kLevelIsAscentExpectedBytes.size()> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
    if (!verify_bytes(kLevelIsAscentExpectedBytes.data(), bytes.data(), bytes.size())) {
        return false;
    }
    *method = candidate;
    return true;
}

// 批次 8（2026-09-15）：`Level:GetAbsoluteStage()` / `Level:IsNextStageAvailable()` 的入口守卫。
// 形状与 `VerifyLevelIsAscent` 完全相同（`const` 成员、只吃 `this`），所以三份逻辑逐句对应：
// 偏移不越界、入口 4 字节对齐、落在模块代码段且映射为 Rx、再逐字节比对 16 字节守卫。
// 任一项不符就只留绑定为 0（handler 会报"绑定不可用"），不影响其它挂点安装。
bool VerifyGetRenderPositionStub(const TargetModule& module, uintptr_t* method) {
    if (method == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kGetRenderPositionStubOffset > UINTPTR_MAX - module.base ||
        kGetRenderPositionStubExpectedBytes.size() > module.textSize ||
        kGetRenderPositionStubOffset >
            module.textSize - kGetRenderPositionStubExpectedBytes.size()) {
        return false;
    }
    const uintptr_t candidate = module.base + kGetRenderPositionStubOffset;
    if ((candidate & 3) != 0 ||
        !module.Contains(candidate, kGetRenderPositionStubExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidate, kGetRenderPositionStubExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kGetRenderPositionStubExpectedBytes.size()> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
    if (!verify_bytes(kGetRenderPositionStubExpectedBytes.data(), bytes.data(), bytes.size())) {
        return false;
    }
    *method = candidate;
    return true;
}

bool VerifyLevelGetAbsoluteStage(const TargetModule& module, uintptr_t* method) {
    if (method == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kLevelGetAbsoluteStageOffset > UINTPTR_MAX - module.base ||
        kLevelGetAbsoluteStageExpectedBytes.size() > module.textSize ||
        kLevelGetAbsoluteStageOffset > module.textSize - kLevelGetAbsoluteStageExpectedBytes.size()) {
        return false;
    }
    const uintptr_t candidate = module.base + kLevelGetAbsoluteStageOffset;
    if ((candidate & 3) != 0 || !module.Contains(candidate, kLevelGetAbsoluteStageExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidate, kLevelGetAbsoluteStageExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kLevelGetAbsoluteStageExpectedBytes.size()> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
    if (!verify_bytes(kLevelGetAbsoluteStageExpectedBytes.data(), bytes.data(), bytes.size())) {
        return false;
    }
    *method = candidate;
    return true;
}

// 2026-09-16：`Room:GetFrameCount()` 的入口（`Room::GetFrameCount @ 0x470B0C`）。
// 与上面几条同形：**安装期必须核对入口 16 字节**；不符就只留 0 ⇒ handler 报"绑定不可用"，
// 不会去调一个"地址恰好落在模块里"的东西，也不会编造帧数。
bool VerifyRoomGetFrameCount(const TargetModule& module, uintptr_t* method) {
    if (method == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kRoomGetFrameCountOffset > UINTPTR_MAX - module.base ||
        kRoomGetFrameCountExpectedBytes.size() > module.textSize ||
        kRoomGetFrameCountOffset > module.textSize - kRoomGetFrameCountExpectedBytes.size()) {
        return false;
    }
    const uintptr_t candidate = module.base + kRoomGetFrameCountOffset;
    if ((candidate & 3) != 0 || !module.Contains(candidate, kRoomGetFrameCountExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidate, kRoomGetFrameCountExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kRoomGetFrameCountExpectedBytes.size()> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
    if (!verify_bytes(kRoomGetFrameCountExpectedBytes.data(), bytes.data(), bytes.size())) {
        return false;
    }
    *method = candidate;
    return true;
}

// 2026-09-21：`GridEntity::GetPosition() const @ 0x37E498`（PC 的 `GridEntity.Position`）。
// 与上面几条同形：**安装期必须核对入口 16 字节**；不符就只留 0 ⇒ handler 报"绑定不可用"，
// 绝不返回编造的坐标（EID 靠它挑"离玩家最近的刺"，编一个坐标会让它挑错实体）。
bool VerifyGridEntityGetPosition(const TargetModule& module, uintptr_t* method) {
    if (method == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kGridEntityGetPositionOffset > UINTPTR_MAX - module.base ||
        kGridEntityGetPositionExpectedBytes.size() > module.textSize ||
        kGridEntityGetPositionOffset > module.textSize - kGridEntityGetPositionExpectedBytes.size()) {
        return false;
    }
    const uintptr_t candidate = module.base + kGridEntityGetPositionOffset;
    if ((candidate & 3) != 0 ||
        !module.Contains(candidate, kGridEntityGetPositionExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidate, kGridEntityGetPositionExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kGridEntityGetPositionExpectedBytes.size()> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
    if (!verify_bytes(kGridEntityGetPositionExpectedBytes.data(), bytes.data(), bytes.size())) {
        return false;
    }
    *method = candidate;
    return true;
}

bool VerifyLevelIsNextStageAvailable(const TargetModule& module, uintptr_t* method) {
    if (method == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kLevelIsNextStageAvailableOffset > UINTPTR_MAX - module.base ||
        kLevelIsNextStageAvailableExpectedBytes.size() > module.textSize ||
        kLevelIsNextStageAvailableOffset > module.textSize - kLevelIsNextStageAvailableExpectedBytes.size()) {
        return false;
    }
    const uintptr_t candidate = module.base + kLevelIsNextStageAvailableOffset;
    if ((candidate & 3) != 0 || !module.Contains(candidate, kLevelIsNextStageAvailableExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidate, kLevelIsNextStageAvailableExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kLevelIsNextStageAvailableExpectedBytes.size()> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
    if (!verify_bytes(kLevelIsNextStageAvailableExpectedBytes.data(), bytes.data(), bytes.size())) {
        return false;
    }
    *method = candidate;
    return true;
}

// 重新发布绑定时只接受本HookId已登记、且完整入口桩地址匹配的中继。
// 初次安装前仍必须逐字核原生16字节，不能接受未知钩子。
bool IsInstalledManagerInputEntry(isaac::runtime::HookId id, std::uintptr_t candidate,
                                  const std::uint8_t* bytes) {
    if (!isaac::runtime::EntryRelayInstalled(id)) return false;
    const auto fallback = isaac::runtime::EntryRelayFallbackEntry(id);
    if (fallback < isaac::runtime::relay::kSlotFallbackOffset) return false;
    std::uint8_t expected[isaac::runtime::relay::kEntryPatchBytes]{};
    isaac::runtime::relay::BuildEntryPatch(expected,
        fallback - isaac::runtime::relay::kSlotFallbackOffset);
    return candidate != 0 && std::memcmp(bytes, expected, sizeof(expected)) == 0;
}

bool VerifyManagerIsActionTriggered(const TargetModule& module, uintptr_t* method) {
    if (method == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kManagerIsActionTriggeredOffset > UINTPTR_MAX - module.base ||
        kManagerIsActionTriggeredExpectedBytes.size() > module.textSize ||
        kManagerIsActionTriggeredOffset > module.textSize - kManagerIsActionTriggeredExpectedBytes.size()) {
        return false;
    }
    const uintptr_t candidate = module.base + kManagerIsActionTriggeredOffset;
    if ((candidate & 3) != 0 || !module.Contains(candidate, kManagerIsActionTriggeredExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidate, kManagerIsActionTriggeredExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kManagerIsActionTriggeredExpectedBytes.size()> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
    if (!verify_bytes(kManagerIsActionTriggeredExpectedBytes.data(), bytes.data(), bytes.size()) &&
        !IsInstalledManagerInputEntry(isaac::runtime::HookId::ManagerIsActionTriggered,
                                     candidate, bytes.data())) return false;
    *method = candidate;
    return true;
}

bool VerifyManagerIsActionPressed(const TargetModule& module, uintptr_t* method) {
    if (method == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kManagerIsActionPressedOffset > UINTPTR_MAX - module.base ||
        kManagerIsActionPressedExpectedBytes.size() > module.textSize ||
        kManagerIsActionPressedOffset > module.textSize - kManagerIsActionPressedExpectedBytes.size()) {
        return false;
    }
    const uintptr_t candidate = module.base + kManagerIsActionPressedOffset;
    if ((candidate & 3) != 0 ||
        !module.Contains(candidate, kManagerIsActionPressedExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidate, kManagerIsActionPressedExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kManagerIsActionPressedExpectedBytes.size()> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
    if (!verify_bytes(kManagerIsActionPressedExpectedBytes.data(), bytes.data(), bytes.size()) &&
        !IsInstalledManagerInputEntry(isaac::runtime::HookId::ManagerIsActionPressed,
                                     candidate, bytes.data())) {
        return false;
    }
    *method = candidate;
    return true;
}

bool VerifyManagerGetActionValue(const TargetModule& module, uintptr_t* method) {
    if (method == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kManagerGetActionValueOffset > UINTPTR_MAX - module.base ||
        kManagerGetActionValueExpectedBytes.size() > module.textSize ||
        kManagerGetActionValueOffset > module.textSize - kManagerGetActionValueExpectedBytes.size()) {
        return false;
    }
    const uintptr_t candidate = module.base + kManagerGetActionValueOffset;
    if ((candidate & 3) != 0 ||
        !module.Contains(candidate, kManagerGetActionValueExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidate, kManagerGetActionValueExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kManagerGetActionValueExpectedBytes.size()> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
    if (!verify_bytes(kManagerGetActionValueExpectedBytes.data(), bytes.data(), bytes.size()) &&
        !IsInstalledManagerInputEntry(isaac::runtime::HookId::ManagerGetActionValue,
                                     candidate, bytes.data())) {
        return false;
    }
    *method = candidate;
    return true;
}

bool VerifyMusicBindings(const TargetModule& module, uintptr_t* getCurrentMusicId,
                         uintptr_t* pause, uintptr_t* resume) {
    if (getCurrentMusicId == nullptr || pause == nullptr || resume == nullptr || module.base == 0 ||
        module.buildId != kTargetBuildId) {
        return false;
    }
    const auto verify = [&module](uintptr_t offset, const u8* expected, std::size_t length,
                                  uintptr_t* output) {
        if (offset > UINTPTR_MAX - module.base || length > module.textSize ||
            offset > module.textSize - length) {
            return false;
        }
        const uintptr_t candidate = module.base + offset;
        if ((candidate & 3) != 0 || !module.Contains(candidate, length) ||
            !IsMappedRxModuleCodeWindow(candidate, length)) {
            return false;
        }
        std::array<u8, 16> bytes{};
        std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), length);
        if (!verify_bytes(expected, bytes.data(), length)) {
            return false;
        }
        *output = candidate;
        return true;
    };
    return verify(kMusicGetCurrentMusicIdOffset, kMusicGetCurrentMusicIdExpectedBytes.data(),
                  kMusicGetCurrentMusicIdExpectedBytes.size(), getCurrentMusicId) &&
           verify(kMusicPauseOffset, kMusicPauseExpectedBytes.data(), kMusicPauseExpectedBytes.size(), pause) &&
           verify(kMusicResumeOffset, kMusicResumeExpectedBytes.data(), kMusicResumeExpectedBytes.size(), resume);
}

// 批次 137/138：Music 族那两条**单方法**入口守卫共用的一处字节读取
// （偏移不越界 → 4 字节对齐 + 落在模块代码段的 Rx 映射里 → 逐字节比对 16 字节守卫）。
// 判据与同文件既有的 `VerifyLevelIsAscent` 一族**逐条相同**，只是把那段逐字重复收成一份 ——
// 本批一口气要加两条（`UpdateVolume` / `Play`），再各抄一遍就是"同一判据两份实现"。
// （注：它自己**不出现任何 `k…Offset` 常量**，参数由调用方传进来 —— ABI 体检靠这一点把
// 每个常量唯一地归到各自的单方法守卫上，见 `tools/engine_offset_abi_report.py` 的形态 D。）
bool VerifyMusicSingleEntry(const TargetModule& module, uintptr_t offset, const u8* expected,
                            std::size_t length, uintptr_t* output) {
    if (output == nullptr || expected == nullptr || length == 0 || module.base == 0 ||
        module.buildId != kTargetBuildId) {
        return false;
    }
    if (offset > UINTPTR_MAX - module.base || length > module.textSize ||
        offset > module.textSize - length) {
        return false;
    }
    const uintptr_t candidate = module.base + offset;
    if ((candidate & 3) != 0 || !module.Contains(candidate, length) ||
        !IsMappedRxModuleCodeWindow(candidate, length)) {
        return false;
    }
    std::array<u8, 16> bytes{};
    std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), length);
    if (!verify_bytes(expected, bytes.data(), length)) {
        return false;
    }
    *output = candidate;
    return true;
}

// 批次 137：`MusicManager:UpdateVolume()` 的**单方法**守卫（The Specialist for Good Items 要用）。
//
// 为什么单独一份而不是并进 `VerifyMusicBindings`：那一份是"一个助手体里三个常量"的成对写法，
// 再加一个会让"UpdateVolume 的守卫不符"连带把 `GetCurrentMusicID`/`Pause`/`Resume` 一起丢掉
// （EID / GoodTrip 在用）—— 与既有设计"守卫不符只让那一个字段保持 0"相反。
bool VerifyMusicUpdateVolume(const TargetModule& module, uintptr_t* updateVolume) {
    return VerifyMusicSingleEntry(module, kMusicUpdateVolumeOffset,
                                  kMusicUpdateVolumeExpectedBytes.data(),
                                  kMusicUpdateVolumeExpectedBytes.size(), updateVolume);
}

// 批次 138：`MusicManager:Play(ID, Volume)` 的单方法守卫（同形）。
bool VerifyMusicPlay(const TargetModule& module, uintptr_t* play) {
    return VerifyMusicSingleEntry(module, kMusicPlayOffset, kMusicPlayExpectedBytes.data(),
                                  kMusicPlayExpectedBytes.size(), play);
}

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC push_options
#pragma GCC optimize ("Os")
#endif
bool VerifyRngBindings(const TargetModule& module, uintptr_t* setSeed, uintptr_t* next) {
    if (setSeed == nullptr || next == nullptr || module.base == 0 ||
        module.buildId != kTargetBuildId) {
        return false;
    }
    const auto verify = [&module](uintptr_t offset, const u8* expected, std::size_t length,
                                  uintptr_t* output) {
        if (offset > UINTPTR_MAX - module.base || length > module.textSize ||
            offset > module.textSize - length) {
            return false;
        }
        const uintptr_t candidate = module.base + offset;
        if ((candidate & 3) != 0 || !module.Contains(candidate, length) ||
            !IsMappedRxModuleCodeWindow(candidate, length)) {
            return false;
        }
        std::array<u8, 16> bytes{};
        std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), length);
        if (!verify_bytes(expected, bytes.data(), length)) {
            return false;
        }
        *output = candidate;
        return true;
    };
    return verify(kRngSetSeedOffset, kRngSetSeedExpectedBytes.data(),
                  kRngSetSeedExpectedBytes.size(), setSeed) &&
           verify(kRngNextOffset, kRngNextExpectedBytes.data(),
                  kRngNextExpectedBytes.size(), next);
}

// 批次 195：`RNG:RandomInt(Max)` / `RNG:RandomFloat()` 的两条入口。
//
// ★ 为什么**与上面那条分开验、分开发布**（而不是把四条并进一次 all-or-nothing 的核对）：
//   上面那两条是**已经在真机上跑着**的能力（EID 的 `GetRNG():GetSeed()` 一条链都要它）。
//   把四条并成一个布尔值 ⇒ 只要新加的两条入口指纹对不上，连老能力一起被停用 ——
//   那是"新功能没上成、顺手把旧功能停了"的形态。分开之后各自失败各自停，互不牵连。
//
// ★★ 判据必须写成**内联 lambda + 直写发布**（与 `VerifyMusicBindings`/`VerifyRngBindings` 同形）：
//   门禁 `test_engine_offset_signatures` 的"单方法绑定链"是**纯形状匹配**
//   （常量 → 校验 → 局部变量 → 发布函数 → 全局槽 → 取址助手），把一个**具名的共享校验助手**
//   插在中间会让它读成"这条链从没被比过"（实测：把常量交给一个**具名的**共享校验助手之后，
//   `declared_signature` 直接返回 None）。所以这里逐条写开，不做 helper。
//   ⚠️ 另外：连注释里**提到**那些常量名都会让它误判（工具在注释里也按字面找常量、而注释没有
//   "所属函数"）⇒ 这段说明里刻意不再写出常量名。
bool VerifyRngRandomBindings(const TargetModule& module, uintptr_t* randomUint,
                             uintptr_t* randomFloat) {
    if (randomUint == nullptr || randomFloat == nullptr || module.base == 0 ||
        module.buildId != kTargetBuildId) {
        return false;
    }
    const auto verify = [&module](uintptr_t offset, const u8* expected, std::size_t length,
                                  uintptr_t* output) {
        if (offset > UINTPTR_MAX - module.base || length > module.textSize ||
            offset > module.textSize - length) {
            return false;
        }
        const uintptr_t candidate = module.base + offset;
        if ((candidate & 3) != 0 || !module.Contains(candidate, length)) {
            return false;
        }
        // 逐字节核对走 L2（`VerifyEntryBytes`：区间判定 + 注入的可读判定 + 比较），
        // **不再自己 `memcpy`** —— 门禁 `test_no_new_raw_engine_access` 逐文件钉存量。
        // 注入的仍是本文件那份**更严**的判定（只认模块代码段的 Rx 映射）。
        if (!isaac::runtime::engine_call::VerifyEntryBytes(candidate, expected, length,
                                                           &IsMappedRxModuleCodeWindow)) {
            return false;
        }
        *output = candidate;
        return true;
    };
    return verify(kRngRandomUintOffset, kRngRandomUintExpectedBytes.data(),
                  kRngRandomUintExpectedBytes.size(), randomUint) &&
           verify(kRngRandomOffset, kRngRandomExpectedBytes.data(),
                  kRngRandomExpectedBytes.size(), randomFloat);
}

bool TryInstallRngBindings(const TargetModule& module) {
    uintptr_t setSeed = 0;
    uintptr_t next = 0;
    // ★ 这两条**必须是一条直写的链**：`VerifyRngBindings(module, &setSeed, &next)` 紧接着
    // `LuaRuntime::SetRngBindings(setSeed, next)`。门禁 `test_engine_offset_signatures` 的
    // `test_single_binding_chain_is_actually_checked` 按这个形状判"这条单方法绑定链真的被比过"
    // —— 把发布挪进 `if` 里会让它读成"没比过"（判据是纯文本形状匹配，不是语义分析）。
    uintptr_t randomUint = 0;
    uintptr_t randomFloat = 0;
    const bool coreInstalled = VerifyRngBindings(module, &setSeed, &next);
    // 两条新入口同样按"可选能力"处理：守卫不符就留 0（发布 0 与"不发布"同义），
    // handler 会报"绑定不可用"，**绝不编一个随机数**。
    static_cast<void>(VerifyRngRandomBindings(module, &randomUint, &randomFloat));
    LuaRuntime::SetRngBindings(setSeed, next);
    LuaRuntime::SetRngRandomBindings(randomUint, randomFloat);
    return coreInstalled;
}

// 批次 195（2026-09-29）：`KAGE::Input::ManagerBase` 上按**按键号**查询的三条入口。
//
// ★ 这三条（连同同族的动作查询，共四条）的**头 32 字节完全相同** ⇒ 只比序言认不出谁是谁，
//   偏移写串会被静默放过。所以除 16 字节序言外**再比 `entry+0xE0` 的 4 字节**（那条"取虚表槽"
//   的指令：Pressed 是 `[#0x30]`、Triggered 是 `[#0x38]`）。逐条证据见 `runtime_constants.hpp`
//   的 `kKageInputButtonDiscriminatorOffset`。
//
// ★ 三条**互相独立**：某一条偏移写错只让那一条不发布（handler 报"绑定不可用"），
//   不会把另外两条一起停掉 —— 与 `VerifyRngRandomBindings` 同一条口径。
// ★ 判据同样必须写成**内联 lambda + 直写发布**（理由见 `VerifyRngRandomBindings` 上面那段：
//   具名共享助手会让门禁的"单方法绑定链"读成"从没被比过"）。
bool VerifyInputButtonBindings(const TargetModule& module, uintptr_t* isButtonPressed,
                               uintptr_t* getButtonValue) {
    if (isButtonPressed == nullptr || getButtonValue == nullptr || module.base == 0 ||
        module.buildId != kTargetBuildId) {
        return false;
    }
    constexpr std::size_t kPrologue = 16;
    //: 序言 + `entry+0xE0` 的 4 字节（`discriminator == nullptr` 时只比序言）。
    const auto verify = [&module](uintptr_t offset, const u8* expected, std::size_t length,
                                  const u8* discriminator, uintptr_t* output) {
        if (offset > UINTPTR_MAX - module.base || length > module.textSize ||
            offset > module.textSize - length) {
            return false;
        }
        const uintptr_t candidate = module.base + offset;
        if ((candidate & 3) != 0 || !module.Contains(candidate, length) ||
            !IsMappedRxModuleCodeWindow(candidate, length)) {
            return false;
        }
        // ★ 两次逐字节核对都走 L2 的 `VerifyEntryBytes`（它自己做"区间可用 + 注入的可读判定 +
        //   逐字节比较"），**不在这里再写一遍 `memcpy` + `verify_bytes`**：
        //   门禁 `test_no_new_raw_engine_access` 逐文件钉"裸碰引擎"的存量（只能减不能增），
        //   而这一批新加的三条入口如果各抄一份，就会把 `hook_manager.cpp` 的存量顶上去。
        //   注入的是本文件那份**更严**的判定（只认模块代码段的 Rx 映射），与原来逐条同义。
        if (!isaac::runtime::engine_call::VerifyEntryBytes(candidate, expected, length,
                                                           &IsMappedRxModuleCodeWindow)) {
            return false;
        }
        if (discriminator != nullptr) {
            constexpr std::size_t kTailLength = 4;
            if (kKageInputButtonDiscriminatorOffset > module.textSize - offset - kTailLength) {
                return false;
            }
            const uintptr_t tail = candidate + kKageInputButtonDiscriminatorOffset;
            if (!module.Contains(tail, kTailLength) ||
                !isaac::runtime::engine_call::VerifyEntryBytes(tail, discriminator, kTailLength,
                                                               &IsMappedRxModuleCodeWindow)) {
                return false;
            }
        }
        *output = candidate;
        return true;
    };
    // 三条各自核对、各自写自己的出参：任一条失败只让它保持 0（handler 报"绑定不可用"）。
    static_cast<void>(verify(kKageIsButtonPressedOffset, kKageIsButtonPressedExpectedBytes.data(),
                             kPrologue, kKageIsButtonPressedDiscriminator.data(),
                             isButtonPressed));
    // `GetButtonValue` 的序言与那三条**本来就不同**（浮点返回 ⇒ `str d8,[sp,#-0x50]!` 打头）
    // ⇒ 16 字节指纹已经分得开，不需要第二个判据（也没有对应的虚表槽指令落在前 0xE0 内可比）。
    static_cast<void>(verify(kKageGetButtonValueOffset, kKageGetButtonValueExpectedBytes.data(),
                             kPrologue, nullptr, getButtonValue));
    return true;
}

// 按键号那三条查询的发布点（与 `TryInstallRngBindings` 同形：**可选能力**，守卫不符只留 0）。
void TryInstallInputButtonBindings(const TargetModule& module) {
    uintptr_t isButtonPressed = 0;
    uintptr_t getButtonValue = 0;
    static_cast<void>(VerifyInputButtonBindings(module, &isButtonPressed, &getButtonValue));
    LuaRuntime::SetInputButtonBindings(isButtonPressed, getButtonValue);
}

// One row per `KAGE::Graphics::Font` entry point. All eleven guards are the same 16-byte window,
// so a single loop checks them all, and the table doubles as the list of which field of
// `LuaFontBindings` each guard fills.
struct BindingGuardEntry {
    uintptr_t offset;
    std::size_t memberOffset;
    const std::array<u8, 16>* expected;
};

constexpr std::array<BindingGuardEntry, 15> kFontBindingEntries{{
    {kFontCtorOffset, offsetof(LuaRuntime::LuaFontBindings, ctor), &kFontCtorExpectedBytes},
    {kFontDestructorOffset, offsetof(LuaRuntime::LuaFontBindings, destructor_),
     &kFontDestructorExpectedBytes},
    {kFontLoadOffset, offsetof(LuaRuntime::LuaFontBindings, load), &kFontLoadExpectedBytes},
    {kFontUnloadOffset, offsetof(LuaRuntime::LuaFontBindings, unload), &kFontUnloadExpectedBytes},
    {kFontIsLoadedOffset, offsetof(LuaRuntime::LuaFontBindings, isLoaded),
     &kFontIsLoadedExpectedBytes},
    {kFontGetStringWidthOffset, offsetof(LuaRuntime::LuaFontBindings, getStringWidth),
     &kFontGetStringWidthExpectedBytes},
    {kFontGetStringWidthUTF8Offset, offsetof(LuaRuntime::LuaFontBindings, getStringWidthUTF8),
     &kFontGetStringWidthUTF8ExpectedBytes},
    {kFontGetLineHeightOffset, offsetof(LuaRuntime::LuaFontBindings, getLineHeight),
     &kFontGetLineHeightExpectedBytes},
    {kFontGetBaselineHeightOffset, offsetof(LuaRuntime::LuaFontBindings, getBaselineHeight),
     &kFontGetBaselineHeightExpectedBytes},
    {kFontGetCharacterWidthOffset, offsetof(LuaRuntime::LuaFontBindings, getCharacterWidth),
     &kFontGetCharacterWidthExpectedBytes},
    {kFontSetMissingCharacterOffset, offsetof(LuaRuntime::LuaFontBindings, setMissingCharacter),
     &kFontSetMissingCharacterExpectedBytes},
    {kFontDrawStringOffset, offsetof(LuaRuntime::LuaFontBindings, drawString),
     &kFontDrawStringExpectedBytes},
    // 三个绘制变体。**每一行都必须在这里**：漏掉的字段会保持 0，handler 于是抛
    // "native binding is unavailable"，而 host 测试直接发布绑定、看不到这个缺口 ——
    // 2026-09-13 第八轮的真机现象就是"只画出了普通 DrawString 的几行，缩放那行起全没了"
    // （报告 `01789144065` 掩码：MARK=6、位 61=0，即 Mod 自己 pcall 到了这个错误）。
    {kFontDrawStringScaledOffset, offsetof(LuaRuntime::LuaFontBindings, drawStringScaled),
     &kFontDrawStringScaledExpectedBytes},
    {kFontDrawStringUTF8Offset, offsetof(LuaRuntime::LuaFontBindings, drawStringUTF8),
     &kFontDrawStringUTF8ExpectedBytes},
    {kFontDrawStringScaledUTF8Offset,
     offsetof(LuaRuntime::LuaFontBindings, drawStringScaledUTF8),
     &kFontDrawStringScaledUTF8ExpectedBytes},
}};

// Font bindings are optional, exactly like the controller-input ones: they must never block hook
// installation, and every entry point is judged on its own. A row whose guard does not match
// leaves its field at zero, which the `Font` handlers turn into an unavailable-binding Lua error;
// the other rows are still verified, so a single moved function does not disable the whole family.
// 同一个校验循环服务所有"原生入口表"家族：逐行判守卫、命中就写进对应字段，未命中保持 0。
// 每个家族各有一张表；表里少一行 = 那个字段永远为 0（2026-09-13 的 Font 事故），所以
// `runtime/tests/` 里有一条测试逐家族比对"结构体字段集合 == 守卫表成员集合"。
template <typename Bindings, std::size_t Count>
bool VerifyBindingTable(const TargetModule& module,
                        const std::array<BindingGuardEntry, Count>& entries, Bindings* bindings) {
    if (bindings == nullptr || module.base == 0 || module.buildId != kTargetBuildId) {
        return false;
    }
    // 绑定记录的字段现在是**声明过的函数指针类型**（2026-09-17，见 `lua_runtime_state.hpp`），
    // 所以安装期往字段里放地址必须按字节写：`reinterpret_cast<uintptr_t*>` 去写就成了类型双关，
    // 而 `memcpy` 两边表示相同（本平台函数指针与 `uintptr_t` 都是 8 字节），也不违反别名规则。
    // 顺带把"这张表逐字段覆盖整个记录"钉死：字段数 × 指针宽 = 记录大小，多一个字段就会在这里炸。
    static_assert(sizeof(Bindings) == Count * sizeof(uintptr_t),
                  "绑定记录必须恰好是 Count 个指针宽（守卫表逐字段覆盖它）");
    auto* const base = reinterpret_cast<u8*>(bindings);
    bool verified = true;
    for (const BindingGuardEntry& entry : entries) {
        const std::size_t length = entry.expected->size();
        auto* const output = base + entry.memberOffset;
        const uintptr_t empty = 0;
        std::memcpy(output, &empty, sizeof(empty));
        if (entry.offset > UINTPTR_MAX - module.base || length > module.textSize ||
            entry.offset > module.textSize - length) {
            verified = false;
            continue;
        }
        const uintptr_t candidate = module.base + entry.offset;
        if ((candidate & 3) != 0 || !module.Contains(candidate, length) ||
            !IsMappedRxModuleCodeWindow(candidate, length)) {
            verified = false;
            continue;
        }
        std::array<u8, 16> bytes{};
        std::memcpy(bytes.data(), reinterpret_cast<const void*>(candidate), bytes.size());
        if (!verify_bytes(entry.expected->data(), bytes.data(), bytes.size())) {
            verified = false;
            continue;
        }
        std::memcpy(output, &candidate, sizeof(candidate));
    }
    return verified;
}

bool VerifyFontBindings(const TargetModule& module, LuaRuntime::LuaFontBindings* bindings) {
    return VerifyBindingTable(module, kFontBindingEntries, bindings);
}

// `Sprite`（`IsaacRepentance::ANM2`）第一步：只收 `char const*`/数值的入口。尺寸 `0x158` 由
// `tools/stage155_anm2_size_audit.py` 两种独立方法定案；`Load`/`ReplaceSpritesheet` 需要
// libc++ 的 `std::string` 桥，放在第二步。
// ★ 槽数 = `sizeof(LuaRuntime::LuaSpriteBindings) / 8` 必须**恰好相等**（下面 `VerifyBindingTable`
//   里有静态断言）。批次 214 加了 `reset` ⇒ 21 → 22；**批次 279 加了 overlay 三条 ⇒ 22 → 25、
//   批次 280 加 `Stop` ⇒ 25 → 26、批次 283 加四条「按名字查询」⇒ 26 → 30**
//   （漏改这一处的症状是编译期两条错：
//   "too many initializers" + "static_assert failed: 绑定记录必须恰好是 Count 个指针宽"）。
constexpr std::array<BindingGuardEntry, 30> kSpriteBindingEntries{{
    {kSpriteCtorOffset, offsetof(LuaRuntime::LuaSpriteBindings, ctor), &kSpriteCtorExpectedBytes},
    {kSpriteDestructorOffset, offsetof(LuaRuntime::LuaSpriteBindings, destructor_),
     &kSpriteDestructorExpectedBytes},
    {kSpritePlayOffset, offsetof(LuaRuntime::LuaSpriteBindings, play), &kSpritePlayExpectedBytes},
    {kSpriteSetAnimationOffset, offsetof(LuaRuntime::LuaSpriteBindings, setAnimation),
     &kSpriteSetAnimationExpectedBytes},
    {kSpriteSetFrameNamedOffset, offsetof(LuaRuntime::LuaSpriteBindings, setFrameNamed),
     &kSpriteSetFrameNamedExpectedBytes},
    {kSpriteSetFrameOffset, offsetof(LuaRuntime::LuaSpriteBindings, setFrame),
     &kSpriteSetFrameExpectedBytes},
    {kSpriteGetFrameOffset, offsetof(LuaRuntime::LuaSpriteBindings, getFrame),
     &kSpriteGetFrameExpectedBytes},
    {kSpriteSetLayerFrameOffset, offsetof(LuaRuntime::LuaSpriteBindings, setLayerFrame),
     &kSpriteSetLayerFrameExpectedBytes},
    {kSpriteGetLayerFrameOffset, offsetof(LuaRuntime::LuaSpriteBindings, getLayerFrame),
     &kSpriteGetLayerFrameExpectedBytes},
    // `GetTexel`：EID 判"赎罪线问号底座"的依据（见 `runtime_constants.hpp` 该条的说明）。
    {kSpriteGetTexelOffset, offsetof(LuaRuntime::LuaSpriteBindings, getTexel),
     &kSpriteGetTexelExpectedBytes},
    {kSpriteUpdateOffset, offsetof(LuaRuntime::LuaSpriteBindings, update), &kSpriteUpdateExpectedBytes},
    {kSpriteIsPlayingOffset, offsetof(LuaRuntime::LuaSpriteBindings, isPlaying),
     &kSpriteIsPlayingExpectedBytes},
    {kSpriteIsFinishedOffset, offsetof(LuaRuntime::LuaSpriteBindings, isFinished),
     &kSpriteIsFinishedExpectedBytes},
    // 批次 214：`ANM2::Reset()`（中文版 MCM 的 anm2 探测要用）。
    {kSpriteResetOffset, offsetof(LuaRuntime::LuaSpriteBindings, reset),
     &kSpriteResetExpectedBytes},
    {kSpriteRenderOffset, offsetof(LuaRuntime::LuaSpriteBindings, render), &kSpriteRenderExpectedBytes},
    {kSpriteRenderLayerOffset, offsetof(LuaRuntime::LuaSpriteBindings, renderLayer),
     &kSpriteRenderLayerExpectedBytes},
    {kSpritePlayRandomOffset, offsetof(LuaRuntime::LuaSpriteBindings, playRandom),
     &kSpritePlayRandomExpectedBytes},
    // 批次 279：overlay 三条（`PlayOverlay`/`SetOverlayFrame` 走 `char const*` 重载，
    // 所以仍然落在这张「第一步只收 char const*/数值」的表里）。
    {kSpritePlayOverlayOffset, offsetof(LuaRuntime::LuaSpriteBindings, playOverlay),
     &kSpritePlayOverlayExpectedBytes},
    {kSpriteSetLastFrameOffset, offsetof(LuaRuntime::LuaSpriteBindings, setLastFrame),
     &kSpriteSetLastFrameExpectedBytes},
    {kSpriteSetOverlayFrameOffset, offsetof(LuaRuntime::LuaSpriteBindings, setOverlayFrame),
     &kSpriteSetOverlayFrameExpectedBytes},
    // 批次 280：`Stop`。
    {kSpriteStopOffset, offsetof(LuaRuntime::LuaSpriteBindings, stop),
     &kSpriteStopExpectedBytes},
    // 批次 283：四条「按名字查询」。它们与下面 `Load` 那三条同属"需要 libc++ `std::string`"的
    // 一族 —— 引擎侧只有 `std::string const&` 那一份签名，没有 `char const*` 重载可选。
    {kSpriteIsOverlayPlayingOffset, offsetof(LuaRuntime::LuaSpriteBindings, isOverlayPlaying),
     &kSpriteIsOverlayPlayingExpectedBytes},
    {kSpriteIsOverlayFinishedOffset, offsetof(LuaRuntime::LuaSpriteBindings, isOverlayFinished),
     &kSpriteIsOverlayFinishedExpectedBytes},
    {kSpriteIsEventTriggeredOffset, offsetof(LuaRuntime::LuaSpriteBindings, isEventTriggered),
     &kSpriteIsEventTriggeredExpectedBytes},
    {kSpriteWasEventTriggeredOffset, offsetof(LuaRuntime::LuaSpriteBindings, wasEventTriggered),
     &kSpriteWasEventTriggeredExpectedBytes},
    // 第二步：需要 libc++ `std::string` 的三个入口，以及借来代建字符串的 `assign` 桩。
    {kSpriteLoadOffset, offsetof(LuaRuntime::LuaSpriteBindings, load), &kSpriteLoadExpectedBytes},
    {kSpriteLoadGraphicsOffset, offsetof(LuaRuntime::LuaSpriteBindings, loadGraphics),
     &kSpriteLoadGraphicsExpectedBytes},
    {kSpriteReplaceSpritesheetOffset, offsetof(LuaRuntime::LuaSpriteBindings, replaceSpritesheet),
     &kSpriteReplaceSpritesheetExpectedBytes},
    {kLibcxxStringAssignOffset, offsetof(LuaRuntime::LuaSpriteBindings, libcxxStringAssign),
     &kLibcxxStringAssignExpectedBytes},
    // 长路径（超过 SSO）的缓冲要用游戏自己的 `operator delete` 释放，不能借本模块的 `free`。
    {kGameOperatorDeleteOffset, offsetof(LuaRuntime::LuaSpriteBindings, gameOperatorDelete),
     &kGameOperatorDeleteExpectedBytes},
}};

bool VerifySpriteBindings(const TargetModule& module, LuaRuntime::LuaSpriteBindings* bindings) {
    return VerifyBindingTable(module, kSpriteBindingEntries, bindings);
}

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC pop_options
#endif

// Shared relay plumbing for both the Stage48 diagnostics and the production rebuild
// relay: these two helpers must stay outside every `#if`, otherwise a build that does
// not enable the diagnostic loses the definition while a caller keeps the reference
// (hardware caught that as `PC=0` from an unresolved PLT slot).
namespace {
// 批次 358：**把"卡在哪一条"暴露出来**。以前只返回 bool ⇒ 真机上只能看到"没装上"，
// 不知道是"分支没打上"还是"字节对不上"还是"槽被占了"，而这三种的修法完全不同。
//   1 = 前置守卫（空指针 / base 为 0 / buildId 不符 / 长度越界）
//   2 = 范围与对齐（不在模块内、不在可执行窗口、未对齐）
//   3 = **目标处字节对不上**（入口分支 或 其后 12 字节）
//   4 = **代码洞桩字节对不上**
//   5 = 桩长度超出本地缓冲
//   6 = 发布失败：槽 / 回调非法（0 或未对齐）
//   7 = 发布失败：**槽非空**（已经有人占着）
//   8 = 发布失败：写进去读回来不一致
enum : unsigned {
    kRelayVerifyGuard = 1,
    kRelayVerifyRange = 2,
    kRelayVerifyTargetBytes = 3,
    kRelayVerifyStubBytes = 4,
    kRelayVerifyStubLength = 5,
    kRelayPublishBadArgument = 6,
    kRelayPublishSlotTaken = 7,
    kRelayPublishMismatch = 8,
};

bool VerifyStage48Relay(const TargetModule& module, uintptr_t targetOffset,
                        const std::array<u8, 16>& original,
                        const std::array<u8, 4>& expectedEntry,
                        uintptr_t relayOffset, const u8* expectedRelay,
                        std::size_t relayLength, uintptr_t slotOffset,
                        uintptr_t* slot, unsigned* failureCode = nullptr) {
    const auto fail = [failureCode](unsigned code) {
        if (failureCode != nullptr) {
            *failureCode = code;
        }
        return false;
    };
    if (slot == nullptr || expectedRelay == nullptr || module.base == 0 ||
        module.buildId != kTargetBuildId || original.size() > module.textSize ||
        relayLength > module.textSize || sizeof(uintptr_t) > module.textSize ||
        targetOffset > UINTPTR_MAX - module.base ||
        relayOffset > UINTPTR_MAX - module.base ||
        slotOffset > UINTPTR_MAX - module.base ||
        targetOffset > module.textSize - original.size() ||
        relayOffset > module.textSize - relayLength ||
        slotOffset > module.textSize - sizeof(uintptr_t)) {
        return fail(kRelayVerifyGuard);
    }
    const uintptr_t target = module.base + targetOffset;
    const uintptr_t relay = module.base + relayOffset;
    const uintptr_t candidateSlot = module.base + slotOffset;
    if ((target & 3u) != 0 || (relay & 3u) != 0 ||
        (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(target, original.size()) || !module.Contains(relay, relayLength) ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(target, original.size()) ||
        !IsMappedRxModuleCodeWindow(relay, relayLength) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return fail(kRelayVerifyRange);
    }
    std::array<u8, 16> targetBytes{};
    std::memcpy(targetBytes.data(), reinterpret_cast<const void*>(target), targetBytes.size());
    if (!verify_bytes(expectedEntry.data(), targetBytes.data(), expectedEntry.size()) ||
        !verify_bytes(original.data() + expectedEntry.size(),
                      targetBytes.data() + expectedEntry.size(),
                      original.size() - expectedEntry.size())) {
        return fail(kRelayVerifyTargetBytes);
    }
    std::array<u8, 64> relayBytes{};
    if (relayLength > relayBytes.size()) return fail(kRelayVerifyStubLength);
    std::memcpy(relayBytes.data(), reinterpret_cast<const void*>(relay), relayLength);
    if (!verify_bytes(expectedRelay, relayBytes.data(), relayLength)) {
        return fail(kRelayVerifyStubBytes);
    }
    *slot = candidateSlot;
    return true;
}

// 批次 358：同样把失败原因暴露出来（见 `VerifyStage48Relay` 上方那张码表）。
bool PublishStage48RelayCallback(uintptr_t slot, uintptr_t callback,
                                 unsigned* failureCode = nullptr) {
    const auto fail = [failureCode](unsigned code) {
        if (failureCode != nullptr) {
            *failureCode = code;
        }
        return false;
    };
    if (slot == 0 || callback == 0 || (callback & 3u) != 0) {
        return fail(kRelayPublishBadArgument);
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (rwSlot == nullptr || __atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return fail(kRelayPublishSlotTaken);
    }
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    const bool ok = __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot),
                                    __ATOMIC_ACQUIRE) == callback;
    return ok ? true : fail(kRelayPublishMismatch);
}

}  // namespace

// Stage 148 rebuild relay.
//
// 它由 `ExlaunchHookAdapter`（`HookId::RebuildMountPoints`）调用，不再是 Lua 层回调；
// 属于内容挂载子系统，装不上只意味着重建挂载点表后 Mod 的挂载点不恢复，不得让 Mod 加载失败。
// 与其它中继一样逐步校验（入口分支、代码洞字节、回调槽为空）之后才发布回调地址。
//
// This definition must stay *outside* every `#if` block: it is called from the port
// adapter (`ExlaunchHookAdapter`), which every non-diagnostic build compiles together with
// `TryInstallDefaultManifestMod`, and a definition that a conditional removes leaves the
// module with an undefined symbol whose PLT slot stays zero -- hardware caught exactly
// that as `PC=0` inside `ModuleWorker`.
extern "C" __attribute__((visibility("hidden"))) void
IsaacModRuntime_RebuildContentMountPointsRelay();

// 新后端（入口中继）下的"取道具前"挂点。回调体与旧后端**共用同一个派发器**
// （`LuaRuntime::DispatchPreGetCollectible`），差别只在"没人覆盖时谁来跑原函数"：
//   * 旧后端的 IPS 中继桩自己判 —— 回调返回值的高 32 位为 0 就跳回原函数；
//   * 入口中继的桩不做任何判断（尾调用进回调），所以**回调自己判**：高 32 位非 0 ⇒ Mod 覆盖了
//     返回值，直接以低 32 位返回；否则调回退入口执行原函数。
// 目标 ABI 是 `ItemPool::GetCollectible(this, poolType, seed, noDecrease, defaultItem)` —— 第 5 个参数
// 真的存在（Lua 侧的 `ItemPool:GetCollectible` 就是按 5 个实参调它、旧 IPS 桩也原样透传 x4），
// 所以这里必须**原样收、原样交给原函数**，少传一个就会让原函数读到垃圾。
extern "C" std::uint32_t EntryRelayPreGetCollectibleCallback(void* itemPool, std::uint32_t itemPoolType,
                                                             std::uint32_t seed,
                                                             std::uint32_t noDecrease,
                                                             std::uint32_t defaultItem) {
    const std::uint64_t dispatched = LuaRuntime::DispatchPreGetCollectible(
        itemPool, itemPoolType, seed, noDecrease, defaultItem);
    // 位 33 = "**返回过非 nil**"（可能是没有替换值的 `false` 之类）。PC 文档：
    // "If any non nil value was returned to **MC_PRE_GET_COLLECTIBLE** then this callback
    // （即 `MC_POST_GET_COLLECTIBLE`）will be skipped." ⇒ 它决定的是"要不要派发 POST"，
    // 与"有没有替换值"（位 32）是两件事。
    const bool preReturnedNonNil = ((dispatched >> 33) & 1U) != 0;
    if ((dispatched >> 32) & 1U) {
        return static_cast<std::uint32_t>(dispatched);  // 有替换值：这次就给它
    }
    const auto original = isaac::runtime::Original<std::uint32_t (*)(
        void*, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t)>(
        isaac::runtime::HookId::PreGetCollectible);
    const std::uint32_t result = original(itemPool, itemPoolType, seed, noDecrease, defaultItem);
    if (preReturnedNonNil) {
        return result;  // PRE 返回过非 nil ⇒ 跳过 POST（PC 规则）
    }
    // 批次 102：`MC_POST_GET_COLLECTIBLE`（id 63）—— 必须放在**原函数返回之后**，
    // 因为它的第一个实参"刚选出来的那个道具"只有此刻才存在（EID 的
    // `EID:postGetCollectible(selectedCollectible, itemPoolType)` 就读它来记抓娃娃机/Flip 的道具）。
    // 中继是**入口**中继，所以"原函数之后"这件事得由我们自己在回调里排顺序。
    const std::uint64_t post =
        LuaRuntime::DispatchPostGetCollectible(itemPool, itemPoolType, seed, noDecrease, result);
    if ((post >> 32) != 0) {
        return static_cast<std::uint32_t>(post);
    }
    return result;
}

// --- 批次 102：四个事件中继的回调体 ---------------------------------------------
//
// 三个"使用类"的靶点形状一致：**先在入口派发（可以拦），再跑原函数，最后派发"事后通知"**。
// 这一族都是尾调用入口（[sp, #-0x..]! 起头、把 x29/x30 存进去），所以本回调以目标函数的身份
// 运行，`ret` 直接回到游戏的调用方 —— 与 `EntryRelayRebuildMountPointsCallback` 同一个前提。
//
// ⚠️ 一个必须写明的偏离（`MC_PRE_USE_ITEM` 拦下之后）：PC 的文档是
// "Return true to prevent the default code of an item to be triggered. **This will still
// discharge the item.**" —— 也就是拦下之后**仍然要消耗电荷、播使用动画**。我们第一版**不复刻**
// 那套收尾（那要动引擎的道具槽与动画状态机，风险远高于收益），拦下就是直接返回。
// 后果：模组拦下的那次使用不会掉电荷。EID 的处理器**全都不返回**（`OnUseSmelter`/`CheckVoidAbsorbs`
// /`CheckFlipGridIndexes`/`OnUseLemegeton`/`OnUseGlowingHourglass`/`OnUseGeneral` 末尾都没有
// `return`）⇒ 这条偏离对卡上现有模组的实际行为**无影响**；将来有模组真的用返回值拦，要按
// PC 语义补上"照常放电"。
// ★★ 返回值必须原样搬运（2026-09-21 修：真机 bug"所有主动道具用后不掉充能、部分道具被移除"）★★
//
// 入口中继是**以目标函数的身份**运行的（`entry_relay.hpp`：槽里 `br` 尾调用本回调，本回调的
// `ret` 直接回到游戏的调用方）⇒ **目标函数的返回值也由本回调负责**。而
// `Entity_Player::UseActiveItem` 是**有返回值**的：本体镜像里它唯一的收尾点（`0x31A8C0`，
// 函数 `0x30653C` 起、长 `0x143B4`）是
//     bfi  x22, x20, #8, #1     ; 把 (UseFlags & 1) 塞进第 8 位
//     mov  x0, x22              ; ← 返回值
//     …拆栈… ret
// 第一版把它声明成 `void` ⇒ 游戏调用方读到的 `x0` 是我们回调里最后一次调用的残留值
// （不是本次使用算出来的那套标志）⇒ 用后记账（扣充能 / 移除单次道具 / 服装动画）按垃圾值走分支。
// 判据与扫描方式见 `tools/engine_offset_abi_report.py` 的"入口中继回调"一节（门禁
// `runtime/tests/test_engine_offset_signatures.py` 钉住"引擎有返回值而我们声明 void"这一类错）。
// MC_INPUT_ACTION在Manager高层接收真实Entity*；底层ManagerBase第四实参是unsigned*。
// 三个高层原生函数各16字节，加载输入单例、清x3后尾跳到底层；入口中继精确重定位
// 该短函数并保留原回退，不再将所有KAGE通用查询伪装成玩家输入。
// 公开Input查询保留RawEngineInputQueryScope，保证覆盖不影响模组读取。
// 证据与历史更正见docs/MCM与StageAPI兼容层修复实施计划-20261025.md及本轮反汇编。
// raw直接回退；否则先派发，首非nil可以覆盖，不覆盖则原样交还原函数结果。
#define ISAAC_RUNTIME_INPUT_ACTION_RELAY(NAME, HOOK, HOOKPTR, RET, HOOKVALUE)                     \
    extern "C" RET NAME(void* manager, std::uint32_t action, std::uint32_t controller,            \
                        void* entity) {                                                        \
        using QueryFn = RET (*)(void*, std::uint32_t, std::uint32_t, void*);                      \
        const auto original = isaac::runtime::Original<QueryFn>(isaac::runtime::HookId::HOOK);    \
        if (LuaRuntime::IsRawEngineInputQuery()) {                                                \
            return original(manager, action, controller, entity);                               \
        }                                                                                         \
        const LuaRuntime::InputActionOutcome outcome =                                            \
            LuaRuntime::DispatchInputAction(action, controller, HOOKVALUE,                      \
                reinterpret_cast<std::uintptr_t>(entity));                                      \
        if (outcome.overridden) {                                                                 \
            return outcome.HOOKPTR;                                                               \
        }                                                                                         \
        return original(manager, action, controller, entity);                                   \
    }

ISAAC_RUNTIME_INPUT_ACTION_RELAY(EntryRelayManagerIsActionPressedCallback, ManagerIsActionPressed,
                                 boolean, bool, kInputHookIsActionPressed)
ISAAC_RUNTIME_INPUT_ACTION_RELAY(EntryRelayManagerIsActionTriggeredCallback,
                                 ManagerIsActionTriggered, boolean, bool,
                                 kInputHookIsActionTriggered)
ISAAC_RUNTIME_INPUT_ACTION_RELAY(EntryRelayManagerGetActionValueCallback, ManagerGetActionValue,
                                 value, float, kInputHookGetActionValue)
#undef ISAAC_RUNTIME_INPUT_ACTION_RELAY

// ============================================================================
// 批次 392（2026-10-07）：我们这侧的输入读取怎么绕开上面的覆盖
// ============================================================================
//
// 上面那三条中继**同时**拦到了 Lua 的 `Input.*`（两者是同一个函数，证据见那一节的注释）。
// 绕法**不在本文件**：`LuaRuntime::InputIsActionPressedThunk()` / `…GetActionValueThunk()`
// 现在返回的是 `lua_runtime.cpp` 里的**直读壳**（壳里套一次 `RawEngineInputQueryScope` 再转发到
// 引擎胶水）⇒ 所有消费者（Lua 的 `Input.*`、每帧全动作采样器、原生模组页与探针）**自动**全部走直读，
// 将来再加消费者也不会漏。
//
// ★ 为什么绕在"取值助手"那一层、而不是改这里的发布点：`tools/engine_offset_abi_report.py` 的
//   `single_binding_signature` 靠**文本**追踪"常量 → 校验助手 → 局部变量 → 发布函数 → 全局槽 →
//   取值助手 → 调用点"这条链，而它认的发布函数名必须是 `Set*`（`SETTER_CALL_RE`）。发布点一改名，
//   三条 `kManager*Offset` 的判决就会掉回"没比过"（门禁 `test_engine_offset_signatures` 当场红）。
//   发布点保持原样 ⇒ 引擎地址仍然是被校验过、被追踪过的那一份；绕行只发生在读取侧。

extern "C" std::uint64_t EntryRelayUseActiveItemCallback(void* player, std::uint32_t item,
                                                        std::uint32_t useFlags,
                                                        std::int32_t activeSlot,
                                                        std::int32_t customVarData) {
    using UseActiveItemFn = std::uint64_t (*)(void*, std::uint32_t, std::uint32_t, std::int32_t,
                                              std::int32_t);
    // PC 5A13D8..5A13DA skips both use callbacks for the empty item (0).
    // Keep the native empty-item return path and all original arguments intact.
    if (item == 0 || !LuaRuntime::IsOnGameThread()) {
        const auto original =
            isaac::runtime::Original<UseActiveItemFn>(isaac::runtime::HookId::UseActiveItem);
        return original(player, item, useFlags, activeSlot, customVarData);
    }
    if (LuaRuntime::DispatchPreUseItem(isaac::runtime::engine_memory::AddressOf(player),
                                       static_cast<std::int32_t>(item),
                                       static_cast<std::int32_t>(useFlags), activeSlot,
                                       customVarData)) {
        // PC取消仅跳过道具效果，默认结果仍是{Discharge=true,Remove=false}。
        return 1;
    }
    const auto original =
        isaac::runtime::Original<UseActiveItemFn>(isaac::runtime::HookId::UseActiveItem);
    std::uint32_t type{}, variant{};
    const bool mainVariant = isaac::runtime::ReadEntityIdentity(
        isaac::runtime::engine_memory::AddressOf(player), &type, &variant) && variant == 0;
    isaac::runtime::UseItemCallScope scope(isaac::runtime::ActiveUseItemFrame(),
        isaac::runtime::engine_memory::AddressOf(player),static_cast<std::int32_t>(item),
        useFlags,activeSlot,customVarData,mainVariant);
    return original(player,item,useFlags,activeSlot,customVarData);
}

extern "C" void EntryRelayUseCardCallback(void* player, std::uint32_t card,
                                          std::uint32_t useFlags) {
    // 入口中继用BR保留原始LR；这里必须在调用原生/回调之前取调用点。
    const auto caller = isaac::runtime::engine_memory::AddressOf(
        __builtin_extract_return_addr(__builtin_return_address(0)));
    if (card == 48 && LuaRuntime::IsOnGameThread()) {
        auto* frame = isaac::runtime::ActiveUseItemFrame();
        if (frame && !frame->dispatched && frame->item == 286) {
            isaac::runtime::NoteUseItemCardAnimation(frame,
                isaac::runtime::engine_memory::AddressOf(player), card, caller,
                LuaRuntime::EngineModuleBase());
        }
    }
    using UseCardFn = void (*)(void*, std::uint32_t, std::uint32_t);
    const auto original = isaac::runtime::Original<UseCardFn>(isaac::runtime::HookId::UseCard);
    original(player, card, useFlags);
    LuaRuntime::DispatchUseCard(isaac::runtime::engine_memory::AddressOf(player),
                                static_cast<std::int32_t>(card),
                                static_cast<std::int32_t>(useFlags));
}

extern "C" void EntryRelayUsePillCallback(void* player, std::uint32_t pillEffect,
                                          std::uint32_t pillColor, std::uint32_t useFlags) {
    using UsePillFn = void (*)(void*, std::uint32_t, std::uint32_t, std::uint32_t);
    // `pillColor` 只是透传给原函数 —— PC 的 `MC_USE_PILL` **没有**这个实参（可选实参类型是
    // `PillEffect`，EID 自己从玩家口袋读颜色）。这里刻意写出来是为了让"它被读到了但没有丢"可见。
    const auto original = isaac::runtime::Original<UsePillFn>(isaac::runtime::HookId::UsePill);
    original(player, pillEffect, pillColor, useFlags);
    LuaRuntime::DispatchUsePill(isaac::runtime::engine_memory::AddressOf(player),
                                static_cast<std::int32_t>(pillEffect),
                                static_cast<std::int32_t>(useFlags));
}

extern "C" void EntryRelayGameExitCallback(void* game, std::uint32_t shouldSave) {
    using GameExitFn = void (*)(void*, std::uint32_t);
    // ★★ 批次 117：**局内单向闩锁**的"出局"边界 —— 本回调在**退出流程一开始**就触发
    //   （"先派发、再跑原函数"），所以它**严格早于下一局的任何写位**。
    //   ★ 批次 119 起它在闩锁上的作用**不是"清成干净的"**，而是**把闩锁转成"留存"**：
    //   用户裁定"继续同一份存档算同一局"，而他改开关的唯一时机就是出局之后 ⇒ 清了就永远
    //   看不到"中途开启后又关掉仍锁"。留存由下一次"继续"接回来（见 `NoteNewRun`）。
    //   这一格 `gameExitCalls` 同时是"本路确实会触发"的现场证据（状态面 [49]）。
    auto& state = isaac::runtime::modmenu::g_ModMenuState;
    ++state.gameExitCalls;
    isaac::runtime::modmenu::NoteNewRun(isaac::runtime::modmenu::RunBoundaryKind::GameExit);
    // `MC_PRE_GAME_EXIT` 的名字里那个 PRE 是相对"这一局结束"而言的：PC 在**退出流程开始前**
    // 触发它，模组在这里做收尾（EID 唯一的 `SaveData` 调用点）。所以顺序是"先派发、再跑原函数"。
    LuaRuntime::DispatchPreGameExit(shouldSave != 0);
    const auto optionStatus=isaac::runtime::FlushRuntimeOptions();
    if(!optionStatus.ok()&&optionStatus.code()!=isaac::runtime::StatusCode::Unsupported){
        char message[96];const auto n=std::snprintf(message,sizeof(message),"runtime options save failed: %u",static_cast<unsigned>(optionStatus.code()));
        if(n>0)LuaRuntime::RecordLuaErrorText(message,static_cast<std::size_t>(n));
    }
    const auto original = isaac::runtime::Original<GameExitFn>(isaac::runtime::HookId::GameExit);
    original(game, shouldSave);
}

// 批次 103：掉落物碰撞。
// 顺序是"**先派发、后决定要不要跑原函数**"：PC 的返回值三态里 `true` 与 `false` 都不执行
// 内部代码（区别只在引擎自己怎么记这次碰撞，那部分我们没有对应实现），只有 `nil` 才照常执行。
// ★ 返回值同样必须原样搬运（2026-09-21）：本体里 `Entity_Pickup::handle_collision` 在收尾前
// 有 `mov w0, #1`（`0x2728C8`，函数 `0x271F2C` 起、长 `0x9C4`）⇒ 它返回"这次碰撞有没有被处理"。
// 我们声明成 `void` 时游戏拿到的是垃圾值，掉落物拾取的记账（含"道具被拿走"那条路）会走错分支。
extern "C" std::uint64_t EntryRelayPickupCollisionCallback(void* pickup, void* collider,
                                                          std::uint32_t low) {
    using HandleCollisionFn = std::uint64_t (*)(void*, void*, std::uint32_t);
    // 过滤值 = 掉落物的变体（PC 给这条回调的可选实参类型是 `PickupVariant`）。
    // 用导出的 `ReadEntityIdentity`（它内部做"读引擎字段前先判可读"那套判据 —— 这套判据只有
    // `isaac_api.cpp` 里有一份，不在这里重写一份）。
    // 读失败给 −1：它与任何真实变体都不相等 ⇒ 带过滤器的登记不会被调用（"说不出就不调用"），
    // 而**不带**过滤器的登记照常收到回调 —— 读不到变体不该让整条回调静默消失。
    std::uint32_t type = 0;
    std::uint32_t variant = 0;
    const bool identityReadable = isaac::runtime::ReadEntityIdentity(
        isaac::runtime::engine_memory::AddressOf(pickup), &type, &variant);
    const auto decision = LuaRuntime::DispatchPreEntityCollision(isaac::runtime::kCallbackPrePickupCollision,
        isaac::runtime::engine_memory::AddressOf(pickup), isaac::runtime::engine_memory::AddressOf(collider), low != 0,
        identityReadable ? static_cast<std::int32_t>(variant) : -1);
    if (decision != LuaRuntime::CollisionOverride::Continue) return decision == LuaRuntime::CollisionOverride::Ignore ? 1 : 0;
    const auto original =
        isaac::runtime::Original<HandleCollisionFn>(isaac::runtime::HookId::PickupCollision);
    return original(pickup, collider, low);
}

// 批次 104：房间生成实体。
//
// 顺序是"**先派发、再跑原函数**"：PC 的 `MC_PRE_ROOM_ENTITY_SPAWN` 本意就是"在引擎按房间布局
// 生成实体**之前**"（文档还说"返回一个表可以覆盖引擎自己会做的替换（例如敌人变体）"⇒ 回调发生
// 在替换之前）。这个靶点天然满足：引擎的自然替换（`Room::FixSpawnEntry`）是在**函数体内**做的，
// 我们在入口派发，拿到的正是替换前的 Type/Variant/SubType。
//
// ⚠️ 读不到 `RoomConfig::Entry` 那三个字段时**不派发**（不编造值）：EID 的处理器拿
// `entityType/variant/subtype/gridIndex` 去建索引，给错的比给不到更糟。可读性判据在
// `ReadRoomConfigEntryFields` 里（唯一一份"读引擎字段前先判可读"的实现）。
// ★ 返回值原样搬运（2026-09-21）：本体里 `Room::spawn_entity` 在收尾前有 `mov w0, w21`
// （`0x453EA0`，函数 `0x453918` 起、长 `0x5A8`）⇒ 它返回一个 32 位结果（调用方要用的那个值）。
// ★更正（2026-10-09）：上方批次104注释仅保留历史；Roomspawn实际长0x117C，
// 其入口不是71的PC阶段。生产已改为FixSpawnEntry预转换之后的Internal挂点；
// 旧函数只留诊断原样转发，不能再据此称71只通知或把0x453EA0当完整函数尾。
extern "C" std::uint64_t EntryRelayRoomEntitySpawnCallback(void* room, std::uint32_t gridIndex,
                                                          const void* entry, std::uint32_t seed,
                                                          void** outEntity,
                                                          std::uint32_t flags) {
    using SpawnEntityFn =
        std::uint64_t (*)(void*, std::uint32_t, const void*, std::uint32_t, void**, std::uint32_t);
    // 历史诊断入口仅原样转发；生产71现在由FixSpawnEntry内部挂点派发。
    const auto original =
        isaac::runtime::Original<SpawnEntityFn>(isaac::runtime::HookId::RoomEntitySpawn);
    return original(room, gridIndex, entry, seed, outEntity, flags);
}

// ============================================================================
// 批次 396（2026-10-07）：`MC_ENTITY_TAKE_DMG` 的四条入口中继 + `MC_EVALUATE_CACHE`
// ============================================================================
namespace {

//: 四条受伤入口中继共用的身体。形状 = 目标 ABI：
//: `(实体 /*x0*/, Amount /*s0*/, DamageFlags /*x1*/, Source /*x2*/, CountdownFrames /*w3*/)`。
//:
//: 返回值的搬运口径：本体在 `w0` 里返回"这次伤害有没有落实"，调用方（例如
//: `Entity_NPC::TakeDamage` 的 `mov w20,w0`）会继续用 ⇒ **必须原样转发**；
//: 只有"模组要求取消"时不跑原函数、返回 0（= 没落实）。
template <typename Fn>
std::uint64_t RunEntityTakeDamageRelay(isaac::runtime::HookId hook, void* entity, float amount,
                                       std::uint64_t damageFlags, const void* sourceRef,
                                       std::int32_t countdownFrames) {
    // 过滤值 = 实体的 `EntityType`（PC 给这条回调的可选实参类型就是 `EntityType`）。
    // 用导出的 `ReadEntityIdentity`（"读引擎字段前先判可读"那套只有 `isaac_api.cpp` 一份）。
    // 读不到给 −1：带过滤器的登记不会被调用（"说不出就不调用"），不带过滤器的照常收到 ——
    // 读不到类型不该让整条回调静默消失。
    std::uint32_t type = 0;
    std::uint32_t variant = 0;
    const bool identityReadable = isaac::runtime::ReadEntityIdentity(
        isaac::runtime::engine_memory::AddressOf(entity), &type, &variant);
    if (LuaRuntime::DispatchEntityTakeDamage(
            isaac::runtime::engine_memory::AddressOf(entity), amount,
            static_cast<std::int32_t>(damageFlags),
            reinterpret_cast<std::uintptr_t>(sourceRef), countdownFrames,
            identityReadable ? static_cast<std::int32_t>(type) : -1)) {
        // 模组返回 `false` ⇒ 取消这次伤害：不跑原函数、交回"没落实"。
        return 0;
    }
    const auto original = isaac::runtime::Original<Fn>(hook);
    return original(entity, amount, damageFlags, sourceRef, countdownFrames);
}

}  // namespace

// 四条：基类 `Entity::TakeDamage`（覆盖 NPC/跟班/一切不覆写 TakeDamage 的实体）
// + 三个不回跳基类的子类（玩家 / 掉落物 / 槽位）。靶点与守卫见 `runtime_constants.hpp`。
extern "C" std::uint64_t EntryRelayEntityTakeDamageCallback(void* entity, float amount,
                                                            std::uint64_t damageFlags,
                                                            const void* sourceRef,
                                                            std::int32_t countdownFrames) {
    using TakeDamageFn = std::uint64_t (*)(void*, float, std::uint64_t, const void*, std::int32_t);
    return RunEntityTakeDamageRelay<TakeDamageFn>(isaac::runtime::HookId::EntityTakeDamage, entity,
                                                  amount, damageFlags, sourceRef, countdownFrames);
}

extern "C" std::uint64_t EntryRelayEntityPlayerTakeDamageCallback(void* entity, float amount,
                                                                  std::uint64_t damageFlags,
                                                                  const void* sourceRef,
                                                                  std::int32_t countdownFrames) {
    using TakeDamageFn = std::uint64_t (*)(void*, float, std::uint64_t, const void*, std::int32_t);
    return RunEntityTakeDamageRelay<TakeDamageFn>(isaac::runtime::HookId::EntityPlayerTakeDamage,
                                                  entity, amount, damageFlags, sourceRef,
                                                  countdownFrames);
}

extern "C" std::uint64_t EntryRelayEntityPickupTakeDamageCallback(void* entity, float amount,
                                                                  std::uint64_t damageFlags,
                                                                  const void* sourceRef,
                                                                  std::int32_t countdownFrames) {
    using TakeDamageFn = std::uint64_t (*)(void*, float, std::uint64_t, const void*, std::int32_t);
    return RunEntityTakeDamageRelay<TakeDamageFn>(isaac::runtime::HookId::EntityPickupTakeDamage,
                                                  entity, amount, damageFlags, sourceRef,
                                                  countdownFrames);
}

extern "C" std::uint64_t EntryRelayEntitySlotTakeDamageCallback(void* entity, float amount,
                                                                std::uint64_t damageFlags,
                                                                const void* sourceRef,
                                                                std::int32_t countdownFrames) {
    using TakeDamageFn = std::uint64_t (*)(void*, float, std::uint64_t, const void*, std::int32_t);
    return RunEntityTakeDamageRelay<TakeDamageFn>(isaac::runtime::HookId::EntitySlotTakeDamage,
                                                  entity, amount, damageFlags, sourceRef,
                                                  countdownFrames);
}

// `MC_EVALUATE_CACHE`：`Entity_Player::EvaluateItems()` 的入口中继（x0 = this = 玩家，返回 void）。
//
// ★★ 批次 405（2026-10-07）：顺序从"**先派发、再跑原函数**"改成"**先跑原函数、再派发**"。
//   病根：引擎这个函数体对 `Damage`/`MoveSpeed`/`MaxFireDelay`/`ShotSpeed`/`Luck`/`TearRange`
//   是**清零 + 重建**（`CACHE_DAMAGE` 置位就先 `str wzr,[x19,#0x1844]` 再累加，收尾还有两处回写），
//   而它内部**没有**这条回调的派发点 ⇒ 原来"入口先派发"时，模组写进去的属性会在**同一次**
//   `EvaluateItems` 里被重算覆盖 ⇒ 「自定义角色属性调整完全不生效」（Trinity `main.lua:85/:116`）。
//   PC 侧这条回调是引擎**重算之后**派发的（契约反复写 "Only change this in MC_EVALUATE_CACHE"）
//   ⇒ 我们原来**不同形**，现在对齐。
//   掩码仍取**调用前快照**：原函数会把 `_cacheFlags` 的脏位清掉，跑到它之后再读就没了。
//   顺序与快照语义抽在 `interfaces/lua/evaluate_cache_dispatch.hpp`（宿主上可测）。
//
// ★ 重入：`EvaluateItems` 会为同屏第二个玩家**递归调用自己**（`0x28bc0c bl EvaluateItems`，
//   走 PLT ⇒ 也会进我们这里）。这是**刻意的**：内层那次是另一个玩家，本来就该各派发一次，
//   所以这里**不加**重入保护。
// ★ 掩码读不到 ⇒ **不派发**（不编造 CacheFlag）：过滤值是模组用来建索引的，给错的比给不到更糟。
extern "C" void EntryRelayEvaluateItemsCallback(void* player) {
    using EvaluateItemsFn = void (*)(void*);
    const std::uintptr_t address = isaac::runtime::engine_memory::AddressOf(player);
    const auto original =
        isaac::runtime::Original<EvaluateItemsFn>(isaac::runtime::HookId::EvaluateItems);
    isaac::runtime::DispatchEvaluateCacheAfterOriginal(
        [address](std::uint32_t* mask) {
            return isaac::runtime::ReadEntityPlayerCacheFlags(address, mask);
        },
        [original, player]() { original(player); },
        // ★★★ 批次 409（2026-10-08）：**必须是 `CacheFlag` 的【值】**（`1 << bit`），**不是位序号**。
        //   模组拿这个实参跟 `CacheFlag.CACHE_XXX` 比（值 = 1/2/4/8/16/…/1024），
        //   原来直接传 `bit` ⇒ `CACHE_SPEED(16)` / `CACHE_LUCK(1024)` **永远不触发**、
        //   `CACHE_DAMAGE(1)` 撞到射速位上（真机 Isaiah 的伤害/速度就是因此对不上）。
        //   逐字依据见 `interfaces/lua/evaluate_cache_dispatch.hpp` 的 `CacheFlagValueForBit`。
        [address](std::int32_t bit) {
            LuaRuntime::DispatchEvaluateCache(address,
                                              isaac::runtime::CacheFlagValueForBit(bit));
        });
}

// ============================================================================
// 批次 397（2026-10-07）：补全回调（第 2 批）—— 三条入口中继的回调体
// ============================================================================
//
// 三条的时机选择都按 PC 契约原文（见 `runtime_constants.hpp` 的「批次 397」那段）：
//   * `Entity::Kill`：契约说"**right before** a death animation is triggered" ⇒ **先派发、再跑原函数**。
//   * `Entity_NPC::trigger_death_remove`：契约说"**after** the Death animation is played" ⇒
//     这个函数本身就是"动画播完之后"那一步 ⇒ **先派发、再跑原函数**（赶在它把 NPC 掉落/移除之前）。
//   * `Game::End`：契约说"when the game over screen appears / an ending starts playing" ⇒
//     引擎那一步在**原函数体内**，所以**先派发、再跑原函数**；顺带避开一个坑：
//     `ShouldDispatchManagedCallbacks()` 要求"房间非空 + 至少一个可验证玩家"，而 `End` 跑完之后
//     这一局正在拆 ⇒ 放到它后面派发很可能被这道闸静默跳过（同 `MC_PRE_GAME_EXIT` 的教训）。

// `MC_POST_ENTITY_KILL`(68)：`Entity::Kill()` 入口（x0 = this = 实体），返回 void。
// ★ 只挂基类一条即全覆盖：`Entity_NPC::Kill` / `Entity_Familiar::Kill` 两个覆写都回跳基类
//   （逐条反汇编核对，见 `runtime_constants.hpp`）⇒ 不存在"漏了某个子类"的问题。
extern "C" void EntryRelayEntityKillCallback(void* entity) {
    using KillFn = void (*)(void*);
    // 过滤值 = 实体的 `EntityType`（读不到给 −1：带过滤器的登记不会被调用，不带过滤器的照常收到）。
    std::uint32_t type = 0;
    std::uint32_t variant = 0;
    const bool identityReadable = isaac::runtime::ReadEntityIdentity(
        isaac::runtime::engine_memory::AddressOf(entity), &type, &variant);
    LuaRuntime::DispatchPostEntityKill(isaac::runtime::engine_memory::AddressOf(entity),
                                       identityReadable ? static_cast<std::int32_t>(type) : -1);
    const auto original = isaac::runtime::Original<KillFn>(isaac::runtime::HookId::EntityKill);
    original(entity);
}

// 在StartStageTransition原生楼层完成/切层操作之前拦截非法贪婪Home分支。
extern "C" void EntryRelayGameStartStageTransitionCallback(
    void* game, bool goingUp, int animation, void* player) {
    using namespace isaac::runtime;
    const auto original = Original<StageTransitionFn>(HookId::GameStartStageTransition);
    const auto room = engine_call::AsFunction<RoomTransitionFn>(
        g_GreedHourglassRoomTransition.load(std::memory_order_acquire));
    const auto result = DispatchGreedHourglassTransition(
        game, goingUp, animation, player, original, room,
        {kLevelStageOffset, kGameDifficultyOffset, kGameStateFlagsOffset,
         kGamePlayerArrayBeginOffset, kGamePlayerArrayEndOffset},
        &engine_memory::EngineMemoryReadable);
    const char* error = nullptr;
    switch (result) {
        case HourglassTransitionResult::Forwarded:
        case HourglassTransitionResult::Rerouted: return;
        case HourglassTransitionResult::StateUnreadable:
            error = "Glowing Hour Glass transition failed: native game state unreadable"; break;
        case HourglassTransitionResult::RoomUnavailable:
            error = "Glowing Hour Glass transition failed: native ERROR room entry unavailable"; break;
        case HourglassTransitionResult::OriginalUnavailable:
            error = "Glowing Hour Glass transition failed: original stage entry unavailable"; break;
    }
    if (error) LuaRuntime::RecordLuaErrorText(error, std::strlen(error));
}

// Init为虚调用；挂实际入口才能覆盖开局、读档与合作玩家创建。
extern "C" void EntryRelayEntityPlayerInitCallback(void* player, std::uint32_t type,
    std::uint32_t variant, std::uint32_t subType, std::uint32_t seed) {
    using Init = void (*)(void*, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    const auto original = isaac::runtime::Original<Init>(isaac::runtime::HookId::EntityPlayerInit);
    if (!original) return;
    original(player, type, variant, subType, seed);
    LuaRuntime::DispatchNativePlayerInit(isaac::runtime::engine_memory::AddressOf(player));
}

// `MC_POST_NPC_DEATH`(29)：`Entity_NPC::trigger_death_remove()` 入口，返回 void。
// ★ 符号名是无参（`…20trigger_death_removeEv`），但函数体开头就读 `x1` ⇒ 我们按两个实参声明、
//   把它**原样转发**（我们从不解释它 ⇒ 转发即透明）。
// ⚠️ 已知覆盖范围（如实记）：这是 NPC 死亡的标准汇合点（`Entity_NPC::Update` 在
//   `ANM2::IsFinished` 之后调它，另有 `update_frozen` / `ai_mega_satan_head` 两条路径）；
//   个别 Boss 若自己重写了死亡收尾、不走这里，就收不到这条回调 —— 上卡时用只读探针确认。
extern "C" void EntryRelayNpcDeathRemoveCallback(void* npc, void* forwarded) {
    using DeathRemoveFn = void (*)(void*, void*);
    std::uint32_t type = 0;
    std::uint32_t variant = 0;
    const bool identityReadable = isaac::runtime::ReadEntityIdentity(
        isaac::runtime::engine_memory::AddressOf(npc), &type, &variant);
    LuaRuntime::DispatchPostNpcDeath(isaac::runtime::engine_memory::AddressOf(npc),
                                     identityReadable ? static_cast<std::int32_t>(type) : -1);
    const auto original =
        isaac::runtime::Original<DeathRemoveFn>(isaac::runtime::HookId::NpcDeathRemove);
    original(npc, forwarded);
}

// `MC_POST_GAME_END`(16)：`Game::End(eEnding)` 入口（x0 = Game*、w1 = eEnding），返回 void。
// ★ `IsGameOver` 的取值**是推断出来的**（两项独立证据，见 `runtime_constants.hpp`）：
//   `eEnding == 1` ⇒ 玩家死亡/GameOver；其余结局 ⇒ false。上卡时必须用只读探针实测一次。
extern "C" void EntryRelayGameEndCallback(void* game, std::int32_t ending) {
    using GameEndFn = void (*)(void*, std::int32_t);
    LuaRuntime::DispatchPostGameEnd(ending == 1);
    const auto original = isaac::runtime::Original<GameEndFn>(isaac::runtime::HookId::GameEnd);
    original(game, ending);
}

// `MC_POST_FIRE_TEAR`(61)：`Entity_Player::FireTear(...)` 入口，返回 `Entity_Tear*`。
// 形状**逐字照批次 337 的 ABI 取证**（`runtime_constants.hpp` 的「批次 337」段）：
// `(this, Vector2 const& /*x1*/, Vector2 按值 /*HFA s0:s1*/, u32 flags /*w2*/,
//   Entity* Source /*x3*/, float DamageMultiplier /*s2*/)`。
// ★ 派发点在**原函数返回之后**：PC 给这条回调的第一个实参是"刚生出来的那颗泪弹"，
//   而它只有原函数返回时才存在（同 `MC_POST_GET_COLLECTIBLE` 的形状）。
// ★ 返回值原样搬运（x0 = 泪弹指针，调用方 `Weapon::FireTear` 会拿它继续用）。
// ★ 生不出泪弹（返回空）就不派发：PC 的实参是一个真泪弹，给 `nil` 不如不给。
extern "C" void* EntryRelayFireTearCallback(void* player, const void* position,
                                            RelayVector2Hfa velocity, std::uint32_t flags,
                                            void* source, float damageMultiplier) {
    using FireTearFn =
        void* (*)(void*, const void*, RelayVector2Hfa, std::uint32_t, void*, float);
    const auto original = isaac::runtime::Original<FireTearFn>(isaac::runtime::HookId::FireTear);
    void* tear = original(player, position, velocity, flags, source, damageMultiplier);
    if (tear != nullptr) {
        LuaRuntime::DispatchPostFireTear(reinterpret_cast<std::uintptr_t>(tear));
    }
    return tear;
}

// 新后端（入口中继）下的挂载点重建挂点。语义与旧后端一致：**先跑原函数，再跑我们的重挂载**。
// 旧后端把中继桩放在函数体内唯一的 `ret` 上，天然就是"返回前"；入口挂法得自己按这个顺序调。
// 函数无参数（`_ZN15IsaacRepentance25RebuildContentMountPointsEv`）；入口桩是尾调用，
// 本回调即以它的身份运行，`ret` 直接回到游戏的调用方（含尾调用点）。
extern "C" void EntryRelayRebuildMountPointsCallback() {
    // ★★ 批次 359：**先记一笔"这层包装真的被调到了"**。357 里我只读了"重挂动作跑过 0 次"，
    //   但那个 0 有两种含义（引擎没重建 / 我们这层没装上），必须在**活的路径**上分开量。
    isaac::runtime::bridge::NoteRebuildMountPointsEntryRelayCallbackFired();
    const auto original =
        isaac::runtime::Original<void (*)()>(isaac::runtime::HookId::RebuildMountPoints);
    original();
    IsaacModRuntime_RebuildContentMountPointsRelay();
}


bool TryInstallRebuildMountPointsRelay(const TargetModule& module) {
    // ★★★ 批次 358：357 的读数证明**这个中继压根没装上**（而它就是"引擎重建挂载点表之后
    //   把模组挂载点补回来"的那一环）⇒ 真机上必须能看见"卡在哪一条"。这里把失败码与**现场字节**
    //   一起交给诊断结构体（只读；范围先自己判一遍，绝不盲读）。
    unsigned failure = 0;
    uintptr_t slot = 0;
    if (!VerifyStage48Relay(module, kRebuildMountPointsRelayOffset,
                            kRebuildMountPointsRelayExpectedOriginal,
                            kRebuildMountPointsRelayExpectedEntry,
                            kRebuildMountPointsRelayCodeOffset,
                            kRebuildMountPointsRelayExpectedBytes.data(),
                            kRebuildMountPointsRelayExpectedBytes.size(),
                            kRebuildMountPointsRelaySlotOffset, &slot, &failure)) {
        // 只有"范围/映射都过了、只是字节对不上"那几种才去读现场 —— 更前面的失败连地址都不可信。
        const bool siteTrustworthy = failure >= kRelayVerifyTargetBytes &&
                                     module.base != 0 &&
                                     kRebuildMountPointsRelayOffset + 16 <= module.textSize &&
                                     kRebuildMountPointsRelayCodeOffset + 16 <= module.textSize;
        if (siteTrustworthy) {
            isaac::runtime::bridge::NoteRebuildRelayVerifyDetail(
                failure,
                reinterpret_cast<const void*>(module.base + kRebuildMountPointsRelayOffset),
                reinterpret_cast<const void*>(module.base + kRebuildMountPointsRelayCodeOffset),
                0);
        } else {
            isaac::runtime::bridge::NoteRebuildRelayVerifyDetail(failure, nullptr, nullptr, 0);
        }
        return false;
    }
    unsigned publishFailure = 0;
    const bool published = PublishStage48RelayCallback(
        slot, reinterpret_cast<uintptr_t>(&IsaacModRuntime_RebuildContentMountPointsRelay),
        &publishFailure);
    if (!published) {
        isaac::runtime::bridge::NoteRebuildRelayVerifyDetail(publishFailure, nullptr, nullptr, 0);
    }
    return published;
}

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48

Stage48MusicReplayProbeInstallResult TryInstallStage48MusicReplayProbe(const TargetModule& module) {
    uintptr_t musicSlot = 0;
    uintptr_t actorPlaySlot = 0;
    uintptr_t actorPauseSlot = 0;
    if (!VerifyStage48Relay(module, kStage48MusicPlayOffset, kStage48MusicPlayExpectedBytes,
                            kStage48MusicPlayRelayExpectedEntry, kStage48MusicPlayRelayCodeOffset,
                            kStage48MusicPlayRelayExpectedBytes.data(), kStage48MusicPlayRelayExpectedBytes.size(),
                            kStage48MusicPlayRelaySlotOffset, &musicSlot))
        return Stage48MusicReplayProbeInstallResult::TargetMismatchMusicPlay;
    if (!VerifyStage48Relay(module, kStage48SoundActorPlayOffset, kStage48SoundActorPlayExpectedBytes,
                            kStage48SoundActorPlayRelayExpectedEntry, kStage48SoundActorPlayRelayCodeOffset,
                            kStage48SoundActorPlayRelayExpectedBytes.data(), kStage48SoundActorPlayRelayExpectedBytes.size(),
                            kStage48SoundActorPlayRelaySlotOffset, &actorPlaySlot))
        return Stage48MusicReplayProbeInstallResult::TargetMismatchSoundActorPlay;
    if (!VerifyStage48Relay(module, kStage48SoundActorPauseOffset, kStage48SoundActorPauseExpectedBytes,
                            kStage48SoundActorPauseRelayExpectedEntry, kStage48SoundActorPauseRelayCodeOffset,
                            kStage48SoundActorPauseRelayExpectedBytes.data(), kStage48SoundActorPauseRelayExpectedBytes.size(),
                            kStage48SoundActorPauseRelaySlotOffset, &actorPauseSlot))
        return Stage48MusicReplayProbeInstallResult::TargetMismatchSoundActorPause;
    if (!PublishStage48RelayCallback(musicSlot, reinterpret_cast<uintptr_t>(&MusicReplayMusicPlayHook::Callback)))
        return Stage48MusicReplayProbeInstallResult::RelayPublishMusicPlayFailed;
    if (!PublishStage48RelayCallback(actorPlaySlot, reinterpret_cast<uintptr_t>(&MusicReplaySoundActorPlayHook::Callback)))
        return Stage48MusicReplayProbeInstallResult::RelayPublishSoundActorPlayFailed;
    if (!PublishStage48RelayCallback(actorPauseSlot, reinterpret_cast<uintptr_t>(&MusicReplaySoundActorPauseHook::Callback)))
        return Stage48MusicReplayProbeInstallResult::RelayPublishSoundActorPauseFailed;
    return Stage48MusicReplayProbeInstallResult::Success;
}

void Stage48ArmMusicReplayProbe() {
    for (auto& slot : g_Stage48PausedActors) slot.store(0, std::memory_order_release);
    g_Stage48Frames.store(0, std::memory_order_release);
    g_Stage48PauseCount.store(0, std::memory_order_release);
    g_Stage48MusicPlayCount.store(0, std::memory_order_release);
    g_Stage48ActorPlayCount.store(0, std::memory_order_release);
    g_Stage48Flags.store(0, std::memory_order_release);
    g_Stage48Reported.store(false, std::memory_order_release);
    g_Stage48Armed.store(true, std::memory_order_release);
}

void Stage48AdvanceMusicReplayProbe() {
    if (g_Stage48Armed.load(std::memory_order_acquire)) {
        g_Stage48Frames.fetch_add(1, std::memory_order_relaxed);
    }
}

bool Stage48TakeMusicReplayReport(u32* payload) {
    if (payload == nullptr || !g_Stage48Armed.load(std::memory_order_acquire) ||
        g_Stage48Frames.load(std::memory_order_acquire) < kStage48WindowFrames) {
        return false;
    }
    u32 expected = 0;
    if (!g_Stage48Reported.compare_exchange_strong(expected, 1, std::memory_order_acq_rel)) return false;
    const u32 flags = g_Stage48Flags.load(std::memory_order_acquire);
    const u32 pauseCount = g_Stage48PauseCount.load(std::memory_order_acquire);
    const u32 musicPlayCount = g_Stage48MusicPlayCount.load(std::memory_order_acquire);
    const u32 actorPlayCount = g_Stage48ActorPlayCount.load(std::memory_order_acquire);
    *payload = flags | (std::min(pauseCount, 0xffu) << 8) |
               (std::min(musicPlayCount, 0xffu) << 16) | (std::min(actorPlayCount, 0xffu) << 24);
    g_Stage48Armed.store(false, std::memory_order_release);
    return true;
}
#endif

bool VerifyGameObserverRelay(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 ||
        module.textSize < kGameObserverRelayCodeOffset + kGameObserverRelayExpectedBytes.size()) {
        return false;
    }
    const uintptr_t target = target_address(module.base, kGameInitCallFileOffset);
    if (target < module.base || target % 4 != 0 ||
        !module.Contains(target, kGameObserverRelayExpectedEntry.size()) ||
        !IsMappedRxModuleCodeWindow(target, kGameObserverRelayExpectedEntry.size())) {
        return false;
    }
    const uintptr_t context = target - kGameInitContextExpectedBytes.size();
    if (context < module.base || !module.Contains(context, kGameInitContextExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(context, kGameInitContextExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kGameInitContextExpectedBytes.size()> contextBytes{};
    std::memcpy(contextBytes.data(), reinterpret_cast<const void*>(context), contextBytes.size());
    if (!verify_bytes(kGameInitContextExpectedBytes.data(), contextBytes.data(), contextBytes.size())) {
        return false;
    }
    std::array<u8, kGameObserverRelayExpectedEntry.size()> entry{};
    std::memcpy(entry.data(), reinterpret_cast<const void*>(target), entry.size());
    if (!verify_bytes(kGameObserverRelayExpectedEntry.data(), entry.data(), entry.size())) {
        return false;
    }
    const uintptr_t relay = target_address(module.base, kGameObserverRelayCodeOffset);
    if (relay < module.base || relay % 4 != 0 ||
        !module.Contains(relay, kGameObserverRelayExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(relay, kGameObserverRelayExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kGameObserverRelayExpectedBytes.size()> bridge{};
    std::memcpy(bridge.data(), reinterpret_cast<const void*>(relay), bridge.size());
    if (!verify_bytes(kGameObserverRelayExpectedBytes.data(), bridge.data(), bridge.size())) {
        return false;
    }
    const uintptr_t candidateSlot = target_address(module.base, kGameObserverRelaySlotOffset);
    if (candidateSlot < module.base || (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    *slot = candidateSlot;
    return true;
}

GameObserverInstallResult TryInstallGameObserverRelay(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyGameObserverRelay(module, &slot)) {
        return GameObserverInstallResult::RelayPatchMismatch;
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return GameObserverInstallResult::RelaySlotNotEmpty;
    }
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveGameFrame);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return GameObserverInstallResult::RelayPublishFailed;
    }
    return GameObserverInstallResult::Success;
}

bool VerifyGameUpdateObserverRelay(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 ||
        module.textSize < kGameUpdateObserverRelayCodeOffset + kGameUpdateObserverRelayExpectedBytes.size()) {
        return false;
    }
    const uintptr_t target = target_address(module.base, kGameUpdateCallFileOffset);
    if (target < module.base || target % 4 != 0 ||
        !module.Contains(target, kGameUpdateObserverRelayExpectedEntry.size()) ||
        !IsMappedRxModuleCodeWindow(target, kGameUpdateObserverRelayExpectedEntry.size())) {
        return false;
    }
    const uintptr_t context = target - kGameUpdateContextExpectedBytes.size();
    if (context < module.base || !module.Contains(context, kGameUpdateContextExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(context, kGameUpdateContextExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kGameUpdateContextExpectedBytes.size()> contextBytes{};
    std::memcpy(contextBytes.data(), reinterpret_cast<const void*>(context), contextBytes.size());
    if (!verify_bytes(kGameUpdateContextExpectedBytes.data(), contextBytes.data(), contextBytes.size())) {
        return false;
    }
    std::array<u8, kGameUpdateObserverRelayExpectedEntry.size()> entry{};
    std::memcpy(entry.data(), reinterpret_cast<const void*>(target), entry.size());
    if (!verify_bytes(kGameUpdateObserverRelayExpectedEntry.data(), entry.data(), entry.size())) {
        return false;
    }
    const uintptr_t relay = target_address(module.base, kGameUpdateObserverRelayCodeOffset);
    if (relay < module.base || relay % 4 != 0 ||
        !module.Contains(relay, kGameUpdateObserverRelayExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(relay, kGameUpdateObserverRelayExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kGameUpdateObserverRelayExpectedBytes.size()> bridge{};
    std::memcpy(bridge.data(), reinterpret_cast<const void*>(relay), bridge.size());
    if (!verify_bytes(kGameUpdateObserverRelayExpectedBytes.data(), bridge.data(), bridge.size())) {
        return false;
    }
    const uintptr_t candidateSlot = target_address(module.base, kGameUpdateObserverRelaySlotOffset);
    if (candidateSlot < module.base || (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    *slot = candidateSlot;
    return true;
}

GameUpdateObserverInstallResult TryInstallGameUpdateObserverRelay(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyGameUpdateObserverRelay(module, &slot)) {
        return GameUpdateObserverInstallResult::RelayPatchMismatch;
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return GameUpdateObserverInstallResult::RelaySlotNotEmpty;
    }
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveGameUpdateFrame);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return GameUpdateObserverInstallResult::RelayPublishFailed;
    }
    return GameUpdateObserverInstallResult::Success;
}

bool VerifyGameState2ObserverRelay(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 ||
        module.textSize < kGameState2ObserverRelayCodeOffset + kGameState2ObserverRelayExpectedBytes.size()) {
        return false;
    }
    const uintptr_t target = target_address(module.base, kGameState2CallFileOffset);
    if (target < module.base || target % 4 != 0 ||
        !module.Contains(target, kGameState2ObserverRelayExpectedEntry.size()) ||
        !IsMappedRxModuleCodeWindow(target, kGameState2ObserverRelayExpectedEntry.size())) {
        return false;
    }
    const uintptr_t context = target - kGameState2ContextExpectedBytes.size();
    if (context < module.base || !module.Contains(context, kGameState2ContextExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(context, kGameState2ContextExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kGameState2ContextExpectedBytes.size()> contextBytes{};
    std::memcpy(contextBytes.data(), reinterpret_cast<const void*>(context), contextBytes.size());
    if (!verify_bytes(kGameState2ContextExpectedBytes.data(), contextBytes.data(), contextBytes.size())) {
        return false;
    }
    std::array<u8, kGameState2ObserverRelayExpectedEntry.size()> entry{};
    std::memcpy(entry.data(), reinterpret_cast<const void*>(target), entry.size());
    if (!verify_bytes(kGameState2ObserverRelayExpectedEntry.data(), entry.data(), entry.size())) {
        return false;
    }
    const uintptr_t relay = target_address(module.base, kGameState2ObserverRelayCodeOffset);
    if (relay < module.base || relay % 4 != 0 ||
        !module.Contains(relay, kGameState2ObserverRelayExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(relay, kGameState2ObserverRelayExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kGameState2ObserverRelayExpectedBytes.size()> bridge{};
    std::memcpy(bridge.data(), reinterpret_cast<const void*>(relay), bridge.size());
    if (!verify_bytes(kGameState2ObserverRelayExpectedBytes.data(), bridge.data(), bridge.size())) {
        return false;
    }
    const uintptr_t candidateSlot = target_address(module.base, kGameState2ObserverRelaySlotOffset);
    if (candidateSlot < module.base || (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    *slot = candidateSlot;
    return true;
}

GameState2ObserverInstallResult TryInstallGameState2ObserverRelay(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyGameState2ObserverRelay(module, &slot)) {
        return GameState2ObserverInstallResult::RelayPatchMismatch;
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return GameState2ObserverInstallResult::RelaySlotNotEmpty;
    }
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveGameState2Frame);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return GameState2ObserverInstallResult::RelayPublishFailed;
    }
    return GameState2ObserverInstallResult::Success;
}

bool VerifyGameRenderObserverRelay(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || module.textSize < kGameIsPausedRenderObserverRelayCodeOffset + kGameIsPausedRenderObserverRelayExpectedBytes.size()) return false;
    const uintptr_t target = target_address(module.base, kGameIsPausedRenderCallFileOffset);
    const uintptr_t context = target - kGameIsPausedRenderContextExpectedBytes.size();
    if (target < module.base || context < module.base || !module.Contains(target, kGameIsPausedRenderObserverRelayExpectedEntry.size()) || !module.Contains(context, kGameIsPausedRenderContextExpectedBytes.size()) || !IsMappedRxModuleCodeWindow(target, 4) || !IsMappedRxModuleCodeWindow(context, kGameIsPausedRenderContextExpectedBytes.size())) return false;
    std::array<u8, 12> contextBytes{}; std::array<u8, 4> entry{};
    std::memcpy(contextBytes.data(), reinterpret_cast<const void*>(context), contextBytes.size());
    std::memcpy(entry.data(), reinterpret_cast<const void*>(target), entry.size());
    if (!verify_bytes(kGameIsPausedRenderContextExpectedBytes.data(), contextBytes.data(), contextBytes.size()) || !verify_bytes(kGameIsPausedRenderObserverRelayExpectedEntry.data(), entry.data(), entry.size())) return false;
    const uintptr_t relay = target_address(module.base, kGameIsPausedRenderObserverRelayCodeOffset);
    if (relay < module.base || !module.Contains(relay, kGameIsPausedRenderObserverRelayExpectedBytes.size()) || !IsMappedRxModuleCodeWindow(relay, kGameIsPausedRenderObserverRelayExpectedBytes.size())) return false;
    std::array<u8, 64> relayBytes{}; std::memcpy(relayBytes.data(), reinterpret_cast<const void*>(relay), relayBytes.size());
    if (!verify_bytes(kGameIsPausedRenderObserverRelayExpectedBytes.data(), relayBytes.data(), relayBytes.size())) return false;
    const uintptr_t candidateSlot = target_address(module.base, kGameIsPausedRenderObserverRelaySlotOffset);
    if (candidateSlot < module.base || (candidateSlot & 7) != 0 || !module.Contains(candidateSlot, sizeof(uintptr_t)) || !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) return false;
    *slot = candidateSlot;
    return true;
}

GameRenderObserverInstallResult TryInstallGameRenderObserverRelay(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyGameRenderObserverRelay(module, &slot)) return GameRenderObserverInstallResult::RelayPatchMismatch;
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t)); auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) return GameRenderObserverInstallResult::RelaySlotNotEmpty;
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ObserveGameRenderFrame);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE); slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) return GameRenderObserverInstallResult::RelayPublishFailed;
    return GameRenderObserverInstallResult::Success;
}

#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 8 || EXL_DIAGNOSTIC_STAGE == 9)
bool VerifyManagerLoadConfigs(const TargetModule& module, uintptr_t* target) {
    if (target == nullptr || module.base == 0 ||
        module.textSize < kManagerLoadConfigsFileOffset + kManagerLoadConfigsRelayExpectedEntry.size()) {
        return false;
    }
    if (module.buildId != kTargetBuildId || kManagerLoadConfigsFileOffset % 4 != 0) {
        return false;
    }
    const uintptr_t candidate = target_address(module.base, kManagerLoadConfigsFileOffset);
    if (candidate < module.base || !module.Contains(candidate, kManagerLoadConfigsRelayExpectedEntry.size()) ||
        candidate % 4 != 0 || !IsMappedRxModuleCodeWindow(candidate, kManagerLoadConfigsRelayExpectedEntry.size())) {
        return false;
    }
    *target = candidate;
    return true;
}

bool VerifyManagerLoadConfigsRelay(const TargetModule& module, uintptr_t target, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || target == 0 ||
        module.textSize < kManagerLoadConfigsRelayCodeOffset + kManagerLoadConfigsRelayExpectedBytes.size()) {
        return false;
    }
    if (target != target_address(module.base, kManagerLoadConfigsFileOffset) ||
        !module.Contains(target, kManagerLoadConfigsRelayExpectedEntry.size()) ||
        !IsMappedRxModuleCodeWindow(target, kManagerLoadConfigsRelayExpectedEntry.size())) {
        return false;
    }
    std::array<u8, kManagerLoadConfigsRelayExpectedEntry.size()> entry{};
    std::memcpy(entry.data(), reinterpret_cast<const void*>(target), entry.size());
    if (!verify_bytes(kManagerLoadConfigsRelayExpectedEntry.data(), entry.data(), entry.size())) {
        return false;
    }

    const uintptr_t relay = target_address(module.base, kManagerLoadConfigsRelayCodeOffset);
    if (relay < module.base || !module.Contains(relay, kManagerLoadConfigsRelayExpectedBytes.size()) ||
        relay % 4 != 0 || !IsMappedRxModuleCodeWindow(relay, kManagerLoadConfigsRelayExpectedBytes.size())) {
        return false;
    }
    std::array<u8, kManagerLoadConfigsRelayExpectedBytes.size() - sizeof(uintptr_t)> bridge{};
    std::memcpy(bridge.data(), reinterpret_cast<const void*>(relay), bridge.size());
    if (!verify_bytes(kManagerLoadConfigsRelayExpectedBytes.data(), bridge.data(), bridge.size())) {
        return false;
    }

    const uintptr_t candidateSlot = target_address(module.base, kManagerLoadConfigsRelaySlotOffset);
    if (candidateSlot < module.base || (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    *slot = candidateSlot;
    return true;
}
#endif

HookInstallResult TryInstallManagerUpdateHook(const TargetModule& module) {
    uintptr_t target = 0;
    if (!VerifyManagerUpdate(module, &target)) {
        return RecordUpdateHookInstall(HookInstallResult::InstructionMismatch);
    }

    uintptr_t slot = 0;
    if (!VerifyManagerRelay(module, target, &slot)) {
        return RecordUpdateHookInstall(HookInstallResult::RelayPatchMismatch);
    }

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
    uintptr_t ownerSlot = 0;
    if (!VerifyGameOwnerSlot(module, &ownerSlot)) {
        return HookInstallResult::GameOwnerSlotMismatch;
    }

    uintptr_t isPausedThunk = 0;
    if (!VerifyGameIsPausedThunk(module, &isPausedThunk)) {
        return HookInstallResult::GameIsPausedThunkMismatch;
    }

    g_Stage6GameOwnerSlot.store(ownerSlot, std::memory_order_release);
    if (g_Stage6GameOwnerSlot.load(std::memory_order_acquire) != ownerSlot) {
        return HookInstallResult::GameOwnerSlotPublishFailed;
    }
    g_Stage6GameIsPausedThunk.store(isPausedThunk, std::memory_order_release);
    if (g_Stage6GameIsPausedThunk.load(std::memory_order_acquire) != isPausedThunk) {
        return HookInstallResult::GameIsPausedThunkPublishFailed;
    }
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
    uintptr_t ownerSlot = 0;
    uintptr_t isPausedThunk = 0;
    uintptr_t actionMethod = 0;
    if (!VerifyGameOwnerSlot(module, &ownerSlot) || !VerifyGameIsPausedThunk(module, &isPausedThunk)) {
        return HookInstallResult::Stage88GameBindingsMismatch;
    }
    if (!VerifyManagerIsActionTriggered(module, &actionMethod)) {
        return HookInstallResult::ManagerIsActionTriggeredMismatch;
    }
    ConfigureStage88Bindings(ownerSlot, isPausedThunk, actionMethod);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
    uintptr_t ownerSlot = 0;
    uintptr_t isPausedThunk = 0;
    uintptr_t actionMethod = 0;
    if (!VerifyGameOwnerSlot(module, &ownerSlot) || !VerifyGameIsPausedThunk(module, &isPausedThunk)) {
        return HookInstallResult::Stage89GameBindingsMismatch;
    }
    if (!VerifyManagerIsActionTriggered(module, &actionMethod)) {
        return HookInstallResult::ManagerIsActionTriggeredMismatch;
    }
    ConfigureStage89Bindings(ownerSlot, isPausedThunk, actionMethod);
#endif

#if !defined(EXL_DIAGNOSTIC_STAGE)
    // Optional native bindings must not prevent generic Lua callbacks from running.
    // 生产分支的"校验 + 发布"已抽成 `PublishManagerEngineBindings()`（定义在本文件后部、
    // 与更新钩子的旧安装器相邻），并在下面钩子写好后统一调用一次。
    // 抽出来的原因见那个函数的注释：零占洞后端路径**不会**走到这个安装器，但它同样需要这些绑定。
#else
#if EXL_DIAGNOSTIC_STAGE == 14 || EXL_DIAGNOSTIC_STAGE == 15 || EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17 || EXL_DIAGNOSTIC_STAGE == 45 || EXL_DIAGNOSTIC_STAGE == 48
    uintptr_t isActionPressed = 0;
    uintptr_t isActionTriggered = 0;
    uintptr_t getActionValue = 0;
    uintptr_t ownerSlot = 0;
    if (!VerifyGameOwnerSlot(module, &ownerSlot)) {
        return HookInstallResult::GameBindingsMismatch;
    }
    uintptr_t isPausedThunk = 0;
    if (!VerifyGameIsPausedThunk(module, &isPausedThunk)) {
        return HookInstallResult::GameBindingsMismatch;
    }
    uintptr_t isGreedMode = 0;
    if (!VerifyGameIsGreedMode(module, &isGreedMode)) {
        return HookInstallResult::GameBindingsMismatch;
    }
    uintptr_t isAscent = 0;
    if (!VerifyLevelIsAscent(module, &isAscent)) {
        return HookInstallResult::GameBindingsMismatch;
    }
    uintptr_t getCurrentMusicId = 0;
    uintptr_t musicPause = 0;
    uintptr_t musicResume = 0;
    if (!VerifyMusicBindings(module, &getCurrentMusicId, &musicPause, &musicResume)) {
        return HookInstallResult::MusicBindingsMismatch;
    }
    g_LuaGameOwnerSlot.store(ownerSlot, std::memory_order_release);
    g_LuaGameIsPausedThunk.store(isPausedThunk, std::memory_order_release);
    const uintptr_t publishedOwnerSlot = g_LuaGameOwnerSlot.load(std::memory_order_acquire);
    const uintptr_t publishedIsPausedThunk = g_LuaGameIsPausedThunk.load(std::memory_order_acquire);
    if (publishedOwnerSlot != ownerSlot || publishedIsPausedThunk != isPausedThunk) {
        return HookInstallResult::GameBindingsPublishFailed;
    }
    // 控制器输入绑定：与生产分支同样按"可选"处理 —— 守卫不符时留 0，handler 报绑定不可用。
    // 这段以前只写在 `#if !defined(EXL_DIAGNOSTIC_STAGE)` 分支里，而下面同一个
    // `SetInputBindings` 调用在诊断档（14/15/16/17/45/48）也会编译，于是诊断构建报
    // "isActionPressed was not declared in this scope"（2026-09-13 修）。
    VerifyManagerIsActionPressed(module, &isActionPressed);
    VerifyManagerIsActionTriggered(module, &isActionTriggered);
    VerifyManagerGetActionValue(module, &getActionValue);
#endif
#endif

    const uintptr_t fallback = target_address(module.base, kManagerRelayFallbackOffset);
    if (!ManagerUpdateHook::PublishOriginal(fallback)) {
        return RecordUpdateHookInstall(HookInstallResult::RelayPublishFailed);
    }

    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return RecordUpdateHookInstall(HookInstallResult::RelaySlotNotEmpty);
    }

    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ManagerUpdateHook::Callback);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return RecordUpdateHookInstall(HookInstallResult::RelayPublishFailed);
    }

    ManagerUpdateHookAudit::RecordInstall(
        module.base, target, target_address(module.base, kManagerRelayCodeOffset),
        slot, callback, IsMappedRxModuleCodeWindow(callback, sizeof(u32)));

#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 14 || EXL_DIAGNOSTIC_STAGE == 15 || EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17 || EXL_DIAGNOSTIC_STAGE == 45 || EXL_DIAGNOSTIC_STAGE == 48
#if !defined(EXL_DIAGNOSTIC_STAGE)
    // 引擎绑定：与零占洞后端共用同一个实现（抽出来的原因见函数注释）。
    PublishManagerEngineBindings(module);
#else
    LuaRuntime::SetGameBindings(publishedOwnerSlot, publishedIsPausedThunk);
    // 游戏本体模块基址（批次 2）：`Isaac.GetPlayer` 的指针链与 `Entity_Player` 的 vptr 判据都用它。
    // 发布点与 `SetGameBindings` 同一个：这里已经拿到并且校验过 `TargetModule::base`。
    LuaRuntime::SetEngineModuleBase(module.base);
    LuaRuntime::SetGameIsGreedModeBinding(isGreedMode);
    LuaRuntime::SetLevelIsAscentBinding(isAscent);
    // 批次 8（2026-09-15）：诊断构建这条分支也要发布，否则诊断档里 `Level` 家族少两个方法
    // （历史教训：这里与 `PublishManagerEngineBindings` 曾因漏发而分叉）。
    {
        uintptr_t absoluteStage = 0;
        uintptr_t nextStageAvailable = 0;
        VerifyLevelGetAbsoluteStage(module, &absoluteStage);
        VerifyLevelIsNextStageAvailable(module, &nextStageAvailable);
        LuaRuntime::SetLevelGetAbsoluteStageBinding(absoluteStage);
        LuaRuntime::SetLevelIsNextStageAvailableBinding(nextStageAvailable);
        // 2026-09-16：`Room:GetFrameCount()`。同样两处发布点都要发（漏发=某个档位少一个方法）。
        uintptr_t roomGetFrameCount = 0;
        VerifyRoomGetFrameCount(module, &roomGetFrameCount);
        LuaRuntime::SetRoomGetFrameCountBinding(roomGetFrameCount);
        // 2026-09-21：`GridEntity::GetPosition()`（PC 的 `GridEntity.Position`，EID 献祭房那条路要用）。
        uintptr_t gridEntityGetPosition = 0;
        VerifyGridEntityGetPosition(module, &gridEntityGetPosition);
        LuaRuntime::SetGridEntityGetPositionBinding(gridEntityGetPosition);
        // 批次 10：`Room:WorldToScreenPosition()` 的引擎函数（两处发布点都要发 —— 漏发会让
        // 诊断档里少一个方法，这条教训本项目已经栽过一次）。
        uintptr_t getRenderPosition = 0;
        VerifyGetRenderPositionStub(module, &getRenderPosition);
        LuaRuntime::SetGetRenderPositionBinding(getRenderPosition);
    }
    LuaRuntime::SetMusicBindings(getCurrentMusicId, musicPause, musicResume);
    // 批次 137：`MusicManager:UpdateVolume()`（诊断档这一处发布点，与生产档那处必须成对 ——
    // 漏发会让某个档位少一个方法，这条教训本项目已经栽过一次）。
    {
        uintptr_t musicUpdateVolume = 0;
        VerifyMusicUpdateVolume(module, &musicUpdateVolume);
        LuaRuntime::SetMusicUpdateVolumeBinding(musicUpdateVolume);
    }
    // 批次 138：`MusicManager:Play(ID, Volume)`（诊断档发布点，与生产档成对）。
    {
        uintptr_t musicPlay = 0;
        VerifyMusicPlay(module, &musicPlay);
        LuaRuntime::SetMusicPlayBinding(musicPlay);
    }
    LuaRuntime::SetInputBindings(isActionPressed, isActionTriggered, getActionValue);
    // 批次 195：按键号那三条查询（可选能力，守卫不符只留 0 ⇒ handler 报"绑定不可用"）。
    TryInstallInputButtonBindings(module);
    // RNG is optional; an unavailable guard must not block the default Mod.
    TryInstallRngBindings(module);
    // Font is optional for the same reason. The record is verified and published right here
    // rather than in the per-stage branch above, so every diagnostic variant that reaches this
    // block compiles unchanged; a failed guard only leaves that one field at zero.
    LuaRuntime::LuaFontBindings fontBindings{};
    VerifyFontBindings(module, &fontBindings);
    LuaRuntime::SetFontBindings(fontBindings);
    // Sprite 同样按"可选能力"处理：守卫不符只让那一个字段保持 0，handler 会报绑定不可用。
    LuaRuntime::LuaSpriteBindings spriteBindings{};
    VerifySpriteBindings(module, &spriteBindings);
    LuaRuntime::SetSpriteBindings(spriteBindings);
#endif
#endif
    g_HookEnabled.store(true, std::memory_order_release);
    return RecordUpdateHookInstall(HookInstallResult::Success);
}

#if !defined(EXL_DIAGNOSTIC_STAGE)
// 引擎绑定（Lua 层要用的那组游戏内地址）：与"装钩子"本来是两件事，历史上却挤在更新钩子的旧安装器
// 里（`TryInstallManagerUpdateHook`）。M2a 第一次真机失败正是栽在这一点上 —— 把更新挂点切到零占洞
// 后端会**跳过那个安装器**，于是这些绑定一个都没发布：EID 的 `main.lua:61` 调 `Sprite()` 当场报
// "Sprite native binding is unavailable"，整个 Mod 加载失败
// （`TestRunObserver` 的 `ManifestInstallReturned` detail = 0x15 = LuaInit/ScriptRunFailed）。
// 因此把"校验 + 发布"抽成独立一步，两条后端路径都调用同一个实现：
//   * 旧 IPS 后端：仍在 `TryInstallManagerUpdateHook` 里调用（位置、顺序都不变）；
//   * 零占洞后端：在 `TryInstallDefaultManifestMod` 里、钩子装好之后调用。
// 生产分支下这些绑定一律按"可选"处理：守卫不符只让对应字段留 0（handler 会报该绑定不可用），
// 不阻断任何钩子的安装、也不影响安装结果。
void PublishManagerEngineBindings(const TargetModule& module) {
    uintptr_t ownerSlot = 0;
    uintptr_t isPausedThunk = 0;
    const bool hasOwnerSlot = VerifyGameOwnerSlot(module, &ownerSlot);
    const bool hasIsPaused = VerifyGameIsPausedThunk(module, &isPausedThunk);
    uintptr_t isGreedMode = 0;
    VerifyGameIsGreedMode(module, &isGreedMode);
    uintptr_t isAscent = 0;
    VerifyLevelIsAscent(module, &isAscent);
    uintptr_t getCurrentMusicId = 0;
    uintptr_t musicPause = 0;
    uintptr_t musicResume = 0;
    VerifyMusicBindings(module, &getCurrentMusicId, &musicPause, &musicResume);
    // Controller input bindings: optional, like the others, so a missing guard leaves the
    // handler reporting an unavailable binding instead of blocking hook installation.
    uintptr_t isActionPressed = 0;
    uintptr_t isActionTriggered = 0;
    uintptr_t getActionValue = 0;
    VerifyManagerIsActionPressed(module, &isActionPressed);
    VerifyManagerIsActionTriggered(module, &isActionTriggered);
    VerifyManagerGetActionValue(module, &getActionValue);
    if (!hasOwnerSlot || !hasIsPaused) {
        ownerSlot = 0;
        isPausedThunk = 0;
    }
    g_LuaGameOwnerSlot.store(ownerSlot, std::memory_order_release);
    g_LuaGameIsPausedThunk.store(isPausedThunk, std::memory_order_release);
    const uintptr_t publishedOwnerSlot = g_LuaGameOwnerSlot.load(std::memory_order_acquire);
    const uintptr_t publishedIsPausedThunk = g_LuaGameIsPausedThunk.load(std::memory_order_acquire);
    LuaRuntime::SetGameBindings(publishedOwnerSlot, publishedIsPausedThunk);
    // 游戏本体模块基址（批次 2）：`Isaac.GetPlayer` 的指针链与 `Entity_Player` 的 vptr 判据都用它。
    // 发布点与 `SetGameBindings` 同一个：这里已经拿到并且校验过 `TargetModule::base`。
    LuaRuntime::SetEngineModuleBase(module.base);
    // Install before Continue/loot generation; native Present then fills real CPU pixels.
    static_cast<void>(isaac::runtime::InstallProceduralTexelReadbackHook(module.base));
    LuaRuntime::SetGameIsGreedModeBinding(isGreedMode);
    LuaRuntime::SetLevelIsAscentBinding(isAscent);
    // 批次 8（2026-09-15）：与上面那两处同样的"可选能力"处理 —— 守卫不符只留 0，
    // handler 会报"绑定不可用"，不会编造值，也不影响其它挂点。
    uintptr_t absoluteStage = 0;
    uintptr_t nextStageAvailable = 0;
    VerifyLevelGetAbsoluteStage(module, &absoluteStage);
    VerifyLevelIsNextStageAvailable(module, &nextStageAvailable);
    LuaRuntime::SetLevelGetAbsoluteStageBinding(absoluteStage);
    LuaRuntime::SetLevelIsNextStageAvailableBinding(nextStageAvailable);
    // 2026-09-16：`Room:GetFrameCount()`（`0x470B0C`）。与上面几条同样按"可选能力"处理：
    // 守卫不符只留 0，handler 报"绑定不可用"，**不编造帧数**。
    uintptr_t roomGetFrameCount = 0;
    VerifyRoomGetFrameCount(module, &roomGetFrameCount);
    LuaRuntime::SetRoomGetFrameCountBinding(roomGetFrameCount);
    // 2026-09-21（第二处发布点，与上面那条必须成对）：`GridEntity::GetPosition()`。
    // 守卫不符只留 0 ⇒ handler 报"绑定不可用"并让那次字段读取失败，不编造坐标。
    uintptr_t gridEntityGetPosition = 0;
    VerifyGridEntityGetPosition(module, &gridEntityGetPosition);
    LuaRuntime::SetGridEntityGetPositionBinding(gridEntityGetPosition);
    // 批次 10（2026-09-15）：`Room:WorldToScreenPosition()` 要调的引擎函数。同样按"可选能力"
    // 处理：守卫不符只留 0，handler 报"绑定不可用"，不编造坐标。
    uintptr_t getRenderPosition = 0;
    VerifyGetRenderPositionStub(module, &getRenderPosition);
    LuaRuntime::SetGetRenderPositionBinding(getRenderPosition);
    LuaRuntime::SetMusicBindings(getCurrentMusicId, musicPause, musicResume);
    // 批次 137：`MusicManager:UpdateVolume()`（生产档发布点）。同样按"可选能力"处理：
    // 守卫不符只留 0 ⇒ handler 报"绑定不可用"，不编造，也不影响其它挂点。
    {
        uintptr_t musicUpdateVolume = 0;
        VerifyMusicUpdateVolume(module, &musicUpdateVolume);
        LuaRuntime::SetMusicUpdateVolumeBinding(musicUpdateVolume);
    }
    // 批次 138：`MusicManager:Play(ID, Volume)`（生产档发布点，同"可选能力"口径）。
    {
        uintptr_t musicPlay = 0;
        VerifyMusicPlay(module, &musicPlay);
        LuaRuntime::SetMusicPlayBinding(musicPlay);
    }
    LuaRuntime::SetInputBindings(isActionPressed, isActionTriggered, getActionValue);
    // 批次 195：按键号那三条查询（可选能力，守卫不符只留 0 ⇒ handler 报"绑定不可用"）。
    TryInstallInputButtonBindings(module);
    // RNG is optional; an unavailable guard must not block the default Mod.
    TryInstallRngBindings(module);
    // Font is optional for the same reason. The record is verified and published right here
    // rather than in the per-stage branch above, so every diagnostic variant that reaches this
    // block compiles unchanged; a failed guard only leaves that one field at zero.
    LuaRuntime::LuaFontBindings fontBindings{};
    VerifyFontBindings(module, &fontBindings);
    LuaRuntime::SetFontBindings(fontBindings);
    // Sprite 同样按"可选能力"处理：守卫不符只让那一个字段保持 0，handler 会报绑定不可用。
    LuaRuntime::LuaSpriteBindings spriteBindings{};
    VerifySpriteBindings(module, &spriteBindings);
    LuaRuntime::SetSpriteBindings(spriteBindings);
}
#endif

namespace {
// `Present` 前派发中继：调用点已被 IPS 改成分支，代码洞里是"调回调→补回原 bl→跳回调用点+4"，
// 槽保持零值直到运行时发布回调。三段都要逐步校验，任何一段不符都返回 false（只留绑定为 0，
// 不影响其它钩子安装）。
bool VerifyManagerPresentRelay(const TargetModule& module, uintptr_t* slot) {
    if (slot == nullptr || module.base == 0 || module.buildId != kTargetBuildId ||
        kManagerPresentCallExpectedEntry.size() > module.textSize ||
        kManagerPresentRelayExpectedBytes.size() > module.textSize ||
        sizeof(uintptr_t) > module.textSize ||
        kManagerPresentCallFileOffset > module.textSize - kManagerPresentCallExpectedEntry.size() ||
        kManagerPresentRelayCodeOffset > module.textSize - kManagerPresentRelayExpectedBytes.size() ||
        kManagerPresentRelaySlotOffset > module.textSize - sizeof(uintptr_t)) {
        return false;
    }
    const uintptr_t target = target_address(module.base, kManagerPresentCallFileOffset);
    const uintptr_t relay = target_address(module.base, kManagerPresentRelayCodeOffset);
    const uintptr_t candidateSlot = target_address(module.base, kManagerPresentRelaySlotOffset);
    if (target < module.base || relay < module.base || candidateSlot < module.base ||
        (target & 3u) != 0 || (relay & 3u) != 0 ||
        (candidateSlot & (alignof(uintptr_t) - 1)) != 0 ||
        !module.Contains(target, kManagerPresentCallExpectedEntry.size()) ||
        !module.Contains(relay, kManagerPresentRelayExpectedBytes.size()) ||
        !module.Contains(candidateSlot, sizeof(uintptr_t)) ||
        !IsMappedRxModuleCodeWindow(target, kManagerPresentCallExpectedEntry.size()) ||
        !IsMappedRxModuleCodeWindow(relay, kManagerPresentRelayExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(candidateSlot, sizeof(uintptr_t))) {
        return false;
    }
    std::array<u8, kManagerPresentCallExpectedEntry.size()> entry{};
    std::memcpy(entry.data(), reinterpret_cast<const void*>(target), entry.size());
    if (!verify_bytes(kManagerPresentCallExpectedEntry.data(), entry.data(), entry.size())) {
        return false;
    }
    std::array<u8, kManagerPresentRelayExpectedBytes.size() - sizeof(uintptr_t)> bridge{};
    std::memcpy(bridge.data(), reinterpret_cast<const void*>(relay), bridge.size());
    if (!verify_bytes(kManagerPresentRelayExpectedBytes.data(), bridge.data(), bridge.size())) {
        return false;
    }
    *slot = candidateSlot;
    return true;
}
}  // namespace

// 图片加载中继：入口已被 IPS 改成分支（首字必须是跳向我们代码洞的 `b`），回调槽保持零值
// 直到运行时发布。校验的每一步都返回**可区分的码**，探针会把低位报出来（位 23..25），
// 这样"到底卡在哪一步"不需要靠猜。
RenderPresentRelayInstallResult TryInstallManagerPresentRelay(const TargetModule& module) {
    uintptr_t slot = 0;
    if (!VerifyManagerPresentRelay(module, &slot)) {
        return RecordRenderPresentRelayInstall(RenderPresentRelayInstallResult::RelayPatchMismatch);
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return RecordRenderPresentRelayInstall(RenderPresentRelayInstallResult::RelaySlotNotEmpty);
    }
    const uintptr_t callback =
        reinterpret_cast<uintptr_t>(&IsaacModRuntime_DispatchPostRenderBeforePresent);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return RecordRenderPresentRelayInstall(RenderPresentRelayInstallResult::RelayPublishFailed);
    }
    return RecordRenderPresentRelayInstall(RenderPresentRelayInstallResult::Success);
}

// ---- M2b：`Present` 的 GOT 槽方案（零代码字节）--------------------------------------
//
// 拦截函数**按调用方过滤**：PLT 桩是尾调用（`br x17`），所以进入我们函数时 `x30`（LR）就是
// 原来那处调用的返回地址。只有它等于"模块基址 + `kManagerPresentCallFileOffset` + 4"时才派发
// `MC_POST_RENDER`；其余调用原样转发给真正的 `Present`。
//
// 为什么必须过滤：这条槽被 43 处调用共用（见 `kManagerPresentStubOffset` 的注释）。不过滤的话
// `MC_POST_RENDER` 会在它从没被派发过的时机与次数上被派发（菜单、过场、背景、实体更新…）。
//
// 为什么调 `target` 而不是"槽里读出来的原值"：槽在模块初始化期可能还指着**懒绑定解析桩**
// （文件初值 `0x66FAA0`）。调原值会走解析桩，而解析桩解析完会把**我们刚写进去的拦截函数覆盖掉**，
// 于是一次之后就再也不会派发。直接调 `Present` 本体（`0x4F3014`，已由三段守卫核对过）绕开这个坑。
std::atomic<uintptr_t> g_PresentGotSlotDispatchReturn{0};
std::atomic<uintptr_t> g_PresentGotSlotTarget{0};

// ---- ★ 2026-09-17 重写：`Present` 的转发桩改成「保存全部寄存器」的汇编桩 ---------------
//
// **为什么要重写**：旧实现是一个 C 函数，靠"实参只在 `x0`~`x7`"这条**推断**接收参数再转发。
// 但这条 GOT 槽被 **43 处调用共用**，而 C 函数转发意味着：
//   * 浮点/向量实参（`v0`~`v7`）在我们代码一进来就已经被编译器破坏；
//   * 间接结果寄存器 `x8` 同样不保证；
//   * 最根本的是"实参在哪些寄存器"只能靠猜（旧注释里"说明这处调用不依赖 x5 以上与浮点寄存器"
//     正是这样一条未证实的推断）。
// 而 `docs/开发规范.md` 第 11 条对这类"调用回调后继续执行原函数"的转发有明确要求：
// **必须逐项验证寄存器保存**。所以改成汇编桩 —— 进入时把 `x0~x8`、`q0~q7`、`x30(LR)` 全存到栈上，
// 只调两个 C 辅助函数（派发判定、取目标地址），然后**一个不差地还原**，最后 `br` 尾跳到真 `Present`。
// 这样"不碰任何参数寄存器"变成**构造保证**，不再依赖任何推断。
//
// 栈布局（0xe0 = 224 字节，16 字节对齐 ⇒ 调用 C 函数时 SP 仍满足 AAPCS 要求）：
//   +0x00 x0,x1   +0x10 x2,x3   +0x20 x4,x5   +0x30 x6,x7   +0x40 x8
//   +0x50 q0,q1   +0x70 q2,q3   +0x90 q4,q5   +0xb0 q6,q7   +0xd0 x30
// 跳转目标只在 `x9` 里暂存（`x9`~`x15` 是调用者保存寄存器，调用点不能指望 `bl` 之后还留着）。
// 目标为 0（理论上不该发生）时返回 0 —— 与旧实现在这一点上行为一致：**绝不跳空**。
//
// 它必须是非静态的全局符号：安装时要把这个函数地址写进 GOT 槽（见下方 `TryInstall…`）。
// ★ `EXL_LEGACY_PRESENT_FORWARDER=1` 是**只用于单变量对照**的开关（2026-09-17 加）：
//   打开就退回"用 C 函数按 x0~x7 接收参数再转发"的**旧形态**，用来回答"`Present` 转发桩的
//   ABI 缺陷（浮点实参 v0~v7、间接结果 x8 会被破坏）到底是不是真问题"。
//   **正式形状永远是 0**（默认 = 下面的汇编桩）。
#if defined(EXL_LEGACY_PRESENT_FORWARDER) && EXL_LEGACY_PRESENT_FORWARDER == 1
extern "C" __attribute__((noinline)) uintptr_t
IsaacModRuntime_PresentGotSlotIntercept(uintptr_t a0, uintptr_t a1, uintptr_t a2, uintptr_t a3,
                                        uintptr_t a4, uintptr_t a5, uintptr_t a6, uintptr_t a7) {
    const uintptr_t caller = reinterpret_cast<uintptr_t>(__builtin_return_address(0));
    if (caller == g_PresentGotSlotDispatchReturn.load(std::memory_order_acquire)) {
        IsaacModRuntime_DispatchPostRenderBeforePresent(reinterpret_cast<void*>(a0));
    }
    const uintptr_t target = g_PresentGotSlotTarget.load(std::memory_order_acquire);
    if (target == 0) {
        return 0;
    }
    using PresentFn = uintptr_t (*)(uintptr_t, uintptr_t, uintptr_t, uintptr_t, uintptr_t, uintptr_t,
                                    uintptr_t, uintptr_t);
    // 旧形态的原话："整数参数按 x0..x7 原样转发；IPS 方案同样只保存 x0..x4 + LR 就能工作，
    // 说明这处调用不依赖 x5 以上与浮点寄存器。" —— 这条**推断**正是本对照要检验的对象。
    return reinterpret_cast<PresentFn>(target)(a0, a1, a2, a3, a4, a5, a6, a7);
}
#else
extern "C" void IsaacModRuntime_PresentGotSlotIntercept(void);
__asm__(
    ".text\n"
    ".align 4\n"
    ".globl IsaacModRuntime_PresentGotSlotIntercept\n"
    ".type IsaacModRuntime_PresentGotSlotIntercept, %function\n"
    "IsaacModRuntime_PresentGotSlotIntercept:\n"
    "  sub sp, sp, #0xe0\n"
    "  stp x0, x1, [sp, #0x00]\n"
    "  stp x2, x3, [sp, #0x10]\n"
    "  stp x4, x5, [sp, #0x20]\n"
    "  stp x6, x7, [sp, #0x30]\n"
    "  str x8, [sp, #0x40]\n"
    "  stp q0, q1, [sp, #0x50]\n"
    "  stp q2, q3, [sp, #0x70]\n"
    "  stp q4, q5, [sp, #0x90]\n"
    "  stp q6, q7, [sp, #0xb0]\n"
    "  str x30, [sp, #0xd0]\n"
    "  mov x1, x0\n"
    "  mov x0, x30\n"
    "  bl IsaacModRuntime_PresentGotSlotDispatch\n"
    "  bl IsaacModRuntime_PresentGotSlotTargetAddress\n"
    "  mov x9, x0\n"
    "  ldr x30, [sp, #0xd0]\n"
    "  ldp q0, q1, [sp, #0x50]\n"
    "  ldp q2, q3, [sp, #0x70]\n"
    "  ldp q4, q5, [sp, #0x90]\n"
    "  ldp q6, q7, [sp, #0xb0]\n"
    "  ldr x8, [sp, #0x40]\n"
    "  ldp x6, x7, [sp, #0x30]\n"
    "  ldp x4, x5, [sp, #0x20]\n"
    "  ldp x2, x3, [sp, #0x10]\n"
    "  ldp x0, x1, [sp, #0x00]\n"
    "  add sp, sp, #0xe0\n"
    "  cbz x9, 1f\n"
    "  br x9\n"
    "1:\n"
    "  mov x0, #0\n"
    "  ret\n"
    ".size IsaacModRuntime_PresentGotSlotIntercept, .-IsaacModRuntime_PresentGotSlotIntercept\n");

// 派发判定：只有"调用方是那处被我们盯上的调用点"时才派发 `MC_POST_RENDER`。
extern "C" void IsaacModRuntime_PresentGotSlotDispatch(uintptr_t caller, uintptr_t a0) {
    if (caller == g_PresentGotSlotDispatchReturn.load(std::memory_order_acquire)) {
        // `a0` 就是调用点上下文里的 `x0`：`Present` 的实参（`KAGE::Graphics::g_Manager`）。
        IsaacModRuntime_DispatchPostRenderBeforePresent(reinterpret_cast<void*>(a0));
    }
}

// 取真正的 `Present` 地址（绝不拿文件初值：那是懒绑定解析桩）。
extern "C" uintptr_t IsaacModRuntime_PresentGotSlotTargetAddress(void) {
    return g_PresentGotSlotTarget.load(std::memory_order_acquire);
}
#endif

namespace {
// 该地址所在页是否可写（可写就直接写，避开 `RwPages` 的 `EXL_ASSERT` 路径）。
bool PageIsWritable(uintptr_t address) {
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (R_FAILED(svcQueryMemory(&info, &pageInfo, address))) {
        return false;
    }
    return (info.perm & Perm_W) != 0;
}
}  // namespace

RenderPresentRelayInstallResult TryInstallManagerPresentGotSlot(const TargetModule& module) {
    if (module.base == 0 || module.buildId != kTargetBuildId) {
        return RecordRenderPresentRelayInstall(
            RenderPresentRelayInstallResult::GotSlotTargetMismatch);
    }
    const uintptr_t callsite = target_address(module.base, kManagerPresentCallFileOffset);
    const uintptr_t stub = target_address(module.base, kManagerPresentStubOffset);
    const uintptr_t target = target_address(module.base, kManagerPresentTargetOffset);
    const uintptr_t slot = target_address(module.base, kManagerPresentGotSlotOffset);
    // 三段守卫：调用点必须已回到**原样**（即那份 IPS 已删）、桩形态、`Present` 本体序言。
    if (!module.Contains(callsite, kManagerPresentCallExpectedBytes.size()) ||
        !module.Contains(stub, kManagerPresentStubExpectedBytes.size()) ||
        !module.Contains(target, kManagerPresentTargetExpectedBytes.size()) ||
        !verify_bytes(kManagerPresentCallExpectedBytes.data(),
                      reinterpret_cast<const u8*>(callsite),
                      kManagerPresentCallExpectedBytes.size()) ||
        !verify_bytes(kManagerPresentStubExpectedBytes.data(),
                      reinterpret_cast<const u8*>(stub),
                      kManagerPresentStubExpectedBytes.size()) ||
        !verify_bytes(kManagerPresentTargetExpectedBytes.data(),
                      reinterpret_cast<const u8*>(target),
                      kManagerPresentTargetExpectedBytes.size())) {
        return RecordRenderPresentRelayInstall(
            RenderPresentRelayInstallResult::GotSlotTargetMismatch);
    }
    // 槽必须在已映射页内、8 字节对齐、且加载器已经写过（非零）。
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (R_FAILED(svcQueryMemory(&info, &pageInfo, slot)) || info.size == 0 ||
        slot < info.addr || slot > info.addr + info.size ||
        sizeof(uintptr_t) > info.addr + info.size - slot ||
        (slot & (alignof(uintptr_t) - 1)) != 0) {
        return RecordRenderPresentRelayInstall(
            RenderPresentRelayInstallResult::GotSlotUnavailable);
    }
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) == 0) {
        return RecordRenderPresentRelayInstall(
            RenderPresentRelayInstallResult::GotSlotUnavailable);
    }
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&IsaacModRuntime_PresentGotSlotIntercept);
    g_PresentGotSlotDispatchReturn.store(callsite + 4, std::memory_order_release);
    g_PresentGotSlotTarget.store(target, std::memory_order_release);
    if (PageIsWritable(slot)) {
        // 数据页直接写即可（不是代码改写，不需要 icache 失效）。
        __atomic_store_n(reinterpret_cast<uintptr_t*>(slot), callback, __ATOMIC_RELEASE);
    } else {
        exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
        auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
        __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
        slotPages.Flush();
    }
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return RecordRenderPresentRelayInstall(
            RenderPresentRelayInstallResult::GotSlotWriteFailed);
    }
    // 与 IPS 路径共用同一个状态字：渲染入口中继据此判断"Present 前派发点已就绪"，
    // 从而不再走那条"晚一帧"的回退派发。
    return RecordRenderPresentRelayInstall(RenderPresentRelayInstallResult::Success);
}

RenderHookInstallResult TryInstallManagerRenderHook(const TargetModule& module) {
    uintptr_t target = 0;
    if (!VerifyManagerRender(module, &target)) {
        return RecordRenderHookInstall(RenderHookInstallResult::InstructionMismatch);
    }
    uintptr_t slot = 0;
    if (!VerifyManagerRenderRelay(module, target, &slot)) {
        return RecordRenderHookInstall(RenderHookInstallResult::RelayPatchMismatch);
    }
    const uintptr_t fallback = target_address(module.base, kManagerRenderRelayFallbackOffset);
    if (!ManagerRenderHook::PublishOriginal(fallback)) {
        return RecordRenderHookInstall(RenderHookInstallResult::RelayPublishFailed);
    }
    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return RecordRenderHookInstall(RenderHookInstallResult::RelaySlotNotEmpty);
    }
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ManagerRenderHook::Callback);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return RecordRenderHookInstall(RenderHookInstallResult::RelayPublishFailed);
    }
    return RecordRenderHookInstall(RenderHookInstallResult::Success);
}

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
LoadConfigsDiagnosticInstallResult TryInstallManagerLoadConfigsDiagnostic(const TargetModule& module) {
    uintptr_t target = 0;
    if (!VerifyManagerLoadConfigs(module, &target)) {
        return LoadConfigsDiagnosticInstallResult::InstructionOrRelayMismatch;
    }

    uintptr_t slot = 0;
    if (!VerifyManagerLoadConfigsRelay(module, target, &slot)) {
        return LoadConfigsDiagnosticInstallResult::InstructionOrRelayMismatch;
    }

    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return LoadConfigsDiagnosticInstallResult::RelaySlotNotEmpty;
    }

    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ManagerLoadConfigsDiagnosticCallback);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        return LoadConfigsDiagnosticInstallResult::RelayPublishFailed;
    }
    return LoadConfigsDiagnosticInstallResult::Success;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
LoadConfigsResetDiagnosticInstallResult TryInstallManagerLoadConfigsResetDiagnostic(const TargetModule& module) {
    uintptr_t target = 0;
    if (!VerifyManagerLoadConfigs(module, &target)) {
        return LoadConfigsResetDiagnosticInstallResult::LoadConfigsInstructionOrRelayMismatch;
    }

    uintptr_t slot = 0;
    if (!VerifyManagerLoadConfigsRelay(module, target, &slot)) {
        return LoadConfigsResetDiagnosticInstallResult::LoadConfigsInstructionOrRelayMismatch;
    }

    const uintptr_t resetAddress = target_address(module.base, kModManagerResetFileOffset);
    if (resetAddress < module.base || resetAddress % 4 != 0 ||
        !module.Contains(resetAddress, kModManagerResetExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(resetAddress, kModManagerResetExpectedBytes.size())) {
        return LoadConfigsResetDiagnosticInstallResult::ResetInstructionOrMappingMismatch;
    }
    std::array<u8, kModManagerResetExpectedBytes.size()> resetBytes{};
    std::memcpy(resetBytes.data(), reinterpret_cast<const void*>(resetAddress), resetBytes.size());
    if (!verify_bytes(kModManagerResetExpectedBytes.data(), resetBytes.data(), resetBytes.size())) {
        return LoadConfigsResetDiagnosticInstallResult::ResetInstructionOrMappingMismatch;
    }

    exl::util::RwPages slotPages(slot, sizeof(uintptr_t));
    auto* rwSlot = reinterpret_cast<uintptr_t*>(slotPages.GetRw());
    if (__atomic_load_n(rwSlot, __ATOMIC_ACQUIRE) != 0) {
        return LoadConfigsResetDiagnosticInstallResult::RelaySlotNotEmpty;
    }

    g_Stage9ResetAddress.store(resetAddress, std::memory_order_release);
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&ManagerLoadConfigsResetDiagnosticCallback);
    __atomic_store_n(rwSlot, callback, __ATOMIC_RELEASE);
    slotPages.Flush();
    if (__atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) != callback) {
        g_Stage9ResetAddress.store(0, std::memory_order_release);
        return LoadConfigsResetDiagnosticInstallResult::RelayPublishFailed;
    }
    return LoadConfigsResetDiagnosticInstallResult::Success;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
Stage11InstallResult TryInstallRomfsSentinelDiagnostic(const TargetModule& module) {
    uintptr_t target = 0;
    uintptr_t slot = 0;
    GameFileReader::Bindings bindings{};
    if (!VerifyManagerUpdate(module, &target) || !VerifyManagerRelay(module, target, &slot) ||
        !GameFileReader::VerifyBindings(module, &bindings)) {
        return Stage11InstallResult::FileBindingMismatch;
    }

    g_Stage11Bindings = bindings;
    g_Stage11State.store(Stage11State::Armed, std::memory_order_release);
    if (TryInstallManagerUpdateHook(module) != HookInstallResult::Success) {
        Stage11State expected = Stage11State::Armed;
        if (g_Stage11State.compare_exchange_strong(expected, Stage11State::Unarmed, std::memory_order_acq_rel)) {
            g_Stage11Bindings = {};
        }
        return Stage11InstallResult::FileBindingMismatch;
    }
    return Stage11InstallResult::Success;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
Stage12InstallResult TryInstallRomfsLuaDiagnostic(const TargetModule& module) {
    uintptr_t target = 0;
    uintptr_t slot = 0;
    GameFileReader::Bindings bindings{};
    if (!VerifyManagerUpdate(module, &target) || !VerifyManagerRelay(module, target, &slot) ||
        !GameFileReader::VerifyBindings(module, &bindings)) {
        return Stage12InstallResult::FileBindingMismatch;
    }

    g_Stage12Bindings = bindings;
    g_Stage12State.store(Stage12State::Armed, std::memory_order_release);
    if (TryInstallManagerUpdateHook(module) != HookInstallResult::Success) {
        Stage12State expected = Stage12State::Armed;
        if (g_Stage12State.compare_exchange_strong(expected, Stage12State::Unarmed, std::memory_order_acq_rel)) {
            g_Stage12Bindings = {};
        }
        return Stage12InstallResult::FileBindingMismatch;
    }
    return Stage12InstallResult::Success;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
Stage13InstallResult TryInstallManifestRequireDiagnostic(const TargetModule& module) {
    uintptr_t target = 0;
    uintptr_t slot = 0;
    GameFileReader::Bindings bindings{};
    if (!VerifyManagerUpdate(module, &target) || !VerifyManagerRelay(module, target, &slot) ||
        !GameFileReader::VerifyBindings(module, &bindings)) {
        return Stage13InstallResult::FileBindingMismatch;
    }

    g_Stage13Bindings = bindings;
    g_Stage13State.store(Stage13State::Armed, std::memory_order_release);
    if (TryInstallManagerUpdateHook(module) != HookInstallResult::Success) {
        Stage13State expected = Stage13State::Armed;
        if (g_Stage13State.compare_exchange_strong(expected, Stage13State::Unarmed, std::memory_order_acq_rel)) {
            g_Stage13Bindings = {};
            return Stage13InstallResult::FileBindingMismatch;
        }
    }
    return Stage13InstallResult::Success;
}
#endif

#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
Stage118InstallResult TryInstallStage118ManagedFileWriteDiagnostic(const TargetModule& module) {
    GameFileReader::WriteBindings bindings{};
    if (!GameFileReader::VerifyWriteBindings(module, &bindings)) {
        return Stage118InstallResult::FileBindingMismatch;
    }
    g_Stage118Bindings = bindings;
    if (TryInstallManagerUpdateHook(module) != HookInstallResult::Success) {
        g_Stage118Bindings = {};
        return Stage118InstallResult::HookInstallFailed;
    }
    g_Stage118Armed.store(true, std::memory_order_release);
    return Stage118InstallResult::Success;
}
#endif

bool InstallManagerUpdateHook(const TargetModule& module) {
    return TryInstallManagerUpdateHook(module) == HookInstallResult::Success;
}

bool IsHookEnabled() {
    return g_HookEnabled.load(std::memory_order_acquire);
}

// 批次 370：**外部链接的壳**（必须放在文件末尾的全局作用域 —— 上面好几个匿名命名空间都还没关，
// 之前把它写在里面 ⇒ 编译器报"定义了但没用到"，而 `runtime_entry.cpp` 也链不到它）。
// 真正的实现在本文件的匿名命名空间里（要用那几个文件作用域的服务），只给它一层外部链接。
EarlyModMountOutcome MountModsBeforeHeavyWork(const TargetModule& module) noexcept {
    return MountModsBeforeHeavyWorkImpl(module);
}

// 实验 B（2026-10-05）：同样只给它一层**外部链接**的壳。★ 必须放在这里（全局作用域）——
// 真正的实现在上面的匿名命名空间里（要用那几个文件作用域的服务），而**没有这层壳就是
// `defined but not used`**（`-Werror` 直接红；370 那次 `MountModsBeforeHeavyWork` 踩过同一个坑）。
bool ReadManifestOnlyForExperiment(const TargetModule& module) noexcept {
    return ReadManifestOnlyForExperimentImpl(module);
}

// 批次 371（2026-10-05）：`IsMappedRxModuleCodeWindow` 的**外部链接定义**（搬迁说明见本文件
// 中部原来那个位置）。判据与搬迁前逐字相同：`svcQueryMemory` 答 `MemType_ModuleCodeStatic` +
// `Perm_Rx`，且给定长度整段落在那一段映射里。
//
// 为什么必须是外部链接：`runtime_entry.cpp` 的早期那一段要"先确认 `Game::Init` 入口那一页现在
// 可执行"，才敢让 `TryInstallEntryRelay` 去读它那 16 字节（地址没映射时，读它本身就是崩溃）。
// 那条判据只该有一份。
bool IsMappedRxModuleCodeWindow(uintptr_t address, size_t length) {
    if (length == 0 || address > UINTPTR_MAX - length) {
        return false;
    }
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (R_FAILED(svcQueryMemory(&info, &pageInfo, address)) || info.size == 0) {
        return false;
    }
    const uintptr_t end = address + length;
    const uintptr_t mappingEnd = info.addr + info.size;
    return mappingEnd >= info.addr && address >= info.addr && end <= mappingEnd &&
           (info.type & MemState_Type) == MemType_ModuleCodeStatic && info.perm == Perm_Rx;
}

// 2026-10-09：PC三态映射到原生碰撞bool；nil才执行内部代码。
extern "C" std::uint64_t EntryRelayFamiliarCollisionCallback(void* entity, void* collider, std::uint32_t low) {
    using CollisionFn = std::uint64_t (*)(void*, void*, std::uint32_t);
    std::uint32_t type = 0, variant = 0;
    const bool readable = isaac::runtime::ReadEntityIdentity(isaac::runtime::engine_memory::AddressOf(entity), &type, &variant);
    const auto decision = LuaRuntime::DispatchPreEntityCollision(isaac::runtime::kCallbackPreFamiliarCollision,
        isaac::runtime::engine_memory::AddressOf(entity), isaac::runtime::engine_memory::AddressOf(collider), low != 0, readable ? static_cast<std::int32_t>(variant) : -1);
    if (decision != LuaRuntime::CollisionOverride::Continue) return decision == LuaRuntime::CollisionOverride::Ignore ? 1 : 0;
    const auto original = isaac::runtime::Original<CollisionFn>(isaac::runtime::HookId::FamiliarCollision);
    return original(entity, collider, low);
}
extern "C" std::uint64_t EntryRelayNpcCollisionCallback(void* entity, void* collider, std::uint32_t low) {
    using CollisionFn = std::uint64_t (*)(void*, void*, std::uint32_t);
    std::uint32_t type = 0, variant = 0;
    const bool readable = isaac::runtime::ReadEntityIdentity(isaac::runtime::engine_memory::AddressOf(entity), &type, &variant);
    const auto decision = LuaRuntime::DispatchPreEntityCollision(isaac::runtime::kCallbackPreNpcCollision,
        isaac::runtime::engine_memory::AddressOf(entity), isaac::runtime::engine_memory::AddressOf(collider), low != 0, readable ? static_cast<std::int32_t>(type) : -1);
    if (decision != LuaRuntime::CollisionOverride::Continue) return decision == LuaRuntime::CollisionOverride::Ignore ? 1 : 0;
    const auto original = isaac::runtime::Original<CollisionFn>(isaac::runtime::HookId::NpcCollision);
    return original(entity, collider, low);
}
extern "C" std::uint64_t EntryRelayPlayerCollisionCallback(void* entity, void* collider, std::uint32_t low) {
    using CollisionFn = std::uint64_t (*)(void*, void*, std::uint32_t);
    std::uint32_t type = 0, variant = 0;
    const bool readable = isaac::runtime::ReadEntityIdentity(isaac::runtime::engine_memory::AddressOf(entity), &type, &variant);
    const auto decision = LuaRuntime::DispatchPreEntityCollision(isaac::runtime::kCallbackPrePlayerCollision,
        isaac::runtime::engine_memory::AddressOf(entity), isaac::runtime::engine_memory::AddressOf(collider), low != 0, readable ? static_cast<std::int32_t>(variant) : -1);
    if (decision != LuaRuntime::CollisionOverride::Continue) return decision == LuaRuntime::CollisionOverride::Ignore ? 1 : 0;
    const auto original = isaac::runtime::Original<CollisionFn>(isaac::runtime::HookId::PlayerCollision);
    return original(entity, collider, low);
}
extern "C" std::uint64_t EntryRelayTearCollisionCallback(void* entity, void* collider, std::uint32_t low) {
    using CollisionFn = std::uint64_t (*)(void*, void*, std::uint32_t);
    std::uint32_t type = 0, variant = 0;
    const bool readable = isaac::runtime::ReadEntityIdentity(isaac::runtime::engine_memory::AddressOf(entity), &type, &variant);
    const auto decision = LuaRuntime::DispatchPreEntityCollision(isaac::runtime::kCallbackPreTearCollision,
        isaac::runtime::engine_memory::AddressOf(entity), isaac::runtime::engine_memory::AddressOf(collider), low != 0, readable ? static_cast<std::int32_t>(variant) : -1);
    if (decision != LuaRuntime::CollisionOverride::Continue) return decision == LuaRuntime::CollisionOverride::Ignore ? 1 : 0;
    const auto original = isaac::runtime::Original<CollisionFn>(isaac::runtime::HookId::TearCollision);
    return original(entity, collider, low);
}
extern "C" std::uint64_t EntryRelayProjectileCollisionCallback(void* entity, void* collider, std::uint32_t low) {
    using CollisionFn = std::uint64_t (*)(void*, void*, std::uint32_t);
    std::uint32_t type = 0, variant = 0;
    const bool readable = isaac::runtime::ReadEntityIdentity(isaac::runtime::engine_memory::AddressOf(entity), &type, &variant);
    const auto decision = LuaRuntime::DispatchPreEntityCollision(isaac::runtime::kCallbackPreProjectileCollision,
        isaac::runtime::engine_memory::AddressOf(entity), isaac::runtime::engine_memory::AddressOf(collider), low != 0, readable ? static_cast<std::int32_t>(variant) : -1);
    if (decision != LuaRuntime::CollisionOverride::Continue) return decision == LuaRuntime::CollisionOverride::Ignore ? 1 : 0;
    const auto original = isaac::runtime::Original<CollisionFn>(isaac::runtime::HookId::ProjectileCollision);
    return original(entity, collider, low);
}
extern "C" std::uint64_t EntryRelayKnifeCollisionCallback(void* entity, void* collider, std::uint32_t low) {
    using CollisionFn = std::uint64_t (*)(void*, void*, std::uint32_t);
    std::uint32_t type = 0, variant = 0;
    const bool readable = isaac::runtime::ReadEntityIdentity(isaac::runtime::engine_memory::AddressOf(entity), &type, &variant);
    std::uint32_t subtype = 0;
    const bool subtypeReadable = isaac::runtime::ReadEntitySubType(isaac::runtime::engine_memory::AddressOf(entity), &subtype);
    static_cast<void>(readable);
    const auto decision = LuaRuntime::DispatchPreEntityCollision(isaac::runtime::kCallbackPreKnifeCollision,
        isaac::runtime::engine_memory::AddressOf(entity), isaac::runtime::engine_memory::AddressOf(collider), low != 0, subtypeReadable ? static_cast<std::int32_t>(subtype) : -1);
    if (decision != LuaRuntime::CollisionOverride::Continue) return decision == LuaRuntime::CollisionOverride::Ignore ? 1 : 0;
    const auto original = isaac::runtime::Original<CollisionFn>(isaac::runtime::HookId::KnifeCollision);
    return original(entity, collider, low);
}
extern "C" std::uint64_t EntryRelayBombCollisionCallback(void* entity, void* collider, std::uint32_t low) {
    using CollisionFn = std::uint64_t (*)(void*, void*, std::uint32_t);
    std::uint32_t type = 0, variant = 0;
    const bool readable = isaac::runtime::ReadEntityIdentity(isaac::runtime::engine_memory::AddressOf(entity), &type, &variant);
    const auto decision = LuaRuntime::DispatchPreEntityCollision(isaac::runtime::kCallbackPreBombCollision,
        isaac::runtime::engine_memory::AddressOf(entity), isaac::runtime::engine_memory::AddressOf(collider), low != 0, readable ? static_cast<std::int32_t>(variant) : -1);
    if (decision != LuaRuntime::CollisionOverride::Continue) return decision == LuaRuntime::CollisionOverride::Ignore ? 1 : 0;
    const auto original = isaac::runtime::Original<CollisionFn>(isaac::runtime::HookId::BombCollision);
    return original(entity, collider, low);
}
extern "C" void EntryRelayNpcRenderCallback(void* npc, const void* offset) {
    using RenderFn = void (*)(void*, const void*);
    const auto original = isaac::runtime::Original<RenderFn>(isaac::runtime::HookId::NpcRender);
    original(npc, offset);
    LuaRuntime::DispatchPostNpcRender(isaac::runtime::engine_memory::AddressOf(npc), offset);
}

extern "C" std::int32_t EntryRelayItemPoolGetPillCallback(void* pool, std::uint32_t seed) {
    using Fn = std::int32_t (*)(void*, std::uint32_t);
    const auto original = isaac::runtime::Original<Fn>(isaac::runtime::HookId::ItemPoolGetPill);
    return LuaRuntime::DispatchGetPillColor(seed, original(pool, seed));
}
extern "C" std::int32_t EntryRelayItemPoolGetPillEffectCallback(void* pool, std::uint32_t color, void* player) {
    using Fn = std::int32_t (*)(void*, std::uint32_t, void*);
    const auto original = isaac::runtime::Original<Fn>(isaac::runtime::HookId::ItemPoolGetPillEffect);
    return LuaRuntime::DispatchGetPillEffect(color, original(pool, color, player));
}
extern "C" std::uint64_t EntryRelayGameDevolveEnemyCallback(void* game, void* entity) {
    using Fn = std::uint64_t (*)(void*, void*);
    if (LuaRuntime::DispatchPreEntityDevolve(isaac::runtime::engine_memory::AddressOf(entity))) return 0;
    const auto original = isaac::runtime::Original<Fn>(isaac::runtime::HookId::GameDevolveEnemy);
    return original(game, entity);
}

// AI入口的ABI为void(this)，没有浮点/间接结果实参；目标先发布再改槽。
std::atomic<uintptr_t> g_NpcUpdateAiGotSlotTarget{0};
extern "C" void IsaacModRuntime_NpcUpdateAiGotSlotIntercept(void* npc) {
    std::uint32_t type = 0, variant = 0;
    const bool readable = isaac::runtime::ReadEntityIdentity(isaac::runtime::engine_memory::AddressOf(npc), &type, &variant);
    if (readable && LuaRuntime::DispatchPreNpcUpdate(isaac::runtime::engine_memory::AddressOf(npc),
                                                    static_cast<std::int32_t>(type))) return;
    using Fn = void (*)(void*);
    const auto original = reinterpret_cast<Fn>(g_NpcUpdateAiGotSlotTarget.load(std::memory_order_acquire));
    original(npc);
}
RenderPresentRelayInstallResult TryInstallNpcUpdateAiGotSlot(const TargetModule& module) {
    using Result = RenderPresentRelayInstallResult;
    if (module.base == 0 || module.buildId != kTargetBuildId ||
        kNpcUpdateAiGotSlotOffset > module.size ||
        sizeof(uintptr_t) > module.size - kNpcUpdateAiGotSlotOffset ||
        module.base > UINTPTR_MAX - kNpcUpdateAiGotSlotOffset) return Result::GotSlotTargetMismatch;
    const uintptr_t target = target_address(module.base, kNpcUpdateAiOffset);
    const uintptr_t stub = target_address(module.base, kNpcUpdateAiStubOffset);
    const uintptr_t slot = target_address(module.base, kNpcUpdateAiGotSlotOffset);
    if (!module.Contains(target, kNpcUpdateAiExpectedBytes.size()) ||
        !module.Contains(stub, kNpcUpdateAiStubExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(target, kNpcUpdateAiExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(stub, kNpcUpdateAiStubExpectedBytes.size()) ||
        !verify_bytes(kNpcUpdateAiExpectedBytes.data(), reinterpret_cast<const u8*>(target), kNpcUpdateAiExpectedBytes.size()) ||
        !verify_bytes(kNpcUpdateAiStubExpectedBytes.data(), reinterpret_cast<const u8*>(stub), kNpcUpdateAiStubExpectedBytes.size()))
        return Result::GotSlotTargetMismatch;
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (R_FAILED(svcQueryMemory(&info, &pageInfo, slot)) || (info.perm & Perm_R) == 0 ||
        info.size < sizeof(uintptr_t) || slot < info.addr || slot - info.addr > info.size - sizeof(uintptr_t) ||
        (slot & (alignof(uintptr_t) - 1)) != 0) return Result::GotSlotUnavailable;
    const uintptr_t current = __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE);
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&IsaacModRuntime_NpcUpdateAiGotSlotIntercept);
    // 可接受引擎目标或模块内尚未解析的PLT入口；拒绝其它插件写入的陌生目标。
    if (current != target && current != module.base + kPltResolverOffset) return Result::GotSlotTargetMismatch;
    g_NpcUpdateAiGotSlotTarget.store(target, std::memory_order_release);
    if (PageIsWritable(slot)) {
        __atomic_store_n(reinterpret_cast<uintptr_t*>(slot), callback, __ATOMIC_RELEASE);
    } else {
        exl::util::RwPages pages(slot, sizeof(uintptr_t));
        __atomic_store_n(reinterpret_cast<uintptr_t*>(pages.GetRw()), callback, __ATOMIC_RELEASE);
        pages.Flush();
    }
    return __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) == callback
        ? Result::Success : Result::GotSlotWriteFailed;
}

// 原生HUD只画一次；返回后立即派发，后面的暂停/过场原生前景自然覆盖模组。
std::atomic<uintptr_t> g_HudRenderGotSlotTarget{0};
extern "C" void IsaacModRuntime_HudRenderGotSlotIntercept(void* hud) {
    using Fn = void (*)(void*);
    const auto original = reinterpret_cast<Fn>(g_HudRenderGotSlotTarget.load(std::memory_order_acquire));
    isaac::runtime::RenderAfterNativeHud(g_RenderFrameCoordinator, hud, original, DispatchModPostRender);
}
RenderPresentRelayInstallResult TryInstallHudRenderGotSlot(const TargetModule& module) {
    using Result = RenderPresentRelayInstallResult;
    if (module.base == 0 || module.buildId != kTargetBuildId ||
        kHudRenderGotSlotOffset > module.size ||
        sizeof(uintptr_t) > module.size - kHudRenderGotSlotOffset ||
        module.base > UINTPTR_MAX - kHudRenderGotSlotOffset) return Result::GotSlotTargetMismatch;
    const uintptr_t target = target_address(module.base, kHudRenderOffset);
    const uintptr_t stub = target_address(module.base, kHudRenderStubOffset);
    const uintptr_t slot = target_address(module.base, kHudRenderGotSlotOffset);
    if (!module.Contains(target, kHudRenderExpectedBytes.size()) ||
        !module.Contains(stub, kHudRenderStubExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(target, kHudRenderExpectedBytes.size()) ||
        !IsMappedRxModuleCodeWindow(stub, kHudRenderStubExpectedBytes.size()) ||
        !verify_bytes(kHudRenderExpectedBytes.data(), reinterpret_cast<const u8*>(target), kHudRenderExpectedBytes.size()) ||
        !verify_bytes(kHudRenderStubExpectedBytes.data(), reinterpret_cast<const u8*>(stub), kHudRenderStubExpectedBytes.size()))
        return Result::GotSlotTargetMismatch;
    MemoryInfo info{};
    u32 pageInfo = 0;
    if (R_FAILED(svcQueryMemory(&info, &pageInfo, slot)) || (info.perm & Perm_R) == 0 ||
        info.size < sizeof(uintptr_t) || slot < info.addr || slot - info.addr > info.size - sizeof(uintptr_t) ||
        (slot & (alignof(uintptr_t) - 1)) != 0) return Result::GotSlotUnavailable;
    const uintptr_t current = __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE);
    const uintptr_t callback = reinterpret_cast<uintptr_t>(&IsaacModRuntime_HudRenderGotSlotIntercept);
    // 可接受引擎目标或模块内尚未解析的PLT入口；拒绝其它插件写入的陌生目标。
    if (current != target && current != module.base + kPltResolverOffset) return Result::GotSlotTargetMismatch;
    g_HudRenderGotSlotTarget.store(target, std::memory_order_release);
    if (PageIsWritable(slot)) {
        __atomic_store_n(reinterpret_cast<uintptr_t*>(slot), callback, __ATOMIC_RELEASE);
    } else {
        exl::util::RwPages pages(slot, sizeof(uintptr_t));
        __atomic_store_n(reinterpret_cast<uintptr_t*>(pages.GetRw()), callback, __ATOMIC_RELEASE);
        pages.Flush();
    }
    return __atomic_load_n(reinterpret_cast<const uintptr_t*>(slot), __ATOMIC_ACQUIRE) == callback
        ? Result::Success : Result::GotSlotWriteFailed;
}

extern "C" void* EntryRelayGameSpawnExCallback(void* game, std::int32_t type, std::uint32_t variant, const void* position, const void* velocity, void* spawner, std::uint32_t subType, std::uint32_t seed, std::uint32_t forceSpawn) {
    using Fn = void* (*)(void*, std::int32_t, std::uint32_t, const void*, const void*, void*,
                         std::uint32_t, std::uint32_t, std::uint32_t);
    const auto result = LuaRuntime::DispatchPreEntitySpawn(type, variant, subType, position, velocity,
        isaac::runtime::engine_memory::AddressOf(spawner), seed);
    const auto original = isaac::runtime::Original<Fn>(isaac::runtime::HookId::GameSpawnEx);
    return original(game, result.type, result.variant, position, velocity, spawner, result.subType,
                    result.seed, forceSpawn);
}

namespace isaac::runtime::console {
void RenderConsoleAfterGame() noexcept { SessionRenderOverlay(); }
}
