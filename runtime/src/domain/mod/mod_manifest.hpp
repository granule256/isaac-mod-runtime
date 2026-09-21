#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace isaac::runtime {

// Capacities match the existing on-device manifest contract; changing them
// changes how much of a manifest can be addressed, so they are part of the
// domain model rather than a platform detail.
inline constexpr std::size_t kModDirectoryCapacity = 256;
inline constexpr std::size_t kModEntryCapacity = 1024;

enum class ManifestParseResult : std::uint32_t {
    Ok = 0,
    InvalidArgument,
    InvalidJson,
    InvalidSchema,
    InvalidMod,
    NoEnabledMod,
};

// One entry of the manifest "mods" array. `enabled` comes from the manifest,
// never from a default.
struct ModManifestEntry {
    std::array<char, kModDirectoryCapacity> directory{};
    std::array<char, kModEntryCapacity> entry{};
    bool enabled{false};
};

// The selected, enabled Mod as a pure value object: no file handle, no Lua
// state and no pointer to game memory.
struct ModManifest {
    std::array<char, kModDirectoryCapacity> directory{};
    std::array<char, kModEntryCapacity> entry{};

    [[nodiscard]] const char* Directory() const noexcept { return directory.data(); }
    [[nodiscard]] const char* Entry() const noexcept { return entry.data(); }

    // A PC Mod may ship resources only: the game mounts its `resources/` and never
    // runs a script for it, so `main.lua` -- and therefore the manifest `entry`
    // -- is optional. An absent entry is stored as the empty string, which is
    // also the "no script" flag every layer below reads.
    [[nodiscard]] bool HasEntry() const noexcept { return entry[0] != '\0'; }
};

// 同一次加载里最多几个 Mod（2026-09-16 多模组加载；2026-09-21 由 4 → 16 → 32）。
//
// 与旧解析器 `ModManifest::kMaximumSelectedMods` 必须一致（`hook_manager.cpp` 里有
// `static_assert` 兜住，理由同 `kRomfsModScriptMaximumLength`：两份常量各自演化过就埋过坑）。
//
// 为什么可以从 4 抬到 16：
//   * 这个"按值传递的解析结果"**不放在栈上** —— 运行时那条路径用的是静态 `batch`
//     与静态解析器（`hook_manager.cpp`），抬到 32 只多占约 80 KiB 静态存储；
//   * 挂载位（`ContentMountService::kMaxMods`）同步抬到 64：每个 Mod 最多占 4 个挂载点
//     （`resources`、`resources/gfx`、`content`、`content/gfx`）。
inline constexpr std::size_t kModManifestCapacity = 32;

struct ModManifestSet {
    std::array<ModManifestEntry, kModManifestCapacity> entries{};
    std::size_t count{0};
    // 清单里**显式 `enabled = false`** 的目录名（2026-09-21，为"拷贝目录即安装"服务）：
    // 自动发现合并时用它 —— **被显式关掉的模组不许被"扫目录"重新捡回来**，
    // 否则用户就再也关不掉任何模组了。
    std::array<std::array<char, kModDirectoryCapacity>, kModManifestCapacity> disabledDirectories{};
    std::size_t disabledCount{0};

    [[nodiscard]] bool empty() const noexcept { return count == 0; }
};

} // namespace isaac::runtime
