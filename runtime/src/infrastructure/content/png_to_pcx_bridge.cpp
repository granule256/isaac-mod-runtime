// 贴图桥转码器：PNG → PCX，供 `ImagePcxLoad` 入口中继回调在内存里把「只带 .png」的 Mod 资源
// 喂给引擎。逐字段复刻 `tools/png_to_pcx.py`（用本体 `*.pcx` 逐字段核对过）。
//
// 不引第三方库、不 vendoring stb_image：PNG 解码靠注入的 `InflateFn`（形状 = zlib `uncompress`），
// PCX 编码纯手写。跨 TU 的 `PngToPcx` 放在 `isaac::runtime::content` 命名空间（不放匿名命名空间）。
//
// ★★★ 批次 402（2026-10-07，真机崩溃 `01791381539` 换来的）：
//   `PngToPcx` 是 `noexcept`，但内部原来用 `std::vector` / `operator new`。模块假堆只有 128 MiB，
//   一旦分配失败，`std::vector` 走 `__throw_bad_alloc` ⇒ 抛 `std::bad_alloc` ⇒ 穿过 `noexcept`
//   边界 ⇒ `std::terminate` ⇒ **整个游戏 abort**（现象：选模组角色进局、停在加载画面退回 HOME）。
//   ⇒ 本文件三条硬约束：
//     ① **全程 nothrow 分配**：本模块的构建**关掉了 C++ 异常**（`-fno-exceptions`，所以连
//        `try {} catch (...)` 都编译不过）⇒ 不能用 try/catch 兜、也不能用会抛的 `std::vector`。
//        一律用 `new (std::nothrow)`（见下面 `NothrowBytes`）+ 显式判空，**任一分配失败就
//        `return false`**。**不许**改成"抛给上层接"（上层穿的是引擎的 C 栈）。
//     ② 进入任何分配之前先做**峰值闸门**：用公共头里的 `PngToPcxPeakUpperBound(...)` 算最坏峰值，
//        超 `kPngToPcxPeakBudgetBytes`（64 MiB = 假堆的一半）就直接 `return false`。
//        旧的 `kMaxDecodedBytes = 256 MiB` **大于整个假堆**，本身就是个必然踩穿的洞，已删除。
//     ③ 失败的契约不变：返回 `false` + 不写 `*out` —— 调用方已有
//        `if (!ok || pcx == nullptr) { ++convertFailures; return false; }` 这条分支。

#include "infrastructure/content/png_to_pcx_bridge.hpp"

#include <array>
#include <cstdint>
#include <cstring>
#include <new>

namespace isaac::runtime::content {
namespace {

constexpr std::size_t kPngSignatureSize = 8;
constexpr std::uint8_t kPngSignature[kPngSignatureSize] = {0x89, 0x50, 0x4E, 0x47,
                                                           0x0D, 0x0A, 0x1A, 0x0A};

// 无异常的小缓冲（批次 402）。本模块的构建**关掉了 C++ 异常**：`std::vector` 的分配失败会走
// `__throw_bad_alloc` ⇒ 直接 abort（这正是 2026-10-07 崩溃的根因）。所以这里全用
// `new (std::nothrow)` + 显式判空：失败 = `Resize` 返回 false = 调用方 `return false`，进程不受影响。
class NothrowBytes {
public:
    NothrowBytes() noexcept = default;
    NothrowBytes(const NothrowBytes&) = delete;
    NothrowBytes& operator=(const NothrowBytes&) = delete;
    ~NothrowBytes() { delete[] data_; }

    //: 申请 `n` 字节（**不清零**）。失败返回 false 且对象保持原状（调用方据此 return false）。
    [[nodiscard]] bool Resize(std::size_t n) {
        if (n == size_) {
            return true;
        }
        std::uint8_t* next = nullptr;
        if (n != 0) {
            next = new (std::nothrow) std::uint8_t[n];
            if (next == nullptr) {
                return false;
            }
        }
        delete[] data_;
        data_ = next;
        size_ = n;
        return true;
    }

    [[nodiscard]] std::uint8_t* data() noexcept { return data_; }
    [[nodiscard]] std::size_t size() const noexcept { return size_; }

private:
    std::uint8_t* data_ = nullptr;
    std::size_t size_ = 0;
};

// 固定64KiB分段：避免几何扩容与整幅raw，最终仅一次精确连续拼接。
class EncodedBlocks {
    struct Block { Block* next; size_t used; uint8_t bytes[65536]; };
    Block* first_ = nullptr;
    Block* last_ = nullptr;
    size_t size_ = 0;
public:
    ~EncodedBlocks() { while(first_) { auto* next=first_->next; delete first_; first_=next; } }
    size_t size() const noexcept { return size_; }
    bool Append(const uint8_t* data, size_t n) noexcept {
        while(n) {
            if(!last_ || last_->used==sizeof(last_->bytes)) {
                auto* block=new (std::nothrow) Block;
                if(!block) return false;
                block->next=nullptr; block->used=0;
                if(last_) last_->next=block; else first_=block;
                last_=block;
            }
            const auto room=sizeof(last_->bytes)-last_->used;
            const auto take=n<room?n:room;
            std::memcpy(last_->bytes+last_->used,data,take);
            last_->used+=take; size_+=take; data+=take; n-=take;
        }
        return true;
    }
    void CopyTo(uint8_t* out) const noexcept {
        for(auto* b=first_; b; b=b->next) { std::memcpy(out,b->bytes,b->used); out+=b->used; }
    }
};

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
//
// ★ 2026-09-26（批次 135）：原来是"直接往 `std::vector body` 里 push"，而 `body` 按
//   **最坏情况 8 字节/像素**预留（`width*height*4*2`），最后还要再拷一份进结果缓冲 ——
//   一张 1404×933 的图峰值就是 20·W×H ≈ 26 MB，而本模块自己的堆（假堆）总共约 32 MB，
//   撞满就是 `bad_alloc`（2026-09-25/26 两次真机事故的根因）。
//   ⇒ 现在**同一份 run 逻辑服务两个 pass**：`out == nullptr` 时只数、否则照数出的位置写。
//   一个实现两条路，**尺寸与实际写入不可能对不上**（这是这次改写最容易出错的地方，
//   所以刻意不做成两份代码）。
size_t WalkPlaneRuns(const uint8_t* row, int width, int plane, uint8_t* out) {
    size_t written = 0;
    int x = 0;
    while (x < width) {
        const uint8_t value = row[x * 4 + plane];
        int run = 1;
        while (x + run < width && run < 63 && row[(x + run) * 4 + plane] == value) {
            ++run;
        }
        if (run > 1 || value >= 0xC0) {
            if (out != nullptr) {
                out[written] = static_cast<uint8_t>(0xC0 | run);
                out[written + 1] = value;
            }
            written += 2;
        } else {
            if (out != nullptr) {
                out[written] = value;
            }
            written += 1;
        }
        x += run;
    }
    return written;
}

//: 只数：第 `y` 行四个平面的 RLE 字节数（第一遍用，零额外内存）。
size_t PlaneRowRunBytes(const uint8_t* row, int width) {
    size_t total = 0;
    for (int plane = 0; plane < 4; ++plane) {
        total += WalkPlaneRuns(row, width, plane, nullptr);
    }
    return total;
}

//: 写入：把第 `y` 行四个平面写进 `out`（第二遍用），返回写入字节数（与上面数出的一致）。
size_t WritePlaneRowRuns(const uint8_t* row, int width, uint8_t* out) {
    size_t written = 0;
    for (int plane = 0; plane < 4; ++plane) {
        written += WalkPlaneRuns(row, width, plane, out + written);
    }
    return written;
}

}  // namespace

static bool Convert(const uint8_t* png, size_t png_size, InflateFn inflate_one, InflateRowsFn inflate_rows,
                    uint8_t** out, size_t* out_size, PngToPcxFailure* failure) noexcept {
    PngToPcxFailure localFailure{};
    if(!failure) failure=&localFailure;
    *failure=PngToPcxFailure::InvalidPng;
    if (png == nullptr || (inflate_one == nullptr && inflate_rows == nullptr) || out == nullptr || out_size == nullptr ||
        png_size < kPngSignatureSize + 12) {
        return false;
    }
    if (std::memcmp(png, kPngSignature, kPngSignatureSize) != 0) {
        return false;  // 不是 PNG
    }

    // 第一遍：扫块头 —— 取 IHDR，并累加 IDAT 总长（用于第二遍**一次性精确分配**，
    // 避免 `std::vector` 式的"边插边几何扩容"（那会在失败时抛、且峰值算不清））。
    int width = 0, height = 0, bit_depth = 0, color_type = 0, interlace = 0;
    std::size_t idat_bytes = 0;
    bool sawIhdr = false;
    for (std::size_t offset = kPngSignatureSize; offset + 12 <= png_size;) {
        const uint32_t length = ReadBE32(png + offset);
        const uint8_t* type = png + offset + 4;
        const uint8_t* data = png + offset + 8;
        if (offset + 12 + static_cast<size_t>(length) > png_size) {
            return false;  // 截断的块
        }
        if (std::memcmp(type, "IHDR", 4) == 0) {
            if (length < 13) return false;
            width = static_cast<int>(ReadBE32(data));
            height = static_cast<int>(ReadBE32(data + 4));
            bit_depth = data[8];
            color_type = data[9];
            // data[10]=压缩, data[11]=滤波, data[12]=隔行
            interlace = data[12];
            sawIhdr = true;
        } else if (std::memcmp(type, "IDAT", 4) == 0) {
            idat_bytes += length;
        }
        offset += 12 + static_cast<size_t>(length);
        if (std::memcmp(type, "IEND", 4) == 0) break;
    }
    if (!sawIhdr) return false;
    *failure=PngToPcxFailure::Unsupported;
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
    if (idat_bytes == 0) return false;

    const int row_bytes = width * channels;
    // ★★★ 批次 402：进任何分配之前先做**峰值闸门**（公式与预算都在 `.hpp` 里，与调用方预检同源）。
    //   旧的单一"解码后上限"是 256 MiB —— 比整个假堆（128 MiB）还大，等于没设限。
    //   现在按"整条路最坏要同时活着多少"算：`2·n + raw + 2·行字节 + 4·W + 128 + 8·W·H`。
    const std::uint64_t raw_size =
        static_cast<std::uint64_t>(row_bytes + 1) * static_cast<std::uint64_t>(height);
    const std::uint64_t peak =
        PngToPcxPeakUpperBound(static_cast<std::uint64_t>(png_size),
                               static_cast<std::uint64_t>(width),
                               static_cast<std::uint64_t>(height),
                               static_cast<std::uint64_t>(channels));
    *failure=PngToPcxFailure::Budget;
    if (raw_size == 0 || peak > kPngToPcxPeakBudgetBytes) {
        return false;  // 超预算：拒绝（宁可这次不转，也别冒 bad_alloc 的险）
    }

    // ★★★ 402：全部缓冲**一次性 nothrow 分配**，逐条判空 ⇒ 任一失败都只是 `return false`。
    *failure=PngToPcxFailure::Allocation;
    NothrowBytes idat;
    if (!idat.Resize(idat_bytes)) return false;
    NothrowBytes raw;
    if (!inflate_rows && !raw.Resize(static_cast<std::size_t>(raw_size))) return false;

    NothrowBytes previous;
    if (!previous.Resize(static_cast<std::size_t>(row_bytes))) return false;
    std::memset(previous.data(), 0, previous.size());
    NothrowBytes line;
    if (!line.Resize(static_cast<std::size_t>(row_bytes))) return false;
    std::memset(line.data(), 0, line.size());
    NothrowBytes row_rgba;
    if (!row_rgba.Resize(static_cast<std::size_t>(width) * 4)) return false;
    std::memset(row_rgba.data(), 0, row_rgba.size());

    // 第二遍：把各 IDAT 块拼成**一段连续**的 zlib 流（`inflate_one` 要的就是这个形状）。
    // 第一遍已经校验过每个块的边界 ⇒ 这里不会越界读。
    {
        std::size_t pos = 0;
        for (std::size_t offset = kPngSignatureSize; offset + 12 <= png_size;) {
            const uint32_t length = ReadBE32(png + offset);
            const uint8_t* type = png + offset + 4;
            const uint8_t* data = png + offset + 8;
            if (std::memcmp(type, "IDAT", 4) == 0) {
                std::memcpy(idat.data() + pos, data, length);
                pos += length;
            }
            offset += 12 + static_cast<size_t>(length);
            if (std::memcmp(type, "IEND", 4) == 0) break;
        }
        if (pos != idat_bytes) return false;  // 两遍数出来的必须一致（防御）
    }

    *failure=PngToPcxFailure::Inflate;
    if (!inflate_rows && inflate_one(raw.data(), raw.size(), idat.data(), idat.size()) != 0) {
        return false;  // 解压失败或没写满
    }

    // ★ 批次 135：**不再留整幅 RGBA**（原来那一份是 4·W×H）。逐行解码包成一个 lambda，
    //   两个 pass（先数尺寸、再写输出）都调它 —— 同一份"解过滤 + 通道展开"逻辑，不会漂移。
    const auto decode_bytes = [&](const uint8_t* row) -> bool {
        const int filter_type = row[0];
        std::memcpy(line.data(), row + 1, static_cast<size_t>(row_bytes));
        switch (filter_type) {
            case 0:  // 无
                break;
            case 1:  // Sub
                for (int i = channels; i < row_bytes; ++i) {
                    line.data()[i] =
                        static_cast<uint8_t>((line.data()[i] + line.data()[i - channels]) & 0xFF);
                }
                break;
            case 2:  // Up
                for (int i = 0; i < row_bytes; ++i) {
                    line.data()[i] = static_cast<uint8_t>((line.data()[i] + previous.data()[i]) & 0xFF);
                }
                break;
            case 3:  // Average
                for (int i = 0; i < row_bytes; ++i) {
                    const int left = i >= channels ? line.data()[i - channels] : 0;
                    line.data()[i] =
                        static_cast<uint8_t>((line.data()[i] + ((left + previous.data()[i]) >> 1)) & 0xFF);
                }
                break;
            case 4:  // Paeth
                for (int i = 0; i < row_bytes; ++i) {
                    const int left = i >= channels ? line.data()[i - channels] : 0;
                    const int up = previous.data()[i];
                    const int up_left = i >= channels ? previous.data()[i - channels] : 0;
                    line.data()[i] =
                        static_cast<uint8_t>((line.data()[i] + Paeth(left, up, up_left)) & 0xFF);
                }
                break;
            default:
                *failure=PngToPcxFailure::InvalidPng;
                return false;  // 未知滤波
        }
        ExpandChannels(line.data(), width, channels, color_type, row_rgba.data());
        std::memcpy(previous.data(), line.data(), static_cast<size_t>(row_bytes));
        return true;
    };

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

    if (inflate_rows) {
        EncodedBlocks blocks;
        NothrowBytes encodedRow;
        *failure=PngToPcxFailure::Allocation;
        if (!encodedRow.Resize(static_cast<size_t>(width)*8)) return false;
        const auto consume = [&](const uint8_t* row) -> bool {
            if(!decode_bytes(row)) return false;
            const auto count=WritePlaneRowRuns(row_rgba.data(),width,encodedRow.data());
            if(!blocks.Append(encodedRow.data(),count)) { *failure=PngToPcxFailure::Allocation; return false; }
            return true;
        };
        struct Context { const decltype(consume)* consumer; } context{&consume};
        const auto sink=[](void* ctx,const uint8_t* row,size_t) -> bool {
            return (*static_cast<Context*>(ctx)->consumer)(row);
        };
        *failure=PngToPcxFailure::Inflate;
        if (!inflate_rows(idat.data(),idat.size(),static_cast<size_t>(row_bytes)+1,
                          static_cast<size_t>(height),&context,sink)) return false;
        const auto total=header.size()+blocks.size();
        *failure=PngToPcxFailure::Allocation;
        auto* result=new (std::nothrow) uint8_t[total];
        if(!result) return false;
        std::memcpy(result,header.data(),header.size());
        blocks.CopyTo(result+header.size());
        *failure=PngToPcxFailure::None;
        *out=result; *out_size=total;
        return true;
    }
    const auto decode_row=[&](int y) { return decode_bytes(raw.data()+static_cast<size_t>(y)*(row_bytes+1)); };

    // ★ 两遍式（批次 135）：第一遍只**数** body 精确字节数（零额外内存），
    //   第二遍直接写进**唯一**的输出缓冲 —— 既不再按"最坏情况 8 字节/像素"预留，
    //   也不再先攒一个 `std::vector body` 再拷一份。
    //   峰值因此从约 20·W×H 降到约 5·W×H（`raw` + 精确的 body）。
    size_t body_bytes = 0;
    for (int y = 0; y < height; ++y) {
        if (!decode_row(y)) return false;
        body_bytes += PlaneRowRunBytes(row_rgba.data(), width);
    }

    const size_t total = header.size() + body_bytes;  // 128 + 精确字节数
    uint8_t* result = new (std::nothrow) uint8_t[total];
    if (result == nullptr) return false;
    std::memcpy(result, header.data(), header.size());

    // 第二遍：`previous` 必须清零（PNG 的滤波器要的是"上一行解过滤结果"，
    // 第一遍结束时它停在最后一行 ⇒ 不清零会算错第二遍的所有 Up/Average/Paeth 行）。
    std::memset(previous.data(), 0, previous.size());
    size_t pos = header.size();
    for (int y = 0; y < height; ++y) {
        if (!decode_row(y)) {  // 第一遍已保证滤波合法，这里只防御
            delete[] result;
            return false;
        }
        pos += WritePlaneRowRuns(row_rgba.data(), width, result + pos);
    }
    if (pos != total) {  // 数出来的和写出来的必须一致（同一份 run 逻辑，理论上不可能不等）
        delete[] result;
        return false;
    }
    *out = result;
    *out_size = total;
    return true;
}

bool PngToPcx(const uint8_t* png, size_t png_size, InflateFn inflate_one, uint8_t** out,
              size_t* out_size) noexcept {
    return Convert(png,png_size,inflate_one,nullptr,out,out_size,nullptr);
}
bool PngToPcxStreaming(const uint8_t* png, size_t png_size, InflateRowsFn inflate_rows,
                       uint8_t** out, size_t* out_size, PngToPcxFailure* failure) noexcept {
    return Convert(png,png_size,nullptr,inflate_rows,out,out_size,failure);
}
}  // namespace isaac::runtime::content
