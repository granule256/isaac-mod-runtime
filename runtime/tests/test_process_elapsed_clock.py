"""固定PC Windows CRT clock的毫秒墙钟、重载与24.8天边界。"""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
class ProcessElapsedClockTests(unittest.TestCase):
 def test_windows_clock_quantization_reload_and_overflow(self):
  source=r'''
#include "interfaces/lua/process_elapsed_clock.hpp"
#include <cassert>
using isaac::runtime::ProcessElapsedClock;
int main(){ProcessElapsedClock c{};assert(c.Seconds(0,19200000)==-.001);c.Start(100);assert(c.Seconds(100,19200000)==0);assert(c.Seconds(19299,19200000)==0);assert(c.Seconds(19300,19200000)==.001);assert(c.Seconds(19200100,19200000)==1);c.Start(999999);assert(c.Seconds(19200100,19200000)==1);assert(c.Seconds(99,19200000)==-.001);assert(c.Seconds(100,0)==-.001);assert(c.Seconds(100+2147483647ULL*19200,19200000)==2147483.647);assert(c.Seconds(100+2147483648ULL*19200,19200000)==-.001);}
'''
  with tempfile.TemporaryDirectory(prefix='pc-elapsed-clock-')as d:
   p=Path(d);(p/'main.cpp').write_text(source);r=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),str(p/'main.cpp'),'-o',str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr);r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
