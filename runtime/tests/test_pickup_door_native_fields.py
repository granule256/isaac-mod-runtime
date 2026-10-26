"""五字段固定PC/NS合约：真实公开读写、原生位型、邻字节与寿命。

独立依据见delegated-pickup-door-proof.json；不引用生产字段表生成期望。
State为PC实际u32；PreviousVariant为PC实际eVariant自有值，不能按在线int伪造。
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
static std::vector<unsigned char> doorBytes(0x400);
void* PickupDoorRoom(){return g_RoomBytes.data();}
static void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){std::fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::exit(10);}}
static void Unchanged(lua_State*L,const char*s){auto before=g_Entities;auto doorBefore=doorBytes;Run(L,s);assert(before==g_Entities&&doorBefore==doorBytes);}
template<class T>static void Change(lua_State*L,unsigned offset,T value,const char*s){auto expected=g_Entities;WriteAt<T>(expected[kPickup],offset,value);auto doorBefore=doorBytes;Run(L,s);assert(expected==g_Entities&&doorBefore==doorBytes);}
static void DoorChange(lua_State*L,unsigned value,const char*s){auto expected=doorBytes;WriteAt<unsigned>(expected,0x314,value);auto entitiesBefore=g_Entities;Run(L,s);assert(expected==doorBytes&&entitiesBefore==g_Entities);}
static std::uint32_t Opaque(lua_State*L,int index){assert(lua_type(L,index)==LUA_TUSERDATA&&lua_rawlen(L,index)==4);std::uint32_t value{};std::memcpy(&value,lua_touserdata(L,index),4);return value;}
int main(int argc,char**argv){if(argc!=2)return 90;const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 FROZEN_GUARDS
 for(unsigned i=0x550;i<0x5c0;++i)g_Entities[kPickup][i]=static_cast<unsigned char>(0x51+i%71);
 for(unsigned i=0x300;i<0x330;++i)doorBytes[i]=static_cast<unsigned char>(0x71+i%41);
 WriteWord(doorBytes,0,g_EngineBase+kGridEntity_DoorVtableOffset);WriteAt<unsigned>(doorBytes,kGridEntityGridIndexOffset,20);WriteAt<unsigned>(doorBytes,kGridEntityDoorSlotOffset,0);WriteAt<unsigned>(g_RoomBytes,kRoomGridWidthOffset,13);WriteAt<unsigned>(g_RoomBytes,kRoomGridHeightOffset,7);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+20*8,AddressOf(doorBytes));WriteWord(g_RoomBytes,kRoomDoorObjectTableOffset,AddressOf(doorBytes));
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(RegisterIsaacApi(L));
 PushEntityCallbackArgument(L,AddressOf(g_Entities[kPickup]));lua_setglobal(L,"pickup");PushEntityCallbackArgument(L,AddressOf(g_Entities[kPlayer]));lua_setglobal(L,"player");
 // Door未命中字段时按生产协议回落Grid基类，两个通用元表都必须先装配。
 luaL_newmetatable(L,LuaRuntime::kGridEntityMetatable);lua_pushcfunction(L,GridEntityIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,Api500GridNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachGridEntityMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 // 只装配生产Door通用访问器，不补挂任何待测字段或模拟setter。
 luaL_newmetatable(L,LuaRuntime::kGridEntityDoorMetatable);lua_pushcfunction(L,GridEntityDoorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,Api500GridNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachGridEntityDoorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 auto*h=static_cast<LuaRuntime::DoorHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::DoorHandle)));*h={doorBytes.data(),0,0};luaL_getmetatable(L,LuaRuntime::kGridEntityDoorMetatable);lua_setmetatable(L,-2);lua_setglobal(L,"door");
 if(scene=="charge"){
  WriteAt<std::int32_t>(g_Entities[kPickup],0x558,-17003);Unchanged(L,"assert(pickup.Charge==-17003,'Pickup.Charge signed native read')");
  Change<std::int32_t>(L,0x558,-29,"pickup.Charge=-29;assert(pickup.Charge==-29)");Change<std::int32_t>(L,0x558,1,"pickup.Charge=0x100000001;assert(pickup.Charge==1)");
  Unchanged(L,"assert(not pcall(function()pickup.Charge={}end));assert(not pcall(function()pickup.Charge=1.5 end))");
 }else if(scene=="state"){
  // PC8598ab→7f8840高32位固定0；不是7f8820的cdq有符号扩展。
  WriteAt<unsigned>(g_Entities[kPickup],0x5b8,0xf1234567U);Unchanged(L,"assert(pickup.State==0xf1234567,'Pickup.State must expose uint32')");
  Change<unsigned>(L,0x5b8,0xffffffffU,"pickup.State=-1;assert(pickup.State==0xffffffff)");Change<unsigned>(L,0x5b8,1,"pickup.State=0x100000001;assert(pickup.State==1)");
  Unchanged(L,"assert(not pcall(function()pickup.State={}end));assert(not pcall(function()pickup.State=1.5 end))");
 }else if(scene=="timeout"){
  WriteAt<std::int32_t>(g_Entities[kPickup],0x570,-17003);Unchanged(L,"assert(pickup.Timeout==-17003,'Pickup.Timeout signed native read')");
  Change<std::int32_t>(L,0x570,-29,"pickup.Timeout=-29;assert(pickup.Timeout==-29)");Change<std::int32_t>(L,0x570,1,"pickup.Timeout=0x100000001;assert(pickup.Timeout==1)");
  Unchanged(L,"assert(not pcall(function()pickup.Timeout={}end));assert(not pcall(function()pickup.Timeout=1.5 end))");
 }else if(scene=="touched"){
  // +560由碰撞和保存/恢复独立闭合，不能引用旧kEntityPickupTouchedOffset猜测自证。
  WriteAt<std::uint8_t>(g_Entities[kPickup],0x560,0x7d);Unchanged(L,"assert(pickup.Touched==true,'Pickup.Touched native byte read')");
  Change<std::uint8_t>(L,0x560,0,"pickup.Touched=false;assert(pickup.Touched==false)");Change<std::uint8_t>(L,0x560,1,"pickup.Touched=0;assert(pickup.Touched==true)");Change<std::uint8_t>(L,0x560,0,"pickup.Touched=nil;assert(pickup.Touched==false)");
 }else if(scene=="previous_variant"){
  WriteAt<unsigned>(doorBytes,0x314,0xf1234567U);Unchanged(L,"savedVariant=door.PreviousVariant;assert(type(savedVariant)=='userdata','Door.PreviousVariant must return opaque eVariant')");
  lua_getglobal(L,"savedVariant");assert(Opaque(L,-1)==0xf1234567U);const unsigned replacement=0x11223344;auto before=doorBytes;std::memcpy(lua_touserdata(L,-1),&replacement,4);assert(before==doorBytes);lua_pop(L,1);
  DoorChange(L,replacement,"door.PreviousVariant=savedVariant;copiedVariant=door.PreviousVariant;assert(type(copiedVariant)=='userdata' and copiedVariant~=savedVariant)");lua_getglobal(L,"copiedVariant");assert(Opaque(L,-1)==replacement);lua_pop(L,1);
  Unchanged(L,"assert(not pcall(function()door.PreviousVariant=2 end));assert(not pcall(function()door.PreviousVariant={}end))");
  // 真实vptr失效，不把一次移槽等同于D2/销毁。
  WriteWord(doorBytes,0,0);Unchanged(L,"local ok,value=pcall(function()return door.PreviousVariant end);assert(not ok or value==nil);assert(not pcall(function()door.PreviousVariant=savedVariant end))");lua_getglobal(L,"savedVariant");assert(Opaque(L,-1)==replacement);lua_pop(L,1);
 }else return 91;
 if(scene!="previous_variant"){
  const char*name=scene=="charge"?"Charge":scene=="state"?"State":scene=="timeout"?"Timeout":"Touched";
  RetireEntityLifetime(AddressOf(g_Entities[kPickup]));const std::string script="assert(pickup."+std::string(name)+"==nil);pickup."+name+"={} ";Unchanged(L,script.c_str());
 }
 lua_close(L);return 0;}
'''


class PickupDoorNativeFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='pickup-door-fields-');cls.addClassCleanup(cls.tmp.cleanup);work=Path(cls.tmp.name)
        sources=test_support.layered_lua_runtime_sources(SOURCE);cls.paths=tuple(sorted(set(sources)|set((ROOT/'runtime/src').rglob('*.hpp'))|set(SOURCE.rglob('*.hpp'))));cls.before=cls._snapshot()
        EVIDENCE.mkdir(parents=True,exist_ok=True);(EVIDENCE/'delegated-pickup-door-input-before.json').write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls._stable)
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        # 只为生产现有布局守卫铺原件；不同段按真实32/16/16/16字节长度复制。
        regions=((0x2695c4,32),(0x26e810,16),(0x26e89c,16),(0x385fec,16))
        guards='\n'.join('const unsigned char b'+str(i)+'[]={'+','.join(map(str,nro[offset:offset+size]))+'};std::memcpy(g_ModuleBytes.data()+'+hex(offset)+',b'+str(i)+','+str(size)+');' for i,(offset,size) in enumerate(regions))
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')];prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
        prefix=prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}','void* PickupDoorRoom();\nGameRoomObservation ReadCurrentGameRoom(uintptr_t,void** room){*room=PickupDoorRoom();return GameRoomObservation::Success;}')
        (EVIDENCE/'delegated-pickup-door-harness.cpp').write_text(prefix+MAIN.replace('FROZEN_GUARDS',guards))
        cls.binary=test_support.build_lua_harness(source_root=SOURCE,workdir=work,harness_source=prefix+MAIN.replace('FROZEN_GUARDS',guards))
    @classmethod
    def _snapshot(cls):return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
    @classmethod
    def _stable(cls):
        after=cls._snapshot();(EVIDENCE/'delegated-pickup-door-input-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('运行期间生产输入SHA改变，不能归属同一版本')
    def test_five_fixed_pc_native_field_contracts(self):
        selected=os.environ.get('ISAAC_PICKUP_DOOR_SCENES');scenes=selected.split(',') if selected else ('charge','state','timeout','touched','previous_variant')
        self.assertTrue(all(s in ('charge','state','timeout','touched','previous_variant') for s in scenes))
        for scene in scenes:
            with self.subTest(scene=scene):
                result=subprocess.run([str(self.binary),scene],capture_output=True,text=True);print(f'{scene}: exit={result.returncode} {result.stdout}{result.stderr}',flush=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
