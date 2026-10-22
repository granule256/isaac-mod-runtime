"""名字必须消费原生实际配置ID，而非XML拟定编号或本体快照。"""
import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
BASELINE=r'''
#include "interfaces/lua/rplus_content_names.hpp"
#include "interfaces/lua/rplus_content_names_guards.hpp"
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 std::vector<unsigned char> manager(kManagerEntityConfigOffset+0xb0),slot(8),pill(0x60),pills(8);
 WriteWord(slot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(slot));
 std::int32_t id=67;std::memcpy(pill.data(),&id,4);const char*name="Estrogen Up";pill[8]=22;std::memcpy(pill.data()+9,name,11);
 WriteWord(pills,0,AddressOf(pill));WriteWord(manager,kManagerItemConfigOffset+0x60,AddressOf(pills));WriteWord(manager,kManagerItemConfigOffset+0x68,AddressOf(pills)+8);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 WriteWord(manager,kManagerEntityConfigOffset,AddressOf(manager)+kManagerEntityConfigOffset+8);
 namespace guard=isaac::runtime::content_names;auto bytes=[&](auto off,const auto&v){std::memcpy(g_ModuleBytes.data()+off,v.data(),v.size());};
 bytes(guard::kPillVectorEntry,guard::kPillVectorGuard);bytes(guard::kPillNameEntry,guard::kPillNameGuard);bytes(guard::kEntityTreeEntry,guard::kEntityTreeGuard);bytes(guard::kEntityValueEntry,guard::kEntityValueGuard);bytes(guard::kEntityNameEntry,guard::kEntityNameGuard);bytes(guard::kEntitySizeEntry,guard::kEntitySizeGuard);bytes(guard::kEntityIdsEntry,guard::kEntityIdsGuard);
 if(!isaac::runtime::RefreshRuntimeContentNames())return 3;
 const char*script="local m=RegisterMod('native-name-red',1);m:AddCallback(1,function()assert(Isaac.GetPillEffectByName('Estrogen Up')==67)end)";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@native-name-red.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();return LuaRuntime::TakeCallbackError()?2:0;
}
'''
class ContentNameConsumerTests(unittest.TestCase):
 def test_mod_pill_uses_actual_loaded_native_id(self):
  with tempfile.TemporaryDirectory(prefix='isaac-content-name-')as d:
   source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+BASELINE
   source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=source)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,'原生已加载pill67，但动态名字查询没有消费：'+r.stdout+r.stderr)
NATIVE_MAIN=r'''
#include "interfaces/lua/rplus_content_names.hpp"
#include "interfaces/lua/rplus_content_names_guards.hpp"
#include <cassert>
static void Word(std::vector<unsigned char>&v,std::size_t off,std::int32_t n){std::memcpy(v.data()+off,&n,4);}
static void Name(std::vector<unsigned char>&v,std::size_t off,const std::string&name,std::vector<unsigned char>&longName){
 std::memset(v.data()+off,0,24);
 if(name.size()<=22){v[off]=static_cast<unsigned char>(name.size()*2);std::memcpy(v.data()+off+1,name.data(),name.size());}
 else{longName.assign(name.begin(),name.end());longName.push_back(0);WriteWord(v,off,(name.size()+1)|1);WriteWord(v,off+8,name.size());WriteWord(v,off+16,AddressOf(longName));}
}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 std::vector<unsigned char> manager(kManagerEntityConfigOffset+0xb0),slot(8),pills(7*8),pill[6],nodes[4],pillLong[6],entityLong[4];
 WriteWord(slot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(slot));
 const std::string pillNames[]={"#HEALTH_UP","Estrogen Up","Same Pill","Same Pill","Long Native Pill Effect Name","42"};const std::int32_t ids[]={1,67,51,79,77,81};
 for(unsigned i=0;i<6;++i){pill[i].assign(0x60,0);Word(pill[i],0,ids[i]);Name(pill[i],8,pillNames[i],pillLong[i]);WriteWord(pills,(i+1)*8,AddressOf(pill[i]));}
 WriteWord(manager,kManagerItemConfigOffset+0x60,AddressOf(pills));WriteWord(manager,kManagerItemConfigOffset+0x68,AddressOf(pills)+pills.size());
 const auto cfg=AddressOf(manager)+kManagerEntityConfigOffset,end=cfg+8;
 const std::string entityNames[]={"Duplicate Entity","Crippling Hands Helper","Duplicate Entity","Long Loaded Entity Configuration Name"};
 const std::int32_t types[]={23,1000,1001,1000},variants[]={1,2002,0,2003};
 for(unsigned i=0;i<4;++i){nodes[i].assign(0x1d8,0);Word(nodes[i],0x20,(types[i]<<20)|(variants[i]<<8));Word(nodes[i],0x28,types[i]);Word(nodes[i],0x2c,variants[i]);Word(nodes[i],0x30,0);Name(nodes[i],0x38,entityNames[i],entityLong[i]);}
 WriteWord(nodes[1],0,AddressOf(nodes[0]));WriteWord(nodes[1],8,AddressOf(nodes[2]));WriteWord(nodes[1],16,end);
 WriteWord(nodes[0],16,AddressOf(nodes[1]));WriteWord(nodes[2],0,AddressOf(nodes[3]));WriteWord(nodes[2],16,AddressOf(nodes[1]));WriteWord(nodes[3],16,AddressOf(nodes[2]));
 WriteWord(manager,kManagerEntityConfigOffset,AddressOf(nodes[0]));WriteWord(manager,kManagerEntityConfigOffset+8,AddressOf(nodes[1]));WriteWord(manager,kManagerEntityConfigOffset+16,4);
 namespace guard=isaac::runtime::content_names;
 auto bytes=[&](auto off,const auto&v){std::memcpy(g_ModuleBytes.data()+off,v.data(),v.size());};
 bytes(guard::kPillVectorEntry,guard::kPillVectorGuard);bytes(guard::kPillNameEntry,guard::kPillNameGuard);bytes(guard::kEntityTreeEntry,guard::kEntityTreeGuard);bytes(guard::kEntityValueEntry,guard::kEntityValueGuard);bytes(guard::kEntityNameEntry,guard::kEntityNameGuard);bytes(guard::kEntitySizeEntry,guard::kEntitySizeGuard);bytes(guard::kEntityIdsEntry,guard::kEntityIdsGuard);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 if(scene=="badguard")g_ModuleBytes[guard::kEntityIdsEntry]^=1;
 if(scene=="malformed")WriteWord(nodes[3],16,AddressOf(nodes[3]));
 if(scene=="oom")isaac::runtime::SetRuntimeContentNameAllocationFailureForTest(true);
 if(scene=="empty"){WriteWord(manager,kManagerItemConfigOffset+0x60,0);WriteWord(manager,kManagerItemConfigOffset+0x68,0);WriteWord(manager,kManagerEntityConfigOffset,end);WriteWord(manager,kManagerEntityConfigOffset+8,0);WriteWord(manager,kManagerEntityConfigOffset+16,0);}
 bool built=isaac::runtime::RefreshRuntimeContentNames();if(built!=(scene=="normal"||scene=="reload"||scene=="clear"||scene=="empty"))return 1;
 auto stats=isaac::runtime::RuntimeContentNameStatsSnapshot();if(stats.ready!=built)return 2;
 if(scene=="clear")isaac::runtime::ClearRuntimeContentNames();
 if(scene=="reload"){
  Word(pill[1],0,68);Word(nodes[1],0x2c,2001);Word(nodes[1],0x20,(1000<<20)|(2001<<8));
  // 同根、同begin/root/size：只有显式加载边界刷新才能看见实际新ID。
  if(!isaac::runtime::RefreshRuntimeContentNames())return 3;
 }
 std::string script=R"lua(local m=RegisterMod('loaded-config-names',1);_names={count=0};m:AddCallback(1,function()
 )lua";
 if(!built||scene=="clear")script+=R"lua(assert(not pcall(function()Isaac.GetPillEffectByName('Estrogen Up')end));assert(not pcall(function()Isaac.GetEntityVariantByName('Crippling Hands Helper')end)))lua";
 else if(scene=="empty")script+="assert(Isaac.GetPillEffectByName('#HEALTH_UP')==-1 and Isaac.GetEntityTypeByName('Crippling Hands Helper')==0 and Isaac.GetEntityVariantByName('Crippling Hands Helper')==-1)";
 else{
  script+="assert(Isaac.GetPillEffectByName('Estrogen Up')=="+std::to_string(scene=="reload"?68:67)+")\n";
  script+="assert(Isaac.GetEntityTypeByName('Crippling Hands Helper')==1000 and Isaac.GetEntityVariantByName('Crippling Hands Helper')=="+std::to_string(scene=="reload"?2001:2002)+")\n";
  script+=R"lua(
  assert(Isaac.GetPillEffectByName('#HEALTH_UP')==1 and Isaac.GetPillEffectByName('#health_up')==-1)
  assert(Isaac.GetPillEffectByName('Same Pill')==79)
  assert(Isaac.GetPillEffectByName('Long Native Pill Effect Name')==77 and Isaac.GetPillEffectByName(42)==81)
  assert(Isaac.GetPillEffectByName('Estrogen Up\0hidden')==-1)
  assert(Isaac.GetEntityTypeByName('Duplicate Entity')==23 and Isaac.GetEntityVariantByName('Duplicate Entity')==1)
  assert(Isaac.GetEntityTypeByName('Long Loaded Entity Configuration Name')==1000 and Isaac.GetEntityVariantByName('Long Loaded Entity Configuration Name')==2003)
  assert(Isaac.GetEntityTypeByName('crippling hands helper')==0 and Isaac.GetEntityVariantByName('Missing')==-1)
  assert(not pcall(function()Isaac.GetEntityTypeByName(nil)end))
  assert(not pcall(function()Isaac.GetPillEffectByName(false)end))
  for i=1,10000 do assert(Isaac.GetEntityVariantByName('Crippling Hands Helper')>0)end
  )lua";
 }
 script+="\n_names.count=_names.count+1 end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@native-loaded-names.lua")!=LuaRuntime::LuaInitResult::Success)return 4;
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView errors[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(errors,8);for(unsigned i=0;i<n;++i)fprintf(stderr,"%s\n",errors[i].text);return 5;}
 double count=0;if(LuaRuntime::ReadLuaTableNumber("_names","count",&count)||count!=1)return 6;
 auto after=isaac::runtime::RuntimeContentNameStatsSnapshot();if(after.refreshes!=stats.refreshes+(scene=="reload"?1:0))return 7;
 return 0;
}
'''
class NativeContentNameTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-native-content-names-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+NATIVE_MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_loaded_ids_conflict_resolution_cache_lifecycle_and_pc_name_rules(self):
  for scene in ('normal','reload','clear','empty','oom','badguard','malformed'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
