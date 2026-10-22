"""PC启动包装的ChangeRoom缺省值必须经过真实Lua入口并抵达完整原生ABI。"""
import subprocess
from unittest.mock import patch
from . import test_public_engine_arguments as public

EXTRA=r'''
#include "interfaces/lua/api100_scalar.hpp"
#include "infrastructure/call/engine_call_access.hpp"
extern "C" {
#include <lauxlib.h>
}
#include "interfaces/lua/api100_scalar.guards.hpp"
unsigned levelCalls=0,levelProbed=0;std::int32_t levelRoom=0,levelDimension=0;
void LevelNative(void* self,std::int32_t room,std::int32_t dim){if(self!=g_GameBytes.data())std::abort();++levelCalls;levelRoom=room;levelDimension=dim;}
int ProbeLevel(lua_State* L){if(levelCalls!=levelProbed+1||levelRoom!=luaL_checkinteger(L,1)||levelDimension!=luaL_checkinteger(L,2))return luaL_error(L,"Level ChangeRoom native argument mismatch");++levelProbed;return 0;}
'''
GAME=r'''assert(select('#',g:ChangeRoom(84))==0);ProbeArguments(3,84,-1)
g:ChangeRoom(5,nil);ProbeArguments(3,5,-1)
g:ChangeRoom(6,false);ProbeArguments(3,6,-1)
g:ChangeRoom(7,0);ProbeArguments(3,7,0)
g:ChangeRoom(8,1,'ignored');ProbeArguments(3,8,1)
assert(not pcall(function()g:ChangeRoom()end));ProbeArguments(2)
assert(not pcall(function()g:ChangeRoom(nil)end));ProbeArguments(2)
assert(not pcall(function()g:ChangeRoom(1,'bad')end));ProbeArguments(2)
'''
LEVEL=r'''local l=g:GetLevel()
assert(select('#',l:ChangeRoom(84))==0);ProbeLevel(84,-1)
l:ChangeRoom(5,nil);ProbeLevel(5,-1)
l:ChangeRoom(6,false);ProbeLevel(6,-1)
l:ChangeRoom(7,0);ProbeLevel(7,0)
l:ChangeRoom(8,1,'ignored');ProbeLevel(8,1)
assert(not pcall(function()l:ChangeRoom()end))
assert(not pcall(function()l:ChangeRoom(nil)end))
assert(not pcall(function()l:ChangeRoom(1,'bad')end))
'''
MAIN=public.MAIN.replace('namespace LuaRuntime { void InstallPublicArgumentProbes(); }',EXTRA+'\nnamespace LuaRuntime { void InstallPublicArgumentProbes(); }')
MAIN=MAIN.replace('const auto expectedTarget=g_EngineBase+(mode==0?kEntityPlayerAddHeartsOffset:kGameStartRoomTransitionOffset);','const auto expectedTarget=g_EngineBase+(mode==0?kEntityPlayerAddHeartsOffset:(mode==3?kGameChangeRoomOffset:kGameStartRoomTransitionOffset));')
MAIN=MAIN.replace(' if(mode==0){',' if(mode==3){for(int i=1;i<=2;++i)if(static_cast<std::uint32_t>(g_HostEngineCallTrampolineLastIntegers[i])!=static_cast<std::uint32_t>(luaL_checkinteger(L,i+1)))return luaL_error(L,"Game ChangeRoom native argument mismatch");return 0;}\n if(mode==0){')
MAIN=MAIN.replace(' LuaRuntime::SetEngineModuleBase(g_EngineBase);',r''' WriteAt<std::uint32_t>(g_ModuleBytes,kGameChangeRoomOffset,kGameChangeRoomEntryWord);
 std::memcpy(g_ModuleBytes.data()+isaac::runtime::api100_scalar::kLevelChangeRoomEntry,isaac::runtime::api100_scalar::kLevelChangeRoomGuard.data(),16);
 isaac::runtime::Api100ScalarNativeTestBindings bindings{};bindings.methods[14]=isaac::runtime::engine_call::AddressOfFunction(&LevelNative);isaac::runtime::SetApi100ScalarNativeTestBindings(bindings);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);''')
MAIN=MAIN.replace(' if(!std::strcmp(argv[1],"hearts"))script+=R"lua(', ' if(!std::strcmp(argv[1],"gamechange"))script+=R"lua('+GAME+')lua";\n else if(!std::strcmp(argv[1],"levelchange"))script+=R"lua('+LEVEL+')lua";\n else if(!std::strcmp(argv[1],"hearts"))script+=R"lua(')
# 通过已有观测器的mode4检查Level入口，不改生产注册或既有断言。
MAIN=MAIN.replace(' const auto mode=luaL_checkinteger(L,1);',' const auto mode=luaL_checkinteger(L,1);if(mode==4){lua_remove(L,1);return ProbeLevel(L);}')
for room,dimension in [(84,-1),(5,-1),(6,-1),(7,0),(8,1)]:
 MAIN=MAIN.replace(f'ProbeLevel({room},{dimension})',f'ProbeArguments(4,{room},{dimension})')
class RoomChangeDefaultsTests(public.PublicEngineArgumentsTests):
 @classmethod
 def setUpClass(cls):
  with patch.object(public,'MAIN',MAIN):super().setUpClass()
 def test_game_room_change_default_dimension_reaches_native(self):self.check('gamechange')
 def test_level_room_change_default_dimension_reaches_native(self):self.check('levelchange')
