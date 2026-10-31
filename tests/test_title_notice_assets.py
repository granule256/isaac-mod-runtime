"""Focused checks for title notice build assets, using a tiny in-memory font."""
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TitleNoticeAssetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = importlib.util.find_spec("tools.build_title_notice")

    def api(self):
        self.assertIsNotNone(self.spec, "title notice resource generator is missing")
        from tools import build_title_notice
        return build_title_notice

    def font(self, text):
        b = self.api()
        chars = set(text) | set("0123456789 /←→或LR翻页长按B关闭兼容层说明请先完全部面A?ISAACSWITCHv.-")
        glyphs = {ord(c): b.Glyph(0, 0, 2, 3, 0, 0, 4) for c in chars if c != "\n"}
        return b.Font(13, glyphs, b.Image(2, 3, bytearray([255] * 24)))

    def content(self):
        return {"version": "v1.0.0-beta.1", "title": "Title", "subtitle": "ISAAC SWITCH",
                "ui": {"entry": "Info", "footer_locked": "Read | L/R", "footer_auto": "Hold B | L/R", "footer_manual": "B | L/R"},
                "sections": [{"kind": "intro", "paragraphs": ["abc，def。\nxyz!", " a  b "]},
                             {"kind": "warning", "paragraphs": ["warning!" * 80]}]}

    def test_pagination_reconstructs_every_character_and_explicit_newline(self):
        b = self.api()
        content = self.content()
        font = self.font(json.dumps(content, ensure_ascii=False))
        pages = b.paginate(content, font)
        self.assertGreater(len(pages), 1)
        for si, section in enumerate(content["sections"]):
            for pi, paragraph in enumerate(section["paragraphs"]):
                actual = "".join(line.text for page in pages for line in page
                                 if (line.section, line.paragraph) == (si, pi))
                self.assertEqual(actual, paragraph)
        self.assertTrue(all(line.y + font.line_height <= 188 for page in pages for line in page))

    def test_missing_and_overwide_glyphs_are_clear_errors(self):
        b = self.api()
        font = self.font("a")
        with self.assertRaisesRegex(ValueError, "missing glyph.*U\\+2603"):
            b.wrap_text("☃", font, 100)
        with self.assertRaisesRegex(ValueError, "wider than"):
            b.wrap_text("a", font, 3)

    def test_font_tint_uses_white_face_without_turning_black_outline_into_solid_ink(self):
        b = self.api()
        source = b.Image(3, 1, bytearray([0, 0, 0, 255, 255, 255, 255, 255, 0, 0, 0, 77]))
        font = b.Font(1, {ord("a"): b.Glyph(0, 0, 3, 1, 0, 0, 3)}, source)
        target = b.Image(3, 1, bytearray([230, 220, 210, 255] * 3))
        b.draw_text(target, font, "a", 0, 0, b.INK)
        self.assertEqual(target.pixel(0, 0), (230, 220, 210, 255))
        self.assertEqual(target.pixel(1, 0), b.INK)
        self.assertEqual(target.pixel(2, 0), (230, 220, 210, 255))

    def test_rejects_page_overflow_without_dropping_content(self):
        b = self.api()
        content = self.content()
        content["sections"] = [{"paragraphs": ["a\n" * 400]}]
        with self.assertRaisesRegex(ValueError, "32 pages"):
            b.paginate(content, self.font("a"))

    def test_explicit_section_page_breaks_keep_the_first_page_concise(self):
        b = self.api()
        content = {"sections": [
            {"page_break_before": True, "paragraphs": ["a"]},
            {"page_break_before": True, "paragraphs": ["bb"]},
            {"page_break_before": True, "paragraphs": ["ccc"]}]}
        pages = b.paginate(content, self.font("abc"))
        self.assertEqual([[line.text for line in page] for page in pages], [["a"], ["bb"], ["ccc"]])

    def test_support_is_a_separate_last_page_even_when_body_grows(self):
        b = self.api()
        for size in (0, 1, 25, 200):
            content = self.content()
            content['sections'] = [{'paragraphs': ['a\n' * size]}]
            content['support'] = {'title': 'Support', 'message': 'Free; optional support.',
                                  'labels': ['WeChat', 'Alipay', 'Ko-fi'],
                                  'github': 'https://github.com/granule256/isaac-mod-runtime'}
            font = self.font(json.dumps(content) + 'GitHub:')
            pages = b.paginate(content, font)
            self.assertTrue(all(l.kind == 'support' for l in pages[-1]))
            self.assertTrue(all(l.kind != 'support' for p in pages[:-1] for l in p))
            self.assertIn('isaac-mod-runtime', ''.join(l.text for l in pages[-1]))
            self.assertEqual(len(pages), len(b.paginate({**content, 'support': None}, font)) + 1)

    def test_support_counts_toward_page_limit(self):
        b = self.api()
        content = self.content()
        content['sections'] = [{'page_break_before': True, 'paragraphs': ['a']} for _ in range(32)]
        content['support'] = {'title': 'a', 'message': 'a', 'labels': ['a'] * 3,
                              'github': 'https://github.com/granule256/isaac-mod-runtime'}
        with self.assertRaisesRegex(ValueError, '32 pages'):
            b.paginate(content, self.font(json.dumps(content)))

    def test_resource_graph_animation_contract_and_header_are_consistent(self):
        b = self.api()
        content = self.content()
        font = self.font(json.dumps(content, ensure_ascii=False))
        with tempfile.TemporaryDirectory() as tmp:
            result = b.build_assets(Path(tmp) / "tree", Path(tmp) / "generated.hpp", content, font)
            self.assertEqual(len(result["files"]), 4)
            self.assertEqual(result["page_count"], len(b.paginate(content, font)))
            for path in result["files"]:
                self.assertTrue(Path(path).is_file())
            header = (Path(tmp) / "generated.hpp").read_text()
            self.assertIn(content["version"], header)
            self.assertIn(f'kPageCount = {result["page_count"]}', header)
            self.assertIn('kPaperWidth = 336.F', header)
            self.assertIn('kPaperHeight = 216.F', header)
            anm = ET.parse(next(p for p in result["files"] if p.endswith(".anm2"))).getroot()
            pcx = b.decode_pcx(next(p for p in result["files"] if p.endswith(".pcx")))
            self.assertEqual(anm.find("Info").attrib["Version"], "18")
            self.assertLessEqual(max(pcx.width, pcx.height), 4096)
            for sheet in anm.findall("./Content/Spritesheets/Spritesheet"):
                self.assertEqual(sheet.attrib["Path"], "nnotice.pcx")
            animations = {a.attrib["Name"]: a for a in anm.findall("./Animations/Animation")}
            for index in range(result["page_count"]):
                for name, delays in [("Open", [5, 2, 2, 1]), ("Idle", [1]),
                                     ("Close", [2, 1, 6, 1]), ("FlipOut", [1, 1, 1]),
                                     ("FlipIn", [1, 1, 1])]:
                    anim = animations[f"{name}_{index}"]
                    keys = anim.findall("./RootAnimation/Frame")
                    self.assertEqual([int(k.attrib["Delay"]) for k in keys], delays)
                    self.assertEqual(int(anim.attrib["FrameNum"]), sum(delays))
                    if name == "Open":
                        self.assertEqual([int(k.attrib["XPosition"]) for k in keys], [-700, -176, 0, 0])
                        self.assertEqual([int(k.attrib["XScale"]) for k in keys], [160, 120, 80, 100])
                    frame = anim.find("./LayerAnimations/LayerAnimation/Frame").attrib
                    self.assertEqual((frame["XPivot"], frame["YPivot"]), ("168", "108"))
            for frame in anm.findall(".//LayerAnimation/Frame"):
                a = frame.attrib
                self.assertLessEqual(int(a["XCrop"]) + int(a["Width"]), pcx.width)
                self.assertLessEqual(int(a["YCrop"]) + int(a["Height"]), pcx.height)
            support_names = ["Entry", "EntrySelected", "FooterLocked", "FooterAuto", "FooterManual", "Progress", "Dim"]
            for name in support_names:
                self.assertIn(name, animations)
            crops = []
            for name in support_names:
                a = animations[name].find("./LayerAnimations/LayerAnimation/Frame").attrib
                crops.append((name, int(a["XCrop"]), int(a["YCrop"]), int(a["Width"]), int(a["Height"])))
            for i, (name, x, y, width, height) in enumerate(crops):
                for other, ox, oy, ow, oh in crops[i + 1:]:
                    overlap = x < ox + ow and ox < x + width and y < oy + oh and oy < y + height
                    self.assertFalse(overlap, f"support crops overlap: {name} and {other}")
            locked = animations["FooterLocked"].find("./LayerAnimations/LayerAnimation/Frame").attrib
            self.assertEqual((locked["Width"], locked["Height"], locked["YPosition"]), ("336", "18", "82"))
            for name in ["Entry", "EntrySelected"]:
                a = animations[name].find("./LayerAnimations/LayerAnimation/Frame").attrib
                self.assertLessEqual(int(a["Width"]), 120)
                self.assertLessEqual(int(a["Height"]), 26)
                self.assertEqual(a["XPosition"], "0")
                self.assertEqual(a["YPosition"], "0")
            progress = animations["Progress"].find("./LayerAnimations/LayerAnimation/Frame").attrib
            self.assertEqual((progress["Width"], progress["Height"], progress["XPivot"]), ("60", "3", "0"))
            dim = animations["Dim"].find("./LayerAnimations/LayerAnimation/Frame").attrib
            self.assertEqual((dim["Width"], dim["Height"], dim["AlphaTint"]), ("1", "1", "140"))

    def test_binary_bmfont_parser_reads_metrics_and_case_insensitive_page(self):
        b = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            common = struct.pack("<HHHHHBBBBB", 13, 11, 2, 3, 1, 0, 0, 0, 0, 0)
            chars = struct.pack("<IHHHHhhhBB", ord("字"), 0, 0, 2, 3, -1, 2, 10, 0, 15)
            data = b"BMF\x03" + b"".join(bytes([i]) + struct.pack("<I", len(body)) + body
                                        for i, body in [(2, common), (3, b"FONT_0.pcx\x00"), (4, chars)])
            (root / "font.fnt").write_bytes(data)
            (root / "font_0.pcx").write_bytes(b.encode_pcx(b.Image(2, 3, bytearray([255] * 24))))
            font = b.load_font(root / "font.fnt")
            self.assertEqual(font.line_height, 13)
            self.assertEqual(font.glyphs[ord("字")].advance, 10)
            self.assertEqual(font.glyphs[ord("字")].xoffset, -1)

    def test_header_only_cli_does_not_decode_bitmap_or_write_deployment_tree(self):
        content = self.content()
        font = self.font(json.dumps(content, ensure_ascii=False))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font_dir = root / "dump/rp_patch/resources/font/cjk"
            font_dir.mkdir(parents=True)
            common = struct.pack("<HHHHHBBBBB", 13, 11, 2, 3, 1, 0, 0, 0, 0, 0)
            chars = b"".join(struct.pack("<IHHHHhhhBB", code, g.x, g.y, g.width, g.height,
                                          g.xoffset, g.yoffset, g.advance, 0, 15)
                             for code, g in font.glyphs.items())
            (font_dir / "lanapixel.fnt").write_bytes(b"BMF\x03" + b"".join(
                bytes([i]) + struct.pack("<I", len(body)) + body
                for i, body in [(2, common), (3, b"lanapixel_0.pcx\x00"), (4, chars)]))
            (font_dir / "lanapixel_0.pcx").write_bytes(b"intentionally not decodable")
            (root / "content.json").write_text(json.dumps(content), encoding="utf-8")
            (root / "locales.json").write_text(json.dumps({code: content for code in self.api().LANGUAGES if code != "zh"}), encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "tools/build_title_notice.py"),
                                     "--tree", str(root / "tree"), "--header", str(root / "header.hpp"),
                                     "--dump-root", str(root / "dump"), "--content", str(root / "content.json"),
                                     "--locales", str(root / "locales.json"),
                                     "--header-only"], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "header.hpp").is_file())
            self.assertFalse((root / "tree").exists())


if __name__ == "__main__":
    unittest.main()
