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

inline constexpr std::uint8_t kEntityBombBuildId[20] = {
    0x91, 0xC7, 0x3F, 0xDD, 0x57, 0x50, 0x61, 0x31, 0x8D, 0x68, 0x88, 0x63, 0x16, 0xAF, 0xEA, 0xC7, 0x23, 0x88, 0xB2, 0xAB
};

// 真实Bomb vptr存实体首8B，值为导出Entity_Bomb vtable+16即模块+A35048；PC dynamic_cast与NS type4交叉。（confirmed）
//   证据：0x0007ad64 —— 7AD50加载导出Entity_Bomb vtable，7AD5C加16，7AD64 str x8,[x19]（this）；原件ns-bomb-constructor.txt。
inline constexpr std::uintptr_t kEntityBombVtableOffset = 0x0;
inline constexpr std::uintptr_t kEntityBombVtableWidth = 8;

// 炸弹是否是胎儿；非零真，可按PC bool原样读写。（confirmed）
//   证据：0x0007af7c —— Init初始化false
//   证据：0x002e4520 —— 产生胎儿炸弹写1；对应PC765E38写已命名IsFetus+398
//   证据：0x0007b7c8 —— 更新根据真实胎儿标志选择动画帧路径
inline constexpr std::uintptr_t kEntityBombIsFetusOffset = 0x438;
inline constexpr std::uintptr_t kEntityBombIsFetusWidth = 1;

// 对外 API 只允许读这些字段（`confidence == confirmed`）。
// 当前可用：IsFetus、vtable

} // namespace isaac::runtime::layout
