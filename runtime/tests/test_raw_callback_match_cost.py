"""Production integer matcher: raw misses, live getters, GC/stack growth and OOM."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_lua_api_method_lookup_cost import function
from .test_support import lua_harness_objects

ROOT = Path(__file__).resolve().parents[2]
PREFIX = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <utility>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
#include "lobject.h"
#include "lstate.h"
#include "ltable.h"
#include "lvm.h"
}
unsigned arrayReads{}, paramReads{};
int CountGetI(lua_State* L,int i,lua_Integer key){++arrayReads;return lua_geti(L,i,key);}
int CountGetField(lua_State* L,int i,const char* key){if(!std::strcmp(key,"Param"))++paramReads;return lua_getfield(L,i,key);}
#define lua_geti CountGetI
#define lua_getfield CountGetField
'''
MAIN = r'''
#undef lua_geti
#undef lua_getfield
struct Alloc {bool deny{};unsigned denied{},attempts{};};
void* Allocate(void* context,void* block,size_t,size_t size){
 if(!size){std::free(block);return nullptr;}
 auto& a=*static_cast<Alloc*>(context);++a.attempts;
 if(a.deny){++a.denied;return nullptr;}return std::realloc(block,size);
}
int ResetReads(lua_State*){arrayReads=paramReads=0;return 0;}
int ReadCounts(lua_State*L){lua_pushinteger(L,arrayReads);lua_pushinteger(L,paramReads);return 2;}
int AllocateBig(lua_State*L){lua_newuserdata(L,65536);return 1;}
void Run(lua_State*L,const char* text){if(luaL_dostring(L,text)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));std::exit(20);}}
void PushCall(lua_State*L,const char* callbacks){lua_getglobal(L,"next_match");lua_getglobal(L,callbacks);lua_pushinteger(L,0);lua_pushinteger(L,135);}
int main(){
 Alloc a;auto*L=lua_newstate(Allocate,&a);assert(L);
 for(auto lib:{std::pair<const char*,lua_CFunction>{"_G",luaopen_base},{"table",luaopen_table},{"string",luaopen_string}}){luaL_requiref(L,lib.first,lib.second,1);lua_pop(L,1);}
 lua_pushliteral(L,"Param");lua_pushcclosure(L,NextMatchingCallback,1);lua_setglobal(L,"next_match");
 lua_pushcfunction(L,ResetReads);lua_setglobal(L,"reset_reads");lua_pushcfunction(L,ReadCounts);lua_setglobal(L,"read_counts");
 lua_pushcfunction(L,AllocateBig);lua_setglobal(L,"allocate_big");
 Run(L,R"lua(
 local cb={};for i=1,256 do cb[i]={Param=10000+i}end
 reset_reads();assert(next_match(cb,0,135)==nil)
 local arrays,params=read_counts()
 assert(arrays==1 and params==0,'integer raw misses used C API reads: '..arrays..'/'..params)
 cb[256].Param=135;reset_reads();local i,e=next_match(cb,0,135)
 assert(i==256 and e==cb[256]);arrays,params=read_counts();assert(arrays==1 and params==0)
 for _,value in ipairs({false,-1,-1.0,135.0})do cb[256].Param=value;assert(next_match(cb,0,135)==256)end
 for _,value in ipairs({'135','-1',true,{},0/0})do cb[256].Param=value;assert(next_match(cb,0,135)==nil)end
 -- Even raw Param on a proxy entry retains the ordinary C API path.
 cb={setmetatable({Param=135},{__index=function()error('not needed')end})}
 reset_reads();assert(next_match(cb,0,135)==1);arrays,params=read_counts();assert(params==1)
 -- A getter can replace itself and resize the array. Return the captured entry.
 cb={{Param=7}};local reads=0;local original
 original=setmetatable({tag='original'},{__index=function(_,k)
  assert(k=='Param');reads=reads+1
  for j=3,1500 do cb[j]={Param=999}end
  cb[2]={Param=999};cb[3]={Param=135}
  local function grow(n)if n==0 then return 0 end;return 1+grow(n-1)end
  assert(grow(100)==100);collectgarbage('collect');return reads==1 and 135 or 999
 end});cb[2]=original
 local index,entry=next_match(cb,0,135);assert(index==2 and entry==original and reads==1)
 assert(next_match(cb,index,135)==3)
 local supplied=setmetatable({},{__index=function(_,k)assert(k=='Param');collectgarbage('collect');return 135 end})
 cb=setmetatable({{Param=9}},{__index=function(_,k)if k==2 then return supplied end end})
 index,entry=next_match(cb,0,135);assert(index==2 and entry==supplied)
 local marker={};local bad={setmetatable({},{__index=function()error(marker)end})}
 local ok,err=pcall(next_match,bad,0,135);assert(not ok and err==marker)
 assert(not pcall(next_match,{false},0,135))
 local eq=0;local mt={__eq=function()eq=eq+1;return true end}
 local p=setmetatable({},mt);assert(next_match({{Param=setmetatable({},mt)}},0,p)==1 and eq==1)
 local touched=0;local proxy={setmetatable({},{__index=function()touched=touched+1;return 900 end})}
 assert(next_match(proxy,0,nil)==1 and touched==1)
 assert(next_match(proxy,0,false)==1 and touched==2)
 -- Immutable raw-path metadata is held by an upvalue, not a hot string push.
 hot={};for j=1,256 do hot[j]={Param=999}end
 oom={setmetatable({},{__index=function()allocate_big();return 135 end})}
 )lua");
 // Warm frames/stack before denying every allocator request.
 assert(lua_checkstack(L,128));PushCall(L,"hot");assert(lua_pcall(L,3,0,0)==LUA_OK);
 PushCall(L,"hot");auto attempts=a.attempts;a.deny=true;auto status=lua_pcall(L,3,0,0);a.deny=false;
 assert(status==LUA_OK&&a.attempts==attempts&&lua_gettop(L)==0);
 // A failing getter allocation must stay protected and permit the next call.
 PushCall(L,"oom");assert(lua_pcall(L,3,0,0)==LUA_OK);
 PushCall(L,"oom");a.deny=true;status=lua_pcall(L,3,0,0);a.deny=false;
 assert(status==LUA_ERRMEM&&a.denied>0);lua_pop(L,1);assert(lua_gettop(L)==0);
 PushCall(L,"oom");assert(lua_pcall(L,3,0,0)==LUA_OK&&lua_gettop(L)==0);
 std::puts("RAW_MATCH_PASS: C API miss reads=1/0, GC/stack/OOM recovery, stack=0");
 lua_close(L);
}
'''


class RawCallbackMatchTests(unittest.TestCase):
    def test_production_raw_matcher_cost_and_protected_fallbacks(self):
        source = (ROOT/'runtime/src/interfaces/lua/callback_table_api.cpp').read_text()
        body = ''
        if 'int NextMatchingCallbackGeneric(' in source:
            body += function(source, 'int NextMatchingCallbackGeneric(') + '\n'
        body += function(source, 'int NextMatchingCallback(') + '\n'
        with tempfile.TemporaryDirectory(prefix='raw-callback-match-') as tmp:
            work = Path(tmp)
            cpp = work/'raw.cpp'
            cpp.write_text(PREFIX + body + MAIN)
            objects = lua_harness_objects(ROOT/'runtime/source', work)
            binary = work/'raw'
            compiled = subprocess.run(['c++','-O2','-std=c++17',
                '-I'+str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(cpp),
                *map(str,objects),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            result = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            print(result.stdout.strip())
