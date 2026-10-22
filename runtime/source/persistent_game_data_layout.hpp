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

inline constexpr std::uint8_t kPersistentGameDataBuildId[20] = {
    0x91, 0xC7, 0x3F, 0xDD, 0x57, 0x50, 0x61, 0x31, 0x8D, 0x68, 0x88, 0x63, 0x16, 0xAF, 0xEA, 0xC7, 0x23, 0x88, 0xB2, 0xAB
};

// Boss是否被标为击杀，合法Lua下标1..103；数组0槽不由本API开放。值锚点：AddBoss以id索引后写byte1，后续解锁分支逐Boss读同表。（confirmed）
//   证据：0x00439a74 —— 439A60先add x8,this,w1,uxtw，439A68 mov w9,#1，439A74 strb w9,[x8,#0xD87]；id作为逐byte下标。
//   证据：0x00439a84 —— id1真实读者，随后解锁分支读取id2与其它boss；与写入同一表。
inline constexpr std::uintptr_t kPersistentGameDataBossKilledOffset = 0xD87;
inline constexpr std::uintptr_t kPersistentGameDataBossKilledWidth = 104;

// 对外 API 只允许读这些字段（`confidence == confirmed`）。
// 当前可用：BossKilled

} // namespace isaac::runtime::layout
