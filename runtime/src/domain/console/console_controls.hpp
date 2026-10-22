#pragma once

// Switch 物理按钮号，独立于可重绑定的游戏动作。设置只在游戏线程修改。
#include <cstdint>
#include <cstdio>
#include <string_view>

namespace isaac::runtime {
inline constexpr std::uint32_t kConsoleNoSecondButton = 255;
inline constexpr std::uint32_t kConsoleMinimumHoldTenths = 2;
inline constexpr std::uint32_t kConsoleMaximumHoldTenths = 50;
struct ConsoleControls {
    std::uint32_t first{4}, second{5}, holdTenths{8};
};
inline bool ValidConsoleControls(ConsoleControls value) noexcept {
    return value.first < 14 && (value.second < 14 || value.second == kConsoleNoSecondButton) &&
           value.holdTenths >= kConsoleMinimumHoldTenths && value.holdTenths <= kConsoleMaximumHoldTenths;
}
inline bool SameConsoleControls(ConsoleControls a, ConsoleControls b) noexcept {
    return a.first == b.first && a.second == b.second && a.holdTenths == b.holdTenths;
}
inline bool ConsoleButtonsHeld(ConsoleControls value, std::uint32_t pressed) noexcept {
    if (!ValidConsoleControls(value)) return false;
    const auto required = (1U << value.first) |
        (value.second == kConsoleNoSecondButton ? 0U : (1U << value.second));
    return (pressed & required) == required;
}
inline ConsoleControls ParseConsoleControls(std::string_view text) noexcept {
    ConsoleControls value{};
    // 逐行严格解析：旧文件无新增字段自然保留默认；坏字段各自回默认。
    const auto field = [&](std::string_view key, std::uint32_t fallback) {
        std::size_t at = 0;
        while (at < text.size()) {
            const auto end = text.find('\n', at);
            auto line = text.substr(at, (end == text.npos ? text.size() : end) - at);
            if (!line.empty() && line.back() == '\r') line.remove_suffix(1);
            if (line.substr(0, key.size()) == key) {
                line.remove_prefix(key.size());
                if (line.empty()) return fallback;
                std::uint32_t number = 0;
                for (const char ch : line) {
                    if (ch < '0' || ch > '9' || number > 1000) return fallback;
                    number = number * 10 + static_cast<unsigned>(ch - '0');
                }
                return number;
            }
            if (end == text.npos) break;
            at = end + 1;
        }
        return fallback;
    };
    const auto first = field("first_button=", value.first);
    const auto second = field("second_button=", value.second);
    const auto hold = field("hold_tenths=", value.holdTenths);
    if (first < 14) value.first = first;
    if (second < 14 || second == kConsoleNoSecondButton) value.second = second;
    if (hold >= kConsoleMinimumHoldTenths && hold <= kConsoleMaximumHoldTenths) value.holdTenths = hold;
    return value;
}
inline std::size_t SerializeConsoleControls(ConsoleControls value, char* out, std::size_t size) noexcept {
    if (!ValidConsoleControls(value) || !out || size < 64) return 0;
    const int n = std::snprintf(out, size, "first_button=%u\nsecond_button=%u\nhold_tenths=%u\n",
                              value.first, value.second, value.holdTenths);
    return n > 0 && static_cast<std::size_t>(n) < size ? static_cast<std::size_t>(n) : 0;
}
inline void FormatConsoleControlRow(bool enabled, ConsoleControls value, char* out, std::size_t size) noexcept {
    constexpr const char* names[] = {"Left", "Right", "Up", "Down", "A", "B", "X", "Y",
                                   "L", "ZL", "LS", "R", "ZR", "RS"};
    if (!ValidConsoleControls(value)) value = {};
    const bool second = value.second != kConsoleNoSecondButton && value.second != value.first;
    std::snprintf(out, size, "Console: %s (Hold %s%s%s %u.%us)", enabled ? "ON" : "OFF",
                  names[value.first], second ? "+" : "", second ? names[value.second] : "",
                  value.holdTenths / 10, value.holdTenths % 10);
}
} // namespace isaac::runtime
