"""Knife callbacks use PC KnifeSubType; self-made native bytes exercise real Lua.

No author source or game binary is a fixture. The small Lua callback mirrors the
range calculation and parent lookup needed by Bones & Sword without modifying
or importing that mod. The production callback registry, classifier, entity
views, native fields, FindByType, and Entity.Update binding remain in the path.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from . import test_lua_entity_query as fixture
from . import test_support

MAIN = r'''
#include "lua_object_handles.hpp"
#include "interfaces/lua/api400_fields.guards.hpp"
#include "interfaces/lua/api600_fields.guards.hpp"
#include "interfaces/lua/rplus_extended_fields_guards.hpp"
#include <cassert>
#include <cmath>
namespace LuaRuntime { void ExerciseRangeKnife(std::uintptr_t,bool); }
extern "C" { extern std::uint32_t g_HostEngineCallTrampolineCalls; }
template<class T>T ReadAt(const std::vector<unsigned char>&b,unsigned o){T v{};std::memcpy(&v,b.data()+o,sizeof(v));return v;}
static double Number(const char*n){double v{};assert(LuaRuntime::ReadLuaGlobalNumber(n,&v));return v;}
static void Check(){if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView e[16]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,16);for(std::size_t i=0;i<n;++i)std::fprintf(stderr,"CALLBACK_ERROR %s\n",e[i].text);std::abort();}}
int main(int argc,char**argv){
 assert(argc==3);const std::string mode=argv[1];const unsigned variant=std::atoi(argv[2]);
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();
 // Four live entities: player, a wrong-spawner candidate, a matching parent,
 // and the subtype-4 knife. Variant deliberately differs from subtype.
 for(auto&b:g_Entities)WriteWord(b,0,0);
 FillEntity(kPlayer,1,0,0,0,0,1,0,0,g_EngineBase+kEntityPlayerVtableOffset,0);
 FillEntity(kEnemyA,8,variant,0,10,20,1,1,kFrameNow,g_EngineBase+kEntityKnifeVtableOffset,0);
 FillEntity(kNoQuery,8,variant,0,100,200,1,2,kFrameNow,g_EngineBase+kEntityKnifeVtableOffset,0);
 FillEntity(kBullet,8,variant,4,300,400,1,3,kFrameNow,g_EngineBase+kEntityKnifeVtableOffset,0);
 auto&knife=g_Entities[kBullet];const auto entity=AddressOf(knife);
 WriteWord(g_Entities[kEnemyA],kEntitySpawnerEntityOffset,AddressOf(g_Entities[kNoQuery]));
 WriteWord(g_Entities[kNoQuery],kEntitySpawnerEntityOffset,AddressOf(g_Entities[kPlayer]));
 WriteWord(knife,kEntitySpawnerEntityOffset,AddressOf(g_Entities[kPlayer]));
 WriteWord(g_Entities[kPlayer],kEntityParentOffset,entity);
 WriteAt<LuaRuntime::VectorHandle>(knife,0x308,{45,12});
 WriteAt<float>(knife,0x420,2);WriteAt<float>(knife,0x430,90);
 WriteAt<LuaRuntime::VectorHandle>(knife,0x12c,{1.5F,2});
 WriteAt<LuaRuntime::VectorHandle>(knife,kEntityVelocityOffset,{7,8});
 PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 namespace F=isaac::runtime::api400_fields;namespace E=isaac::runtime::extended_fields;
 std::memcpy(g_ModuleBytes.data()+F::kKnifeEntry,F::kKnifeGuard.data(),F::kKnifeGuard.size());
 for(const auto&g:isaac::runtime::api600_fields::kLayouts)std::memcpy(g_ModuleBytes.data()+g.offset,g.bytes.data(),g.bytes.size());
 std::memcpy(g_ModuleBytes.data()+E::kEntity0Entry,E::kEntity0Guard.data(),E::kEntity0Guard.size());
 std::memcpy(g_ModuleBytes.data()+E::kEntity1Entry,E::kEntity1Guard.data(),E::kEntity1Guard.size());
 std::memcpy(g_ModuleBytes.data()+E::kEntity2Entry,E::kEntity2Guard.data(),E::kEntity2Guard.size());
 std::memcpy(g_ModuleBytes.data()+E::kSprite0Entry,E::kSprite0Guard.data(),E::kSprite0Guard.size());
 std::memcpy(g_ModuleBytes.data()+E::kSprite1Entry,E::kSprite1Guard.data(),E::kSprite1Guard.size());
 std::memcpy(g_ModuleBytes.data()+E::kSprite2Entry,E::kSprite2Guard.data(),E::kSprite2Guard.size());
 WriteWord(g_ModuleBytes,kEntityKnifeVtableOffset+4*sizeof(std::uintptr_t),0x5E6F0004);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0);LuaRuntime::ObserveGameThread();
 std::string script=R"lua(
 local m=RegisterMod('knife subtype regression',1)
 local knife=Isaac.GetPlayer(0).Parent
 init=0;update=0;render=0;plain=0;wrong=0;fixed=0
 local function reg(id,label)
   m:AddCallback(id,function(_,e,offset)
     assert(e.SubType==4 and e.Variant~=e.SubType)
     assert(GetPtrHash(e)==GetPtrHash(knife))
     if label=='init' then init=init+1;e:GetData().initialized=true
     elseif label=='update' then assert(e:GetData().initialized);update=update+1
     else assert(offset.X==3 and offset.Y==-2);render=render+1 end
   end,4)
   m:AddCallback(id,function()wrong=wrong+1 end,knife.Variant)
   m:AddCallback(id,function()plain=plain+1 end)
 end
 )lua";
 if(mode=="lifecycle")script+=R"lua(
 reg(ModCallbacks.MC_POST_KNIFE_INIT,'init')
 reg(ModCallbacks.MC_POST_KNIFE_UPDATE,'update')
 reg(ModCallbacks.MC_POST_KNIFE_RENDER,'render')
 m:AddCallback(ModCallbacks.MC_POST_KNIFE_RENDER,function()knife:Update() end,4)
 )lua";
 else {
 script+="local boc="+std::string(mode=="boc"||mode=="boc-disabled"?"true":"false")+";local enabled="+(mode=="boc-disabled"?"false":"true")+"\n";
 script+=R"lua(
 local whitelist={[1]=true,[2]=true,[3]=true,[9]=true,[10]=true,[11]=true}
 m:AddCallback(ModCallbacks.MC_POST_KNIFE_UPDATE,function(_,e)
   update=update+1
   if e.FrameCount>0 then return end
   if boc then
     if e.Variant~=4 then return end
   elseif not whitelist[e.Variant] then return end
   if not enabled then return end
   local factor=boc and 0 or 5
   local scale=1+e.TargetPosition.X*factor/450
   e.TargetPosition=Vector(4,0)
   e.Scale=e.Scale*scale;e.SpriteScale=e.SpriteScale*scale
   for _,p in ipairs(Isaac.FindByType(8,e.Variant,0)) do
     if GetPtrHash(p.SpawnerEntity)==GetPtrHash(e.SpawnerEntity) then
       e.Position=p.Position+Vector.FromAngle(e.Rotation)*8
       e.Velocity=Vector.Zero;fixed=fixed+1;break
     end
   end
 end,4)
 )lua";
 }
 auto expected=g_Entities;
 const auto result=LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@range-knife-regression.lua");
 if(result!=LuaRuntime::LuaInitResult::Success){char e[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::fprintf(stderr,"INIT_ERROR %s\n",e);return 2;}
 LuaRuntime::ExerciseRangeKnife(entity,false);Check();
 if(mode=="lifecycle"){
  LuaRuntime::ExerciseRangeKnife(entity,false);Check();
  LuaRuntime::ExerciseRangeKnife(entity,true);Check();
  if(Number("init")!=1||Number("update")!=3||Number("render")!=1||Number("plain")!=5||Number("wrong")!=0){
   std::fprintf(stderr,"subtype counts init=%g update=%g render=%g plain=%g wrong=%g expected 1/3/1/5/0\n",Number("init"),Number("update"),Number("render"),Number("plain"),Number("wrong"));return 3;}
  assert(g_HostEngineCallTrampolineCalls==1);assert(expected==g_Entities);
 }else{
  if(Number("update")!=1){std::fprintf(stderr,"subtype-4 callback received %g updates, expected 1\n",Number("update"));return 4;}
  const bool applies=variant!=4||mode=="boc";
  if(applies){
   assert(Number("fixed")==1);
   WriteAt<LuaRuntime::VectorHandle>(expected[kBullet],0x308,{4,0});
   // BOC defaults to factor 0: scale stays numerically identical, while
   // target, position, and velocity still receive the correction.
   if(mode!="boc"){
    WriteAt<float>(expected[kBullet],0x420,3);
    WriteAt<LuaRuntime::VectorHandle>(expected[kBullet],0x12c,{2.25F,3});
   }
   const auto pos=ReadAt<LuaRuntime::VectorHandle>(knife,kEntityPositionOffset);
   assert(std::fabs(pos.x-100)<0.0001F&&std::fabs(pos.y-208)<0.0001F);
   WriteAt<LuaRuntime::VectorHandle>(expected[kBullet],kEntityPositionOffset,pos);
   WriteAt<LuaRuntime::VectorHandle>(expected[kBullet],kEntityVelocityOffset,{0,0});
  }else assert(Number("fixed")==0);
  assert(expected==g_Entities);
  WriteAt<std::uint32_t>(g_GameBytes,kGameFrameCountOffset,kFrameNow+1);
  LuaRuntime::ExerciseRangeKnife(entity,false);Check();
  assert(Number("update")==2&&Number("fixed")==((applies)?1:0));assert(expected==g_Entities);
 }
 std::printf("PASS %s variant=%u subtype=4 update=%g fixed=%g\n",mode.c_str(),variant,Number("update"),Number("fixed"));return 0;
}
'''


class RangeFixKnifeCallbacks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='range-knife-callbacks-')
        source = fixture.SOURCE / 'lua_runtime.cpp'
        copied = Path(cls.temp.name) / 'runtime.cpp'
        copied.write_text(source.read_text() + r'''
namespace LuaRuntime {
void ExerciseRangeKnife(std::uintptr_t entity,bool render){
 EntityEventScan scan{};scan.registered=BuildRegisteredCallbackMask();scan.renderPhase=render;
 scan.renderOffsetX=3;scan.renderOffsetY=-2;OnEntityEvent(&scan,entity);
}
}
''')
        sources = tuple(copied if p == source else p for p in test_support.layered_lua_runtime_sources(fixture.SOURCE))
        flags = tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
        prefix = fixture.HARNESS[:fixture.HARNESS.index('int main(')]
        prefix = re.sub(r'namespace GameFileReader \{[\s\S]*?#endif\n\}', '', prefix, count=1)
        with patch.object(test_support, 'HARNESS_COMPILE_FLAGS', flags), patch.object(test_support, 'layered_lua_runtime_sources', return_value=sources):
            cls.binary = test_support.build_lua_harness(source_root=fixture.SOURCE, workdir=Path(cls.temp.name), harness_source=prefix + MAIN)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def scenario(self, mode, variant):
        r = subprocess.run([str(self.binary), mode, str(variant)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_init_update_render_and_manual_update_filter_by_subtype(self):
        for variant in (1, 2, 3, 9, 10, 11):
            with self.subTest(variant=variant): self.scenario('lifecycle', variant)

    def test_frame_zero_range_fields_and_same_spawner_parent(self):
        for variant in (1, 2, 3, 9, 10, 11):
            with self.subTest(variant=variant): self.scenario('fields', variant)

    def test_whitelist_branch_alone_does_not_change_variant_four(self):
        # The separate BOC callback is intentionally absent in fields mode.
        self.scenario('fields', 4)

    def test_boc_default_factor_zero_still_fixes_target_position_and_velocity(self):
        self.scenario('boc', 4)

    def test_disabled_boc_preserves_all_entity_bytes(self):
        self.scenario('boc-disabled', 4)
