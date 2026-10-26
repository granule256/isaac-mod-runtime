#pragma once

#include <cstdint>
namespace isaac::runtime {
bool PublishManagerUpdateEntryRelayOriginal(std::uintptr_t original) noexcept;
// 仅原生模组页退出安全点调用；失败保持在模组页供用户修正。
bool ReloadModsFromMenu(bool edited) noexcept;
}

#include "module_finder.hpp"

#include <cstdint>

uintptr_t target_address(uintptr_t base, uintptr_t offset);
bool verify_bytes(const u8* expected, const u8* actual, size_t length);

bool VerifyManagerUpdate(const TargetModule& module, uintptr_t* target);
bool VerifyManagerRelay(const TargetModule& module, uintptr_t target, uintptr_t* slot);
bool VerifyManagerRender(const TargetModule& module, uintptr_t* target);
bool VerifyManagerRenderRelay(const TargetModule& module, uintptr_t target, uintptr_t* slot);
enum class RenderHookInstallResult {
    Success,
    InstructionMismatch,
    RelayPatchMismatch,
    RelaySlotNotEmpty,
    RelayPublishFailed,
};
RenderHookInstallResult TryInstallManagerRenderHook(const TargetModule& module);
// `MC_POST_RENDER`局内从HUD返回后派发，早于暂停等前景；主菜单等无HUD帧由最终Present兜底。
// ManagerRender入口建立栈上帧scope，三个入口共用该scope防止重复派发。
enum class RenderPresentRelayInstallResult {
    Success = 0,
    RelayPatchMismatch = 1,
    RelaySlotNotEmpty = 2,
    RelayPublishFailed = 3,
    // M2b：改 GOT 槽的方案（零代码字节），失败码继续往后排，旧值不动。
    GotSlotTargetMismatch = 4,   // 桩 / `Present` 本体 / 调用点三段守卫任一不符（含"IPS 还没删"）
    GotSlotUnavailable = 5,      // 槽不在已映射页里，或槽内当前值是 0（加载器还没解析出来）
    GotSlotWriteFailed = 6,      // 写完读回不一致
};
RenderPresentRelayInstallResult TryInstallManagerPresentRelay(const TargetModule& module);
// M2b：把 `Present` 的 GOT 槽改写成我们的拦截函数（只改数据、零代码字节），
// 拦截函数按调用方过滤，只有那**一处**调用点会派发 `MC_POST_RENDER`。
RenderPresentRelayInstallResult TryInstallManagerPresentGotSlot(const TargetModule& module);
RenderPresentRelayInstallResult TryInstallNpcUpdateAiGotSlot(const TargetModule& module);
RenderPresentRelayInstallResult TryInstallHudRenderGotSlot(const TargetModule& module);
enum class PreGetCollectibleRelayInstallResult {
    Success,
    RelayPatchMismatch,
    RelaySlotNotEmpty,
    RelayPublishFailed,
};
PreGetCollectibleRelayInstallResult TryInstallPreGetCollectibleRelay(const TargetModule& module);

// Stage 148: verify and publish the rebuild relay, which restores Mod content mount
// points after the engine rebuilds its mount point table. Reports true only when the
// relay entry, its cave and the (still empty) callback slot all match the audited build
// and the callback address was published. A false result is not fatal for Mod loading:
// it only means mount points are not restored after a rebuild.
bool TryInstallRebuildMountPointsRelay(const TargetModule& module);
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 102
enum class Stage102ChangeRoomInstallResult {
    Success = 0,
    RelayPatchMismatch = 1,
    RelaySlotNotEmpty = 2,
    RelayPublishFailed = 3,
};
Stage102ChangeRoomInstallResult TryInstallStage102ChangeRoomDiagnostic(const TargetModule& module);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 104
enum class Stage104RoomKeyInstallResult {
    Success = 0,
    RelayPatchMismatch = 1,
    RelaySlotNotEmpty = 2,
    RelayPublishFailed = 3,
};
Stage104RoomKeyInstallResult TryInstallStage104RoomKeyDiagnostic(const TargetModule& module);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 112
enum class Stage112DescriptorReentryInstallResult {
    Success = 0,
    RelayPatchMismatch = 1,
    RelaySlotNotEmpty = 2,
    RelayPublishFailed = 3,
};
Stage112DescriptorReentryInstallResult TryInstallStage112DescriptorReentryDiagnostic(const TargetModule& module);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 108
enum class Stage108LifecycleInstallResult {
    Success = 0,
    RelayPatchMismatch = 1,
    RelaySlotNotEmpty = 2,
    RelayPublishFailed = 3,
};
Stage108LifecycleInstallResult TryInstallStage108LifecycleDiagnostic(const TargetModule& module);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 109
enum class Stage109RestartInstallResult {
    Success = 0,
    RelayPatchMismatch = 1,
    RelaySlotNotEmpty = 2,
    RelayPublishFailed = 3,
};
Stage109RestartInstallResult TryInstallStage109RestartDiagnostic(const TargetModule& module);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 127
enum class Stage127SaveLoadInstallResult {
    Success = 0,
    RelayPatchMismatch = 1,
    RelaySlotNotEmpty = 2,
    RelayPublishFailed = 3,
};
Stage127SaveLoadInstallResult TryInstallStage127SaveLoadDiagnostic(const TargetModule& module);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 128
enum class Stage128SaveDataManagerInstallResult {
    Success = 0,
    RelayPatchMismatch = 1,
    RelaySlotNotEmpty = 2,
    RelayPublishFailed = 3,
};
Stage128SaveDataManagerInstallResult TryInstallStage128SaveDataManagerDiagnostic(const TargetModule& module);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 110
enum class Stage110ChangeRoomInstallResult { Success = 0, RelayPatchMismatch = 1, RelaySlotNotEmpty = 2, RelayPublishFailed = 3 };
enum class Stage110LifecycleInstallResult { Success = 0, RelayPatchMismatch = 1, RelaySlotNotEmpty = 2, RelayPublishFailed = 3 };
Stage110ChangeRoomInstallResult TryInstallStage110ChangeRoomDiagnostic(const TargetModule& module);
Stage110LifecycleInstallResult TryInstallStage110LifecycleDiagnostic(const TargetModule& module);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 118
enum class Stage118InstallResult { Success = 0, FileBindingMismatch = 1, HookInstallFailed = 2 };
Stage118InstallResult TryInstallStage118ManagedFileWriteDiagnostic(const TargetModule& module);
#endif
bool VerifyGameObserverRelay(const TargetModule& module, uintptr_t* slot);
enum class GameObserverInstallResult {
    Success,
    RelayPatchMismatch,
    RelaySlotNotEmpty,
    RelayPublishFailed,
};
GameObserverInstallResult TryInstallGameObserverRelay(const TargetModule& module);
bool VerifyGameUpdateObserverRelay(const TargetModule& module, uintptr_t* slot);
enum class GameUpdateObserverInstallResult {
    Success,
    RelayPatchMismatch,
    RelaySlotNotEmpty,
    RelayPublishFailed,
};
GameUpdateObserverInstallResult TryInstallGameUpdateObserverRelay(const TargetModule& module);
bool VerifyGameState2ObserverRelay(const TargetModule& module, uintptr_t* slot);
enum class GameState2ObserverInstallResult {
    Success,
    RelayPatchMismatch,
    RelaySlotNotEmpty,
    RelayPublishFailed,
};
GameState2ObserverInstallResult TryInstallGameState2ObserverRelay(const TargetModule& module);
enum class GameRenderObserverInstallResult { Success, RelayPatchMismatch, RelaySlotNotEmpty, RelayPublishFailed };
GameRenderObserverInstallResult TryInstallGameRenderObserverRelay(const TargetModule& module);
bool VerifyGameOwnerSlot(const TargetModule& module, uintptr_t* slot);
bool VerifyGameIsPausedThunk(const TargetModule& module, uintptr_t* thunk);
bool VerifyGameIsGreedMode(const TargetModule& module, uintptr_t* method);
bool VerifyLevelIsAscent(const TargetModule& module, uintptr_t* method);
bool VerifyManagerIsActionTriggered(const TargetModule& module, uintptr_t* method);
bool VerifyMusicBindings(const TargetModule& module, uintptr_t* getCurrentMusicId,
                         uintptr_t* pause, uintptr_t* resume);
bool VerifyRngBindings(const TargetModule& module, uintptr_t* setSeed, uintptr_t* next);
//: 批次 195：同一条判据的**单入口版本**（`RNG:RandomInt` / `RNG:RandomFloat` 的两条入口用它）。
bool VerifyRngEntry(const TargetModule& module, uintptr_t offset, const u8* expected,
                    std::size_t length, uintptr_t* output);
bool VerifyRngRandomBindings(const TargetModule& module, uintptr_t* randomUint,
                             uintptr_t* randomFloat);
bool TryInstallRngBindings(const TargetModule& module);
//: 批次 195（2026-09-29）：`KAGE::Input::ManagerBase` 上按**按键号**查询的三条入口
//: （`IsButtonPressed` / `IsButtonTriggered` / `GetButtonValue`）。
//: ★ 四条按钮/动作入口的头 32 字节完全相同 ⇒ 判据除 16 字节序言外**再比 `entry+0xE0` 的 4 字节**
//:   （那条"取虚表槽"的指令），否则偏移写串会被静默放过（换到另一条按钮查询 = 给出错语义）。
//: 三条互相独立：某一条守卫不符只让它自己留 0（handler 报"绑定不可用"），不牵连另外两条。
bool VerifyInputButtonBindings(const TargetModule& module, uintptr_t* isButtonPressed,
                               uintptr_t* getButtonValue);
void TryInstallInputButtonBindings(const TargetModule& module);
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 48
enum class Stage48MusicReplayProbeInstallResult {
    Success = 0,
    TargetMismatchMusicPlay = 11,
    TargetMismatchSoundActorPlay = 12,
    TargetMismatchSoundActorPause = 13,
    RelayPublishMusicPlayFailed = 21,
    RelayPublishSoundActorPlayFailed = 22,
    RelayPublishSoundActorPauseFailed = 23,
};
Stage48MusicReplayProbeInstallResult TryInstallStage48MusicReplayProbe(const TargetModule& module);
void Stage48ArmMusicReplayProbe();
void Stage48AdvanceMusicReplayProbe();
bool Stage48TakeMusicReplayReport(std::uint32_t* payload);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
[[noreturn]] void ReportStage6Failure(std::uint32_t status);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && (EXL_DIAGNOSTIC_STAGE == 8 || EXL_DIAGNOSTIC_STAGE == 9)
bool VerifyManagerLoadConfigs(const TargetModule& module, uintptr_t* target);
bool VerifyManagerLoadConfigsRelay(const TargetModule& module, uintptr_t target, uintptr_t* slot);
#endif
enum class HookInstallResult {
    Success,
    InstructionMismatch,
    RelayPatchMismatch,
    RelaySlotNotEmpty,
    RelayPublishFailed,
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 14 || EXL_DIAGNOSTIC_STAGE == 15 || EXL_DIAGNOSTIC_STAGE == 16 || EXL_DIAGNOSTIC_STAGE == 17 || EXL_DIAGNOSTIC_STAGE == 45 || EXL_DIAGNOSTIC_STAGE == 48
    GameBindingsMismatch,
    GameBindingsPublishFailed,
    MusicBindingsMismatch,
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 6
    GameOwnerSlotMismatch,
    GameOwnerSlotPublishFailed,
    GameIsPausedThunkMismatch,
    GameIsPausedThunkPublishFailed,
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 88
    Stage88GameBindingsMismatch,
    ManagerIsActionTriggeredMismatch,
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 89
    Stage89GameBindingsMismatch,
    ManagerIsActionTriggeredMismatch,
#endif
};
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
enum class LoadConfigsDiagnosticInstallResult {
    Success,
    InstructionOrRelayMismatch,
    RelaySlotNotEmpty,
    RelayPublishFailed,
};
#endif
HookInstallResult TryInstallManagerUpdateHook(const TargetModule& module);
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 8
LoadConfigsDiagnosticInstallResult TryInstallManagerLoadConfigsDiagnostic(const TargetModule& module);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 9
enum class LoadConfigsResetDiagnosticInstallResult {
    Success,
    LoadConfigsInstructionOrRelayMismatch,
    ResetInstructionOrMappingMismatch,
    RelaySlotNotEmpty,
    RelayPublishFailed,
};
LoadConfigsResetDiagnosticInstallResult TryInstallManagerLoadConfigsResetDiagnostic(const TargetModule& module);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 11
enum class Stage11InstallResult {
    Success,
    FileBindingMismatch,
};
Stage11InstallResult TryInstallRomfsSentinelDiagnostic(const TargetModule& module);
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 12
enum class Stage12InstallResult {
    Success,
    FileBindingMismatch,
};
Stage12InstallResult TryInstallRomfsLuaDiagnostic(const TargetModule& module);
#endif
#if !defined(EXL_DIAGNOSTIC_STAGE) || EXL_DIAGNOSTIC_STAGE == 13
#if !defined(EXL_DIAGNOSTIC_STAGE)
enum class DefaultManifestInstallResult {
    Success,
    FileBindingMismatch,
};
DefaultManifestInstallResult TryInstallDefaultManifestMod(const TargetModule& module);
// 批次 370（2026-10-05）：**重活之前**先把"注册模组挂载点"做完（工人线程、有界、失败不回归）。
//
// 复用既有的清单/自动发现/挂载服务（`ManifestService` / `ModDiscoveryService` /
// `ContentMountService`），**只挂挂载点**：不装钩子、不建 Lua 状态、不跑模组脚本。
// 与 `LoadDefaultManifestModThroughService` 的 Prepare/Mounts 两步逐条一致，差别只有
// "不读存档侧模组开关"（那条通道是 nnSdk 存档 API，从我们自己的线程调它每次开机必崩，
// 见 `hook_manager.cpp` 里 `g_CardSwitchProbeAllowed` 上面那条纪律）与"挂完就返回"。
struct EarlyModMountOutcome {
    //: ★ 批次 378（2026-10-05）改口径：这里不再是"`RegisterMod` 调了几次"（那条机制已撤除），
    //: 而是"发布重定向清单时，清单里有几个模组根"（0 = 清单与自动发现都没成功）。
    std::uint32_t mountsAttempted = 0;
    //: 其中返回失败的有几次（新机制下：清单为空 ⇒ 发布返回 false，这里记 0）。
    std::uint32_t mountsFailed = 0;
    //: 走到"发布清单"这一步了吗（false = 文件绑定不齐 / 清单与自动发现都读不出来）。
    bool attempted = false;
};
EarlyModMountOutcome MountModsBeforeHeavyWork(const TargetModule& module) noexcept;
// ★ 实验 B（2026-10-05）：**只读清单、一个字节都不碰引擎**（不 `RegisterMod`、不写引擎内存）。
// 由来与判据写在 `hook_manager.cpp` 里那段实现的注释里；它只给实验卡用，不是生产线的一部分。
bool ReadManifestOnlyForExperiment(const TargetModule& module) noexcept;
#if defined(EXL_STARTUP_PROBE_STAGE) && EXL_STARTUP_PROBE_STAGE == 8
void AllowDefaultManifestInitialization();
#endif
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 13
enum class Stage13InstallResult {
    Success,
    FileBindingMismatch,
};
Stage13InstallResult TryInstallManifestRequireDiagnostic(const TargetModule& module);
[[noreturn]] void ReportStage13Failure(std::uint32_t status);
#endif
#endif
#if defined(EXL_DIAGNOSTIC_STAGE) && EXL_DIAGNOSTIC_STAGE == 14
void MarkStage14DiagnosticReady();
#endif
// 批次 371（2026-10-05）：一条"这个地址**现在**可执行吗"的判据 —— `svcQueryMemory` 必须答
// `MemType_ModuleCodeStatic` + `Perm_Rx`，且给定长度落在那一段映射里。
//
// 为什么提到头文件：装入口中继之前**必须先过它**（`TryInstallEntryRelay` 第一步就会读目标入口
// 那 16 字节做守卫比对；地址若还没映射/不可执行，**读它本身就是崩溃**，不是"守卫不符"）。
// 它一直定义在 `hook_manager.cpp`（与那一排 `Verify*` 邻居同处、在匿名命名空间之外），
// 批次 371 起 `runtime_entry.cpp` 也要用这条判据 ⇒ 在这里给出声明，**不再各写一份**。
bool IsMappedRxModuleCodeWindow(uintptr_t address, size_t length);

bool InstallManagerUpdateHook(const TargetModule& module);

// 游戏开局的常驻中继安装结果。与 `ManagerUpdate` 一样，失败**不阻断**加载 Mod：
// 失败只会让 `MC_POST_GAME_STARTED` 收不到事件，而不是让整个运行时起不来。
enum class GameStartRelayInstallResult {
    Success,
    RelayPatchMismatch,
    RelaySlotNotEmpty,
    RelayPublishFailed,
};
GameStartRelayInstallResult TryInstallGameStartRelay(const TargetModule& module);
bool TryInstallProjectileTailRelay(const TargetModule& module,bool initialize);
bool IsHookEnabled();
