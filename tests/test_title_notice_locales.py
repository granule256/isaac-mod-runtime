"""Scoped locale layout/resource consistency checks without proprietary assets."""
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import build_title_notice as b


class TitleNoticeLocaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogs = b.load_catalogs(ROOT / 'tools/title_notice_content.json')
        chars = set(json.dumps(cls.catalogs, ensure_ascii=False)) | set('0123456789/A?')
        cls.font = b.Font(13, {ord(c): b.Glyph(0, 0, 2, 3, 0, 0, 4) for c in chars if c != '\n'},
                          b.Image(2, 3, bytearray([255] * 24)))
        cls.paper = b.PaperArt(b.Image(336, 216, bytearray([230, 220, 225, 255] * (336 * 216))),
                               b.Image(120, 26, bytearray([230, 220, 225, 255] * (120 * 26))))

    def test_catalog_sections_reconstruct_exactly_with_fixed_size_and_explicit_breaks(self):
        self.assertEqual(tuple(self.catalogs), b.LANGUAGES)
        self.assertEqual({c['version'] for c in self.catalogs.values()}, {'v1.0.0-beta.4'})
        for code, content in self.catalogs.items():
            with self.subTest(code=code):
                self.assertEqual([s['kind'] for s in content['sections']],
                                 ['intro', 'warning', 'free', 'disclaimer', 'instructions', 'disclaimer'])
                b.validate_labels(content, self.font)
                pages = b.paginate(content, self.font)
                self.assertLessEqual(len(pages), b.MAX_PAGES)
                for si, section in enumerate(content['sections']):
                    for pi, paragraph in enumerate(section['paragraphs']):
                        self.assertEqual(''.join(l.text for p in pages for l in p
                                                if (l.section, l.paragraph) == (si, pi)), paragraph)
                    if section.get('page_break_before'):
                        containing = next(p for p in pages if any(l.section == si for l in p))
                        self.assertEqual(containing[0].section, si)
                if code != 'zh':
                    # Japanese legitimately shares Han glyphs; forbid actual Chinese UI fallback phrases.
                    self.assertTrue(all(label not in b.DEFAULT_UI.values() for label in content['ui'].values()))

    def test_wrap_prefers_words_preserves_whitespace_and_splits_long_words(self):
        for text, width, expected in [
                ('ab cd ef', 20, ['ab ', 'cd ef']),
                ('ab cd\nef', 20, ['ab cd\n', 'ef']),
                ('abcdef', 12, ['abc', 'def']),
                (' a  b ', 12, None),
                ('日本語日本語', 12, ['日本語', '日本語'])]:
            # This fixture uses uniform advances so the expected boundaries are unambiguous.
            font = b.Font(13, {ord(c): b.Glyph(0, 0, 2, 3, 0, 0, 4) for c in text if c != '\n'}, self.font.image)
            lines = b.wrap_text(text, font, width)
            self.assertEqual(''.join(lines), text)
            self.assertTrue(all(font.width(line) <= width for line in lines))
            if expected is not None:
                self.assertEqual(lines, expected)
        self.assertEqual(b.wrap_text('ab cd ef', self.font, 20, prefer_words=False), ['ab cd', ' ef'])

    def test_localized_resource_paths_crops_counts_and_header_only_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = b.build_localized_assets(root / 'tree', root / 'normal.hpp', self.catalogs, self.font,
                                               paper_art=self.paper)
            # Metadata-only operation must neither render nor create a deployment tree.
            with patch.object(b, 'render_asset', side_effect=AssertionError('must not render')):
                metadata = b.build_localized_assets(root / 'unused', root / 'metadata.hpp', self.catalogs, self.font, header_only=True)
            self.assertFalse((root / 'unused').exists())
            self.assertNotIn('kIntegrityManifestDigest', (root / 'metadata.hpp').read_text())
            self.assertIn('kIntegrityManifestDigest', (root / 'normal.hpp').read_text())
            header = (root / 'normal.hpp').read_text()
            self.assertIn('kLocaleAssets[8]', header)
            self.assertIn('const char* language; unsigned pageCount; const char* assetPath;', header)
            rows = re.findall(r'\{"([a-z]{2})", (\d+), "([^"]+)"\}', header)
            self.assertEqual(tuple(code for code, _, _ in rows), b.LANGUAGES)
            self.assertEqual(sum(len(r['files']) for r in result['locales'].values()), 30)
            for code, count, asset in rows:
                locale = result['locales'][code]
                self.assertEqual(int(count), locale['page_count'])
                self.assertEqual(int(count), metadata['locales'][code]['page_count'])
                self.assertEqual(asset, f'gfx/ui/main menu/isaac-switch/nnotice_{code}.anm2')
                files = list(map(Path, locale['files']))
                expected_roots = {'resources'} | ({f'resources.{code}'} if code != 'en' else set())
                self.assertEqual({p.relative_to(root / 'tree' / b.RESOURCE_ROOT).parts[0] for p in files}, expected_roots)
                for path in files:
                    if path.suffix != '.anm2':
                        continue
                    anm = ET.parse(path).getroot()
                    self.assertEqual(anm.find('./Content/Spritesheets/Spritesheet').get('Path'), f'nnotice_{code}.pcx')
                    self.assertTrue(path.with_suffix('.pcx').is_file())
                    self.assertEqual(len(anm.findall('./Animations/Animation')), int(count) * 5 + 7)
                    for frame in anm.findall('.//LayerAnimation/Frame'):
                        a = frame.attrib
                        self.assertLessEqual(int(a['XCrop']) + int(a['Width']), locale['atlas_width'])
                        self.assertLessEqual(int(a['YCrop']) + int(a['Height']), locale['atlas_height'])

    def test_required_label_failures_also_fail_metadata_only(self):
        for key, text, pattern in [('entry', 'A' * 30, 'entry.*75px'),
                                   ('footer_auto', 'B' * 80, 'footer_auto.*260px'),
                                   ('footer_manual', '\u2603', 'missing glyph')]:
            catalogs = {code: {**content, 'ui': dict(content['ui'])} for code, content in self.catalogs.items()}
            catalogs['en']['ui'][key] = text
            with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, pattern):
                b.build_localized_assets(Path(tmp) / 'tree', Path(tmp) / 'header.hpp', catalogs, self.font, header_only=True)


if __name__ == '__main__':
    unittest.main()
