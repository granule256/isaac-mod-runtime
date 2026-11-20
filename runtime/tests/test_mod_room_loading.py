"""验证本体STB成功后才合并模组房间，并保留原生参数与bool结果。"""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
PROGRAM=r'''
#include "application/mod/mod_room_loading.hpp"
#include <cstdio>
struct Config {int count, id, stage, mode, calls;bool success;};
bool Base(void* pointer,int stage,int mode){auto& c=*static_cast<Config*>(pointer);c.calls=c.calls*10+1;c.stage=stage;c.mode=mode;c.count=1;c.id=1;return c.success;}
void Mods(void* pointer,int stage,int mode){auto& c=*static_cast<Config*>(pointer);if(c.stage!=stage||c.mode!=mode||c.count!=1)__builtin_trap();c.calls=c.calls*10+2;c.count=2;c.id=70050;}
int main(){
 for(int mode:{0,1,-1}){
  Config c{0,0,0,0,0,true};isaac::runtime::ModRoomLoadBindings n{Base,Mods};
  if(!isaac::runtime::LoadStageRoomsWithMods(n,&c,1,mode))return 1;
  if(c.count!=2||c.id!=70050||c.calls!=12){std::puts("mod room 70050 missing after successful base load");return 2;}
  if(c.stage!=1||c.mode!=mode)return 3;
 }
 Config fail{0,0,0,0,0,false};isaac::runtime::ModRoomLoadBindings n{Base,Mods};
 if(isaac::runtime::LoadStageRoomsWithMods(n,&fail,36,1)||fail.calls!=1)return 4;
 Config noMods{0,0,0,0,0,true};n.append=nullptr;
 if(!isaac::runtime::LoadStageRoomsWithMods(n,&noMods,0,0)||noMods.calls!=1)return 5;
}
'''.replace('#include <cstdio>','#include <cstdio>\n#include <initializer_list>')
PENDING_PROGRAM=r'''
#include "application/mod/mod_room_loading.hpp"
#include <cstddef>

int main() {
    using isaac::runtime::ModRoomPendingLoads;
    ModRoomPendingLoads pending;
    int stage = -1;
    int mode = -1;
    if (!pending.Empty() || pending.Size() != 0 || pending.Peek(&stage, &mode)) return 1;
    if (!pending.Add(1, -1) || !pending.Add(1, -1) || pending.Size() != 1) return 2;
    if (!pending.Peek(&stage, &mode) || stage != 1 || mode != -1) return 3;
    if (!pending.Add(36, 1) || pending.Size() != 2) return 4;
    if (pending.Add(37, 0) || pending.Add(-1, 0) || pending.Add(2, 2)) return 5;
    if (!pending.Remove(1, -1) || pending.Size() != 1) return 6;
    if (!pending.Peek(&stage, &mode) || stage != 36 || mode != 1) return 7;
    pending.Clear();
    if (!pending.Empty() || pending.Peek(&stage, &mode)) return 8;
}
'''
class ModRoomLoadingTests(unittest.TestCase):
 def test_successful_native_load_merges_mod_rooms_without_changing_arguments_or_failure(self):
  with tempfile.TemporaryDirectory(prefix='isaac-mod-rooms-') as temp:
   source=Path(temp)/'test.cpp';source.write_text(PROGRAM);binary=Path(temp)/'test'
   subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),str(source),'-o',str(binary)],check=True,capture_output=True)
   result=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)

 def test_unready_stage_loads_are_kept_for_one_later_replay(self):
  with tempfile.TemporaryDirectory(prefix='isaac-mod-room-pending-') as temp:
   source=Path(temp)/'test.cpp';source.write_text(PENDING_PROGRAM);binary=Path(temp)/'test'
   subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),str(source),'-o',str(binary)],check=True,capture_output=True)
   result=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
