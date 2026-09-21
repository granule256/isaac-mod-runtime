// 宿主测试夹具：把 `PngToPcx` 桥接成「读一个 PNG 文件、写一个 PCX 文件」的可执行，
// 供 `test_png_to_pcx_bridge.py` 与 `tools/png_to_pcx.py` 做逐字节对照。
//
// `InflateFn` 用系统 zlib 的 `uncompress` 充当（与设备侧真实 zlib 同形状）：一次解压完整 zlib 流、
// 写满 dest_len 才成功。这是本夹具唯一允许的第三方依赖 —— 仅在宿主测试里，设备侧不引 zlib。
#include "infrastructure/content/png_to_pcx_bridge.hpp"

#include <zlib.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace {
int HostInflate(std::uint8_t* dest, std::size_t dest_len, const std::uint8_t* src,
                std::size_t src_len) {
    unsigned long out = static_cast<unsigned long>(dest_len);
    const int r = uncompress(dest, &out, src, static_cast<unsigned long>(src_len));
    if (r == Z_OK && out == dest_len) return 0;
    return -1;
}
}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: %s <in.png> <out.pcx>\n", argv[0]);
        return 2;
    }
    FILE* in = std::fopen(argv[1], "rb");
    if (in == nullptr) {
        std::fprintf(stderr, "cannot open input\n");
        return 2;
    }
    std::vector<std::uint8_t> png;
    {
        std::uint8_t buf[1u << 16];
        std::size_t n = 0;
        while ((n = std::fread(buf, 1, sizeof(buf), in)) > 0) {
            png.insert(png.end(), buf, buf + n);
        }
    }
    std::fclose(in);

    std::uint8_t* pcx = nullptr;
    std::size_t pcx_size = 0;
    const bool ok = isaac::runtime::content::PngToPcx(
        png.data(), png.size(), &HostInflate, &pcx, &pcx_size);
    if (!ok || pcx == nullptr) {
        std::printf("REJECT\n");
        return 1;  // 形态不支持 / 损坏：与参考实现一致地拒绝
    }
    FILE* out = std::fopen(argv[2], "wb");
    if (out == nullptr) {
        delete[] pcx;
        std::fprintf(stderr, "cannot open output\n");
        return 2;
    }
    std::fwrite(pcx, 1, pcx_size, out);
    std::fclose(out);
    delete[] pcx;
    std::printf("OK\n");
    return 0;
}
