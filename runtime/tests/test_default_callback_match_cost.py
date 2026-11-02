"""Actual bootstrap must inline its default matcher and retain custom semantics."""
from pathlib import Path
import subprocess,tempfile,unittest
from .test_support import lua_harness_objects
ROOT=Path(__file__).resolve().parents[2]
DRIVER=r'''
#include "program/callback_bootstrap.hpp"
#include <cstdio>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
int matchref=0;unsigned calls=0;
void hook(lua_State*L,lua_Debug*ar){lua_getinfo(L,"f",ar);lua_rawgeti(L,LUA_REGISTRYINDEX,matchref);if(lua_rawequal(L,-1,-2))++calls;lua_pop(L,2);}
int noop(lua_State*){return 0;}
int invoke(lua_State*L){int n=lua_gettop(L);lua_getfield(L,2,"Function");lua_getfield(L,2,"Mod");for(int i=3;i<=n;++i)lua_pushvalue(L,i);lua_call(L,n-1,1);return 1;}
int ownermatches(lua_State*L){lua_getfield(L,1,"id");lua_pushboolean(L,lua_tointeger(L,-1)==lua_tointeger(L,2));return 1;}
bool run(lua_State*L,const char*s){if(luaL_dostring(L,s)){std::fprintf(stderr,"%s",lua_tostring(L,-1));return false;}return true;}
int main(){
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,"table",luaopen_table,1);lua_pop(L,1);
 if(!run(L,"Isaac={SetBuiltInCallbackState=function()end};CallbackPriority={DEFAULT=0};ModCallbacks={MC_PRE_MOD_UNLOAD=79};debug={getinfo=function()return{name='test'}end}"))return 1;
 const auto&s=isaac::runtime::kPcCallbackBootstrap;if(luaL_loadbuffer(L,s,sizeof(s)-1,"@pc/callbacks.lua"))return 2;
 lua_pushcfunction(L,invoke);lua_pushcfunction(L,noop);lua_pushcfunction(L,ownermatches);if(lua_pcall(L,3,4,0))return 3;
 lua_setglobal(L,"owner_run");lua_settop(L,0);
 if(!run(L,"m={id=2};for i=1,132 do Isaac.AddCallback(m,0,function()end,i<=11 and 160 or 200+i)end;expected=getmetatable(Isaac.GetCallbacks(0)).__matchParams"))return 4;
 lua_getglobal(L,"expected");matchref=luaL_ref(L,LUA_REGISTRYINDEX);lua_sethook(L,hook,LUA_MASKCALL,0);
 if(!run(L,"Isaac.RunCallbackWithParam(0,160)"))return 5;lua_sethook(L,nullptr,0,0);
 if(calls){std::fprintf(stderr,"default matcher called %u times",calls);return 6;}
 const char*checks=R"lua(
local values={{},{false},{true},{-1},{0},{1},{160},{'160'}}
for _,a in ipairs(values)do for _,b in ipairs(values)do
 local count=0;Isaac.GetCallbacks(3,true)[1]={Mod=m,Param=b[1],Function=function()count=count+1 end}
 Isaac.RunCallbackWithParam(3,a[1]);assert(count==(expected(a[1],b[1])and 1 or 0))
end end
local t=Isaac.GetCallbacks(4,true);local reads=0
t[1]=setmetatable({Mod=m,Function=function()return false end},{__index=function(_,k)if k=='Param'then reads=reads+1 end end})
assert(Isaac.RunCallbackWithParam(4,160)==false and reads==1)
local mt=getmetatable(t);mt.__matchParams=function()return false end
assert(Isaac.RunCallbackWithParam(4,160)==nil and reads==2);mt.__matchParams=expected
local err={};setmetatable(t[1],{__index=function(_,k)if k=='Param'then error(err)end end})
assert(owner_run(4,nil,1)==nil);local ok,e=pcall(owner_run,4,nil,2);assert(not ok and e==err)
local list=Isaac.GetCallbacks(5,true);local count=0
list[1]={Mod=m,Function=function()list[2].Param=160;list[2].Function=function()count=count+7 end end}
list[2]={Mod=m,Param=200,Function=function()count=count+1 end};Isaac.RunCallbackWithParam(5,160);assert(count==7)
)lua";
 if(!run(L,checks))return 7;lua_close(L);return 0;
}
'''
class DefaultCallbackMatchTests(unittest.TestCase):
 def test_default_match_cost_and_shared_custom_match_behavior(self):
  with tempfile.TemporaryDirectory(prefix='callback-matcher-')as tmp:
   p=Path(tmp);cpp=p/'matcher.cpp';cpp.write_text(DRIVER);objects=lua_harness_objects(ROOT/'runtime/source',p)
   r=subprocess.run(['c++','-std=c++17','-I'+str(ROOT/'runtime/source'),'-I'+str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(cpp),*[str(x)for x in objects],'-o',str(p/'matcher')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'matcher')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
