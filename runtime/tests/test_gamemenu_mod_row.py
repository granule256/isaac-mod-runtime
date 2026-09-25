"""『模组』那一行：**工具生成的东西必须与仓库里那份逐字节一致**，而且规则本身成立。

为什么值得单独钉（2026-09-22 晚，用户"为什么要自己一个个调"之后的落地）：

这一行现在**没有一个手写的数字** —— 每行挪多少、贴图落在哪、光标落在哪、纸的上下沿，
全部由 `tools/gamemenu_mod_row.py` 从该语言自己的 `gamemenu.anm2` / `gamemenu.pcx` 量出来，
生成到 `runtime/source/mod_row_generated.hpp`（八个语言各一套）。

这一类"生成物"最典型的坏法是**悄悄过期**：改了工具（或改了美术）却忘了重新生成，
真机上跑到的是旧数字，而在仓库里看不出任何异常。所以第一条判据就是**重新生成一遍、
与仓库那份逐字节比**（`test_byte_exact_delivery_dirs` 用的也是同一招）。

其余判据是**对着真游戏美术**跑出来的性质（不是常量表）：
我们那张贴图的字要落在纸里、六格的锚点要自上而下、光标与行位移要自洽、贴图本身要能解回来。
"""

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "gamemenu_mod_row.py"
GENERATED = ROOT / "runtime" / "source" / "mod_row_generated.hpp"
DUMP = (ROOT / "The Binding of Isaac_ Afterbirth+ 1.7.9b [010021C000B6A800][v524288][UPD]"
        / "Program #0/1")

sys.path.insert(0, str(ROOT))

from tools import gamemenu_mod_row as row  # noqa: E402


class GamemenuModRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DUMP.is_dir():
            raise unittest.SkipTest(f"没有游戏 dump：{DUMP}")
        # 排版真值源：PC 版**每语言**的主菜单参考（游戏数据，不进仓库；取法见
        # docs/PC-主菜单参考资源.md）。缺了就没法判"位置是不是 PC 的"，跳过。
        if not Path(row.PC_LANGUAGE_ROOT, "zh", "gfx", "ui", "main menu",
                    "gamemenu.anm2").is_file():
            raise unittest.SkipTest(f"没有 PC 参考资源：{row.PC_LANGUAGE_ROOT}")
        cls.bands = row.measure_paper_bands(str(DUMP))
        cls.results = {language: row.build_language(str(DUMP), language, None,
                                                    band=cls.bands[language],
                                                    pc=row.pc_language_layout(language))
                       for language in row.LANGUAGE_ROOTS}

    # ---- 0) 生成物必须是最新的（这一条最重要）--------------------------------

    def test_generated_header_is_up_to_date(self):
        with tempfile.TemporaryDirectory(prefix="isaac-mod-row-") as directory:
            fresh = Path(directory) / "mod_row_generated.hpp"
            producing = subprocess.run(
                [sys.executable, str(TOOL), "--dump-root", str(DUMP),
                 "--emit-layouts", str(fresh)],
                text=True, capture_output=True, cwd=ROOT)
            self.assertEqual(producing.returncode, 0, producing.stdout + producing.stderr)
            self.assertTrue(GENERATED.is_file(), f"仓库里没有 {GENERATED}")
            # 逐字节比：生成物是"提交进仓库的产物"，过期就是门禁红（不是"重新生成一下就好"）
            self.assertEqual(GENERATED.read_bytes(), fresh.read_bytes(),
                             "runtime/source/mod_row_generated.hpp 与工具刚生成的不一致 —— "
                             "要么有人手改了它，要么改了工具/换了美术却没重新生成")

    # ---- 1) 纸与贴图：我们的字要落在纸里 --------------------------------------

    def test_our_row_ink_inside_paper(self):
        for language, result in self.results.items():
            band_top, band_bottom = result["band"]
            ink_top = result["new_layer_y"] + result["ink_top"]
            ink_bottom = ink_top + result["sprite"][1] - 1
            self.assertGreaterEqual(ink_top, band_top, f"{language}：我们的字顶跑到纸上面")
            self.assertLessEqual(ink_bottom, band_bottom, f"{language}：我们的字底跑到纸下面")

    def test_paper_band_is_measured_not_guessed(self):
        # 八个语言的纸带一致（同一张版面）；英文那套因为"底是不透明背景"而退回参考带。
        for language, band in self.bands.items():
            self.assertEqual(band, (36.0, 213.0), f"{language} 的纸带量出来是 {band}")
        self.assertFalse(self.results["en"]["vanilla_row"], "英文那套没有原版行")

    # ---- 2) 六格的锚点：自上而下、都在纸里 ------------------------------------

    #: 判"跑到纸外"时的放宽量：纸的上沿是一条从透明渐入的软边（实测 25..36）、
    #: 下沿是画在背景上的阴影（实测 213..222）⇒ 落在这一圈里仍然"在纸上"，只是压在边上。
    #: ★ 但**我们摆的那一行**仍然按实心带严格判（见 `test_our_row_ink_inside_paper`）。
    PAPER_SLACK = 8.0

    def test_slot_tops_are_ordered_and_inside_paper(self):
        for language, result in self.results.items():
            tops = result["slot_tops"]
            self.assertEqual(len(tops), row.SLOT_COUNT, language)
            for index in range(1, len(tops)):
                self.assertGreater(tops[index], tops[index - 1] + 1.0,
                                   f"{language}：第 {index} 格没有排在第 {index - 1} 格下面：{tops}")
            # 每一行的**字**（不是那个 48 高的框）要落在纸里
            band_top, band_bottom = result["band"]
            for index, entry in enumerate(result["rows"]):
                top = result["plan"][index]["y"] + entry["ink_top"]
                bottom = result["plan"][index]["y"] + entry["ink_bottom"]
                self.assertGreaterEqual(top, band_top - self.PAPER_SLACK,
                                        f"{language}：{entry['name']} 的字顶 {top} 跑到纸上面")
                self.assertLessEqual(bottom, band_bottom + self.PAPER_SLACK,
                                     f"{language}：{entry['name']} 的字底 {bottom} 跑到纸下面")

    # ---- 3) 光标：行挪多少光标挪多少（自洽性）+ 都在纸里 ----------------------

    def test_cursor_follows_rows_and_stays_on_paper(self):
        for language, result in self.results.items():
            frames = result["cursor_frames"]
            for slot in range(row.SLOT_COUNT):
                frame = result["cursor_frame"][slot]
                self.assertLess(frame, len(frames), f"{language}：第 {slot} 格用了不存在的帧")
                cursor = result["cursor_y"][slot]
                self.assertGreaterEqual(cursor, result["band"][0] - 8.0, f"{language} 第 {slot} 格")
                self.assertLessEqual(cursor, result["band"][1] + 8.0, f"{language} 第 {slot} 格")
                if slot == row.MOD_ENTRY_SLOT:
                    continue
                # 光标的判据（2026-09-22 晚改）：**按 PC 的六帧来**，而且必须落在它那一行的字上。
                # （原来那条"光标位移 == 行位移"是旧规则的自洽性；现在行按 PC 的字中心摆、
                #   光标直接取 PC 的帧 ⇒ 两者不必逐值相等，要判的是"指对了那一行"。）
                if frame >= len(result["cursor_frames"]):
                    continue  # 该语言光标帧数少于 6（中文 5 帧）⇒ 帧位由生成表给，单独判
                if slot == row.MOD_ENTRY_SLOT:
                    top = result["new_layer_y"] + result["ink_top"]
                    bottom = result["new_layer_y"] + result["ink_bottom"]
                else:
                    index = slot if slot < row.MOD_ENTRY_SLOT else slot - 1
                    top = result["plan"][index]["y"] + result["rows"][index]["ink_top"]
                    bottom = result["plan"][index]["y"] + result["rows"][index]["ink_bottom"]
                self.assertGreaterEqual(cursor, top - 8.0, f"{language}：第 {slot} 格的光标偏高")
                self.assertLessEqual(cursor, bottom + 8.0, f"{language}：第 {slot} 格的光标偏低")

    def test_our_cursor_lands_on_our_row(self):
        for language, result in self.results.items():
            ink_top = result["new_layer_y"] + result["ink_top"]
            ink_bottom = ink_top + result["sprite"][1] - 1
            cursor = result["cursor_y"][row.MOD_ENTRY_SLOT]
            self.assertGreaterEqual(cursor, ink_top - 2.0, f"{language}：光标跑到我们那行字上面")
            self.assertLessEqual(cursor, ink_bottom + 2.0, f"{language}：光标跑到我们那行字下面")

    # ---- 4) 法语那一套是"原版自己就有一行" ------------------------------------

    def test_french_uses_the_vanilla_row(self):
        result = self.results["fr"]
        self.assertTrue(result["vanilla_row"], "法语那套的 ANM2 里本来就有一行（Item6），应当用它")
        self.assertEqual(result["shifts"], [0.0] * row.ENGINE_ROW_COUNT,
                         "用原版那一行时五行一动不动")
        self.assertEqual(result["cursor_frame"], [0, 1, 2, 3, 4, 5],
                         "原版六行 ↔ 六帧，一一对应")
        # 其余语言都是我们自己排的
        for language, other in self.results.items():
            if language != "fr":
                self.assertFalse(other["vanilla_row"], f"{language} 不该走原版行那条路")

    # ---- 5) 贴图本身：能解回来、不是空的、尺寸合理 ----------------------------

    def test_sprite_pcx_round_trips(self):
        for language, result in self.results.items():
            sprite = result["row_image"]
            encoded = row.encode_pcx(sprite)
            decoded = self._decode_bytes(encoded)
            self.assertEqual((decoded.width, decoded.height), (sprite.width, sprite.height),
                             language)
            self.assertEqual(bytes(decoded.rgba), bytes(sprite.rgba),
                             f"{language}：编出来的 PCX 解回来与内存里那张不一样")
            opaque = sum(1 for index in range(0, len(decoded.rgba), 4) if decoded.rgba[index + 3] > 120)
            self.assertGreater(opaque, 50, f"{language}：贴图几乎是空的（只有 {opaque} 个不透明像素）")
            self.assertGreaterEqual(sprite.width, 40, language)
            self.assertLessEqual(sprite.width, 160, language)
            self.assertLessEqual(sprite.height, 64, language)

    @staticmethod
    def _decode_bytes(data: bytes):
        with tempfile.TemporaryDirectory(prefix="isaac-mod-row-pcx-") as directory:
            path = Path(directory) / "sprite.pcx"
            path.write_bytes(data)
            return row.decode_pcx(str(path))

    # ---- 5a) ★★ 六格的位置**就是 PC 那六个绝对位置**（用户 2026-09-22 晚定）---------
    #
    # 用户的原话是："你不要改了，先查清楚 pc 到底是如何处理的"。查清楚的结果：
    # **PC 不做任何"算间距"这件事** —— 它在 `gamemenu.anm2` 里把六行写死成绝对坐标
    # （英语/中文/日文/韩文/俄语都是 34/59/87/[模组 123]/150/177，德语那条"挑战"是
    # 88 格高的斜横幅、西班牙语第一行在 37），"模组"在 PC 里本来就占一格（`Item6`，
    # 轴心 (16,16)、位置 (201,139) ⇒ 框顶 123）。挑战与统计数据之间那 63 格空档就是留给它的。
    # Switch 版**删掉了这一层**（法语那份没被改过，是 PC 的原件 ⇒ 它是"删之前"的样子）。
    #
    # ⇒ 判据从"白边不许比 PC 松"改成更强的一条：**我们发出去的六个页内 y 必须逐格等于
    #   PC 同一语言那份文件里的值**（位置是照搬的 ⇒ 可以要求完全相等，不是近似）。
    #
    # ⚠️ 被推翻的旧规则（留档，别回头走）：我先后用过"六格等间距""按 PC 的字中心"
    #     "逐格链 PC 的白边"—— 三条都在**推导**间距，而 PC 没有可推导的规律；推导还把我
    #     自己量字高的误差带进了位置里，真机上就是用户看到的"这一列偏上"和
    #     "模组上下两行的间距变大"。
    def test_rows_are_exactly_where_pc_puts_them(self):
        for language, result in self.results.items():
            layout = row.pc_language_layout(language)
            for slot in range(row.SLOT_COUNT):
                expected = layout["slots"][slot]["page_top"]
                self.assertAlmostEqual(result["slot_tops"][slot], expected, delta=0.001,
                                       msg=f"{language}：第 {slot} 格的框顶不是 PC 的值"
                                           f"（PC={expected}，我们={result['slot_tops'][slot]}）")
            # 横向也必须是 PC 的框（`Item6` 的 201−16 = 185）
            self.assertAlmostEqual(result["sprite_x"], layout["slots"][row.MOD_ENTRY_SLOT]["page_x"],
                                   delta=0.001, msg=f"{language}：我们那一格没有落在 PC 的框上")
            # ★ 横向：五行挪完之后的框 x 也必须逐格等于 PC 的值。
            #   用户 2026-09-22 深夜："模组似乎偏左了一点" —— 根因就是只搬了 Y：中文那一列
            #   排出来是 185/187/192/**189**/195/199（模组比它上面那行挑战还靠左 3 格），
            #   而 PC 中文自己那一列是 183/184/187/**189**/196/199。两边的图集是同一块美术
            #   （每行"框内字左"逐行相等）⇒ 差别只在 ANM2 里的框 x，照搬即可。
            for index in range(row.ENGINE_ROW_COUNT):
                slot = index if index < row.MOD_ENTRY_SLOT else index + 1
                moved = result["row_original_left"][index] + result["shifts_x"][index]
                expected_x = layout["slots"][slot]["page_x"]
                self.assertAlmostEqual(moved, expected_x, delta=0.001,
                                       msg=f"{language}：第 {slot} 格的框 x 不是 PC 的值"
                                           f"（PC={expected_x}，我们={moved}）")
            # 光标：PC 六帧的绝对 y（PC 一行一帧）
            for slot in range(row.SLOT_COUNT):
                self.assertAlmostEqual(result["cursor_y"][slot], layout["cursor"][slot], delta=0.001,
                                       msg=f"{language}：第 {slot} 格的光标不是 PC 的那一帧")

    def test_pc_reference_constants_have_not_drifted(self):
        """工具里那几个 PC（英语）锚点常量必须与仓库里那份 PC 参考文件一致。

        `PC_ROW_TOP` / `PC_ROW_INK` / `PC_CURSOR_Y` 只是**锚点**（真值源是文件本身，
        见上一条）：它们能替"PC 换了文件/我们抄错了数字"报警。参考文件不在（没解包）就跳过。
        """
        reference = os.path.join(row.PC_REFERENCE_DIR, "gamemenu.anm2")
        if not os.path.exists(reference):
            self.skipTest(f"没有 PC 参考文件：{reference}")
        fresh = row.pc_layout(reference)
        for index, entry in enumerate(fresh["rows"][:row.SLOT_COUNT]):
            self.assertAlmostEqual(entry["page_top"], row.PC_ROW_TOP[index], delta=0.001,
                                   msg=f"PC 第 {index} 格的框顶与工具里的锚点不一致")
            self.assertAlmostEqual(entry["ink_page_top"], row.PC_ROW_INK[index][0], delta=0.6,
                                   msg=f"PC 第 {index} 格的字顶与工具里的锚点不一致")
            self.assertAlmostEqual(entry["ink_page_bottom"], row.PC_ROW_INK[index][1], delta=0.6,
                                   msg=f"PC 第 {index} 格的字底与工具里的锚点不一致")
        for slot, value in enumerate(row.PC_CURSOR_Y):
            self.assertAlmostEqual(fresh["cursor"][slot], value, delta=0.001,
                                   msg=f"PC 第 {slot} 帧光标与工具里的锚点不一致")

    def test_our_row_sits_in_the_pc_box(self):
        """我们那一格必须画在 PC `Item6` 那个框上（位置 (211−16, 139−16) 那种）。"""
        for language, result in self.results.items():
            layout = row.pc_language_layout(language)
            box = layout["slots"][row.MOD_ENTRY_SLOT]
            self.assertEqual(box["crop"], (195, 475, 80, 39),
                             f"{language}：PC 的 `Item6` 裁切块变了？{box['crop']}")
            self.assertAlmostEqual(result["new_layer_y"], box["page_top"], delta=0.001, msg=language)
            self.assertAlmostEqual(result["sprite_x"], box["page_x"], delta=0.001, msg=language)

    # ---- 5b) ★★ 我们那张贴图**就是游戏自己画的**（用户点出来的那条）----------------
    #
    # 用户看到的是"这个模组更斜、像一张截图随便贴在纸上"，根因是我找错了美术：
    # 我用的是**模组页标题纸带**上的字（另一张版面、更大、更斜），再缩放+旋转去凑周围几行。
    # 正确的那块美术是各语言图集里的『第 6 行』（只有法语 ANM2 引用了它）。
    # ⇒ 判据不再是"斜度像不像"，而是更强的一条：**贴图与图集里那一块逐像素相同、尺寸也相同**
    #   （1:1 取用，既不缩放也不旋转 —— 那就不可能"像截图贴在纸上"）。
    def test_our_sprite_is_the_games_own_row_art(self):
        region = row.sixth_row_region(str(DUMP))
        for language, result in self.results.items():
            # 本语言图集里那一块；空的（英文那套是旧版面）就用借来的那个语言的
            sources = [language] + ([result["donor"]] if result.get("donor") else [])
            found = None
            for candidate in sources:
                if candidate is None:
                    continue
                sheet = row.decode_pcx(row.resolve_content_file(str(DUMP), candidate,
                                                                row.GAMEMENU_PCX))
                found = row.sixth_row_art(sheet, region)
                if found is not None:
                    break
            self.assertIsNotNone(found, f"{language}：连借都借不到那一块")
            atlas_art, ink_rel = found
            mine = result["row_image"]
            self.assertEqual((mine.width, mine.height), (atlas_art.width, atlas_art.height),
                             f"{language}：贴图尺寸与图集里那一块不一样（被缩放过了）")
            self.assertEqual(bytes(mine.rgba), bytes(atlas_art.rgba),
                             f"{language}：贴图与图集里那一块不是逐像素相同（被改过了）")
            self.assertEqual((int(result["ink_left"]), int(result["ink_top"]),
                              int(result["ink_bottom"])),
                             (ink_rel[0], ink_rel[1], ink_rel[3]),
                             f"{language}：报给运行时的字框与实测不一致")
            # 字不许比周围几行明显大（同一支笔画的，尺寸本来就该在同一档）
            mine_h = result["ink_bottom"] - result["ink_top"] + 1
            theirs = sorted(entry["ink_bottom"] - entry["ink_top"] + 1
                            for index, entry in enumerate(result["rows"])
                            if not result["plan"][index].get("background"))
            self.assertLessEqual(mine_h, theirs[len(theirs) // 2] + 6,
                                 f"{language}：我们的字高 {mine_h:.0f} 比周围几行中位 "
                                 f"{theirs[len(theirs) // 2]} 大得多")

    # ---- 6) 贴图确实是"**那个语言**的字"（用墨迹形状做指纹）---------------------
    #
    # 八个语言的贴图**尺寸一样**（都是图集里那一块 80×39），不同的是里面的字
    #（中文「模组」/日文的那套/韩文「모드」/俄文「МОДЫ」/拉丁的 "MODS"）⇒
    # 拿"字在块里的包围盒"当指纹：至少要有三种不同的形状，否则就是"八个语言拿到了同一张图"
    #（那说明挑文件挑错了 —— 这正是上一轮出问题的形态）。
    def test_sprite_ink_differs_per_language(self):
        fingerprints = {}
        for language, result in self.results.items():
            box = row.ink_bbox(result["row_image"],
                               (0, 0, result["row_image"].width - 1,
                                result["row_image"].height - 1))
            fingerprints[language] = box
        self.assertGreater(len(set(fingerprints.values())), 2,
                           f"八个语言的字形状几乎一样：{fingerprints}")
        # 中文那两个字本语言必须能找到（它是这台的用户语言）
        self.assertIn("zh", self.results)

    # ---- 7) 法语那套是"原版自己就有一行" -----------------------------------------


if __name__ == "__main__":
    unittest.main()
