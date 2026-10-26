"""真实Lua更新派发必须尊重原生暂停，暂停不扫描实体且渲染继续。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_lua_entity_query as fixture
from . import test_support

ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include "infrastructure/memory/engine_memory_guard.hpp"
#include <cassert>
#if __has_include("infrastructure/call/managed_update_snapshot.hpp")
#include "infrastructure/call/managed_update_snapshot.hpp"
#define HAS_MANAGED_SNAPSHOT 1
#endif
unsigned roomVisits{},playerVisits{},locationReads{},pauseReads{};
GameIsPausedObservation pauseResult=GameIsPausedObservation::PausedTrue;
bool locationReady=true,requestReentry{},nestedCompleted{};
extern "C" void PauseTestVisitRoom(){++roomVisits;}
extern "C" void PauseTestVisitPlayer(){++playerVisits;}
GameIsPausedObservation ObserveGameIsPaused(uintptr_t owner,uintptr_t thunk){
 ++pauseReads;assert(owner==g_EngineBase+kGameOwnerGlobalSlotOffset&&thunk==0x2222);
 assert(isaac::runtime::EngineGuardDispatchActive().load()==1);
 if(requestReentry&&LuaRuntime::InManagedCallbackScope()){
  requestReentry=false;LuaRuntime::DispatchPostUpdate();nestedCompleted=true;
  assert(isaac::runtime::EngineGuardDispatchActive().load()==1);
 }
 return pauseResult;
}
GameRoomObservation ReadGameLocationKey(uintptr_t,GameLocationKey*key){
 ++locationReads;if(!locationReady)return GameRoomObservation::GameUnreadable;
 *key={84,0,1,0};return GameRoomObservation::Success;
}
#if defined(HAS_MANAGED_SNAPSHOT)
static std::uintptr_t snapshotGame{};
static unsigned nativePauseCalls{};
static bool NativePause(const void*game){assert(reinterpret_cast<std::uintptr_t>(game)==snapshotGame);++nativePauseCalls;return false;}
static bool Snapshot(isaac::runtime::ManagedUpdateSnapshot*out)noexcept{
 std::uintptr_t current{};std::memcpy(&current,g_OwnerSlotBytes.data(),sizeof(current));assert(current==snapshotGame);
 const bool valid=isaac::runtime::ReadNativeManagedUpdateSnapshot(current,reinterpret_cast<std::uintptr_t>(&NativePause),kGameFrameCountOffset,out,&isaac::runtime::engine_memory::EngineMemoryReadable);
 std::printf("snapshot game=%p frame=%u valid=%d\n",reinterpret_cast<void*>(current),out->frame,valid);return valid;
}
#endif
static bool Number(const char*key,double value){return ExpectNumber(key,value);}
static bool Dispatch(){
 LuaRuntime::DispatchPostUpdate();
 assert(isaac::runtime::EngineGuardDispatchActive().load()==0);
 if(LuaRuntime::TakeCallbackError()){char error[1024]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::fprintf(stderr,"%s\n",error);return false;}return true;
}
int main(int argc,char**argv){
 assert(argc==2);const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);
 LuaRuntime::DispatchPostUpdate();assert(isaac::runtime::EngineGuardDispatchActive().load()==0);
 CreateBlocks();g_GameBytes.resize(0x360000);FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::ObserveGameThread();LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 std::string script=scene=="cadence"?"triggerReentry=true\n":"";
 script+=R"lua(
 local m=RegisterMod('native pause updates',1);updates=0;renders=0;npcUpdates=0;playerUpdates=0;inits=0;started=0
 local trace=''
 m:AddCallback(9,function(_,p)assert(type(p)=='userdata');inits=inits+1;trace='9,' end)
 m:AddCallback(19,function()assert(trace=='9,');trace=trace..'19,' end)
 m:AddCallback(18,function()assert(trace=='9,19,');trace=trace..'18,' end)
 m:AddCallback(15,function(_,continued)assert(continued==false and trace=='9,19,18,');trace=trace..'15,';started=started+1 end)
 m:AddCallback(1,function()assert(trace=='9,19,18,15,');if triggerReentry then assert(Game():IsPaused()==false) end;updates=updates+1 end)
 m:AddCallback(2,function()renders=renders+1 end)
 m:AddCallback(0,function()npcUpdates=npcUpdates+1 end)
 m:AddCallback(31,function()playerUpdates=playerUpdates+1 end)
 )lua";
 assert(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@managed-update-pause.lua")==LuaRuntime::LuaInitResult::Success);
 LuaRuntime::NoteGameStarted(false);
 if(scene=="cadence"){
  pauseResult=GameIsPausedObservation::PausedFalse;
#if defined(HAS_MANAGED_SNAPSHOT)
  snapshotGame=AddressOf(g_GameBytes);isaac::runtime::SetManagedUpdateSnapshotReaderForTest(Snapshot);
#endif
  requestReentry=true;WriteAt<std::uint32_t>(g_GameBytes,kGameFrameCountOffset,10);if(!Dispatch())return 20;assert(nestedCompleted&&Number("updates",1));
  const auto rooms=roomVisits,players=playerVisits,locations=locationReads;
  if(!Dispatch())return 21;assert(Number("updates",1)&&roomVisits==rooms&&playerVisits==players&&locationReads==locations);
  WriteAt<std::uint32_t>(g_GameBytes,kGameFrameCountOffset,11);if(!Dispatch())return 22;assert(Number("updates",2));
  pauseResult=GameIsPausedObservation::PausedTrue;WriteAt<std::uint32_t>(g_GameBytes,kGameFrameCountOffset,12);if(!Dispatch())return 23;assert(Number("updates",2));
  pauseResult=GameIsPausedObservation::PausedFalse;if(!Dispatch())return 24;assert(Number("updates",3));
  auto other=g_GameBytes;WriteWord(g_OwnerSlotBytes,0,AddressOf(other));
#if defined(HAS_MANAGED_SNAPSHOT)
  snapshotGame=AddressOf(other);
#endif
  if(!Dispatch())return 25;assert(Number("updates",4));
  WriteAt<std::uint32_t>(other,kGameFrameCountOffset,0);if(!Dispatch())return 26;assert(Number("updates",5));
  LuaRuntime::NoteGameStarted(false);if(!Dispatch())return 27;assert(Number("updates",6)&&Number("inits",2)&&Number("started",2));
#if defined(HAS_MANAGED_SNAPSHOT)
  assert(nativePauseCalls==8);
#endif
  return 0;
 }else if(scene=="paused"||scene=="unknown"){
  pauseResult=GameIsPausedObservation::PausedFalse;if(!Dispatch())return 8;
  assert(Number("updates",1)&&Number("started",1));
  roomVisits=playerVisits=locationReads=pauseReads=0;
  pauseResult=scene=="paused"?GameIsPausedObservation::PausedTrue:GameIsPausedObservation::OwnerUnreadable;
  for(unsigned i=0;i<5;++i){if(!Dispatch())return 1;}
  assert(Number("updates",1)&&Number("playerUpdates",1)&&Number("inits",1)&&Number("started",1));
  assert(roomVisits==0&&playerVisits==0&&locationReads==0&&pauseReads==5);
  LuaRuntime::DispatchPostRender(0x1234);assert(Number("renders",1));assert(isaac::runtime::EngineGuardDispatchActive().load()==0);
 }else if(scene=="pending_paused"){
  pauseResult=GameIsPausedObservation::PausedTrue;if(!Dispatch())return 9;
  assert(Number("updates",0)&&Number("started",1)&&Number("inits",1));
 }else if(scene=="location_retry"){
  pauseResult=GameIsPausedObservation::PausedFalse;locationReady=false;
  if(!Dispatch())return 2;assert(Number("updates",0)&&Number("started",0)&&Number("inits",1));locationReady=true;
 }else if(scene=="player_retry"){
  pauseResult=GameIsPausedObservation::PausedFalse;
  WriteWord(g_GameBytes,kGamePlayerArrayEndOffset,AddressOf(g_PlayerArrayBytes));
  if(!Dispatch())return 3;assert(Number("updates",0)&&Number("started",0)&&Number("inits",0));
  WriteWord(g_GameBytes,kGamePlayerArrayEndOffset,AddressOf(g_PlayerArrayBytes)+sizeof(std::uintptr_t));
 }else return 90;
 pauseResult=GameIsPausedObservation::PausedFalse;
 const auto epoch=isaac::runtime::EngineGuardDispatchEpoch().load();
 if(!Dispatch())return 4;
 assert(isaac::runtime::EngineGuardDispatchEpoch().load()==epoch+1);
 const double expectedUpdates=(scene=="paused"||scene=="unknown")?2:1;
 assert(Number("updates",expectedUpdates)&&Number("inits",1)&&Number("started",1)&&Number("playerUpdates",expectedUpdates));
 double npc{};assert(LuaRuntime::ReadLuaGlobalNumber("npcUpdates",&npc)&&npc>0&&roomVisits>0&&playerVisits>0);
 return 0;
}
'''


class ManagedUpdatePauseTests(unittest.TestCase):
    def test_pause_resume_scan_and_dispatch_scope(self):
        source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
        source=source.replace('GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {\n    return GameIsPausedObservation::ThunkUnavailable;\n}', '')
        source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)+MAIN
        original=test_support.layered_lua_runtime_sources
        with tempfile.TemporaryDirectory(prefix='managed-update-pause-') as tmp:
            path=Path(tmp);tu=ROOT/'runtime/src/interfaces/lua/isaac_api.cpp';text=tu.read_text()
            for name,hook in (('VisitRoomEntities','PauseTestVisitRoom'),('VisitPlayerEntities','PauseTestVisitPlayer')):
                signature=f'void {name}(EntityVisitFn visit, void* context) noexcept {{'
                self.assertEqual(text.count(signature),1)
                text=text.replace(signature,signature+f'\n    {hook}();')
            copied=path/'isaac_api_pause_instrumented.cpp'
            copied.write_text('extern "C" void PauseTestVisitRoom();\nextern "C" void PauseTestVisitPlayer();\n'+text)
            def sources(root):
                return [copied if p.resolve()==tu.resolve() else p for p in original(root)]
            with mock.patch.object(test_support,'layered_lua_runtime_sources',side_effect=sources):
                binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=path,harness_source=source)
            for scene in ('paused','unknown','pending_paused','location_retry','player_retry','cadence'):
                with self.subTest(scene=scene):
                    result=subprocess.run([str(binary),scene],capture_output=True,text=True)
                    print(scene,result.returncode,result.stdout+result.stderr,flush=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
