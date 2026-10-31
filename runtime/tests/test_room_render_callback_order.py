"""Real Lua dispatch: room load must precede render consumers of cached room data.

Independent map sample, generated host room/pickup inputs, no author/game payload.
Reproduces the native frame-0 render that otherwise writes the destination's
pickups to the previous room and leaves duplicate icons after repeated travel.
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
extern "C" int RenderOrderRoom(lua_State*);
extern "C" int RenderOrderPickup(lua_State*);
extern "C" int RenderOrderLoad(lua_State*);
extern "C" void InstallRenderOrderInputs() {
 lua_pushcfunction(LuaRuntime::g_LuaState,RenderOrderRoom);
 lua_setglobal(LuaRuntime::g_LuaState,"NativeRoom");
 lua_pushcfunction(LuaRuntime::g_LuaState,RenderOrderPickup);
 lua_setglobal(LuaRuntime::g_LuaState,"NativePickup");
 lua_pushcfunction(LuaRuntime::g_LuaState,RenderOrderLoad);
 lua_setglobal(LuaRuntime::g_LuaState,"LoadDuringRoomCallback");
}
'''
MAIN = r'''
#include "native_room_events.hpp"
#include "application/shader/shader_pipeline.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"
#include <cassert>
extern "C" { void InstallRenderOrderInputs(); }
static GameLocationKey currentLocation{84,0,1,0};
static unsigned nativeFrame=10,pickup=1,locationReads{},roomVisits{},playerVisits{};
static bool locationReady=true,paused{},nestedLoad{};
extern "C" void RenderOrderVisitRoom(){++roomVisits;}
extern "C" void RenderOrderVisitPlayer(){++playerVisits;}
extern "C" int RenderOrderRoom(lua_State*L){lua_pushinteger(L,currentLocation.roomIndex);return 1;}
extern "C" int RenderOrderPickup(lua_State*L){lua_pushinteger(L,pickup);return 1;}
extern "C" int RenderOrderLoad(lua_State*){
 if(nestedLoad){nestedLoad=false;currentLocation.roomIndex=85;pickup=3;isaac::runtime::NoteNativeRoomLoaded();}return 0;
}
GameRoomObservation ReadGameLocationKey(uintptr_t,GameLocationKey*key){
 ++locationReads;if(!locationReady)return GameRoomObservation::GameUnreadable;
 *key=currentLocation;return GameRoomObservation::Success;
}
GameIsPausedObservation ObserveGameIsPaused(uintptr_t,uintptr_t){
 return paused?GameIsPausedObservation::PausedTrue:GameIsPausedObservation::PausedFalse;
}
static bool Snapshot(isaac::runtime::ManagedUpdateSnapshot*out)noexcept{
 *out={AddressOf(g_GameBytes),nativeFrame};return true;
}
static bool Number(const char*name,double expected){return ExpectNumber(name,expected);}
static bool Render(bool shader){
 bool ready=true;
 if(shader){
  const isaac::runtime::ShaderProgramView program{"test","map",nullptr,nullptr,nullptr,nullptr,0,0,14};
  float vertices[56]{};ready=LuaRuntime::FillShaderParameters(program,vertices,0x1234);
 }else LuaRuntime::DispatchPostRender(0x1234);
 assert(isaac::runtime::EngineGuardDispatchActive().load()==0);
 if(LuaRuntime::TakeCallbackError()){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);std::abort();
 }
 return ready;
}
int main(int argc,char**argv){
 assert(argc==2);const std::string mode=argv[1];const bool shader=mode=="shader";
 nestedLoad=mode=="callback_load";
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::ObserveGameThread();LuaRuntime::SetEngineModuleBase(g_EngineBase);
 LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0);
 const char* script=R"lua(
 local m=RegisterMod('independent pickup map',1)
 local cachedRoom,icons
 icons={};rooms=0;levels=0;updates=0;renders=0;badWrites=0
 mapStart=0;mapShop=0;mapThird=0
 m:AddCallback(19,function()cachedRoom=NativeRoom();rooms=rooms+1;if rooms==2 then LoadDuringRoomCallback() end end)
 m:AddCallback(18,function()levels=levels+1 end)
 m:AddCallback(1,function()updates=updates+1 end)
 local function draw()
  if cachedRoom~=NativeRoom() then badWrites=badWrites+1 end
  icons[cachedRoom]=NativePickup();renders=renders+1
  mapStart=icons[84] or 0;mapShop=icons[82] or 0;mapThird=icons[85] or 0
  return {}
 end
 m:AddCallback(2,draw);m:AddCallback(21,draw)
 -- Keep entity scanning enabled; a render must never synthesize updates.
 m:AddCallback(0,function()end);m:AddCallback(31,function()end)
 )lua";
 assert(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@pickup-map.lua")==LuaRuntime::LuaInitResult::Success);
 InstallRenderOrderInputs();isaac::runtime::SetManagedUpdateSnapshotReaderForTest(Snapshot);
 LuaRuntime::NoteGameStarted(false);LuaRuntime::DispatchPostUpdate();Render(shader);
 assert(Number("rooms",1)&&Number("updates",1)&&Number("mapStart",1)&&Number("badWrites",0));
 locationReads=roomVisits=playerVisits=0;
 unsigned roomEvents=1;
 for(unsigned index:{82u,85u,84u,82u}){
  currentLocation.roomIndex=index;pickup=index==84?1:index==82?2:3;
  isaac::runtime::NoteNativeRoomLoaded();
  if(mode=="retry"&&roomEvents==1){
   locationReady=false;Render(false);assert(!Render(true));
   assert(Number("renders",1)&&Number("rooms",1)&&Number("badWrites",0));locationReady=true;
  }
  if(mode=="paused")paused=true;
  if(mode=="level"&&roomEvents==1){
   currentLocation.stage=2;
   isaac::runtime::g_NativeLoadedLevelKey.store(1);
   Render(false);assert(!Render(true));assert(Number("renders",1)&&Number("rooms",1));
   isaac::runtime::g_NativeLoadedLevelKey.store(2);
  }
  if(mode=="callback_load"&&roomEvents==1){
   Render(false);assert(Number("renders",1)&&Number("rooms",2));++roomEvents;
  }
  assert(Render(shader));++roomEvents;
  if(!Number("badWrites",0)||!Number("rooms",roomEvents)){
   std::puts("new-room pickups were drawn with the previous room cache");return 21;
  }
  assert(Number("updates",1)&&roomVisits==0&&playerVisits==0);
  const auto reads=locationReads;
  for(unsigned n=0;n<8;++n){Render(shader);Render(!shader);}
  assert(locationReads==reads&&roomVisits==0&&playerVisits==0);
 }
 assert(Number("mapStart",1)&&Number("mapShop",2)&&Number("mapThird",3));
 assert(Number("levels",mode=="level"?2:1));
 paused=false;++nativeFrame;LuaRuntime::DispatchPostUpdate();
 assert(Number("rooms",mode=="callback_load"?6:5)&&Number("updates",2)&&Number("badWrites",0));
 assert(roomVisits==1&&playerVisits==1);
 std::printf("PASS %s: three distinct room icons, no extra scans or updates\n",mode.c_str());
}
'''


class RoomRenderCallbackOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='isaac-room-render-order-')
        path = Path(cls.tmp.name)
        prefix = fixture.HARNESS.split('int main(', 1)[0]
        prefix = prefix.replace(
            'GameIsPausedObservation ObserveGameIsPaused(uintptr_t, uintptr_t) {\n'
            '    return GameIsPausedObservation::ThunkUnavailable;\n}', '')
        prefix = re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}',
                        '', prefix, count=1)
        runtime = ROOT / 'runtime/source/lua_runtime.cpp'
        runtime_copy = path / 'runtime_render_order.cpp'
        runtime_copy.write_text(runtime.read_text() + BRIDGE)
        api = ROOT / 'runtime/src/interfaces/lua/isaac_api.cpp'
        api_text = api.read_text()
        for name, hook in (('VisitRoomEntities', 'RenderOrderVisitRoom'),
                           ('VisitPlayerEntities', 'RenderOrderVisitPlayer')):
            signature = f'void {name}(EntityVisitFn visit, void* context) noexcept {{'
            assert api_text.count(signature) == 1
            api_text = api_text.replace(signature, signature + f'\n    {hook}();')
        api_copy = path / 'api_render_order.cpp'
        api_copy.write_text('extern "C" void RenderOrderVisitRoom();\n'
                            'extern "C" void RenderOrderVisitPlayer();\n' + api_text)
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

    def test_post_render_keeps_pickups_in_their_own_rooms(self): self.check_mode('render')
    def test_shader_hud_keeps_pickups_in_their_own_rooms(self): self.check_mode('shader')
    def test_failed_location_waits_before_render_and_retries(self): self.check_mode('retry')
    def test_pause_still_delivers_completed_room_before_render(self): self.check_mode('paused')
    def test_early_stage_waits_for_native_load_completion(self): self.check_mode('level')
    def test_load_inside_room_callback_waits_for_final_destination(self): self.check_mode('callback_load')


if __name__ == '__main__':
    unittest.main()
