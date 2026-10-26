"""Pickup.CanReroll/HUD.Render独立正向合约：真实公开接线与最终native边界。

不使用NPC.CanReroll或Room.Render；不设置HudNativeTestBindings绕过守卫。
取证及运行边界见dist/api-remaining-recovery-20261025/pickup-hud-notes.md。
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
OUT=ROOT/'dist/api-remaining-recovery-20261025'
MAIN=r'''
#include "interfaces/lua/game_api.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
#include <cstdlib>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static unsigned pickupCalls{},hudCalls{},pickupRedirects{},hudRedirects{};
static bool pickupResult=true;
static bool wrongSelfProbe{};
static bool NativePickupCanReroll(const void*self){if(!wrongSelfProbe)assert(self==g_Entities[kPickup].data());++pickupCalls;return pickupResult;}
static void NativeHudRender(void*self){assert(reinterpret_cast<std::uintptr_t>(self)==AddressOf(g_GameBytes)+0xe8468);++hudCalls;}
extern "C" std::uintptr_t PickupHudNativeRedirect(std::uintptr_t original) noexcept {
 if(original==g_EngineBase+0x26afa8){++pickupRedirects;return reinterpret_cast<std::uintptr_t>(&NativePickupCanReroll);}
 if(original==g_EngineBase+0x3ac71c){++hudRedirects;return reinterpret_cast<std::uintptr_t>(&NativeHudRender);}
 return original;
}
static void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::exit(10);}}
static void Denied(lua_State*L,const char*s){const auto p=pickupCalls,h=hudCalls,pr=pickupRedirects,hr=hudRedirects;const auto entities=g_Entities;const auto game=g_GameBytes;Run(L,s);assert(p==pickupCalls&&h==hudCalls&&pr==pickupRedirects&&hr==hudRedirects&&entities==g_Entities&&game==g_GameBytes);}
static void GameHudViews(lua_State*L){
 // 私有RegisterGameApi不由RegisterIsaacApi执行；只补装生产Game/HUD方法与访问器。
 luaL_newmetatable(L,LuaRuntime::kGameMetatable);lua_newtable(L);static_cast<void>(AttachGameMethods(L));lua_pushcclosure(L,GameIndex,1);lua_setfield(L,-2,"__index");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kHudMetatable);lua_newtable(L);static_cast<void>(AttachHudMethods(L));lua_setfield(L,-2,"__methods");lua_pushcfunction(L,NativeClassMethodIndex);lua_setfield(L,-2,"__index");lua_pop(L,1);
 auto*h=static_cast<LuaRuntime::GameHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::GameHandle)));h->reserved=0;luaL_getmetatable(L,LuaRuntime::kGameMetatable);lua_setmetatable(L,-2);lua_setglobal(L,"game");
}
int main(int argc,char**argv){
 if(argc!=2)return 90;const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();if(scene=="pickup_wrong_entity")WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 FROZEN_GUARDS
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(RegisterIsaacApi(L));GameHudViews(L);
 PushEntityCallbackArgument(L,AddressOf(g_Entities[kPickup]));lua_setglobal(L,"pickup");
 Run(L,"assert(getmetatable(pickup).__type=='EntityPickup');hud=game:GetHUD();assert(type(hud)=='userdata');pickupMethod=pickup.CanReroll;hudMethod=hud.Render;assert(type(pickupMethod)=='function' and type(hudMethod)=='function')");
 const auto entities=g_Entities;const auto game=g_GameBytes;
 if(scene=="pickup_positive"){
  Run(L,"local values={pickup:CanReroll()};assert(#values==1 and type(values[1])=='boolean' and values[1]==true)");assert(pickupCalls==1&&pickupRedirects==1&&hudCalls==0&&hudRedirects==0);
  pickupResult=false;Run(L,"local values={pickup:CanReroll()};assert(#values==1 and type(values[1])=='boolean' and values[1]==false)");assert(pickupCalls==2&&pickupRedirects==2);
  pickupResult=true;Run(L,"assert(pickupMethod(pickup)==true)");assert(pickupCalls==3&&pickupRedirects==3);
  Denied(L,"assert(not pcall(pickupMethod,{}));assert(not pcall(function()pickup:CanReroll(1)end))");
 }else if(scene=="pickup_retired"){
  Run(L,"assert(pickup:CanReroll()==true)");assert(pickupCalls==1&&pickupRedirects==1);RetireEntityLifetime(AddressOf(g_Entities[kPickup]));Denied(L,"assert(not pcall(pickupMethod,pickup))");
 }else if(scene=="pickup_guard"){
  g_ModuleBytes[0x26afa8]^=1;Denied(L,"assert(not pcall(pickupMethod,pickup))");assert(!pickupCalls&&!pickupRedirects&&!hudCalls);
 }else if(scene=="pickup_wrong_entity"){
  Run(L,"assert(pickup:CanReroll()==true);wrongPlayer=Isaac.GetPlayer(0);wrongNpc=Isaac.FindByType(20)[1];assert(type(wrongPlayer)=='userdata' and getmetatable(wrongPlayer).__type=='EntityPlayer');assert(type(wrongNpc)=='userdata' and getmetatable(wrongNpc).__type=='EntityNPC')");assert(pickupCalls==1&&pickupRedirects==1);
  // PC806F76→820CA0→837D70用Pickup专属registry C06843；不允许同属Entity的兄弟族。
  // 若生产漏校验，桩只记录调用而不解引用错族内存，确保两个错误self均被探测。
  wrongSelfProbe=true;Run(L,"local f=pickup.CanReroll;wrongPlayerAccepted=pcall(f,wrongPlayer);wrongNpcAccepted=pcall(f,wrongNpc)");
  fprintf(stderr,"wrong entity native=%u redirect=%u (expected both 1)\n",pickupCalls,pickupRedirects);
  assert(pickupCalls==1&&pickupRedirects==1&&!hudCalls&&!hudRedirects);Run(L,"assert(not wrongPlayerAccepted,'Pickup method accepted EntityPlayer self');assert(not wrongNpcAccepted,'Pickup method accepted EntityNPC self')");
 }else if(scene=="hud_positive"){
  Run(L,"assert(select('#',hud:Render())==0);assert(select('#',hudMethod(hud))==0)");assert(hudCalls==2&&hudRedirects==2&&!pickupCalls&&!pickupRedirects);Denied(L,"assert(not pcall(hudMethod,{}))");
 }else if(scene=="hud_owner_lost"){
  Run(L,"assert(select('#',hud:Render())==0)");assert(hudCalls==1&&hudRedirects==1);WriteWord(g_OwnerSlotBytes,0,0);Denied(L,"assert(not pcall(hudMethod,hud))");
 }else if(scene=="hud_guard"){
  g_ModuleBytes[0x3ac71c]^=1;Denied(L,"assert(not pcall(hudMethod,hud))");assert(!hudCalls&&!hudRedirects&&!pickupCalls);
 }else return 91;
 assert(entities==g_Entities&&game==g_GameBytes);lua_close(L);return 0;
}
'''

class PickupHudNativeCallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='pickup-hud-');cls.addClassCleanup(cls.tmp.cleanup);work=Path(cls.tmp.name)
        cls.prefix=os.environ.get('ISAAC_PICKUP_HUD_PREFIX','pickup-hud-main')
        cls.paths=tuple(sorted(set(test_support.layered_lua_runtime_sources(fixture.SOURCE))|set((ROOT/'runtime/src').rglob('*.hpp'))|set(fixture.SOURCE.rglob('*.hpp'))));cls.before=cls.snapshot();OUT.mkdir(parents=True,exist_ok=True)
        (OUT/(cls.prefix+'-input-before.json')).write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls.stable)
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        # 来自固定原件，不能从生产guard数组反向生成独立期望。
        guards='\n'.join('const unsigned char b'+str(i)+'[]={'+','.join(map(str,nro[o:o+n]))+'};std::memcpy(g_ModuleBytes.data()+'+hex(o)+',b'+str(i)+','+str(n)+');' for i,(o,n) in enumerate(((0x26afa8,4),(0x3ac71c,16))))
        header=ROOT/'runtime/src/infrastructure/call/engine_call_access.hpp';code=header.read_text();old='return address == 0 ? nullptr : reinterpret_cast<Fn>(address);';assert code.count(old)==1
        code=code.replace('namespace isaac::runtime::engine_call {','extern "C" std::uintptr_t PickupHudNativeRedirect(std::uintptr_t) noexcept;\nnamespace isaac::runtime::engine_call {',1).replace(old,'return address == 0 ? nullptr : reinterpret_cast<Fn>(::PickupHudNativeRedirect(address));')
        shadow=work/'compatibility/infrastructure/call/engine_call_access.hpp';shadow.parent.mkdir(parents=True,exist_ok=True);shadow.write_text(code)
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')];prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
        source=prefix+MAIN.replace('FROZEN_GUARDS',guards);(OUT/(cls.prefix+'-harness.cpp')).write_text(source);(OUT/(cls.prefix+'-shadow-engine-call.hpp')).write_text(code)
        cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=work,harness_source=source)
    @classmethod
    def snapshot(cls):return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
    @classmethod
    def stable(cls):
        after=cls.snapshot();(OUT/(cls.prefix+'-input-after.json')).write_text(json.dumps(after,indent=2)+'\n')
        if cls.before!=after:raise AssertionError('生产输入在编译/执行期间改变')
    def test_pickup_can_reroll_real_public_native(self):
        self.scenes(('pickup_positive','pickup_retired','pickup_guard','pickup_wrong_entity'))
    def test_hud_render_real_public_native(self):
        self.scenes(('hud_positive','hud_owner_lost','hud_guard'))
    def scenes(self,scenes):
        for scene in scenes:
            with self.subTest(scene=scene):
                r=subprocess.run([str(self.binary),scene],text=True,capture_output=True);print(f'{scene}: exit={r.returncode} {r.stdout}{r.stderr}',flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
