"""生产实体入口须按PC类型/变体/刀子类型筛选，并先初始化再更新。"""
import subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import test_lua_entity_player as fixture
from . import test_support
MAIN=r'''
namespace LuaRuntime { void ExerciseEntityFamily(uintptr_t,bool,bool); }
int main(int argc,char**argv){
 if(argc!=2)return 90;
 static_cast<void>(&CorruptVtable);static_cast<void>(&PublishNullCostumes);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);
 CreateBlocks();FillPlayer(true);PublishOwnerSlot(AddressOf(g_OwnerSlotBytes));WriteWord(g_OwnerSlotBytes,0,AddressOf(g_GameBytes));PublishPlayers({AddressOf(g_PlayerBytes)});
 const int kind=std::atoi(argv[1]);
 const unsigned types[]={13,3,2,9,7,8,1000,4,5,1};
 const char*init[]={"MC_POST_NPC_INIT","MC_FAMILIAR_INIT","MC_POST_TEAR_INIT","MC_POST_PROJECTILE_INIT","MC_POST_LASER_INIT","MC_POST_KNIFE_INIT","MC_POST_EFFECT_INIT","MC_POST_BOMB_INIT","MC_POST_PICKUP_INIT","MC_POST_PLAYER_INIT"};
 const char*update[]={"MC_NPC_UPDATE","MC_FAMILIAR_UPDATE","MC_POST_TEAR_UPDATE","MC_POST_PROJECTILE_UPDATE","MC_POST_LASER_UPDATE","MC_POST_KNIFE_UPDATE","MC_POST_EFFECT_UPDATE","MC_POST_BOMB_UPDATE","MC_POST_PICKUP_UPDATE","MC_POST_PLAYER_UPDATE"};
 const char*render[]={nullptr,"MC_POST_FAMILIAR_RENDER","MC_POST_TEAR_RENDER","MC_POST_PROJECTILE_RENDER","MC_POST_LASER_RENDER","MC_POST_KNIFE_RENDER","MC_POST_EFFECT_RENDER","MC_POST_BOMB_RENDER","MC_POST_PICKUP_RENDER","MC_POST_PLAYER_RENDER"};
 WriteAt<std::uint32_t>(g_PlayerBytes,kEntityTypeOffset,types[kind]);
 WriteAt<std::uint32_t>(g_PlayerBytes,kEntityVariantOffset,7);
 WriteAt<std::uint32_t>(g_PlayerBytes,kEntitySubTypeOffset,4);
 if(kind==1)WriteWord(g_PlayerBytes,0,g_EngineBase+kEntityFamiliarVtableOffset);
 if(kind==8)WriteWord(g_PlayerBytes,0,g_EngineBase+kEntityPickupVtableOffset);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 std::string script="local m=RegisterMod('family filters',1);_family={init=0,update=0,render=0,plain=0};local filter="+std::to_string(kind==0?13:kind==5?4:7)+";";
 script+="local function reg(id,label) m:AddCallback(id,function(_,e) assert(e~=nil); _family[label]=_family[label]+1; if label=='init' then e:GetData().initialized=true elseif label=='update' then assert(e:GetData().initialized,'UPDATE before INIT') end end,filter);m:AddCallback(id,function()error('wrong family filter invoked')end,filter+100);m:AddCallback(id,function()_family.plain=_family.plain+1 end) end;";
 script+="reg(ModCallbacks."+std::string(init[kind])+",'init');reg(ModCallbacks."+std::string(update[kind])+",'update');";
 if(render[kind])script+="reg(ModCallbacks."+std::string(render[kind])+",'render');";
 auto result=LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@family-filters.lua");if(result!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::ExerciseEntityFamily(AddressOf(g_PlayerBytes),kind==9,false);
 LuaRuntime::ExerciseEntityFamily(AddressOf(g_PlayerBytes),kind==9,false);
 if(render[kind])LuaRuntime::ExerciseEntityFamily(AddressOf(g_PlayerBytes),kind==9,true);
 if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView e[16]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,16);for(std::size_t i=0;i<n;++i)std::printf("FAMILY_FAIL %s\n",e[i].text);return 2;}
 for(auto pair:{std::pair<const char*,double>{"init",1},{"update",2},{"render",render[kind]?1.:0.},{"plain",render[kind]?4.:3.}}){double value=-1;if(LuaRuntime::ReadLuaTableNumber("_family",pair.first,&value)||value!=pair.second){std::printf("count %s %f expected %f\n",pair.first,value,pair.second);return 3;}}
 return 0;
}
'''
class EntityFamilyFiltersTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='isaac-family-filters-')
  source=fixture.SOURCE/'lua_runtime.cpp';copied=Path(cls.temp.name)/'runtime.cpp'
  copied.write_text(source.read_text()+r'''
namespace LuaRuntime {
void ExerciseEntityFamily(std::uintptr_t entity,bool player,bool render){
 EntityEventScan scan{};scan.registered=BuildRegisteredCallbackMask();scan.renderPhase=render;
 if(player)OnEntityEventPlayer(&scan,entity);else OnEntityEvent(&scan,entity);
}
}
''')
  sources=tuple(copied if p==source else p for p in test_support.layered_lua_runtime_sources(fixture.SOURCE))
  flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
  with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags),patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
   cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.temp.name),harness_source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_real_entity_family_entry_filters_and_initializes(self):
  for i,name in enumerate(['npc','familiar','tear','projectile','laser','knife','effect','bomb','pickup','player']):
   with self.subTest(family=name):
    r=subprocess.run([str(self.binary),str(i)],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
