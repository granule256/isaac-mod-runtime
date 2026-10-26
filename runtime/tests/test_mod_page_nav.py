"""模组页（引擎状态 16）里"我们自己维护"的那点算术：状态号、按住节奏、回环、开关翻转。

判据都在宿主上跑（纯常量表达式 + 几个 constexpr 函数）。为什么值得单独钉：

真机一轮很贵（构建 → 上卡 → 用户退游戏进游戏 → 读数），而这几条错法的**现象都很难分辨**：

* 状态号错一位 ⇒ 切过去是**另一个页面**（甚至什么都不显示），看起来像"没接上"；
* 按住节奏错 ⇒ 上/下"飞"或者"按着不动"，看起来像"输入没接上"；
* 回环/越界算错 ⇒ 一个模组都没有时算出越界项 ⇒ 引擎拿它去读表**越界**（本项目一贯的硬线）。

★ 其中最重要的是**"状态 16"这件事必须能被验算**，而不是靠"我记得"：
`kModsPageState`、`kMenuManagerStateSlotBase`、`kMenuManagerModsScrollY` 三个常数放在
`mod_page_nav.hpp` 里，这里用第 2 组断言把它们的算术关系钉死 —— 谁把状态号改成别的值，
`SetModsOffset` 写的那个槽就对不上了，门禁立刻红。
（依据：`MenuManager::SetModsOffset @0x3FF6F4` 写 `+0x1AFF8C`；`MenuManager::Update` 取
 `MenuManager + 状态*8 + 0x1AFF08`；`SetOptionsOffset` 写 `+0x1AFF5C` = 第 10 格 = "选项"。）
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

HARNESS = r'''
#include "mod_page_nav.hpp"
#include "mod_menu_entry_row.hpp"  // 往返时"引擎索引 ↔ 我们的格子"的换算在那边

#include <cstdio>

using namespace isaac::runtime;

namespace {
int failures = 0;
void Check(bool condition, const char* label) {
    if (!condition) { std::printf("FAIL %s\n", label); ++failures; }
}
void CheckU(std::uint32_t actual, std::uint32_t expected, const char* label) {
    if (actual != expected) {
        std::printf("FAIL %s：实际 %u 期望 %u\n", label, actual, expected);
        ++failures;
    }
}
}  // namespace

int main() {
    // ---- 1) 状态号与"字段偏移"（后者来自 REPENTOGON 的 MenuMods.zhl，是可复核的第三方取证）----
    CheckU(kModsPageState, 16, "模组页 = 引擎状态 16（PC 上选模组就是切到它）");
    CheckU(kModsSelectedElementOffset, 0x0, "SelectedElement 在页面对象 +0x0");
    CheckU(kModsHoldTimerOffset, 0x4, "HoldInputTimer 在 +0x4");
    CheckU(kModsEditedOffset, 0x168, "Switch修改标记在 +0x168，不能写入ANM2内部");
    CheckU(kModsSelectedElementOffset + 4, kModsHoldTimerOffset,
           "两个字段首尾相接（抄错偏移最容易在这里露馅）");

    // ---- 2) ★ 状态号的**算术自证**：SetModsOffset 写的那个槽必须正好是"第 16 格的 Y" ----
    CheckU(static_cast<std::uint32_t>(MenuManagerStateSlotYOffset(kModsPageState)),
           static_cast<std::uint32_t>(kMenuManagerModsScrollY),
           "SetModsOffset 写的 +0x1AFF8C 必须等于 `状态 16 那一格的 Y`");
    CheckU(static_cast<std::uint32_t>(MenuManagerStateSlotYOffset(10)), 0x1AFF5CU,
           "同一套算术要能算出「选项」那一格（状态 10 ⇒ +0x1AFF5C，SetOptionsOffset 写的正是它）");
    CheckU(static_cast<std::uint32_t>(MenuManagerStateSlotYOffset(0)),
           static_cast<std::uint32_t>(kMenuManagerStateSlotBase) + 4U,
           "第 0 格从表的起点开始（X 在 +0，Y 在 +4）");
    CheckU(static_cast<std::uint32_t>(kMenuManagerModsScrollY) % 8, 4,
           "每一格是 8 字节（X、Y 各 4），所以 Y 永远落在 8 的倍数 +4 上");

    // ---- 3) 按住节奏：刚按下立刻走一格，之后 50 帧、再每 10 帧一格 ----
    Check(ModPageHoldShouldMove(0), "刚按下的那一帧就走（不是等 50 帧）");
    for (std::uint32_t hold = 1; hold < 50; ++hold) {
        if (ModPageHoldShouldMove(hold)) {
            std::printf("FAIL 按住第 %u 帧不该走（要不就成了连发）\n", hold);
            ++failures;
        }
    }
    Check(ModPageHoldShouldMove(50), "第 50 帧走一格");
    Check(!ModPageHoldShouldMove(51), "第 51 帧不走");
    Check(ModPageHoldShouldMove(60), "第 60 帧又走一格（每 10 帧一次）");
    Check(ModPageHoldShouldMove(1000), "长按仍然是每 10 帧一格");

    // ---- 4) 按住计时：按住 +1、松开归零 ----
    CheckU(ModPageHoldNext(0, true), 1, "按住一次 ⇒ 1");
    CheckU(ModPageHoldNext(49, true), 50, "连按 ⇒ 逐帧累加");
    CheckU(ModPageHoldNext(123, false), 0, "一松开就归零");

    // ---- 5) 上/下回环（引擎原版就是回环）----
    CheckU(ModPageAdvance(0, 5, true), 1, "往下走一格");
    CheckU(ModPageAdvance(4, 5, true), 0, "末项往下 ⇒ 回第一项");
    CheckU(ModPageAdvance(0, 5, false), 4, "首项往上 ⇒ 回末项");
    CheckU(ModPageAdvance(2, 5, false), 1, "往上走一格");
    CheckU(ModPageAdvance(0, 1, true), 0, "只有一个模组时原地不动");
    CheckU(ModPageAdvance(0, 1, false), 0, "只有一个模组时往上也原地不动");
    CheckU(ModPageAdvance(0, 0, true), 0, "一个模组都没有 ⇒ 0（绝不算出越界值）");
    CheckU(ModPageAdvance(7, 5, true), 0, "当前值越界（表变短）⇒ 回到第一项");
    for (std::uint32_t count = 1; count <= 8; ++count) {
        for (std::uint32_t selected = 0; selected < count; ++selected) {
            const std::uint32_t down = ModPageAdvance(selected, count, true);
            const std::uint32_t up = ModPageAdvance(selected, count, false);
            if (down >= count || up >= count) {
                std::printf("FAIL count=%u selected=%u ⇒ 算出越界值 (%u, %u)\n", count, selected,
                            down, up);
                ++failures;
            }
        }
    }

    // ---- 6) 开关翻转：与引擎同形的异或 ----
    CheckU(ModPageToggleEnabled(0), 1, "关着 ⇒ 开");
    CheckU(ModPageToggleEnabled(1), 0, "开着 ⇒ 关");
    CheckU(ModPageToggleEnabled(0xFF), 0xFE, "非 0/1 的值也照异或（与引擎同形，不自己发明语义）");
    CheckU(ModPageToggleEnabled(ModPageToggleEnabled(1)), 1, "翻两次回到原样");

    // ---- 7) 门控与"该不该写清单" ----
    Check(ModPageIsActive(16), "状态 16 ⇒ 页面归我们驱动");
    Check(!ModPageIsActive(3), "状态 3（选择界面）⇒ 不驱动模组页");
    Check(!ModPageIsActive(1), "状态 1（标题）⇒ 不驱动模组页");
    Check(!ModPageShouldPersist(false), "没改过就不写清单（退出时只写一次，没改就不写）");
    Check(ModPageShouldPersist(true), "改过就写");

    // ---- 8) ★ 进页面那一刻的"锁边沿 / 锁计时"（批次 058 自查抓到的那条）----
    // 进页面用的就是那个确认键（A），它此刻还按着：不锁的话页面第一帧会把它当成一次新按下，
    // **刚进模组页就把第一条模组的开关翻掉**。
    CheckU(ModPageLatchedEdge(true), 1, "按着进来的键 ⇒ 锁成「已按下」（第一帧不再算边沿）");
    CheckU(ModPageLatchedEdge(false), 0, "没按的键 ⇒ 锁成 0（该按的时候照常触发）");
    CheckU(ModPageHoldSeed(true), 1, "按着方向键进来 ⇒ 计时从 1 起");
    CheckU(ModPageHoldSeed(false), 0, "没按方向键 ⇒ 计时从 0 起（下一帧真按下会立刻走一格）");
    Check(!ModPageHoldShouldMove(ModPageHoldSeed(true)),
          "★ 按着方向键进来时第一帧**不许**走一格（否则一进页面就跳一条）");
    Check(ModPageHoldShouldMove(ModPageHoldSeed(false)),
          "没按方向键进来时，第一帧若真按下应当立刻走一格（手感不能变钝）");

    // ---- 9) ★ 往返：从模组页回来时光标必须回到**我们那一格** ----
    // 这里钉的是那条"很容易顺手写错"的换算：我们那一格写回给引擎的索引就是 3
    // （EngineIndexClampedForSlot(3) == 3），而"引擎索引 → 我们的格子"的换算是
    // "≥ 落点就 +1"（因为插进去的那一格占了引擎原来的第 4 格）
    // ⇒ 拿引擎索引 3 去换算会得到**第 5 格（统计数据）**，光标就跑到隔壁了。
    // 结论：往返时**不能走那条换算**，要直接回到落点。
    CheckU(EngineIndexClampedForSlot(kModEntrySlot), kModEntrySlot,
           "我们那一格写回给引擎的索引就是落点本身（3）");
    CheckU(EngineRowForSlot(kModEntrySlot), kModEntrySlot, "落点对应的引擎行号也是 3");
    {
        const std::uint32_t engineIndex = 3;
        const std::uint32_t naive = engineIndex < kModEntrySlot ? engineIndex : engineIndex + 1;
        CheckU(naive, kModEntrySlot + 1,
               "★ 拿引擎索引去换算会落到第 5 格（这正是往返后光标跑掉的原因）");
        Check(naive != kModEntrySlot, "所以往返必须直接回到落点，不能走这条换算");
    }

    // ---- 10) ★★ 写回给引擎的必须是**行号**（`EngineRowForSlot`），不是"格子号夹一下" ----
    // 这条是 2026-09-23 真机反馈逼出来的（"统计和选项按了都是设置"）：
    // 引擎的确认跳表按**它的行号**查（行 3 = 统计 ⇒ SetState(9)；行 4 = 选项 ⇒ SetState(10)），
    // 而我们那一列插过一格 ⇒ 视觉上的"统计数据"（我们的第 4 格）在引擎那里**必须是行 3**。
    // 上一版用的是 `EngineIndexClampedForSlot`（把格子号夹到 0..4）⇒ 第 4 格写成 4
    // ⇒ 引擎以为选中的是"选项" ⇒ "统计按了进设置"。
    CheckU(EngineRowForSlot(4), 3, "★ 视觉上的「统计数据」必须写成引擎的第 4 行（索引 3）");
    CheckU(EngineIndexClampedForSlot(4), 4,
           "反例：用「夹一下」的映射会把第 4 格写成 4 = 引擎的「选项」（这就是那个 bug）");
    Check(EngineRowForSlot(4) != EngineIndexClampedForSlot(4),
          "★ 两种映射在「我们那一格之后」必须不同 —— 谁把它们当成一回事，统计就会变成设置");
    CheckU(EngineRowForSlot(5), 4, "视觉上的「选项」写成引擎的最后一行（索引 4）");
    CheckU(EngineIndexClampedForSlot(5), 4, "第 6 格夹回 4（两种映射在这一格恰好一致）");
    for (std::uint32_t slot = 0; slot < kMenuGameEntryCount; ++slot) {
        if (EngineRowForSlot(slot) >= kMenuGameEngineEntryCount) {
            std::printf("FAIL 第 %u 格算出的引擎行号越界\n", slot);
            ++failures;
        }
    }

    if (failures != 0) { std::printf("MOD_PAGE_NAV_CHECKS_FAILED %d\n", failures); return 1; }
    std::printf("MOD_PAGE_NAV_CHECKS_PASSED\n");
    return 0;
}
'''


class ModPageNavTests(unittest.TestCase):
    def test_mods_page_arithmetic_on_host(self):
        compiler = next((shutil.which(c) for c in ("c++", "clang++", "g++")
                         if shutil.which(c)), None)
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-mod-page-nav-") as directory:
            workdir = Path(directory)
            source = workdir / "harness.cpp"
            source.write_text(HARNESS.lstrip(), encoding="utf-8")
            binary = workdir / "harness"
            build = subprocess.run(
                [compiler, "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE),
                 str(source), "-o", str(binary)],
                text=True, capture_output=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("MOD_PAGE_NAV_CHECKS_PASSED", run.stdout)


if __name__ == "__main__":
    unittest.main()
