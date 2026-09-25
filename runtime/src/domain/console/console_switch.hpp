#pragma once

// 控制台的**总开关**状态（2026-09-25 批次 124，用户指令）。
//
// ## 它对应 PC 的什么
//
// PC 版的控制台要靠 `options.ini` 里的 `EnableDebugConsole=1` 才出现（也就是"默认没有控制台"）。
// Switch 版没有这个配置入口，所以用户定案：**在自建的模组菜单里放一个开关**，
// 并在模组页上单独画一行「控制台：开/关」。开关打到"关"时连 `Isaac.ExecuteCommand` 一起拒
// ⇒ 语义就是 PC 的 `EnableDebugConsole=0`：**没有控制台**。
//
// ## 文件格式（与 `isaac-switch-mods-state.txt` / `isaac-runtime-run-taint.txt` 同一种做法）
//
//     isaac-switch-console-state 1
//     enabled=1
//
// * 头一行是**可读的标识 + 版本**，解析时不参与判定（将来加字段不会让老版本读不懂）；
// * 只认 `enabled=` 开头的行，值只认 `0` / `1`；只认**第一处**出现的那一行；
// * 其它行、其它值、空内容、乱码 ⇒ 一律当成**开**（= 默认值）。
//
// ## ★ 默认值与 fail-open 的方向（与污染标记那条**方向相反**，理由不同，别混）
//
// 污染标记的 fail-open 是"读不懂 ⇒ 当没污染"（宁可少禁一次成就，也不误禁）。
// 这里的"读不懂 / 文件不在 / 读失败 ⇒ 当**开**"出于另一个理由：
// **不能因为读一个状态文件失败，就把用户唯一能用的调试入口静默关掉**（那会让现象变成
// "控制台忽然没了、还不报错"，最难查）。所以这个开关只有两条明确路径能关掉它：
// ① 文件里写着 `enabled=0`；② 用户在模组页上亲手拨到关。
// 写失败时内存里的值照旧生效（拨动当场可见），但**跨重启不保**，失败次数记在状态面 `[21]`。

#include <cstddef>
#include <cstring>
#include <string_view>

namespace isaac::runtime {

//: 状态文件名（相对**存档根**，与模组开关、污染标记同一片区域）。
//: ★ 改名等于让所有已存的开关状态失效（下次开机回到默认"开"）⇒ 它是一个具名常量。
inline constexpr char kConsoleSwitchFileName[] = "isaac-switch-console-state.txt";
//: 头一行的标识 + 版本（解析不依赖它，只为可读性与将来升级时有落脚点）。
inline constexpr char kConsoleSwitchHeader[] = "isaac-switch-console-state 1";
//: 序列化后的最大字节数（头一行 + 换行 + `enabled=` 那一行）。
inline constexpr std::size_t kConsoleSwitchMaximumBytes =
    sizeof(kConsoleSwitchHeader) + sizeof("enabled=1\n");
//: 默认值（文件不在 / 读不懂 ⇒ 开）。这条**由门禁钉住**（`test_console_switch.py`）。
inline constexpr bool kConsoleSwitchDefaultEnabled = true;

//: 解析一份文本 ⇒ 开关值。**任何看不懂的内容都回默认值（开）**，理由见文件头。
[[nodiscard]] inline bool ParseConsoleSwitch(std::string_view text) noexcept {
    constexpr std::string_view kKey = "enabled=";
    std::size_t offset = 0;
    while (offset <= text.size()) {
        const std::size_t end = text.find('\n', offset);
        const std::size_t length =
            (end == std::string_view::npos ? text.size() : end) - offset;
        const std::string_view line = text.substr(offset, length);
        if (line.size() > kKey.size() && line.substr(0, kKey.size()) == kKey) {
            // 只认 0 / 1：`enabled=2` / `enabled=yes` 之类**不是**"关"，而是看不懂 ⇒ 回默认（开）。
            return line.substr(kKey.size()) != "0";
        }
        if (end == std::string_view::npos) {
            break;
        }
        offset = end + 1;
    }
    return kConsoleSwitchDefaultEnabled;
}

//: 序列化。放不下（或 `out` 为空）返回 0 —— 调用方按"写不了"处理，**不写半截**
//: （半截状态比没有状态更难查，与 `ISaveFilePort::Write` 的口径一致）。
[[nodiscard]] inline std::size_t SerializeConsoleSwitch(bool enabled, char* out,
                                                        std::size_t capacity) noexcept {
    constexpr std::string_view kKey = "enabled=";
    const std::size_t headerLength = sizeof(kConsoleSwitchHeader) - 1;  // 不含结尾 '\0'
    const std::size_t valueLength = kKey.size() + 1 /*值*/ + 1 /*'\n'*/;
    const std::size_t total = headerLength + 1 /*'\n'*/ + valueLength;
    if (out == nullptr || capacity < total) {
        return 0;
    }
    std::size_t at = 0;
    std::memcpy(out + at, kConsoleSwitchHeader, headerLength);
    at += headerLength;
    out[at++] = '\n';
    std::memcpy(out + at, kKey.data(), kKey.size());
    at += kKey.size();
    out[at++] = enabled ? '1' : '0';
    out[at++] = '\n';
    return at;
}

} // namespace isaac::runtime