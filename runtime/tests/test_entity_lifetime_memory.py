"""真实Lua GC/coroutine/OOM：原生移除清理不能分配，退役不复活旧引用。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import lua_harness_objects, LUA_SOURCE_RELATIVE

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
extern "C" {
#include "lua.h"
#include "lauxlib.h"
}
#include <cassert>
#include <cstdlib>
using namespace isaac::runtime;
struct Alloc {bool fail{};unsigned denied{},attempts{};};
void* allocator(void* u,void* p,size_t,size_t n){
 auto& a=*static_cast<Alloc*>(u);
 if(n==0){std::free(p);return nullptr;}
 ++a.attempts;if(a.fail){++a.denied;return nullptr;}return std::realloc(p,n);
}
int make(lua_State* L){return PushEntityLifetimeData(L,0x1234);}
int main(){
 Alloc a;auto* L=lua_newstate(allocator,&a);assert(L);
 auto* old=PushEntityLifetimeToken(L,0x1234);const int token=lua_gettop(L);
 PushEntityLifetimeData(L,0x1234);lua_pushinteger(L,77);lua_setfield(L,-2,"value");
 const void* data=lua_topointer(L,-1);int saved=luaL_ref(L,LUA_REGISTRYINDEX);
 auto* co=lua_newthread(L);PushEntityLifetimeData(co,0x1234);
 assert(lua_topointer(co,-1)==data);lua_pop(co,1);
 lua_gc(L,LUA_GCCOLLECT,0);assert(old->alive);
 // 留足栈空间后禁用分配，Lua和native共同状态必须仍能清理。
 lua_pushcfunction(L,make);assert(lua_checkstack(L,64));int top=lua_gettop(L);
 a.fail=true;const unsigned attempts=a.attempts;
 ClearEntityLifetimeData(0x1234);RetireEntityLifetime(0x1234);
 assert(!old->alive && lua_gettop(L)==top && a.attempts==attempts);
 // 新对象token创建OOM必须由Lua保护拦下；旧身份仍然dead。
 assert(lua_pcall(L,0,1,0)==LUA_ERRMEM);assert(a.denied>0&&!old->alive);lua_pop(L,1);
 a.fail=false;
 auto* fresh=PushEntityLifetimeToken(L,0x1234);assert(fresh!=old&&fresh->alive);
 PushEntityLifetimeData(L,0x1234);assert(lua_topointer(L,-1)!=data);
 lua_rawgeti(L,LUA_REGISTRYINDEX,saved);lua_getfield(L,-1,"value");assert(lua_tointeger(L,-1)==77);
 lua_settop(L,token);luaL_unref(L,LUA_REGISTRYINDEX,saved);
 lua_gc(L,LUA_GCCOLLECT,0);assert(!old->alive);
 // 关闭前重置opaque指针，状态关闭后清理不得碰旧Lua内存。
 ResetEntityLifetimeState();lua_close(L);RetireEntityLifetime(0x1234);
 L=lua_newstate(allocator,&a);assert(L);auto* again=PushEntityLifetimeToken(L,0x1234);assert(again->alive);
 ResetEntityLifetimeState();lua_close(L);
}
'''

class EntityLifetimeMemoryTests(unittest.TestCase):
    def test_gc_coroutine_oom_and_state_reset(self):
        source = ROOT / "runtime/source"
        with tempfile.TemporaryDirectory(prefix="isaac-lifetime-memory-") as tmp:
            p=Path(tmp);(p/"test.cpp").write_text(DRIVER)
            objects=lua_harness_objects(source,p)
            command=["clang++","-std=c++23","-Wall","-Wextra","-Werror",
                     "-I",str(source),"-I",str(ROOT/"runtime/src"),
                     "-I",str(source/LUA_SOURCE_RELATIVE),str(p/"test.cpp"),
                     str(ROOT/"runtime/src/interfaces/lua/entity_lifetime.cpp"),
                     *map(str,objects),"-o",str(p/"test")]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(p/"test")],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
