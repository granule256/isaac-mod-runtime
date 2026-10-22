"""Entity五方法真实继承消费、返回身份与失效引用。"""
import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
MAIN=r'''
#include "interfaces/lua/api100_core.hpp"
#include "interfaces/lua/api100_core.guards.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static unsigned calls[5]{};static bool exploded{};static void*child{};
static void Touch(void*p,unsigned i){assert(p==g_Entities[kPlayer].data());++calls[i];}
static void Blood(void*p){Touch(p,0);exploded=true;}
static void*Parent(void*p){Touch(p,1);return g_Entities[kEnemyA].data();}
static void*Child(void*p){Touch(p,2);return child?child:p;}
static bool Health(void*p){Touch(p,3);return !exploded;}
static bool Frame(void*p,std::int32_t frame,std::int32_t offset){Touch(p,4);assert(frame==17||frame==0);assert(offset==3||offset==-1);return frame==17;}
int main(){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 namespace guards=api100_core;auto guard=[&](auto o,const auto&bytes){std::memcpy(g_ModuleBytes.data()+o,bytes.data(),16);};
 guard(guards::kBloodExplodeEntry,guards::kBloodExplodeGuard);guard(guards::kGetLastParentEntry,guards::kGetLastParentGuard);guard(guards::kGetLastChildEntry,guards::kGetLastChildGuard);guard(guards::kHasFullHealthEntry,guards::kHasFullHealthGuard);guard(guards::kIsFrameEntry,guards::kIsFrameGuard);
 Api100CoreNativeTestBindings bindings{{engine_call::AddressOfFunction(&Blood),engine_call::AddressOfFunction(&Parent),engine_call::AddressOfFunction(&Child),engine_call::AddressOfFunction(&Health),engine_call::AddressOfFunction(&Frame)}};SetApi100CoreNativeTestBindings(bindings);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));
 const char*s=R"LUA(
 p=Isaac.GetPlayer();local npc=Isaac.FindByType(20)[1];local fam=Isaac.FindByType(3)[1]:ToFamiliar();assert(GetPtrHash(fam)~=0,"typed Familiar must retain its pointer hash");assert(p:HasFullHealth('extra'))
 assert(GetPtrHash(p:GetLastParent())==GetPtrHash(npc));assert(GetPtrHash(p:GetLastChild())==GetPtrHash(p));p:BloodExplode(true);assert(not p:HasFullHealth())
 assert(p:IsFrame('4294967313',4294967299));assert(not p:IsFrame(0,-1));assert(not pcall(function()p:IsFrame(17)end));assert(not pcall(function()p:IsFrame({},1)end));assert(not pcall(function()p.IsFrame(nil,17,3)end))
 )LUA";
 if(luaL_dostring(L,s)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}
 child=g_Entities[kEnemyA].data();assert(luaL_dostring(L,"local c=p:GetLastChild();assert(c.Type==20)")==LUA_OK);
 RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));assert(luaL_dostring(L,"assert(not pcall(function()p:BloodExplode()end));assert(not pcall(function()p:GetLastChild()end))")==LUA_OK);
 assert(calls[0]==1&&calls[1]==1&&calls[2]==2&&calls[3]==2&&calls[4]==2);
 lua_close(L);return 0;
}
'''
class Core5Behavior(unittest.TestCase):
 def test_entity_inheritance_effects_identity_integer_and_lifetime(self):
  prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
  prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
  with tempfile.TemporaryDirectory(prefix='api100-core-')as d:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+MAIN)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
