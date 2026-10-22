import subprocess,tempfile,unittest,sys
from pathlib import Path
try:
 from .test_png_to_pcx_alloc_safety import build_harness
except ImportError:
 from test_png_to_pcx_alloc_safety import build_harness
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from png_to_pcx import png_to_pcx
class StreamPressureTest(unittest.TestCase):
 def test_real_dance_sheet_with_four_mib_allocation_limit(self):
  source=Path.home()/'Library/Application Support/Steam/steamapps/workshop/content/250900/2575911103/resources/the/sheets/isaac.png'
  self.assertTrue(source.exists(),'真实舞装样本缺失')
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'out.pcx'
   r=subprocess.run([str(build_harness()),str(source),str(out),'--max-allocation',str(4*1024*1024)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   self.assertEqual(out.read_bytes(),png_to_pcx(source.read_bytes()))
if __name__=='__main__':unittest.main()
