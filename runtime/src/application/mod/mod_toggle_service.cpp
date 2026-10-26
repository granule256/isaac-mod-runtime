#include "application/mod/mod_toggle_service.hpp"

#include <array>
#include <cstring>
#include <memory>
#include <new>

namespace isaac::runtime {

// ★★ 批次 427：两个读数（见头文件里的说明）。写在 `namespace {` **之外** ⇒ 外部链接 ⇒
//    读数工具能按符号名读（本项目在"探针写进匿名命名空间"上栽过 5 次）。
std::atomic<std::uint32_t> g_ModTogglePrunedEntries{0};
std::atomic<std::uint32_t> g_ModToggleCapacityRejections{0};

namespace {

// 用户手工标记文件的名字（放在模组目录里）。卡上的覆盖层是只读的，所以这条路径只能**读**：
// 它给用户一个"不改存档也能证明性地禁用某个模组"的保底手段。
constexpr char kUserDisableMarker[] = "/disable.it";

constexpr std::size_t kMarkerPathCapacity = kModRootPathCapacity + sizeof(kUserDisableMarker);

// 模组根的**目录名**（`rom:/isaac_mods/mods/SomeMod` ⇒ `SomeMod`）。
// 状态文件里存的、以及发现服务产出的，都是这个短名字 —— 这样两种加载路径（清单/自动发现）
// 用同一把钥匙，用户改清单也不会让开关失效。
std::string_view LeafName(std::string_view path) noexcept {
    if (path.empty()) {
        return {};
    }
    while (!path.empty() && path.back() == '/') {
        path.remove_suffix(1);
    }
    const std::size_t slash = path.rfind('/');
    return slash == std::string_view::npos ? path : path.substr(slash + 1);
}

} // namespace

Status ModToggleService::Load() noexcept {
    std::unique_ptr<char[]> buffer(new (std::nothrow) char[kModToggleStateMaximumBytes]);
    if (!buffer) return Status{StatusCode::IoFailure};
    std::size_t size = 0;
    const Status read = files_.Read(kModToggleStateFileName, buffer.get(), kModToggleStateMaximumBytes, &size);
    if (read.code() == StatusCode::NotFound) {
        state_.disabled.fill({}); state_.disabledCount = 0; // 第一次运行：全都开着
        ++revision_;
        return Status::Ok();
    }
    if (!read.ok()) {
        return read;
    }
    if (size > kModToggleStateMaximumBytes) return Status{StatusCode::Corrupted};
    ++revision_; // Parse失败也可能清理部分状态，读面必须重新计算。
    return state_.Parse(std::string_view(buffer.get(), size));
}

Status ModToggleService::Save() noexcept {
    std::unique_ptr<char[]> buffer(new (std::nothrow) char[kModToggleStateMaximumBytes]);
    if (!buffer) return Status{StatusCode::IoFailure};
    const std::size_t size = state_.Serialize(buffer.get(), kModToggleStateMaximumBytes);
    if (size == 0) {
        return Status{StatusCode::CapacityExceeded};
    }
    return files_.Write(kModToggleStateFileName, std::string_view(buffer.get(), size));
}

bool ModToggleService::HasUserDisableMarker(const char* modRoot) noexcept {
    if (modRoot == nullptr || modRoot[0] == '\0') {
        return false;
    }
    char path[kMarkerPathCapacity] = {};
    const std::size_t rootLength = std::strlen(modRoot);
    if (rootLength + sizeof(kUserDisableMarker) > sizeof(path)) {
        return false;
    }
    std::memcpy(path, modRoot, rootLength);
    std::memcpy(path + rootLength, kUserDisableMarker, sizeof(kUserDisableMarker));
    bool exists = false;
    if (!files_.Exists(path, &exists).ok()) {
        return false;   // 查不了 ⇒ 不当成"被禁用"（宁可多加载，也不要静默少加载）
    }
    return exists;
}

std::size_t ModToggleService::ApplyToBatch(ResolvedManifestModBatch* batch) noexcept {
    if (batch == nullptr) {
        return 0;
    }
    // ★★ 批次 427：**先把名单里"这次扫描没看到的目录"清掉**（模组被删/改名留下的死条目）。
    //   ★ 必须在过滤**之前**做：否则"确实存在、只是被关掉"的那些也会被当死条目丢掉。
    //   为什么非有不可：427 之前**没有任何清理逻辑** ⇒ 从卡上删一个模组就永久占掉一格，
    //   很快把名单吃满 ⇒ 用户看到的"后面那些模组怎么关都关不掉"。
    const std::size_t pruned = state_.PruneMissing([batch](std::string_view directory) noexcept {
        for (std::size_t index = 0; index < batch->count; ++index) {
            const ResolvedManifestMod& mod = batch->mods[index];
            const char* root = mod.modRoot == nullptr ? "" : mod.modRoot;
            if (LeafName(root) == directory) {
                return true;
            }
        }
        return false;
    });
    g_ModTogglePrunedEntries.fetch_add(static_cast<std::uint32_t>(pruned),
                                       std::memory_order_relaxed);
    if (pruned) ++revision_;
    std::size_t kept = 0;
    std::size_t removed = 0;
    for (std::size_t index = 0; index < batch->count; ++index) {
        const ResolvedManifestMod& source = batch->mods[index];
        const char* root = source.modRoot == nullptr ? "" : source.modRoot;
        const std::string_view directory = LeafName(root);
        const bool disabled = !directory.empty() && !IsEnabled(directory);
        if (disabled || HasUserDisableMarker(root)) {
            ++removed;
            continue;
        }
        if (kept != index) {
            batch->paths[kept] = batch->paths[index];
            ResolvedManifestMod moved = source;
            // 指针是**指进缓冲**的（`ResolvedManifestMod` 只存指针），搬动之后必须重新指向
            // 新位置，否则它们会指向已经作废的那一份（症状是"加载了错误的模组路径"）。
            moved.modRoot = batch->paths[kept].modRoot.data();
            moved.entryPath = source.hasEntry ? batch->paths[kept].entryPath.data() : "";
            moved.chunkName = source.hasEntry ? batch->paths[kept].chunkName.data() : "";
            batch->mods[kept] = moved;
        }
        ++kept;
    }
    batch->count = kept;
    return removed;
}

} // namespace isaac::runtime
