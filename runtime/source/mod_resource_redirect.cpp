#include "mod_resource_redirect.hpp"

#include <array>
#include <atomic>
#include <cstring>

// 实现说明与取证见头文件；本文件只放"规则 + 记账"。
//
// 三条不变量（改这个文件之前先读一遍）：
//   ① **不分配自己的内存**：命中时把引擎原函数解析出来的那条路径**原样交回**
//      （它就是"模组目录被挂载时"会得到的那条串），所有权直接转移给调用方。
//      我们既不 `new` 也不 `free` 引擎的路径 —— 没有堆混用的余地。
//   ② **只调原函数**：探测走的是中继给进来的 `probe`（贴图桥的 `OriginalGetMountedFilePath()`），
//      它绕过钩子 ⇒ 不可能递归。
//   ③ **失败即放手**：清单未发布 / 参数不全 / 拼不下 ⇒ 一律返回 `nullptr`，
//      调用方照旧问引擎 —— 与"没有模组"逐字同义。
// 2026-10-14更正①：完整路径不符的hash碰撞回答由调用方提供的引擎release归还；
// 正常命中仍不复制/不释放。旧“不free”的说明不涵盖这类新证实的假命中。

namespace isaac::runtime::bridge {

ModResourceRedirectState g_ModResourceRedirectState{};

namespace {

constexpr char kApplicationPrefix[] = "rom:/";
constexpr char kModsRootPrefix[] = "isaac_mods/";
// PC 的两个候选后缀，顺序即优先级（`0x87066F` 的 `"-dlc3/"` 在前）。
constexpr const char* kCandidateSuffixes[] = {"resources-dlc3/", "resources/"};
constexpr std::size_t kCandidateSuffixCount =
    sizeof(kCandidateSuffixes) / sizeof(kCandidateSuffixes[0]);
// 根（≤287）+ `/` + 后缀（16）+ 资源名（≤191）+ `\0`。
constexpr std::size_t kCandidateCapacity = 512;

std::array<char, kModResourceRedirectRootCapacity> g_ModRoots[kModResourceRedirectCapacity]{};
std::size_t g_ModRootCount = 0;

void CopyDiagString(char* destination, std::size_t capacity, const char* source) noexcept {
    if (destination == nullptr || capacity == 0) {
        return;
    }
    if (source == nullptr) {
        destination[0] = '\0';
        return;
    }
    std::size_t length = std::strlen(source);
    if (length >= capacity) {
        length = capacity - 1;
    }
    std::memcpy(destination, source, length);
    destination[length] = '\0';
}

// 规范化：去掉 `rom:/` 前缀与结尾的 `/`（与 `engine_content_mount_adapter.cpp` 的
// `RelativeToApplicationRoot` 同一口径 —— 引擎的 `ContentMountPointPath` 会自己拼应用根，
// 而我们的候选串要交给引擎的解析器，同样必须是**应用根相对**形态）。
std::size_t NormalizeRoot(const char* modRoot, char* out, std::size_t capacity) noexcept {
    if (modRoot == nullptr || out == nullptr || capacity == 0) {
        return 0;
    }
    const char* begin = modRoot;
    if (std::strncmp(begin, kApplicationPrefix, sizeof(kApplicationPrefix) - 1) == 0) {
        begin += sizeof(kApplicationPrefix) - 1;
    }
    std::size_t length = std::strlen(begin);
    while (length > 0 && begin[length - 1] == '/') {
        --length;
    }
    if (length == 0 || length + 1 > capacity) {
        return 0;
    }
    std::memcpy(out, begin, length);
    out[length] = '\0';
    return length;
}

// 早退判定：已经是"解析过的形态"的资源名不可能再是模组资源名（见头文件"已知偏离 ③"）。
bool LooksAlreadyResolved(const char* path) noexcept {
    return std::strncmp(path, kApplicationPrefix, sizeof(kApplicationPrefix) - 1) == 0 ||
           std::strncmp(path, kModsRootPrefix, sizeof(kModsRootPrefix) - 1) == 0;
}

// 只核完整文件名；与原生CreateCleanPath/FileManager一致折叠ASCII大小写及斜杠。
// 模组候选是应用根相对路径，解析结果应为rom:/加同一候选。
unsigned char CanonicalPathByte(unsigned char value) noexcept {
    if (value == '\\') return '/';
    if (value >= 'A' && value <= 'Z') return value + ('a' - 'A');
    return value;
}

bool MatchesCandidate(const char* resolved, const char* candidate) noexcept {
    for (std::size_t index = 0; index < sizeof(kApplicationPrefix) - 1; ++index) {
        if (CanonicalPathByte(static_cast<unsigned char>(*resolved)) !=
            static_cast<unsigned char>(kApplicationPrefix[index])) {
            return false;
        }
        ++resolved;
    }
    for (;;) {
        const unsigned char actual = CanonicalPathByte(static_cast<unsigned char>(*resolved++));
        const unsigned char expected = CanonicalPathByte(static_cast<unsigned char>(*candidate++));
        if (actual != expected) return false;
        if (actual == 0) return true;
    }
}

}  // namespace

bool PublishModResourceRedirectList(const char* const* modRoots, std::size_t count) noexcept {
    g_ModRootCount = 0;
    if (modRoots != nullptr) {
        for (std::size_t index = 0; index < count && index < kModResourceRedirectCapacity;
             ++index) {
            if (NormalizeRoot(modRoots[index], g_ModRoots[g_ModRootCount].data(),
                              g_ModRoots[g_ModRootCount].size()) == 0) {
                continue;  // 空根 / 拼不下：跳过这一个，不污染后面的顺序
            }
            ++g_ModRootCount;
        }
    }
    // ★ 发布屏障（2026-10-05，批次 378）：发布点跑在**游戏线程**的 `Game::Init` 中继里，
    //   而读取点在引擎的文件入口上 —— 多数也在游戏线程，但引擎内部有自己的线程（音频/视频解码），
    //   而 **AArch64 是弱内存序**：没有这一对屏障，另一个线程可能看见新的 `g_ModRootCount`
    //   而看不见 `g_ModRoots` 里的字节（于是按越界的空根去拼路径）。
    //   顺序固定为"先填数组、再放计数"；读取侧在读到计数后加 acquire 屏障（见下面那个函数）。
    std::atomic_thread_fence(std::memory_order_release);
    g_ModResourceRedirectState.published = 1;
    g_ModResourceRedirectState.modCount = static_cast<std::uint32_t>(g_ModRootCount);
    ++g_ModResourceRedirectState.publishCount;
    g_ModResourceRedirectState.lastHitMod = kModResourceRedirectNoMod;
    return g_ModRootCount > 0;
}

void ClearModResourceRedirectList() noexcept {
    g_ModRootCount = 0;
    g_ModResourceRedirectState.published = 0;
    g_ModResourceRedirectState.modCount = 0;
}

bool ModResourceRedirectListPublished() noexcept {
    return g_ModResourceRedirectState.published != 0;
}

char* TryRedirectModResource(const char* requestedPath, void* contentManager,
                             ProbeMountedFilePathFn probe,
                             ReleaseMountedFilePathFn release) noexcept {
    ModResourceRedirectState& state = g_ModResourceRedirectState;
    ++state.calls;
    if (requestedPath == nullptr || requestedPath[0] == '\0' || probe == nullptr ||
        release == nullptr) {
        return nullptr;
    }
    // ★ 与发布侧那一句配对（见 `PublishModResourceRedirectList`）：先读计数，
    //   拿到非零之后再 acquire —— 保证后面读到的 `g_ModRoots` 一定是填好的字节。
    const std::size_t modCount = g_ModRootCount;
    std::atomic_thread_fence(std::memory_order_acquire);
    if (modCount == 0) {
        return nullptr;
    }
    CopyDiagString(state.lastQuery, sizeof(state.lastQuery), requestedPath);
    state.lastAnswer[0] = '\0';
    if (LooksAlreadyResolved(requestedPath)) {
        ++state.skippedResolved;
        return nullptr;
    }
    const std::size_t nameLength = std::strlen(requestedPath);
    if (nameLength >= kModResourceRedirectQueryCapacity) {
        ++state.skippedTooLong;
        return nullptr;
    }

    char candidate[kCandidateCapacity];
    // 顺序 = PC 的两层：外层"模组清单顺序"，内层"`resources-dlc3/` 再看 `resources/`"。
    for (std::size_t mod = 0; mod < modCount; ++mod) {
        const char* root = g_ModRoots[mod].data();
        const std::size_t rootLength = std::strlen(root);
        for (std::size_t suffixIndex = 0; suffixIndex < kCandidateSuffixCount; ++suffixIndex) {
            const char* suffix = kCandidateSuffixes[suffixIndex];
            const std::size_t suffixLength = std::strlen(suffix);
            if (rootLength + 1 + suffixLength + nameLength + 1 > sizeof(candidate)) {
                continue;
            }
            std::memcpy(candidate, root, rootLength);
            candidate[rootLength] = '/';
            std::memcpy(candidate + rootLength + 1, suffix, suffixLength);
            std::memcpy(candidate + rootLength + 1 + suffixLength, requestedPath, nameLength);
            candidate[rootLength + 1 + suffixLength + nameLength] = '\0';

            char* resolved = probe(contentManager, candidate);
            if (resolved == nullptr) {
                continue;  // 这个模组没有这个文件 ⇒ 问下一个（PC 同：`0x8705B2` 的循环）
            }
            if (!MatchesCandidate(resolved, candidate)) {
                // 真实碰撞：goodtripfixed的怀表候选与原版左手hash同为0x2cdc96e3。
                // 非空≠存在；归还原生分配的错回答，再按PC顺序搜索真实文件。
                release(resolved);
                continue;
            }
            ++state.hits;
            if (suffixIndex == 0) {
                ++state.dlc3Hits;
            } else {
                ++state.plainHits;
            }
            state.lastHitMod = static_cast<std::uint32_t>(mod);
            CopyDiagString(state.lastAnswer, sizeof(state.lastAnswer), resolved);
            return resolved;  // 引擎分配、调用方归还 —— 所有权直接转移
        }
    }
    return nullptr;
}

}  // namespace isaac::runtime::bridge
