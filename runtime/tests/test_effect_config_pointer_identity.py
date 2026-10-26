"""四族真实公开getter与GetPtrHash：拥有弱引用值、借用、重分配及D2世代。"""
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
from .entityptr_native_fixture import SUPPORT

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'dist/api-remaining-recovery-20261025'
MAIN=r'''
#include "interfaces/lua/api600_entityptr.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
#include <cstdlib>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
WEAK_SUPPORT
static void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::exit(10);}}
static std::uintptr_t Hash(lua_State*L,int index){const int top=lua_gettop(L);index=lua_absindex(L,index);lua_getglobal(L,"GetPtrHash");lua_pushvalue(L,index);if(lua_pcall(L,1,1,0)!=LUA_OK)std::exit(11);assert(lua_isinteger(L,-1));const auto value=static_cast<std::uintptr_t>(lua_tointeger(L,-1));lua_settop(L,top);return value;}
static void Identity(lua_State*L,const char*name,std::uintptr_t expected){lua_getglobal(L,name);assert(lua_type(L,-1)==LUA_TUSERDATA);const int top=lua_gettop(L);bool known=false;assert(ResolveRegisteredObjectIdentity(L,-1,&known)==expected&&known&&lua_gettop(L)==top);assert(Hash(L,-1)==expected);lua_pop(L,1);}
int main(int argc,char**argv){
 if(argc!=2)return 90;const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 std::vector<unsigned char>manager(kManagerItemConfigOffset+0x100),slot(8),item(0x200),item2(0x200),items(16),effects(32),replacement(32);
 WriteWord(slot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(slot));WriteWord(items,8,AddressOf(item));WriteWord(manager,kManagerItemConfigOffset,AddressOf(items));WriteWord(manager,kManagerItemConfigOffset+8,AddressOf(items)+16);
 WriteAt<int>(item,0,1);WriteAt<int>(item,4,1);WriteAt<int>(item,0x80,17);WriteAt<int>(item2,0,1);WriteAt<int>(item2,4,2);
 WriteWord(effects,0,AddressOf(item));WriteAt<int>(effects,8,7);WriteAt<int>(effects,12,-9);WriteWord(effects,16,AddressOf(item2));WriteAt<int>(effects,24,8);WriteAt<int>(effects,28,-10);replacement=effects;
 const auto player=AddressOf(g_Entities[kPlayer]);auto publish=[&](std::vector<unsigned char>&v){WriteWord(g_Entities[kPlayer],0x18d8+8,AddressOf(v));WriteWord(g_Entities[kPlayer],0x18d8+16,AddressOf(v)+v.size());};publish(effects);
 FROZEN_GUARDS
 InstallWeakBindings();
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(RegisterIsaacApi(L));PushEntityCallbackArgument(L,player);lua_setglobal(L,"player");
 Run(L,"ptr1=EntityPtr(player);ptr2=EntityPtr(player);empty=EntityPtr(nil);item=Isaac.GetItemConfig():GetCollectible(1);costume1=item.Costume;costume2=item.Costume;effects=player:GetEffects();list1=effects:GetEffectsList();list2=effects:GetEffectsList();effect1=effects:GetCollectibleEffect(1);effect2=list1:Get(0);assert(effect1.Count==7 and effect2.Cooldown==-9 and list1.Size==2)");
 const auto before=g_Entities;const auto beforeEffects=effects;const auto beforeItem=item;
 if(scene=="ptr"){
  for(const auto*name:{"ptr1","ptr2","empty"}){lua_getglobal(L,name);const auto native=reinterpret_cast<std::uintptr_t>(lua_touserdata(L,-1));lua_pop(L,1);Identity(L,name,native);}
  lua_getglobal(L,"ptr1");const auto*slotPtr=static_cast<std::uintptr_t*>(lua_touserdata(L,-1));assert(weakRefs[player].count(const_cast<std::uintptr_t*>(slotPtr))==1);const auto native=reinterpret_cast<std::uintptr_t>(slotPtr);lua_pop(L,1);
  Run(L,"assert(ptr1~=ptr2 and GetPtrHash(ptr1)~=GetPtrHash(ptr2));alias=ptr1;assert(GetPtrHash(alias)==GetPtrHash(ptr1));ptr1:SetReference(nil);assert(ptr1.Ref==nil)");Identity(L,"ptr1",native);
  ClearNativeWeak(player);RetireEntityLifetime(player);Run(L,"assert(ptr2.Ref==nil and GetPtrHash(ptr1)~=0 and GetPtrHash(ptr2)~=0 and GetPtrHash(empty)~=0)");Identity(L,"ptr1",native);
 }else if(scene=="live"){
  Identity(L,"costume1",AddressOf(item)+0x80);Identity(L,"costume2",AddressOf(item)+0x80);Identity(L,"effects",player+0x18d8);Identity(L,"list1",player+0x18d8+8);Identity(L,"list2",player+0x18d8+8);Identity(L,"effect1",AddressOf(effects));Identity(L,"effect2",AddressOf(effects));
  Run(L,"assert(costume1~=costume2 and GetPtrHash(costume1)==GetPtrHash(costume2));assert(effect1~=effect2 and GetPtrHash(effect1)==GetPtrHash(effect2));assert(list1~=list2 and GetPtrHash(list1)==GetPtrHash(list2));assert(GetPtrHash(list1)~=GetPtrHash(effect1))");
 }else if(scene=="realloc"){
  publish(replacement);Run(L,"assert(effect1.Count==nil and effect2.Count==nil);fresh=list1:Get(0);assert(fresh.Count==7 and list1.Size==2)");Identity(L,"effect1",0);Identity(L,"effect2",0);Identity(L,"fresh",AddressOf(replacement));Identity(L,"list1",player+0x18d8+8);
 }else if(scene=="item_swap"){
  WriteWord(effects,0,AddressOf(item2));Run(L,"assert(effect1.Count==nil and effect2.Count==nil);fresh=list1:Get(0)");Identity(L,"effect1",0);Identity(L,"effect2",0);Identity(L,"fresh",AddressOf(effects));
 }else if(scene=="retire"){
  // D2真实退役，保留vptr和所有原生地址，再同址产生新token，旧wrapper不能复活。
  ClearNativeWeak(player);RetireEntityLifetime(player);Run(L,"assert(effect1.Count==nil,'D2 retired TemporaryEffect remained live');assert(not pcall(function()return list1.Size end),'D2 retired EffectList remained live');assert(effects:GetEffectsList()==nil,'D2 retired TemporaryEffects remained live')");
  for(const auto*name:{"effect1","effect2","list1","list2","effects"})Identity(L,name,0);
  PushEntityCallbackArgument(L,player);lua_setglobal(L,"newPlayer");Run(L,"newEffects=newPlayer:GetEffects();newList=newEffects:GetEffectsList();newEffect=newList:Get(0);assert(newEffect.Count==7);assert(effect1.Count==nil and not pcall(function()return list1.Size end))");Identity(L,"newEffect",AddressOf(effects));Identity(L,"effect1",0);
 }else if(scene=="base"){
  LuaRuntime::SetEngineModuleBase(g_EngineBase+8);for(const auto*name:{"costume1","effect1","list1","effects"})Identity(L,name,0);Run(L,"assert(not pcall(function()return costume1.ID end));assert(effect1.Count==nil);assert(not pcall(function()return list1.Size end))");LuaRuntime::SetEngineModuleBase(g_EngineBase);
 }else if(scene=="config_retire"){
  WriteWord(items,8,0);Identity(L,"costume1",0);Identity(L,"costume2",0);Run(L,"assert(not pcall(function()return costume1.ID end))");
 }else if(scene=="short"){
  for(const auto*mt:{"IsaacRuntime.EntityPtr","IsaacRuntime.ItemConfig_Costume","IsaacRuntime.TemporaryEffects","IsaacRuntime.TemporaryEffect","IsaacRuntime.EffectList"})for(unsigned size:{0U,1U,7U}){lua_newuserdata(L,size);luaL_getmetatable(L,mt);lua_setmetatable(L,-2);bool known=false;const int top=lua_gettop(L);assert(ResolveRegisteredObjectIdentity(L,-1,&known)==0&&known&&lua_gettop(L)==top);assert(Hash(L,-1)==0);lua_pushnil(L);lua_setmetatable(L,-2);lua_pop(L,1);}
 }else return 91;
 if(scene=="live"||scene=="short"||scene=="config_retire"||scene=="base")assert(g_Entities==before&&effects==beforeEffects&&item==beforeItem);
 ClearAllNativeWeak();lua_close(L);return 0;
}
'''

class EffectConfigPointerIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='effect-config-identity-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.prefix=os.environ.get('ISAAC_EFFECT_IDENTITY_PREFIX','delegated-effect-identity-red')
        cls.paths=tuple(sorted(set(test_support.layered_lua_runtime_sources(fixture.SOURCE))|set((ROOT/'runtime/src').rglob('*.hpp'))|set(fixture.SOURCE.rglob('*.hpp'))));cls.before=cls.snapshot();EVIDENCE.mkdir(parents=True,exist_ok=True)
        (EVIDENCE/(cls.prefix+'-input-before.json')).write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls.stable)
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        guards='\n'.join('const unsigned char b'+str(i)+'[]={'+','.join(map(str,nro[o:o+16]))+'};std::memcpy(g_ModuleBytes.data()+'+hex(o)+',b'+str(i)+',16);' for i,o in enumerate((0x3ba064,)))
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')];prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
        source=prefix+MAIN.replace('WEAK_SUPPORT',SUPPORT).replace('FROZEN_GUARDS',guards);(EVIDENCE/(cls.prefix+'-harness.cpp')).write_text(source)
        cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
    @classmethod
    def snapshot(cls):return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
    @classmethod
    def stable(cls):
        after=cls.snapshot();(EVIDENCE/(cls.prefix+'-input-after.json')).write_text(json.dumps(after,indent=2)+'\n')
        if cls.before!=after:raise AssertionError('生产输入在编译/执行期间变化')
    def test_real_owner_identities(self):
        for scene in ('ptr','live','realloc','item_swap','retire','base','config_retire','short'):
            with self.subTest(scene=scene):
                r=subprocess.run([str(self.binary),scene],text=True,capture_output=True);print(f'{scene}: exit={r.returncode} {r.stdout}{r.stderr}',flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
