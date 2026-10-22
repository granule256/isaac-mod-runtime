"""从生产源码抽真实类型，AArch64实执行核x0房间与s0/s1位置、signed w0返回。"""
import platform,re,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class RoomCollisionHfaTests(unittest.TestCase):
 def test_real_aarch64_by_value_position(self):
  if platform.machine() not in ('arm64','aarch64'):self.skipTest('需要AArch64宿主')
  text=(ROOT/'runtime/src/interfaces/lua/remaining_api.cpp').read_text()
  types=text.split('struct AgonyRoomVector',1)[1].split('int RoomGetGridCollisionAtPos',1)[0]
  types='struct AgonyRoomVector'+types
  darwin=platform.system()=='Darwin';prefix='_' if darwin else ''
  def address(reg,name):
   return f'adrp {reg}, _{name}@PAGE\nadd {reg},{reg},_{name}@PAGEOFF\n' if darwin else f'adrp {reg},{name}\nadd {reg},{reg},:lo12:{name}\n'
  asm=f'.text\n.global {prefix}collision_abi\n.align 2\n{prefix}collision_abi:\n'+address('x9','receiver')+'str x0,[x9]\n'+address('x9','position')+'stp s0,s1,[x9]\nmov w0,#-4\nret\n'
  driver='#include <cstdint>\n#include <cstddef>\n#include <cassert>\n'+types+r'''
extern "C" {std::uintptr_t receiver{};float position[2]{};std::int32_t collision_abi(std::uintptr_t,AgonyRoomVector);}
int main(){AgonyRoomCollisionFn fn=&collision_abi;assert(fn(0x12345678,{1.25F,-2.5F})==-4);assert(receiver==0x12345678&&position[0]==1.25F&&position[1]==-2.5F);}
'''
  with tempfile.TemporaryDirectory(prefix='isaac-room-hfa-') as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(driver);(p/'test.s').write_text(asm)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror',str(p/'test.cpp'),str(p/'test.s'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
