"""PC公开字段拼写Subtype及原生有符号16位边界。"""
import unittest
from .test_api600_containers import SETUP
from .test_api400_params import run_main
class EntrySubtype(unittest.TestCase):
 def test_pc_spelling_and_signed_value(self):
  main=SETUP.replace('es:Get(0).SubType==7','es:Get(0).Subtype==7 and es:Get(0).SubType==7')
  main=main.replace('// Extra lifetime checks still use public userdata methods;', 'WriteAt<std::int16_t>(entries,6,-32768);\n// Extra lifetime checks still use public userdata methods;')
  main=main.replace('entry.Type==5)', 'entry.Type==5 and entry.Subtype==-32768 and entry.SubType==-32768)')
  r=run_main(main);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
