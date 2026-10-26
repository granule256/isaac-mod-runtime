"""忏悔加作者版本受控补丁：不覆盖未知内容，不改源文件。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import build_deploy_package as package
ROOT=Path(__file__).resolve().parents[2]
class RPlusReadingPackagingTests(unittest.TestCase):
 def test_known_source_and_unknown_version(self):
  author=(ROOT/'dist/change-archive-20261024/001-rplus-reading-controller/main.before.lua').read_bytes()
  patched=(ROOT/'runtime/mod-patches/repentanceplus/main.lua').read_bytes()
  for content,expected in [(author,patched),(patched,patched),(author+b'\n',author+b'\n'),(author.replace(b'CustomData = {}',b'CustomData = { }',1),author.replace(b'CustomData = {}',b'CustomData = { }',1))]:
   with self.subTest(size=len(content)),tempfile.TemporaryDirectory()as tmp:
    src=Path(tmp)/'author';src.mkdir();(src/'main.lua').write_bytes(content);(src/'keep.bin').write_bytes(b'asset')
    self.assertEqual(package.copy_tree(src,Path(tmp)/'release'),2)
    self.assertEqual((Path(tmp)/'release/main.lua').read_bytes(),expected)
    self.assertEqual((src/'main.lua').read_bytes(),content)
    self.assertEqual((Path(tmp)/'release/keep.bin').read_bytes(),b'asset')
 def test_tampered_patch_is_rejected(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);src=root/'author';src.mkdir();(src/'main.lua').write_bytes((ROOT/'dist/change-archive-20261024/001-rplus-reading-controller/main.before.lua').read_bytes())
   fake=root/'runtime/mod-patches/repentanceplus/main.lua';fake.parent.mkdir(parents=True);fake.write_bytes(b'unreviewed')
   with patch.object(package,'ROOT',root),self.assertRaisesRegex(ValueError,'忏悔加'):
    package.copy_tree(src,root/'release')
