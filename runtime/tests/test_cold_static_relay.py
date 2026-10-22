"""加载前IPS：精确原件/空区校验，源跳转、LDAR发布槽与原指令重放。"""
import importlib,struct,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class ColdStaticRelayTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.module=None
  try:cls.module=importlib.import_module('tools.cold_static_callbacks')
  except ModuleNotFoundError:pass
  cls.nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
 def test_builder_exists(self):self.assertIsNotNone(self.module,'普通LDR/CMP内部点的加载前安全中继尚未实现')
 def decode(self,blob):
  self.assertEqual(blob[:5],b'PATCH');i=5;records={}
  while blob[i:i+3]!=b'EOF':
   off=int.from_bytes(blob[i:i+3],'big');n=int.from_bytes(blob[i+3:i+5],'big');i+=5
   self.assertNotEqual(n,0);records[off]=blob[i:i+n];i+=n
  return records
 def test_original_instruction_and_acquire_slot(self):
  if self.module is None:self.skipTest('尚未实现')
  records=self.decode(self.module.build_static_callback_patch(self.nro))
  for src,gate,original in [(0x3e0c88,0x68cdc0,0xf9400309),(0x269d50,0x68cde0,0x7100a29f)]:
   branch=0x14000000|(((gate-src)//4)&0x3ffffff)
   self.assertEqual(records[src],struct.pack('<I',branch))
   raw=records[gate];self.assertEqual(len(raw),32)
   words=struct.unpack('<6I',raw[:24])
   self.assertEqual(words[:4],(0x100000d0,0xc8dffe10,0xb4000050,0xd61f0200))
   self.assertEqual(words[4],original)
   self.assertEqual(words[5],0x14000000|((((src+4)-(gate+20))//4)&0x3ffffff))
   self.assertEqual(raw[24:],bytes(8))
 def test_trophy_path_has_its_own_relay_before_currency_correction(self):
  if self.module is None:self.skipTest('尚未实现')
  records=self.decode(self.module.build_static_callback_patch(self.nro))
  self.assertIn(0x269d08,records,'原奖杯110配置后直接走269D08，跳过269D50，不能漏派37')
  self.assertEqual(records[0x68cd00][16:20],struct.pack('<I',0xb85fc3b4))
  self.assertEqual(records[0x269d08],struct.pack('<I',0x14000000|(((0x68cd00-0x269d08)//4)&0x3ffffff)))
 def test_every_source_and_full_gate_corruption_is_rejected(self):
  if self.module is None:self.skipTest('尚未实现')
  for offset,length in [(0x3e0c88,4),(0x269d50,4),(0x68cdc0,32),(0x68cde0,32),(0x269d08,4),(0x68cd00,32)]:
   for i in range(length):
    raw=bytearray(self.nro);raw[offset+i]^=1
    with self.subTest(address=hex(offset+i)),self.assertRaises(ValueError):self.module.build_static_callback_patch(raw)
