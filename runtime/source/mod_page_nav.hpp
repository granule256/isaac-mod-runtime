#pragma once

// 模组页（引擎状态 16）里**我们自己维护**的那点算术（2026-09-22 夜，批次 058）。
//
// ## 为什么这部分自己做，而不是调引擎的 `Menu_Mods::Update`
//
// 引擎的 `Menu_Mods::Update` 本来能做全套（上/下、确认、返回），但它**按确认时会往模组目录里
// 写/删一个 `disable.it`**（反汇编 0x4105D4 起：翻转条目 `+0x138` 的启用位 ⇒
// `FileManager::Exists` ⇒ `DeleteSaveFile` / `OpenSaveFileForWriting`）。
// 而卡上的模组目录就在 **romfs 覆盖层**里（`/atmosphere/contents/<title>/romfs/isaac_mods/mods/`）——
// 那正是本项目历史上"往覆盖层写东西 ⇒ 下次启动在装载阶段崩"的雷区（见 `AGENTS.md` 的
// 「设备取证纪律」与 `docs/问题与解决记录.md`）。
// ⇒ 纪律：**页面只借引擎的 `Render`**（含它自己调 `MenuManager::SetModsOffset` 的滚动），
// **输入与开关状态由我们自己维护**，清单（`manifest.json`）是唯一真值源、只在退出页面时写一次
// （用户 2026-09-22 裁定）。
//
// ## 这些数字从哪来（都可复核）
//
// * 字段偏移：`libzhl/functions/MenuMods.zhl`（REPENTOGON 对 PC 引擎逆向出来的结构定义）
//       `int SelectedElement : 0x0;  int HoldInputTimer : 0x4;  int State : 0x124;`
//   条目启用位 `+0x138` 见 `mod_page_entries.hpp`（同一套结构的另一段）。
// * 按住节奏：`Menu_Mods::Update` 与 `Menu_Game::Update` 的反汇编同形 ——
//   "松开时归零；按住超过 50 帧之后每 10 帧走一格"。
// * 状态号 16：见下面 `kModsPageState` 的注释（两条互相印证的证据）。

#include <cstdint>

namespace isaac::runtime {

//: 引擎状态机里"模组页"那一格。
//:
//: ★ 依据（2026-09-22 夜的反汇编取证，完整记录见 `docs/问题与解决记录.md` 续七十四）：
//: `MenuManager::SetModsOffset`（`0x3FF6F4`）—— 模组页滚动用的那个函数 —— 把目标写进
//: `MenuManager + 0x1AFF8C`；而引擎取"每个状态自己的位置"用的是
//: `MenuManager + 状态*8 + 0x1AFF08`（`MenuManager::Update` 里 `ldr w8,[x0,#0x38]` 之后
//: `this + w8*8 + 0x1aff08`）⇒ `0x1AFF8C` 正是**第 16 格**的 Y。
//: **交叉验证**：`SetOptionsOffset` 写 `0x1AFF5C` = 第 10 格，而"选项"在 Switch 的状态表里就是 10。
//: `MenuManager::Init`（`0x3FC898`）里也真的初始化了第 16 格（17 格连排，第 16 格在中间被插了一笔）。
//:
//: ⇒ **PC 上"选模组"就是切到状态 16**；Switch 版只把这一格从
//: `MenuManager::Update` 的分派表（0..15）与 `MenuManager::Render` 的页面清单里删了，
//: 页面代码（`Menu_Mods` 六个方法）、资源（`modsmenu.anm2` 与 PC 那份逐字节相同）全都还在。
constexpr std::uint32_t kModsPageState = 16;

//: 每个状态的"位置/滚动"槽：`MenuManager + 状态*8 + kMenuManagerStateSlotBase`
//:（每格两个 float：X、Y）。这两个常量把上面那条算术**变成门禁能核的东西**。
constexpr std::uintptr_t kMenuManagerStateSlotBase = 0x1AFF08;
constexpr std::uintptr_t kMenuManagerModsScrollY = 0x1AFF8C;

//: 第 `state` 个状态那一格的 Y 偏移（`SetModsOffset` 写的就是它）。
constexpr std::uintptr_t MenuManagerStateSlotYOffset(std::uint32_t state) noexcept {
    return kMenuManagerStateSlotBase + static_cast<std::uintptr_t>(state) * 8U + 4U;
}

//: `Menu_Mods` 页面对象里我们要读写的那三个字段。
constexpr std::uintptr_t kModsSelectedElementOffset = 0x0;
constexpr std::uintptr_t kModsHoldTimerOffset = 0x4;
constexpr std::uintptr_t kModsEditedOffset = 0x124;

//: 按住重复的节奏（与引擎一致）。
constexpr std::uint32_t kModPageHoldDelayFrames = 50;
constexpr std::uint32_t kModPageHoldRepeatEvery = 10;

//: 按住计时：按住 +1、松开归零（引擎的 `UpdateKeyPress` 就是这两句）。
constexpr std::uint32_t ModPageHoldNext(std::uint32_t holdFrames, bool held) noexcept {
    return held ? holdFrames + 1U : 0U;
}

//: 这一帧要不要因为"按住"再走一格。引擎的判断（`Menu_Mods::Update`，`0x4103xx` 那段）是
//: `hold == 0 || (hold >= 50 && hold % 10 == 0)` —— 刚按下的那一帧立刻走一格，
//: 之后要等过 50 帧、再每 10 帧一格。
constexpr bool ModPageHoldShouldMove(std::uint32_t holdFrames) noexcept {
    return holdFrames == 0U ||
           (holdFrames >= kModPageHoldDelayFrames &&
            (holdFrames % kModPageHoldRepeatEvery) == 0U);
}

//: 上/下走一格，在 `0..count-1` 之间**回环**（引擎原版就是回环：末项往下回第一项、首项往上回末项）。
//: `count == 0`（一个模组都没有）或当前值越界（表变短了）⇒ 一律答 0，**绝不算出越界的值**。
constexpr std::uint32_t ModPageAdvance(std::uint32_t selected, std::uint32_t count,
                                       bool down) noexcept {
    if (count == 0U || selected >= count) {
        return 0U;
    }
    if (down) {
        return (selected + 1U) % count;
    }
    return selected == 0U ? count - 1U : selected - 1U;
}

//: 翻转"启用"字节：引擎自己是 `*(unsigned char*)(条目 + 0x138) ^= 1`，这里**逐位照抄**
//: （不写成 `1 - x`：引擎对 0/1 之外的值也是异或，两边必须同形）。
constexpr std::uint32_t ModPageToggleEnabled(std::uint32_t enabled) noexcept {
    return (enabled ^ 1U) & 0xFFU;
}

//: 引擎状态是不是"模组页"。页面对象每帧要不要由我们驱动，就看这一条。
constexpr bool ModPageIsActive(std::uint32_t engineState) noexcept {
    return engineState == kModsPageState;
}

//: 退出页面时该不该把开关写回清单：**只有真改过才写**（用户 2026-09-22 裁定）。
constexpr bool ModPageShouldPersist(bool edited) noexcept {
    return edited;
}

//: 进页面那一刻，"某个键的上一帧状态"该锁成什么：**当前按着就当它已经按下过**。
//:
//: ★ 这条是 2026-09-22 深夜（批次 058）在自查时抓到的：进页面用的就是那个确认键（A），
//: 它此刻**还按着**，而上一帧状态是 0 ⇒ 页面第一帧的边沿判断会得出"刚按下"
//: ⇒ **刚进模组页就顺手把第一条模组的开关翻掉了**。锁上就没有这个问题。
constexpr std::uint32_t ModPageLatchedEdge(bool held) noexcept {
    return held ? 1U : 0U;
}

//: 进页面那一刻"按住计时"的初值：按着方向键进来就给 1（见 `ModPageHoldShouldMove`：
//: 计时为 1 时本帧不走），否则 0（下一帧真的按下时立刻就走一格）。
constexpr std::uint32_t ModPageHoldSeed(bool directionHeld) noexcept {
    return directionHeld ? 1U : 0U;
}

//: 引擎的"模组总开关"（`g_Manager + 0x36519`，一个字节）该置成什么。
//:
//: ★ 2026-09-22 深夜真机读数（批次 058 的第一次现场）定下来的：那个字节**当时是 0**，
//: 而 `Menu_Mods::Render` 在它为 0 时走的那条分支**只用一个颜色画所有行**
//: （反汇编 `0x4109xx` 段：为 0 的那一支完全不读条目自己的 `+0x138` 启用位），
//: 非 0 的那一支才"开着的行一种色、关掉的行另一种色"。
//: ⇒ 不置它，"按确认切换开关"在屏幕上**看不出来**（这正是批次 058 的验收判据之一）。
//: 置 1 与 PC 的语义一致：`Menu_Mods::Update` 里那一下 "按 0x17 键翻转这一位" 就是 PC 的
//: "启用模组"开关，而我们这份运行时**确实在加载模组**。
//: 只改内存，不碰任何文件（引擎自己那一下也只改内存；写 `disable.it` 是另一条路，我们不走）。
constexpr std::uint32_t kModsEnabledGateOn = 1;

} // namespace isaac::runtime
