"""弹幕正常完成的静态指令、全函数守卫、互斥代码区和空槽回退。"""
from pathlib import Path
import subprocess,tempfile,unittest,sys,struct
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import cold_static_callbacks as patches

class ProjectileTailPatchTests(unittest.TestCase):
 def check_site(self,initialize):
  nro=next(ROOT.glob('The Binding*Afterbirth*/*/1/.nro/Repentance.nro')).read_bytes()
  source,gate,original=patches.PROJECTILE_INIT_TAIL_SITE if initialize else patches.PROJECTILE_TAIL_SITE
  self.assertEqual((source,gate,original),(0x31f2d8,0x68ce20,0xa9424ff4) if initialize else (0x32744c,0x68ccd0,0x910603ff))
  self.assertEqual(nro[gate:gate+40],bytes(40))
  self.assertGreaterEqual(gate,0x68ce00 if initialize else 0x68ccc8);self.assertLessEqual(gate+40,0x68ce60 if initialize else 0x68cd00)
  block=patches.projectile_tail_gate(source,gate,original)
  self.assertEqual(struct.unpack('<8IQ',block)[:6],(0x10000110,0xc8dffe10,0xb4000070,0xaa1303e0 if initialize else 0xaa1c03e0,0xd63f0200,original))
  self.assertEqual(struct.unpack_from('<I',block,24)[0],patches.branch(gate+24,source+4))
  # CBZ从gate+8直接跳到gate+20重放ADD SP；不执行MOV/BLR，slot保持0。
  self.assertEqual(((struct.unpack_from('<I',block,8)[0]>>5)&0x7ffff)*4,12)
  self.assertEqual(block[32:],bytes(8))
  patched=bytearray(nro);patched[source:source+4]=struct.pack('<I',patches.branch(source,gate));patched[gate:gate+40]=block
  # 两个提前尾跳逐字保留；正常尾部后的原生epilogue也不改。
  self.assertEqual(patched[0x31f680:0x31f700],nro[0x31f680:0x31f700])
  self.assertEqual(patched[source+4:source+44],nro[source+4:source+44])
  cpp=r'''
#include "projectile_update_tail.hpp"
#include <fstream>
#include <iterator>
#include <vector>
#include <cassert>
int main(int n,char**v){assert(n==2);std::ifstream f(v[1],std::ios::binary);std::vector<unsigned char>b((std::istreambuf_iterator<char>(f)),{});using namespace isaac::runtime::projectile_tail;
const bool init=INITIALIZE;const auto function=init?kInitFunction:kFunction, length=init?kInitSize:kSize, site=init?kInitSite:kSite, gate=init?kInitGate:kGate,slot=init?kInitSlot:kSlot;
assert(ImageMatches(b.data(),b.size(),init));assert(!ImageMatches(b.data(),slot,init));
for(auto i:{function,site,site+4,gate,gate+24,function+length-1}){b[i]^=1;assert(!ImageMatches(b.data(),b.size(),init));b[i]^=1;}
assert(ImageMatches(b.data(),b.size(),init));}
'''
  with tempfile.TemporaryDirectory(prefix='projectile-tail-patch-')as tmp:
   p=Path(tmp);(p/'image').write_bytes(patched);(p/'test.cpp').write_text(cpp.replace('INITIALIZE','true' if initialize else 'false'))
   r=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test'),str(p/'image')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_update_boundary_gate_and_complete_function_guard(self):self.check_site(False)
 def test_initialization_boundary_gate_and_complete_function_guard(self):self.check_site(True)
