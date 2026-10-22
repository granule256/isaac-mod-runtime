#pragma once
#include <atomic>
#include <cstdint>

namespace isaac::runtime::console {
// 与原生控制台一致：面板动画/输入法期间暂停逻辑；关掉后等按键释放再交还输入。
inline std::atomic<std::uint32_t> g_ConsolePaused{false};
inline std::atomic<std::uint32_t> g_ConsoleInputCaptured{false};
inline std::atomic<std::uint32_t> g_ConsoleSessionEpoch{};
inline void InvalidateConsoleSession() noexcept {
    g_ConsoleSessionEpoch.fetch_add(1,std::memory_order_relaxed);
    g_ConsolePaused.store(0,std::memory_order_relaxed);
}
inline bool ConsolePaused() noexcept { return g_ConsolePaused.load(std::memory_order_relaxed); }
inline bool ConsoleCapturesInput() noexcept { return g_ConsoleInputCaptured.load(std::memory_order_relaxed); }
}
