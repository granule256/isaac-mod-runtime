"""StageAPI closes room doors without supplying Force."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_batch304_grid_entity_vtable as grid
from . import test_support


MAIN = r'''
int main(int argc,char**argv){
 if(argc!=2)return 90;
 PublishFakeWorld(0x1111,0x2222,0x3333);
 g_RoomBytes.resize(0x2000);
 WriteAt<std::uintptr_t>(g_OwnerSlotBytes,0,AddressOf(g_RoomBytes));
 WriteAt<std::uintptr_t>(g_GridABytes,0,g_EngineBase+kGridEntity_DoorVtableOffset);
 WriteAt<std::uint32_t>(g_GridABytes,kGridEntityTypeOffset,7);
 WriteAt<std::uintptr_t>(g_RoomBytes,0xe30,AddressOf(g_GridABytes));
 // Keep native code absent: the real Lua handler still validates this live door.
 LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x3040);
 const std::string script=std::string("local d=Game():GetRoom():GetDoor(0);assert(d);assert(select('#',d:Close(")+argv[1]+"))==0);local m=RegisterMod('door defaults',1);m:AddCallback(1,function()end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@door-close-defaults.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[512]{};(void)LuaRuntime::CopyLastLuaErrorText(error,sizeof(error));std::fprintf(stderr,"%s\n",error);return 1;
 }
 if(g_HostEngineCallTrampolineCalls!=0)return 2;
 return 0;
}
'''


class DoorCloseDefaultsTests(unittest.TestCase):
 def test_stageapi_omitted_force_and_lua_boolean_arguments_are_accepted(self):
  with tempfile.TemporaryDirectory(prefix='door-close-defaults-') as folder:
   binary=test_support.build_lua_harness(source_root=grid.SOURCE,workdir=Path(folder),
       harness_source=grid.HARNESS.split('int main(',1)[0]+MAIN)
   for argument in ['', 'nil', 'false', 'true', '0', "''", '{}', 'nil,true']:
    with self.subTest(argument=argument):
     result=subprocess.run([str(binary),argument],text=True,capture_output=True)
     self.assertEqual(result.returncode,0,result.stdout+result.stderr)
