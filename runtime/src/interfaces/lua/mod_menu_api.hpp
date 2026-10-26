#pragma once

#include "application/mod/manifest_service.hpp"

#include <cstddef>
#include "domain/mod/mod_bits.hpp"

struct lua_State;

namespace isaac::runtime {

class ModToggleService;

// 模组开关菜单的控制面（2026-09-16，路线 B）。
//
// 这是**运行时自己的**接口，不是 PC 的 Lua API：PC 的模组开关在游戏自己的菜单里，Lua 侧
// 看不到模组清单，所以我们没有可对齐的 PC 语义，只能自己定义一套最小的。表名 `RuntimeMods`，
// 只有四个成员，全部围绕"读清单 / 改开关 / 落盘"：
//
//   RuntimeMods.List()                     -> { {Directory=, Enabled=, Active=}, ... }
//   RuntimeMods.SetEnabled(directory, on)  -> boolean（只改内存）
//   RuntimeMods.Save()                     -> boolean（写进游戏存档分区）
//   RuntimeMods.Reload()                   -> boolean（从存档重新读）
//
// `Active` = 最近一轮加载选择的模组（含纯资源模组）。菜单内Enabled表示待应用选择；
// 退出菜单的同步重载把内容、脚本与Active一起切换，不再要求重启进程。
//
//   RuntimeMods.Report(code)               -> 无返回值；菜单上报"走到哪一步了"
//
// 清单由 `hook_manager` 在扫描/过滤时灌进来（见 `ModMenuPublishDiscovered` /
// `ModMenuMarkActive`），所以这个 TU 不自己去列目录、也不自己读文件。
//
// `Report` 是**给真机排障用的**：菜单是脚本，出问题时"没反应"什么都看不出来，所以脚本每走到
// 一个里程碑就报一次（脚本已加载 / 字体装上了 / 字体失败 / 菜单打开 / update 回调跑过 /
// 切换过 / 存过盘）。C++ 侧把它们记成位图，调试桩一次读数就能分辨到底卡在哪一步。

// 建立 `RuntimeMods` 表并挂成全局（由 `lua_runtime.cpp` 的准备阶段调用）。
int RegisterModMenuApi(lua_State* state) noexcept;

// hook_manager 侧：告诉菜单"发现了哪些模组"（过滤**之前**调用）。
// displayNames 指向稳定名称区，必须存活到下次发布；为空时使用目录名。
void ModMenuPublishDiscovered(const ResolvedManifestModBatch& batch,
                              const char* const* displayNames = nullptr) noexcept;
[[nodiscard]] const char* ModMenuDiscoveredDisplayName(std::size_t index) noexcept;
[[nodiscard]] std::uint32_t ModMenuDiscoveryGeneration() noexcept;

// hook_manager 侧：标记"这一批本次真的加载了"（过滤**之后**调用）。
void ModMenuMarkActive(const ResolvedManifestModBatch& batch) noexcept;

// hook_manager 侧：把开关服务交给菜单（读状态、改开关、落盘都通过它）。
void ModMenuAttachToggles(ModToggleService* service) noexcept;

// ---- 读面（C++ 侧访问器，2026-09-22 批次 043）---------------------------------
//
// 原生模组页（引擎自己的 `Menu_Mods`，见 `source/probe/native_mods_menu_probe.cpp`）要显示的
// 就是**这一份发现结果**。走访问器而不是让它自己再列一次目录、再读一次开关，理由是"两处各自
// 维护一份"必然会漂：用户在原生日志页上看到的名字与在自己的 Lua 模组菜单里看到的对不上时，
// 没有人能判断哪一份是对的。
//
// 口径与 `RuntimeMods.List()` **完全一致**：
//   * 目录 = `ModMenuPublishDiscovered` 收下的那一批（清单 + 扫目录合并后、按开关过滤**之前**）
//     ⇒ 被用户关掉的模组也在里面（页面上正是要显示它们）；
//   * 启用 = 开关服务现在的状态（`ModToggleService::IsEnabled`）。开关服务还没接上时**恒 true**
//     （与 `RuntimeMods.List()` 里 `g_toggles == nullptr` 那一条同口径）。
//
// 生命周期：返回的指针指向本单元里的静态缓冲，进程内稳定；`ModMenuPublishDiscovered` 下一次
// 被调用时内容会被整体替换。
[[nodiscard]] std::size_t ModMenuDiscoveredCount() noexcept;

//: 模组发现**是否已经出过结果**。★ 2026-09-24 批次 098 起**不再**用于「禁成就」——
//: 那时它撑的是 fail-closed（"还没出结果就按有模组算"），而那正是"关着模组也不给成就"的形状；
//: 现在判据只看 `ModMenuActiveCount()`（实际加载结果，启动时就有）。此函数保留给页面与读数用。
[[nodiscard]] bool ModMenuDiscoveryDone() noexcept;

//: 越界返回 `nullptr`。
[[nodiscard]] const char* ModMenuDiscoveredDirectory(std::size_t index) noexcept;

//: 这个目录当前是不是"开着"。实测开关服务**只认识本次扫描到的目录**（`RuntimeMods.SetEnabled`
//: 同一条限制），所以传一个不在列表里的名字时，开关服务那边同样答"开着"。
[[nodiscard]] bool ModMenuDiscoveredEnabled(const char* directory) noexcept;

//: ★ 运行层**实际加载**的真实模组个数（启动时 `ModMenuMarkActive` 标出来的那批，
//: **不含**运行时自身与它自带的菜单模组）。
//: 与上面那个"开关状态"的区别：用户把开关关掉之后，要**重启游戏**才会真的不加载。
//: ★ 2026-09-24 批次 107 起「禁成就」**不再**用它（改用下面那个"启用状态"的口径，见那里的说明）；
//:   它现在只作为**读数/诊断**用（"本局到底加载了几个"是排障时最有用的一格）。
[[nodiscard]] std::size_t ModMenuActiveCount() noexcept;

//: ★ 处于**启用状态**的真实模组个数 —— 口径 = 开关服务里那一份（**模组页开关 / Lua 侧
//: `RuntimeMods.SetEnabled` 改的就是它**，与页面上看到的一致），**不看有没有重启**。
//:
//: 为什么需要它（用户 2026-09-24 实测后裁定，见 `docs/问题与解决记录.md`「续八十三」）：
//: PC 的 `ModManager::AchievementsLocked()` 走的是**模组列表里每一项的启用位** —— 界面上一开
//: 就变、**不需要重启**；而"实际加载"只在**开机那一刻**按存档里的开关定下来
//: ⇒ 拿"实际加载"当判据时，"开了开关但还没重启就进局"这一种会被**漏判**（真机实测：
//: 开着模组进局却照样给成就）。⇒ 「禁成就」按 **PC 口径**用它。
//:
//: ★ 开关服务还没接上时（`g_toggles == nullptr`）与页面保持同一口径：一律当"开着"
//:   （那时数出来的就是"发现的真实模组数"）。这个状态只在开机极早期存在，而判据是在
//:   **开局那一刻**问的 ⇒ 实际走不到；真走到了也是"宁可锁"，与 PC 同方向。
[[nodiscard]] std::size_t ModMenuEnabledCount() noexcept;

//: 读数专用（2026-09-24 批次 116）：把"发现清单"前 32 条的两种状态各打成一张**位图**，外加条数。
//:
//: 为什么需要它：`[30]` / `[40]` 只是两个**汇总数**，而待修记录里出现过一对互相矛盾的读数
//: （`[40] = 0` 与"开关服务读不出来时默认全都开着"）—— 汇总数分不出是"状态文件写着全禁用"、
//: "清单是空的"，还是"发现根本没跑过"。位图一格就能把这三者分开（见状态面 `.hpp` 的 [41]..[44]）。
//: ★ 为什么用位图而不是逐条名字：状态面是**定长 u32 数组**，名字留几格都不够、还会随模组数漂；
//:   位图 + 条数就足以自证"清单非空、且哪几条开着/哪几条真的加载了"。
struct ModMenuDiscoveredReading {
    std::uint32_t count;        //: 清单条数（与 `ModMenuDiscoveredCount()` 同一个值）
    std::uint32_t enabledMask;  //: bit i = 第 i 条**现在开着**（开关服务 `IsEnabled`）
    std::uint32_t activeMask;   //: bit i = 第 i 条**本局开机时真的加载了**
    ModBits enabledBits; // 完整256条；上述Mask只表示低32条，保留旧诊断ABI。
    ModBits activeBits;
};

[[nodiscard]] ModMenuDiscoveredReading ModMenuDiscoveredForReading() noexcept;

// ---- 写面（C++ 侧访问器）：与 Lua 侧 `RuntimeMods.SetEnabled` / `RuntimeMods.Save` **同一口径** ----
// 为什么要有它们：原生模组页（探针）要在游戏里改开关，而"改内存 / 什么时候落盘"这两件事
// 已经有既定口径（`RuntimeMods` 的处理器就是这么写的）—— 原生页直接复用，**不引入第二份判断**：
//   * `ModMenuSetEnabled`：**只改内存**，不落盘；未知目录一律拒绝
//     （与 Lua 侧同一条纪律：名字打错时不要往状态文件里塞一个永远不生效的条目）；
//   * `ModMenuSaveToggles`：把状态写进**游戏存档分区**（`isaac-switch-mods-state.txt`），
//     由调用方在合适时机调（原生页 = **退出模组页时一次**，与用户 2026-09-22 的裁定一致）。
// ★ 刻意**不写 `romfs/` 里的 `manifest.json`**：那份清单在 SD 的**资源覆盖层**里，
//   运行期写它正是本项目历史上"写覆盖层 ⇒ 下次启动装载崩溃"的雷区（见 `AGENTS.md`）。
[[nodiscard]] bool ModMenuSetEnabled(const char* directory, bool enabled) noexcept;
[[nodiscard]] bool ModMenuSaveToggles() noexcept;

} // namespace isaac::runtime
