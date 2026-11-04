"""Run real Lua lifecycle dispatch for native same-floor regeneration and render retries."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import test_lua_entity_query as fixture
from . import test_support

PRELUDE = r'''
#include "native_room_events.hpp"
// Before the native Init observer exists this models the unhooked game call.
// The production non-template overload takes precedence once implemented.
namespace isaac::runtime {
template<class Original> void CompleteNativeLevelInit(Original original, void* level) { original(level); }
}
namespace LuaRuntime { bool PrepareRoomEventsForRender(); }
static std::uint32_t nativeLevel[2]={1,0};
static bool rebuildInCallback=false;
static bool renderDuringInit=false,initRenderBlocked=false;
static void NativeInit(void* level) {
 if(renderDuringInit) initRenderBlocked=!LuaRuntime::PrepareRoomEventsForRender();
 isaac::runtime::CompleteNativeRoomLoad([](void*){},level);
 if(renderDuringInit) initRenderBlocked=initRenderBlocked&&!LuaRuntime::PrepareRoomEventsForRender();
}
static void Rebuild() { isaac::runtime::CompleteNativeLevelInit(static_cast<void(*)(void*)>(NativeInit),static_cast<void*>(nativeLevel)); }
extern "C" int FloorTestRebuild(lua_State*) {if(rebuildInCallback){rebuildInCallback=false;Rebuild();}return 0;}
extern "C" void InstallFloorTestInputs();
'''
BRIDGE = r'''
extern "C" int FloorTestRebuild(lua_State*);
extern "C" void InstallFloorTestInputs() {
 lua_pushcfunction(LuaRuntime::g_LuaState,FloorTestRebuild);
 lua_setglobal(LuaRuntime::g_LuaState,"RebuildInsideRoomCallback");
}
'''
CHECKS = r'''
 auto count=[&](int room,int level){return number("room",room)&&number("level",level)&&number("started",1)&&number("init",1);};
 // Native Init/load_room with unchanged stage, type, seed and room index.
 Rebuild();LuaRuntime::DispatchPostUpdate();if(errors())return 20;
 if(!count(2,2)){std::puts("FAIL same-stage native Init: NEW_LEVEL missing");return 21;}
 LuaRuntime::DispatchPostUpdate();if(errors()||!count(2,2))return 22;
 // Ordinary same-index load_room is a room event, never another floor.
 isaac::runtime::CompleteNativeRoomLoad([](void*){},nativeLevel);
 LuaRuntime::DispatchPostUpdate();if(errors()||!count(3,2))return 23;
 // A completed floor's first render precedes its next simulation update.
 Rebuild();if(!LuaRuntime::PrepareRoomEventsForRender()||errors()||!count(4,3))return 24;
 // Both native loads and descriptor read failures retain the floor generation.
 Rebuild();locationReady=false;
 if(LuaRuntime::PrepareRoomEventsForRender()||!count(4,3))return 25;
 LuaRuntime::DispatchPostUpdate();if(errors()||!count(4,3))return 26;
 locationReady=true;
 if(!LuaRuntime::PrepareRoomEventsForRender()||errors()||!count(5,4))return 27;
 // Old loaded stage/type cannot make same-floor Init ready during generation,
 // even after load_room has returned inside Init.
 renderDuringInit=true;Rebuild();renderDuringInit=false;
 if(!initRenderBlocked||!count(5,4))return 28;
 if(!LuaRuntime::PrepareRoomEventsForRender()||errors()||!count(6,5))return 29;
 // A floor rebuild triggered by NEW_ROOM must survive callback consumption.
 rebuildInCallback=true;Rebuild();
 if(LuaRuntime::PrepareRoomEventsForRender()||errors()||!count(7,6))return 30;
 if(!LuaRuntime::PrepareRoomEventsForRender()||errors()||!count(8,7))return 31;
 // Cross-floor Init also has one ordered pair, including reused room index.
 observedStage=2;nativeLevel[0]=2;Rebuild();
 if(!LuaRuntime::PrepareRoomEventsForRender()||errors()||!count(9,8))return 32;
 for(int i=0;i<8;++i){LuaRuntime::DispatchPostUpdate();if(!LuaRuntime::PrepareRoomEventsForRender()||errors()||!count(9,8))return 33;}
 // Init return without a readable matching load must not reuse the old key.
 isaac::runtime::CompleteNativeLevelInit(static_cast<void(*)(void*)>([](void*){}),static_cast<void*>(nativeLevel));
 if(LuaRuntime::PrepareRoomEventsForRender()||!count(9,8))return 34;
 nativeLevel[1]=1;isaac::runtime::CompleteNativeRoomLoad([](void*){},nativeLevel);
 if(LuaRuntime::PrepareRoomEventsForRender()||!count(9,8))return 35;
 nativeLevel[1]=0;isaac::runtime::CompleteNativeRoomLoad([](void*){},nativeLevel);
 if(!LuaRuntime::PrepareRoomEventsForRender()||errors()||!count(10,9))return 36;
 // Same stage/type Init starts a new floor even at a different starting index.
 if(LuaRuntime::StartingRoomIndexForCurrentLevel()!=84)return 37;
 observedRoom=52;Rebuild();locationReady=false;
 if(LuaRuntime::PrepareRoomEventsForRender()||LuaRuntime::StartingRoomIndexForCurrentLevel()!=84)return 38;
 locationReady=true;
 if(!LuaRuntime::PrepareRoomEventsForRender()||errors()||!count(11,10))return 39;
 if(LuaRuntime::StartingRoomIndexForCurrentLevel()!=52){
  std::puts("FAIL same-stage Init retained previous StartingRoomIndex");return 40;
 }
 observedRoom=53;isaac::runtime::CompleteNativeRoomLoad([](void*){},nativeLevel);
 if(!LuaRuntime::PrepareRoomEventsForRender()||errors()||!count(12,10)||LuaRuntime::StartingRoomIndexForCurrentLevel()!=52)return 41;
 std::puts("PASS native floor generation: same identity, room-only load, first render, read retry, in-progress and callback reentry, cross floor");
'''

MAIN = r'''
bool locationReady=true;
static std::uint32_t observedStage=1,observedRoom=84;
GameRoomObservation ReadGameLocationKey(uintptr_t,GameLocationKey* key){
 if(!locationReady)return GameRoomObservation::GameUnreadable;
 *key={observedRoom,0,observedStage,0};return GameRoomObservation::Success;
}
int main(){
 static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);
 LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0);
 const char* script=R"lua(
 local m=RegisterMod('native floor test',1)
 _start={room=0,level=0,started=0,updates=0}
 m:AddCallback(19,function()_start.room=_start.room+1;RebuildInsideRoomCallback() end)
 m:AddCallback(18,function()
  assert(_start.room>_start.level,'NEW_LEVEL before NEW_ROOM')
  _start.level=_start.level+1
 end)
 m:AddCallback(15,function()_start.started=_start.started+1 end)
 m:AddCallback(1,function()_start.updates=_start.updates+1 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@floor.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 InstallFloorTestInputs();
 auto errors=[](){return LuaRuntime::TakeCallbackError();};
 auto number=[](const char* field,double expected){double actual=-1;return LuaRuntime::ReadLuaTableNumber("_start",field,&actual)==0&&actual==expected;};
 LuaRuntime::NoteGameStarted(false);LuaRuntime::DispatchPostUpdate();
 if(errors()||!number("room",1)||!number("level",1)||!number("started",1))return 2;
 @CHECKS@
 return 0;
}
'''

class NativeFloorGenerationTests(unittest.TestCase):
 def test_real_dispatch_observes_completed_native_floor_generations(self):
  with tempfile.TemporaryDirectory(prefix='isaac-native-floor-') as temp:
   path=Path(temp)
   runtime=fixture.SOURCE/'lua_runtime.cpp'
   copied=path/'floor_runtime.cpp';copied.write_text(runtime.read_text()+BRIDGE)
   original=test_support.layered_lua_runtime_sources
   def sources(root):return [copied if p.resolve()==runtime.resolve() else p for p in original(root)]
   flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
   with patch.object(test_support,'layered_lua_runtime_sources',side_effect=sources),patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
    code=fixture.HARNESS.split('int main(',1)[0]+PRELUDE+MAIN.replace('@CHECKS@',CHECKS.replace('&&number("init",1)',''))
    binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=path,harness_source=code)
   result=subprocess.run([str(binary)],capture_output=True,text=True)
   print(result.stdout+result.stderr,flush=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
