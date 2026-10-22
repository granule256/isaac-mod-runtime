"""发布包仅应用逐字核过的StageAPI网格读取复用资源，不修改作者输入或其它资源。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import build_deploy_package as package
ROOT=Path(__file__).resolve().parents[2]
REL=Path('scripts/stageapi/core/callbacks.lua')
class StageApiGridPackagingTests(unittest.TestCase):
 def test_previous_shared_initialization_fix_survives_packaging(self):
  rel=Path('scripts/stageapi/shared.lua')
  original=(ROOT/'analysis/mod-corpus/BOIStageAPI15'/rel).read_bytes()
  fixed=(ROOT/'runtime/mod-patches/StageAPI'/rel).read_bytes()
  for content,expected in [(original,fixed),(fixed,fixed),(original+b'\n',original+b'\n')]:
   with self.subTest(size=len(content)),tempfile.TemporaryDirectory(prefix='stageapi-shared-package-')as tmp:
    source,target=Path(tmp)/'author',Path(tmp)/'release';(source/rel).parent.mkdir(parents=True);(source/rel).write_bytes(content)
    self.assertEqual(package.copy_tree(source,target),1)
    self.assertEqual((source/rel).read_bytes(),content)
    self.assertEqual((target/rel).read_bytes(),expected)
 def test_exact_reviewed_resource_and_version_fallback(self):
  author=(ROOT/'dist/stageapi-grid-read-reuse-20261017/author-callbacks.lua').read_bytes()
  optimized=(ROOT/'runtime/mod-patches/StageAPI'/REL).read_bytes()
  changed=author.replace(b'GridEntityType',b'GridEntityTypo',1)
  for content,expected in [(author,optimized),(optimized,optimized),(changed,changed),(author+b'\n',author+b'\n')]:
   with self.subTest(content_size=len(content)),tempfile.TemporaryDirectory(prefix='dss-package-')as tmp:
    src,dest=Path(tmp)/'author',Path(tmp)/'release';(src/REL).parent.mkdir(parents=True);(src/REL).write_bytes(content);(src/'keep.bin').write_bytes(b'asset');(src/'other').mkdir();(src/'other/callbacks.lua').write_bytes(author)
    self.assertEqual(package.copy_tree(src,dest),3)
    self.assertEqual((dest/REL).read_bytes(),expected)
    self.assertEqual((src/REL).read_bytes(),content)
    self.assertEqual((dest/'keep.bin').read_bytes(),b'asset')
    self.assertEqual((dest/'other/callbacks.lua').read_bytes(),author)
 def test_changed_patch_requires_review(self):
  author=(ROOT/'dist/stageapi-grid-read-reuse-20261017/author-callbacks.lua').read_bytes()
  with tempfile.TemporaryDirectory(prefix='dss-tamper-')as tmp:
   root=Path(tmp);src=root/'author';(src/REL).parent.mkdir(parents=True);(src/REL).write_bytes(author)
   fake=root/'runtime/mod-patches/StageAPI'/REL;fake.parent.mkdir(parents=True);fake.write_bytes(b'changed patch')
   with patch.object(package,'ROOT',root),self.assertRaisesRegex(ValueError,'StageAPI'):
    package.copy_tree(src,root/'release')
if __name__=='__main__':unittest.main()
