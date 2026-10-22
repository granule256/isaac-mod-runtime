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

inline constexpr std::uint8_t kEntityFamiliarBuildId[20] = {
    0x91, 0xC7, 0x3F, 0xDD, 0x57, 0x50, 0x61, 0x31, 0x8D, 0x68, 0x88, 0x63, 0x16, 0xAF, 0xEA, 0xC7, 0x23, 0x88, 0xB2, 0xAB
};

// 轨道距离两个float，Lua getter独立快照，setter复制8B；PC CB4 property getter/setter完整复制证据，NSget_orbit_position以同Vector引用乘轨道坐标。（confirmed）
//   证据：0x000aff6c —— add x1,this,#0xD78，交Vector2乘法const引用，两个float；PC859ECD/DC拷贝两word到userdata+8。
//   证据：0x000ae894 —— 目标this+0xD78交Vector2::operator=，对应PC OrbitDistance真实property CB4。
inline constexpr std::uintptr_t kEntityFamiliarOrbitDistanceOffset = 0xD78;
inline constexpr std::uintptr_t kEntityFamiliarOrbitDistanceWidth = 8;

// 轨道速度float；PC CBC property checknumber后fstp f32，NS在轨道角度计算中作为帧乘数。（confirmed）
//   证据：0x000afed0 —— ldr s1,[this,#0xD80]，随后fmul帧×速度；PC859E28 checknumber，859E33 fstp f32，859E3C写字段。
inline constexpr std::uintptr_t kEntityFamiliarOrbitSpeedOffset = 0xD80;
inline constexpr std::uintptr_t kEntityFamiliarOrbitSpeedWidth = 4;

// 轨道层signed int32，默认/移除-1；PC CC0 checkinteger写低32，NS符号位分支与AddToOrbit实参写入均对应。（confirmed）
//   证据：0x000aff28 —— ldr w8层后检查bit31；正常负层返回Pos。
//   证据：0x000ae880 —— str w19,[this,#0xD84]，w19是Layer参数；AE874先存-1，PC setter859D73写checkinteger低32。
inline constexpr std::uintptr_t kEntityFamiliarOrbitLayerOffset = 0xD84;
inline constexpr std::uintptr_t kEntityFamiliarOrbitLayerWidth = 4;

// 对外 API 只允许读这些字段（`confidence == confirmed`）。
// 当前可用：OrbitDistance、OrbitSpeed、OrbitLayer

} // namespace isaac::runtime::layout
