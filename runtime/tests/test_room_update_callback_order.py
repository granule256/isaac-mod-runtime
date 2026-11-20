"""Real Lua/production dispatch: initialize new-room state before its first update.

The grid tracker is an independent minimal sample, with no author/game payload.
Native room identity, grid presence and simulation frames are host inputs; the
callback registry, Lua invocation, lifecycle and frame deduplication are real.
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from . import test_lua_entity_query as fixture
from . import test_support

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = r'''
extern "C" int RoomOrderHash(lua_State*);
extern "C" int RoomOrderGrid(lua_State*);
extern "C" int RoomOrderReenter(lua_State*);
extern "C" void InstallRoomOrderInputs() {
    lua_pushcfunction(LuaRuntime::g_LuaState, RoomOrderHash);
    lua_setglobal(LuaRuntime::g_LuaState, "TestRoomHash");
    lua_pushcfunction(LuaRuntime::g_LuaState, RoomOrderGrid);
    lua_setglobal(LuaRuntime::g_LuaState, "TestGridAlive");
    lua_pushcfunction(LuaRuntime::g_LuaState, RoomOrderReenter);
    lua_setglobal(LuaRuntime::g_LuaState, "TestReenterUpdate");
}
'''
MAIN = r'''
#include "native_room_events.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"
#include <cassert>
extern "C" {
#include <lua.h>
void InstallRoomOrderInputs();
}
static GameLocationKey currentLocation{84,0,1,0};
static unsigned nativeFrame=10,locationReads{},roomVisits{},playerVisits{},reentries{};
static bool gridAlive=true,paused{},loadFromEntity{};
extern "C" void RoomOrderVisitRoom(){++roomVisits;}
extern "C" void RoomOrderVisitPlayer(){++playerVisits;}
extern "C" int RoomOrderHash(lua_State*L){lua_pushinteger(L,currentLocation.roomIndex);return 1;}
extern "C" int RoomOrderGrid(lua_State*L){lua_pushboolean(L,gridAlive);return 1;}
extern "C" int RoomOrderReenter(lua_State*){
 ++reentries;
 if(loadFromEntity){currentLocation.roomIndex=86;isaac::runtime::NoteNativeRoomLoaded();}
 else LuaRuntime::DispatchPostUpdate();
 return 0;
}
GameRoomObservation ReadGameLocationKey(uintptr_t,GameLocationKey*key){
 ++locationReads;*key=currentLocation;return GameRoomObservation::Success;
}
GameIsPausedObservation ObserveGameIsPaused(uintptr_t,uintptr_t){
 return paused?GameIsPausedObservation::PausedTrue:GameIsPausedObservation::PausedFalse;
}
static bool Snapshot(isaac::runtime::ManagedUpdateSnapshot*out)noexcept{
 *out={AddressOf(g_GameBytes),nativeFrame};return true;
}
static bool Number(const char*name,double expected){return ExpectNumber(name,expected);}
static bool Dispatch(){
 LuaRuntime::DispatchPostUpdate();
 assert(isaac::runtime::EngineGuardDispatchActive().load()==0);
 if(!LuaRuntime::TakeCallbackError())return true;
 char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
 std::fprintf(stderr,"%s\n",error);return false;
}
int main(int argc,char**argv){
 assert(argc==2);const std::string mode=argv[1];
 loadFromEntity=mode=="player_load"||mode=="effect_load"||mode=="peffect_load"||mode=="startup_load";
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 if(mode=="peffect_type")
   WriteAt<std::uint32_t>(g_Entities[kPlayer],kEntityPlayerTypeOffset,58);
 LuaRuntime::ObserveGameThread();LuaRuntime::SetEngineModuleBase(g_EngineBase);
 LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0);
 std::string script=mode=="reentry"?"requestReentry=true\n":"";
 if(mode=="startup_load")script+="startupLoad=true;requestStartupLoad=true\n";
 if(loadFromEntity&&mode!="startup_load")script+="entityLoadTest=true\n";
 if(mode=="peffect_load")script+="requestPeffectLoad=true\n";
 if(mode=="peffect_type")script+=R"lua(
 local m=RegisterMod('player filter regression',1)
 peffectType=0;peffectVariant=0;playerUpdateVariant=0
 m:AddCallback(4,function(_,player)
   assert(player:GetPlayerType()==58 and player.Variant==0)
   peffectType=peffectType+1
 end,58)
 m:AddCallback(4,function()peffectVariant=peffectVariant+1 end,0)
 m:AddCallback(31,function()playerUpdateVariant=playerUpdateVariant+1 end,0)
 )lua";
 if(mode=="late_listener")script+="lateListener=true\n";
 if(mode=="player_load")script+="requestEntityLoad=true\n";
 if(mode=="effect_load")script+="requestEffectLoad=true\n";
 script+=R"lua(
 local m=RegisterMod('independent room grid tracker',1)
 rooms=0;levels=0;started=0;updates=0;destroyed=0;roomA=0;roomB=0;lateUpdates=0
 local destroyedGrids,trackedGrids={},{}
 m:AddCallback(19,function()
   local hash=TestRoomHash()
   if hash==85 then roomA=roomA+1 elseif hash==86 then roomB=roomB+1 end
   if not destroyedGrids[hash] then destroyedGrids[hash]={} end
   trackedGrids={}
   if TestGridAlive() and not destroyedGrids[hash][0] then trackedGrids[0]=true end
   rooms=rooms+1
   if lateListener and rooms==2 then m:AddCallback(31,function()lateUpdates=lateUpdates+1 end) end
   if requestStartupLoad then requestStartupLoad=false;TestReenterUpdate() end
   if requestReentry and started>0 then TestReenterUpdate() end
 end)
 m:AddCallback(18,function() assert(rooms>levels);levels=levels+1 end)
 m:AddCallback(15,function() assert(rooms==(startupLoad and 2 or 1) and levels==1);started=started+1 end)
 m:AddCallback(1,function()
   local hash=TestRoomHash()
   for i in pairs(trackedGrids) do
     if not TestGridAlive() then
       destroyedGrids[hash][i]=true
       trackedGrids[i]=nil
       destroyed=destroyed+1
     end
   end
   assert(destroyedGrids[hash], 'POST_UPDATE before NEW_ROOM initialization')
   updates=updates+1
 end)
 -- Keep production entity scanning enabled to check its cost and deduplication.
 m:AddCallback(0,function() end)
 m:AddCallback(4,function()
   if requestPeffectLoad and updates>0 then requestPeffectLoad=false;TestReenterUpdate() end
 end)
 if not lateListener then m:AddCallback(31,function()
   if entityLoadTest and updates>0 then
     assert(destroyedGrids[TestRoomHash()], 'player update before NEW_ROOM initialization')
   end
   if requestEntityLoad and updates>0 then requestEntityLoad=false;TestReenterUpdate() end
 end) end
 m:AddCallback(55,function()
   if requestEffectLoad and updates>0 then requestEffectLoad=false;TestReenterUpdate() end
 end,7)
 )lua";
 assert(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@room-grid-tracker.lua")==LuaRuntime::LuaInitResult::Success);
 InstallRoomOrderInputs();isaac::runtime::SetManagedUpdateSnapshotReaderForTest(Snapshot);
 LuaRuntime::NoteGameStarted(false);if(!Dispatch())return 1;
 if(mode=="peffect_type"){
   assert(Number("peffectType",1)&&Number("peffectVariant",0)&&Number("playerUpdateVariant",1));
   return 0;
 }
 if(mode=="startup_load"){
   assert(Number("rooms",1)&&Number("levels",1)&&Number("started",0)&&Number("updates",0));
   ++nativeFrame;if(!Dispatch())return 11;
   assert(Number("rooms",2)&&Number("levels",1)&&Number("started",1)&&Number("updates",1));
   assert(reentries==1);std::puts("PASS startup_load: one level/start notification after stable destination");return 0;
 }
 assert(Number("rooms",1)&&Number("updates",1)&&Number("started",1));
 locationReads=roomVisits=playerVisits=0;
 gridAlive=false;
 if(mode=="reload")isaac::runtime::NoteNativeRoomLoaded();
 else currentLocation.roomIndex=85;
 if(mode=="same_frame"){
   if(!Dispatch())return 2;
   assert(Number("rooms",1)&&Number("updates",1));
   assert(locationReads==0&&roomVisits==0&&playerVisits==0);
 }
 ++nativeFrame;
 if(loadFromEntity)isaac::runtime::NoteNativeRoomLoaded();
 if(mode=="paused"){
   paused=true;if(!Dispatch())return 3;
   assert(Number("rooms",1)&&Number("updates",1));
   assert(locationReads==0&&roomVisits==0&&playerVisits==0);paused=false;
 }
 if(!Dispatch())return 4;
 if(mode=="late_listener"){assert(Number("lateUpdates",1));std::puts("PASS late_listener: new entity listener runs on first room update");return 0;}
 if(loadFromEntity){
   assert(Number("roomA",1)&&Number("roomB",0)&&Number("rooms",2));
   assert(Number("updates",1)&&reentries==1);
   ++nativeFrame;if(!Dispatch())return 9;
   assert(Number("roomA",1)&&Number("roomB",1)&&Number("rooms",3));
   assert(Number("updates",2));
   if(!Dispatch())return 10;
   assert(Number("rooms",3)&&reentries==1);
   std::printf("PASS %s: A=1 B=1, no update in unannounced destination\n",mode.c_str());
   return 0;
 }
 assert(Number("rooms",2)&&Number("updates",2)&&Number("destroyed",0));
 assert(locationReads==1&&roomVisits==1&&playerVisits==1);
 assert(reentries==(mode=="reentry"?1U:0U));
 if(!Dispatch())return 5;
 assert(Number("rooms",2)&&Number("updates",2));
 assert(locationReads==1&&roomVisits==1&&playerVisits==1);
 // Real destruction in a room must still reach the mod, exactly once.
 ++nativeFrame;currentLocation.roomIndex=86;gridAlive=true;if(!Dispatch())return 6;
 assert(Number("rooms",3)&&Number("updates",3)&&Number("destroyed",0));
 ++nativeFrame;gridAlive=false;if(!Dispatch())return 7;
 assert(Number("rooms",3)&&Number("updates",4)&&Number("destroyed",1));
 ++nativeFrame;if(!Dispatch())return 8;
 assert(Number("rooms",3)&&Number("updates",5)&&Number("destroyed",1));
 assert(locationReads==4&&roomVisits==4&&playerVisits==4);
 std::printf("PASS %s rooms=3 updates=5 real-destruction=1 scans=4\n",mode.c_str());
}
'''


class RoomUpdateCallbackOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='isaac-room-update-order-')
        path = Path(cls.tmp.name)
        prefix = fixture.HARNESS.split('int main(', 1)[0]
        prefix = prefix.replace(
            'GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {\n'
            '    return GameIsPausedObservation::ThunkUnavailable;\n}', '')
        prefix = re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}',
                        '', prefix, count=1)
        runtime = ROOT / 'runtime/source/lua_runtime.cpp'
        runtime_copy = path / 'runtime_room_order.cpp'
        runtime_copy.write_text(runtime.read_text() + BRIDGE)
        api = ROOT / 'runtime/src/interfaces/lua/isaac_api.cpp'
        api_text = api.read_text()
        for name, hook in (('VisitRoomEntities', 'RoomOrderVisitRoom'),
                           ('VisitPlayerEntities', 'RoomOrderVisitPlayer')):
            signature = f'void {name}(EntityVisitFn visit, void* context) noexcept {{'
            assert api_text.count(signature) == 1
            api_text = api_text.replace(signature, signature + f'\n    {hook}();')
        api_copy = path / 'api_room_order.cpp'
        api_copy.write_text('extern "C" void RoomOrderVisitRoom();\n'
                            'extern "C" void RoomOrderVisitPlayer();\n' + api_text)
        original = test_support.layered_lua_runtime_sources
        def sources(root):
            return [runtime_copy if p.resolve() == runtime.resolve() else
                    api_copy if p.resolve() == api.resolve() else p for p in original(root)]
        flags = tuple(f for f in test_support.HARNESS_COMPILE_FLAGS
                      if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
        with mock.patch.object(test_support, 'layered_lua_runtime_sources', side_effect=sources), \
                mock.patch.object(test_support, 'HARNESS_COMPILE_FLAGS', flags):
            cls.binary = test_support.build_lua_harness(
                source_root=fixture.SOURCE, workdir=path, harness_source=prefix + MAIN)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check_mode(self, mode):
        result = subprocess.run([str(self.binary), mode], capture_output=True, text=True)
        print(mode, result.returncode, result.stdout + result.stderr, flush=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_player_effect_update_stops_before_destination_player_update(self): self.check_mode('peffect_load')
    def test_player_effect_update_filters_by_player_type_not_variant(self): self.check_mode('peffect_type')
    def test_new_room_entity_listener_runs_in_the_first_update(self): self.check_mode('late_listener')
    def test_startup_room_callback_can_load_a_stable_destination(self): self.check_mode('startup_load')
    def test_player_update_can_load_another_room_without_mislabeling_events(self): self.check_mode('player_load')
    def test_effect_update_stops_before_destination_player_callbacks(self): self.check_mode('effect_load')
    def test_new_room_initializes_tracker_before_update(self): self.check_mode('transition')
    def test_same_index_reload_does_not_report_old_grid_as_destroyed(self): self.check_mode('reload')
    def test_paused_transition_waits_for_simulation(self): self.check_mode('paused')
    def test_new_room_callback_reentry_does_not_duplicate_frame(self): self.check_mode('reentry')
    def test_same_frame_skips_room_reads_and_scans(self): self.check_mode('same_frame')


if __name__ == '__main__':
    unittest.main()
