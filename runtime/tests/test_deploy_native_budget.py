"""发布包必须携带与本包SDK对应的449预算，拒绝旧SDK的预算。"""
import tempfile,unittest,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import build_deploy_package as package
import native_heap_budget_patch as budget
from nro_ips import encode_ips
class DeployNativeBudgetTests(unittest.TestCase):
 def test_matching_patch_is_required_and_stale_patch_is_rejected(self):
  self.assertIn('isaac-repentance-native-heap-budget',package.REQUIRED_RELAY_PATCHES)
  self.assertTrue(callable(getattr(package,'verify_native_heap_budget',None)))
  with tempfile.TemporaryDirectory(prefix='isaac-deploy-budget-')as d:
   p=Path(d);exefs=p/package.EXEFS_RELATIVE;exefs.mkdir(parents=True)
   nso=bytearray(256);nso[:4]=b'NSO0';struct.pack_into('<III',nso,0x30,256,0x400000,0x1000);struct.pack_into('<I',nso,0x3c,152*1024*1024)
   (exefs/'subsdk9').write_bytes(nso)
   patch=p/'atmosphere/nro_patches/isaac-repentance-native-heap-budget'/(budget.MODULE_ID+'.ips');patch.parent.mkdir(parents=True)
   with self.assertRaises(ValueError):package.verify_native_heap_budget(p)
   # 独立固定样本：奇数4KiB页的NSO映射为0x9c01000，CPU需补一页，
   # 原生图形池除二后才保持整页；不调用预算生成器来构造期望。
   reserve=240*1024*1024+0x9c02000
   patch.write_bytes(encode_ips([(0x8bf884,reserve.to_bytes(4,'little'))]))
   package.verify_native_heap_budget(p)
   for invalid in (reserve-4096,reserve+8192):
    patch.write_bytes(encode_ips([(0x8bf884,invalid.to_bytes(4,'little'))]))
    with self.assertRaises(ValueError):package.verify_native_heap_budget(p)
   patch.write_bytes(encode_ips([(0x8bf884,reserve.to_bytes(4,'little'))]))
   struct.pack_into('<I',nso,0x3c,153*1024*1024);(exefs/'subsdk9').write_bytes(nso)
   with self.assertRaises(ValueError):package.verify_native_heap_budget(p)
