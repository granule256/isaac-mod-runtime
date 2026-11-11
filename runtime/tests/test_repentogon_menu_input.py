"""Menu input uses callback 1464 outside the gameplay managed gate."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = PREFIX + r'''
#include "runtime_constants.hpp"
#include <vector>
static std::vector<unsigned char> moduleBytes,manager;
int main(){
 moduleBytes.resize(kGameManagerGlobalSlotOffset+sizeof(std::uintptr_t));
 manager.assign(0x100,0);
 const auto object=reinterpret_cast<std::uintptr_t>(manager.data());
 std::memcpy(moduleBytes.data()+kGameManagerGlobalSlotOffset,&object,sizeof(object));
 const std::uint32_t menuScene=1;
 std::memcpy(manager.data()+kManagerRenderSceneOffset,&menuScene,sizeof(menuScene));
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(moduleBytes.data()));
 Files files(true);SetSessionSaveFilePort(&files);LuaRuntime::ObserveGameThread();
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 const char* script=R"lua(
local m=RegisterMod('menu-input',1)
m:AddCallback(ModCallbacks.MC_MENU_INPUT_ACTION,function(_,entity,hook,action)
 assert(entity==nil and hook==0 and action==20)
 _G.menu_input_calls=(_G.menu_input_calls or 0)+1
 return false
end,0)
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@menu-input.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 const auto blocked=LuaRuntime::DispatchLogicalInputAction(20,0,0);
 assert(blocked.overridden&&!blocked.boolean);
 double calls=0;assert(LuaRuntime::ReadLuaGlobalNumber("menu_input_calls",&calls)&&calls==1);
 assert(LuaRuntime::ShutdownForModReload());
 repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonMenuInputTests(unittest.TestCase):
    def test_menu_scene_dispatches_1464_with_override(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-menu-input-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
