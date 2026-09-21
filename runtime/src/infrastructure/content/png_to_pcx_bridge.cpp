// 贴图桥转码器：PNG → PCX，供 `ImagePcxLoad` 入口中继回调在内存里把「只带 .png」的 Mod 资源
// 喂给引擎。逐字段复刻 `tools/png_to_pcx.py`（用本体 `*.pcx` 逐字段核对过）。
//
// 不引第三方库、不 vendoring stb_image：PNG 解码靠注入的 `InflateFn`（形状 = zlib `uncompress`），
// PCX 编码纯手写。跨 TU 的 `PngToPcx` 放在 `isaac::runtime::content` 命名空间（不放匿名命名空间）。

#include "infrastructure/content/png_to_pcx_bridge.hpp"

#include <array>
#include <cstdint>
#include <cstring>
#include <vector>

namespace isaac::runtime::content {
namespace {

constexpr std::size_t kPngSignatureSize = 8;
constexpr std::uint8_t kPngSignature[kPngSignatureSize] = {0x89, 0x50, 0x4E, 0x47,
                                                           0x0D, 0x0A, 0x1A, 0x0A};
// 输出上限：引擎不可能加载更大的贴图，超出视为损坏、直接拒绝（避免分配失控）。
constexpr std::uint64_t kMaxDecodedBytes = 256ull * 1024 * 1024;

// 大端读 32 位（PNG 多用大端）。
[[nodiscard]] std::uint32_t ReadBE32(const uint8_t* p) noexcept {
    return (static_cast<std::uint32_t>(p[0]) << 24) |
           (static_cast<std::uint32_t>(p[1]) << 16) |
           (static_cast<std::uint32_t>(p[2]) << 8) |
           (static_cast<std::uint32_t>(p[3]));
}

// Paeth 预测器（与 Python `_paeth` 一致：距离是绝对值，取最近的那一侧）。
[[nodiscard]] int Paeth(int left, int up, int up_left) noexcept {
    const int p = left + up - up_left;
    const int pa = p > left ? p - left : left - p;
    const int pb = p > up ? p - up : up - p;
    const int pc = p > up_left ? p - up_left : up_left - p;
    if (pa <= pb && pa <= pc) return left;
    return pb <= pc ? up : up_left;
}

// 把一行滤波后的 RGB(A) 扩成 4 通道 RGBA（与 Python `_decode` 的着色段一致）。
void ExpandChannels(const uint8_t* line, int width, int channels, int color_type,
                    uint8_t* rgba) noexcept {
    for (int x = 0; x < width; ++x) {
        const int at = x * channels;
        int r = 0, g = 0, b = 0, a = 255;
        if (color_type == 0) {        // 灰度
            r = g = b = line[at];
        } else if (color_type == 2) { // RGB
            r = line[at];
            g = line[at + 1];
            b = line[at + 2];
        } else if (color_type == 4) { // 灰度 + 透明
            r = g = b = line[at];
            a = line[at + 1];
        } else {                      // 6：RGBA
            r = line[at];
            g = line[at + 1];
            b = line[at + 2];
            a = line[at + 3];
        }
        const int base = x * 4;
        rgba[base] = static_cast<uint8_t>(r);
        rgba[base + 1] = static_cast<uint8_t>(g);
        rgba[base + 2] = static_cast<uint8_t>(b);
        rgba[base + 3] = static_cast<uint8_t>(a);
    }
}

// 逐平面 RLE 编码一行的一个通道（与 Python `_encode_pcx` 内层一致）。
void EncodePlane(std::vector<uint8_t>& body, const uint8_t* row, int width, int plane) {
    int x = 0;
    while (x < width) {
        const uint8_t value = row[x * 4 + plane];
        int run = 1;
        while (x + run < width && run < 63 && row[(x + run) * 4 + plane] == value) {
            ++run;
        }
        if (run > 1 || value >= 0xC0) {
            body.push_back(static_cast<uint8_t>(0xC0 | run));
            body.push_back(value);
        } else {
            body.push_back(value);
        }
        x += run;
    }
}

}  // namespace

bool PngToPcx(const uint8_t* png, size_t png_size, InflateFn inflate_one,
              uint8_t** out, size_t* out_size) noexcept {
    if (png == nullptr || inflate_one == nullptr || out == nullptr || out_size == nullptr ||
        png_size < kPngSignatureSize + 12) {
        return false;
    }
    if (std::memcmp(png, kPngSignature, kPngSignatureSize) != 0) {
        return false;  // 不是 PNG
    }

    int width = 0, height = 0, bit_depth = 0, color_type = 0, interlace = 0;
    std::vector<uint8_t> idat;
    idat.reserve(1 << 16);

    size_t offset = kPngSignatureSize;
    bool sawIhdr = false;
    while (offset + 12 <= png_size) {
        const uint32_t length = ReadBE32(png + offset);
        const uint8_t* type = png + offset + 4;
        const uint8_t* data = png + offset + 8;
        if (offset + 12 + static_cast<size_t>(length) > png_size) {
            return false;  // 截断的块
        }
        const bool isIhdr = std::memcmp(type, "IHDR", 4) == 0;
        const bool isIdat = std::memcmp(type, "IDAT", 4) == 0;
        if (isIhdr) {
            if (length < 13) return false;
            width = static_cast<int>(ReadBE32(data));
            height = static_cast<int>(ReadBE32(data + 4));
            bit_depth = data[8];
            color_type = data[9];
            // data[10]=压缩, data[11]=滤波, data[12]=隔行
            interlace = data[12];
            sawIhdr = true;
        } else if (isIdat) {
            idat.insert(idat.end(), data, data + length);
        }
        offset += 12 + static_cast<size_t>(length);
        if (std::memcmp(type, "IEND", 4) == 0) break;
    }
    if (!sawIhdr) return false;
    if (bit_depth != 8 || interlace != 0) return false;  // 只支持 8bit 非隔行
    int channels = 0;
    switch (color_type) {
        case 0: channels = 1; break;  // 灰度
        case 2: channels = 3; break;  // RGB
        case 4: channels = 2; break;  // 灰度 + 透明
        case 6: channels = 4; break;  // RGBA
        default: return false;        // 调色板等不支持
    }
    if (width <= 0 || height <= 0 || width > 0xFFFF || height > 0xFFFF) return false;
    if (idat.empty()) return false;

    const int row_bytes = width * channels;
    // 溢出与上限双重防护。
    const std::uint64_t raw_size =
        static_cast<std::uint64_t>(row_bytes + 1) * static_cast<std::uint64_t>(height);
    if (raw_size == 0 || raw_size > kMaxDecodedBytes) return false;

    std::vector<uint8_t> raw(raw_size, 0);
    if (inflate_one(raw.data(), static_cast<size_t>(raw_size), idat.data(), idat.size()) != 0) {
        return false;  // 解压失败或没写满
    }

    std::vector<uint8_t> rgba(static_cast<size_t>(width) * static_cast<size_t>(height) * 4, 0);
    std::vector<uint8_t> previous(static_cast<size_t>(row_bytes), 0);
    std::vector<uint8_t> line(static_cast<size_t>(row_bytes), 0);
    for (int y = 0; y < height; ++y) {
        const size_t row_start = static_cast<size_t>(y) * static_cast<size_t>(row_bytes + 1);
        const int filter_type = raw[row_start];
        std::memcpy(line.data(), raw.data() + row_start + 1, static_cast<size_t>(row_bytes));
        switch (filter_type) {
            case 0:  // 无
                break;
            case 1:  // Sub
                for (int i = channels; i < row_bytes; ++i) {
                    line[i] = static_cast<uint8_t>((line[i] + line[i - channels]) & 0xFF);
                }
                break;
            case 2:  // Up
                for (int i = 0; i < row_bytes; ++i) {
                    line[i] = static_cast<uint8_t>((line[i] + previous[i]) & 0xFF);
                }
                break;
            case 3:  // Average
                for (int i = 0; i < row_bytes; ++i) {
                    const int left = i >= channels ? line[i - channels] : 0;
                    line[i] = static_cast<uint8_t>((line[i] + ((left + previous[i]) >> 1)) & 0xFF);
                }
                break;
            case 4:  // Paeth
                for (int i = 0; i < row_bytes; ++i) {
                    const int left = i >= channels ? line[i - channels] : 0;
                    const int up = previous[i];
                    const int up_left = i >= channels ? previous[i - channels] : 0;
                    line[i] = static_cast<uint8_t>((line[i] + Paeth(left, up, up_left)) & 0xFF);
                }
                break;
            default:
                return false;  // 未知滤波
        }
        ExpandChannels(line.data(), width, channels, color_type,
                       rgba.data() + static_cast<size_t>(y) * static_cast<size_t>(width) * 4);
        std::memcpy(previous.data(), line.data(), static_cast<size_t>(row_bytes));
    }

    // --- PCX 编码 -------------------------------------------------------------
    std::array<uint8_t, 128> header{};
    header[0] = 10;   // magic
    header[1] = 5;    // version
    header[2] = 1;    // RLE
    header[3] = 8;    // bits per pixel
    // [4:12] = <HHHH(0,0,w-1,h-1)>
    header[4] = 0; header[5] = 0; header[6] = 0; header[7] = 0;
    header[8] = static_cast<uint8_t>((width - 1) & 0xFF);
    header[9] = static_cast<uint8_t>(((width - 1) >> 8) & 0xFF);
    header[10] = static_cast<uint8_t>((height - 1) & 0xFF);
    header[11] = static_cast<uint8_t>(((height - 1) >> 8) & 0xFF);
    // [12:16] = <HH(w,h)>
    header[12] = static_cast<uint8_t>(width & 0xFF);
    header[13] = static_cast<uint8_t>((width >> 8) & 0xFF);
    header[14] = static_cast<uint8_t>(height & 0xFF);
    header[15] = static_cast<uint8_t>((height >> 8) & 0xFF);
    header[64] = 1;   // 与本体保留字节一致
    header[65] = 4;   // 4 planes = RGBA
    // [66:68] = <H(w)>
    header[66] = static_cast<uint8_t>(width & 0xFF);
    header[67] = static_cast<uint8_t>((width >> 8) & 0xFF);
    // [68:70] = <H(1)>
    header[68] = 1; header[69] = 0;

    std::vector<uint8_t> body;
    body.reserve(static_cast<size_t>(width) * static_cast<size_t>(height) * 4 * 2 + 16);
    for (int y = 0; y < height; ++y) {
        const uint8_t* row = rgba.data() + static_cast<size_t>(y) * static_cast<size_t>(width) * 4;
        for (int plane = 0; plane < 4; ++plane) {
            EncodePlane(body, row, width, plane);
        }
    }

    const size_t total = header.size() + body.size();
    uint8_t* result = new (std::nothrow) uint8_t[total];
    if (result == nullptr) return false;
    std::memcpy(result, header.data(), header.size());
    if (!body.empty()) {
        std::memcpy(result + header.size(), body.data(), body.size());
    }
    *out = result;
    *out_size = total;
    return true;
}

}  // namespace isaac::runtime::content
