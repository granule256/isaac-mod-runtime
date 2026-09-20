#pragma once

// **本文件由 `tools/build_layout_table.py` 从 `tools/layout_tables/item.json` 生成，请勿手改。**
//
// 每个常量都对应表里的一行，那一行带可复现证据（函数符号 + 指令地址）。
// 复核命令：`python3 tools/build_layout_table.py --table tools/layout_tables/item.json --verify`
//
// 口径（与表的 `confidence` 一致）：
//   confirmed  —— 语义有独立锚点 ⇒ **可以**用于对外 API；
//   candidate  —— 偏移确定、名字只有间接依据 ⇒ 只作登记，不进 API；
//   structural —— 只说明结构，不声称字段名。

#include <cstdint>

namespace isaac::runtime::layout {

inline constexpr std::uint8_t kItemConfigBuildId[20] = {
    0x91, 0xC7, 0x3F, 0xDD, 0x57, 0x50, 0x61, 0x31, 0x8D, 0x68, 0x88, 0x63, 0x16, 0xAF, 0xEA, 0xC7, 0x23, 0x88, 0xB2, 0xAB
};

// 收藏品向量的起始指针（`ItemConfig` 的 `std::vector<Item*>` begin）：`ItemConfig::GetCollectible(int)` 就是拿它 + 元素索引取指针的（confirmed）
//   证据：0x003c0c78 —— `ldp x8, x9, [x0]` 一次取出本字段（+0x00，向量起点）与 +0x08（向量终点）；紧随的 `sub` + `lsr #3` 把两者之差除以 8 ⇒ 元素是 8 字节指针 ⇒ 这是一对 `std::vector<Item*>` 的边界。`ItemConfig::GetCollectible(int)` 这个引擎自己的访问器就是语义锚点（它专门用来按索引取收藏品）。
//   证据：0x003c0c80 —— `lsr …, #3`：两指针之差 ÷ 8 ⇒ 元素是 8 字节指针（不是内联元素）
//   证据：0x003b4160 —— `cmp x10, #0x2dc`：`ItemConfig::Init` 拿**引擎自己的容量常量** 732 = 0x2DC 判越界 ⇒ 收藏品向量最多 732 项
inline constexpr std::uintptr_t kItemConfigCollectibleBeginOffset = 0x0;
inline constexpr std::uintptr_t kItemConfigCollectibleBeginWidth = 8;

// 收藏品向量的结束指针（同一对向量的 end，begin/end 之差 ÷ 8 即元素个数）（confirmed）
//   证据：0x003c0c80 —— 同一条 `ldp x8, x9, [x0]` 的**第二寄存器**就是本字段（+0x08）：`ldp` 一次读出相邻的两个 8 字节指针，随后 `sub x9, x9, x8` + `lsr #3` 说明它们正是同一向量的 begin/end。⚠️ 局限：`ldp` 隐含第二个偏移，指令里不出现 `#0x8` ⇒ 本行**偏移值本身**无法用「指令里出现立即数」的方式核对；机器核对的是「它是与 begin 相邻的第二个指针」与「元素 8 字节」。
inline constexpr std::uintptr_t kItemConfigCollectibleEndOffset = 0x8;
inline constexpr std::uintptr_t kItemConfigCollectibleEndWidth = 8;

// 饰品向量的起始指针（`ItemConfig` 的 `std::vector<Item*>` begin）：`ItemConfig::GetTrinket(int)` 就是拿它 + 元素索引取指针的（confirmed）
//   证据：0x003c0c9c —— `ldp x8, x9, [x0, #0x18]` 一次取出本字段（+0x18，向量起点）与 +0x20（向量终点）；紧随的 `sub` + `lsr #3` 把两者之差除以 8 ⇒ 元素是 8 字节指针 ⇒ 这是一对 `std::vector<Item*>` 的边界。`ItemConfig::GetTrinket(int)` 这个引擎自己的访问器就是语义锚点（它专门用来按索引取饰品）。
//   证据：0x003c0ca8 —— `lsr …, #3`：两指针之差 ÷ 8 ⇒ 元素是 8 字节指针（不是内联元素）
inline constexpr std::uintptr_t kItemConfigTrinketBeginOffset = 0x18;
inline constexpr std::uintptr_t kItemConfigTrinketBeginWidth = 8;

// 饰品向量的结束指针（同一对向量的 end，begin/end 之差 ÷ 8 即元素个数）（confirmed）
//   证据：0x003c0ca8 —— 同一条 `ldp x8, x9, [x0, #0x18]` 的**第二寄存器**就是本字段（+0x20）：`ldp` 一次读出相邻的两个 8 字节指针，随后 `sub x9, x9, x8` + `lsr #3` 说明它们正是同一向量的 begin/end。⚠️ 局限：`ldp` 隐含第二个偏移，指令里不出现 `#0x20` ⇒ 本行**偏移值本身**无法用「指令里出现立即数」的方式核对；机器核对的是「它是与 begin 相邻的第二个指针」与「元素 8 字节」。
inline constexpr std::uintptr_t kItemConfigTrinketEndOffset = 0x20;
inline constexpr std::uintptr_t kItemConfigTrinketEndWidth = 8;

// 空物品向量的起始指针（`ItemConfig` 的 `std::vector<Item*>` begin）：`ItemConfig::GetNullItem(int)` 就是拿它 + 元素索引取指针的（confirmed）
//   证据：0x003c0cc8 —— `ldp x8, x9, [x0, #0x30]` 一次取出本字段（+0x30，向量起点）与 +0x38（向量终点）；紧随的 `sub` + `lsr #3` 把两者之差除以 8 ⇒ 元素是 8 字节指针 ⇒ 这是一对 `std::vector<Item*>` 的边界。`ItemConfig::GetNullItem(int)` 这个引擎自己的访问器就是语义锚点（它专门用来按索引取空物品）。
//   证据：0x003c0cd0 —— `lsr …, #3`：两指针之差 ÷ 8 ⇒ 元素是 8 字节指针（不是内联元素）
inline constexpr std::uintptr_t kItemConfigNullItemBeginOffset = 0x30;
inline constexpr std::uintptr_t kItemConfigNullItemBeginWidth = 8;

// 空物品向量的结束指针（同一对向量的 end，begin/end 之差 ÷ 8 即元素个数）（confirmed）
//   证据：0x003c0cd0 —— 同一条 `ldp x8, x9, [x0, #0x30]` 的**第二寄存器**就是本字段（+0x38）：`ldp` 一次读出相邻的两个 8 字节指针，随后 `sub x9, x9, x8` + `lsr #3` 说明它们正是同一向量的 begin/end。⚠️ 局限：`ldp` 隐含第二个偏移，指令里不出现 `#0x38` ⇒ 本行**偏移值本身**无法用「指令里出现立即数」的方式核对；机器核对的是「它是与 begin 相邻的第二个指针」与「元素 8 字节」。
inline constexpr std::uintptr_t kItemConfigNullItemEndOffset = 0x38;
inline constexpr std::uintptr_t kItemConfigNullItemEndWidth = 8;

// 卡牌向量的起始指针（`ItemConfig` 的 `std::vector<Item*>` begin）：`ItemConfig::GetCard(int)` 就是拿它 + 元素索引取指针的（confirmed）
//   证据：0x003c0d18 —— `ldp x8, x9, [x0, #0x48]` 一次取出本字段（+0x48，向量起点）与 +0x50（向量终点）；紧随的 `sub` + `lsr #3` 把两者之差除以 8 ⇒ 元素是 8 字节指针 ⇒ 这是一对 `std::vector<Item*>` 的边界。`ItemConfig::GetCard(int)` 这个引擎自己的访问器就是语义锚点（它专门用来按索引取卡牌）。
//   证据：0x003c0d20 —— `lsr …, #3`：两指针之差 ÷ 8 ⇒ 元素是 8 字节指针（不是内联元素）
inline constexpr std::uintptr_t kItemConfigCardBeginOffset = 0x48;
inline constexpr std::uintptr_t kItemConfigCardBeginWidth = 8;

// 卡牌向量的结束指针（同一对向量的 end，begin/end 之差 ÷ 8 即元素个数）（confirmed）
//   证据：0x003c0d20 —— 同一条 `ldp x8, x9, [x0, #0x48]` 的**第二寄存器**就是本字段（+0x50）：`ldp` 一次读出相邻的两个 8 字节指针，随后 `sub x9, x9, x8` + `lsr #3` 说明它们正是同一向量的 begin/end。⚠️ 局限：`ldp` 隐含第二个偏移，指令里不出现 `#0x50` ⇒ 本行**偏移值本身**无法用「指令里出现立即数」的方式核对；机器核对的是「它是与 begin 相邻的第二个指针」与「元素 8 字节」。
inline constexpr std::uintptr_t kItemConfigCardEndOffset = 0x50;
inline constexpr std::uintptr_t kItemConfigCardEndWidth = 8;

// 药丸向量的起始指针（`ItemConfig` 的 `std::vector<Item*>` begin）：`ItemConfig::GetPillEffect(ePillEffect)` 就是拿它 + 元素索引取指针的（confirmed）
//   证据：0x003c0cf0 —— `ldp x8, x9, [x0, #0x60]` 一次取出本字段（+0x60，向量起点）与 +0x68（向量终点）；紧随的 `sub` + `lsr #3` 把两者之差除以 8 ⇒ 元素是 8 字节指针 ⇒ 这是一对 `std::vector<Item*>` 的边界。`ItemConfig::GetPillEffect(ePillEffect)` 这个引擎自己的访问器就是语义锚点（它专门用来按索引取药丸）。
//   证据：0x003c0cf8 —— `lsr …, #3`：两指针之差 ÷ 8 ⇒ 元素是 8 字节指针（不是内联元素）
inline constexpr std::uintptr_t kItemConfigPillEffectBeginOffset = 0x60;
inline constexpr std::uintptr_t kItemConfigPillEffectBeginWidth = 8;

// 药丸向量的结束指针（同一对向量的 end，begin/end 之差 ÷ 8 即元素个数）（confirmed）
//   证据：0x003c0cf8 —— 同一条 `ldp x8, x9, [x0, #0x60]` 的**第二寄存器**就是本字段（+0x68）：`ldp` 一次读出相邻的两个 8 字节指针，随后 `sub x9, x9, x8` + `lsr #3` 说明它们正是同一向量的 begin/end。⚠️ 局限：`ldp` 隐含第二个偏移，指令里不出现 `#0x68` ⇒ 本行**偏移值本身**无法用「指令里出现立即数」的方式核对；机器核对的是「它是与 begin 相邻的第二个指针」与「元素 8 字节」。
inline constexpr std::uintptr_t kItemConfigPillEffectEndOffset = 0x68;
inline constexpr std::uintptr_t kItemConfigPillEffectEndWidth = 8;

// 玩家形态向量的起始指针（`ItemConfig` 的 `std::vector<Item*>` begin）：`ItemConfig::GetPlayerForm(ePlayerForm)` 就是拿它 + 元素索引取指针的（confirmed）
//   证据：0x003c0d40 —— `ldp x8, x9, [x0, #0x90]` 一次取出本字段（+0x90，向量起点）与 +0x98（向量终点）；紧随的 `sub` + `lsr #3` 把两者之差除以 8 ⇒ 元素是 8 字节指针 ⇒ 这是一对 `std::vector<Item*>` 的边界。`ItemConfig::GetPlayerForm(ePlayerForm)` 这个引擎自己的访问器就是语义锚点（它专门用来按索引取玩家形态）。
//   证据：0x003c0d48 —— `lsr …, #3`：两指针之差 ÷ 8 ⇒ 元素是 8 字节指针（不是内联元素）
inline constexpr std::uintptr_t kItemConfigPlayerFormBeginOffset = 0x90;
inline constexpr std::uintptr_t kItemConfigPlayerFormBeginWidth = 8;

// 玩家形态向量的结束指针（同一对向量的 end，begin/end 之差 ÷ 8 即元素个数）（confirmed）
//   证据：0x003c0d48 —— 同一条 `ldp x8, x9, [x0, #0x90]` 的**第二寄存器**就是本字段（+0x98）：`ldp` 一次读出相邻的两个 8 字节指针，随后 `sub x9, x9, x8` + `lsr #3` 说明它们正是同一向量的 begin/end。⚠️ 局限：`ldp` 隐含第二个偏移，指令里不出现 `#0x98` ⇒ 本行**偏移值本身**无法用「指令里出现立即数」的方式核对；机器核对的是「它是与 begin 相邻的第二个指针」与「元素 8 字节」。
inline constexpr std::uintptr_t kItemConfigPlayerFormEndOffset = 0x98;
inline constexpr std::uintptr_t kItemConfigPlayerFormEndWidth = 8;

// 对外 API 只允许读这些字段（`confidence == confirmed`）。
// 当前可用：CollectibleBegin、CollectibleEnd、TrinketBegin、TrinketEnd、NullItemBegin、NullItemEnd、CardBegin、CardEnd、PillEffectBegin、PillEffectEnd、PlayerFormBegin、PlayerFormEnd

} // namespace isaac::runtime::layout
