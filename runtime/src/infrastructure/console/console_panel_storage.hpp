#pragma once
#include "domain/console/console_panel_state.hpp"
#include <cstdint>
#include <cstddef>

namespace isaac::runtime::console {
// 独立存储，不移动console-layout-v2的Core或BridgeState任何字段。
inline constexpr std::size_t kPanelTextCapacity=501; // 原生系统键盘500字符，加终止符
inline constexpr std::size_t kPanelUtf8Capacity=2001;
struct PanelState {
    bool hooksReady{};
    bool keyboardOpen{};
    bool keyboardFinished{};
    bool waitRelease{};
    bool touchHeld{};
    bool draftChanged{};
    std::uintptr_t game{};
    std::uint32_t previousMask{}, sessionEpoch{};
    char completedUtf8[kPanelUtf8Capacity]{};
    std::uint32_t completedLength{};
    std::uint32_t opened{}, closed{}, rendered{}, pausedUpdates{};
    std::uint32_t draft[kPanelTextCapacity]{};
    char draftUtf8[kPanelUtf8Capacity]{};
};
inline PanelState g_ConsolePanel{};
inline PanelState& Panel() noexcept { return g_ConsolePanel; }
}
