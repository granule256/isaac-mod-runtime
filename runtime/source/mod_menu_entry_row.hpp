#pragma once

// 在选择界面那一列里**多插一格（模组）**的纯算术：格子布局、每行的位移、光标落点、索引推进。
//
// ## 这一批（2026-09-22 晚）最重要的变化：**数字全部由工具算出来**
//
// 用户的原话是"你不能看看其他的行代码是这么写的，按它们的来写吗？为什么要自己一个个调？"。
// 顺着这句话查下去，得出了两条结论，这一批按它们重写了：
//
//   1. **那五行不是代码画的**，是 `gamemenu.anm2` 里五张手绘贴图（`Item1`~`Item5`）；
//   2. 于是我们这一行也应当是**一张贴图**，而"贴哪儿、多大、光标在哪儿"这些数字
//      应当**从该语言自己的美术里量出来**，不再手写。
//
// 具体做法见 `tools/gamemenu_mod_row.py`；它量出来的东西生成在
// `runtime/source/mod_row_generated.hpp`（八个语言各一套：行贴图 PCX 字节 + 布局常量）。
// 本文件只剩下**与数据无关的算术**（格子 ↔ 引擎行、光标帧、索引推进），
// 以及"按游戏语言码挑一套布局"。
//
// ## 量出来的事实底座（可复核，`tools/gamemenu_mod_row.py` 会重新生成并逐字节比对）
//
//   * 行图 `Item1..Item5`（layer 1..5）在 ANM2 里的框顶 = `YPosition`（pivot 是 `(0,0)`），
//     各语言略有差别（中文 `Item4`=138、基础版 140）；行图 128×48；
//   * 光标层 `Cursor`（layer 6）的帧数**逐语言不同**（中文 5 帧、基础版 6 帧、法语 6 帧），
//     帧的 `YPosition` 就是光标**中心**（pivot 是 `(16,16)`）；
//   * 纸的可用带 = 行图那几列里"每一列都还是纸"的纵向范围，实测八个语言都是 **36..213**
//     （英文那套的底是不透明背景、量不出来 ⇒ 退参考带，见工具里的 `measure_paper_bands`）；
//   * 引擎只认 **5** 项（`Menu_Game::Update` 里上界硬编码 4）⇒ 我们那一格靠"夹住引擎索引 +
//     自己驱动光标"实现；
//   * **法语那套原版自己就有一行**（`Item6`，画的就是 MODS，且五行的 Y 已经为它让好位）
//     ⇒ 那个语言位移全是 0、贴图直接用游戏自己的（布局里的 `vanillaRow`）。
//
// ## 排法：**照搬 PC 那六个绝对位置**（纵向与横向都搬，一个字都不算）
//
// 用户 2026-09-22 晚的原话是"你不要改了，先查清楚 pc 到底是如何处理的"。查清楚的结果是：
// **PC 不推导任何间距** —— 它在 `gamemenu.anm2` 里把六行写死成绝对坐标
// （英语/中文/日文/韩文/俄语都是 34/59/87/**模组 123**/150/177；德语那条"挑战"是 88 格高的
// 斜横幅、西班牙语第一行在 37），横向也各有各的框 x。所以生成器读的是
// **PC 版同一语言**的那份文件（`reference-pc/lang/<语言>/…`），把六个 `page_top` / `page_x`
// 与光标的六帧照搬下来，本文件只负责把它应用到引擎的图层上（`+0x4C` 是 Y、`+0x48` 是 X）。
//
// ⚠️ 被推翻的三条旧规则（留档，别再走一遍）：**六格等间距**、**按 PC 的字中心**、
//    **逐格链 PC 的白边** —— 三条都在"推导"间距，而 PC 没有可推导的规律（它的行框 128×48、
//    相邻只隔 25~35，本来就互相重叠）。推导还把我自己量字高的误差带进了位置里，
//    真机上就是用户看到的"这一列偏上""模组上下两行间距变大"。历史数值见 056 批存档。

#include <cstdint>

#include "mod_row_generated.hpp"

namespace isaac::runtime {

//: 这一列一共有几格（含我们插进去的那一格）。
inline constexpr std::uint32_t kMenuGameEntryCount = 6;
//: 我们那一格落在第几格（0 起）。**3 = CHALLENGES 与 STATS 之间**。
inline constexpr std::uint32_t kModEntrySlot = 3;
//: 引擎自己认的条目数（上界 4）。
inline constexpr std::uint32_t kMenuGameEngineEntryCount = 5;

static_assert(kModRowSlotCount == kMenuGameEntryCount,
              "生成的布局与这里的格子数不一致（重新跑 tools/gamemenu_mod_row.py）");
static_assert(kModRowEngineRowCount == kMenuGameEngineEntryCount,
              "生成的布局与这里的引擎行数不一致（重新跑 tools/gamemenu_mod_row.py）");

//: 行图在 ANM2 里的 layer id：`Item1` = 1（0 是 Main 背景）。
inline constexpr std::uint32_t kMenuGameFirstRowLayer = 1;
//: 光标层 id。
inline constexpr std::uint32_t kMenuGameCursorLayer = 6;

//: 图层的位置偏移是一个 `Vector2`：**`+0x48` 是 X、`+0x4C` 是 Y**。
//:
//: ★★ 这一条是**真机换来的**（2026-09-22 傍晚，第一次上卡）：我先把「下挪」写进了 `+0x48`，
//: 用户看到的现象是「**最后两格统计数据和选项偏到右侧了**」—— 正好证明 `+0x48` 是 X。
//: 为什么静态看不出来：`Menu_Game::Render` **自己只碰 `+0x48`**
//: （它对每日挑战那几层做 `s0=[layer+0x48]; s0+=15; [layer+0x48]=s0`，那是横向滑动），
//: 它从来没写过 Y —— 所以「Y 在哪」只能靠真机试出来。
inline constexpr std::uintptr_t kAnm2LayerOffsetXField = 0x48;
inline constexpr std::uintptr_t kAnm2LayerOffsetYField = 0x4C;
//: 图层的"可见"字节（`Menu_Game` 里 `strb w19, [layer, #0x7c]`）。
inline constexpr std::uintptr_t kAnm2LayerVisibleField = 0x7c;

//: 行图的高度（128×48 的 48）。
inline constexpr float kMenuGameRowHeight = 48.0F;

// ---------------------------------------------------------------------------
// 按游戏语言码挑一套布局
// ---------------------------------------------------------------------------

//: 挑布局：`code` 是 `Manager::GetLanguageCode()` 给的两字符码（`"zh"` / `"de"` / …）。
//: 八个语言都支持（`en/de/es/fr/jp/kr/ru/zh`）；**其它语言码（`it`/`pt`/`pl`…）用 `en` 那套** ——
//: 引擎那边也是这么办的：只有这八个有 `resources.<code>` 语言包，其余的走基础资源。
[[nodiscard]] inline const ModRowLayout* ModRowLayoutForLanguage(const char* code) noexcept {
    const ModRowLayout* fallback = &kModRowLayouts[0];
    for (std::uint32_t index = 0; index < kModRowLayoutCount; ++index) {
        const char* candidate = kModRowLayouts[index].language;
        if (candidate[0] == 'e' && candidate[1] == 'n') {
            fallback = &kModRowLayouts[index];  // 认不出来就用英文那套（引擎也是这么办的）
        }
        if (code != nullptr && code[0] == candidate[0] && code[1] == candidate[1]
            && candidate[2] == '\0') {
            return &kModRowLayouts[index];
        }
    }
    return fallback;
}

// ---------------------------------------------------------------------------
// 引擎索引：绝不越界
// ---------------------------------------------------------------------------

//: 第 `slot` 格的**引擎行号**（0..4）。我们那一格**借用引擎第 4 行**（索引 3 = STATS 原位），
//: 插点以下的格子顺延一位（第 5 格 = 引擎第 4 行 STATS、第 6 格 = 引擎第 5 行 OPTIONS）。
[[nodiscard]] constexpr std::uint32_t EngineRowForSlot(std::uint32_t slot) noexcept {
    if (slot >= kMenuGameEntryCount) {
        return kMenuGameEngineEntryCount;
    }
    if (slot == kModEntrySlot) {
        return kModEntrySlot;
    }
    return slot < kModEntrySlot ? slot : slot - 1;
}

//: 引擎索引该写成什么：**夹在 0..4**。引擎只认 5 项，越界有风险；
//: 我们的第 6 格（slot 5）在引擎看来"停在最后一项（OPTIONS）上"，光标位置由我们自己给。
[[nodiscard]] constexpr std::uint32_t EngineIndexClampedForSlot(std::uint32_t slot) noexcept {
    return slot < kMenuGameEngineEntryCount ? slot : kMenuGameEngineEntryCount - 1;
}

//: 上下键推进：`down` = 往下走。按格子数取模。
[[nodiscard]] constexpr std::uint32_t AdvanceSlot(std::uint32_t slot, bool down) noexcept {
    if (kMenuGameEntryCount == 0) {
        return 0;
    }
    const std::uint32_t current = slot < kMenuGameEntryCount ? slot : 0;
    return down ? (current + 1) % kMenuGameEntryCount
                : (current + kMenuGameEntryCount - 1) % kMenuGameEntryCount;
}

// ---------------------------------------------------------------------------
// 布局（全部取自生成的那一套）
// ---------------------------------------------------------------------------

//: 第 `engineRow` 行要挪多少（给探针用：它把这个值加到图层 `+0x4C` 上，画完再减回去）。
[[nodiscard]] constexpr float MenuGameRowShiftFor(const ModRowLayout& layout,
                                                 std::uint32_t engineRow) noexcept {
    return engineRow < kMenuGameEngineEntryCount ? layout.rowShiftY[engineRow] : 0.0F;
}

//: 第 `engineRow` 行要**横向**挪多少（给探针用：它把这个值加到图层 `+0x48` 上，画完再减回去）。
//:
//: ★ 2026-09-22 深夜补（用户："模组似乎偏左了一点"）：只搬 PC 的 Y、横向留本语言自己的框 x
//: 是不够的 —— 中文那样排出来"字左"是 185/187/192/**189**/195/199（模组比它上面的挑战还靠左
//: 3 格），而 PC 中文自己那一列是 183/184/187/**189**/196/199（模组在挑战右边 2 格）。
//: 两边的图集是同一块美术（每行"框内字左"逐行相等），差别只在 ANM2 里的框 x ⇒ 照搬 x 就对了。
[[nodiscard]] constexpr float MenuGameRowShiftXFor(const ModRowLayout& layout,
                                                   std::uint32_t engineRow) noexcept {
    return engineRow < kMenuGameEngineEntryCount ? layout.rowShiftX[engineRow] : 0.0F;
}

//: 第 `engineRow` 行挪完之后的框顶。
[[nodiscard]] constexpr float MenuGameRowTop(const ModRowLayout& layout,
                                            std::uint32_t engineRow) noexcept {
    return engineRow < kMenuGameEngineEntryCount
               ? layout.rowOriginalTop[engineRow] + layout.rowShiftY[engineRow]
               : 0.0F;
}

//: 第 `slot` 格的锚点（页面坐标 y）：引擎行 = 挪完之后的框顶，我们那一格 = 贴图顶。
[[nodiscard]] constexpr float MenuGameSlotTop(const ModRowLayout& layout,
                                             std::uint32_t slot) noexcept {
    return slot < kMenuGameEntryCount ? layout.slotTop[slot] : 0.0F;
}

//: 第 `slot` 格的横向锚点（页面坐标 x）：**就是 PC 的框 x**（横向照搬 PC）。
[[nodiscard]] constexpr float MenuGameSlotLeft(const ModRowLayout& layout,
                                               std::uint32_t slot) noexcept {
    return slot < kMenuGameEntryCount ? layout.slotLeft[slot] : 0.0F;
}

//: 第 `slot` 格的光标帧号（由生成器给出：我们插一行的语言是 `0,1,2,3,3,4`，
//: 原版自己就有六行的语言是 `0..5`）。
//:
//: ⚠️ 这里容易写错（第一版就写成"帧号 = 格子号"）：原版那五帧是按**它自己的五行**画的，
//: 而我们的六格是"把第 4 格换成模组、后面两格顺延" ⇒ 第 5、6 格（STATS/OPTIONS）对应的是
//: 原版第 **4、5** 帧，不是第 5、6 帧。写错的表现就是"光标比格子低一格"。
[[nodiscard]] constexpr std::uint32_t CursorFrameForSlot(const ModRowLayout& layout,
                                                        std::uint32_t slot) noexcept {
    if (slot >= kMenuGameEntryCount) {
        return 0;  // 非法格子 ⇒ 退第一帧（安全值，不是越界值）
    }
    const std::uint32_t frame = layout.cursorFrame[slot];
    return frame < kMenuGameEntryCount ? frame : 0;
}

//: 第 `slot` 格要加到光标层 `+0x4C` 上的量 = 目标 y − **该格所用帧**的原生 y。
//: 对引擎那五格，这个差值**必须等于该格对应那一行的位移**（行挪多少光标挪多少）—— 宿主门禁钉住。
[[nodiscard]] constexpr float CursorDeltaYForSlot(const ModRowLayout& layout,
                                                 std::uint32_t slot) noexcept {
    if (slot >= kMenuGameEntryCount) {
        return 0.0F;
    }
    const std::uint32_t frame = CursorFrameForSlot(layout, slot);
    return layout.cursorY[slot] - layout.cursorFrameY[frame];
}

}  // namespace isaac::runtime
