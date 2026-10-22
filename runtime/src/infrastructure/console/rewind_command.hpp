#pragma once

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "runtime_constants.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

// Switch控制台缺少rewind分支，但回退所用的引擎快照与重载入口都存在。
// PC分支证据：Console @0x66A7DC恢复，@0x66A809请求RestartGame，
// @0x66A826重新复制种子，@0x66A836/@0x66A83D设置保存退出/载入状态。
namespace isaac::runtime::console {

using RewindRestoreFn = void (*)(void*, void*);
using RewindRestartFn = void (*)(void*, const void*, bool, bool);
using RewindCopySeedsFn = void* (*)(void*, const void*);

struct RewindEntries {
    RewindRestoreFn restore{nullptr};
    RewindRestartFn restart{nullptr};
    RewindCopySeedsFn copySeeds{nullptr};
    bool instantFadeLayoutVerified{};

    [[nodiscard]] bool Ready() const noexcept {
        return restore != nullptr && restart != nullptr && copySeeds != nullptr && instantFadeLayoutVerified;
    }
};

// 原控制台按空格切第一项，命令名大小写敏感；尾部参数不影响rewind分支。
[[nodiscard]] inline bool IsRewindCommand(const char* command, std::size_t length) noexcept {
    if (command == nullptr) return false;
    while (length != 0 && *command == ' ') { ++command; --length; }
    return length >= 6 && std::memcmp(command, "rewind", 6) == 0 &&
           (length == 6 || command[6] == ' ');
}

#if !defined(__SWITCH__)
// 宿主没有AArch64引擎，仅在离线测试中注入已知调用与内存判定。
inline bool g_RewindHostConfigured = false;
inline RewindEntries g_RewindHostEntries{};
inline engine_memory::ReadableCheck g_RewindHostReadable = nullptr;
inline engine_memory::WritableCheck g_RewindHostWritable = nullptr;
inline void SetRewindHostBindings(RewindEntries entries, engine_memory::ReadableCheck readable,
                                   engine_memory::WritableCheck writable,
                                   bool instantFadeLayoutVerified = true) noexcept {
    g_RewindHostEntries = entries;
    g_RewindHostEntries.instantFadeLayoutVerified = instantFadeLayoutVerified;
    g_RewindHostReadable = readable;
    g_RewindHostWritable = writable;
    g_RewindHostConfigured = true;
}
#endif

[[nodiscard]] inline RewindEntries ResolveRewindEntries(std::uintptr_t base) noexcept {
#if !defined(__SWITCH__)
    if (g_RewindHostConfigured) return g_RewindHostEntries;
#endif
    std::uintptr_t verified{};
    const bool fadeLayout = engine_call::ResolveEntryAddress(base,kGameModuleRangeCheckSize,
        kApi200GameFadeinOffset,kApi200GameFadeinExpectedBytes,&verified,
        &engine_memory::EngineMemoryReadable) &&
        engine_call::ResolveEntryAddress(base,kGameModuleRangeCheckSize,
            kGameInstantFadeUpdateLayoutOffset,kGameInstantFadeUpdateLayoutExpectedBytes,&verified,
            &engine_memory::EngineMemoryReadable);
    return {
        engine_call::ResolveFunction<RewindRestoreFn>(base, kGameModuleRangeCheckSize,
            kGameRestoreGlowingHourGlassStateOffset, kGameRestoreGlowingHourGlassStateExpectedBytes,
            &engine_memory::EngineMemoryReadable),
        engine_call::ResolveFunction<RewindRestartFn>(base, kGameModuleRangeCheckSize,
            kManagerConsoleRestartGameOffset, kManagerConsoleRestartGameExpectedBytes,
            &engine_memory::EngineMemoryReadable),
        engine_call::ResolveFunction<RewindCopySeedsFn>(base, kGameModuleRangeCheckSize,
            kConsoleSeedsAssignOffset, kConsoleSeedsAssignExpectedBytes,
            &engine_memory::EngineMemoryReadable),
        fadeLayout,
    };
}

[[nodiscard]] inline bool ExecuteRewind(const RewindEntries& entries, std::uintptr_t game,
                                       std::uintptr_t manager) noexcept {
    if (!entries.Ready() || game == 0 || manager == 0) return false;
    engine_memory::ReadableCheck readable = &engine_memory::EngineMemoryReadable;
    engine_memory::WritableCheck writable = &engine_memory::EngineMemoryWritable;
#if !defined(__SWITCH__)
    if (g_RewindHostConfigured) {
        readable = g_RewindHostReadable;
        writable = g_RewindHostWritable;
    }
#endif
    // 所有依赖先确认，防止已经恢复房间之后才发现重载请求无法落下。
    const std::uintptr_t seeds = engine_memory::FieldAddress(
        game, kGameSeedsObjectOffset, 0x70, 0, readable);
    const std::uintptr_t targetSeeds = engine_memory::FieldAddress(
        manager, kManagerConsoleRestartSeedsOffset, 0x70, 0, writable);
    const std::uintptr_t saveFlag = engine_memory::FieldAddress(
        manager, kManagerConsoleSaveOnRestartOffset, 1, 0, writable);
    const std::uintptr_t loadFlag = engine_memory::FieldAddress(
        manager, kManagerConsoleLoadSavedOffset, 1, 0, writable);
    const std::uintptr_t instantFade = engine_memory::FieldAddress(
        game, kGameInstantFadeOffset, 1, 0, writable);
    if (seeds == 0 || targetSeeds == 0 || saveFlag == 0 || loadFlag == 0 || instantFade == 0 ||
        engine_memory::FieldAddress(game, 0, 0x345E58, 0, readable) == 0) return false;

    // Restore的返回类型是void；无快照时原版直接返回，不编造上一个房间状态。
    entries.restore(engine_memory::AsObject(game), nullptr);
    // RestartGame只发布下一帧的请求，尚未销毁Game；Seeds参数仅被读取并复制。
    entries.restart(engine_memory::AsObject(manager), engine_memory::AsObject(seeds), false, false);
    // 原版Restart会对待用种子做Restart；PC随后再复制恢复后的原种子，保留其状态。
    static_cast<void>(entries.copySeeds(engine_memory::AsObject(targetSeeds),
                                       engine_memory::AsObject(seeds)));
    const std::uint8_t enabled = 1;
    return engine_memory::WriteAt(saveFlag, enabled, writable) &&
           engine_memory::WriteAt(loadFlag, enabled, writable) &&
           engine_memory::WriteAt(instantFade, enabled, writable);
}

} // namespace isaac::runtime::console
