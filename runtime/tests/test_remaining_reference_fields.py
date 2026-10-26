"""NPC弱引用/地下室返回索引/炸弹伤害/开门的固定PC与NS公开合约。

取证见delegated-reference-proof.json。只重定向已解析的两个最终native地址；
NPC回链树的完整算法由NS原文证明，宿主桩只验证ABI、禁止提前裸写及注销调用。
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from . import test_support

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'
EVIDENCE=ROOT/'dist/api-remaining-recovery-20261025'
MAIN=r'''
#include "interfaces/lua/api500_world.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
#include <cstdlib>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static std::vector<unsigned char> doorBytes(0x400);static unsigned setCalls{},openCalls{},unregistered{},registered{};static std::uintptr_t expectedOld{},expectedTarget{},lastOriginal{};
void* ReferenceRoom(){return g_RoomBytes.data();}
static void NativeSetReference(void*self,void*target){
 assert(self==g_Entities[kEnemyA].data());std::uintptr_t old{};std::memcpy(&old,static_cast<unsigned char*>(self)+0xc20,8);
 assert(old==expectedOld&&reinterpret_cast<std::uintptr_t>(target)==expectedTarget); // 裸写后再补调native也不允许。
 ++setCalls;if(old)++unregistered;if(target)++registered;WriteWord(g_Entities[kEnemyA],0xc20,reinterpret_cast<std::uintptr_t>(target));
}
static void NativeDoorOpen(void*self){assert(self==doorBytes.data());++openCalls;}
extern "C" std::uintptr_t ReferenceNativeRedirect(std::uintptr_t original)noexcept {
 if(original==g_EngineBase+0x11fb70){lastOriginal=original;return reinterpret_cast<std::uintptr_t>(&NativeSetReference);}
 if(original==g_EngineBase+0x385894){lastOriginal=original;return reinterpret_cast<std::uintptr_t>(&NativeDoorOpen);}
 return original;
}
static void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){std::fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::exit(10);}}
static void Unchanged(lua_State*L,const char*s){const auto calls=setCalls+openCalls;auto entities=g_Entities;auto game=g_GameBytes;auto door=doorBytes;Run(L,s);assert(calls==setCalls+openCalls&&entities==g_Entities&&game==g_GameBytes&&door==doorBytes);}
static void SetReference(lua_State*L,std::uintptr_t old,std::uintptr_t target,const char*s){expectedOld=old;expectedTarget=target;const auto calls=setCalls;auto expected=g_Entities;WriteWord(expected[kEnemyA],0xc20,target);auto game=g_GameBytes;auto door=doorBytes;Run(L,s);assert(setCalls==calls+1&&lastOriginal==g_EngineBase+0x11fb70&&expected==g_Entities&&game==g_GameBytes&&door==doorBytes);}
int main(int argc,char**argv){if(argc!=2)return 90;const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();g_GameBytes.resize(0x320000);FillEntities();WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);FillEntity(kBullet,4,0,0,0,0,1,8,1,g_EngineBase+kEntityBombVtableOffset,0);PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 FROZEN_GUARDS
 WriteWord(g_Entities[kEnemyA],0xc20,AddressOf(g_Entities[kPlayer]));
 for(unsigned i=0x400;i<0x420;++i)g_Entities[kBullet][i]=static_cast<unsigned char>(0x51+i%71);
 for(unsigned i=0x21560;i<0x21580;++i)g_GameBytes[i]=static_cast<unsigned char>(0x71+i%41);
 WriteWord(doorBytes,0,g_EngineBase+kGridEntity_DoorVtableOffset);WriteAt<unsigned>(doorBytes,kGridEntityGridIndexOffset,20);WriteAt<unsigned>(doorBytes,kGridEntityDoorSlotOffset,0);WriteAt<unsigned>(g_RoomBytes,kRoomGridWidthOffset,13);WriteAt<unsigned>(g_RoomBytes,kRoomGridHeightOffset,7);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+20*8,AddressOf(doorBytes));WriteWord(g_RoomBytes,kRoomDoorObjectTableOffset,AddressOf(doorBytes));
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(RegisterIsaacApi(L));
 for(const auto&pair:{std::pair<EntitySlot,const char*>{kEnemyA,"npc"},{kPlayer,"player"},{kPickup,"pickup"},{kBullet,"bomb"}}){PushEntityCallbackArgument(L,AddressOf(g_Entities[pair.first]));lua_setglobal(L,pair.second);}
 lua_pushinteger(L,static_cast<lua_Integer>(AddressOf(g_Entities[kPlayer])));lua_setglobal(L,"playerAddress");lua_pushinteger(L,static_cast<lua_Integer>(AddressOf(g_Entities[kPickup])));lua_setglobal(L,"pickupAddress");
 // 通用Level和Grid/Door基础设施按生产注册方式装配，不补待测字段。
 luaL_newmetatable(L,LuaRuntime::kLevelMetatable);static_cast<void>(AttachLevelMethods(L));lua_pushvalue(L,-1);lua_pushcclosure(L,LevelIndex,1);lua_setfield(L,-2,"__index");lua_pushcfunction(L,IgnoredObjectFieldWrite);lua_setfield(L,-2,"__newindex");lua_pop(L,1);auto*level=static_cast<LuaRuntime::LevelHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::LevelHandle)));*level={};luaL_getmetatable(L,LuaRuntime::kLevelMetatable);lua_setmetatable(L,-2);lua_setglobal(L,"level");
 luaL_newmetatable(L,LuaRuntime::kGridEntityMetatable);lua_pushcfunction(L,GridEntityIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,Api500GridNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachGridEntityMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kGridEntityDoorMetatable);lua_pushcfunction(L,GridEntityDoorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,Api500GridNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachGridEntityDoorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);auto*h=static_cast<LuaRuntime::DoorHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::DoorHandle)));*h={doorBytes.data(),0,0};luaL_getmetatable(L,LuaRuntime::kGridEntityDoorMetatable);lua_setmetatable(L,-2);lua_setglobal(L,"door");
 if(scene=="npc_get"){
  Unchanged(L,"held=npc.EntityRef;assert(type(held)=='userdata' and held.Type==1 and GetPtrHash(held)==playerAddress,'NPC.EntityRef must return target entity, not global EntityRef constructor');assert(held:GetData()==player:GetData())");
  WriteWord(g_Entities[kEnemyA],0xc20,0);Unchanged(L,"assert(npc.EntityRef==nil)");
 }else if(scene=="npc_set"){
  SetReference(L,AddressOf(g_Entities[kPlayer]),AddressOf(g_Entities[kPickup]),"npc.EntityRef=pickup;assert(GetPtrHash(npc.EntityRef)==pickupAddress)");
  SetReference(L,AddressOf(g_Entities[kPickup]),0,"npc.EntityRef=nil;assert(npc.EntityRef==nil)");assert(unregistered==2&&registered==1);
  Unchanged(L,"assert(not pcall(function()npc.EntityRef={}end))");RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));WriteWord(g_Entities[kPlayer],0,0);Unchanged(L,"assert(not pcall(function()npc.EntityRef=player end))");
  SetReference(L,0,AddressOf(g_Entities[kPickup]),"npc.EntityRef=pickup;targetAlias=npc.EntityRef");
  // 模拟原生弱引用容器在目标D2时清零注册槽；此算法本体只由NS原文取证，不冒称宿主执行NS树。
  WriteWord(g_Entities[kEnemyA],0xc20,0);RetireEntityLifetime(AddressOf(g_Entities[kPickup]));WriteWord(g_Entities[kPickup],0,0);Unchanged(L,"assert(npc.EntityRef==nil and targetAlias.Type==nil)");
  RetireEntityLifetime(AddressOf(g_Entities[kEnemyA]));Unchanged(L,"assert(npc.EntityRef==nil);pcall(function()npc.EntityRef=nil end)");
 }else if(scene=="npc_guard"){
  g_ModuleBytes[0x11fb70]^=1;Unchanged(L,"pcall(function()npc.EntityRef=pickup end)");
 }else if(scene=="dungeon_index"){
  WriteAt<std::int32_t>(g_GameBytes,0x21570,-17003);Unchanged(L,"assert(level.DungeonReturnRoomIndex==-17003,'DungeonReturnRoomIndex native signed read')");
  for(unsigned i=0;i<2;++i){auto expected=g_GameBytes;WriteAt<std::int32_t>(expected,0x21570,i?1:-29);auto entities=g_Entities;auto door=doorBytes;Run(L,i?"level.DungeonReturnRoomIndex=0x100000001;assert(level.DungeonReturnRoomIndex==1)":"level.DungeonReturnRoomIndex=-29;assert(level.DungeonReturnRoomIndex==-29)");assert(expected==g_GameBytes&&entities==g_Entities&&door==doorBytes);}
  Unchanged(L,"assert(not pcall(function()level.DungeonReturnRoomIndex={}end));assert(not pcall(function()level.DungeonReturnRoomIndex=1.5 end))");WriteWord(g_ModuleBytes,kGameOwnerGlobalSlotOffset,0);Unchanged(L,"local ok,value=pcall(function()return level.DungeonReturnRoomIndex end);assert(not ok or value==nil);pcall(function()level.DungeonReturnRoomIndex=33 end)");
 }else if(scene=="bomb_damage"){
  WriteAt<float>(g_Entities[kBullet],0x408,13.25F);Unchanged(L,"assert(bomb.ExplosionDamage==13.25,'Bomb native explosion damage');assert(npc.ExplosionDamage==nil and player.ExplosionDamage==nil)");auto expected=g_Entities;WriteAt<float>(expected[kBullet],0x408,-2.625F);auto game=g_GameBytes;auto door=doorBytes;Run(L,"bomb.ExplosionDamage='-2.625';assert(bomb.ExplosionDamage==-2.625)");assert(expected==g_Entities&&game==g_GameBytes&&door==doorBytes);Unchanged(L,"assert(not pcall(function()bomb.ExplosionDamage={}end))");RetireEntityLifetime(AddressOf(g_Entities[kBullet]));Unchanged(L,"assert(bomb.ExplosionDamage==nil);bomb.ExplosionDamage=33");
 }else if(scene=="door_open"){
  Run(L,"assert(select('#',door:Open())==0);assert(select('#',door:Open())==0)");assert(openCalls==2&&lastOriginal==g_EngineBase+0x385894);Unchanged(L,"assert(not pcall(door.Open,{}))");WriteWord(doorBytes,0,0);Unchanged(L,"pcall(door.Open,door)");
 }else if(scene=="door_guard"){
  g_ModuleBytes[0x385894]^=1;Unchanged(L,"pcall(door.Open,door)");
 }else return 91;
 lua_close(L);return 0;}
'''


class RemainingReferenceFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact_prefix=os.environ.get('ISAAC_REFERENCE_ARTIFACT_PREFIX','delegated-reference')
        cls.tmp=tempfile.TemporaryDirectory(prefix='remaining-reference-');cls.addClassCleanup(cls.tmp.cleanup);work=Path(cls.tmp.name)
        sources=test_support.layered_lua_runtime_sources(SOURCE);cls.paths=tuple(sorted(set(sources)|set((ROOT/'runtime/src').rglob('*.hpp'))|set(SOURCE.rglob('*.hpp'))));cls.before=cls._snapshot()
        EVIDENCE.mkdir(parents=True,exist_ok=True);(EVIDENCE/(cls.artifact_prefix+'-input-before.json')).write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls._stable)
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        regions=((0x11fb70,0x19c),(0x385894,16),(0x7aeb0,32),(0x3d9b80,16),(0x3e5d1c,16))
        guards='\n'.join('const unsigned char b'+str(i)+'[]={'+','.join(map(str,nro[o:o+n]))+'};std::memcpy(g_ModuleBytes.data()+'+hex(o)+',b'+str(i)+','+str(n)+');' for i,(o,n) in enumerate(regions))
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')];prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1);prefix=prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}','void* ReferenceRoom();\nGameRoomObservation ReadCurrentGameRoom(uintptr_t,void**room){*room=ReferenceRoom();return GameRoomObservation::Success;}')
        # 临时头只改AsFunction最终地址；类型/查址/guard/公开注册全部使用生产代码。
        header=ROOT/'runtime/src/infrastructure/call/engine_call_access.hpp';code=header.read_text();old='return address == 0 ? nullptr : reinterpret_cast<Fn>(address);';assert code.count(old)==1
        shadow=work/'compatibility/infrastructure/call/engine_call_access.hpp';shadow.parent.mkdir(parents=True,exist_ok=True);code=code.replace('namespace isaac::runtime::engine_call {','extern "C" std::uintptr_t ReferenceNativeRedirect(std::uintptr_t) noexcept;\nnamespace isaac::runtime::engine_call {',1).replace(old,'return address == 0 ? nullptr : reinterpret_cast<Fn>(::ReferenceNativeRedirect(address));');shadow.write_text(code)
        (EVIDENCE/(cls.artifact_prefix+'-harness.cpp')).write_text(prefix+MAIN.replace('FROZEN_GUARDS',guards));(EVIDENCE/(cls.artifact_prefix+'-shadow-engine-call.hpp')).write_bytes(shadow.read_bytes())
        cls.binary=test_support.build_lua_harness(source_root=SOURCE,workdir=work,harness_source=prefix+MAIN.replace('FROZEN_GUARDS',guards))
    @classmethod
    def _snapshot(cls):return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
    @classmethod
    def _stable(cls):
        after=cls._snapshot();(EVIDENCE/(cls.artifact_prefix+'-input-after.json')).write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('运行期间生产输入改变，不能归属单一版本')
    def test_reference_and_world_field_native_contracts(self):
        selected=os.environ.get('ISAAC_REFERENCE_SCENES');scenes=selected.split(',') if selected else ('npc_get','npc_set','npc_guard','dungeon_index','bomb_damage','door_open','door_guard')
        self.assertTrue(all(s in ('npc_get','npc_set','npc_guard','dungeon_index','bomb_damage','door_open','door_guard') for s in scenes))
        for scene in scenes:
            with self.subTest(scene=scene):
                result=subprocess.run([str(self.binary),scene],capture_output=True,text=True);print(f'{scene}: exit={result.returncode} {result.stdout}{result.stderr}',flush=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
