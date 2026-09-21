#pragma once

#include <cstddef>
#include <cstdint>

namespace isaac::runtime::content {

// 注入式解压器：把一段**完整的 zlib 流**解压进 `dest`（容量 `dest_len`），全部写满后返回 0。
// 形状与 zlib 的 `uncompress` 一致 —— 由调用方注入：设备侧包真实 zlib 符号，宿主测试包系统 zlib。
// 约定：成功时 `dest` 的前 `dest_len` 字节被完整写出（部分写出视为失败）。
using InflateFn = int (*)(uint8_t* dest, size_t dest_len, const uint8_t* src, size_t src_len);

// 把 PNG（8bit、非隔行、颜色类型 0/2/4/6）转成引擎认识的 PCX 字节：
//   128 字节头 + 8bpp × 4 平面（RGBA）逐行逐平面 RLE，无尾部调色板（与本体 `*.pcx` 逐字段一致）。
// 成功：`*out` 指向新分配的缓冲（调用方须 `delete[]` 释放）、`*out_size` 写入字节数，返回 true。
// 形态不支持（调色板/16bit/隔行/未知色型）或字节损坏：返回 false（不抛、不崩、不越界读）。
bool PngToPcx(const uint8_t* png, size_t png_size, InflateFn inflate_one,
              uint8_t** out, size_t* out_size) noexcept;

}  // namespace isaac::runtime::content
