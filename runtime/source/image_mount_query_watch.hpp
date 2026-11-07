#pragma once

// 路径解析中继里"按路径分桶"的纯逻辑。
//
// ── 为什么要有它 ────────────────────────────────────────────────────────────────
// 的教训（真机读数当场暴露）：诊断只记全局计数（"非 `.pcx` 查询 1342 次、
// 其中 `.anm2` 78 次、引擎答出模组目录 19 次"）**判不了"某一条具体路径归谁"** ——
// 模组独有的路径必然答模组、本体独有的路径必然答本体，两类都被计进那个计数里，
// 而我们要问的恰恰是第三类：**两边都有的共享路径**。
// ⇒ 判据必须**按路径记**。本文件就是那个"按路径分桶"的纯函数：只吃字符串、不碰引擎、
//    不碰文件，因此可以在宿主上直接跑门禁（样板见 `runtime/tests/test_batch352_mount_query_watch.py`）。
//
// ── 桶的取法 ────────────────────────────────────────────────────────────────────
// 目标是 minimapi 的 `IsBadLoad()` 读的那两条路径（`main.lua:1456-1462`）：
//   `gfx/ui/minimap1.anm2`（`RoomUnvisited` 模块 1 帧）与 `gfx/ui/minimap2.anm2`。
// 它自己带的那份在 `mods/<ModDir>/resources/gfx/ui/`，与本体 `rom:/rp_patch/resources/gfx/ui/`
// **同相对路径** ⇒ 谁赢由解析层决定。
//
// 只按"最后一段文件名"匹配，**不按子串**：`foo_minimap1.anm2` 不算（那是另一个文件）。
// 这一点是刻意写成可测的 —— 子串匹配会把不相干的模组资源也算进这两个桶里，读数就脏了。

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace isaac::runtime::bridge {

// 被监视的路径桶。
enum class MountQueryWatch : std::uint32_t {
    None = 0,      // 不关心（绝大多数查询）
    Minimap1 = 1,  // 最后一段 == `minimap1.anm2`
    Minimap2 = 2,  // 最后一段 == `minimap2.anm2`
};

// `path` 的**最后一段**是不是 `segment`。
//
// 与"以 `segment` 结尾"的区别：这里额外要求它前面是路径分隔符（或整个串就是它）。
// 判据来自真机读数的形状（引擎回的是 `rom:/rp_patch/resources/gfx/ui/minimap1.anm2`，
// 查询串是 `gfx/ui/minimap1.anm2`），`/` 与 `\` 都算分隔符（PC 上模组有时写反斜杠）。
[[nodiscard]] inline bool LastPathSegmentEquals(const char* path, const char* segment) noexcept {
    if (path == nullptr || segment == nullptr) {
        return false;
    }
    const std::size_t pathLength = std::strlen(path);
    const std::size_t segmentLength = std::strlen(segment);
    if (segmentLength == 0 || pathLength < segmentLength) {
        return false;
    }
    const std::size_t offset = pathLength - segmentLength;
    if (std::memcmp(path + offset, segment, segmentLength) != 0) {
        return false;
    }
    if (offset == 0) {
        return true;  // 整个串就是那一段
    }
    const char separator = path[offset - 1];
    return separator == '/' || separator == '\\';
}

// 本次查询属于哪个桶（`None` = 不关心）。
[[nodiscard]] inline MountQueryWatch ClassifyMountQueryPath(const char* path) noexcept {
    if (LastPathSegmentEquals(path, "minimap1.anm2")) {
        return MountQueryWatch::Minimap1;
    }
    if (LastPathSegmentEquals(path, "minimap2.anm2")) {
        return MountQueryWatch::Minimap2;
    }
    return MountQueryWatch::None;
}

// "共享路径独立探测"该不该在第 `otherCalls` 次非 `.pcx` 查询时跑一次。
//
// 为什么要独立探测：只在"模组自己来问"的时候记一笔，万一它**压根不走这条中继**
// （比如已被缓存、或走了另一条解析路），我们就只会看到 0 —— 而 0 有两种含义
// （"没被问到"与"被问到但答案是对的"完全相反）。独立探测由**我们主动问引擎**，
// 所以它一定能给出"引擎此刻把这条共享路径解析到哪一层"。
//
// 第 1 次就跑（尽早拿一个样本），之后每 `period` 次再跑一次（拿"更晚、挂载更完整"的样本）。
// 两次样本若不一致，本身就是"解析结果会随时间/缓存变化"的直接证据。
// 主动探测的那一组路径，每条各自留痕。
//
// 为什么要"一组"而不是一条：已经量到 `gfx/ui/minimap1.anm2` 被解析到了本体的
// `rom:/rp_patch/…`，但**光凭这一条分不开两种成因** ——
//   （甲'）解析顺序/优先级：本体那一层就是排在模组前面；
//   （乙'）解析结果被记住了：这条路径在**模组挂载之前**就被本体 HUD 解析过一次，之后一直吃那份记忆。
// 分开它们的办法就是**同时问几条不同性质的路径**，看"谁能赢、谁不能"：
//
//   [0] `gfx/ui/minimap1.anm2`   —— 共享（本体 `rp_patch` 里也有）、**本体启动期就会用** ⇒ 已知答本体；
//   [1] `gfx/eid_inline_icons.anm2` —— **模组独有**（本机核过：本体 `resources/` 与
//       `rp_patch/resources/` 两棵树里都没有这个文件）⇒ **正对照**：它若答模组，就证明
//       模组的挂载点对解析器是可见的（这一步排掉"挂载根本没上"）。
//   [2] `costumes2.xml`          —— 共享、**在 `rp_patch` 里**、模组是在 `content` 叶子下带的
//       ⇒ 与 [0] 同"层"但**本体未必在启动期用过**：它若答模组，成因就是（乙'）。
//   [3] `music.xml`              —— 共享、**只在 `resources` 里**（`rp_patch` 没有）⇒
//       它若答模组、而 [0]/[2] 答本体 ⇒ 说明"模组压得过 `resources`、压不过 `rp_patch`" = （甲'）。
//
// 四条都是只读的路径解析（和引擎自己做的事一样），不改任何状态。
// 换过一轮（2026-10-04）：353 已经量到 `gfx/eid_inline_icons.anm2`（模组独有、
//   叶子相对形式）**答空** ⇒ "覆盖没生效"不是优先级问题，而是**解析器看不到模组那一层**。
//   ⇒ 现在问的是"**换一种键的形状，模组文件能不能被解析到**"，用来分清两件事：
//      （a）挂载点根本不在表里 / 模组树对解析器不可见；
//      （b）挂载在、但**叶子相对**这种键形状匹配不上（那我们自己的挂载层级就要改）。
//   形式沿用真机已证的形状：`GetMountedFilePath` 认**应用根相对**（不带 `rom:/`）的串
//   —— batch 152/153 读数里见过它答出 `isaac_mods/mods/<目录>/content/…`。
// 再换一轮（2026-10-04）：354 已经量到"应用根相对能命中模组、叶子相对不能"，
//   但仍分不开两件事：**A（层序）** 模组挂载点**有**叶子相对的键、只是本体先命中；
//   **B（键形状/挂载层级）** 模组挂载点的键压根**不是**叶子相对。
//   ⇒ 唯一的解法是**拿同一份文件问两种形式**，而且那份文件必须**已经被证明真的在卡上**
//     —— `isaac_mods/mods/goodtripfixed/resources/sprite/gt/gt_ui.anm2` 在 354 里答出了模组目录，
//        所以 goodtripfixed 的 `resources/sprite/gt/gt_ui.anm2` **一定在**。
//   （354 的教训：上一轮的"正对照"靠的是二十天前的卡备份，卡上现在有没有那份文件从没核过 ⇒
//     判据白费一半。**对照路径必须"同一份文件、两种问法"。**）
inline constexpr std::array<const char*, 4> kSharedPathProbeQueries = {
    // [0] 叶子相对：goodtripfixed 独有（应用根相对那条已证它在卡上 ⇒ 这一格只反映"键形状"）
    "sprite/gt/gt_ui.anm2",
    // [1] 应用根相对：**同一份文件**（354 已证能命中 ⇒ 本轮的"文件确实在"的锚点）
    "isaac_mods/mods/goodtripfixed/resources/sprite/gt/gt_ui.anm2",
    // [2] 叶子相对、共享（本体 `rp_patch` 里也有）—— 已知答本体
    "gfx/ui/minimap1.anm2",
    // [3] 应用根相对：**minimapi 自己那份**（就是"本该覆盖本体"的那个文件）
    "isaac_mods/mods/minimapi/resources/gfx/ui/minimap1.anm2",
};

[[nodiscard]] inline bool ShouldRunSharedPathProbe(std::uint32_t otherCalls,
                                                   std::uint32_t period) noexcept {
    if (otherCalls == 0) {
        return false;
    }
    if (otherCalls == 1) {
        return true;
    }
    return period != 0 && (otherCalls % period) == 0;
}

} // namespace isaac::runtime::bridge
