"""Door callbacks must receive the existing door view, including door-only fields."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from . import test_support
from .test_repentogon_callbacks import RUNTIME_DRIVER,SOURCE

DRIVER=RUNTIME_DRIVER.replace('#include "lua_runtime.hpp"','#include "lua_runtime.hpp"\n#include "lua_runtime_state.hpp"')
DRIVER=DRIVER.replace('    if(mode=="off"||mode=="none"){',r'''
    if(mode=="door") {
        script+="m:AddCallback(1402,function(_,door) assert(door.TargetRoomIndex==42);calls=calls+1 end,16)";
    }else if(mode=="off"||mode=="none"){
''',1)
DRIVER=DRIVER.replace('        if(mode=="catalog"){',r'''
        if(mode=="door") {
            constexpr std::uintptr_t base=0x10000000;
            LuaRuntime::SetEngineModuleBase(base);
            const std::uintptr_t vtable=base+kGridEntity_DoorVtableOffset;
            const unsigned type=16;const std::int32_t slot=3,target=42;
            std::memcpy(grid,&vtable,sizeof(vtable));
            std::memcpy(grid+kGridEntityTypeOffset,&type,sizeof(type));
            std::memcpy(grid+kGridEntityDoorSlotOffset,&slot,sizeof(slot));
            std::memcpy(grid+kGridEntityDoorTargetRoomIndexOffset,&target,sizeof(target));
            send(1402,EventKind::Grid);Check();assert(Number("calls")==1);
            LuaRuntime::SetEngineModuleBase(0);
        }else if(mode=="catalog"){
''',1)
class DoorArgumentTests(unittest.TestCase):
 def test_existing_door_fields_available_in_grid_callback(self):
  with tempfile.TemporaryDirectory() as task_dir:
   binary=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(task_dir),harness_source=DRIVER)
   result=subprocess.run([str(binary),'door'],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
