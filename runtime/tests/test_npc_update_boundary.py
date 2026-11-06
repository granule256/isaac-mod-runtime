"""NPC callbacks run before the native death tail resets StateFrame to zero."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness

MAIN = r'''
#include "interfaces/lua/api500_entities.guards.hpp"
#include "native_room_events.hpp"
#include <cassert>
// Absent on the old implementation; the production definition overrides this seam.
namespace LuaRuntime {__attribute__((weak,noinline)) void DispatchPostNpcUpdate(std::uintptr_t){}}
static double Number(const char*name){double n{};assert(LuaRuntime::ReadLuaGlobalNumber(name,&n));return n;}
static bool observableRoom=false;
static GameLocationKey location{84,0,1,0};
static unsigned nativeFrame=10;
GameRoomObservation ReadCurrentGameRoom(uintptr_t,void**out){if(!observableRoom)return GameRoomObservation::RoomUnreadable;*out=g_RoomBytes.data();return GameRoomObservation::Success;}
GameRoomObservation ReadGameLocationKey(uintptr_t,GameLocationKey*out){if(!observableRoom)return GameRoomObservation::RoomUnreadable;*out=location;return GameRoomObservation::Success;}
static bool Snapshot(isaac::runtime::ManagedUpdateSnapshot*out)noexcept{*out={AddressOf(g_GameBytes),nativeFrame};return true;}
static void Tick(){++nativeFrame;LuaRuntime::DispatchPostUpdate();}
int main(int argc,char**argv){
 assert(argc==2);const std::string mode=argv[1];
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();g_Entities[kEnemyA].resize(0x1200);PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 auto& npc=g_Entities[kEnemyA];WriteWord(npc,0,g_EngineBase+kEntityNpcVtableOffset);
 namespace G=isaac::runtime::api500_entities;
 std::memcpy(g_ModuleBytes.data()+G::kNpcLayout,G::kNpcGuard.data(),G::kNpcGuard.size());
 WriteAt<std::uint32_t>(npc,0xb70,0);WriteAt<std::uint32_t>(npc,0x400,40);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 const char*script=R"lua(
calls=0;inits=0;deadSeen=0;wrong=0
local m=RegisterMod('npc native boundary',1)
m:AddCallback(27,function(_,n)assert(lifecycle or calls==0);inits=inits+1 end,20)
m:AddCallback(0,function(_,n)
 assert(lifecycle or inits==1);calls=calls+1
 if n:IsDead()then deadSeen=deadSeen+1 end
 n.StateFrame=n.StateFrame+1
end,20)
m:AddCallback(0,function()wrong=wrong+1 end,999)
)lua";
 const auto code=std::string(mode=="lifecycle"?"lifecycle=true\n":"")+script;
 if(LuaRuntime::InitializeFromBuffer(code.data(),code.size(),"@npc-boundary.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(mode=="lifecycle"){
  observableRoom=true;LuaRuntime::ObserveGameThread();isaac::runtime::SetManagedUpdateSnapshotReaderForTest(Snapshot);
  isaac::runtime::NoteNativeRoomLoaded();LuaRuntime::NoteGameStarted(false);
  LuaRuntime::DispatchPostNpcUpdate(AddressOf(npc));Tick();
  if(Number("inits")!=1||Number("calls")!=1){std::fprintf(stderr,"native then first room observation duplicated INIT: %g\n",Number("inits"));return 11;}
  // Same address, same grid index, new native room lifetime.
  isaac::runtime::NoteNativeRoomLoaded();LuaRuntime::DispatchPostNpcUpdate(AddressOf(npc));Tick();
  if(Number("inits")!=2||Number("calls")!=2)return 12;
  LuaRuntime::DispatchPostNpcUpdate(AddressOf(npc));Tick();
  if(Number("inits")!=2||Number("calls")!=3)return 13;
  // Preserve location-based reset when no native load notification exists.
  location.roomIndex=85;Tick();
  if(Number("inits")!=3||Number("calls")!=3)return 14;
  isaac::runtime::NoteNativeRoomLoaded();LuaRuntime::DispatchPostNpcUpdate(AddressOf(npc));Tick();
  if(Number("inits")!=4||Number("calls")!=4||LuaRuntime::TakeCallbackError())return 15;
  return 0;
 }
 if(mode=="native"){
  LuaRuntime::DispatchPostNpcUpdate(AddressOf(npc));
  if(Number("calls")!=1||Number("inits")!=1)return 2;
  // A lethal frame can already be dead while still in its active AI state.
  WriteAt<std::uint8_t>(npc,kEntityIsDeadOffset,1);
  LuaRuntime::DispatchPostNpcUpdate(AddressOf(npc));
  if(Number("calls")!=2||Number("deadSeen")!=1)return 3;
 }
 // Generic native death handling follows the AI callback, preserving this zero
 // for the next native frame's one-time Death animation startup.
 WriteAt<std::uint8_t>(npc,kEntityIsDeadOffset,1);
 WriteAt<std::uint32_t>(npc,0xb70,18);WriteAt<std::uint32_t>(npc,0x400,0);
 LuaRuntime::DispatchPostUpdate();
 std::uint32_t frame{};std::memcpy(&frame,npc.data()+0x400,4);
 if(frame!=0||Number("calls")!=(mode=="native"?2:0)){
  std::fprintf(stderr,"frame-tail NPC callback changed death StateFrame: frame=%u calls=%g\n",frame,Number("calls"));return 4;
 }
 if(Number("wrong")!=0||LuaRuntime::TakeCallbackError())return 5;
 return 0;
}
'''


class NpcUpdateBoundaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='npc-boundary-')
  source=fixture.HARNESS.split('int main(',1)[0]+MAIN
  source=source.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}', '')
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def check(self,mode):
  result=subprocess.run([str(self.binary),mode],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
 def test_frame_tail_cannot_overwrite_native_death_startup(self):self.check('manager')
 def test_init_precedes_update_and_lethal_frame_remains_visible(self):self.check('native')
 def test_native_init_and_frame_scan_share_each_room_lifetime(self):self.check('lifecycle')
