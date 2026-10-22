#include "application/mod/mod_discovery_service.hpp"

#include <cstring>

namespace isaac::runtime {
namespace {

// 与 `manifest_service.cpp` 同一套前缀（那边是拼清单里的 `directory`/`entry`，这边是拼
// "引擎列出来的目录名"）。两处必须一致，否则同一个模组走清单与走自动发现会落到不同路径上。
constexpr const char* kModsRootRelative = "isaac_mods/mods";
constexpr const char* kManifestRootPrefix = "rom:/isaac_mods/";
constexpr const char* kModRootPrefix = "rom:/isaac_mods/mods/";
constexpr const char* kChunkRootPrefix = "@rom:/isaac_mods/";
constexpr std::size_t kMaximumDiscoveredMods = ResolvedManifestModBatch::kCapacity;

bool JoinPath(char* output, std::size_t capacity, const char* prefix, const char* suffix) noexcept {
    if (output == nullptr || prefix == nullptr || suffix == nullptr) {
        return false;
    }
    const std::size_t prefixLength = std::strlen(prefix);
    const std::size_t suffixLength = std::strlen(suffix);
    if (prefixLength + suffixLength >= capacity) {
        return false;
    }
    std::memcpy(output, prefix, prefixLength);
    std::memcpy(output + prefixLength, suffix, suffixLength + 1);
    return true;
}

// 目录名必须是"一层目录"：空、`.`、`..`、带斜杠或反斜杠的一律拒绝。
// 引擎列出来的名字里出现这些说明我们对返回块的解读错了，**此时宁可少加载一个模组，
// 也不能拿一个可疑字符串去拼路径**（拼出来的路径会让引擎去读别的东西）。
bool IsUsableDirectoryName(const char* name) noexcept {
    if (name == nullptr || name[0] == '\0') {
        return false;
    }
    if (std::strcmp(name, ".") == 0 || std::strcmp(name, "..") == 0) {
        return false;
    }
    for (const char* cursor = name; *cursor != '\0'; ++cursor) {
        if (*cursor == '/' || *cursor == '\\') {
            return false;
        }
    }
    return true;
}

// 模组配置菜单**必须最先加载**（2026-10-01）。
//
// 为什么：GoodTrip / TheSpecialist 这类模组是在**加载那一刻**用全局 `ModConfigMenu` 判断
// "要不要注册自己的设置页"的（它们的 main.lua 里就是 `if ModConfigMenu then include(...) end`）。
// 菜单排在它们后面 ⇒ 那一刻全局还不存在 ⇒ **设置页永不注册**
// （真机现象：模组页里能看到这个模组、可它的设置页在菜单里怎么也找不到）。
//
// 清单时代这个顺序由清单写死（第一条就是菜单模组）；改用"扫目录"之后是**名字升序**，
// `mod_config_menu_cn` 会落到第 4 位（前面还有 `external item descriptions…` / `goodtripfixed` /
// `infinite-coins`）⇒ 必须在这里把它提回最前。
//
// 识别口径 = "去掉分隔符、转小写之后含 `configmenu`"（见下面的 `IsModConfigMenuDirectory`）：
// 中英文两份的目录名 `mod_config_menu_cn` 与 `isaac-mod-config-menu` 都命中；
// 不写死整名，免得换个语言/后缀就失效。
// 只看"去掉分隔符、转小写之后的名字里有没有 configmenu"。
// 这样 `mod_config_menu_cn`（中文版）与 `isaac-mod-config-menu`（英文版）都命中，
// 不必为每种写法的分隔符（下划线 / 连字符 / 驼峰）各列一条
// —— 第一版只写了下划线，被判据当场抓出英文版漏判（见 `test_multi_mod_manifest`）。
bool IsModConfigMenuDirectory(const char* name) noexcept {
    constexpr char kNeedle[] = "configmenu";
    std::size_t matched = 0;
    for (const char* cursor = name; *cursor != '\0'; ++cursor) {
        char lower = *cursor;
        if (lower >= 'A' && lower <= 'Z') {
            lower = static_cast<char>(lower - 'A' + 'a');
        }
        if (lower == '_' || lower == '-' || lower == ' ') {
            continue;   // 分隔符不参与比较
        }
        if (lower == kNeedle[matched]) {
            ++matched;
            if (kNeedle[matched] == '\0') {
                return true;
            }
        } else {
            matched = (lower == kNeedle[0]) ? 1U : 0U;
        }
    }
    return false;
}

std::size_t ModPriorityRank(const char* name) noexcept {
    if (name == nullptr) {
        return 1;
    }
    return IsModConfigMenuDirectory(name) ? 0 : 1;
}

// 排序键：**先比优先级，再比名字**（升序）。顺序必须确定：两个模组的回调派发顺序会影响游戏行为，
// 而"引擎给的顺序"没有保证。
bool RanksBefore(const ModDirectoryEntry& left, const ModDirectoryEntry& right) noexcept {
    const std::size_t leftRank = ModPriorityRank(left.name.data());
    const std::size_t rightRank = ModPriorityRank(right.name.data());
    if (leftRank != rightRank) {
        return leftRank < rightRank;
    }
    return std::strcmp(left.name.data(), right.name.data()) < 0;
}

// 按上面的排序键插入排序（模组数量是个位数，插入排序最简单且不引入算法依赖）。
void SortNames(ModDirectoryEntry* entries, std::size_t count) noexcept {
    for (std::size_t index = 1; index < count; ++index) {
        ModDirectoryEntry current = entries[index];
        std::size_t position = index;
        while (position > 0 && RanksBefore(current, entries[position - 1])) {
            entries[position] = entries[position - 1];
            --position;
        }
        entries[position] = current;
    }
}

// 把一个目录名填成批次里的一条（三条路径 + 指针视图）。`Discover` 与 `AppendUnlisted` 共用。
// `hasEntry` 一律为 true：真缺 `main.lua`（纯资源型模组）时由 `ModLoadService` 如实报
// `EntryAbsent` 并保留内容挂载点 —— 这正是 PC 上"只带 resources 的模组"的行为。
bool FillOneMod(ResolvedManifestModBatch* batch, std::size_t index, const char* name) noexcept {
    ModPathBuffers& buffers = batch->paths[index];
    if (!JoinPath(buffers.modRoot.data(), buffers.modRoot.size(), kModRootPrefix, name)) {
        return false;
    }
    char entryRelative[kModEntryCapacity]{};
    const std::size_t nameLength = std::strlen(name);
    if (nameLength + 9 >= sizeof(entryRelative)) {   // "mods/" + 名字 + "/main.lua"
        return false;
    }
    std::memcpy(entryRelative, "mods/", 5);
    std::memcpy(entryRelative + 5, name, nameLength);
    std::memcpy(entryRelative + 5 + nameLength, "/main.lua", 10);
    if (!JoinPath(buffers.entryPath.data(), buffers.entryPath.size(), kManifestRootPrefix,
                  entryRelative) ||
        !JoinPath(buffers.chunkName.data(), buffers.chunkName.size(), kChunkRootPrefix,
                  entryRelative)) {
        return false;
    }
    ResolvedManifestMod& resolved = batch->mods[index];
    resolved.entryPath = buffers.entryPath.data();
    resolved.modRoot = buffers.modRoot.data();
    resolved.chunkName = buffers.chunkName.data();
    resolved.manifestBytes = 0;      // 没有清单：这个字段只用于诊断
    resolved.hasEntry = true;
    return true;
}

// 批次里是否已经有这个目录（比对 `modRoot` 的最后一段）。
bool BatchHasDirectory(const ResolvedManifestModBatch& batch, const char* name) noexcept {
    for (std::size_t index = 0; index < batch.count; ++index) {
        const char* root = batch.mods[index].modRoot;
        if (root == nullptr) {
            continue;
        }
        const char* base = root;
        for (const char* cursor = root; *cursor != '\0'; ++cursor) {
            if (*cursor == '/' || *cursor == '\\') {
                base = cursor + 1;
            }
        }
        if (std::strcmp(base, name) == 0) {
            return true;
        }
    }
    return false;
}

// 清单里是否**显式关掉**了这个目录（`enabled = false`）。
bool BatchHasDisabledDirectory(const ResolvedManifestModBatch& batch, const char* name) noexcept {
    for (std::size_t index = 0; index < batch.disabledCount; ++index) {
        if (std::strcmp(batch.disabledDirectories[index].data(), name) == 0) {
            return true;
        }
    }
    return false;
}

} // namespace

Status ModDiscoveryService::Discover(ResolvedManifestModBatch* batch) const noexcept {
    if (batch == nullptr) {
        return Status{StatusCode::InvalidArgument};
    }
    *batch = ResolvedManifestModBatch{};

    ModDirectoryEntry names[kMaximumDiscoveredMods]{};
    std::size_t count = 0;
    const Status listed = directories_.ListSubdirectories(kModsRootRelative, names,
                                                         kMaximumDiscoveredMods, &count);
    if (!listed.ok()) {
        return listed;
    }
    if (count == 0) {
        return Status{StatusCode::NotFound};
    }
    if (count > kMaximumDiscoveredMods) {
        return Status{StatusCode::CapacityExceeded};
    }
    SortNames(names, count);

    for (std::size_t index = 0; index < count; ++index) {
        if (!IsUsableDirectoryName(names[index].name.data())) {
            // 一个可疑名字就整批拒绝：宁可让用户看到"没加载"，也不要拿可疑路径去调引擎。
            *batch = ResolvedManifestModBatch{};
            return Status{StatusCode::Corrupted};
        }
        if (!FillOneMod(batch, index, names[index].name.data())) {
            *batch = ResolvedManifestModBatch{};
            return Status{StatusCode::CapacityExceeded};
        }
    }
    batch->count = count;
    batch->manifestBytes = 0;
    return Status{StatusCode::Ok};
}

// 把"清单里没列出（或没关掉）的目录"追加到已解析的清单批次后面（2026-09-21）。
//
// 用户的要求是"拷进 `mods/` 就能用"，而清单一旦存在，原来的语义是"只听清单"。
// 这里做**合并**：清单里的先来（顺序、开关都由清单说了算），随后按名字升序追加扫到的其余目录。
// 被清单显式 `enabled = false` 的目录**不追加** —— 否则用户再也关不掉模组。
//
// 失败语义：目录列不出来 / 拼路径失败 / 装不下 ⇒ 返回错误，但**调用方按 best-effort 处理**
// （保留清单那一批照常加载，把错误记进诊断）——"多加载几个"这件事不该让整个加载失败。
Status ModDiscoveryService::AppendUnlisted(ResolvedManifestModBatch* batch) const noexcept {
    if (batch == nullptr) {
        return Status{StatusCode::InvalidArgument};
    }
    ModDirectoryEntry names[ResolvedManifestModBatch::kCapacity]{};
    std::size_t count = 0;
    const Status listed = directories_.ListSubdirectories(kModsRootRelative, names,
                                                         ResolvedManifestModBatch::kCapacity, &count);
    if (!listed.ok()) {
        return listed;
    }
    if (count == 0) {
        return Status{StatusCode::Ok};   // 没有可追加的，正常
    }
    SortNames(names, count);

    for (std::size_t index = 0; index < count; ++index) {
        const char* name = names[index].name.data();
        if (!IsUsableDirectoryName(name)) {
            continue;   // 清单已经生效：单个可疑名字**跳过**即可，不必整批失败
        }
        if (BatchHasDirectory(*batch, name) || BatchHasDisabledDirectory(*batch, name)) {
            continue;   // 清单里已列出（或已显式关掉）
        }
        if (batch->count >= ResolvedManifestModBatch::kCapacity) {
            return Status{StatusCode::CapacityExceeded};   // 装不下：显式失败（不截断）
        }
        if (!FillOneMod(batch, batch->count, name)) {
            return Status{StatusCode::CapacityExceeded};
        }
        ++batch->count;
    }
    return Status{StatusCode::Ok};
}

} // namespace isaac::runtime
