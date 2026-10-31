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
static bool gridAlive=true,paused{};
extern "C" void RoomOrderVisitRoom(){++roomVisits;}
extern "C" void RoomOrderVisitPlayer(){++playerVisits;}
extern "C" int RoomOrderHash(lua_State*L){lua_pushinteger(L,currentLocation.roomIndex);return 1;}
extern "C" int RoomOrderGrid(lua_State*L){lua_pushboolean(L,gridAlive);return 1;}
extern "C" int RoomOrderReenter(lua_State*){++reentries;LuaRuntime::DispatchPostUpdate();return 0;}
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
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::ObserveGameThread();LuaRuntime::SetEngineModuleBase(g_EngineBase);
 LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0);
 std::string script=mode=="reentry"?"requestReentry=true\n":"";
 script+=R"lua(
 local m=RegisterMod('independent room grid tracker',1)
 rooms=0;levels=0;started=0;updates=0;destroyed=0
 local destroyedGrids,trackedGrids={},{}
 m:AddCallback(19,function()
   local hash=TestRoomHash()
   if not destroyedGrids[hash] then destroyedGrids[hash]={} end
   trackedGrids={}
   if TestGridAlive() and not destroyedGrids[hash][0] then trackedGrids[0]=true end
   rooms=rooms+1
   if requestReentry and started>0 then TestReenterUpdate() end
 end)
 m:AddCallback(18,function() assert(rooms>levels);levels=levels+1 end)
 m:AddCallback(15,function() assert(rooms==1 and levels==1);started=started+1 end)
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
 m:AddCallback(31,function() end)
 )lua";
 assert(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@room-grid-tracker.lua")==LuaRuntime::LuaInitResult::Success);
 InstallRoomOrderInputs();isaac::runtime::SetManagedUpdateSnapshotReaderForTest(Snapshot);
 LuaRuntime::NoteGameStarted(false);if(!Dispatch())return 1;
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
 if(mode=="paused"){
   paused=true;if(!Dispatch())return 3;
   assert(Number("rooms",1)&&Number("updates",1));
   assert(locationReads==0&&roomVisits==0&&playerVisits==0);paused=false;
 }
 if(!Dispatch())return 4;
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

    def test_new_room_initializes_tracker_before_update(self): self.check_mode('transition')
    def test_same_index_reload_does_not_report_old_grid_as_destroyed(self): self.check_mode('reload')
    def test_paused_transition_waits_for_simulation(self): self.check_mode('paused')
    def test_new_room_callback_reentry_does_not_duplicate_frame(self): self.check_mode('reentry')
    def test_same_frame_skips_room_reads_and_scans(self): self.check_mode('same_frame')


if __name__ == '__main__':
    unittest.main()
