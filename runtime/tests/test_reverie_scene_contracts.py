"""Contracts needed by Reverie's ordinary familiar, HUD and laser workloads."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from . import test_support
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include "interfaces/lua/rplus_extended_fields.hpp"
#include "interfaces/lua/rplus_extended_fields_guards.hpp"
#include <cassert>
static unsigned spawners{};
[[maybe_unused]] static void SetSpawner(void*self,void*target){++spawners;std::memcpy(static_cast<char*>(self)+0x3a8,&target,8);}
template<class T>void BindSpawner(T&b){if constexpr(requires{b.setSpawner;})b.setSpawner=SetSpawner;}
extern "C" {extern std::uint32_t g_HostEngineCallTrampolineCalls;extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];}
int main(int argc,char**argv){
 if(argc!=2)return 90;static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();if(g_RoomBytes.size()<0x2000)g_RoomBytes.resize(0x2000);FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);
 std::memcpy(g_ModuleBytes.data()+kEntityNpcCanShutDoorsMethodOffset,kEntityNpcCanShutDoorsExpectedBytes.data(),kEntityNpcCanShutDoorsExpectedBytes.size());
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 namespace guards=isaac::runtime::extended_fields;
 auto guard=[&](auto o,const auto&b){std::memcpy(g_ModuleBytes.data()+o,b.data(),b.size());};
 /*GUARDS*/
 WriteAt<std::uint32_t>(g_ModuleBytes,kLevelAddCurseOffset,kLevelAddCurseEntryWord);
 isaac::runtime::ExtendedFieldsNativeTestBindings bindings{};BindSpawner(bindings);isaac::runtime::SetExtendedFieldsNativeTestBindings(bindings);
 std::vector<unsigned char> grid(0x100);
 WriteWord(grid,0,g_EngineBase+kGridEntityVtableOffset);
 WriteWord(g_RoomBytes,kRoomGridEntityTableOffset,AddressOf(grid));
 // The 448-entry grid array ends exactly where the separate door table begins.
 WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+447*8,AddressOf(grid));
 WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+448*8,AddressOf(grid));
 WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+456*8,1); // adjacent door indices are not pointers
 const std::string scene=argv[1];std::string script="local m=RegisterMod('scene contracts',1);";
 if(scene=="familiar")script+=R"lua(
 local f=Isaac.FindByType(3,5)[1];assert(f and f.AddToOrbit==nil and type(f:ToFamiliar().AddToOrbit)=='function')
 local n=Isaac.FindByType(20,5)[1];assert(type(n.CanShutDoors)=='function' and type(n:ToNPC().CanShutDoors)=='boolean')
 for _,v in ipairs(Isaac.FindInRadius(Vector.Zero,1000,EntityPartition.FAMILIAR))do assert(v.AddToOrbit==nil)end
 for _,v in ipairs(Isaac.GetRoomEntities())do if v.Type==3 and v.Variant==5 then assert(v.GetOrbitPosition==nil and type(v:ToFamiliar().GetOrbitPosition)=='function')end end
 m:AddCallback(6,function(_,v)assert(type(v.RemoveFromFollowers)=='function');familiarCalled=1 end,5)
 )lua";
 else if(scene=="color")script+=R"lua(
 local c=Color.Default;assert(type(c)=='userdata' and c.R==1 and c.A==1 and c.RO==0)
 assert(rawequal(c,Color.Default));c.A=.75;assert(Color.Default.A==.75)
 assert(Color.Lerp(Color(1,1,1,0),Color.Default,1).A==.75)
 )lua";
 else if(scene=="spawner")script+=R"lua(
 local p=Isaac.GetPlayer(0);local f=Isaac.FindByType(3,5)[1]
 p.SpawnerEntity=f;assert(p.SpawnerEntity.Index==f.Index)
 p.SpawnerEntity=p;assert(p.SpawnerEntity.Index==p.Index)
 p.SpawnerEntity=nil;assert(p.SpawnerEntity==nil)
 assert(not pcall(function()p.SpawnerEntity={}end))
 )lua";
 else if(scene=="grid")script+=R"lua(
 local room=Game():GetRoom();assert(type(room:GetGridEntity(0))=='userdata');assert(room:GetGridEntity(-1)==nil)
 assert(room:GetGridEntity(-2147483648)==nil)
 assert(type(room:GetGridEntity(447))=='userdata')
 assert(room:GetDoor(0),'the neighboring door table is deliberately occupied')
 assert(room:GetGridEntity(448)==nil,'grid queries must not alias the door table')
 for _,i in ipairs({449,456,476,2147483647})do assert(room:GetGridEntity(i)==nil)end
 assert(not pcall(function()room:GetGridEntity({})end))
 )lua";
 else if(scene=="curse")script+="Game():GetLevel():AddCurse(1);Game():GetLevel():AddCurse(1,nil)";
 else return 91;
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@scene-contracts.lua")!=LuaRuntime::LuaInitResult::Success){char e[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::fprintf(stderr,"%s\n",e);return 1;}
 if(scene=="familiar"){LuaRuntime::DispatchPostUpdate();double v{};if(!LuaRuntime::ReadLuaGlobalNumber("familiarCalled",&v)||v!=1)return 2;}
 if(scene=="spawner"&&spawners!=3)return 3;
 if(scene=="curse"&&(g_HostEngineCallTrampolineCalls!=2||g_HostEngineCallTrampolineLastIntegers[2]!=0))return 4;
 if(LuaRuntime::TakeCallbackError())return 5;return 0;
}
'''
class ReverieSceneContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='reverie-scene-')
  header=(ROOT/'runtime/src/interfaces/lua/rplus_extended_fields_guards.hpp').read_text()
  guards='\n'.join(f'guard(guards::k{n}Entry,guards::k{n}Guard);'for n in re.findall(r'k(\w+)Entry=',header))
  prefix=fixture.HARNESS.split('int main(',1)[0]
  prefix=prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}', '')
  source=prefix+'GameRoomObservation ReadCurrentGameRoom(uintptr_t,void**out){*out=g_RoomBytes.data();return GameRoomObservation::Success;}\n'+MAIN.replace('/*GUARDS*/',guards)
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_scene(self,scene):
  result=subprocess.run([str(self.binary),scene],text=True,capture_output=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
 def test_base_queries_and_typed_familiar_callbacks_match_pc(self):self.run_scene('familiar')
 def test_color_default_has_pc_bootstrap_identity(self):self.run_scene('color')
 def test_spawner_assignment_uses_native_setter(self):self.run_scene('spawner')
 def test_addcurse_omitted_boolean_is_false(self):self.run_scene('curse')
 def test_negative_grid_indices_return_nil(self):self.run_scene('grid')
