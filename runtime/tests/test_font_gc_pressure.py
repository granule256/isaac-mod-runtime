import subprocess, tempfile, unittest
from pathlib import Path
try:
 from .test_support import build_lua_harness
except ImportError:
 from test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
class FontGcPressureTest(unittest.TestCase):
 def test_real_callback_storm_reclaims_temporaries(self):
  with tempfile.TemporaryDirectory() as work:
   exe=build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(work),harness_source=(ROOT/'runtime/tests/font_gc_pressure_harness.cpp').read_text())
   r=subprocess.run([str(exe)],capture_output=True,text=True)
   print(r.stdout)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
