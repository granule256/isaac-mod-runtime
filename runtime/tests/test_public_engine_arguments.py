"""公开Lua默认参数必须与PC一致，原生跳板仍收到完整ABI实参。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import test_lua_entity_player as fixture
from . import test_support

MAIN = r'''
namespace LuaRuntime { void InstallPublicArgumentProbes(); }
extern "C" {
#include <lauxlib.h>
extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
}
std::uint32_t capturedCalls=0;
int BeginProbe(lua_State*){capturedCalls=g_HostEngineCallTrampolineCalls;return 0;}
int ProbeArguments(lua_State* L){
 const auto mode=luaL_checkinteger(L,1);
 if(mode==2){if(g_HostEngineCallTrampolineCalls!=capturedCalls)return luaL_error(L,"invalid call reached native code");return 0;}
 if(g_HostEngineCallTrampolineCalls!=capturedCalls+1)return luaL_error(L,"native call count mismatch");
 capturedCalls=g_HostEngineCallTrampolineCalls;
 const auto expectedTarget=g_EngineBase+(mode==0?kEntityPlayerAddHeartsOffset:kGameStartRoomTransitionOffset);
 if(g_HostEngineCallTrampolineLastTarget!=expectedTarget)return luaL_error(L,"native target mismatch");
 if(g_HostEngineCallTrampolineLastIntegers[0]!=(mode==0?AddressOf(g_PlayerBytes):AddressOf(g_GameBytes)))return luaL_error(L,"native receiver mismatch");
 if(mode==0){
  if(static_cast<std::uint32_t>(g_HostEngineCallTrampolineLastIntegers[1])!=static_cast<std::uint32_t>(luaL_checkinteger(L,2))||g_HostEngineCallTrampolineLastIntegers[2]!=static_cast<std::uint64_t>(luaL_checkinteger(L,3)))return luaL_error(L,"heart amount/bool mismatch");
 }else{
  for(int i:{1,2,3,5})if(static_cast<std::uint32_t>(g_HostEngineCallTrampolineLastIntegers[i])!=static_cast<std::uint32_t>(luaL_checkinteger(L,i+1)))return luaL_error(L,"room integer argument mismatch at %d",i);
  const auto player=luaL_checkinteger(L,5)!=0?AddressOf(g_PlayerBytes):0;
  if(g_HostEngineCallTrampolineLastIntegers[4]!=player)return luaL_error(L,"room player argument mismatch");
 }
 return 0;
}
int main(int argc,char**argv){
 if(argc!=2)return 90;
 static_cast<void>(&CorruptVtable);static_cast<void>(&PublishNullCostumes);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);
 CreateBlocks();FillPlayer(true);PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));PublishPlayers({AddressOf(g_PlayerBytes)});
 WriteAt<std::uint32_t>(g_ModuleBytes,kEntityPlayerAddHeartsOffset,kEntityPlayerAddHeartsEntryWord);
 WriteAt<std::uint32_t>(g_ModuleBytes,kGameStartRoomTransitionOffset,kGameStartRoomTransitionEntryWord);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 std::string script="local m=RegisterMod('public engine args',1);m:AddCallback(1,function() local p=Isaac.GetPlayer();local g=Game();BeginProbe();\n";
 if(!std::strcmp(argv[1],"hearts"))script+=R"lua(
assert(select('#',p:AddHearts(2))==0);ProbeArguments(0,2,0)
p:AddHearts(-1,false);ProbeArguments(0,-1,0)
p:AddHearts(3,true);ProbeArguments(0,3,1)
p:AddHearts(4,nil);ProbeArguments(0,4,0)
p:AddHearts(5,0);ProbeArguments(0,5,1)
p:AddHearts(6,{});ProbeArguments(0,6,1)
p:AddHearts('4294967298','');ProbeArguments(0,2,1)
p:AddHearts(7,true,'ignored');ProbeArguments(0,7,1)
assert(not pcall(function()p:AddHearts()end));ProbeArguments(2)
assert(not pcall(function()p:AddHearts(nil)end));ProbeArguments(2)
assert(not pcall(function()p:AddHearts('bad')end));ProbeArguments(2)
)lua";
 else script+=R"lua(
assert(select('#',g:StartRoomTransition(84,-1))==0);ProbeArguments(1,84,-1,0,0,-1)
g:StartRoomTransition(5,1,7);ProbeArguments(1,5,1,7,0,-1)
g:StartRoomTransition(6,2,nil,p,0);ProbeArguments(1,6,2,0,1,0)
g:StartRoomTransition(7,3,false,nil,false);ProbeArguments(1,7,3,0,0,-1)
g:StartRoomTransition(8,0,12,p,2,'ignored');ProbeArguments(1,8,0,12,1,2)
assert(not pcall(function()g:StartRoomTransition(1)end));ProbeArguments(2)
assert(not pcall(function()g:StartRoomTransition(1,'bad')end));ProbeArguments(2)
)lua";
 script+="_public_args={ok=1};end)";
 auto result=LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@public-engine-args.lua");
 if(result!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::InstallPublicArgumentProbes();
 LuaRuntime::DispatchPostUpdate();
 if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView entries[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(entries,8);for(std::size_t i=0;i<n;++i)std::printf("PUBLIC_ARGS_FAIL %s\n",entries[i].text);return 2;}
 double ok=0;return LuaRuntime::ReadLuaTableNumber("_public_args","ok",&ok)==0&&ok==1?0:3;
}
'''

class PublicEngineArgumentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='isaac-public-arguments-')
        code = fixture.HARNESS[:fixture.HARNESS.index('int main(')] + MAIN
        runtime = fixture.SOURCE/'lua_runtime.cpp'
        copied = Path(cls.temp.name)/'instrumented_runtime.cpp'
        copied.write_text(runtime.read_text()+r'''
int BeginProbe(lua_State*);
int ProbeArguments(lua_State*);
namespace LuaRuntime {
void InstallPublicArgumentProbes(){
 lua_pushcfunction(g_LuaState,::BeginProbe);lua_setglobal(g_LuaState,"BeginProbe");
 lua_pushcfunction(g_LuaState,::ProbeArguments);lua_setglobal(g_LuaState,"ProbeArguments");
}
}
''')
        sources = tuple(copied if source == runtime else source for source in test_support.layered_lua_runtime_sources(fixture.SOURCE))
        flags = tuple(flag for flag in test_support.HARNESS_COMPILE_FLAGS if not flag.startswith('-DEXL_DIAGNOSTIC_STAGE='))
        with patch.object(test_support, 'HARNESS_COMPILE_FLAGS', flags), patch.object(test_support, 'layered_lua_runtime_sources', return_value=sources):
            cls.binary = test_support.build_lua_harness(source_root=fixture.SOURCE, workdir=Path(cls.temp.name), harness_source=code)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self, scenario):
        result = subprocess.run([str(self.binary), scenario], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_add_hearts_optional_boolean_matches_pc_native_registers(self):
        self.check('hearts')

    def test_room_transition_defaults_match_pc_bootstrap(self):
        self.check('room')
