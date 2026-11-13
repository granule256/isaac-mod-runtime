"""IsInGame follows the engine scene, not entry into a managed Lua callback."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_rng import DRIVER as RNG_DRIVER

SOURCE = Path(__file__).resolve().parents[1] / 'source'
PREFIX = RNG_DRIVER[:RNG_DRIVER.index('static unsigned calls;')]
DRIVER = PREFIX + r'''
#include "runtime_constants.hpp"
#include <vector>
static std::vector<unsigned char> moduleBytes,managerSlot,manager;
static int Scene(lua_State* state){
 const auto value=static_cast<std::uint32_t>(luaL_checkinteger(state,1));
 std::memcpy(manager.data()+kManagerRenderSceneOffset,&value,sizeof(value));return 0;
}
static void Extensions(lua_State* state) noexcept{
 lua_pushcfunction(state,Scene);lua_setglobal(state,"_scene");
}
int main(){
 moduleBytes.resize(kGameManagerGlobalSlotOffset+sizeof(std::uintptr_t));
 managerSlot.resize(sizeof(std::uintptr_t));manager.resize(0x50000);
 const auto slot=reinterpret_cast<std::uintptr_t>(managerSlot.data());
 const auto object=reinterpret_cast<std::uintptr_t>(manager.data());
 std::memcpy(moduleBytes.data()+kGameManagerGlobalSlotOffset,&slot,sizeof(slot));
 std::memcpy(managerSlot.data(),&object,sizeof(object));
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(moduleBytes.data()));
 Files files(true);SetSessionSaveFilePort(&files);LuaRuntime::ObserveGameThread();
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
 const char* script=R"lua(
assert(REPENTOGON and REPENTOGON.FullCompatibility==false)
_scene(2);assert(Isaac.IsInGame(),'gameplay scene must be true even at script load')
_scene(1);assert(not Isaac.IsInGame())
_scene(5);assert(not Isaac.IsInGame())
local m=RegisterMod('scene-contract',1)
m:AddCallback(ModCallbacks.MC_POST_UPDATE,function()
 _scene(1);assert(not Isaac.IsInGame(),'managed callback does not imply gameplay')
 _scene(2);assert(Isaac.IsInGame())
end)
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@scene-contract.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 LuaRuntime::DispatchPostUpdate();assert(!LuaRuntime::TakeCallbackError());
 assert(LuaRuntime::ShutdownForModReload());
 LuaRuntime::SetRuntimeExtensionInstaller(nullptr);repentogon::SetNativePort(nullptr);
 SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonInGameTests(unittest.TestCase):
    def test_scene_in_loading_and_callback_contexts(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-scene-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
