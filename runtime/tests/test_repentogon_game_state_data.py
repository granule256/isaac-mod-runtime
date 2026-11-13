"""Hourglass prerequisites snapshot real per-mod game tables before callbacks."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support
from .test_repentogon_in_game import PREFIX
SOURCE=Path(__file__).resolve().parents[1]/'source'
DRIVER=PREFIX+r'''
#include "interfaces/lua/repentogon_game_state_data.hpp"
#include <cstdio>
static int Store(lua_State* L){RepentogonStoreGameStateData(static_cast<int>(luaL_checkinteger(L,1)));return 0;}
static int Restore(lua_State* L){RepentogonRestoreGameStateData(static_cast<int>(luaL_checkinteger(L,1)));return 0;}
static void Extensions(lua_State* L) noexcept {
 lua_pushcfunction(L,Store);lua_setglobal(L,"_store");
 lua_pushcfunction(L,Restore);lua_setglobal(L,"_restore");
}
int main(){
 LuaRuntime::ObserveGameThread();Files files(true);SetSessionSaveFilePort(&files);
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
 const char* script=R"lua(
local m=RegisterMod('state-snapshot',1)
local n=RegisterMod('state-second',1)
local data=SaveStateManager.GetGameData(m)
data.number=7;data.self=data
local child={value=3};data.a=child;data.b=child;data.bad=function()end
SaveStateManager.GetGameData(n).number=19
_store(1)
data.number=99;child.value=45
_store(2)
_restore(1)
local old=SaveStateManager.GetGameData(m)
assert(old~=data and old.number==7 and old.self==old)
assert(old.a==old.b and old.a.value==3 and old.bad==nil)
assert(SaveStateManager.GetGameData(n).number==19)
_restore(2)
assert(SaveStateManager.GetGameData(m).number==99)
_restore(42)
assert(next(SaveStateManager.GetGameData(m))==nil)
SaveStateManager.GetGameData(m).number=3
SaveStateManager.ClearGameData(m)
assert(next(SaveStateManager.GetGameData(m))==nil)
assert(not pcall(SaveStateManager.GetGameData,{}))
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@state-data.lua")!=LuaRuntime::LuaInitResult::Success){
 char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(LuaRuntime::ShutdownForModReload());LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
 repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
}
'''
class GameStateDataTests(unittest.TestCase):
 def test_mod_tables_cycles_aliases_and_independent_slots(self):
  with tempfile.TemporaryDirectory(prefix='rgon-game-state-') as tmp:
   binary=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(tmp),harness_source=DRIVER)
   result=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
