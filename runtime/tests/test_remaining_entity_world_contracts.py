"""剩余实体/寻路公开合约：独立原文期望、真实注册解析、原生消费及失效保护。

GetOrbitDistance / CalculateEndPoint已有真实native桩通过证据，仅索引，不重复造测试。
其余12项使用生产公开入口；只替换SetActiveRotation最终AsFunction的宿主目标。
这里不证明真机引擎内部效果。失败必须保留并交主线程，不能跟随生产改期望。
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_lua_entity_query as fixture
from . import test_support

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'runtime/source'
EVIDENCE = ROOT/'dist/api-remaining-recovery-20261025'
EXISTING_EVIDENCE = {
    'EntityFamiliar:GetOrbitDistance': {
        'test': 'runtime/tests/test_api200_main.py',
        'log': 'dist/api-half-recovery-20261025/test_api200_main-run.log',
        'scope': '公开入口→NS静态get_orbit_distance(int)0xad254，参数及Vec HFA2float返回值',
    },
    'EntityLaser:CalculateEndPoint': {
        'test': 'runtime/tests/test_api700_world.py',
        'log': 'dist/api-half-recovery-20261025/test_api700_world-run.log',
        'scope': '公开静态类→NS0xf7bd8，三个Vector/实体nil,false及有效值/float/Vec返回和错误参数',
    },
}
# 固定期望来自PC/NS原文，不能读取生产表产生offset或同名owner判断。
SOURCE_LEDGER = {
    'EntityFamiliar:FollowParent': ('NS follow_parent0xaec14', 'PC0x60d000；runtime_constants.hpp批次330路线原文'),
    'EntityFamiliar:FollowPosition': ('NS follow_position0xafcc0', 'PC0x5f4eb0；输入Vector实参消费在NS0xafd24'),
    'EntityFamiliar:State': ('NS+d98：Familiar::AddCoins0xd6328/Update0xb8f70,0xb9468', 'PC Familiar registrar0x822100/State+cd4/wrapper0x859cc0'),
    'EntityKnife:IsFlying': ('NS+454：Shoot0xf4d28置1、Init0xeac04清零、Update0xecc7c消费', 'PC Knife registrar0x825efb闭包5ef380，5ef380读取+3b4，非Entity同名方法'),
    'EntityLaser:SetActiveRotation': ('NS0xf7540(unsigned,float,float,bool)', 'tools/pc_contract_docs/EntityLaser.md；固定NRO唯一同名签名'),
    'EntityLaser:SetMaxDistance': ('NS+4f8：update_laser0xf9cb8/init_laser0xf8718消费，0x4b8724写入', 'PC0x4275b0直接写Laser+420'),
    'EntityLaser:ShootAngle': ('NS0xf743c静态七参；s0角度、x0variant,x1pos,x2timeout,x3offset,x4source,w5bool', 'PC0x8c7550七参，固定main.lua默认桥及批次325原文'),
    'EntityNPC:IsBoss': ('NS对象vptr第19槽，NPC覆盖0x124b20，基类0x67580', 'PC0x86051b跳板 [vptr+48]；test_lua_batch319_entity_virtual.py原件说明'),
    'EntityNPC:Scale': ('NS SetScale0x10fcd8直接写+cc4，update_sprite_scale0x11b2b4读取', 'PC EntityNPC.md float Scale，固定NPC专属'),
    'Entity:ToKnife': ('NS Knife原生vptr与type8精确匹配', 'PC返回Knife视图；生产注册类__class精确对比，非只测函数存在'),
    'Entity:ToLaser': ('NS Laser原生vptr与type7精确匹配', 'PC返回Laser视图；生产注册类__class精确对比'),
    'PathFinder:HasPathToPos': ('NS0x42f6cc(Vector2 const&,bool)，NPC内嵌PathFinder+408', 'PC PathFinder.md，NPC构造和ai_poky/ai_stonehead三个+408消费者'),
}
MOCKS = r'''
#include <cstdint>
extern "C" void WorldRotation(std::uintptr_t,std::uintptr_t,std::uint32_t,float,float,bool);
static std::uintptr_t rotationTarget;
static void WorldRotationHost(std::uintptr_t s,std::uint32_t d,float a,float v,bool b){WorldRotation(rotationTarget,s,d,a,v,b);}
template<class F>F WorldRotationFunction(std::uintptr_t target){rotationTarget=target;return &WorldRotationHost;}
'''
MAIN = r'''
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
#include <cstdlib>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
extern unsigned g_HostEngineCallTrampolineCalls;
extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;
extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];
extern std::uint64_t g_HostEngineCallTrampolineIntegerResult;
extern float g_HostEngineCallTrampolineLastFloat32[8];
}
using namespace isaac::runtime;using Vec=LuaRuntime::VectorHandle;
static unsigned rotationCalls{};static bool wantedBoolean{};
extern "C" void WorldRotation(std::uintptr_t target,std::uintptr_t self,std::uint32_t delay,float angle,float speed,bool b){
 ++rotationCalls;assert(target==g_EngineBase+0xf7540&&self==AddressOf(g_Entities[kSizeOnly]));assert(delay==0xfffffffeU&&angle==-35.5F&&speed==2.625F&&b==wantedBoolean);
}
static void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){std::fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::exit(10);}}
static void NoNative(lua_State*L,const char*s){const auto calls=g_HostEngineCallTrampolineCalls;const auto rotations=rotationCalls;auto before=g_Entities;Run(L,s);if(g_HostEngineCallTrampolineCalls!=calls||rotationCalls!=rotations||before!=g_Entities){std::fprintf(stderr,"NoNative failed: %s shared=%u/%u rotations=%u/%u bytes=%d\n",s,g_HostEngineCallTrampolineCalls,calls,rotationCalls,rotations,before==g_Entities);std::abort();}}
template<class T>static void Change(lua_State*L,EntitySlot slot,unsigned offset,T value,const char*s){auto expected=g_Entities;WriteAt<T>(expected[slot],offset,value);Run(L,s);assert(expected==g_Entities);}
static void Shared(lua_State*L,const char*s,std::uintptr_t target,std::uintptr_t self,bool low32=false){auto before=g_HostEngineCallTrampolineCalls;Run(L,s);assert(g_HostEngineCallTrampolineCalls==before+1);assert(g_HostEngineCallTrampolineLastTarget==target);assert(low32?static_cast<std::uint32_t>(g_HostEngineCallTrampolineLastIntegers[0])==static_cast<std::uint32_t>(self):g_HostEngineCallTrampolineLastIntegers[0]==self);}
int main(int argc,char**argv){
 if(argc!=2)return 90;const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();
 FillEntity(kSizeOnly,7,1,0,0,0,1,4,1,g_EngineBase+kEntityLaserVtableOffset,0);
 FillEntity(kNoQuery,8,1,0,0,0,1,5,1,g_EngineBase+kEntityKnifeVtableOffset,0);
 WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);
 FillEntity(kFamiliar,3,1,0,0,0,1,6,1,g_EngineBase+kEntityFamiliarVtableOffset,0);
 PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 const unsigned offsets[]={0xaec14,0xafcc0,0xf7540,0xf743c,0x42f6cc,0x5c744,0xeaa9c,0xeb964};const unsigned char guards[][16]={FROZEN_GUARDS};for(unsigned i=0;i<8;++i)std::memcpy(g_ModuleBytes.data()+offsets[i],guards[i],16);
 FAMILIAR_LAYOUT_GUARDS
 WriteWord(g_ModuleBytes,kEntityNpcVtableOffset+19*8,g_EngineBase+0x124b20);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);assert(RegisterIsaacApi(L));
 RegisterVectorReferenceMetatable(L);luaL_newmetatable(L,LuaRuntime::kVectorMetatable);lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,VectorNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachVectorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");
 for(const auto& pair:{std::pair<EntitySlot,const char*>{kFamiliar,"fam"},{kEnemyA,"npc"},{kNoQuery,"knife"},{kSizeOnly,"laser"}}){PushEntityCallbackArgument(L,AddressOf(g_Entities[pair.first]));lua_setglobal(L,pair.second);}
 Run(L,"fam=fam:ToFamiliar();assert(fam and getmetatable(fam).__type=='EntityFamiliar');v=Vector(3.25,-7.5);off=Vector(-11.25,13.5)");
 if(scene=="follow_parent"||scene=="follow_position"){
  const bool parent=scene=="follow_parent";const auto entry=parent?0xaec14:0xafcc0;
  const char*call=parent?"assert(select('#',fam:FollowParent())==0)":"assert(select('#',fam:FollowPosition(v))==0)";
  // 不在成功缓存之后自改不可变代码；首次解析前验证真实guard拒绝。
  g_ModuleBytes[entry]^=1;NoNative(L,parent?"pcall(fam.FollowParent,fam)":"pcall(fam.FollowPosition,fam,v)");g_ModuleBytes[entry]^=1;
  Shared(L,call,g_EngineBase+entry,AddressOf(g_Entities[kFamiliar]));
  if(!parent){Vec value{};std::memcpy(&value,reinterpret_cast<const void*>(g_HostEngineCallTrampolineLastIntegers[1]),8);assert(value.x==3.25F&&value.y==-7.5F);}
  NoNative(L,parent?"assert(not pcall(fam.FollowParent,{}));assert(not pcall(fam.FollowParent,fam,1))":"assert(not pcall(fam.FollowPosition,fam,{}));assert(not pcall(fam.FollowPosition,fam))");
  RetireEntityLifetime(AddressOf(g_Entities[kFamiliar]));NoNative(L,parent?"pcall(fam.FollowParent,fam)":"pcall(fam.FollowPosition,fam,v)");
 }else if(scene=="familiar_state"){
  WriteAt<std::int32_t>(g_Entities[kFamiliar],0xd98,-17003);NoNative(L,"assert(fam.State==-17003,'Familiar.State native read')");
  Change<std::int32_t>(L,kFamiliar,0xd98,-29,"fam.State=-29;assert(fam.State==-29)");
  Change<std::int32_t>(L,kFamiliar,0xd98,1,"fam.State=0x100000001;assert(fam.State==1)");NoNative(L,"assert(not pcall(function()fam.State=1.5 end));assert(not pcall(function()fam.State={}end))");
  RetireEntityLifetime(AddressOf(g_Entities[kFamiliar]));NoNative(L,"assert(fam.State==nil);fam.State=99");
 }else if(scene=="knife_flying"){
  // PC Knife自己的getter读飞行阶段字节，不可继承Entity基类的悬浮/飞行判定。
  WriteAt<std::uint8_t>(g_Entities[kNoQuery],0x454,1);g_HostEngineCallTrampolineIntegerResult=0;NoNative(L,"assert(knife:IsFlying()==true,'Knife.IsFlying must read knife flight state')");
  WriteAt<std::uint8_t>(g_Entities[kNoQuery],0x454,0);g_HostEngineCallTrampolineIntegerResult=1;NoNative(L,"assert(knife:IsFlying()==false)");
  NoNative(L,"assert(not pcall(knife.IsFlying,{}))");RetireEntityLifetime(AddressOf(g_Entities[kNoQuery]));NoNative(L,"pcall(knife.IsFlying,knife)");
 }else if(scene=="rotation"){
  for(unsigned i=0;i<2;++i){wantedBoolean=i==1;const auto before=rotationCalls;Run(L,i?"assert(select('#',laser:SetActiveRotation('4294967294','-35.5','2.625',0))==0)":"assert(select('#',laser:SetActiveRotation(-2,-35.5,2.625,nil))==0)");assert(rotationCalls==before+1);}
  NoNative(L,"assert(not pcall(laser.SetActiveRotation,laser,1.5,1,2,true));assert(not pcall(laser.SetActiveRotation,laser,2,{},2,true))");g_ModuleBytes[0xf7540+15]^=1;NoNative(L,"pcall(laser.SetActiveRotation,laser,-2,-35.5,2.625,false)");g_ModuleBytes[0xf7540+15]^=1;
  RetireEntityLifetime(AddressOf(g_Entities[kSizeOnly]));NoNative(L,"pcall(laser.SetActiveRotation,laser,-2,-35.5,2.625,false)");
 }else if(scene=="max_distance"){
  WriteAt<float>(g_Entities[kSizeOnly],0x4f8,91.25F);Change<float>(L,kSizeOnly,0x4f8,-37.25F,"assert(select('#',laser:SetMaxDistance('-37.25'))==0)");
  NoNative(L,"assert(not pcall(laser.SetMaxDistance,laser,{}));assert(not pcall(laser.SetMaxDistance,laser))");RetireEntityLifetime(AddressOf(g_Entities[kSizeOnly]));NoNative(L,"pcall(laser.SetMaxDistance,laser,123)");
 }else if(scene=="shoot_angle"){
  g_ModuleBytes[0xf743c]^=1;NoNative(L,"pcall(EntityLaser.ShootAngle,2,v,0,1,off,nil)");g_ModuleBytes[0xf743c]^=1;
  g_HostEngineCallTrampolineIntegerResult=AddressOf(g_Entities[kSizeOnly]);
  for(unsigned i=0;i<2;++i){Shared(L,i?"shot=EntityLaser.ShootAngle(0x100000002,v,-35.5,-7,off,npc,0)":"shot=EntityLaser.ShootAngle(0x100000002,v,-35.5,-7,off,npc)",g_EngineBase+0xf743c,2,true);
   assert(static_cast<std::uint32_t>(g_HostEngineCallTrampolineLastIntegers[2])==static_cast<std::uint32_t>(-7)&&g_HostEngineCallTrampolineLastIntegers[4]==AddressOf(g_Entities[kEnemyA])&&g_HostEngineCallTrampolineLastIntegers[5]==i&&g_HostEngineCallTrampolineLastFloat32[0]==-35.5F);
   Vec pos{},offset{};std::memcpy(&pos,reinterpret_cast<const void*>(g_HostEngineCallTrampolineLastIntegers[1]),8);std::memcpy(&offset,reinterpret_cast<const void*>(g_HostEngineCallTrampolineLastIntegers[3]),8);assert(pos.x==3.25F&&pos.y==-7.5F&&offset.x==-11.25F&&offset.y==13.5F);
   Run(L,"assert(shot.Type==7 and getmetatable(shot).__class==getmetatable(laser).__class and getmetatable(shot).__type=='EntityLaser')");}
  g_HostEngineCallTrampolineIntegerResult=0;Shared(L,"assert(EntityLaser.ShootAngle(2,v,0,1,off,nil)==nil)",g_EngineBase+0xf743c,2,true);
  NoNative(L,"assert(not pcall(EntityLaser.ShootAngle,2,{},0,1,off,nil));assert(not pcall(EntityLaser.ShootAngle,2,v,0,1,off,{}))");
 }else if(scene=="npc_boss"){
  g_HostEngineCallTrampolineIntegerResult=1;Shared(L,"assert(npc:IsBoss()==true)",g_EngineBase+0x124b20,AddressOf(g_Entities[kEnemyA]));
  WriteWord(g_ModuleBytes,kEntityNpcVtableOffset+19*8,g_EngineBase+0x67580);g_HostEngineCallTrampolineIntegerResult=0;Shared(L,"assert(npc:IsBoss()==false)",g_EngineBase+0x67580,AddressOf(g_Entities[kEnemyA]));
  WriteWord(g_ModuleBytes,kEntityNpcVtableOffset+19*8,0);NoNative(L,"pcall(npc.IsBoss,npc)");NoNative(L,"assert(not pcall(npc.IsBoss,{}))");RetireEntityLifetime(AddressOf(g_Entities[kEnemyA]));NoNative(L,"pcall(npc.IsBoss,npc)");
 }else if(scene=="npc_scale"){
  WriteAt<float>(g_Entities[kEnemyA],0xcc4,13.25F);NoNative(L,"assert(npc.Scale==13.25)");Change<float>(L,kEnemyA,0xcc4,-2.625F,"npc.Scale='-2.625';assert(npc.Scale==-2.625)");NoNative(L,"assert(not pcall(function()npc.Scale={}end))");
  RetireEntityLifetime(AddressOf(g_Entities[kEnemyA]));NoNative(L,"assert(npc.Scale==nil);npc.Scale=33");
 }else if(scene=="to_knife"||scene=="to_laser"){
  const bool knife=scene=="to_knife";const auto slot=knife?kNoQuery:kSizeOnly;
  Run(L,knife?"cast=knife:ToKnife();assert(getmetatable(cast).__type=='EntityKnife' and getmetatable(cast).__class==getmetatable(knife).__class);assert(cast:GetData()==knife:GetData() and knife:ToLaser()==nil)":"cast=laser:ToLaser();assert(getmetatable(cast).__type=='EntityLaser' and getmetatable(cast).__class==getmetatable(laser).__class);assert(cast:GetData()==laser:GetData() and laser:ToKnife()==nil)");
  WriteAt<unsigned>(g_Entities[slot],kEntityTypeOffset,20);NoNative(L,knife?"assert(knife:ToKnife()==nil)":"assert(laser:ToLaser()==nil)");WriteAt<unsigned>(g_Entities[slot],kEntityTypeOffset,knife?8:7);
  RetireEntityLifetime(AddressOf(g_Entities[slot]));NoNative(L,knife?"assert(knife:ToKnife()==nil and cast:ToKnife()==nil)":"assert(laser:ToLaser()==nil and cast:ToLaser()==nil)");
 }else if(scene=="pathfinder"){
  Run(L,"path=npc.Pathfinder;assert(path)");
  g_ModuleBytes[0x42f6cc]^=1;NoNative(L,"pcall(path.HasPathToPos,path,v,true)");g_ModuleBytes[0x42f6cc]^=1;
  for(unsigned i=0;i<2;++i){g_HostEngineCallTrampolineIntegerResult=i;Shared(L,i?"assert(path:HasPathToPos(v,0)==true)":"assert(path:HasPathToPos(v,nil)==false)",g_EngineBase+0x42f6cc,AddressOf(g_Entities[kEnemyA])+0x408);assert(g_HostEngineCallTrampolineLastIntegers[2]==i);Vec pos{};std::memcpy(&pos,reinterpret_cast<const void*>(g_HostEngineCallTrampolineLastIntegers[1]),8);assert(pos.x==3.25F&&pos.y==-7.5F);}
  NoNative(L,"assert(not pcall(path.HasPathToPos,path,{},true))");NoNative(L,"assert(not pcall(path.HasPathToPos,path,v))");NoNative(L,"assert(path.HasPathToPos({},v,true)==false)");
  RetireEntityLifetime(AddressOf(g_Entities[kEnemyA]));NoNative(L,"pcall(path.HasPathToPos,path,v,true)");
 }else return 91;
 lua_close(L);return 0;
}
'''


class RemainingEntityWorldContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='remaining-entityworld-')
        cls.addClassCleanup(cls.tmp.cleanup)
        work = Path(cls.tmp.name)
        sources = list(test_support.layered_lua_runtime_sources(SOURCE))
        cls.paths = tuple(sorted(set(sources) | set((ROOT/'runtime/src').rglob('*.hpp')) | set(SOURCE.rglob('*.hpp'))))
        cls.before = cls._snapshot()
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE/'main-entityworld-input-before.json').write_text(json.dumps(cls.before, indent=2)+'\n')
        cls.addClassCleanup(cls._check_stable)
        original = Path('/Users/kelinls/code/github/isaac mod')
        nro = next(original.glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        main = MAIN.replace('FROZEN_GUARDS', ','.join('{'+','.join(map(str,nro[o:o+16]))+'}' for o in (0xaec14,0xafcc0,0xf7540,0xf743c,0x42f6cc,0x5c744,0xeaa9c,0xeb964)))
        # 按NS各段实际长度冻结：12/12/12/20/8，不能一律16字节。
        familiar_guards = ((0xaaeb8,12),(0xd63fc,12),(0xd8dc0,12),(0xd6448,20),(0xaca78,8))
        main = main.replace('FAMILIAR_LAYOUT_GUARDS', '\n'.join(
            'const unsigned char f'+str(i)+'[]={'+','.join(map(str,nro[o:o+size]))+'};std::memcpy(g_ModuleBytes.data()+'+hex(o)+',f'+str(i)+','+str(size)+');'
            for i,(o,size) in enumerate(familiar_guards)))
        prefix = fixture.HARNESS[:fixture.HARNESS.index('int main(')]
        prefix = re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', prefix, count=1)
        api = ROOT/'runtime/src/interfaces/lua/isaac_api.cpp'
        code = api.read_text()
        old = 'engine_call::AsFunction<EntityLaserSetActiveRotationFn>'
        assert code.count(old)==1
        instrumented = work/'instrumented_isaac_api.cpp'
        instrumented.write_text(MOCKS+code.replace(old,'WorldRotationFunction<EntityLaserSetActiveRotationFn>'))
        replacements = [instrumented if path==api else path for path in sources]
        (EVIDENCE/'main-entityworld-harness.cpp').write_text(prefix+main)
        with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=replacements):
            cls.binary = test_support.build_lua_harness(source_root=SOURCE,workdir=work,harness_source=prefix+main)

    @classmethod
    def _snapshot(cls):
        return {str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in cls.paths}

    @classmethod
    def _check_stable(cls):
        after=cls._snapshot()
        (EVIDENCE/'main-entityworld-input-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:
            raise AssertionError('测试期间生产输入SHA改变；结果不能归属同一版本')

    def test_public_native_fields_casts_and_owner_boundaries(self):
        available=('follow_parent','follow_position','familiar_state','knife_flying','rotation','max_distance','shoot_angle','npc_boss','npc_scale','to_knife','to_laser','pathfinder')
        selected=os.environ.get('ISAAC_ENTITYWORLD_SCENES')
        scenes=tuple(selected.split(',')) if selected else available
        self.assertTrue(all(scene in available for scene in scenes),'unknown targeted scenario')
        for scene in scenes:
            with self.subTest(scene=scene):
                result=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
                print(f'{scene}: exit={result.returncode} {result.stdout}{result.stderr}',flush=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_main_failed_boundaries_and_knife(self):
        for scene in ('follow_parent','follow_position','familiar_state','knife_flying','shoot_angle','pathfinder'):
            with self.subTest(scene=scene):
                r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)
