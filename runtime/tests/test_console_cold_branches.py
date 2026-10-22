"""未知命令仅两条真实分支，加载前重定位条件，null槽仍保留内建路径。"""
import unittest,struct
from pathlib import Path
from tools import cold_static_callbacks as c
ROOT=Path(__file__).resolve().parents[2]
class ConsoleColdBranchTests(unittest.TestCase):
 def test_unknown_branch_builder_exists(self):
  self.assertTrue(hasattr(c,'CONSOLE_BRANCH_SITES'),'未知命令条件分支尚无加载前中继')
 def test_real_sources_and_null_condition_targets(self):
  if not hasattr(c,'CONSOLE_BRANCH_SITES'):self.fail('未知命令条件分支尚无加载前中继')
  nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  for source,gate,original in c.CONSOLE_BRANCH_SITES:
   self.assertEqual(struct.unpack_from('<I',nro,source)[0],original)
   raw=c.console_branch_gate(source,gate,original);self.assertEqual(len(raw),40)
   words=struct.unpack('<8I',raw[:32]);self.assertEqual(words[:4],(0x10000110,0xc8dffe10,0xb4000050,0xd61f0200))
   self.assertEqual(words[4],0x54000040 if source==0x41878 else 0x34000040)
   self.assertEqual(words[5],c.branch(gate+20,0x41d64));self.assertEqual(words[6],c.branch(gate+24,source+4));self.assertEqual(raw[32:],bytes(8))
   broken=bytearray(nro);broken[source]^=1
   with self.assertRaises(ValueError):c.build_static_callback_patch(broken)
