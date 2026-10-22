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

// ---------------------------------------------------------------------------
// 视角偏转：**照引擎 `SetModsOffset @0x3FF6F4` 的公式**，但要**用 PC 口径的下标/条数**
// ---------------------------------------------------------------------------
//
// 引擎的公式（反汇编原文）：`选中项 < 5` ⇒ 不滚；`选中项 < 行数 − 3` ⇒ 滚 `选中项 − 4`；
// 否则 ⇒ 滚 `行数 − 7`（到底段）。
//
// ★★ 2026-09-27 真机实测（批次 170）：**直接让引擎自己调**（`modsRender` 之后补一次
// `SetModsOffset(选中项)`）**完全不会滚** —— 因为那条公式里的"行数"是从 `g_Manager+0x36800`
// 读的，而**那张表是我们造的、比 PC 多一行**（下标 0 = 控制台开关）：
//   * 我们的表 7 行（6 模组 + 控制台）⇒ 到底段 `7 − 7 = 0`，而中间段要求 `选中项 < 行数−3 = 4`
//     与首段 `选中项 ≥ 5` **互斥** ⇒ **中间段永远走不到** ⇒ 每一档都算出 0 ⇒ 一行都不滚；
//   * PC 的同名清单 6 行 ⇒ 到底段 `6 − 7 = −1` ⇒ 往下挪一行（用户看到的"PC 有偏转"）。
// ⇒ 所以我们要做的不是"另发明一套"，而是**把公式按 PC 口径求值**（模组序号 / 模组条数，
//   控制台那一行不算），再把结果写进引擎那一格 —— 结果与 PC 对同一份模组清单逐值一致。
inline constexpr std::uint32_t kModPageScrollStartRow = 5;
inline constexpr std::uint32_t kModPageScrollTailRows = 3;
inline constexpr std::uint32_t kModPageScrollEndRows = 7;
inline constexpr float kModPageRowStep = 25.0F;
//: 不滚动时状态 16 那一格的 Y（引擎在"选中项 < 5"时写的常数）。
inline constexpr float kModPageScrollBaseY = -336.0F;
//: `MenuManager + 0x0` = 引擎的"菜单还在动"标志（`SetModsOffset` 收尾把它置 1）。
inline constexpr std::uintptr_t kMenuManagerMovingFlagOffset = 0x0;

//: ★★ 该滚几行 —— **按我们自己纸里能看到的行数**算（2026-09-27 批次 173 定案）。
//:
//: 为什么不能照搬引擎那三个常数（`5` / `−3` / `−7`）：那是按 **PC 的可见行数**定的，
//: 而 **NS 这版把画布裁掉了一圈且不缩放**（可见 426×240 ÷ 画布 480×270 ⇒ 所有东西看上去大 1.127 倍）
//: ⇒ 同一张纸在 NS 上**露出来的行数比 PC 少**。用户实测：纸比 PC 大、显示的行数更少
//: （这是移植的裁切方式，不是我们改的 —— 见 `docs/问题与解决记录.md` 续七十五）。
//: ⇒ 于是那条按"5 行"写的公式在我们这儿要么滚得太晚、要么（行数少时）**退化成完全不滚**：
//:   我们的表 7 行时，中间段条件 `选中项 < 行数−3 = 4` 与首段 `选中项 ≥ 5` **互斥** ⇒ 只有到底段 `7−7 = 0`。
//: ⇒ 照**我们自己的窗口**来：`滚几行 = clamp(选中项 − (可见行数 − 1), 0, 模组条数 − 可见行数)`。
//:   **这不是"另发明一套"**：引擎的中间段本来就是同一条式子（它的"可见行数"是 5）。
//: ★ 位置不再参与（批次 169 起位置只在 `Init` 时定一次、之后不写），所以这里只算滚动量，没有反馈回路。
inline constexpr std::uint32_t kModPageVisibleRows = 5;

[[nodiscard]] constexpr std::uint32_t ModPageScrollRows(std::uint32_t selected,
                                                        std::uint32_t modCount) noexcept {
    if (modCount <= kModPageVisibleRows || selected < kModPageVisibleRows) {
        return 0;
    }
    const std::uint32_t maximum = modCount - kModPageVisibleRows;
    const std::uint32_t rows = selected - (kModPageVisibleRows - 1);
    return rows < maximum ? rows : maximum;
}

//: 滚 `scrollRows` 行时状态 16 那一格的目标 Y。
[[nodiscard]] constexpr float ModPageScrollSlotY(std::int32_t scrollRows) noexcept {
    return kModPageScrollBaseY - kModPageRowStep * static_cast<float>(scrollRows);
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
