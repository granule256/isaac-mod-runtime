"""发布包仅应用逐字核过的DSS裁剪复用资源，不修改作者输入或其它资源。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import build_deploy_package as package
ROOT=Path(__file__).resolve().parents[2]
REL=Path('scripts/dssmenucore.lua')
class DssPackagingTests(unittest.TestCase):
 def test_exact_reviewed_resource_and_version_fallback(self):
  author=(ROOT/'dist/dss-clip-reuse-20261017/author-dssmenucore.lua').read_bytes()
  optimized=(ROOT/'runtime/mod-patches/repentanceplus'/REL).read_bytes()
  changed=author.replace(b'DSSModName',b'DSSModNamo',1)
  for content,expected in [(author,optimized),(optimized,optimized),(changed,changed),(author+b'\n',author+b'\n')]:
   with self.subTest(content_size=len(content)),tempfile.TemporaryDirectory(prefix='dss-package-')as tmp:
    src,dest=Path(tmp)/'author',Path(tmp)/'release';(src/'scripts').mkdir(parents=True);(src/REL).write_bytes(content);(src/'keep.bin').write_bytes(b'asset');(src/'other').mkdir();(src/'other/dssmenucore.lua').write_bytes(author)
    self.assertEqual(package.copy_tree(src,dest),3)
    self.assertEqual((dest/REL).read_bytes(),expected)
    self.assertEqual((src/REL).read_bytes(),content)
    self.assertEqual((dest/'keep.bin').read_bytes(),b'asset')
    self.assertEqual((dest/'other/dssmenucore.lua').read_bytes(),author)
 def test_changed_patch_requires_review(self):
  author=(ROOT/'dist/dss-clip-reuse-20261017/author-dssmenucore.lua').read_bytes()
  with tempfile.TemporaryDirectory(prefix='dss-tamper-')as tmp:
   root=Path(tmp);src=root/'author';(src/'scripts').mkdir(parents=True);(src/REL).write_bytes(author)
   fake=root/'runtime/mod-patches/repentanceplus'/REL;fake.parent.mkdir(parents=True);fake.write_bytes(b'changed patch')
   with patch.object(package,'ROOT',root),self.assertRaisesRegex(ValueError,'DSS'):
    package.copy_tree(src,root/'release')
if __name__=='__main__':unittest.main()
