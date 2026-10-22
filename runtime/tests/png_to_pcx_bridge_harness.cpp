// 宿主测试夹具：把 `PngToPcx` 桥接成「读一个 PNG 文件、写一个 PCX 文件」的可执行，
// 供 `test_png_to_pcx_bridge.py` 与 `tools/png_to_pcx.py` 做逐字节对照。
//
// `InflateFn` 用系统 zlib 的 `uncompress` 充当（与设备侧真实 zlib 同形状）：一次解压完整 zlib 流、
// 写满 dest_len 才成功。这是本夹具唯一允许的第三方依赖 —— 仅在宿主测试里，设备侧不引 zlib。
//
// ★★★ 批次 402：加一条**故障注入**开关 —— 真机崩溃的根因是"分配失败时 `bad_alloc` 从 `noexcept`
//   里逃出来 ⇒ `terminate`"。宿主没法把假堆饿死，那就**把分配本身弄失败**：
//     `--fail-alloc-after K`：在 `PngToPcx` 调用期间允许 K 次成功分配，第 K+1 次 `operator new`
//     直接抛 `std::bad_alloc`（只在该调用期间生效，读文件的分配不受影响）。
//   判据 = 进程**正常退出**、打印 `REJECT`、退出码 1（**不是**被 abort/信号带走）。
#include "infrastructure/content/png_to_pcx_bridge.hpp"

#include <zlib.h>
#include "infrastructure/content/inflate_rows.hpp"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
#include <vector>
#include <chrono>

namespace {
[[maybe_unused]] int HostInflate(std::uint8_t* dest, std::size_t dest_len, const std::uint8_t* src,
                std::size_t src_len) {
    unsigned long out = static_cast<unsigned long>(dest_len);
    const int r = uncompress(dest, &out, src, static_cast<unsigned long>(src_len));
    if (r == Z_OK && out == dest_len) return 0;
    return -1;
}

// ── 故障注入状态（只在 `PngToPcx` 调用期间置位）──────────────────────────────────
bool g_inject = false;
long long g_allow = 0;

void* InjectAlloc(std::size_t n) {
    if (g_inject) {
        if (g_allow <= 0) {
            throw std::bad_alloc();  // 第 K+1 次分配：注入失败
        }
        --g_allow;
    }
    void* p = std::malloc(n == 0 ? 1 : n);
    if (p == nullptr) {
        throw std::bad_alloc();
    }
    return p;
}
}  // namespace

// 替换全局 operator new/delete：让 `std::vector` / `new` 的分配都能被注入失败。
// （`std::malloc` 直调者不受影响；设备侧 zlib 用 malloc、宿主 zlib 亦用 malloc。）
void* operator new(std::size_t n) { return InjectAlloc(n); }
void* operator new[](std::size_t n) { return InjectAlloc(n); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: %s <in.png> <out.pcx> [--fail-alloc-after K]\n", argv[0]);
        return 2;
    }
    long long failAfter = -1;  // < 0 = 不注入
    if (argc >= 5 && std::strcmp(argv[3], "--fail-alloc-after") == 0) {
        failAfter = std::strtoll(argv[4], nullptr, 10);
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
    g_allow = failAfter;
    g_inject = failAfter >= 0;
    const bool ok = isaac::runtime::content::PngToPcx(
        png.data(), png.size(), &HostInflate, &pcx, &pcx_size);
    g_inject = false;
    if (!ok || pcx == nullptr) {
        std::printf("REJECT\n");
        return 1;  // 形态不支持 / 损坏 / 分配失败：与参考实现一致地拒绝（且**没崩**）
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
