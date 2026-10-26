#pragma once

#include "domain/mod/mod_manifest.hpp"
#include "domain/runtime/status.hpp"

#include <array>
#include <cstddef>
#include <string_view>

namespace isaac::runtime {

// 同一次加载里最多记几个"被关掉"的模组。
//
// 为什么只记"关掉的"而不是"每个模组的状态"：新装的模组应当**默认开着**（PC 就是这个语义：
// 把文件夹丢进 `mods/` 就生效）。只记例外，文件就永远只有几十字节，也不会因为"模组换名字"
// 留下过期条目。
//
// ★★★ 2026-10-11（批次 427）：**8 → 32**。
//   真机撞的：用户报「从模组列表序号 6 起都关不掉，关掉重启后还是开着」。
//   机理 = 这份名单**上限只有 8**，而 `SetEnabled` 满了直接 `CapacityExceeded`、**一个字节都不写**
//   ⇒ 菜单上开关跳了、重启后照旧。当时实测"活着的被关"已有 6 条
//   （`[41] discoveredRealMods 17 − [40] enabledRealMods 11 = 6`），
//   **6 + 死条目 = 8 = 满** ⇒ 之后每一次"关掉"都不落盘。
//   ★ 8 这个数是老功能（提交 `c4642f21`，2026-09-16）随手定的；卡上模组已有 17~18 个，
//     上限比模组总数还小 ⇒ **必须抬到 ≥ 模组容量**。这里取 32，与
//     `kModManifestCapacity` 对齐（那是同一条链上的容量）。
inline constexpr std::size_t kMaximumDisabledMods = kModManifestCapacity;

// 一个模组目录名（与自动发现用的容量一致：它来自同一批字符串）。
inline constexpr std::size_t kModToggleNameCapacity = kModDirectoryCapacity;

using ModToggleName = std::array<char, kModToggleNameCapacity>;

// 模组开关状态：**纯值对象**（没有文件句柄、没有指针），因此可以直接被单测覆盖，
// 也可以在栈上传递。序列化格式是纯文本，便于用户理解与排查：
//
//     isaac-switch-mods 1
//     off SomeModDirectory
//     off AnotherMod
//
// 解析纪律（与清单解析器同口径）：不认识的**整行**忽略（未来加字段不会让老版本解析失败），
// 但"明显被写坏"的条目（空名字、名字里带 `/`）整份拒绝 —— 拿可疑名字去拼路径、去比目录，
// 只会让"某个模组没生效"变成查不出来的问题。
struct ModToggleState {
    std::array<ModToggleName, kMaximumDisabledMods> disabled{};
    std::size_t disabledCount{0};

    [[nodiscard]] bool IsDisabled(std::string_view directory) const noexcept;
    [[nodiscard]] bool Empty() const noexcept { return disabledCount == 0; }

    // 解析一份状态文本。`NotFound` 由调用方处理（文件不存在 = 空状态），这里只管文本。
    [[nodiscard]] Status Parse(std::string_view text) noexcept;

    // 序列化到 `out`；放不下返回 0（调用方按 `CapacityExceeded` 处理，不写半截）。
    [[nodiscard]] std::size_t Serialize(char* out, std::size_t capacity) const noexcept;

    // 设置某个模组的开关。关掉时追加；打开时从表里删掉（"只记例外"）。
    // 表满 ⇒ `CapacityExceeded`（不静默丢弃）。
    [[nodiscard]] Status SetEnabled(std::string_view directory, bool enabled) noexcept;

    // ★★ 批次 427：丢掉名单里"这次扫描没看到的目录名"（模组被删/改名后留下的**死条目**），
    // 返回丢掉几条。`exists` 收 `std::string_view`、返回 bool（"这个目录还在不在"）。
    //
    // 为什么必须有它：**模组从卡上删掉之后，它那条名字会永远占着名单里的一格**
    // （427 之前没有任何清理逻辑）⇒ **每删一个模组就永久少一格**，很快就把上限吃满，
    // 症状就是"后面那些模组怎么关都关不掉"（用户 2026-10-11 报的就是这个）。
    // ★ 只改内存：**不在这里落盘**。下一次 `Save()`（或用户改任一个开关）自然就会写回去，
    //   而每次开机都会再清一遍 ⇒ 不落盘也不影响效果，还避免了"开机就写存档"这个副作用。
    template <typename Exists>
    std::size_t PruneMissing(Exists&& exists) noexcept {
        std::size_t kept = 0;
        for (std::size_t index = 0; index < disabledCount; ++index) {
            if (exists(std::string_view(disabled[index].data()))) {
                if (kept != index) {
                    disabled[kept] = disabled[index];
                }
                ++kept;
            }
        }
        const std::size_t dropped = disabledCount - kept;
        for (std::size_t index = kept; index < disabledCount; ++index) {
            disabled[index] = ModToggleName{};
        }
        disabledCount = kept;
        return dropped;
    }
};

//: 状态文件名（相对存档根）。改名等于让所有用户的开关归零，所以它是一个具名常量。
inline constexpr char kModToggleStateFileName[] = "isaac-switch-mods-state.txt";
//: 序列化后的最大字节数：头一行 + 每行 `off ` + 名字 + '\n'。
inline constexpr std::size_t kModToggleStateMaximumBytes =
    32 + kMaximumDisabledMods * (4 + kModToggleNameCapacity);

} // namespace isaac::runtime
