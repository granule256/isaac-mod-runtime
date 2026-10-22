"""真实Lua字符串消费、AArch64非平凡返回与引擎堆释放边界。"""
import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
MAIN=r'''
#include "interfaces/lua/api100_strings.hpp"
#include "interfaces/lua/api100_strings.guards.hpp"
#include "lua_object_handles.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
#include <cstdlib>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static unsigned nameCalls{},curseCalls{},allocs{},frees{};
static unsigned mode{};static bool failAlloc{};
static void Delete(void*p){assert(p);++frees;std::free(p);}
static Api100NativeString String(const char*text,std::size_t length){
 Api100NativeString result;
 if(length<=22){result.bytes[0]=static_cast<unsigned char>(length<<1);std::memcpy(result.bytes+1,text,length);}
 else{void*p=std::malloc(length+1);assert(p);++allocs;std::memcpy(p,text,length);static_cast<char*>(p)[length]=0;result.bytes[0]=1;std::uint64_t n=length;std::memcpy(result.bytes+8,&n,8);std::memcpy(result.bytes+16,&p,8);}
 return result;
}
static Api100NativeString Name(void*p){
 assert(p==g_GameBytes.data());++nameCalls;
 if(mode==1)return String("",0);
 if(mode==2)return String("A\0B",3);
 if(mode==3){const char*t="A native long string for invalid length testing";auto s=String(t,std::strlen(t));std::uint64_t n=4097;std::memcpy(s.bytes+8,&n,8);return s;}
 if(mode==4){char text[2048];std::memset(text,'Q',sizeof(text));auto s=String(text,sizeof(text));failAlloc=true;return s;}
 return String("#BASEMENT",9);
}
static Api100NativeString Curse(void*p){assert(p==g_GameBytes.data());++curseCalls;const char*text="Curse name supplied by a custom mod, including UTF-8: \xe8\xbf\xb7\xe9\x9b\xbe";return String(text,std::strlen(text));}
static void* Alloc(void*,void*p,std::size_t,std::size_t n){if(!n){std::free(p);return nullptr;}if(failAlloc)return nullptr;return std::realloc(p,n);}
int main(){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 namespace guards=api100_strings;
 std::memcpy(g_ModuleBytes.data()+guards::kGetNameEntry,guards::kGetNameGuard.data(),16);std::memcpy(g_ModuleBytes.data()+guards::kGetCurseNameEntry,guards::kGetCurseNameGuard.data(),16);
 LuaRuntime::LuaSpriteBindings binding{};binding.gameOperatorDelete=&Delete;LuaRuntime::SetSpriteBindings(binding);
 SetApi100StringNativeTestBindings({engine_call::AddressOfFunction(&Name),engine_call::AddressOfFunction(&Curse)});
 const char*script=R"LUA(local level=Game():GetLevel();assert(level:GetName()=="#BASEMENT");for i=1,1000 do assert(level:GetCurseName()=="Curse name supplied by a custom mod, including UTF-8: 迷雾")end)LUA";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@strings2.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 std::fprintf(stderr,"step integration %u %u %u %u\n",nameCalls,curseCalls,allocs,frees);assert(nameCalls==1&&curseCalls==1000&&allocs==1000&&frees==1000);
 // Direct consumer exercises error/unwind behavior independently of runtime script loading.
 auto*L=lua_newstate(Alloc,nullptr);luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kLevelMetatable);lua_pop(L,1);
 auto call=[&](lua_CFunction fn){lua_pushcfunction(L,fn);lua_newuserdata(L,1);luaL_getmetatable(L,LuaRuntime::kLevelMetatable);lua_setmetatable(L,-2);return lua_pcall(L,1,1,0);};
 std::fprintf(stderr,"step empty\n");mode=1;assert(call(Api100LevelGetName)==LUA_OK);std::size_t n=99;assert(lua_tolstring(L,-1,&n)&&n==0);lua_pop(L,1);
 std::fprintf(stderr,"step nul\n");mode=2;assert(call(Api100LevelGetName)==LUA_OK);const char*value=lua_tolstring(L,-1,&n);assert(n==3&&!std::memcmp(value,"A\0B",3));lua_pop(L,1);
 std::fprintf(stderr,"step invalid\n");mode=3;assert(call(Api100LevelGetName)!=LUA_OK);assert(allocs==frees);lua_pop(L,1);
 const auto before=nameCalls;LuaRuntime::SetSpriteBindings({});assert(call(Api100LevelGetName)!=LUA_OK);assert(nameCalls==before);lua_pop(L,1);LuaRuntime::SetSpriteBindings(binding);
 std::fprintf(stderr,"step oom\n");mode=4;assert(call(Api100LevelGetName)==LUA_ERRMEM);failAlloc=false;lua_settop(L,0);lua_gc(L,LUA_GCCOLLECT,0);assert(allocs==frees);
 // Cross-module cache is invalidated, refusing both methods before allocating.
 std::fprintf(stderr,"step crossbase\n");std::vector<unsigned char> second=g_ModuleBytes;std::memset(second.data()+guards::kGetNameEntry,0,16);std::memset(second.data()+guards::kGetCurseNameEntry,0,16);auto newBase=AddressOf(second);LuaRuntime::SetEngineModuleBase(newBase);
 assert(call(Api100LevelGetName)!=LUA_OK);lua_pop(L,1);assert(call(Api100LevelGetCurseName)!=LUA_OK);lua_pop(L,1);
 assert(nameCalls==before+1&&allocs==frees);
 lua_close(L);return 0;
}
'''
class String2Behavior(unittest.TestCase):
 def test_strings_short_long_empty_nul_invalid_oom_and_crossbase(self):
  prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
  prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
  with tempfile.TemporaryDirectory(prefix='api100-strings-')as d:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+MAIN)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
