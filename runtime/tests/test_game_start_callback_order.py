"""真实派发器验证PC开局次序、读数重试和同地址玩家的新局初始化。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import test_lua_entity_player as fixture
from . import test_support

ROOT = Path(__file__).resolve().parents[2]
MAIN = r'''
bool locationReady=true;
GameRoomObservation ReadGameLocationKey(uintptr_t,GameLocationKey* key){
 if(!locationReady)return GameRoomObservation::GameUnreadable;
 *key={84,0,1,0};return GameRoomObservation::Success;
}
int main(int argc,char**argv){
 if(argc!=2)return 90;
 static_cast<void>(&CorruptVtable);static_cast<void>(&PublishNullCostumes);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);
 CreateBlocks();FillPlayer(true);PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));PublishPlayers({AddressOf(g_PlayerBytes)});
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const bool continued=std::strcmp(argv[1],"fresh")!=0&&std::strcmp(argv[1],"reused")!=0;
 std::string script=continued?"local expectContinued=true\n":"local expectContinued=false\n";
 script+=R"lua(
local m=RegisterMod('PC startup order',1)
local trace=''
_start={init=0,room=0,level=0,started=0,updates=0}
local shared={}
m:AddPriorityCallback(9,-100,function(_,player)
 assert(type(player)=='userdata')
 _start.init=_start.init+1
 trace='9,'
 shared.Level=true
end)
m:AddCallback(19,function()
 assert(shared.Level,'NEW_ROOM before PLAYER_INIT')
 _start.room=_start.room+1;trace=trace..'19,'
end)
m:AddCallback(18,function()
 assert(trace=='9,19,','NEW_LEVEL before NEW_ROOM')
 _start.level=_start.level+1;trace=trace..'18,'
end)
m:AddCallback(15,function(_,isContinued)
 assert(type(isContinued)=='boolean' and isContinued==expectContinued)
 assert(shared.Level,'StageAPI shared.Level unavailable in GAME_STARTED')
 assert(trace=='9,19,18,','GAME_STARTED before initial room/level callbacks: '..trace)
 _start.started=_start.started+1;trace=trace..'15,'
end)
m:AddCallback(1,function()
 assert(trace=='9,19,18,15,','POST_UPDATE before startup callbacks: '..trace)
 _start.updates=_start.updates+1
end)
)lua";
 auto result=LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@startup-order.lua");
 if(result!=LuaRuntime::LuaInitResult::Success)return 1;
 auto errors=[](){if(!LuaRuntime::TakeCallbackError())return false;LuaRuntime::LuaErrorHistoryEntryView entries[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(entries,8);for(std::size_t i=0;i<n;++i)std::printf("STARTUP_CALLBACK_FAIL %s\n",entries[i].text);return true;};
 auto number=[](const char* field,double expected){double actual=-1;return LuaRuntime::ReadLuaTableNumber("_start",field,&actual)==0&&actual==expected;};
 if(!std::strcmp(argv[1],"retry"))locationReady=false;
 LuaRuntime::NoteGameStarted(continued);LuaRuntime::DispatchPostUpdate();
 if(errors())return 2;
 if(!locationReady){
  if(!number("init",1)||!number("started",0)||!number("updates",0))return 3;
  locationReady=true;LuaRuntime::DispatchPostUpdate();if(errors())return 4;
 }
 if(!number("init",1)||!number("room",1)||!number("level",1)||!number("started",1)||!number("updates",1))return 5;
 LuaRuntime::DispatchPostUpdate();if(errors())return 6;
 if(!number("init",1)||!number("room",1)||!number("level",1)||!number("started",1)||!number("updates",2))return 7;
 if(!std::strcmp(argv[1],"reused")){
  LuaRuntime::NoteGameStarted(false);LuaRuntime::DispatchPostUpdate();if(errors())return 8;
  if(!number("init",2)||!number("room",2)||!number("level",2)||!number("started",2)||!number("updates",3))return 9;
 }
 return 0;
}
'''

class GameStartCallbackOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='isaac-startup-order-')
        code = fixture.HARNESS[:fixture.HARNESS.index('int main(')] + MAIN
        flags = tuple(flag for flag in test_support.HARNESS_COMPILE_FLAGS if not flag.startswith('-DEXL_DIAGNOSTIC_STAGE='))
        with patch.object(test_support, 'HARNESS_COMPILE_FLAGS', flags):
            cls.binary = test_support.build_lua_harness(source_root=fixture.SOURCE, workdir=Path(cls.temp.name), harness_source=code)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self, scenario):
        result = subprocess.run([str(self.binary), scenario], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_fresh_run_uses_pc_callback_order(self):
        self.check('fresh')

    def test_continued_run_uses_pc_callback_order(self):
        self.check('continued')

    def test_room_identity_retry_does_not_repeat_player_init(self):
        self.check('retry')

    def test_new_run_reinitializes_player_at_reused_address(self):
        self.check('reused')
