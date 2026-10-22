import struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import native_heap_budget_patch as budget
from nro_ips import apply_records,decode_ips
class NativeHeapBudgetTests(unittest.TestCase):
 def fixture(self,footprint=0x9d1e000):
  nro=bytearray(budget.MAIN_HEAP_OFFSET+4)
  nro[0x40:0x60]=bytes.fromhex(budget.MODULE_ID)
  struct.pack_into('<I',nro,budget.MAIN_HEAP_OFFSET,budget.BASE_CPU_RESERVE)
  nro[budget.INIT_OFFSET:budget.INIT_OFFSET+len(budget.INIT_GUARD)]=budget.INIT_GUARD
  # 原版initialize_graphics_heaps: (3GiB-CPU预留)>>1。
  graphics_guard=bytes.fromhex('080140b90900b852280108cbf30300aa004002914100805202fd41d3')
  nro[0x4ff1f0:0x4ff1f0+len(graphics_guard)]=graphics_guard
  nso=bytearray(256);nso[:4]=b'NSO0'
  struct.pack_into('<III',nso,0x30,256,0x400000,0x1000)
  struct.pack_into('<I',nso,0x3c,footprint-0x401000)
  return bytes(nro),bytes(nso)
 def test_preserves_original_cpu_reserve_after_injection(self):
  nro,nso=self.fixture();patch,info=budget.generate(nro,nso)
  changed=apply_records(nro,decode_ips(patch))
  reserve=struct.unpack_from('<I',changed,budget.MAIN_HEAP_OFFSET)[0]
  self.assertEqual(reserve,240*1024*1024+0x9d1e000)
  self.assertEqual(reserve-info['runtime_footprint'],budget.BASE_CPU_RESERVE)
  self.assertEqual(changed[:budget.MAIN_HEAP_OFFSET],nro[:budget.MAIN_HEAP_OFFSET])
  self.assertEqual(len(decode_ips(patch)),1)
 def test_changed_module_footprint_regenerates_reserve(self):
  a,b=self.fixture(0x8000000);_,one=budget.generate(a,b)
  a,b=self.fixture(0xa000000);_,two=budget.generate(a,b)
  self.assertEqual(two['cpu_reserve']-one['cpu_reserve'],32*1024*1024)
 def test_odd_module_page_count_keeps_halved_graphics_heap_page_aligned(self):
  nro,nso=self.fixture(0x9d1f000)
  patch,info=budget.generate(nro,nso)
  changed=apply_records(nro,decode_ips(patch))
  reserve=struct.unpack_from('<I',changed,budget.MAIN_HEAP_OFFSET)[0]
  graphics=(budget.NATIVE_TOTAL_RESERVE-reserve)//2
  self.assertEqual(graphics%4096,0,'图形堆除以二后不得剩半页')
  self.assertGreaterEqual(reserve-info['runtime_footprint'],budget.BASE_CPU_RESERVE)
  self.assertEqual(reserve-(budget.BASE_CPU_RESERVE+info['runtime_footprint']),4096)
 def test_mismatched_build_or_initialization_code_rejected(self):
  nro,nso=self.fixture()
  for offset in (0x40,budget.INIT_OFFSET,budget.MAIN_HEAP_OFFSET,budget.GRAPHICS_INIT_OFFSET):
   bad=bytearray(nro);bad[offset]^=1
   with self.assertRaises(ValueError):budget.generate(bytes(bad),nso)
 def test_bad_nso_and_excessive_footprint_rejected(self):
  nro,nso=self.fixture()
  with self.assertRaises(ValueError):budget.generate(nro,b'NSO0')
  _,huge=self.fixture(0xc0000000)
  with self.assertRaises(ValueError):budget.generate(nro,huge)
if __name__=='__main__':unittest.main()
