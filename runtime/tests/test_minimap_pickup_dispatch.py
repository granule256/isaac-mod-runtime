"""Production lifecycle boundaries flush rerolled pickup snapshots before consumers."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import test_lua_entity_query as fixture
from . import test_support

ROOT=Path(__file__).resolve().parents[2]
BRIDGE=r'''
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
#include "interfaces/lua/minimap_pickup_cache.hpp"
#include "native_room_events.hpp"
#include "application/shader/shader_pipeline.hpp"
#include <cassert>
extern "C" bool PickupDispatchScript(const char*);
extern "C" void PickupDispatchFailAlloc(bool);
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
 normal={Descriptor={},ItemIcons={'Coin'}}
 MinimapAPI={PickupList={{Type=5,Variant=20,IconID='Coin'}},GridEntityList={},Levels={[0]={normal}}}
 expected=1;rooms=0;levels=0;renders=0;updates=0;bad=0
 local function check()if #normal.ItemIcons~=expected then bad=bad+1 end end
 m:AddCallback(19,function()check();rooms=rooms+1;savedIcons=#normal.ItemIcons end)
 m:AddCallback(18,function()levels=levels+1 end)
 m:AddCallback(1,function()check();updates=updates+1 end)
 local function draw()check();renders=renders+1;return {} end
 m:AddCallback(2,draw);m:AddCallback(21,draw)
 )lua";
 assert(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@pickup-dispatch.lua")==LuaRuntime::LuaInitResult::Success);
 LuaRuntime::NoteGameStarted(false);LuaRuntime::DispatchPostUpdate();
 using namespace isaac::runtime;
 assert(ExpectNumber("rooms",1)&&ExpectNumber("levels",1)&&ExpectNumber("bad",0));
 auto render=[&](bool shader){
  if(!shader){LuaRuntime::DispatchPostRender(0x1234);return true;}
  const ShaderProgramView program{"test","map",nullptr,nullptr,nullptr,nullptr,0,0,14};float vertices[56]{};
  return LuaRuntime::FillShaderParameters(program,vertices,0x1234);
 };
 if(mode=="new_start"){
  NoteMinimapPickupReroll(MinimapPickupReroll::Pickups);
  LuaRuntime::NoteGameStarted(false);
  if(HasPendingMinimapPickupReroll()){std::puts("FAIL new run retains old mutation");return 20;}
  // A new mutation after the start boundary belongs to the loaded current run.
  NoteMinimapPickupReroll(MinimapPickupReroll::Pickups);assert(PickupDispatchScript("expected=0"));
  LuaRuntime::DispatchPostUpdate();
 }else if(mode=="new_level"){
  NoteMinimapPickupReroll(MinimapPickupReroll::Pickups);location.stage=2;
  std::uint32_t level[]={2,0};CompleteNativeRoomLoad([](void*){},level);
  render(false);if(!ExpectNumber("levels",2))return 21;
 }else if(mode=="shutdown"){
  NoteMinimapPickupReroll(MinimapPickupReroll::Pickups);
  if(!LuaRuntime::ShutdownForModReload()||HasPendingMinimapPickupReroll()){std::puts("FAIL shutdown retains pending mutation");return 22;}
  return 0;
 }else{
  NoteMinimapPickupReroll(MinimapPickupReroll::Pickups);assert(PickupDispatchScript("expected=0"));
  if(mode=="room_update"||mode=="room_render"||mode=="retry"){
   location.roomIndex=85;NoteNativeRoomLoaded();
  }
  if(mode=="retry"){
   PickupDispatchFailAlloc(true);render(false);const bool ready=render(true);PickupDispatchFailAlloc(false);
   if(ready||!HasPendingMinimapPickupReroll()||!ExpectNumber("renders",0)||!ExpectNumber("rooms",1)){
    std::puts("FAIL failed invalidation reached stale render");return 23;
   }
  }
  if(mode=="room_update"||mode=="update")LuaRuntime::DispatchPostUpdate();
  else render(mode=="shader");
 }
 if(LuaRuntime::TakeCallbackError()||HasPendingMinimapPickupReroll()||!ExpectNumber("bad",0)){
  std::puts("FAIL stale pickup snapshot reached production lifecycle consumer");return 24;
 }
 if(mode=="room_update"||mode=="room_render"||mode=="retry"){
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
  helper=ROOT/'runtime/src/interfaces/lua/minimap_pickup_cache.cpp'
  def sources(root):
   files=[copied if p.resolve()==runtime.resolve() else p for p in original(root)]
   return files if helper in files else files+[helper]
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
