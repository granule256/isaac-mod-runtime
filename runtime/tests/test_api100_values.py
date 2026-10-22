"""第一组20玩家方法的真实Lua→原生行为判据。"""
import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
ROOT=Path(__file__).resolve().parents[2]
BASELINE=r'''
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 const char*script="local m=RegisterMod('api100-values',1);m:AddCallback(1,function()local c=Color(1,1,1,1);local s=Isaac.GetPlayer():GetSprite();local music=MusicManager();assert(type(c.SetOffset)=='function' and type(c.SetTint)=='function' and type(c.Reset)=='function' and type(s.Reload)=='function' and type(s.RemoveOverlay)=='function' and type(music.Fadein)=='function' and type(music.Fadeout)=='function')end)";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api100-values.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();return LuaRuntime::TakeCallbackError()?2:0;
}
'''
class Values7Baseline(unittest.TestCase):
 def test_required_methods_registered(self):
  with tempfile.TemporaryDirectory(prefix='api100-values-red-')as d:
   source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+BASELINE
   source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
   extra=ROOT/'runtime/src/interfaces/lua/api100_values.cpp'
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=source,extra_sources=()if not extra.exists()or extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

MAIN=r'''

#include "interfaces/lua/api100_values.hpp"
#include "interfaces/lua/api100_values.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/color_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/music_api.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
#include <cmath>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static void*wantSprite{},*wantMusic{};static unsigned calls[7]{},graphics{},overlays{},starts{};static int musicId{};static float volume{},rate{};
static void Offset(EngineColorMod*c,float r,float g,float b){++calls[0];assert(c->tint[0]==1&&std::fabs(c->colorize[3]-.4F)<1e-6);assert(r==-1&&g==2&&b==3);c->shift[0]=r;c->shift[1]=g;c->shift[2]=b;}
static void Tint(EngineColorMod*c,float r,float g,float b,float a){++calls[1];assert(c->shift[0]==-1&&std::fabs(c->colorize[3]-.4F)<1e-6);assert(r==.25F&&g==.5F&&b==.75F&&a==.125F);c->tint[0]=r;c->tint[1]=g;c->tint[2]=b;c->tint[3]=a;}
static void Reset(EngineColorMod*c){++calls[2];assert(c->tint[3]==.125F&&c->shift[2]==3);*c=DefaultEngineColorMod();}
static void Reload(void*p){++calls[3];assert(p==wantSprite);static_cast<unsigned char*>(p)[0x149]=1;++graphics;}
static void Overlay(void*p){++calls[4];assert(p==wantSprite);std::uintptr_t none=0;std::memcpy(static_cast<unsigned char*>(p)+0x68,&none,8);++overlays;}
static void Fadein(void*p,std::int32_t id,float vol,float fade){++calls[5];assert(p==wantMusic);
 const int ids[]={1,2,3,4};const float vols[]={1,1,0,.5F},rates[]={.08F,.08F,0,.2F};
 const auto i=calls[5]-1;assert(i<4&&id==ids[i]&&vol==vols[i]&&std::fabs(fade-rates[i])<1e-6);
 musicId=id;volume=vol;rate=fade;++starts;std::memcpy(static_cast<unsigned char*>(p)+0x1d8,&vol,4);std::memcpy(static_cast<unsigned char*>(p)+0x1dc,&fade,4);}
static void Fadeout(void*p,float fade){++calls[6];assert(p==wantMusic);const float rates[]={.08F,.08F,0,.3F};const auto i=calls[6]-1;assert(i<4&&std::fabs(fade-rates[i])<1e-6);rate=fade;volume=0;std::memcpy(static_cast<unsigned char*>(p)+0x1dc,&fade,4);}
static int MusicCtor(lua_State*L){auto*h=static_cast<LuaRuntime::MusicHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::MusicHandle)));h->reserved=0;luaL_getmetatable(L,LuaRuntime::kMusicMetatable);lua_setmetatable(L,-2);return 1;}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 std::vector<unsigned char>manager(kManagerMusicOffset+0x1000),slot(8);WriteWord(slot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(slot));wantMusic=manager.data()+kManagerMusicOffset;wantSprite=g_Entities[kPlayer].data()+kEntitySpriteOffset;
 std::uintptr_t overlay=0x1234;std::memcpy(static_cast<unsigned char*>(wantSprite)+0x68,&overlay,8);
 namespace guards=api100_values;auto guard=[&](auto o,const auto&b){std::memcpy(g_ModuleBytes.data()+o,b.data(),b.size());};
 guard(guards::kColorSetOffsetEntry,guards::kColorSetOffsetGuard);
guard(guards::kColorSetTintEntry,guards::kColorSetTintGuard);
guard(guards::kColorResetEntry,guards::kColorResetGuard);
guard(guards::kSpriteReloadEntry,guards::kSpriteReloadGuard);
guard(guards::kSpriteRemoveOverlayEntry,guards::kSpriteRemoveOverlayGuard);
guard(guards::kMusicManagerFadeinEntry,guards::kMusicManagerFadeinGuard);
guard(guards::kMusicManagerFadeoutEntry,guards::kMusicManagerFadeoutGuard);
 Api100ValuesNativeTestBindings bindings{};
 bindings.methods[0]=engine_call::AddressOfFunction(&Offset);
bindings.methods[1]=engine_call::AddressOfFunction(&Tint);
bindings.methods[2]=engine_call::AddressOfFunction(&Reset);
bindings.methods[3]=engine_call::AddressOfFunction(&Reload);
bindings.methods[4]=engine_call::AddressOfFunction(&Overlay);
bindings.methods[5]=engine_call::AddressOfFunction(&Fadein);
bindings.methods[6]=engine_call::AddressOfFunction(&Fadeout);
 SetApi100ValuesNativeTestBindings(bindings);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_MATHLIBNAME,luaopen_math,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));
 luaL_newmetatable(L,LuaRuntime::kColorMetatable);lua_pushcfunction(L,ColorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,ColorNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachColorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);lua_pushcfunction(L,CreateColorHandle);lua_setglobal(L,"Color");
 luaL_newmetatable(L,LuaRuntime::kSpriteMetatable);lua_pushcfunction(L,SpriteIndex);lua_setfield(L,-2,"__index");lua_newtable(L);static_cast<void>(AttachSpriteMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kMusicMetatable);lua_pushvalue(L,-1);lua_setfield(L,-2,"__index");static_cast<void>(AttachMusicMethods(L));lua_pop(L,1);lua_pushcfunction(L,MusicCtor);lua_setglobal(L,"MusicManager");
 if(scene!="integration"){
 luaL_getmetatable(L,LuaRuntime::kColorMetatable);lua_getfield(L,-1,"__methods");
lua_pushcfunction(L,Api100ColorSetOffset);lua_setfield(L,-2,"SetOffset");
lua_pushcfunction(L,Api100ColorSetTint);lua_setfield(L,-2,"SetTint");
lua_pushcfunction(L,Api100ColorReset);lua_setfield(L,-2,"Reset");
lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kSpriteMetatable);lua_getfield(L,-1,"__methods");
lua_pushcfunction(L,Api100SpriteReload);lua_setfield(L,-2,"Reload");
lua_pushcfunction(L,Api100SpriteRemoveOverlay);lua_setfield(L,-2,"RemoveOverlay");
lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kMusicMetatable);
lua_pushcfunction(L,Api100MusicManagerFadein);lua_setfield(L,-2,"Fadein");
lua_pushcfunction(L,Api100MusicManagerFadeout);lua_setfield(L,-2,"Fadeout");
lua_pop(L,1);
 }
 const char*script=R"lua(
 c=Color(1,1,1,1);s=Isaac.GetPlayer():GetSprite();m=MusicManager();local p=Isaac.GetPlayer();local same=c
 c:SetColorize(.1,.2,.3,.4)
 assert(select('#',c:SetOffset('-1',2,3,false))==0);assert(c.RO==-1 and c.GO==2 and c.BO==3 and c.R==1)
 assert(select('#',c:SetTint(.25,.5,.75,.125))==0);assert(c==same and c.R==.25 and c.A==.125 and c.RO==-1)
 assert(select('#',c:Reset('ignored'))==0);assert(c==same and c.R==1 and c.G==1 and c.B==1 and c.A==1 and c.RO==0 and c.GO==0 and c.BO==0)
 assert(select('#',s:Reload(false))==0);assert(s:IsLoaded());assert(select('#',s:RemoveOverlay({}))==0)
 assert(select('#',m:Fadein('4294967297'))==0)
 m:Fadein(2,false,nil);m:Fadein(3,0,0);m:Fadein(4,'0.5','0.2','ignored')
 m:Fadeout();m:Fadeout(false);m:Fadeout(0);m:Fadeout('0.3',{})
 assert(not pcall(function()c:SetOffset(1,2)end));assert(not pcall(function()c:SetTint(1,2,3)end));assert(not pcall(function()c:SetOffset(false,2,3)end));assert(not pcall(function()c:SetTint(1,2,3,{})end))
 assert(not pcall(function()m:Fadein()end));assert(not pcall(function()m:Fadein(1.5)end));assert(not pcall(function()m:Fadein(1,{},1)end));assert(not pcall(function()m:Fadeout('x')end))
 for _,name in ipairs({'SetOffset','SetTint','Reset'})do local fn=c[name];assert(not pcall(function()fn(p,1,2,3,4)end));assert(not pcall(function()fn({},1,2,3,4)end))end
 for _,name in ipairs({'Reload','RemoveOverlay'})do local fn=s[name];assert(not pcall(function()fn(p)end));assert(not pcall(function()fn(nil)end))end
 for _,name in ipairs({'Fadein','Fadeout'})do local fn=m[name];assert(not pcall(function()fn(c,1)end));assert(not pcall(function()fn({},1)end))end
 )lua";
 if(scene=="badguard"){g_ModuleBytes[guards::kColorSetOffsetEntry]^=1;script="local c=Color(1,1,1,1);assert(not pcall(function()c:SetOffset(1,2,3)end))";}
 if(luaL_loadstring(L,script)||lua_pcall(L,0,0,0)){fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}
 if(scene=="badguard"){lua_close(L);return 0;}
 const unsigned expected[]={1,1,1,1,1,4,4};for(unsigned i=0;i<7;++i)if(calls[i]!=expected[i]){fprintf(stderr,"method %u calls %u\n",i,calls[i]);return 2;}
 if(graphics!=1||overlays!=1||starts!=4||musicId!=4||volume!=0||std::fabs(rate-.3F)>1e-6)return 3;
 lua_getglobal(L,"c");EngineColorMod color{};if(!FillEngineColorMod(L,-1,&color))return 4;lua_pop(L,1);
 for(auto f:color.colorize)if(f!=0)return 5;
 std::uintptr_t pointer{};std::memcpy(&pointer,static_cast<unsigned char*>(wantSprite)+0x68,8);if(pointer!=0)return 6;
 if(scene=="dead"){
  RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));WriteWord(slot,0,0);
  if(luaL_dostring(L,"assert(not pcall(function()s:Reload()end));assert(not pcall(function()s:RemoveOverlay()end));assert(not pcall(function()m:Fadein(1)end))"))return 7;
  if(calls[3]!=1||calls[4]!=1||calls[5]!=4)return 8;
 }
 if(scene=="crossbase"){
  std::vector<unsigned char>changed=g_ModuleBytes;const auto base=AddressOf(changed);changed[guards::kColorSetOffsetEntry]^=1;LuaRuntime::SetEngineModuleBase(base);
  if(luaL_dostring(L,"assert(not pcall(function()c:SetOffset(1,2,3)end))"))return 9;
  if(calls[0]!=1)return 10;
 }
 lua_close(L);return 0;
}

'''
class Values7Behavior(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='api100-values-behavior-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  extra=ROOT/'runtime/src/interfaces/lua/api100_values.cpp'
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source,extra_sources=()if extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_color_sprite_music_native_effects_arguments_guards_and_lifetime(self):
  for scene in ('normal','badguard','dead','crossbase'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
class Values7Integration(Values7Behavior):
 def test_color_sprite_music_native_effects_arguments_guards_and_lifetime(self):
  r=subprocess.run([str(self.binary),'integration'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
