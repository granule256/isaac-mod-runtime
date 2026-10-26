"""大字体页按真实流式输出限额，而非16×像素数预拒；输出、内存和拒绝均为真实执行。"""
import re,subprocess,tempfile,unittest,zlib,struct
from pathlib import Path
try:
 from .test_png_to_pcx_alloc_safety import chunk,solid_rgba_png
except ImportError:
 from test_png_to_pcx_alloc_safety import chunk,solid_rgba_png
ROOT=Path(__file__).resolve().parents[2]
class StreamingBudgetTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.exe=Path(cls.temp.name)/'stream-budget'
  subprocess.run(['c++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),str(ROOT/'runtime/tests/png_stream_budget_harness.cpp'),str(ROOT/'runtime/src/infrastructure/content/png_to_pcx_bridge.cpp'),'-lz','-o',str(cls.exe)],check=True,capture_output=True)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def convert(self,png,fail=None):
  with tempfile.TemporaryDirectory()as d:
   source=Path(d)/'in.png';out=Path(d)/'out.pcx';source.write_bytes(png)
   r=subprocess.run([str(self.exe),str(source),str(out)]+([]if fail is None else[str(fail)]),capture_output=True,text=True)
   stats={k:int(v)for k,v in re.findall(r'(\w+)=(\d+)',r.stdout)}
   self.assertIn(r.returncode,(0,1),r.stdout+r.stderr)
   self.assertEqual(stats['live'],0,r.stdout)
   self.assertLessEqual(stats['peak']+len(png)+128*1024,64*1024*1024,r.stdout)
   return r.returncode,stats,out.read_bytes()if out.exists()else None
 def test_large_compressible_font_shape_is_accepted(self):
  code,stats,out=self.convert(solid_rgba_png(2048,2048))
  self.assertEqual(code,0,stats)
  # 每个平面常值，63像素一组，独立计算合法PCX字节，非实现回环。
  row=b''.join((bytes([0xff,value])*32+bytes([0xe0,value]))for value in(7,200,30,255))
  self.assertEqual(out[128:],row*2048)
  self.assertEqual(struct.unpack_from('<HHHH',out,4),(0,0,2047,2047))
  self.assertLess(stats['peak'],2*1024*1024)
 def test_actual_output_over_budget_is_rejected_without_partial_output(self):
  width=4096;height=4096
  row=b'\0'+b''.join(bytes([192+x%64])*4 for x in range(width))
  compressor=zlib.compressobj(9);data=b''.join(compressor.compress(row)for _ in range(height))+compressor.flush()
  png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',data)+chunk(b'IEND',b'')
  code,stats,out=self.convert(png)
  self.assertEqual(code,1,stats);self.assertEqual(stats['failure'],3,stats);self.assertIsNone(out)
 def test_allocation_failures_release_all_streaming_blocks(self):
  png=solid_rgba_png(2048,2048)
  for fail in(0,1,3,5,7,9,15):
   with self.subTest(fail=fail):
    code,stats,out=self.convert(png,fail)
    self.assertEqual(code,1,stats);self.assertIsNone(out)
 def test_small_stream_matches_independent_reference(self):
  import sys
  sys.path.insert(0,str(ROOT/'tools'))
  from png_to_pcx import png_to_pcx
  try:
   from .test_png_to_pcx_bridge import make_png
  except ImportError:
   from test_png_to_pcx_bridge import make_png
  for color in(0,2,4,6):
   png=make_png(9,5,color,[[(x*21,y*37,(x+y)*13,(x*33+y)&255)for x in range(9)]for y in range(5)],[0,1,2,3,4])
   code,stats,out=self.convert(png);self.assertEqual(code,0,stats);self.assertEqual(out,png_to_pcx(png))
if __name__=='__main__':unittest.main()
