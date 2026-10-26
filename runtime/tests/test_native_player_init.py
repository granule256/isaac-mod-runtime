"""真实Lua派发验证出生初始化早于零血死亡判定，且不被后续扫描重复。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import test_lua_entity_player as fixture
from . import test_support

MAIN = r'''
#if __has_include("native_player_init.hpp")
#include "native_player_init.hpp"
static void NativeInit(std::uintptr_t entity){LuaRuntime::DispatchNativePlayerInit(entity);}
#else
static void NativeInit(std::uintptr_t){}
#endif
GameRoomObservation ReadGameLocationKey(uintptr_t,GameLocationKey* key){
 *key={84,0,1,0};return GameRoomObservation::Success;
}
int main(int argc,char**argv){
 if(argc!=2)return 90;
 static_cast<void>(&CorruptVtable);static_cast<void>(&PublishNullCostumes);
 static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);
 CreateBlocks();FillPlayer(true);PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));
 WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));PublishPlayers({AddressOf(g_PlayerBytes)});
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const char* script=R"lua(
 local m=RegisterMod('native zero health birth',1)
 born=0;started=0;updates=0
 m:AddCallback(9,function(_,p)
  assert(not p:IsDead(),'PLAYER_INIT arrived after engine death check')
  born=born+1;p:GetData().InitializedBeforeDeathCheck=true
 end)
 m:AddCallback(15,function()started=started+1 end)
 m:AddCallback(1,function()updates=updates+1 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@native-player-init.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto number=[](const char*key,double expected){double value=-1;return LuaRuntime::ReadLuaGlobalNumber(key,&value)&&value==expected;};
 auto errors=[](){if(!LuaRuntime::TakeCallbackError())return false;char e[1024]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::fprintf(stderr,"%s\n",e);return true;};
 WriteAt<std::uint8_t>(g_PlayerBytes,kEntityIsDeadOffset,0);
 NativeInit(AddressOf(g_PlayerBytes));
 if(errors()||!number("born",1)){std::fprintf(stderr,"native PLAYER_INIT did not reach real Lua callback\n");return 11;}
 // 模拟引擎紧随出生发生的死亡判定；作者必须已经有机会初始化生命。
 if(!number("born",1))WriteAt<std::uint8_t>(g_PlayerBytes,kEntityIsDeadOffset,1);
 LuaRuntime::NoteGameStarted(false);LuaRuntime::DispatchPostUpdate();
 if(errors()||!number("born",1)||!number("started",1)||!number("updates",1))return 12;
 LuaRuntime::DispatchPostUpdate();
 if(errors()||!number("born",1))return 13;
 if(!std::strcmp(argv[1],"reused")){
  // 指针相同，真实Init调用代表新生命周期，不能拿地址缓存吞掉它。
  WriteAt<std::uint8_t>(g_PlayerBytes,kEntityIsDeadOffset,0);
  NativeInit(AddressOf(g_PlayerBytes));
  if(errors()||!number("born",2))return 14;
  LuaRuntime::NoteGameStarted(false);LuaRuntime::DispatchPostUpdate();
  if(errors()||!number("born",2)||!number("started",2))return 15;
 }
 if(!std::strcmp(argv[1],"invalid")){
  NativeInit(0);CorruptVtable();
  NativeInit(AddressOf(g_PlayerBytes));
  if(errors()||!number("born",1))return 16;
 }
 return 0;
}
'''

class NativePlayerInitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='isaac-native-player-init-')
        code=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
        flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
        with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
            cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.temp.name),harness_source=code)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def check(self,name):
        result=subprocess.run([str(self.binary),name],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_birth_precedes_zero_health_death_check(self):self.check('fresh')
    def test_reused_player_address_is_initialized_once_each_lifecycle(self):self.check('reused')
    def test_invalid_native_receiver_does_not_dispatch(self):self.check('invalid')
