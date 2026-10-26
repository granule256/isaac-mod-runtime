"""Agony跟班轨道四方法：真实Lua、真实C++ HFA值与保护；宿主仅映射原生地址。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_lua_batch330_familiar_view as fixture
from . import test_support

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'

HOST_TARGETS=r'''
#include <cstdint>
extern "C" void OrbitHostTarget(std::uintptr_t);
extern "C" void OrbitHostVector(std::uintptr_t,const void*,float,float);
extern "C" void OrbitHostLayer(std::uintptr_t,std::uint32_t,bool);
extern "C" void OrbitHostAdd(std::uintptr_t,std::uint32_t);
extern "C" void OrbitHostRemove(std::uintptr_t);
template<class Fn>struct OrbitNativeMock;
template<class Result,class Self,class Vec>struct OrbitNativeMock<Result(*)(Self,const Vec*)>{
 static Result Call(Self self,const Vec* position){
  OrbitHostVector(self,position,position->x,position->y);
  return Result{position->x+10.125F,position->y-5.25F};
 }
};
template<class Result,class Self,class Layer,class Bool>struct OrbitNativeMock<Result(*)(Self,Layer,Bool)>{
 static Result Call(Self self,Layer layer,Bool add){OrbitHostLayer(self,static_cast<std::uint32_t>(layer),add);return -17;}
};
template<class Self,class Layer>struct OrbitNativeMock<void(*)(Self,Layer)>{
 static void Call(Self self,Layer layer){OrbitHostAdd(self,static_cast<std::uint32_t>(layer));}
};
template<class Self>struct OrbitNativeMock<void(*)(Self)>{
 static void Call(Self self){OrbitHostRemove(self);}
};
template<class Fn>Fn OrbitHostFunction(std::uintptr_t target){OrbitHostTarget(target);return &OrbitNativeMock<Fn>::Call;}
'''

MAIN=r'''
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/rplus_extended_fields_guards.hpp"
static unsigned calls=0;static std::uintptr_t target=0,receiver=0,reference=0;
static unsigned layerValue=0;static bool addValue=false;static float inputX=0,inputY=0;
extern "C" void OrbitHostTarget(std::uintptr_t value){target=value;}
extern "C" void OrbitHostVector(std::uintptr_t self,const void* position,float x,float y){
 ++calls;receiver=self;reference=reinterpret_cast<std::uintptr_t>(position);inputX=x;inputY=y;
}
extern "C" void OrbitHostLayer(std::uintptr_t self,unsigned layer,bool add){++calls;receiver=self;layerValue=layer;addValue=add;}
extern "C" void OrbitHostAdd(std::uintptr_t self,unsigned layer){++calls;receiver=self;layerValue=layer;}
extern "C" void OrbitHostRemove(std::uintptr_t self){++calls;receiver=self;}
int main(int argc,char** argv){
 if(argc!=2)return 99;std::string scenario=argv[1];
 PublishFakeGame();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 // Parent现走完整Entity布局守卫；旧夹具只铺轨道方法指纹会在取fam前失败。
 namespace E=isaac::runtime::extended_fields;
 std::memcpy(g_ModuleBytes.data()+E::kEntity0Entry,E::kEntity0Guard.data(),E::kEntity0Guard.size());
 std::memcpy(g_ModuleBytes.data()+E::kEntity1Entry,E::kEntity1Guard.data(),E::kEntity1Guard.size());
 std::memcpy(g_ModuleBytes.data()+E::kEntity2Entry,E::kEntity2Guard.data(),E::kEntity2Guard.size());
 const unsigned offsets[4]={0xafd84,0xacea0,0xae844,0xad648};
 const unsigned char guards[4][16]={ORBIT_GUARDS};
 for(unsigned i=0;i<4;++i)std::memcpy(g_ModuleBytes.data()+offsets[i],guards[i],16);
 std::string body;unsigned method=0,wantLayer=0,wantCalls=1;bool wantAdd=false;
 if(scenario=="vector")body="local p=Vector(1.25,-2.5);local out=fam:GetOrbitPosition(p);assert(type(out)=='userdata' and out.X==11.375 and out.Y==-7.75);assert(p.X==1.25 and p.Y==-2.5)";
 else if(scenario=="add"||scenario=="add_string"||scenario=="add_low32"){
  method=2;wantLayer=scenario=="add"?2:0xfffffffeU;
  body="assert(select('#',fam:AddToOrbit("+std::string(scenario=="add"?"2":(scenario=="add_string"?"'-2'":"4294967294"))+"))==0)";
 }else if(scenario=="remove"){method=3;body="assert(select('#',fam:RemoveFromOrbit())==0)";}
 else if(scenario=="recalc_true"||scenario=="recalc_false"||scenario=="recalc_nil"||scenario=="recalc_missing"||scenario=="recalc_zero"||scenario=="recalc_string"){
  method=1;wantLayer=0xfffffffeU;
  wantAdd=scenario=="recalc_true"||scenario=="recalc_zero"||scenario=="recalc_string";
  const std::string flag=scenario=="recalc_missing"?"":(","+std::string(scenario=="recalc_nil"?"nil":(scenario=="recalc_zero"?"0":(scenario=="recalc_string"?"'x'":(wantAdd?"true":"false")))));
  body="assert(fam:RecalculateOrbitOffset('4294967294'"+flag+")==-17)";
 }else if(scenario=="invalid_args"){
  wantCalls=0;body="assert(not pcall(fam.GetOrbitPosition,fam,{}));assert(not pcall(fam.GetOrbitPosition,fam));assert(not pcall(fam.AddToOrbit,fam,{}));assert(not pcall(fam.AddToOrbit,fam));assert(not pcall(fam.RecalculateOrbitOffset,fam,1.5,true))";
 }else if(scenario=="entry"||scenario=="token"||scenario=="wrong_type"||scenario=="wrong_vtable"||scenario=="unknown_module"){
  wantCalls=0;body="assert(not pcall(fam.GetOrbitPosition,fam,Vector(1,2)));assert(not pcall(fam.RecalculateOrbitOffset,fam,2,true));assert(not pcall(fam.AddToOrbit,fam,2));assert(not pcall(fam.RemoveFromOrbit,fam))";
 }else if(scenario=="fields"){
  wantCalls=0;body="local v=Vector(9.5,-13.75);fam.OrbitDistance=v;v.X=777;assert(fam.OrbitDistance.X==9.5 and fam.OrbitDistance.Y==-13.75);local copy=fam.OrbitDistance;copy.Y=888;assert(fam.OrbitDistance.Y==-13.75);fam.OrbitSpeed='0.03125';assert(fam.OrbitSpeed==0.03125);fam.OrbitLayer='4294967294';assert(fam.OrbitLayer==-2)";
 }else if(scenario=="bad_fields"){
  wantCalls=0;body="for _,v in ipairs({{},false,'bad'}) do assert(not pcall(function() fam.OrbitDistance=v end));assert(not pcall(function() fam.OrbitSpeed=v end));assert(not pcall(function() fam.OrbitLayer=v end)) end;assert(not pcall(function() fam.OrbitDistance=nil end));assert(not pcall(function() fam.OrbitLayer=1.5 end))";
 }else if(scenario=="field_token"||scenario=="field_npc"||scenario=="field_reuse"){
  wantCalls=0;body="for _,name in ipairs({'OrbitDistance','OrbitSpeed','OrbitLayer'}) do assert(not pcall(function() return fam[name] end));assert(not pcall(function() fam[name]=name=='OrbitDistance' and Vector(99,99) or 99 end)) end";
  if(scenario=="field_reuse")body+=";local fresh=Isaac.GetPlayer(0).Parent:ToFamiliar();fresh.OrbitDistance=Vector(20,30);fresh.OrbitSpeed=0.125;fresh.OrbitLayer=4;assert(not pcall(function() fam.OrbitLayer=99 end));assert(fresh.OrbitLayer==4)";
 }else if(scenario=="soul_juliet"||scenario=="soul_romeo"){
  method=1;wantCalls=2;wantAdd=true;wantLayer=scenario=="soul_juliet"?68:69;
  body="Isaac.RunCallbackWithParam(ModCallbacks.MC_FAMILIAR_UPDATE,"+std::to_string(scenario=="soul_juliet"?9001:9002)+",fam)";
 }else return 98;
 std::string script="local fam=Isaac.GetPlayer(0).Parent:ToFamiliar();for _,method in ipairs({'GetOrbitPosition','RecalculateOrbitOffset','AddToOrbit','RemoveFromOrbit'}) do assert(type(fam[method])=='function',method..' missing') end;local m=RegisterMod('orbit',1);m:AddCallback(1,function() "+body+" end)";
 if(scenario=="soul_juliet"||scenario=="soul_romeo"){
  WriteAt<float>(g_PlayerBytes,kEntityPositionOffset,7);WriteAt<float>(g_PlayerBytes,kEntityPositionOffset+4,9);
  WriteAt<float>(g_PlayerBytes,kEntityVelocityOffset,1);WriteAt<float>(g_PlayerBytes,kEntityVelocityOffset+4,2);
  WriteAt<float>(g_FamiliarBytes,kEntityPositionOffset,2);WriteAt<float>(g_FamiliarBytes,kEntityPositionOffset+4,3);
  script="Agony=RegisterMod('Soulmates-original',1);FamiliarVariant.AGONY_F_SOULMATE_JULIET=9001;FamiliarVariant.AGONY_F_SOULMATE_ROMEO=9002;";
  script+=R"AGONY(SOULMATES_ORIGINAL)AGONY";
  script+="\nAgony:AddCallback(1,function() local fam=Isaac.GetPlayer(0).Parent:ToFamiliar();"+body+" end)";
 }
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@orbit.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView errors[8]{};const auto count=LuaRuntime::CopyLuaErrorHistory(errors,8);for(std::size_t i=0;i<count;++i)std::fprintf(stderr,"%s\n",errors[i].text);std::puts("familiar orbit fixture initialization failed");return 1;}
 if(scenario=="entry")for(unsigned i=0;i<4;++i)g_ModuleBytes[offsets[i]+15]^=1;
 if(scenario=="token")isaac::runtime::RetireEntityLifetime(AddressOf(g_FamiliarBytes));
 if(scenario=="wrong_type")WriteAt<unsigned>(g_FamiliarBytes,kEntityTypeOffset,kEntityTypeTear);
 if(scenario=="wrong_vtable")WriteAt<std::uintptr_t>(g_FamiliarBytes,0,g_EngineBase+kEntityPlayerVtableOffset);
 if(scenario=="unknown_module")LuaRuntime::SetEngineModuleBase(0);
 if(scenario=="field_token"||scenario=="field_reuse")isaac::runtime::RetireEntityLifetime(AddressOf(g_FamiliarBytes));
 if(scenario=="field_npc"){
  WriteAt<unsigned>(g_FamiliarBytes,kEntityTypeOffset,20);WriteAt<std::uintptr_t>(g_FamiliarBytes,0,g_EngineBase+kEntityNpcVtableOffset);
 }
 LuaRuntime::DispatchPostUpdate();
 if(LuaRuntime::TakeCallbackError()){std::puts("orbit callback error");return 2;}
 if(calls!=wantCalls)return 3;
 if(wantCalls){
  if(target!=g_EngineBase+offsets[method]||receiver!=AddressOf(g_FamiliarBytes))return 4;
  if(method==0&&(reference==0||inputX!=1.25F||inputY!=-2.5F))return 5;
  if((method==1||method==2)&&layerValue!=wantLayer)return 6;
  if(method==1&&addValue!=wantAdd)return 7;
 }
 auto readFloat=[&](unsigned offset){float v;std::memcpy(&v,g_FamiliarBytes.data()+offset,4);return v;};
 auto readLayer=[&](){int v;std::memcpy(&v,g_FamiliarBytes.data()+0xd84,4);return v;};
 if(scenario=="fields"&&(readFloat(0xd78)!=9.5F||readFloat(0xd7c)!=-13.75F||readFloat(0xd80)!=0.03125F||readLayer()!=-2))return 8;
 if(scenario=="field_reuse"&&(readFloat(0xd78)!=20||readFloat(0xd7c)!=30||readFloat(0xd80)!=0.125F||readLayer()!=4))return 9;
 if(scenario=="soul_juliet"||scenario=="soul_romeo"){
  if(readFloat(0xd78)!=(scenario=="soul_juliet"?125:150)||readFloat(0xd7c)!=(scenario=="soul_juliet"?150:125)||readFloat(0xd80)!=0.03F||readLayer()!=static_cast<int>(wantLayer))return 10;
  if(inputX!=8||inputY!=11||readFloat(kEntityVelocityOffset)!=16.125F||readFloat(kEntityVelocityOffset+4)!=2.75F)return 11;
 }
 return 0;
}
'''

class FamiliarOrbitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-familiar-orbit-');p=Path(cls.tmp.name)
        source='#include <string>\n'+fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
        nro=next(ROOT.glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        source=source.replace('ORBIT_GUARDS',','.join('{'+','.join(str(x) for x in nro[o:o+16])+'}' for o in [0xafd84,0xacea0,0xae844,0xad648]))
        source=source.replace('SOULMATES_ORIGINAL',(ROOT/'dist/familiar-orbit-static-20261010/Soulmates.lua.original').read_text())
        path=ROOT/'runtime/src/interfaces/lua/isaac_api.cpp'
        code=path.read_text()
        # 只替换四处函数地址转换，生产参数解析、Familiar/token/16B守卫均逐字编译。
        for name in ['EntityFamiliarGetOrbitPositionFn','EntityFamiliarRecalculateOrbitOffsetFn','EntityFamiliarAddToOrbitFn','EntityFamiliarRemoveFromOrbitFn']:
            code=code.replace('engine_call::AsFunction<'+name+'>','OrbitHostFunction<'+name+'>')
        instrumented=p/'instrumented_isaac_api.cpp';instrumented.write_text(HOST_TARGETS+code)
        sources=[instrumented if item==path else item for item in test_support.layered_lua_runtime_sources(SOURCE)]
        with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
            cls.binary=test_support.build_lua_harness(source_root=SOURCE,workdir=p,harness_source=source)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def run_scenarios(self,scenarios):
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                r=subprocess.run([str(self.binary),scenario],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_vector_reference_and_two_float_result(self):self.run_scenarios(('vector',))
    def test_layer_low32_bool_signed_return_and_void_count(self):
        self.run_scenarios(('add','add_string','add_low32','remove','recalc_true','recalc_false','recalc_nil','recalc_missing','recalc_zero','recalc_string','invalid_args'))
    def test_receiver_token_and_complete_entry_guards(self):
        self.run_scenarios(('entry','token','wrong_type','wrong_vtable','unknown_module'))
    def test_three_fields_copy_values_and_reject_bad_types(self):self.run_scenarios(('fields','bad_fields'))
    def test_fields_reject_npc_retired_token_and_same_address_reuse(self):self.run_scenarios(('field_token','field_npc','field_reuse'))
    def test_original_soulmates_updates_consume_all_fields_and_methods(self):self.run_scenarios(('soul_juliet','soul_romeo'))

if __name__=='__main__':unittest.main()
