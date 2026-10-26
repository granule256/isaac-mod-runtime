"""五类参数对象GetPtrHash：真实native存储、别名、值副本、寿命与短userdata。

只按各族原生布局核身份，不把Lua包装头当成借用对象；不通过全局类型扫描补接线。
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
#include "interfaces/lua/api400_params.hpp"
#include "interfaces/lua/api600_player.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
#include <cstdlib>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;using Vec=LuaRuntime::VectorHandle;
static unsigned projectileCalls{},tearCalls{},multiCalls{},posCalls{};static std::uintptr_t projectileAddress{};
static std::uint32_t Random(){return 0x40000000;}
static std::uintptr_t Fire(void*self,const Vec*pos,const Vec*velocity,std::int32_t mode,const void*params){assert(self==g_Entities[kEnemyA].data()&&pos->x==3&&velocity->y==4&&mode==9);++projectileCalls;projectileAddress=reinterpret_cast<std::uintptr_t>(params);float scale{};std::memcpy(&scale,static_cast<const char*>(params)+0x14,4);assert(scale==2.625F);return 0;}
static Api600TearParams Tear(void*self,std::int32_t weapon,float scale,std::int32_t displacement,void*source){assert(self==g_Entities[kPlayer].data()&&weapon==1&&scale==1&&displacement==1&&!source);++tearCalls;Api600TearParams result{};const std::int32_t variant=17;const float damage=13.25;std::memcpy(result.bytes,&variant,4);std::memcpy(result.bytes+0x48,&damage,4);return result;}
static Api600MultiShotParams Multi(void*self,std::int32_t weapon){assert(self==g_Entities[kPlayer].data()&&weapon==1);++multiCalls;Api600MultiShotParams result{};for(unsigned i=0;i<sizeof(result.bytes);++i)result.bytes[i]=static_cast<unsigned char>(i+17);return result;}
static Api600PosVel Pos(std::int32_t loop,std::int32_t weapon,Vec direction,float speed,Api600MultiShotParams params){assert(loop==2&&weapon==1&&direction.x==3&&direction.y==4&&speed==2.5F);++posCalls;for(unsigned i=0;i<sizeof(params.bytes);++i)assert(params.bytes[i]==i+17);return{10,20,7.5F,10};}
static int NativeDesc(lua_State*L){lua_pushinteger(L,static_cast<lua_Integer>(Api600EntityDescArgument(L,1)));return 1;}
static void Run(lua_State*L,const char*script){if(luaL_dostring(L,script)){std::fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),script);std::exit(10);}}
static std::uintptr_t Hash(lua_State*L,int index){const int top=lua_gettop(L);const int object=lua_absindex(L,index);lua_getglobal(L,"GetPtrHash");lua_pushvalue(L,object);if(lua_pcall(L,1,1,0)!=LUA_OK){std::fprintf(stderr,"GetPtrHash error: %s\n",lua_tostring(L,-1));std::exit(11);}assert(lua_isinteger(L,-1));const auto value=static_cast<std::uintptr_t>(lua_tointeger(L,-1));lua_settop(L,top);return value;}
static void CheckOwned(lua_State*L,const char*name,std::size_t size){const int top=lua_gettop(L);lua_getglobal(L,name);assert(lua_type(L,-1)==LUA_TUSERDATA&&lua_rawlen(L,-1)==size);const auto native=reinterpret_cast<std::uintptr_t>(lua_touserdata(L,-1));assert(native&&Hash(L,-1)==native);const auto before=g_Entities;bool recognized=false;const int withObject=lua_gettop(L);const auto direct=ResolveRegisteredObjectIdentity(L,-1,&recognized);assert(recognized&&direct==native&&lua_gettop(L)==withObject);assert(before==g_Entities);lua_settop(L,top);}
int main(int argc,char**argv){if(argc!=2)return 90;const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 FROZEN_GUARDS
 SetApi400ParamsNativeTestBindings({{engine_call::AddressOfFunction(&Random),engine_call::AddressOfFunction(&Fire),0}});SetApi600PlayerNativeTestBindings({{engine_call::AddressOfFunction(&Tear),engine_call::AddressOfFunction(&Multi),engine_call::AddressOfFunction(&Pos),0}});
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);assert(RegisterIsaacApi(L));lua_pushcfunction(L,NativeDesc);lua_setglobal(L,"nativeDescArgument");RegisterVectorReferenceMetatable(L);luaL_newmetatable(L,LuaRuntime::kVectorMetatable);lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,VectorNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachVectorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");
 PushEntityCallbackArgument(L,AddressOf(g_Entities[kPlayer]));lua_setglobal(L,"p");PushEntityCallbackArgument(L,AddressOf(g_Entities[kEnemyA]));lua_setglobal(L,"npc");
 Run(L,"proj1=ProjectileParams();proj2=ProjectileParams();proj1.Scale=2.625;tear1=p:GetTearHitParams(1);tear2=p:GetTearHitParams(1);multi1=p:GetMultiShotParams();multi2=p:GetMultiShotParams();pv1=p:GetMultiShotPositionVelocity(2,1,Vector(3,4),2.5,multi1);pv2=p:GetMultiShotPositionVelocity(2,1,Vector(3,4),2.5,multi2);desc1=p.FriendBallEnemy;desc2=p.FriendBallEnemy");
 assert(tearCalls==2&&multiCalls==2&&posCalls==2);
 if(scene=="owned"){
  CheckOwned(L,"proj1",0xa8);CheckOwned(L,"tear1",0x68);CheckOwned(L,"multi1",0x24);CheckOwned(L,"pv1",0x10);
  Run(L,"for _,pair in ipairs({{proj1,proj2},{tear1,tear2},{multi1,multi2},{pv1,pv2}})do local alias=pair[1];assert(GetPtrHash(alias)~=0 and GetPtrHash(alias)==GetPtrHash(pair[1]) and GetPtrHash(pair[1])~=GetPtrHash(pair[2])) end;assert(tear1.TearVariant==17 and tear1.TearDamage==13.25 and pv1.Position.X==10 and pv1.Velocity.Y==10);npc:FireProjectiles(Vector(3,4),Vector(3,4),9,proj1)");
  lua_getglobal(L,"proj1");assert(Hash(L,-1)==projectileAddress&&projectileCalls==1);lua_pop(L,1);
  const auto calls=projectileCalls+tearCalls+multiCalls+posCalls;Run(L,"for i=1,100 do assert(GetPtrHash(proj1)~=0 and GetPtrHash(tear1)~=0 and GetPtrHash(multi1)~=0 and GetPtrHash(pv1)~=0)end");assert(calls==projectileCalls+tearCalls+multiCalls+posCalls);
  RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));Run(L,"assert(GetPtrHash(proj1)~=0 and GetPtrHash(tear1)~=0 and GetPtrHash(multi1)~=0 and GetPtrHash(pv1)~=0)");
 }else if(scene=="desc_live"||scene=="desc_retired"||scene=="desc_base"){
  const auto native=AddressOf(g_Entities[kPlayer])+0x1d88;lua_getglobal(L,"desc1");const auto wrapper=reinterpret_cast<std::uintptr_t>(lua_touserdata(L,-1));assert(wrapper!=native&&Hash(L,-1)==native);assert(Api600EntityDescArgument(L,-1)==native);lua_pop(L,1);
  lua_pushinteger(L,static_cast<lua_Integer>(native));lua_setglobal(L,"nativeDesc");Run(L,"assert(desc1~=desc2 and GetPtrHash(desc1)==nativeDesc and GetPtrHash(desc2)==nativeDesc)");
  if(scene=="desc_retired"){RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));Run(L,"assert(GetPtrHash(desc1)==0 and GetPtrHash(desc2)==0);assert(not pcall(function()return desc1.Type end));assert(not pcall(nativeDescArgument,desc2))");}
  if(scene=="desc_base"){auto other=g_ModuleBytes;const auto base=AddressOf(other);WriteWord(g_Entities[kPlayer],0,base+kEntityPlayerVtableOffset);LuaRuntime::SetEngineModuleBase(base);Run(L,"assert(GetPtrHash(desc1)==0 and GetPtrHash(desc2)==0);assert(not pcall(function()return desc1.Type end));assert(not pcall(nativeDescArgument,desc2))");LuaRuntime::SetEngineModuleBase(g_EngineBase);WriteWord(g_Entities[kPlayer],0,g_EngineBase+kEntityPlayerVtableOffset);}
 }else if(scene=="short"){
  const char*metatables[]={"IsaacRuntime.ProjectileParams","IsaacRuntime.TearParams","IsaacRuntime.MultiShotParams","IsaacRuntime.PlayerTypesPosVel","IsaacRuntime.ConstEntityDesc"};
  for(const auto*mt:metatables)for(unsigned size:{0U,1U,7U}){lua_newuserdata(L,size);luaL_getmetatable(L,mt);lua_setmetatable(L,-2);const int top=lua_gettop(L);bool recognized=false;assert(ResolveRegisteredObjectIdentity(L,-1,&recognized)==0&&recognized&&lua_gettop(L)==top);assert(Hash(L,-1)==0);lua_pop(L,1);}
 }else return 91;
 lua_close(L);return 0;}
'''


class ParameterObjectIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='parameter-identity-');cls.addClassCleanup(cls.tmp.cleanup);work=Path(cls.tmp.name)
        sources=test_support.layered_lua_runtime_sources(SOURCE);cls.paths=tuple(sorted(set(sources)|set((ROOT/'runtime/src').rglob('*.hpp'))|set(SOURCE.rglob('*.hpp'))));cls.before=cls._snapshot()
        EVIDENCE.mkdir(parents=True,exist_ok=True);(EVIDENCE/'registry-params-input-before.json').write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls._stable)
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        offsets=(0x35830,0x10ce58,0x277b84,0x278da4,0x27f994,0x2b261c,0x280814,0x4a791c,0x2ad64c,0x2bb0f4,0x2bb754)
        guards='\n'.join('const unsigned char g'+str(i)+'[]={'+','.join(map(str,nro[offset:offset+16]))+'};std::memcpy(g_ModuleBytes.data()+'+hex(offset)+',g'+str(i)+',16);' for i,offset in enumerate(offsets))
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')];prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
        cls.binary=test_support.build_lua_harness(source_root=SOURCE,workdir=work,harness_source=prefix+MAIN.replace('FROZEN_GUARDS',guards))

    @classmethod
    def _snapshot(cls):return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
    @classmethod
    def _stable(cls):
        after=cls._snapshot();(EVIDENCE/'registry-params-input-after.json').write_text(json.dumps(after,indent=2)+'\n')
        if after!=cls.before:raise AssertionError('运行期间生产源码发生变化，无法归属单一输入')
    def test_owned_and_borrowed_real_native_identity(self):
        selected=os.environ.get('ISAAC_PARAMS_IDENTITY_SCENES');scenes=selected.split(',') if selected else ('owned','desc_live','desc_retired','desc_base','short')
        self.assertTrue(all(s in ('owned','desc_live','desc_retired','desc_base','short') for s in scenes))
        for scene in scenes:
            with self.subTest(scene=scene):
                result=subprocess.run([str(self.binary),scene],capture_output=True,text=True);print(f'{scene}: exit={result.returncode} {result.stdout}{result.stderr}',flush=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
