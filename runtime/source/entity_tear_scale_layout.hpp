#pragma once

// **本文件由 `tools/build_layout_table.py` 从 `tools/layout_tables/room_descriptor.json` 生成，请勿手改。**
//
// 每个常量都对应表里的一行，那一行带可复现证据（函数符号 + 指令地址）。
// 复核命令：`python3 tools/build_layout_table.py --table tools/layout_tables/room_descriptor.json --verify`
//
// 口径（与表的 `confidence` 一致）：
//   confirmed  —— 语义有独立锚点 ⇒ **可以**用于对外 API；
//   candidate  —— 偏移确定、名字只有间接依据 ⇒ 只作登记，不进 API；
//   structural —— 只说明结构，不声称字段名。

#include <cstdint>

namespace isaac::runtime::layout {

inline constexpr std::uint8_t kEntityTearBuildId[20] = {
    0x91, 0xC7, 0x3F, 0xDD, 0x57, 0x50, 0x61, 0x31, 0x8D, 0x68, 0x88, 0x63, 0x16, 0xAF, 0xEA, 0xC7, 0x23, 0x88, 0xB2, 0xAB
};

// 泪弹float缩放；getter读本格，setter原方法同步维护+414与动画。（confirmed）
//   证据：0x0033d068 —— ldr s0读取真实缩放后分档挑sprite
//   证据：0x0033bf98 —— fcmp/csel后以float位写本格并尾调用Reset
inline constexpr std::uintptr_t kEntityTearScaleOffset = 0x410;
inline constexpr std::uintptr_t kEntityTearScaleWidth = 4;

// 对外 API 只允许读这些字段（`confidence == confirmed`）。
// 当前可用：Scale

} // namespace isaac::runtime::layout
