#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace ModManifest {

inline constexpr std::size_t kDirectoryCapacity = 256;
inline constexpr std::size_t kEntryCapacity = 1024;

struct SelectedMod {
    std::array<char, kDirectoryCapacity> directory{};
    // Empty (all zero) when the manifest omits `entry`: the Mod is a pure-resource
    // Mod and has no script to run.
    std::array<char, kEntryCapacity> entry{};
};

// 同一次加载里最多认几个 Mod（2026-09-16 多模组加载；2026-09-21 由 4 → 16 → 32）。
//
// 为什么是"上限 + 显式失败"而不是"截断到前 N 个"：截断会让第 N+1 个 Mod **安静地不加载**，
// 症状是"某个 Mod 没生效"却无从归因；显式失败至少会出现在诊断里。
// 体积：`SelectedMods` 每个条目 1280 字节，32 个 ≈ 40 KiB（"被关掉的"只留目录名，另 8 KiB）。
// 因此 **`hook_manager.cpp` 里把解析器与服务都挂成 `static`**，这个值对象不进游戏线程的栈。
inline constexpr std::size_t kMaximumSelectedMods = 32;

// 一次性收下**所有**启用的 Mod（PC 语义：清单里 `enabled = true` 的全部加载，
// 执行顺序 = 清单里的书写顺序）。`SelectFirstEnabled` 是它的历史子集，两者共用同一个解析器。
struct SelectedMods {
    std::array<SelectedMod, kMaximumSelectedMods> mods{};
    std::size_t count{0};
    // 清单里 `enabled = false` 的那批（2026-09-21）：只用于"自动发现时别把它们捡回来"。
    // 只留**目录名**（不要整条 `SelectedMod`：32 个 × 1.28 KiB 的值对象没必要）。
    std::array<std::array<char, kDirectoryCapacity>, kMaximumSelectedMods> disabledDirectories{};
    std::size_t disabledCount{0};
};

enum class ParseResult : std::uint32_t {
    Success,
    InvalidArgument,
    InvalidJson,
    InvalidSchema,
    InvalidMod,
    NoEnabledMod,
    // 启用的 Mod 个数超过 `kMaximumSelectedMods`：**不截断**，直接判非法。
    TooManyMods,
};

ParseResult SelectFirstEnabled(const char* json, std::size_t length, SelectedMod* output);

// 收下全部启用的 Mod（顺序 = 清单里的书写顺序）。一个都没有时返回 `NoEnabledMod`。
ParseResult SelectAllEnabled(const char* json, std::size_t length, SelectedMods* output);

} // namespace ModManifest
