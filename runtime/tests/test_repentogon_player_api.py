"""EntityPlayer extension methods validate player identity and native results."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = PREFIX + r'''
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/repentogon_player_api.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <vector>
static std::vector<unsigned char> moduleBytes,player;
static int calls;
static std::int64_t Health(void* p){assert(p==player.data());++calls;return 4;}
static std::uintptr_t Marked(void* p){assert(p==player.data());++calls;return reinterpret_cast<std::uintptr_t>(player.data());}
static std::int64_t Local(void* p){assert(p==player.data());++calls;return 1;}
static void Extensions(lua_State* state) noexcept{
 isaac::runtime::PushEntityCallbackArgument(state,reinterpret_cast<std::uintptr_t>(player.data()));
 lua_setglobal(state,"player");
}
int main(){
 moduleBytes.assign(kEntityPlayerVtableOffset+16,0);
 player.assign(0x3000,0);
 const auto base=reinterpret_cast<std::uintptr_t>(moduleBytes.data());
 const auto vptr=base+kEntityPlayerVtableOffset;
 std::memcpy(player.data(),&vptr,sizeof(vptr));
 const std::uint32_t playerType=kEntityTypePlayer;std::memcpy(player.data()+kEntityTypeOffset,&playerType,4);
 LuaRuntime::SetEngineModuleBase(base);LuaRuntime::ObserveGameThread();
 Files files(true);SetSessionSaveFilePort(&files);
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 SetRepentogonPlayerGetHealthTypeHost(&Health);
 SetRepentogonPlayerGetMarkedTargetHost(&Marked);
 SetRepentogonPlayerIsLocalPlayerHost(&Local);
 LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
 const char* script=R"lua(
assert(player:GetHealthType()==4)
assert(GetPtrHash(player:GetMarkedTarget())==GetPtrHash(player))
assert(player:IsLocalPlayer())
assert(not pcall(function()player:GetHealthType(1)end))
assert(not pcall(function()player:GetMarkedTarget(1)end))
assert(not pcall(function()player:IsLocalPlayer(1)end))
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@player-extension.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(calls==3);assert(LuaRuntime::ShutdownForModReload());
 SetRepentogonPlayerGetHealthTypeHost(nullptr);SetRepentogonPlayerGetMarkedTargetHost(nullptr);
 SetRepentogonPlayerIsLocalPlayerHost(nullptr);repentogon::SetNativePort(nullptr);
 SetSessionSaveFilePort(nullptr);LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
}
'''


class RepentogonPlayerApiTests(unittest.TestCase):
    def test_native_getters_and_argument_gate(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-player-api-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
