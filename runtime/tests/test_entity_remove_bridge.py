"""67真实Lua：Exists清0/data仍在的时机、重复Remove、析构及地址复用。"""
import subprocess,tempfile,unittest,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'
HEADER=SOURCE/'entity_remove_hook.hpp'
MAIN=r'''
#include <regex>
#include "entity_remove_hook.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
static unsigned originalCalls=0,dtorCalls=0;
static void OriginalRemove(void* p){++originalCalls;auto*b=static_cast<unsigned char*>(p);b[kEntityExistsOffset]=0;b[kEntityExistsOffset+1]=1;}
static void RngDtor(void*){++dtorCalls;}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 auto& entity=g_Entities[scene=="player_dtor"?kPlayer:kEnemyA];WriteWord(entity,0,g_EngineBase+(scene=="player_dtor"?kEntityPlayerVtableOffset:kEntityNpcVtableOffset));entity[kEntityExistsOffset]=1;
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 isaac::runtime::EntityRemoveNativeBindings native{};native.remove=OriginalRemove;native.destroyRng=RngDtor;
 std::string script=R"lua(
 local m=RegisterMod('remove67',1);local old=Isaac.FindByType(20)[1];local data=old:GetData();data.mark='before'
 _remove={count=0,tail=0,checked=0};SAVED=old;OLD_DATA=data
 m:AddCallback(1,function()end)
 m:AddCallback(67,function(_,e)
  _remove.count=_remove.count+1;assert(e:Exists()==false and e.Type==20)
  if _remove.count==1 then assert(e:GetData()==data and e:GetData().mark=='before')
  else assert(e:GetData()~=data and e:GetData().mark==nil) end
  e:GetData().callback='present'
 )lua";
 if(scene=="player_dtor"){
  script=std::regex_replace(script,std::regex("FindByType\\(20\\)\\[1\\]"),"GetPlayer()");
  script=std::regex_replace(script,std::regex("e.Type==20"),"e.Type==1");
  script=std::regex_replace(script,std::regex("end,20"),"end,1");
  script+="assert(SAVED:GetData()==data)";
 }
 if(scene=="non_nil")script+="return false";
 if(scene=="error")script+="error('remove67 error')";
 script+=R"lua(
 end,20)
 m:AddCallback(67,function()_remove.tail=_remove.tail+1 end,20)
 m:AddCallback(67,function()error('wrong entity type filter')end,5)
 )lua";
 if(scene=="player_dtor")script=std::regex_replace(script,std::regex("end,20"),"end,1");
 if(scene=="builtin")script+="\nIsaac.SetBuiltInCallbackState(67,false)";
 if(scene=="reuse")script+=R"lua(
 m:AddCallback(1,function()
   local fresh=Isaac.FindByType(20)[1]
   assert(fresh:GetData()~=OLD_DATA and fresh:GetData().mark==nil)
   local ok,value=pcall(function()return SAVED:GetData()end)
   assert(not ok or value==nil,'old handle used reused address')
   OLD_DATA.kept='usable';assert(OLD_DATA.mark=='before');_remove.checked=1
 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@remove67.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto address=AddressOf(entity);
 if(scene=="player_dtor"||scene=="dtor"||scene=="no_event"||scene=="reuse"){
  // 原D2已写base vptr、清Exists、setRemoved；x8=0是原Exists==0分支。
  WriteWord(entity,0,g_EngineBase+kEntityBaseVtableOffset);entity[kEntityExistsOffset]=0;
  isaac::runtime::relay::InternalHookContext ctx{};ctx.x[19]=address;ctx.x[8]=scene=="no_event"?0:1;ctx.x[0]=address+0x3d8;
  if(isaac::runtime::EntityDestructorRemoveInternalCallback(ctx,&native)!=0||dtorCalls!=1)return 2;
  if(scene=="reuse"){
   WriteWord(entity,0,g_EngineBase+kEntityNpcVtableOffset);entity[kEntityExistsOffset]=1;
   LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 3;
  }
 }else{
  isaac::runtime::RunEntityRemoveIntercept(&native,reinterpret_cast<void*>(address));
  if(originalCalls!=1||entity[kEntityExistsOffset]!=0)return 4;
  if(scene=="repeat")isaac::runtime::RunEntityRemoveIntercept(&native,reinterpret_cast<void*>(address));
 }
 double count=0,tail=0,checked=0;
 if(LuaRuntime::ReadLuaTableNumber("_remove","count",&count)||LuaRuntime::ReadLuaTableNumber("_remove","tail",&tail)||LuaRuntime::ReadLuaTableNumber("_remove","checked",&checked))return 5;
 unsigned want=scene=="builtin"||scene=="no_event"?0:scene=="repeat"?2:1;
 if(count!=want||tail!=(scene=="non_nil"||scene=="error"?0:want)||checked!=(scene=="reuse"?1:0))return 6;
 if(LuaRuntime::TakeCallbackError()!=(scene=="error"))return 7;
 return 0;
}
'''
class EntityRemoveBridgeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.binary=None
  if not HEADER.exists():return
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-remove67-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', source, count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source,extra_sources=(SOURCE/'entity_remove_hook.cpp',))
 @classmethod
 def tearDownClass(cls):
  if cls.binary:cls.tmp.cleanup()
 def test_native_bridge_exists(self):self.assertTrue(HEADER.exists(),'67原生移除桥尚未实现')
 def test_timing_repeated_remove_destructor_reuse_and_pc_runner(self):
  if not self.binary:self.skipTest('原生桥尚未实现')
  for scene in ('normal','repeat','dtor','player_dtor','no_event','reuse','non_nil','error','builtin'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
