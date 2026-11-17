"""播报选项是真实全局持久化状态；帧上getter/setter不做I/O。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include "interfaces/lua/rplus_options.hpp"
#include "domain/console/console_commands.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "ports/save_file_port.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
class Store final:public ISaveFilePort{
 public:bool exists{},failWrite{};std::string content;unsigned reads{},writes{},slots{};
 Status Read(std::string_view name,char*out,std::size_t capacity,std::size_t*size)noexcept override{
  if(name!=kRuntimeOptionsFileName)return Status{StatusCode::NotFound};++reads;
  if(!exists)return Status{StatusCode::NotFound};*size=content.size();
  if(content.size()>capacity)return Status{StatusCode::CapacityExceeded};
  std::memcpy(out,content.data(),content.size());return Status::Ok();
 }
 Status Write(std::string_view name,std::string_view data)noexcept override{
  assert(name==kRuntimeOptionsFileName);++writes;if(failWrite)return Status{StatusCode::IoFailure};content.assign(data);exists=true;return Status::Ok();
 }
 Status Remove(std::string_view)noexcept override{return Status::Ok();}
 Status Exists(const char*,bool*out)noexcept override{*out=false;return Status::Ok();}
 Status GetSaveSlot(unsigned*out)noexcept override{++slots;*out=2;return Status::Ok();}
};
static const RepentogonBatch kGateBatch{"runtime-options-gate",nullptr,0,nullptr,0,nullptr,0};
static const RepentogonCatalog kGateCatalog{&kGateBatch,1,nullptr};
static lua_State* OpenGateState(bool active){
 auto*state=luaL_newstate();luaL_requiref(state,"_G",luaopen_base,1);lua_pop(state,1);
 luaL_requiref(state,"string",luaopen_string,1);lua_pop(state,1);
 BeginRepentogonEnvironment(state,active,kGateCatalog);
 if(active)CompleteRepentogonEnvironment(state);
 static_cast<void>(RegisterOptionsTable(state));return state;
}
static void CloseGateState(lua_State*state){
 SuspendRepentogonEnvironment(state);lua_close(state);EndRepentogonEnvironment(state);
}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 Store store;SetSessionSaveFilePort(scene=="unavailable"?nullptr:&store);ClearRuntimeOptions();
 if(scene=="malformed"){store.exists=true;store.content="AnnouncerVoiceMode=2147483648\n";}
 if(scene=="malformed-stat"){store.exists=true;store.content="StatHUDPlanetarium=2\n";}
 if(scene=="autofill-zero"){store.exists=true;store.content="ConsoleAutofillLimit=0\n";}
 if(scene=="autofill-negative"){store.exists=true;store.content="ConsoleAutofillLimit=-1\n";}
 if(scene=="autofill-large"){store.exists=true;store.content="ConsoleAutofillLimit=2000\n";}
 if(scene=="autofill-prefix"){store.exists=true;store.content="ConsoleAutofillLimit=7ignored\n";}
 if(scene=="autofill-invalid"){store.exists=true;store.content="ConsoleAutofillLimit=invalid\n";}
 if(scene=="raw"){store.exists=true;store.content="AnnouncerVoiceMode=-3\n";}
 if(scene=="stathud"){store.exists=true;store.content="StatHUDPlanetarium=0\n";}
 if(scene=="autofill"){store.exists=true;store.content="ConsoleAutofillLimit=37\n";}
 const auto loaded=LoadRuntimeOptions();
 if(scene=="unavailable")assert(loaded.code()==StatusCode::Unsupported);
 else if(scene=="malformed"||scene=="malformed-stat")assert(loaded.code()==StatusCode::Corrupted);
 else assert(loaded.ok());
 if(scene=="autofill-zero"||scene=="autofill-negative"||scene=="autofill-large"||
    scene=="autofill-prefix"||scene=="autofill-invalid"){
  const int expected=scene=="autofill-zero"?0:scene=="autofill-negative"?-1:
                     scene=="autofill-large"?2000:scene=="autofill-prefix"?7:10;
  assert(RuntimeOptionConsoleAutofillLimit()==expected);
  assert(console::ConsoleAutofillLimit()==expected);
  return 0;
 }
 assert(TryPushRuntimeOption(nullptr,"Language")==0);
 assert(TryPushRuntimeOption(nullptr,"StatHUDPlanetarium")==0);
 assert(!TryWriteRuntimeOption(nullptr,"HUDOffset"));
 if(scene=="default"){
  assert(RuntimeOptionConsoleAutofillLimit()==10);
  auto*state=OpenGateState(false);
  const int status=luaL_dostring(state,R"lua(
assert(Options.AnnouncerVoiceMode==0)
Options.AnnouncerVoiceMode=1;assert(Options.AnnouncerVoiceMode==1);Options.AnnouncerVoiceMode=0
assert(Options.StatHUDPlanetarium==nil and rawget(Options,'StatHUDPlanetarium')==nil)
local ok,err=pcall(function()Options.StatHUDPlanetarium=true end)
assert(not ok and type(err)=='string' and err:find('REPENTOGON',1,true))
assert(rawget(Options,'StatHUDPlanetarium')==nil)
)lua");
  if(status!=LUA_OK)std::fprintf(stderr,"disabled gate: %s\n",lua_tostring(state,-1));
  CloseGateState(state);if(status!=LUA_OK)return 30;
  state=OpenGateState(true);
  const int enabledStatus=luaL_dostring(state,R"lua(
assert(Options.StatHUDPlanetarium==true and rawget(Options,'StatHUDPlanetarium')==nil)
Options.StatHUDPlanetarium=false;assert(Options.StatHUDPlanetarium==false)
Options.StatHUDPlanetarium=true;assert(Options.StatHUDPlanetarium==true)
for _,value in ipairs({0,1,'true',{}})do assert(not pcall(function()Options.StatHUDPlanetarium=value end))end
assert(not pcall(function()Options.StatHUDPlanetarium=nil end))
assert(rawget(Options,'StatHUDPlanetarium')==nil)
)lua");
  if(enabledStatus!=LUA_OK)std::fprintf(stderr,"enabled gate: %s\n",lua_tostring(state,-1));
  CloseGateState(state);if(enabledStatus!=LUA_OK)return 31;
  assert(RuntimeOptionStatHudPlanetarium());
 }
 if(scene=="preserve"){
  auto*state=OpenGateState(true);
  int status=luaL_dostring(state,"Options.AnnouncerVoiceMode=2");
  if(status!=LUA_OK)std::fprintf(stderr,"preserve A: %s\n",lua_tostring(state,-1));
  CloseGateState(state);if(status!=LUA_OK)return 32;
  assert(FlushRuntimeOptions().ok());
  assert(store.content=="AnnouncerVoiceMode=2\r\nStatHUDPlanetarium=1\r\nConsoleAutofillLimit=10\r\n");
  ClearRuntimeOptions();assert(LoadRuntimeOptions().ok());
  state=OpenGateState(true);
  status=luaL_dostring(state,"Options.StatHUDPlanetarium=false");
  if(status!=LUA_OK)std::fprintf(stderr,"preserve B: %s\n",lua_tostring(state,-1));
  CloseGateState(state);if(status!=LUA_OK)return 33;
  assert(FlushRuntimeOptions().ok());
  assert(store.content=="AnnouncerVoiceMode=2\r\nStatHUDPlanetarium=0\r\nConsoleAutofillLimit=10\r\n");
  ClearRuntimeOptions();assert(LoadRuntimeOptions().ok());
  if(RuntimeOptionConsoleAutofillLimit()!=10)return 34;
  SetRuntimeOptionConsoleAutofillLimit(37);
  assert(console::ConsoleAutofillLimit()==37);
  assert(FlushRuntimeOptions().ok());
  assert(store.content=="AnnouncerVoiceMode=2\r\nStatHUDPlanetarium=0\r\nConsoleAutofillLimit=37\r\n");
  ClearRuntimeOptions();assert(LoadRuntimeOptions().ok());
  return RuntimeOptionConsoleAutofillLimit()==37?0:35;
 }
 if(scene=="autofill"){
  if(console::ConsoleAutofillLimit()!=37||RuntimeOptionConsoleAutofillLimit()!=37)return 36;
  SetRuntimeOptionConsoleAutofillLimit(0);assert(console::ConsoleAutofillLimit()==1);
  SetRuntimeOptionConsoleAutofillLimit(2000);assert(console::ConsoleAutofillLimit()==1000);
  SetRuntimeOptionConsoleAutofillLimit(12);
  assert(FlushRuntimeOptions().ok());
  assert(store.content=="AnnouncerVoiceMode=0\r\nStatHUDPlanetarium=1\r\nConsoleAutofillLimit=12\r\n");
  return 0;
 }
 if(scene=="replace"){
  SetRuntimeOptionConsoleAutofillLimit(12);
  assert(RuntimeOptionStatsSnapshot().dirty);
  Store replacement;
  SetSessionSaveFilePort(&replacement);
  const auto replaced=LoadRuntimeOptions();
  if(replaced.code()!=StatusCode::InvalidState)return 37;
  if(!RuntimeOptionStatsSnapshot().dirty)return 38;
  SetSessionSaveFilePort(&store);
  if(!FlushRuntimeOptions().ok()||RuntimeOptionStatsSnapshot().dirty)return 39;
  return 0;
 }
 // 原1.60 shouldPlayVoiceover逐字分支；只替其Random/RNG依赖，不替Options。
 const char*consumer=R"lua(
 local rng={SetSeed=function()end,RandomFloat=function()return .25 end};local Random=function()return 123 end
 local function shouldPlayVoiceover()
  local ann = Options.AnnouncerVoiceMode
  if ann == 2 then
   return true
  elseif ann == 1 then
   return false
  else
   rng:SetSeed(Random() + 1, 1)
   return rng:RandomFloat() < 0.5
  end
 end
 local SoundDelays={[100]=2};local delayedSounds={};local played={};local sfx={Play=function(_,id)played[id]=(played[id]or 0)+1 end}
 local function playDelayed(soundId)
  if shouldPlayVoiceover() then
   if SoundDelays[soundId] then
    table.insert(delayedSounds, {soundId, SoundDelays[soundId]})
   else
    sfx:Play(soundId)
   end
  end
 end
 local n=0;local m=RegisterMod('runtime-options-consumer',1);m:AddCallback(1,function()n=n+1;
 )lua";
 const char*body=R"lua(
 if n==1 then
  assert(Options.AnnouncerVoiceMode==0 and shouldPlayVoiceover())
  rng.RandomFloat=function()return .75 end;assert(not shouldPlayVoiceover())
  Options.AnnouncerVoiceMode=1;assert(not shouldPlayVoiceover());playDelayed(100);playDelayed(101);assert(#delayedSounds==0 and played[101]==nil)
  Options.AnnouncerVoiceMode=2;assert(shouldPlayVoiceover());playDelayed(100);playDelayed(101);assert(#delayedSounds==1 and played[101]==1)
  local previous=2;for i=1,10000 do assert(Options.AnnouncerVoiceMode==previous);previous=i%3;Options.AnnouncerVoiceMode=previous end
  Options.AnnouncerVoiceMode=2
 elseif n==2 then assert(Options.AnnouncerVoiceMode==2);Options.AnnouncerVoiceMode=1
 else assert(Options.AnnouncerVoiceMode==1) end
 _opts={done=n}
 )lua";
 if(scene=="default")body="assert(Options.AnnouncerVoiceMode==0);assert(Options.StatHUDPlanetarium==nil);for i=1,10000 do assert(Options.AnnouncerVoiceMode==0)end;_opts={done=n}";
 if(scene=="raw")body="assert(Options.AnnouncerVoiceMode==-3 and shouldPlayVoiceover());_opts={done=n}";
 if(scene=="stathud")body="assert(Options.StatHUDPlanetarium==nil);assert(not pcall(function()Options.StatHUDPlanetarium=true end));assert(rawget(Options,'StatHUDPlanetarium')==nil);_opts={done=n}";
 if(scene=="unavailable"||scene=="malformed"||scene=="malformed-stat"||scene=="malformed-autofill")body="assert(not pcall(function()return Options.AnnouncerVoiceMode end));assert(not pcall(function()Options.AnnouncerVoiceMode=1 end));assert(Options.StatHUDPlanetarium==nil);_opts={done=n}";
 if(scene=="types")body=R"lua(
 Options.AnnouncerVoiceMode=-5;assert(Options.AnnouncerVoiceMode==0)
 Options.AnnouncerVoiceMode=9;assert(Options.AnnouncerVoiceMode==2)
 Options.AnnouncerVoiceMode=4294967297;assert(Options.AnnouncerVoiceMode==1)
 Options.AnnouncerVoiceMode="1";assert(Options.AnnouncerVoiceMode==1)
 for _,v in ipairs({true,false,1.5,{}})do assert(not pcall(function()Options.AnnouncerVoiceMode=v end))end
 assert(not pcall(function()Options.AnnouncerVoiceMode=nil end));Options.AnnouncerVoiceMode=0;_opts={done=n}
 )lua";
 const auto script=std::string(consumer)+body+"end)";
 if(LuaRuntime::InitializeFromBuffer(script.c_str(),script.size(),"@rplus-options.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 const auto before=store.reads;LuaRuntime::DispatchPostUpdate();
 if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView errors[8]{};auto count=LuaRuntime::CopyLuaErrorHistory(errors,8);for(unsigned i=0;i<count;++i)fprintf(stderr,"%s\n",errors[i].text);return 2;}
 if(store.reads!=before||store.writes!=0||store.slots!=0)return 3;
 if(scene=="unavailable"||scene=="malformed"||scene=="malformed-stat"||scene=="malformed-autofill")return 0;
 if(scene=="stathud"){
  if(RuntimeOptionStatHudPlanetarium())return 20;
  SetRuntimeOptionStatHudPlanetarium(true);
  if(!RuntimeOptionStatHudPlanetarium())return 20;
  if(!FlushRuntimeOptions().ok()||store.writes!=1||
     store.content!="AnnouncerVoiceMode=0\r\nStatHUDPlanetarium=1\r\nConsoleAutofillLimit=10\r\n")return 21;
  return 0;
 }
 if(scene!="roundtrip")return FlushRuntimeOptions().ok()&&store.writes==0?0:4;
 if(!RuntimeOptionStatsSnapshot().dirty||!FlushRuntimeOptions().ok()||store.writes!=1||
    store.content!="AnnouncerVoiceMode=2\r\nStatHUDPlanetarium=1\r\nConsoleAutofillLimit=10\r\n")return 5;
 if(!FlushRuntimeOptions().ok()||store.writes!=1)return 6;
 ClearRuntimeOptions();if(!LoadRuntimeOptions().ok())return 7;LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 8;
 store.failWrite=true;const auto failed=FlushRuntimeOptions();if(failed.code()!=StatusCode::IoFailure||!RuntimeOptionStatsSnapshot().dirty||RuntimeOptionStatsSnapshot().mode!=1)return 9;
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 10;
 store.failWrite=false;if(!FlushRuntimeOptions().ok()||RuntimeOptionStatsSnapshot().dirty)return 11;
 ClearRuntimeOptions();if(!LoadRuntimeOptions().ok())return 12;LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 13;
 return store.reads==3&&store.writes==3&&store.slots==0&&
        store.content=="AnnouncerVoiceMode=1\r\nStatHUDPlanetarium=1\r\nConsoleAutofillLimit=10\r\n"?0:14;
}
'''
class RuntimeOptionsConsumers(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-runtime-options-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  extra=ROOT/'runtime/src/interfaces/lua/rplus_options.cpp'
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source,extra_sources=()if extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_original_voiceover_rules_persistence_and_no_frame_io(self):
  for scene in ('roundtrip','default','types','raw','stathud','autofill','preserve','replace','malformed','malformed-stat','autofill-zero','autofill-negative','autofill-large','autofill-prefix','autofill-invalid','unavailable'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],text=True,capture_output=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
