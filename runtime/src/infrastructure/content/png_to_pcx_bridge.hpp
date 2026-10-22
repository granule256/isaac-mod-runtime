#pragma once

#include <cstddef>
#include <cstdint>

namespace isaac::runtime::content {

// 注入式解压器：把一段**完整的 zlib 流**解压进 `dest`（容量 `dest_len`），全部写满后返回 0。
// 形状与 zlib 的 `uncompress` 一致 —— 由调用方注入：设备侧包真实 zlib 符号，宿主测试包系统 zlib。
// 约定：成功时 `dest` 的前 `dest_len` 字节被完整写出（部分写出视为失败）。
enum class PngToPcxFailure : uint32_t { None, InvalidPng, Unsupported, Budget, Allocation, Inflate };
using RowSink = bool (*)(void*, const uint8_t*, size_t);
using InflateRowsFn = bool (*)(const uint8_t*, size_t, size_t, size_t, void*, RowSink);
// 单次inflate，调用方逐行消费；完整校验zlib流尾，额外输出视为错误。
bool PngToPcxStreaming(const uint8_t* png, size_t png_size, InflateRowsFn inflate_rows,
                       uint8_t** out, size_t* out_size, PngToPcxFailure* failure = nullptr) noexcept;

using InflateFn = int (*)(uint8_t* dest, size_t dest_len, const uint8_t* src, size_t src_len);

// ── 一次转码的**峰值内存预算**与**峰值上界公式**（批次 402）────────────────────────
//
// ## 为什么要有这段（真机事故换来的）
//
// `PngToPcx` 声明成 `noexcept`，但内部用 `std::vector` / `operator new`；而我们模块的
// **假堆只有 128 MiB**（`runtime/source/program/setting.hpp` 的 `exl::setting::HeapSize = 0x8000000`，
// 是**整个模块 malloc 的唯一来源**）。分配失败时抛 `std::bad_alloc`，穿过 `noexcept` 边界
// ⇒ `std::terminate` ⇒ **整个游戏 abort**（2026-10-07 崩溃报告 `01791381539`：选模组角色进局、
// 停在加载画面直接退回 HOME；符号化栈落在 `PngToPcx → operator new`）。
// ⇒ 本批两条硬约束：① `PngToPcx` 里任何分配失败都必须变成 `return false`（见 .cpp）；
//   ② **绝不能**在预算不明的情况下申请（下面这条闸门）。
//
// ## 峰值不是一个量：一次转码要**同时**活着的东西
//
//   设 W/H = 像素宽高、c = 通道数（1/2/3/4）、n = 调用方读进内存的整份 PNG 字节数：
//   * `n`            —— 调用方持有的整份 PNG 文件（本函数不改它，但调用期间它占堆）；
//   * `idat`         —— 各 IDAT 块拼成的一份连续拷贝，`≤ n`（第二遍**一次性精确分配**，无几何扩容）；
//   * `raw`          —— 解压后的行缓冲 = `(W·c + 1)·H`；
//   * `line`+`previous` —— 两条解滤波行缓冲 = `2·W·c`；
//   * `row_rgba`     —— 逐行 RGBA = `4·W`；
//   * `result`       —— 输出 PCX = 128 字节头 + 4 平面逐行 RLE；**最坏 8 字节/像素**
//                       （每平面每像素最多 2 字节：`0xC0|run`(1) + 值(1)）⇒ `128 + 8·W·H`。
//   ⇒ 最坏峰值 `≤ 2·n + (W·c+1)·H + 2·W·c + 4·W + 128 + 8·W·H`（下面 `PngToPcxPeakUpperBound`）。
//
// ## 预算为什么是 64 MiB（= 假堆的一半）
//
//   假堆总 128 MiB，而它**同时**装着 Lua 状态、模块自身、转码缓存等常驻量 —— 真机实测
//   `arena` 已用 **47.4 MiB**（批次 181 读数更正，见 `mod_menu_native.hpp` 那段）。
//   把"单次转码峰值"卡在**一半（64 MiB）**：即便算上那 47.4 MiB 常驻，仍留有 ≥16 MiB 活动余量
//   （128 − 47.4 − 64 ≈ 16.6 MiB）给 malloc 碎片与引擎侧临时分配。这个数不像旧值那样"凭空"——
//   旧值 `kMaxDecodedBytes = 256 MiB` > 假堆总量，本身就是个必然踩穿的洞。
//
// ★ 预算与公式**只此一份**：`PngToPcx`（设备侧转码）与调用方预检（`ImagePcxPngVerdict`）都用它，
//   口径不可能漂移；改动只改这里。
inline constexpr std::uint64_t kPngToPcxPeakBudgetBytes = 64ull * 1024 * 1024;

//: 上面那条最坏峰值公式的实现。调用方预检只需 IHDR（W/H/颜色类型）+ 文件长度即可先算它。
[[nodiscard]] constexpr std::uint64_t PngToPcxPeakUpperBound(std::uint64_t png_size,
                                                             std::uint64_t width,
                                                             std::uint64_t height,
                                                             std::uint64_t channels) noexcept {
    const std::uint64_t row_bytes = width * channels;
    // 分段编码输出与最终连续输出最多并存，行工作区与zlib工作区计入。
    return 2ull * png_size + 3ull * row_bytes + 12ull * width + 2ull * 128ull +
           16ull * width * height + 128ull * 1024ull;
}

// 把 PNG（8bit、非隔行、颜色类型 0/2/4/6）转成引擎认识的 PCX 字节：
//   128 字节头 + 8bpp × 4 平面（RGBA）逐行逐平面 RLE，无尾部调色板（与本体 `*.pcx` 逐字段一致）。
// 成功：`*out` 指向新分配的缓冲（调用方须 `delete[]` 释放）、`*out_size` 写入字节数，返回 true。
// 形态不支持（调色板/16bit/隔行/未知色型）或字节损坏：返回 false（不抛、不崩、不越界读）。
// ★ 批次 402：**任何分配失败 / 峰值超 `kPngToPcxPeakBudgetBytes` 也返回 false**（绝不抛、绝不 abort）。
bool PngToPcx(const uint8_t* png, size_t png_size, InflateFn inflate_one,
              uint8_t** out, size_t* out_size) noexcept;

}  // namespace isaac::runtime::content
