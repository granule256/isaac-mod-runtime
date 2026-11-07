#pragma once

#include "ports/content_mount_port.hpp"

#include <array>
#include <cstddef>
#include <string_view>

namespace isaac::runtime {

// Keeps the engine's content mount points in sync with the loaded Mods.
//
// Registering is not a one-time setup: the engine clears its mount point table and
// rebuilds it (base content, add-on content, Rep+ patch) whenever content is
// reloaded, which drops every Mod mount point with it. The service therefore
// remembers which Mod directories were mounted so the rebuild relay can restore
// them, and it owns that memory itself because the rebuild callback can run at a
// point where no Mod load request is in flight.
class ContentMountService {
public:
    // 能挂多少个 Mod（2026-09-21 由 8 → 32 → 64）：每个 Mod 最多占 `kLeaves` 那么多个挂载点
    // （现在是 6 个叶子），而"一次能加载几个 Mod"现在是 32 ⇒ 64 留一倍余量。
    static constexpr std::size_t kMaxMods = 64;
    static constexpr std::size_t kMaxDirectoryLength = 128;
    // A Mod contributes its PC-style content directories; all of them are optional in a
    // Mod. These are the leaf names of the PC Mod contract, so they belong to the Mod
    // application layer rather than to the engine adapter.
    //
    // `resources/gfx`（以及 `content/gfx`）**必须一起挂**：ANM2 内部的
    // `<Spritesheet Path="...">` 是**相对 gfx 目录**的裸文件名（本体自己的 .anm2 就是这么写的，
    // 例如 `005.100_collectible.anm2` 里的 `Items/Collectibles/Collectibles_001_TheSadOnion.png`
    // 对应 `resources/gfx/items/collectibles/...`），而引擎侧 `AnmCache::PreloadANM2Images`
    // （`0x158cc`）是把**挂载点字符串直接拼在路径前面**去找文件的（`strncpy_s` + `strcat_s`，
    // 逐个挂载点试）。只有 `.../resources` 一个挂载点时，Mod 自带 .anm2 里的 `draw149.png` 会被
    // 拼成 `.../resources/draw149.png`（不存在）→ 贴图永远加载不上 → `AnimationLayer::RenderFrame`
    // 在 `[spritesheet+0x7c] == 0` 处**静默返回**：现象是"不崩、不报错、什么都不画"
    // （2026-09-13 真机报告 `01789148187`/`01789148432` 正是这个形态）。
    // `resources-dlc3`（2026-09-21 晚加）：PC 的忏悔层。
    //
    // 为什么必须挂它（用户在真机上踩到的坑）：PC 版游戏本体是**两层**资源 —— `resources/` 与
    // `resources-dlc3/`，后者装忏悔新增/改动的文件，且**同名文件优先于** `resources/`
    // （IsaacDocs `tutorials/directories-and-save-files.md:53`）。模组要覆盖哪一层的文件，
    // 就得把文件放在自己目录里的**同一层**（Isaac Blueprints「Creating a mod」），
    // 所以"只带 PNG 的贴图替换模组"经常整包都在 `resources-dlc3/` 里
    // （实例：`visible tinted rocks` 的 23 张 `gfx/grid/rocks_*.png`）。
    // 不挂这一层 ⇒ 那些文件一个都看不见 ⇒ **不报错、画面就是没变化**。
    //
    // 顺序（`kLeaves` 的次序 = 挂载次序，本引擎**后注册者优先**：Stage147–148 真机实测，
    // 新挂的挂载点会盖过本体的 `rp_patch` 与 `resources`，见 `docs/问题与解决记录.md:4873/4903`）：
    // `resources-dlc3` 排在最后 ⇒ 它同时压过本体两层与**本模组自己的** `resources/`，
    // 与 PC 的层序一致。
    static constexpr std::array<std::string_view, 6> kLeaves = {
        std::string_view{"resources"},
        std::string_view{"resources/gfx"},
        std::string_view{"content"},
        std::string_view{"content/gfx"},
        std::string_view{"resources-dlc3"},
        std::string_view{"resources-dlc3/gfx"},
    };
    static constexpr std::size_t kLeafCount = kLeaves.size();

    explicit ContentMountService(IContentMountPort& port) noexcept : port_(port) {}

    // Records the Mod directory and mounts its content leaves. Registering the same
    // directory twice is a no-op, matching the engine's own duplicate handling.
    [[nodiscard]] Status RegisterMod(std::string_view modDirectory) noexcept;
    // Re-mounts every recorded Mod; called after the engine rebuilds its table.
    [[nodiscard]] Status RemountAll() noexcept;
    // Drops the record without touching the engine (a Mod that failed to load must
    // not keep a mount point alive).
    void Clear() noexcept;

    [[nodiscard]] std::size_t mod_count() const noexcept { return count_; }
    [[nodiscard]] std::string_view mod_directory(std::size_t index) const noexcept;

    // 挂载失败在哪个叶子（`kLeaves` 的下标；`kNoFailedLeaf` = 没有失败）。
    //
    // 为什么要它：`MountLeaves` 在**第一个失败的叶子**上就返回（see `.cpp`），而这个失败此前只
    // 变成 `RegisterMod` 的一个 `Status` 码 —— 看不出"是哪个叶子挂不上"。真机读数需要一个能区分
    // "环境不对"（端口直接 fail closed）与"模组自身某个目录不存在"（按契约不算失败）的抓手。
    // 只读诊断，不影响任何判定。
    static constexpr std::uint32_t kNoFailedLeaf = 0xFFFFFFFFu;
    [[nodiscard]] std::uint32_t last_failed_leaf() const noexcept { return lastFailedLeaf_; }

private:
    struct Entry {
        std::array<char, kMaxDirectoryLength> directory{};
        std::size_t length{0};
    };

    [[nodiscard]] Status MountLeaves(const Entry& entry) noexcept;
    [[nodiscard]] const Entry* Find(std::string_view modDirectory) const noexcept;

    IContentMountPort& port_;
    std::array<Entry, kMaxMods> entries_{};
    std::size_t count_{0};
    // 最近一次 `MountLeaves` 失败落在哪个叶子（只读诊断用）。
    std::uint32_t lastFailedLeaf_{kNoFailedLeaf};
};

// The session-scoped instance the rebuild relay reports through. It is published by
// the bootstrap path once the port exists and stays null before that, which the relay
// treats as "nothing to restore".
void SetSessionContentMountService(ContentMountService* service) noexcept;
ContentMountService* SessionContentMountService() noexcept;

} // namespace isaac::runtime
