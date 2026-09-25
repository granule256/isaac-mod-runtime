#pragma once

// 运行时**发现结果** → 原生模组页的条目来源：把"游戏这次认得哪些模组、它们开着还是关着"
// 变成 `Menu_Mods` 那张纸能直接显示的一行行条目。
//
// ## 为什么单独一个单元
//
// `mod_page_sources.hpp` 回答的是"给定若干**目录名**，怎么读到它们的显示名"；
// 这一层回答的是"**目录名与开关从哪来**"。后者是真机上唯一可能悄悄错的一跳：
// 目录列表取自运行时的模组发现（清单 + 扫目录合并的结果），开关取自运行时的模组开关服务。
// 两者都是**注入**的（宿主测试给假实现），所以"顺序对不对、开关有没有逐条对上、
// 装不下怎么办"这些都能离线判死，真机上只剩"这两条通道能不能读到"这一件事。
//
// ## 口径（与 Lua 侧的 `RuntimeMods.List()` 同一份数据）
//
// * **目录顺序原样保留**：页面上第几行 = 发现结果里的第几个。运行时给的那个顺序本身是有
//   意义的（清单里的书写顺序在前、自动发现的按名字升序在后），重排会让"页面顺序"和
//   "加载顺序"不一致。
// * **开关逐条问**：每条都调一次开关来源（不缓存、不推断）。
// * **"旧版"位恒 false**（见下）。
// * **装不下就整体放弃**（返回 0）：半截列表比空列表更容易让人误判成"某些模组丢了"。
//
// ## "旧版"位为什么恒 false（不是偷懒，是没有证据）
//
// 页面上那一行末尾的 `[Old]` 来自条目的 `+0x13a`。而这个字节在 Switch 版引擎里**没有可观测的
// 来源**：整条 mod 管线是死代码（`ModManager::Reset` 无调用者、`ListMods` 只有它一个调用者），
// 谁写这一位、按什么条件写，静态查不出来。照 PC 猜一个语义（例如"启用但本次没加载"）就是
// **造一个 PC 没有的差异**，而那正是本项目明令不许做的事。
// ⇒ 先恒 false，等有可复核的证据再填；调用方要显示别的意思就该新起一个位置，而不是借这一位。

#include "mod_page_entries.hpp"
#include "mod_page_sources.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>

#include "domain/mod/mod_manifest.hpp"

namespace isaac::runtime {

//: 一次最多往页面上放几个模组 = 一次最多加载几个（`kModManifestCapacity`）。
//: 两者必须是同一个数：能加载却放不下的那种情况没有人会想到去查，也不该出现。
inline constexpr std::uint32_t kModPageMaximumMods =
    static_cast<std::uint32_t>(kModManifestCapacity);

//: "有哪些模组目录"的来源：把目录名写进 `out`（最多 `capacity` 个）并返回写进去的个数。
//: 返回 0 表示"没有目录"；返回 > `capacity` 表示装不下（调用方整体放弃，**不截断**）。
using ModPageDirectoryProvider = std::uint32_t (*)(void* context, const char** out,
                                                  std::uint32_t capacity);

//: "这个目录现在开着吗"的来源。
using ModPageEnabledProvider = bool (*)(void* context, const char* directory);

//: "把这个路径**解析成引擎自己能打开的绝对路径**"的来源。
//:
//: 真机上是 `IContentManager::GetMountedFilePath`：返回**堆上的挂载绝对路径**（调用方要用游戏的
//: `operator delete[]` 还），解析不到返回空。它**只查表、不开文件**，所以路径形状不对时它也只是
//: 返回空 —— 不会 Abort。
//:
//: ⚠️ **契约里最要紧的一条**（2026-09-22 真机事故换来的，见 `docs/问题与解决记录.md` 续七十）：
//: **读的时候必须用这个回调写出来的那条路径，不能用传进去的那条**。
//: `File::OpenRead` **不做挂载解析**，它把路径原样交给 `nn::fs::OpenFile`；形状不对（例如少了
//: `mount:/`）那边**直接 `nn::diag::Abort`**、不是返回错误码。
//: 所以"先问存在性、再拿同一条路径去读"这个写法是错的 —— 它会在形状不被认的那一类路径上崩游戏。
//: 宿主门禁 `test_mod_page_runtime_sources` 逐条钉住这一条。
using ModPagePathResolver = bool (*)(void* context, const char* path, char* out,
                                    std::size_t capacity);

//: `rom:/` 前缀。`CollectModPageSources` 拼出来的是**带前缀**的形式。
inline constexpr char kModPageRomPrefix[] = "rom:/";
inline constexpr std::size_t kModPageRomPrefixBytes = sizeof(kModPageRomPrefix) - 1;

//: 解析路径的两种**输入**形式（"绝不盲开"的最后一步）：
//:   ① 先按原样问 —— `CollectModPageSources` 拼的是**带 `rom:/` 前缀**的形式；
//:   ② 原样答不出来时，去掉前缀再问一次 —— 引擎自己的调用点在真机上用过的形状是
//:      **相对应用根**那一份（Stage147 探针：`gfx/005.100_collectible.anm2`）。
//:
//: 成功时把**解析器写出来的那条绝对路径**交给 `out`（不是传进来的那条！理由见上面那个契约），
//: 并返回 true。`formMask` 的第 0 / 1 位分别记"原样就解析出来了" / "去前缀才解析出来"（失败置 0）
//: ⇒ 读到它的调用方**知道**引擎认哪一种输入形式，而不是靠下次猜。
//:
//: 为什么不写死一种输入形式：两种形状都各自有真机证据，而"哪一种对这个前缀的路径成立"没有。
//: 与其挑一种去赌，不如两种都问、并把答案记下来（多一次内存里的查表，代价可以忽略）。
[[nodiscard]] inline bool ResolveModPagePath(const char* path, ModPagePathResolver resolve,
                                             void* context, char* out, std::size_t capacity,
                                             std::uint32_t* formMask) noexcept {
    if (formMask != nullptr) {
        *formMask = 0;
    }
    if (path == nullptr || resolve == nullptr || out == nullptr || capacity == 0) {
        return false;
    }
    if (resolve(context, path, out, capacity)) {
        if (formMask != nullptr) {
            *formMask = 1u;
        }
        return true;
    }
    if (std::strncmp(path, kModPageRomPrefix, kModPageRomPrefixBytes) != 0) {
        return false;
    }
    const char* stripped = path + kModPageRomPrefixBytes;
    // 前缀后面什么都没有（`"rom:/"`）不是一条路径：不去问，直接判没有。
    if (stripped[0] == '\0' || !resolve(context, stripped, out, capacity)) {
        return false;
    }
    if (formMask != nullptr) {
        *formMask = 2u;
    }
    return true;
}

//: "这次该干什么" —— 只有三态，且是**纯判定**（读数的调用方按它决定"再等一帧"还是"退固定名"）。
enum class ModPageSourceDecision : std::uint32_t {
    Wait,      //: 条目还没备好、但**还可能备好** ⇒ 这一帧什么也别做，下帧再试
    Ready,     //: 真实条目已经造好 ⇒ 往下走
    Fallback,  //: 取不到就不等了 ⇒ 退写死的测试名（并如实记进诊断字）
};

//: `Wait` 与 `Fallback` 的分界，**只此一处**：
//:
//: * 发现结果**一个目录都没有**、而且还没到尝试上限 ⇒ `Wait`。
//:   为什么必须等：发现结果是启动的模组加载填进去的（worker 线程，探针构建还给了 5 秒启动
//:   延迟），而"菜单系统构造好了"并不保证模组已经扫完。赌的话后果是"表只写一次、写的是空表"，
//:   ⇒ 整轮真机白跑。这是"看起来没模组"与"时序还没到"必须分开的那种坑。
//: * 目录数 > 0、但条目没造出来（名字区放不下、读文件那一环断了…）⇒ `Fallback`。
//:   数据在，失败是真的，再等也不会变好 —— 继续等只会让人以为"这一版没反应"。
[[nodiscard]] constexpr ModPageSourceDecision DecideModPageSource(
    bool built, std::uint32_t directories, std::uint32_t attempts,
    std::uint32_t attemptLimit) noexcept {
    if (built) {
        return ModPageSourceDecision::Ready;
    }
    if (directories == 0 && attempts < attemptLimit) {
        return ModPageSourceDecision::Wait;
    }
    return ModPageSourceDecision::Fallback;
}

//: 这一趟的数字（真机读数靠它分辨"页面上没有名字"到底是哪一环断了）。
struct ModPageRuntimeStats {
    std::uint32_t directories;  //: 发现到几个目录
    std::uint32_t enabled;      //: 其中几个是"开着"的
    std::uint32_t entries;      //: 最终造出几条条目来源（0 = 整体放弃）
    std::uint32_t overflowed;   //: 1 = 目录数超出容量 ⇒ 整体放弃
};

//: 收来源。返回造出来的条数（0 = 整体放弃，调用方**不要**拿半截结果去用）。
//: `nameArena` 放名字副本；`scratchPath`/`scratchText` 是拼路径与读文件用的中转缓冲，
//: 大小分别按 `kModPageMetadataPathCapacity` / `kModPageMetadataCapacity` 给。
[[nodiscard]] inline std::uint32_t CollectRuntimeModPageSources(
    ModPageEntrySource* out, std::uint32_t capacity, ModPageDirectoryProvider directories,
    void* directoryContext, ModPageEnabledProvider enabled, void* enabledContext,
    ModPageTextReader reader, void* readerContext, char* nameArena, std::size_t nameArenaSize,
    char* scratchPath, char* scratchText, ModPageRuntimeStats* stats) noexcept {
    if (stats != nullptr) {
        *stats = ModPageRuntimeStats{};
    }
    if (out == nullptr || directories == nullptr || reader == nullptr || nameArena == nullptr ||
        scratchPath == nullptr || scratchText == nullptr || capacity == 0 ||
        capacity > kModPageMaximumMods || nameArenaSize == 0) {
        return 0;
    }
    // 这两张表按"一次最多几个模组"定上界：局部数组（几百字节）而不是函数内 static ——
    // 本模块是 `-nostartfiles` 起的，函数内带动态初始化的 static 会引出线程安全静态守卫，
    // 那是 2026-09-21 真机事故的形状（见 `runtime/tests/test_no_static_guard_init.py`）。
    const char* names[kModPageMaximumMods] = {};
    bool enabledFlags[kModPageMaximumMods] = {};
    bool outdatedFlags[kModPageMaximumMods] = {};

    const std::uint32_t found = directories(directoryContext, names, capacity);
    if (found > capacity) {
        if (stats != nullptr) {
            stats->overflowed = 1;
        }
        return 0;
    }
    if (found == 0) {
        return 0;
    }
    std::uint32_t enabledCount = 0;
    for (std::uint32_t index = 0; index < found; ++index) {
        // 空目录名会让拼路径变成 `mods//metadata.xml` 这种永远读不到的东西 ⇒ 整体放弃，
        // 而不是"悄悄跳过一个"（跳过的后果是页面上少一行、没人知道为什么）。
        if (names[index] == nullptr || names[index][0] == '\0') {
            return 0;
        }
        enabledFlags[index] =
            enabled != nullptr ? enabled(enabledContext, names[index]) : true;
        outdatedFlags[index] = false;  // 理由见文件头
        if (enabledFlags[index]) {
            ++enabledCount;
        }
    }
    const std::uint32_t written =
        CollectModPageSources(out, capacity, names, found, enabledFlags, outdatedFlags, reader,
                              readerContext, nameArena, nameArenaSize, scratchPath, scratchText);
    if (stats != nullptr) {
        stats->directories = found;
        stats->enabled = enabledCount;
        stats->entries = written;
    }
    return written;
}

}  // namespace isaac::runtime
