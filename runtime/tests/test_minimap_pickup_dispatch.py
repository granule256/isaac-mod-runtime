"""Production boundaries pump isolated world consumers before PC callbacks."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import test_lua_entity_query as fixture
from . import test_support

ROOT=Path(__file__).resolve().parents[2]
BRIDGE=r'''
extern "C" bool RegisterTestWorldAdapter() {
 auto* state=LuaRuntime::g_LuaState;
 lua_getglobal(state,"worldAdapter");
 const bool ok=isaac::runtime::RegisterCompatibilityAdapter(state,"test-world",-1);
 lua_pop(state,1);return ok;
}
extern "C" bool PickupDispatchScript(const char* text) {
 const int top=lua_gettop(LuaRuntime::g_LuaState);
 const bool ok=luaL_dostring(LuaRuntime::g_LuaState,text)==LUA_OK;
 if(!ok)std::fprintf(stderr,"%s\n",lua_tostring(LuaRuntime::g_LuaState,-1));
 lua_settop(LuaRuntime::g_LuaState,top);return ok;
}
namespace {
lua_Alloc pickupOriginalAllocator{};void* pickupAllocatorUser{};bool pickupAllocationFailure{};
void* PickupAllocator(void*,void* p,size_t old,size_t size) {
 if(pickupAllocationFailure&&size>old)return nullptr;
 return pickupOriginalAllocator(pickupAllocatorUser,p,old,size);
}
}
extern "C" void PickupDispatchFailAlloc(bool fail) {
 if(!pickupOriginalAllocator){
  pickupOriginalAllocator=lua_getallocf(LuaRuntime::g_LuaState,&pickupAllocatorUser);
  lua_setallocf(LuaRuntime::g_LuaState,PickupAllocator,nullptr);
 }
 pickupAllocationFailure=fail;
}
'''
MAIN=r'''
#include "interfaces/lua/compatibility_adapter_runtime.hpp"
#include "infrastructure/native/world_content_mutations.hpp"
#include "native_room_events.hpp"
#include "application/shader/shader_pipeline.hpp"
#include <cassert>
extern "C" bool PickupDispatchScript(const char*);
extern "C" void PickupDispatchFailAlloc(bool);
extern "C" bool RegisterTestWorldAdapter();
static GameLocationKey location{84,0,1,0};
GameRoomObservation ReadGameLocationKey(uintptr_t,GameLocationKey*out){*out=location;return GameRoomObservation::Success;}
int main(int argc,char**argv){
 assert(argc==2);const std::string mode=argv[1];
 static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::ObserveGameThread();LuaRuntime::SetEngineModuleBase(g_EngineBase);
 LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0);
 const char* script=R"lua(
 local m=RegisterMod('pickup dispatch',1)
 snapshotItems=1
 function worldAdapter(p,c)
  assert(p or c)
  if adapterFail then error('adapter must retry independently') end
  snapshotItems=0
 end
 expected=1;rooms=0;levels=0;renders=0;updates=0;bad=0
 local function check()if snapshotItems~=expected then bad=bad+1 end end
 m:AddCallback(19,function()check();rooms=rooms+1;savedIcons=snapshotItems end)
 m:AddCallback(18,function()levels=levels+1 end)
 m:AddCallback(1,function()check();updates=updates+1 end)
 local function draw()check();renders=renders+1;return {} end
 m:AddCallback(2,draw);m:AddCallback(21,draw)
 )lua";
 assert(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@pickup-dispatch.lua")==LuaRuntime::LuaInitResult::Success);
 assert(RegisterTestWorldAdapter());
 LuaRuntime::NoteGameStarted(false);LuaRuntime::DispatchPostUpdate();
 using namespace isaac::runtime;
 assert(ExpectNumber("rooms",1)&&ExpectNumber("levels",1)&&ExpectNumber("bad",0));
 auto render=[&](bool shader){
  if(!shader){LuaRuntime::DispatchPostRender(0x1234);return true;}
  const ShaderProgramView program{"test","map",nullptr,nullptr,nullptr,nullptr,0,0,14};float vertices[56]{};
  return LuaRuntime::FillShaderParameters(program,vertices,0x1234);
 };
 if(mode=="new_start"){
  RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);
  LuaRuntime::NoteGameStarted(false);
  if(HasPendingCompatibilityAdapters()){std::puts("FAIL new run retains old mutation");return 20;}
  // A new mutation after the start boundary belongs to the loaded current run.
  RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);assert(PickupDispatchScript("expected=0"));
  LuaRuntime::DispatchPostUpdate();
 }else if(mode=="new_level"){
  RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);location.stage=2;
  BeginWorldContentFloor();
  std::uint32_t level[]={2,0};CompleteNativeRoomLoad([](void*){},level);
  render(false);if(!ExpectNumber("levels",2))return 21;
 }else if(mode=="shutdown"){
  RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);
  if(!LuaRuntime::ShutdownForModReload()||HasPendingCompatibilityAdapters()){std::puts("FAIL shutdown retains pending mutation");return 22;}
  return 0;
 }else{
  RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);assert(PickupDispatchScript("expected=0"));
  if(mode=="room_update"||mode=="room_render"||mode=="retry"){
   location.roomIndex=85;NoteNativeRoomLoaded();
  }
  if(mode=="retry"){
   assert(PickupDispatchScript("adapterFail=true;expected=1"));
   LuaRuntime::DispatchPostUpdate();
   assert(ExpectNumber("updates",2)&&HasPendingCompatibilityAdapters());
   render(false);const bool ready=render(true);
   if(!ready||!HasPendingCompatibilityAdapters()||!ExpectNumber("rooms",2)||!ExpectNumber("renders",2)){
    std::puts("FAIL compatibility failure blocked PC room/render callbacks");return 23;
   }
   assert(!LuaRuntime::TakeCallbackError());
   assert(PickupDispatchScript("adapterFail=false;expected=0"));
  }
  if(mode=="room_update"||mode=="update")LuaRuntime::DispatchPostUpdate();
  else render(mode=="shader");
 }
 if(LuaRuntime::TakeCallbackError()||HasPendingCompatibilityAdapters()||!ExpectNumber("bad",0)){
  std::puts("FAIL stale pickup snapshot reached production lifecycle consumer");return 24;
 }
 if(mode=="room_update"||mode=="room_render"){
  if(!ExpectNumber("rooms",2)||!ExpectNumber("savedIcons",0))return 25;
 }
 if(!ExpectNumber("levels",mode=="new_level"||mode=="new_start"?2:1))return 26;
 std::printf("PASS pickup dispatch %s\n",mode.c_str());
}
'''
class MinimapPickupDispatchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-pickup-dispatch-');work=Path(cls.tmp.name)
  runtime=ROOT/'runtime/source/lua_runtime.cpp';copied=work/'pickup_runtime.cpp';copied.write_text(runtime.read_text()+BRIDGE)
  original=test_support.layered_lua_runtime_sources
  def sources(root):
   files=[copied if p.resolve()==runtime.resolve() else p for p in original(root)]
   return files
  flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
  with patch.object(test_support,'layered_lua_runtime_sources',side_effect=sources),patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
   cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=work,harness_source=fixture.HARNESS.split('int main(',1)[0]+MAIN)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_pending_mutations_precede_every_consumer(self):
  for mode in ('render','shader','room_update','room_render','update','retry','new_level','new_start','shutdown'):
   with self.subTest(mode=mode):
    result=subprocess.run([str(self.binary),mode],capture_output=True,text=True)
    print(mode,result.returncode,result.stdout+result.stderr,flush=True)
    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
