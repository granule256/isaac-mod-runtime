#pragma once

// 局内单向闩锁的持久标记（2026-09-25 ，用户裁定"比 PC 严"）。
//
// ## 它解决什么
//
// 117~119 的那颗闩锁只在**内存**里：出局时转成"留存"、下一次"继续"接回来。
// 但**重启游戏/主机**就把内存清空 ⇒ "关掉模组之后仍锁"只能撑到重启为止。
// 用户 2026-09-25 明确要的是**跨重启**也保持：**这一份存档只要在妈腿未解锁时用过模组，
// 之后把模组关掉、甚至重启，都继续禁成就**，直到**开新局**。
//
// 先说清它与 PC 的关系（用户已确认要"比 PC 严"，不是"PC 原样"）：
//   PC 的 `ModManager::AchievementsLocked()`（`0x250CB8`，098 逐条反汇编）是**开局那一刻的
//   实时查询**（遍历模组列表 + 读 `PersistentGameData::Unlocked(4)` 取反），
//   **不持久化任何"这个档被污染过"的标记**；PC 的只读位（`PGD+0x1`）每次开局都会被
//   `Game::Start` 清掉再重算。所以"跨重启仍锁"是**我们自己的语义**，不是 PC 的原样。
//
// ## 为什么不按存档槽隔离
//
// 现在拿不到"当前是哪个槽"的可靠身份，而 `docs/开发规范.md` 第 18 条明确写着
// "**profile/存档槽隔离在取得可靠槽标识前不得假定**" ⇒ 这里只记 **profile 级**的一个标记，
// 也**不对外宣称**按槽隔离（同一个会话内换槽"继续"会被当成同一局 —— 这条边界登记在存档
// README 的"已知边界"里）。
//
// ## 文件格式（照现有 `isaac-switch-mods-state.txt` 那种"人能看懂 + 容忍未知行"的做法）
//
//     isaac-runtime-run-taint 1
//     tainted=1
//
// * 头一行是**可读的标识 + 版本**，解析时**不参与判定**（将来加字段不会让老版本读不懂）；
// * 只认 `tainted=` 开头的行，值只认 `0` / `1`；
// * 其它行、其它值、空内容、乱码 ⇒ 一律当成**干净**（0）。
//   这条方向叫 fail-open：读不懂就当没污染 ⇒ 后果是"可能少禁一次成就"，
//     而不是"把不该禁的档禁掉"。它与本项目一贯的"**宁可不禁，也不误禁**"同方向，
//     也和 098 那条降级（拿不到回退入口就什么都不写）一致。

#include <cstddef>
#include <cstring>
#include <string_view>

namespace isaac::runtime {

// 状态文件名（相对存档根，与模组开关状态文件同一片区域）。
// 改名等于让所有已存的标记失效（用户的档会突然又开始给成就）⇒ 它是一个具名常量。
inline constexpr char kRunTaintFileName[] = "isaac-runtime-run-taint.txt";
// 头一行的标识 + 版本（解析不依赖它，只为了人能看懂、以及将来升级时有落脚点）。
inline constexpr char kRunTaintHeader[] = "isaac-runtime-run-taint 1";
// 序列化后的最大字节数（头一行 + 换行 + `tainted=` 那一行）—— 只有一个标记，够用即可。
inline constexpr std::size_t kRunTaintMaximumBytes =
    sizeof(kRunTaintHeader) + sizeof("tainted=1\n");

// 解析一份文本 ⇒ 标记值。任何看不懂的内容都当成 `false`（fail-open，理由见文件头）。
[[nodiscard]] inline bool ParseRunTaint(std::string_view text) noexcept {
    constexpr std::string_view kKey = "tainted=";
    std::size_t offset = 0;
    while (offset <= text.size()) {
        const std::size_t end = text.find('\n', offset);
        const std::size_t length =
            (end == std::string_view::npos ? text.size() : end) - offset;
        const std::string_view line = text.substr(offset, length);
        if (line.size() > kKey.size() && line.substr(0, kKey.size()) == kKey) {
            // 只认 0 / 1：`tainted=2`、`tainted=yes` 之类**不是**"污染"，而是看不懂 ⇒ 当干净。
            return line.substr(kKey.size()) == "1";
        }
        if (end == std::string_view::npos) {
            break;
        }
        offset = end + 1;
    }
    return false;
}

// 序列化。放不下（或 `out` 为空）返回 0 —— 调用方按"写不了"处理，不写半截
// （半截状态比没有状态更难查，与 `ISaveFilePort::Write` 的口径一致）。
[[nodiscard]] inline std::size_t SerializeRunTaint(bool tainted, char* out,
                                                   std::size_t capacity) noexcept {
    constexpr std::string_view kKey = "tainted=";
    const std::size_t headerLength = sizeof(kRunTaintHeader) - 1;  // 不含结尾 '\0'
    const std::size_t valueLength = kKey.size() + 1 /*值*/ + 1 /*'\n'*/;
    const std::size_t total = headerLength + 1 /*'\n'*/ + valueLength;
    if (out == nullptr || capacity < total) {
        return 0;
    }
    std::size_t at = 0;
    std::memcpy(out + at, kRunTaintHeader, headerLength);
    at += headerLength;
    out[at++] = '\n';
    std::memcpy(out + at, kKey.data(), kKey.size());
    at += kKey.size();
    out[at++] = tainted ? '1' : '0';
    out[at++] = '\n';
    return at;
}

} // namespace isaac::runtime