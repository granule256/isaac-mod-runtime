"""PC选项实际字段，验证公共访问没有落成Lua影子键。"""
import unittest
from .test_api400_params import run_main
MAIN=r'''
#include "interfaces/lua/api700_options.hpp"
#include "interfaces/lua/api700_world.guards.hpp"
#include "interfaces/lua/api700_options.guards.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
#include <cstdio>
#include <cstring>
using namespace isaac::runtime;
template<class T>T ReadAtOpt(const void*p,unsigned o){T v{};std::memcpy(&v,static_cast<const char*>(p)+o,sizeof(v));return v;}
static unsigned musicCalls{},soundCalls{};
static void Music(void*p,float value){++musicCalls;std::memcpy(static_cast<char*>(p)+0x18,&value,4);}
static void Sound(void*p,float value){++soundCalls;std::memcpy(static_cast<char*>(p)+0x1c,&value,4);}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
std::vector<unsigned char> manager(0x36600),slot(8);WriteWord(slot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(slot));
for(const auto&g:api700_options::kGuards)std::memcpy(g_ModuleBytes.data()+g.offset,g.bytes.data(),16);
WriteAt<float>(manager,0x364f0,.3F);WriteAt<float>(manager,0x364f8,1.F);WriteAt<std::int32_t>(manager,0x3650c,1);
std::vector<unsigned char> curses(96);std::string longName(300,'x');WriteAt<std::int32_t>(curses,0,1);curses[8]=16;std::memcpy(curses.data()+9,"Darkness",8);WriteAt<std::int32_t>(curses,32,2);curses[40]=16;std::memcpy(curses.data()+41,"Darkness",8);WriteAt<std::int32_t>(curses,64,7);WriteAt<std::uint64_t>(curses,72,301);WriteAt<std::uint64_t>(curses,80,300);WriteWord(curses,88,reinterpret_cast<std::uintptr_t>(longName.data()));WriteWord(manager,0x24078,AddressOf(curses));WriteWord(manager,0x24080,AddressOf(curses)+96);
for(const auto&g:api700_world::kGuards)std::memcpy(g_ModuleBytes.data()+g.offset,g.bytes.data(),16);
SetApi700OptionNativeTestBindings(engine_call::AddressOfFunction(&Music),engine_call::AddressOfFunction(&Sound));
const char*script=R"lua(
local missing={};for _,name in ipairs({'MusicVolume','SFXVolume','MapOpacity','Filter','Gamma','DisplayPopups','CameraStyle','ExtraHUDStyle','RumbleEnabled','ChargeBars','BulletVisibility'})do if Options[name]==nil then missing[#missing+1]=name end end
assert(#missing==0,table.concat(missing,','))
assert(Isaac.GetCurseIdByName('Darkness')==2 and Isaac.GetCurseIdByName(string.rep('x',300))==7 and Isaac.GetCurseIdByName('darkness')==-1 and Isaac.GetCurseIdByName('')==-1)
assert(not pcall(function()Isaac.GetCurseIdByName({})end))
assert(Options.MapOpacity>.29 and Options.MapOpacity<.31 and Options.Gamma==1 and Options.CameraStyle==1)
for _,name in ipairs({'MusicVolume','SFXVolume','MapOpacity'})do
 Options[name]=.005;assert(Options[name]>.0049 and Options[name]<.0051)
 Options[name]=2;assert(Options[name]>.0099 and Options[name]<.0101)
 Options[name]=-1;assert(Options[name]==0)
 assert(not pcall(function()Options[name]={}end));assert(rawget(Options,name)==nil)
end
Options.Gamma=-1;assert(Options.Gamma==.5);Options.Gamma=9;assert(Options.Gamma==1.5);Options.Gamma=1.25;assert(Options.Gamma==1.25)
Options.CameraStyle=-1;assert(Options.CameraStyle==1);Options.CameraStyle=9;assert(Options.CameraStyle==2);Options.CameraStyle=0x100000002;assert(Options.CameraStyle==2)
Options.ExtraHUDStyle=-1;assert(Options.ExtraHUDStyle==0);Options.ExtraHUDStyle=9;assert(Options.ExtraHUDStyle==2)
assert(not pcall(function()Options.CameraStyle=1.5 end))
for _,name in ipairs({'Filter','DisplayPopups','RumbleEnabled','ChargeBars','BulletVisibility'})do Options[name]=0;assert(Options[name]==true);Options[name]=false;assert(Options[name]==false);assert(rawget(Options,name)==nil)end
)lua";
if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api700-options.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::fprintf(stderr,"%s\n",e[i].text);return 1;}
assert(musicCalls==3&&soundCalls==3);assert(ReadAtOpt<float>(manager.data(),0x364e8)==0.F);assert(ReadAtOpt<float>(manager.data(),0x364f0)==0.F);assert(ReadAtOpt<float>(manager.data(),0x364f8)==1.25F);
WriteAt<float>(manager,0x364f0,.75F);
auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterOptionsTable(L));
if(luaL_dostring(L,"assert(Options.MapOpacity==.75)")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 2;}
std::vector<unsigned char>other=g_ModuleBytes;other[api700_options::kGuards[0].offset]^=1;LuaRuntime::SetEngineModuleBase(AddressOf(other));
if(luaL_dostring(L,"local ok,e=pcall(function()return Options.MapOpacity end);assert(not ok and string.find(e,'guard'),tostring(e));local ok2=pcall(function()Options.Filter=true end);assert(not ok2)")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 3;}
LuaRuntime::SetEngineModuleBase(g_EngineBase);WriteWord(slot,0,0);
if(luaL_dostring(L,"local ok,e=pcall(function()return Options.ChargeBars end);assert(not ok and string.find(e,'unavailable'),tostring(e))")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 4;}
lua_close(L);return 0;}
'''
class OptionsConsumer(unittest.TestCase):
 def test_public_native_options(self):
  r=run_main(MAIN);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
