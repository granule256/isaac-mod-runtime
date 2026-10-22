"""选择界面那一列的"多插一格"算术：格子布局、每行的位移、光标落点、**整列必须在纸里**。

判据都在宿主上跑（纯常量表达式 + 几个 constexpr 函数）。为什么值得单独钉：
真机一轮很贵，而这里每一条错法都很难从现象上看出来 ——
"光标比格子低一格""某一行没跟着挪""引擎索引越界到 5"这三种，**屏幕上看起来都只是"有点不对"**，
查起来却要一轮又一轮。

★★ 这一版（048）最重要的是**把"纸的边界"也钉进来**：046/047 那两批就是栽在这里 ——
把 STATS/OPTIONS 整体下挪 33，真机上把 OPTIONS 挤出了纸外。现在纸的上/下沿、每行贴图里
"可见内容"的相对范围都是**量出来的常量**，门禁逐格核对：
   * 六格的内容都落在纸内；
   * 相邻两格的内容不重叠；
   * 前五格的位移与光标位移**一致**（行挪多少，光标就挪多少 —— 这条自洽性一破就是"光标错位"）。
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"

HARNESS = r'''
#include "mod_menu_entry_row.hpp"

#include <cstdio>
#include <cstring>

using namespace isaac::runtime;

namespace {
int failures = 0;
void Check(bool condition, const char* label) {
    if (!condition) { std::printf("FAIL %s\n", label); ++failures; }
}
void CheckF(float actual, float expected, float tolerance, const char* label) {
    const float delta = actual > expected ? actual - expected : expected - actual;
    if (delta > tolerance) {
        std::printf("FAIL %s：实际 %.2f 期望 %.2f（容差 %.2f）\n", label,
                    static_cast<double>(actual), static_cast<double>(expected),
                    static_cast<double>(tolerance));
        ++failures;
    }
}
//: 纸的"实心带"是量出来的（上沿从透明渐入、下沿是阴影 ⇒ 取保守值 36..213）。
//: 判"过没过界"再放宽 `kPaperSlack`：实测纸的自然边界在 25..222（上半是渐入的软边、
//: 下半是画在背景上的阴影）⇒ 落在这一圈里仍然是"在纸上"，只是压在边上。
//: ★ 但**排布**仍然是照实心带算的（我们那张贴图必须落在实心带里，不放宽）。
constexpr float kPaperSlack = 8.0F;

void CheckInsidePaper(float top, float bottom, float paperTop, float paperBottom,
                      const char* what) {
    if (top < paperTop - kPaperSlack) {
        std::printf("FAIL %s：顶 %.1f 跑到纸上面（纸沿 %.1f）\n", what,
                    static_cast<double>(top), static_cast<double>(paperTop));
        ++failures;
    }
    if (bottom > paperBottom + kPaperSlack) {
        std::printf("FAIL %s：底 %.1f 跑到纸下面（纸沿 %.1f）\n", what,
                    static_cast<double>(bottom), static_cast<double>(paperBottom));
        ++failures;
    }
}
}  // namespace

int main() {
    // ---- 1) 格子数：原版本来是 6 格，Switch 版删了一格 ⇒ 我们插回一格后还是 6 ----
    Check(kMenuGameEntryCount == 6, "含我们那一格应当是 6 格");
    Check(kMenuGameEngineEntryCount == 5, "引擎自己只认 5 项（上界硬编码 4）");
    Check(kModEntrySlot == 3, "落点：第 4 格（CHALLENGES 与 STATS 之间）");
    Check(kModEntrySlot < kMenuGameEntryCount, "落点必须在格子里");
    Check(kModRowLayoutCount == 8, "八个语言各一套布局");

    // ---- 2) 按语言码挑布局：认得出就用自己那套，认不出用英文那套 ----
    Check(std::strcmp(ModRowLayoutForLanguage("zh")->language, "zh") == 0, "zh 挑到中文那套");
    Check(std::strcmp(ModRowLayoutForLanguage("fr")->language, "fr") == 0, "fr 挑到法语那套");
    Check(std::strcmp(ModRowLayoutForLanguage("en")->language, "en") == 0, "en 挑到英文那套");
    Check(std::strcmp(ModRowLayoutForLanguage("it")->language, "en") == 0,
          "没有语言包的语言码（it/pt/pl…）用英文那套（引擎也是这么办的）");
    Check(std::strcmp(ModRowLayoutForLanguage(nullptr)->language, "en") == 0, "空指针兜底用英文");
    Check(std::strcmp(ModRowLayoutForLanguage("")->language, "en") == 0, "空串兜底用英文");

    // ---- 3) 逐语言核对生成出来的那一套（数字全部来自工具，门禁逐条核性质）----
    for (std::uint32_t index = 0; index < kModRowLayoutCount; ++index) {
        const ModRowLayout& layout = kModRowLayouts[index];
        const char* language = layout.language;

        // 3a) 我们那张贴图：尺寸合理、字的位置合理、字落在纸里
        // 贴图 = 那张画布（我们自己排的是 160×48；法语那套直接用原版那一行 80×39）；
        // 字必须落在画布里（`inkTop + 字高 ≤ 画布高`，用像素下标口径闭环）。
        if (layout.sprite.width < 40 || layout.sprite.height < 20 ||
            layout.sprite.inkTop < 0.0F || layout.sprite.inkLeft < 0.0F ||
            layout.sprite.inkBottom >= static_cast<float>(layout.sprite.height) ||
            layout.sprite.inkTop >= layout.sprite.inkBottom) {
            std::printf("FAIL %s：贴图尺寸/字位不合理（%ux%u，字顶 %.1f）\n", language,
                        layout.sprite.width, layout.sprite.height,
                        static_cast<double>(layout.sprite.inkTop));
            ++failures;
        }
        Check(layout.sprite.pcxBytes > 100, "贴图字节数不能小得像个空图");
        // 3a2) 那支笔的两个手感（用户两次指出的"字是正的""仍然很大"就在这里）：
        //      字的**转正后字高** 16..26；那支笔的斜度与"我们那张图实际转了多少"都为负。
        if (!(layout.glyphHeight >= 16.0F && layout.glyphHeight <= 26.0F)) {
            std::printf("FAIL %s：字高 %.1f 不像那支笔写的（应 16..26）\n", language,
                        static_cast<double>(layout.glyphHeight));
            ++failures;
        }
        if (layout.vanillaRow == 0 && !(layout.slant < -0.05F)) {
            std::printf("FAIL %s：那支笔的斜度 %.3f 应当明显为负\n", language,
                        static_cast<double>(layout.slant));
            ++failures;
        }
        const float inkTop = layout.spriteY + layout.sprite.inkTop;
        const float inkBottom = inkTop + static_cast<float>(layout.sprite.height) - 1.0F;
        // ★ 我们那一行是**我们摆的** ⇒ 严格判：必须落在实心纸带里（不放宽）。
        if (inkTop < layout.paperTop || inkBottom > layout.paperBottom) {
            std::printf("FAIL %s：我们那行字 %.1f..%.1f 不在实心纸带 %.1f..%.1f 里\n", language,
                        static_cast<double>(inkTop), static_cast<double>(inkBottom),
                        static_cast<double>(layout.paperTop),
                        static_cast<double>(layout.paperBottom));
            ++failures;
        }

        // 3b) 六格的锚点自上而下、且都在纸里（最后一行按整行高度算）
        for (std::uint32_t slot = 1; slot < kMenuGameEntryCount; ++slot) {
            if (!(MenuGameSlotTop(layout, slot) > MenuGameSlotTop(layout, slot - 1))) {
                std::printf("FAIL %s：第 %u 格没有排在第 %u 格下面\n", language, slot, slot - 1);
                ++failures;
            }
        }
        // 3b1) ★ 横向：五行的框 x **挪完必须正好落在 PC 的框上**（`slotLeft`）。
        //      判据的意义：这两条数一次算错（少加、错位、忘搬）在这里就红，而不是等上真机看
        //      "模组怎么偏左了"。实测踩过一次：生成器里推导式的变量名写错，前三行的目标 x
        //      全取成了最后一行的框（生成表本身看不出来，只有这条判据能兜住）。
        for (std::uint32_t row = 0; row < kMenuGameEngineEntryCount; ++row) {
            const std::uint32_t slot = row < kModEntrySlot ? row : row + 1;
            const float moved = layout.rowOriginalLeft[row] + MenuGameRowShiftXFor(layout, row);
            CheckF(moved, MenuGameSlotLeft(layout, slot), 0.01F, language);
        }
        // 3b2) 每一行的**字**都要落在纸里（行框 48 高，字只有 ~30 ⇒ 不能拿"框"去判）。
        //      法语那套的五行是**原版自己**摆的（且原版自己就压着纸的下沿 4 格）⇒ 不判它。
        if (layout.vanillaRow == 0) {
            for (std::uint32_t row = 0; row < kMenuGameEngineEntryCount; ++row) {
                const float rowTop = MenuGameRowTop(layout, row);
                CheckInsidePaper(rowTop + layout.rowInkTop[row], rowTop + layout.rowInkBottom[row],
                                 layout.paperTop, layout.paperBottom, language);
            }
        }

        // 3c) 光标：引擎那几格"行挪多少光标挪多少"（自洽性一破就是"光标指着别人那一行"）
        for (std::uint32_t slot = 0; slot < kMenuGameEntryCount; ++slot) {
            const std::uint32_t frame = CursorFrameForSlot(layout, slot);
            if (frame >= kMenuGameEntryCount) {
                std::printf("FAIL %s：第 %u 格算出的光标帧 %u 越界\n", language, slot, frame);
                ++failures;
            }
            if (slot == kModEntrySlot) {
                continue;
            }
            // 光标判据（2026-09-22 晚改）：行按 **PC 的字中心**摆、光标直接取 **PC 的六帧**
            // ⇒ 两者不再逐值相等；要判的是"光标落在它那一行的字上"。
            const std::uint32_t index = EngineRowForSlot(slot);
            const float inkTop = MenuGameRowTop(layout, index) + layout.rowInkTop[index];
            const float inkBottom = MenuGameRowTop(layout, index) + layout.rowInkBottom[index];
            if (layout.cursorY[slot] < inkTop - 8.0F || layout.cursorY[slot] > inkBottom + 8.0F) {
                std::printf("FAIL %s：第 %u 格的光标 %.1f 没落在那一行的字（%.1f..%.1f）上\n",
                            language, slot, static_cast<double>(layout.cursorY[slot]),
                            static_cast<double>(inkTop), static_cast<double>(inkBottom));
                ++failures;
            }
            if (layout.cursorY[slot] < layout.paperTop - 8.0F ||
                layout.cursorY[slot] > layout.paperBottom + 8.0F) {
                std::printf("FAIL %s：第 %u 格的光标 y=%.1f 离开了纸（%.1f..%.1f）\n", language,
                            slot, static_cast<double>(layout.cursorY[slot]),
                            static_cast<double>(layout.paperTop),
                            static_cast<double>(layout.paperBottom));
                ++failures;
            }
        }

        // 3d) 引擎索引**绝不越界**：第 6 格也要夹回 4
        for (std::uint32_t slot = 0; slot < kMenuGameEntryCount; ++slot) {
            if (EngineIndexClampedForSlot(slot) >= kMenuGameEngineEntryCount) {
                std::printf("FAIL %s：第 %u 格算出的引擎索引越界\n", language, slot);
                ++failures;
            }
        }

        // 3e) 法语那种"原版自己就有一行"的：五行一动不动、六格 ↔ 六帧一一对应
        if (layout.vanillaRow != 0) {
            for (std::uint32_t row = 0; row < kMenuGameEngineEntryCount; ++row) {
                CheckF(MenuGameRowShiftFor(layout, row), 0.0F, 0.0F, language);
                CheckF(MenuGameRowShiftXFor(layout, row), 0.0F, 0.0F, language);
            }
            for (std::uint32_t slot = 0; slot < kMenuGameEntryCount; ++slot) {
                if (CursorFrameForSlot(layout, slot) != slot) {
                    std::printf("FAIL %s：原版六行应当一格一帧\n", language);
                    ++failures;
                }
            }
        }
    }

    // ---- 4) 与语言无关的那几条算术 ----
    Check(kMenuGameFirstRowLayer == 1 && kMenuGameCursorLayer == 6, "图层号（Item1=1、Cursor=6）");
    Check(kAnm2LayerOffsetXField == 0x48 && kAnm2LayerOffsetYField == 0x4c,
          "图层偏移：+0x48 是 X、+0x4C 是 Y（真机换来的）");
    Check(EngineIndexClampedForSlot(0) == 0 && EngineIndexClampedForSlot(4) == 4,
          "前五格与引擎索引一一对应");
    Check(EngineIndexClampedForSlot(5) == 4, "第 6 格夹回 4（让引擎停在最后一格上）");
    Check(EngineRowForSlot(0) == 0 && EngineRowForSlot(2) == 2, "格子 → 引擎行号（插点以上）");
    Check(EngineRowForSlot(4) == 3 && EngineRowForSlot(5) == 4, "格子 → 引擎行号（插点以下错开）");
    Check(EngineRowForSlot(kModEntrySlot) == 3, "我们那一格借用引擎第 4 行");
    Check(EngineRowForSlot(6) == kMenuGameEngineEntryCount, "越界返回非法值（调用方要判）");
    Check(AdvanceSlot(0, true) == 1, "往下走一格");
    Check(AdvanceSlot(5, true) == 0, "最后一格往下 ⇒ 回环到第 1 格");
    Check(AdvanceSlot(0, false) == 5, "第 1 格往上 ⇒ 回环到最后一格");
    Check(AdvanceSlot(3, true) == 4 && AdvanceSlot(3, false) == 2, "第 4 格（我们的）上下各走一格");
    Check(AdvanceSlot(99, true) == 1, "越界的当前值按第 1 格算（不许算出越界结果）");

    // ---- 5) 引擎说"继续游戏不可选"时，导航必须跳过它（批次 159）------------------
    //
    // 这一条对应一条**真机 bug**（2026-09-27）：没有可继续的局时，引擎把"继续游戏"那一行
    // 画成灰帧、并在它自己的导航里跳过它（`Menu_Game::Update` 读 `Manager+0x2B688` 两个字节，
    // 两个都为 0 就跳过 index 1、还会把停在 1 上的选中项拨回 0）。而这一列是**我们**驱动光标的
    // ⇒ 不照抄这条规则，光标就能停在灰项上；按下确认时引擎读到的正是我们每帧写回去的行号 1
    // ⇒ 走"载入存档"那条路 ⇒ 没有存档 ⇒ **进局即死**。
    Check(kContinueEngineRow == 1, "引擎那 5 项里第 1 项 = 继续游戏");
    Check(!SlotSelectableByEngine(kContinueEngineRow, false), "引擎说不可选时，第 1 格不可选");
    Check(SlotSelectableByEngine(kContinueEngineRow, true), "引擎说可选时，第 1 格可选");
    Check(SlotSelectableByEngine(kModEntrySlot, false), "我们那一格不受它影响");
    Check(SlotSelectableByEngine(0, false) && SlotSelectableByEngine(2, false),
          "其余格子不受它影响（引擎只对 index 1 有这条判断）");
    Check(AdvanceSlotSkipping(0, true, false) == 2, "不可选：从新游戏往下 ⇒ 直接到挑战（跳 1）");
    Check(AdvanceSlotSkipping(2, false, false) == 0, "不可选：从挑战往上 ⇒ 直接到新游戏（跳 1）");
    Check(AdvanceSlotSkipping(0, true, true) == 1, "可选：往下正常到继续游戏");
    Check(AdvanceSlotSkipping(1, false, true) == 0, "可选：往上正常回新游戏");
    Check(AdvanceSlotSkipping(1, true, true) == 2, "可选：往下正常到挑战");
    {
        // 整列绕两圈都不许停在不可选的那一格上（这条是"光标停在灰项上"的直接判据）。
        std::uint32_t walk = 0;
        for (std::uint32_t step = 0; step < kMenuGameEntryCount * 2; ++step) {
            walk = AdvanceSlotSkipping(walk, true, false);
            Check(walk != kContinueEngineRow, "不可选时整列绕圈都不许停在继续游戏上");
        }
        walk = 0;
        for (std::uint32_t step = 0; step < kMenuGameEntryCount * 2; ++step) {
            walk = AdvanceSlotSkipping(walk, false, false);
            Check(walk != kContinueEngineRow, "不可选时反向绕圈也不许停在继续游戏上");
        }
    }
    // 写回给引擎的行号：不可选时**绝不为 1**（引擎的确认分支读的就是它）。
    Check(GuardContinueRowForWrite(kContinueEngineRow, false) != kContinueEngineRow,
          "不可选时写回的行号不能是 1（否则引擎会去载入存档）");
    Check(GuardContinueRowForWrite(kContinueEngineRow, true) == kContinueEngineRow,
          "可选时写回的行号仍是 1（正常的「继续游戏」不许被这条修复挡住）");
    Check(GuardContinueRowForWrite(EngineRowForSlot(kModEntrySlot), false) == 3
              && GuardContinueRowForWrite(EngineRowForSlot(kModEntrySlot), true) == 3,
          "我们那一格写回的行号与这条规则无关（恒 3）");
    for (std::uint32_t slot = 0; slot < kMenuGameEntryCount; ++slot) {
        const std::uint32_t written = GuardContinueRowForWrite(EngineRowForSlot(slot), false);
        Check(written < kMenuGameEngineEntryCount, "写回给引擎的行号必须夹在 0..4");
        Check(written != kContinueEngineRow || slot == kContinueEngineRow,
              "只有「继续游戏」那一格才可能写回 1");
    }

    if (failures != 0) { std::printf("MOD_MENU_ENTRY_ROW_CHECKS_FAILED %d\n", failures); return 1; }
    std::printf("MOD_MENU_ENTRY_ROW_CHECKS_PASSED\n");
    return 0;
}
'''


class ModMenuEntryRowTests(unittest.TestCase):
    def test_layout_arithmetic_on_host(self):
        compiler = next((shutil.which(c) for c in ("c++", "clang++", "g++")
                         if shutil.which(c)), None)
        if compiler is None:
            self.skipTest("宿主机没有 C++ 编译器")
        with tempfile.TemporaryDirectory(prefix="isaac-mod-menu-entry-row-") as directory:
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
            self.assertIn("MOD_MENU_ENTRY_ROW_CHECKS_PASSED", run.stdout)

    def test_continue_skip_is_actually_wired_into_the_update(self):
        """算术对了还不够：**调用点必须真的用上它**（批次 159）。

        为什么单独钉：这一批的错法是"头文件里加了一条跳过规则、但 `ModRowUpdate` 还在用旧那条"
        —— 编译得过、宿主门禁全绿，而真机上光标照样能停在灰掉的"继续游戏"上。
        所以这里按**文本**核对三个点：读引擎那两格、推进走带跳过的那条、写回走带保险的那条。
        """
        cpp = (ROOT / "runtime" / "source" / "mod_menu_native.cpp").read_text(encoding="utf-8")
        self.assertIn("kManagerContinueAvailableOffset = 0x2B688", cpp,
                      "读「继续游戏可不可选」的偏移必须是 `Manager+0x2B688`（反汇编那两处）")
        body = cpp.split("void ModRowUpdate(", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("ReadContinueAvailable(", body,
                      "`ModRowUpdate` 必须每帧问一次引擎（不读就还是旧行为）")
        self.assertIn("AdvanceSlotSkipping(", body, "推进必须走「跳过不可选项」那条")
        self.assertIn("GuardContinueRowForWrite(", body, "写回引擎的行号必须过那道保险")
        self.assertIn("EngineRowForSlot(g_Slot)", body, "写回给引擎的仍然必须是**行号**")
        self.assertNotIn("AdvanceSlot(g_Slot, false);\n        }\n        if (Edge(&g_LastDown",
                         body, "上键那条不许再退回旧的（不跳过的）推进")
        self.assertIn("g_ModMenuState.continueAvailable", body, "引擎的判定要记进状态面（[62]）")
        self.assertIn("g_ModMenuState.continueSkipped", body, "跳过次数要记进状态面（[63]）")


if __name__ == "__main__":
    unittest.main()
