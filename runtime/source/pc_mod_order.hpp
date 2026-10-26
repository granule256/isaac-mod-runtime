#pragma once

#include "application/mod/manifest_service.hpp"
#include "mod_page_sources.hpp"

namespace isaac::runtime {

// PC 1.7.9b 0x870B00：显示名无符号字节序，区分大小写，不跳过标点。
inline int ComparePcModNames(const char* left, const char* right) noexcept {
    return std::strcmp(left, right);
}

// 先读全名称并排索引，再按置换环移动路径槽；不复制整批、不反复移动长路径。
// names/arena 由调用方持有，发布后必须保持到下一次扫描。失败不改 batch。
[[nodiscard]] inline bool CollectAndSortPcModNames(
    ResolvedManifestModBatch& batch, ModPageTextReader reader, void* context,
    ModPageEntrySource* names, char* arena, std::size_t arenaBytes,
    char* scratchPath, char* scratchText) noexcept {
    constexpr auto capacity = ResolvedManifestModBatch::kCapacity;
    if (batch.count > capacity) return false;
    if (batch.count == 0) return true;
    const char* directories[capacity]{};
    std::size_t order[capacity]{};
    for (std::size_t i = 0; i < batch.count; ++i) {
        const char* root = batch.mods[i].modRoot;
        if (root == nullptr) return false;
        const char* slash = std::strrchr(root, '/');
        directories[i] = slash == nullptr ? root : slash + 1;
        order[i] = i;
    }
    if (CollectModPageSources(names, capacity, directories, batch.count, nullptr, nullptr,
                             reader, context, arena, arenaBytes, scratchPath, scratchText)
        != batch.count) return false;
    // 同名只保持输入顺序，不凭目录、开关或 MCM 身份另加优先级。
    for (std::size_t i = 1; i < batch.count; ++i) {
        const auto item = order[i];
        auto j = i;
        while (j > 0 && ComparePcModNames(names[item].displayName,
                                         names[order[j - 1]].displayName) < 0) {
            order[j] = order[j - 1];
            --j;
        }
        order[j] = item;
    }
    bool visited[capacity]{};
    for (std::size_t start = 0; start < batch.count; ++start) {
        if (visited[start]) continue;
        const ModPathBuffers savedPath = batch.paths[start];
        const ResolvedManifestMod savedMod = batch.mods[start];
        const ModPageEntrySource savedName = names[start];
        auto destination = start;
        while (true) {
            visited[destination] = true;
            const auto source = order[destination];
            if (source == start) {
                batch.paths[destination] = savedPath;
                batch.mods[destination] = savedMod;
                names[destination] = savedName;
                break;
            }
            batch.paths[destination] = batch.paths[source];
            batch.mods[destination] = batch.mods[source];
            names[destination] = names[source];
            destination = source;
        }
    }
    for (std::size_t i = 0; i < batch.count; ++i) {
        auto& mod = batch.mods[i];
        mod.modRoot = batch.paths[i].modRoot.data();
        mod.entryPath = mod.hasEntry ? batch.paths[i].entryPath.data() : "";
        mod.chunkName = mod.hasEntry ? batch.paths[i].chunkName.data() : "";
    }
    return true;
}
} // namespace isaac::runtime
