// 贴图桥（`.pcx` 缺失时按需把同名 `.png` 转成 PCX 交给引擎）—— 独立实现文件。
//
// 2026-09-21 从 `hook_manager.cpp` 抽出来（评审第 2 条）：这段胶水自带状态（合成记录环形、
// 转码缓存、诊断结构体）并实现三条引擎入口回调，塞在 4000+ 行的 `hook_manager.cpp` 里既难读
// 也容易与挂点清单互相踩。抽出来后 `hook_manager.cpp` 只保留"注册 + 挂上绑定"两行。
//
// 交付点（来龙去脉见 `docs/评审-贴图桥架构与流程复盘-20260921.md`）：
//   ① `IContentManager::GetMountedFilePath`：`.pcx` 不在任何挂载点、但同名 `.png` 在时，
//      返回一条**合成的 `.pcx` 路径**，并记下 {文件名 → 该 `.png` 的真实挂载路径}；
//   ② `ImagePcx::Load`：原函数打不开合成路径 ⇒ 兜底按**文件名**查记录 → 只读记录里那条
//      **真实**路径 → 内存转 PCX → 调**对象自己的**内存版 Load（纯对象级、无锁）；
//   ③ `ImageManager::LoadImage` 文件版：**纯透传**（只计数），绝不回调贴图管理器。
//
// 三条硬纪律（都是真机事故换来的）：**不盲开路径**、**不在贴图管理器内部回调它自己**、
// **只读引擎自己解析成功过的路径**。

#include "image_pcx_bridge_hook.hpp"

#include "game_file_reader.hpp"
#include "infrastructure/content/png_to_pcx_bridge.hpp"
#include "infrastructure/relay/entry_relay_binding.hpp"
#include "relay/smart_pointer_shim.hpp"

#include <atomic>
#include <cstring>
#include <vector>

namespace {

// 挂上来的两组绑定（地址由 `bridge::Attach` 给定；为空 = 没挂上，回调一律直接放弃）。
const GameFileReader::Bindings* g_fileBindings = nullptr;
const GameFileReader::ImagePcxBindings* g_engineBindings = nullptr;

// 贴图桥（`.pcx` 内存转码）的状态与诊断
// ─────────────────────────────────────────────────────────────────────────────
// 诊断集中成**一个固定布局的结构体**（2026-09-21 评审第四条）：
// 过去是一个个散落的全局符号，读数要逐个手写 mangled 名（这轮被坑过多次：名字猜错 = 门禁红、
// 布局挪动 = 读错值）。现在读数**只认这一个符号**，按固定偏移解析，字段增减都在这里看。
struct ImagePcxDiagnostics {
    std::uint32_t hookCalls;        // 透传挂点（ImageManager 文件版）被调用次数
    std::uint32_t originalOk;       // 其中原函数成功（即真 `.pcx` 正常加载）次数
    std::uint32_t syntheticPaths;   // 合成的 `.pcx` 路径条数
    std::uint32_t fallbackAttempts; // 进入兜底判定（原函数失败且请求是 `.pcx`）次数
    std::uint32_t ringMiss;         // 合成记录未命中 ⇒ 安全放弃次数
    std::uint32_t readOk;           // 按记录读到 `.png` 字节次数
    std::uint32_t cacheHits;        // 转码缓存命中次数（省掉"读 + 解压 + 转码"）
    std::uint32_t cacheConversions; // 实际执行转码次数
    std::uint32_t convertFailures;  // 转码失败次数
    std::uint32_t fedOk;            // 喂给引擎后拿到非空贴图次数
    std::uint32_t bindingMask;      // 依赖绑定逐靶点掩码（0 = 全过）
    std::uint32_t pngOverrideWins;  // ★ 模组 PNG 顶掉**本体已有** `.pcx` 的次数（2026-09-21 由 reserved 改）
    char lastRequestPath[128];      // 最近一次 `.pcx` 请求路径（全部调用，不分来源）
    char lastFallbackPath[128];     // 最近一次"进入兜底判定"的路径
};
ImagePcxDiagnostics g_imagePcxDiag{};

// 合成记录环形：**文件名 → 该 `.png` 的真实挂载路径**。
// 只比文件名（引擎会把路径 `CreateCleanPath` 清洗后再交给对象加载，整串不一定相等）；
// 值用"合成时解析成功过的那条路径"，因此读它必然可开（这是三次 Abort 换来的纪律）。
constexpr std::size_t kImagePcxSyntheticPathBytes = 256;
constexpr std::size_t kImagePcxSyntheticNameBytes = 96;
constexpr std::size_t kImagePcxSyntheticRingSize = 16;
char g_ImagePcxSyntheticNames[kImagePcxSyntheticRingSize][kImagePcxSyntheticNameBytes]{};
char g_ImagePcxSyntheticPngPaths[kImagePcxSyntheticRingSize][kImagePcxSyntheticPathBytes]{};
std::atomic<std::uint32_t> g_ImagePcxSyntheticRingCount{0};

// 转码结果缓存（2026-09-21 评审第一条）：同一张 PNG 在真机上被问过 69 次、实际只读 10 次，
// 每次命中都要重走"读文件 + inflate + 转码"。键 = 该 `.png` 的真实挂载路径（含模组目录，
// 足以区分不同模组里的同名文件）；值是转好的 PCX 字节。LRU + 总字节预算（默认 8 MiB）。
struct ImagePcxCacheEntry {
    char path[kImagePcxSyntheticPathBytes]{};
    std::vector<u8> pcx;
    std::uint64_t lastUse{0};
};
constexpr std::size_t kImagePcxCacheEntries = 4;
constexpr std::size_t kImagePcxCacheBudgetBytes = 8u * 1024u * 1024u;
ImagePcxCacheEntry g_ImagePcxCache[kImagePcxCacheEntries]{};
std::uint64_t g_ImagePcxCacheClock{0};
std::size_t g_ImagePcxCacheBytes{0};

// 从路径里取"最后一节"（文件名）。匹配合成记录用它：清洗可能改变目录部分，文件名不变。
const char* ImagePcxBasename(const char* path) noexcept {
    const char* base = path;
    for (const char* cursor = path; *cursor != '\0'; ++cursor) {
        if (*cursor == '/' || *cursor == '\\') {
            base = cursor + 1;
        }
    }
    return base;
}

// 查缓存：命中返回该条目的 PCX 字节指针（有效到下一次插入为止），否则返回空。
const std::vector<u8>* ImagePcxCacheLookup(const char* pngMounted) noexcept {
    for (std::size_t i = 0; i < kImagePcxCacheEntries; ++i) {
        ImagePcxCacheEntry& entry = g_ImagePcxCache[i];
        if (entry.pcx.empty()) {
            continue;
        }
        if (std::strcmp(entry.path, pngMounted) == 0) {
            entry.lastUse = ++g_ImagePcxCacheClock;
            return &entry.pcx;
        }
    }
    return nullptr;
}

// 插入缓存：按 LRU + 预算淘汰；单条超过预算则不缓存（宁可每次重转，也不撑爆堆）。
void ImagePcxCacheInsert(const char* pngMounted, const std::uint8_t* pcx, std::size_t size) {
    if (pcx == nullptr || size == 0 || size > kImagePcxCacheBudgetBytes) {
        return;
    }
    std::size_t slot = 0;
    bool found = false;
    for (std::size_t i = 0; i < kImagePcxCacheEntries && !found; ++i) {
        if (std::strcmp(g_ImagePcxCache[i].path, pngMounted) == 0 || g_ImagePcxCache[i].pcx.empty()) {
            slot = i;
            found = true;
        }
    }
    if (!found) {  // 全满：挑最久没用过的那条
        slot = 0;
        for (std::size_t i = 1; i < kImagePcxCacheEntries; ++i) {
            if (g_ImagePcxCache[i].lastUse < g_ImagePcxCache[slot].lastUse) {
                slot = i;
            }
        }
    }
    g_ImagePcxCacheBytes -= g_ImagePcxCache[slot].pcx.size();
    std::strncpy(g_ImagePcxCache[slot].path, pngMounted, kImagePcxSyntheticPathBytes - 1);
    g_ImagePcxCache[slot].path[kImagePcxSyntheticPathBytes - 1] = '\0';
    g_ImagePcxCache[slot].pcx.assign(pcx, pcx + size);
    g_ImagePcxCache[slot].lastUse = ++g_ImagePcxCacheClock;
    g_ImagePcxCacheBytes += size;
    // 预算控制：从最久未用开始淘汰（但至少保留刚插入的这条）。
    while (g_ImagePcxCacheBytes > kImagePcxCacheBudgetBytes) {
        std::size_t victim = kImagePcxCacheEntries;
        for (std::size_t i = 0; i < kImagePcxCacheEntries; ++i) {
            if (g_ImagePcxCache[i].pcx.empty() || &g_ImagePcxCache[i] == &g_ImagePcxCache[slot]) {
                continue;
            }
            if (victim == kImagePcxCacheEntries ||
                g_ImagePcxCache[i].lastUse < g_ImagePcxCache[victim].lastUse) {
                victim = i;
            }
        }
        if (victim == kImagePcxCacheEntries) {
            break;
        }
        g_ImagePcxCacheBytes -= g_ImagePcxCache[victim].pcx.size();
        g_ImagePcxCache[victim].pcx.clear();
        g_ImagePcxCache[victim].path[0] = '\0';
        g_ImagePcxCache[victim].lastUse = 0;
    }
}

// 设备侧 zlib 包装（定义见本文件后部）；回调引用它，需前向声明。
int ImagePcxInflateOne(uint8_t* dest, std::size_t dest_len, const uint8_t* src,
                       std::size_t src_len) noexcept;

// 把 `.png` 文件读进内存（照 `GameFileReader::ReadScript` 的既有流程：
// 构造 → 打开 → 取长 → 读 → 关 → 析构）。成功返回 true 并填 `out`；
// 任何一步失败返回 false（文件不存在 / 空 / 超 16 MiB / 读不满）。仅本 TU 使用。
namespace {
bool ReadPngFileForBridge(const char* pngPath, std::vector<u8>* out) {
    if (g_fileBindings == nullptr) {
        return false;
    }
    const auto& b = *g_fileBindings;
    if (b.construct == nullptr || b.openRead == nullptr || b.getLength == nullptr ||
        b.read == nullptr || b.close == nullptr || b.destroy == nullptr) {
        return false;
    }
    alignas(16) std::array<u8, kGameFileObjectSize> fileStorage{};
    b.construct(fileStorage.data());
    if (!b.openRead(fileStorage.data(), pngPath)) {
        b.destroy(fileStorage.data());
        return false;
    }
    const int length = b.getLength(fileStorage.data());
    constexpr int kPngCap = 16 * 1024 * 1024;  // 贴图 Mod 单文件上限 16 MiB
    if (length <= 0 || length > kPngCap) {
        b.close(fileStorage.data());
        b.destroy(fileStorage.data());
        return false;
    }
    out->resize(static_cast<std::size_t>(length));
    const int bytesRead = b.read(fileStorage.data(), out->data(), 1, length);
    b.close(fileStorage.data());
    b.destroy(fileStorage.data());
    return bytesRead == length;
}
}  // namespace

// 贴图桥（2026-09-21）：引擎加载 `.pcx` 的最后一站。
//
// 入口中继契约：本回调**以 `ImagePcx::Load` 的身份**运行（`br` 尾调用，x0..x7 原样传入，
// `ret` 直接回到游戏调用方），所以**返回值也由本回调负责**，且**是否跑原函数由本回调决定**
// （直接调 `Original<>` 才是跑原函数）。顺序：
//   1. 先让原函数跑「`.pcx` 在」这条路径 —— 成功就直接返回，零开销、零副作用。
//   2. 失败时把路径末尾 `.pcx` 换成 `.png`，用 `g_DefaultManifestBindings` 探测/读取 Mod 资源。
//   3. 用注入的 `ImagePcxInflateOne`（包真实 zlib）把 PNG 转成 PCX 字节，喂内存版 `Load`。
//   4. 任一环节缺失/失败都退回 `false`（=「这次没加载到」），**绝不崩、绝不读卡**。
// ★ 返回值必须原样搬运：`KAGE::Graphics::ImagePcx::Load(const char*)` 返回 bool（x0 低 8 位），
//   声明成 void 会让引擎拿到垃圾值、把「加载失败」误判成成功或反之。
extern "C" bool EntryRelayImagePcxLoadCallback(void* self, const char* path) {
    using LoadFn = bool (*)(void*, const char*);
    const auto original = isaac::runtime::Original<LoadFn>(isaac::runtime::HookId::ImagePcxLoad);
    // 诊断：记下最近一次请求路径（不分来源；"进入兜底"的那条另记，见 lastFallbackPath）。
    if (path != nullptr) {
        std::strncpy(g_imagePcxDiag.lastRequestPath, path,
                     sizeof(g_imagePcxDiag.lastRequestPath) - 1);
        g_imagePcxDiag.lastRequestPath[sizeof(g_imagePcxDiag.lastRequestPath) - 1] = '\0';
    }
    // 原函数这条路不碰卡（只查内存里已挂的贴图），先试它。
    if (original(self, path)) {
        return true;
    }
    // 兜底前置：路径必须是以 `.pcx` 结尾的字符串，且引擎入口/zlib 都已发布成功。
    if (path == nullptr || g_engineBindings == nullptr || g_fileBindings == nullptr ||
        g_engineBindings->inMemoryLoad == nullptr ||
        g_engineBindings->inflateInit2 == nullptr || g_engineBindings->inflate == nullptr ||
        g_engineBindings->inflateEnd == nullptr ||
        g_engineBindings->contentManager == nullptr ||
        g_engineBindings->operatorDeleteArray == nullptr) {
        return false;
    }
    const std::size_t pathLen = std::strlen(path);
    if (pathLen < 5 || std::memcmp(path + pathLen - 4, ".pcx", 4) != 0) {
        return false;  // 请求的不是 .pcx（理论上不该发生）
    }
    ++g_imagePcxDiag.fallbackAttempts;
    if (path != nullptr) {
        std::strncpy(g_imagePcxDiag.lastFallbackPath, path,
                     sizeof(g_imagePcxDiag.lastFallbackPath) - 1);
        g_imagePcxDiag.lastFallbackPath[sizeof(g_imagePcxDiag.lastFallbackPath) - 1] = '\0';
    }
    // 构造同名 .png 路径（替换扩展名，容量留 1 字节余量）。
    constexpr std::size_t kPathBuf = 4096;
    char pngPath[kPathBuf];
    if (pathLen + 1 > kPathBuf) return false;
    std::memcpy(pngPath, path, pathLen);
    std::memcpy(pngPath + pathLen - 4, ".png", 4);
    pngPath[pathLen] = '\0';

    // ★ 读哪个路径：**只能用合成时记下来的那条**（它是当时解析成功过的绝对路径）。
    // 绝不能用"把收到的路径末尾换成 .png"自己拼——引擎传下来的路径**已经被它自己的
    // `CreateCleanPath` 清洗过**，拼出来的字符串和真实文件对不上 ⇒ `File::OpenRead`
    // 打开失败 ⇒ 引擎 Abort（真机 01789981130 / 01789981405 两次都栽在这条路上）。
    // 匹配按**文件名**（只比最后一节）：清洗可能改变目录部分，文件名不变。
    const char* base = ImagePcxBasename(path);
    const char* pngMounted = nullptr;
    {
        const std::size_t ringCount = g_ImagePcxSyntheticRingCount.load();
        const std::size_t scan = ringCount < kImagePcxSyntheticRingSize
                                     ? ringCount : kImagePcxSyntheticRingSize;
        for (std::size_t i = 0; i < scan; ++i) {
            if (std::strcmp(g_ImagePcxSyntheticNames[i], base) == 0) {
                pngMounted = g_ImagePcxSyntheticPngPaths[i];
                break;
            }
        }
    }
    if (pngMounted == nullptr) {
        // 不是我们合成的请求（或记录已过期）：**什么都不做**，绝不"盲开"一条来源不明的路径。
        ++g_imagePcxDiag.ringMiss;
        return false;
    }
    // 缓存优先：命中就省掉"读文件 + inflate + 转码"三步（真机实测同一路径会被问很多次）。
    if (const std::vector<u8>* cached = ImagePcxCacheLookup(pngMounted)) {
        ++g_imagePcxDiag.cacheHits;
        const bool loadedCached = g_engineBindings->inMemoryLoad(
            self, cached->data(), static_cast<std::uint32_t>(cached->size()), path);
        if (loadedCached) {
            ++g_imagePcxDiag.fedOk;
        }
        return loadedCached;
    }
    // 用已发布的文件读取绑定把 .png 读进内存（与 `GameFileReader::ReadScript` 同款流程）。
    std::vector<u8> pngBuf;
    if (!ReadPngFileForBridge(pngMounted, &pngBuf)) {
        return false;  // .png 读取失败：退回「没加载到」
    }
    ++g_imagePcxDiag.readOk;

    // 内存转码 + 喂内存版 Load。
    uint8_t* pcx = nullptr;
    std::size_t pcxSize = 0;
    ++g_imagePcxDiag.cacheConversions;
    const bool ok = isaac::runtime::content::PngToPcx(
        pngBuf.data(), pngBuf.size(), &ImagePcxInflateOne, &pcx, &pcxSize);
    if (!ok || pcx == nullptr) {
        ++g_imagePcxDiag.convertFailures;
        return false;
    }
    ImagePcxCacheInsert(pngMounted, pcx, pcxSize);  // 记下来，下次同一条路径直接命中
    const bool loaded =
        g_engineBindings->inMemoryLoad(self, pcx, static_cast<std::uint32_t>(pcxSize), path);
    delete[] pcx;
    if (loaded) {
        ++g_imagePcxDiag.fedOk;
    }
    return loaded;
}

// 设备侧 zlib 包装：把三段 `z_stream` 流程（init2 + inflate(Z_FINISH) + end）包成
// `PngToPcx` 要的「一次性解压完整 zlib 流、写满 dest_len 才成功」形状。
//
// 标准 64 位 `z_stream` 布局（总长 112 = 0x70 字节），与 `inflateInit2_` 校验的
// `stream_size == 0x70`、内核 `version[0] == '1'` 一致：`version` 传 "1.1.4"。
// PNG 的 IDAT 是**带 zlib 头**的流，故 `windowBits = 15`（MAX_WBITS），不是 -15（raw deflate）。
struct ImagePcxZStream {
    void* next_in;             // +0
    std::uint32_t avail_in;    // +8
    std::uint32_t _pad0;       // +12（对齐 total_in 到 8）
    std::uint64_t total_in;    // +16
    void* next_out;            // +24
    std::uint32_t avail_out;   // +32
    std::uint32_t _pad1;       // +36
    std::uint64_t total_out;   // +40
    char* msg;                 // +48
    void* state;               // +56
    void* zalloc;              // +64
    void* zfree;               // +72
    void* opaque;              // +80
    std::int32_t data_type;    // +88
    std::uint32_t _pad2;       // +92
    std::uint64_t adler;       // +96
    std::uint64_t reserved;    // +104
};
static_assert(sizeof(ImagePcxZStream) == 112, "z_stream 必须是 112 字节");

int ImagePcxInflateOne(uint8_t* dest, std::size_t dest_len, const uint8_t* src,
                       std::size_t src_len) noexcept {
    if (g_engineBindings == nullptr) {
        return -1;
    }
    const auto& b = *g_engineBindings;
    if (b.inflateInit2 == nullptr || b.inflate == nullptr || b.inflateEnd == nullptr) {
        return -1;
    }
    ImagePcxZStream s{};
    s.next_in = const_cast<uint8_t*>(src);
    s.avail_in = static_cast<std::uint32_t>(src_len);
    s.next_out = dest;
    s.avail_out = static_cast<std::uint32_t>(dest_len);
    if (b.inflateInit2(&s, 15, "1.1.4", 112) != 0) {
        return -1;
    }
    const int r = b.inflate(&s, 4 /*Z_FINISH*/);
    b.inflateEnd(&s);
    // 成功 = inflate 到达流尾且输出缓冲被写满（与宿主侧 `uncompress` 的语义对齐）。
    if (r == 1 /*Z_STREAM_END*/ && s.avail_out == 0) {
        return 0;
    }
    return -1;
}

// 贴图桥 v2/v3 的挂点（`ImageManager::LoadImage` 文件版）——**已改为纯透传**。
//
// ★★ 2026-09-21 16:22 真机卡死教训：**不要在这个层次回调贴图管理器自己**。
// 该重载的内存版（`0x4d2654`）在"往贴图表插入"时要拿 `ImageManager+0x8` 的互斥锁，而我们的
// 回调本身就是从管理器自己的调用栈里进来的 ⇒ **自己锁死自己**（按一下键就卡死）。
// v4 起把字节的交付改到**文件层**（见 `EntryRelayContentGetMountedFilePathCallback` 与
// `EntryRelayImagePcxLoadCallback`），这个挂点只保留计数与透传，绝不再调引擎的管理器接口。
#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wreturn-type-c-linkage"
#endif
extern "C" isaac::runtime::relay::SmartPointerShim EntryRelayImageManagerLoadFileCallback(
    void* self, const char* path, void* descriptor, int flag) {
    namespace relay = isaac::runtime::relay;
    using LoadFileFn = relay::SmartPointerShim (*)(void*, const char*, void*, int);
    const auto original =
        isaac::runtime::Original<LoadFileFn>(isaac::runtime::HookId::ImageManagerLoadFile);
    ++g_imagePcxDiag.hookCalls;
    if (path != nullptr) {
        std::strncpy(g_imagePcxDiag.lastRequestPath, path,
                     sizeof(g_imagePcxDiag.lastRequestPath) - 1);
        g_imagePcxDiag.lastRequestPath[sizeof(g_imagePcxDiag.lastRequestPath) - 1] = '\0';
    }
    const relay::SmartPointerShim result = original(self, path, descriptor, flag);
    if (result.pointer != nullptr) {
        ++g_imagePcxDiag.originalOk;
    }
    return result;
}
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

// 路径解析的原函数（入口中继的回退入口）：解析 `.png` 时用它 —— **不经过**本钩子的补位逻辑，
// 因此天然不会递归；也不需要"逐字节校验绑定"（挂点安装时已经核对过原版序言）。
using GetMountedFn = char* (*)(void*, const char*);
GetMountedFn OriginalGetMountedFilePath() noexcept {
    return isaac::runtime::Original<GetMountedFn>(
        isaac::runtime::HookId::ContentGetMountedFilePath);
}

// 贴图桥 v4（2026-09-21 晚）：`IContentManager::GetMountedFilePath` —— 在"文件层"补位。
//
// 引擎的文件版贴图加载在**创建贴图对象之前**就用它判断"文件在不在任何挂载点"；`.pcx` 不在
// 就直接返回空（这正是一路失败的根因）。这里在"`.pcx` 不在、但同名 `.png` 在"时，返回一条
// **合成的 `.pcx` 挂载路径**（=`.png` 的挂载路径换扩展名）：
//   * 引擎随后按"扩展名 pcx"建 `ImagePcx`、调它自己的文件版 `Load` ⇒ 我们已挂在
//     `ImagePcx::Load` 上的回调**这时才第一次能被调到**（v1 当年等不到的就是这个前提）；
//   * 那条回调里我们读 `.png`、转 PCX、调**对象自己的**内存版 `Load`（纯对象级、无锁），
//     引擎再自己完成缓存与登记 —— **全程不碰管理器，无重入、无自锁**。
// 合成路径必须用**游戏自己的 `operator new[]`** 分配：调用方会用 `_ZdaPv` 释放它。
// ★ 2026-09-21：`.pcx` 请求的**优先级**要跟 PC 一致 —— PC 模组的贴图是 PNG，
// 而它要覆盖的目标在本体（Switch 版）是**已存在的 `.pcx`**。
//
// 改前的行为：`original(path)` 只要答得出来（哪怕答的是**本体**那份 `.pcx`）就直接交回
// ⇒ 桥永远等不到 ⇒ 模组的 PNG **被静默忽略**（用户实例：`visible tinted rocks` 的
// 23 张 `gfx/grid/rocks_*.png`，而本体 `resources/gfx/grid/` 下就有 13 张同名 `.pcx`）。
//
// 改后的规则（三步）：
//   1. 先按原样问引擎（这一步同时给出"模组自带 `.pcx`"的情形）；
//   2. 若结果**是模组自己的文件** ⇒ 原样交回（**不抢**模组自己的 `.pcx`）；
//   3. 否则（没找到，或找到的是**本体**那份）⇒ 再问一次同名 `.png`：
//      问到 ⇒ 合成 `.pcx` 路径（与"模组自带新贴图"那条路完全一样，交给 `ImagePcx::Load` 转码）；
//      问不到 ⇒ 保持原结果（本体那份照旧用，或维持"文件不存在"）。
//
// 为什么"问得到 `.png`"就等于"这是模组的文件"：Switch 版本体资源**一个 `.png` 都没有**
// （本机整棵本体树 `find -name '*.png'` = 0）⇒ 只有模组会带 PNG。
//
// 代价：每次 `.pcx` 查询多一次挂载搜索（只在"结果不是模组文件"时才多）。诊断里有
// `pngOverrideWins` 计数，真机读数可以看它到底发生了多少次。
// （判据 `IsModMountedPath` 放在头文件里，宿主门禁 `test_png_override_priority.py` 直接测它。）
extern "C" char* EntryRelayContentGetMountedFilePathCallback(void* self, const char* path) {
    const auto original = OriginalGetMountedFilePath();
    char* mounted = original(self, path);
    if (path == nullptr) {
        return mounted;
    }
    const std::size_t pathLen = std::strlen(path);
    if (pathLen < 5 || std::memcmp(path + pathLen - 4, ".pcx", 4) != 0) {
        return mounted;  // 只补 `.pcx` 这一类
    }
    if (isaac::runtime::bridge::IsModMountedPath(mounted)) {
        return mounted;  // 模组自带 `.pcx`：用它的，不做额外探测
    }
    if (g_engineBindings == nullptr ||
        g_engineBindings->operatorNewArray == nullptr ||
        g_engineBindings->operatorDeleteArray == nullptr) {
        return mounted;  // 绑定不全：不动引擎的答案（至少把已有结果交回）
    }
    char pngPath[4096];
    if (pathLen + 1 > sizeof(pngPath)) return mounted;
    std::memcpy(pngPath, path, pathLen);
    std::memcpy(pngPath + pathLen - 4, ".png", 4);
    pngPath[pathLen] = '\0';
    // 直接调**原函数**问 `.png`（不经过本钩子的补位逻辑，天然不会递归）。
    char* pngMounted = original(self, pngPath);
    if (pngMounted == nullptr) {
        return mounted;  // `.png` 也没有：照旧（本体那份 `.pcx`，或"文件不存在"）
    }
    const std::size_t mountedLen = std::strlen(pngMounted);
    if (mountedLen < 5) {
        g_engineBindings->operatorDeleteArray(pngMounted);
        return mounted;
    }
    char* synthetic = static_cast<char*>(g_engineBindings->operatorNewArray(mountedLen + 1));
    if (synthetic == nullptr) {
        g_engineBindings->operatorDeleteArray(pngMounted);
        return mounted;
    }
    std::memcpy(synthetic, pngMounted, mountedLen + 1);
    std::memcpy(synthetic + mountedLen - 4, ".pcx", 4);
    {
        const std::size_t slot =
            (++g_ImagePcxSyntheticRingCount - 1) % kImagePcxSyntheticRingSize;
        const char* name = ImagePcxBasename(synthetic);
        std::strncpy(g_ImagePcxSyntheticNames[slot], name, kImagePcxSyntheticNameBytes - 1);
        g_ImagePcxSyntheticNames[slot][kImagePcxSyntheticNameBytes - 1] = '\0';
        std::strncpy(g_ImagePcxSyntheticPngPaths[slot], pngMounted,
                     kImagePcxSyntheticPathBytes - 1);
        g_ImagePcxSyntheticPngPaths[slot][kImagePcxSyntheticPathBytes - 1] = '\0';
    }
    g_engineBindings->operatorDeleteArray(pngMounted);  // 还掉 `.png` 那份（已抄进环形）
    ++g_imagePcxDiag.syntheticPaths;
    if (mounted != nullptr) {
        // 走的是"模组 PNG 顶掉本体 `.pcx`"这条路（`mounted` 是本体那份，被我们让位了）。
        ++g_imagePcxDiag.pngOverrideWins;
    }
    return synthetic;
}

} // namespace

namespace isaac::runtime::bridge {

void Attach(const GameFileReader::Bindings* fileBindings,
            const GameFileReader::ImagePcxBindings* engineBindings) noexcept {
    g_fileBindings = fileBindings;
    g_engineBindings = engineBindings;
}

} // namespace isaac::runtime::bridge
