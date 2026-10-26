"""原生对象身份登记的独立Lua合约：别名/自有值/失效/索引/栈/零分配。

只链接Lua和object_identity_registry.cpp，不加载既有运行时/族解析器。
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import cached_compile, lua_harness_objects, LUA_SOURCE_RELATIVE

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'runtime/source'
MODULE = ROOT/'runtime/src/interfaces/lua/object_identity_registry.cpp'
MAIN = r'''
#include "interfaces/lua/object_identity_registry.hpp"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
using namespace isaac::runtime;
struct Allocator{unsigned calls{},allocations{},frees{};};
static void* Allocate(void*context,void*old,std::size_t,std::size_t size){auto&a=*static_cast<Allocator*>(context);++a.calls;if(!size){++a.frees;std::free(old);return nullptr;}++a.allocations;return std::realloc(old,size);}
struct Native{int value;};struct Owner{bool alive;};struct Borrow{Owner*owner;Native*object;};struct Owned{Native value;};
static unsigned borrowedCalls{},ownedCalls{},wrongCalls{},luaCalls{};
static std::uintptr_t Borrowed(lua_State*L,int index)noexcept{++borrowedCalls;auto*b=static_cast<Borrow*>(lua_touserdata(L,index));return b&&b->owner->alive?reinterpret_cast<std::uintptr_t>(b->object):0;}
static std::uintptr_t OwnedValue(lua_State*L,int index)noexcept{++ownedCalls;auto*o=static_cast<Owned*>(lua_touserdata(L,index));const auto result=reinterpret_cast<std::uintptr_t>(&o->value);lua_pushinteger(L,9123);return result;}
static std::uintptr_t Wrong(lua_State*,int)noexcept{++wrongCalls;return 0xbad;}
static int LuaTrap(lua_State*){++luaCalls;return 0;}
static void Trap(lua_State*L,int table){lua_newtable(L);lua_pushcfunction(L,LuaTrap);lua_setfield(L,-2,"__index");lua_pushcfunction(L,LuaTrap);lua_setfield(L,-2,"__newindex");lua_setmetatable(L,table);}
static void Register(lua_State*L,int index,NativeObjectIdentityResolver fn,bool want){const int top=lua_gettop(L);assert(RegisterNativeObjectIdentity(L,index,fn)==want);assert(lua_gettop(L)==top);}
static std::uintptr_t Resolve(lua_State*L,int index,bool recognized){const int top=lua_gettop(L);bool known=!recognized;const auto result=ResolveRegisteredObjectIdentity(L,index,&known);assert(known==recognized);assert(lua_gettop(L)==top);return result;}
int main(){
 static_assert(noexcept(RegisterNativeObjectIdentity(nullptr,0,nullptr)));static_assert(noexcept(ResolveRegisteredObjectIdentity(nullptr,0,nullptr)));
 Allocator allocation{};auto*L=lua_newstate(Allocate,&allocation);assert(L);assert(lua_checkstack(L,80));
 lua_pushinteger(L,777);lua_createtable(L,0,4);const int borrowedMeta=lua_gettop(L);Trap(L,borrowedMeta);
 const auto startAllocations=allocation.allocations;Register(L,-1,Borrowed,true);assert(allocation.allocations==startAllocations+1);std::printf("registry preallocated-table registration allocations=%u (one payload)\n",allocation.allocations-startAllocations);
 const auto registeredAllocations=allocation.allocations;Register(L,borrowedMeta,Borrowed,true);Register(L,borrowedMeta,Wrong,false);Register(L,borrowedMeta,nullptr,false);assert(allocation.allocations==registeredAllocations);
 // 元表唯一私有lightuserdata键，值为恰好sizeof(function pointer)的userdata，不转换函数指针。
 unsigned registrations=0;lua_pushnil(L);while(lua_next(L,borrowedMeta)){assert(lua_type(L,-2)==LUA_TLIGHTUSERDATA&&lua_type(L,-1)==LUA_TUSERDATA);assert(lua_rawlen(L,-1)==sizeof(NativeObjectIdentityResolver));NativeObjectIdentityResolver stored{};std::memcpy(&stored,lua_touserdata(L,-1),sizeof(stored));assert(stored==Borrowed);++registrations;lua_pop(L,1);}assert(registrations==1);
 Owner owner{true};Native native{42};
 auto*one=static_cast<Borrow*>(lua_newuserdata(L,sizeof(Borrow)));*one={&owner,&native};lua_pushvalue(L,borrowedMeta);lua_setmetatable(L,-2);const int aliasOne=lua_gettop(L);
 auto*two=static_cast<Borrow*>(lua_newuserdata(L,sizeof(Borrow)));*two={&owner,&native};lua_pushvalue(L,borrowedMeta);lua_setmetatable(L,-2);const int aliasTwo=lua_gettop(L);
 assert(one!=two);assert(Resolve(L,aliasOne,true)==reinterpret_cast<std::uintptr_t>(&native));assert(Resolve(L,-1,true)==reinterpret_cast<std::uintptr_t>(&native));
 lua_pushinteger(L,111);lua_pushinteger(L,222);assert(Resolve(L,aliasOne-lua_gettop(L)-1,true)==reinterpret_cast<std::uintptr_t>(&native));lua_pop(L,2);
 assert(ResolveRegisteredObjectIdentity(L,aliasOne,nullptr)==Resolve(L,aliasTwo,true));
 owner.alive=false;assert(Resolve(L,aliasOne,true)==0&&Resolve(L,aliasTwo,true)==0);owner.alive=true;
 lua_newtable(L);const int ownedMeta=lua_gettop(L);Trap(L,ownedMeta);Register(L,-1,OwnedValue,true);
 auto*valueOne=static_cast<Owned*>(lua_newuserdata(L,sizeof(Owned)));valueOne->value.value=5;lua_pushvalue(L,ownedMeta);lua_setmetatable(L,-2);const int ownedOne=lua_gettop(L);
 auto*valueTwo=static_cast<Owned*>(lua_newuserdata(L,sizeof(Owned)));valueTwo->value.value=5;lua_pushvalue(L,ownedMeta);lua_setmetatable(L,-2);const int ownedTwo=lua_gettop(L);
 const auto first=Resolve(L,ownedOne,true),second=Resolve(L,-1,true);assert(first==reinterpret_cast<std::uintptr_t>(&valueOne->value)&&second==reinterpret_cast<std::uintptr_t>(&valueTwo->value)&&first!=second);
 // 解析器自己留下临时值也由入口恢复；规范化后的index不能指向元表/私有payload。
 assert(Resolve(L,ownedOne-lua_gettop(L)-1,true)==first);
 const auto beforeUnknownBorrowed=borrowedCalls,beforeUnknownOwned=ownedCalls;
 lua_newuserdata(L,1);assert(Resolve(L,-1,false)==0);lua_pop(L,1);
 lua_newuserdata(L,1);lua_newtable(L);Trap(L,lua_gettop(L));lua_setmetatable(L,-2);assert(Resolve(L,-1,false)==0);lua_pop(L,1);
 lua_newtable(L);lua_pushvalue(L,borrowedMeta);lua_setmetatable(L,-2);assert(Resolve(L,-1,false)==0);Register(L,-1,nullptr,false);lua_pop(L,1);
 lua_pushlightuserdata(L,&native);assert(Resolve(L,-1,false)==0);Register(L,-1,Borrowed,false);lua_pop(L,1);
 lua_pushnil(L);assert(Resolve(L,-1,false)==0);Register(L,-1,Borrowed,false);lua_pop(L,1);
 assert(Resolve(L,0,false)==0);assert(Resolve(L,99999,false)==0);Register(L,0,Borrowed,false);Register(L,99999,Borrowed,false);
 assert(borrowedCalls==beforeUnknownBorrowed&&ownedCalls==beforeUnknownOwned&&wrongCalls==0&&luaCalls==0);
 // 另一个Lua状态没有全局类型缓存；它自己的登记完全独立，关闭后不留地址缓存。
 Allocator otherAllocator{};auto*other=lua_newstate(Allocate,&otherAllocator);assert(other);assert(lua_checkstack(other,20));lua_newuserdata(other,1);lua_newtable(other);lua_setmetatable(other,-2);assert(Resolve(other,-1,false)==0);lua_newtable(other);const auto emptyStart=otherAllocator.allocations;Register(other,-1,Borrowed,true);const auto emptyAllocations=otherAllocator.allocations-emptyStart;assert(emptyAllocations>=1);std::printf("registry empty-table registration allocations=%u (payload + Lua table storage)\n",emptyAllocations);lua_close(other);
 // API调用前预留栈，关闭GC避免测试框架引入干扰：10k次双解析不准触碰allocator。
 lua_gc(L,LUA_GCSTOP,0);assert(lua_checkstack(L,80));const auto beforeCalls=allocation.calls;const int top=lua_gettop(L);
 for(unsigned i=0;i<10000;++i){assert(Resolve(L,aliasOne,true)==reinterpret_cast<std::uintptr_t>(&native));assert(Resolve(L,ownedTwo,true)==second);}
 assert(allocation.calls==beforeCalls&&lua_gettop(L)==top&&wrongCalls==0&&luaCalls==0);std::printf("registry warmed resolution allocator calls=%u\n",allocation.calls-beforeCalls);
 owner.alive=false;assert(Resolve(L,aliasOne,true)==0);assert(Resolve(L,ownedOne,true)==first);
 lua_close(L);std::puts("registry: aliases, owned values, lifetime, unknown, registration, stack and 20000 zero-allocation lookups OK");return 0;
}
'''


class ObjectIdentityRegistryTests(unittest.TestCase):
    def test_real_lua_identity_registry_contract(self):
        with tempfile.TemporaryDirectory(prefix='object-identity-registry-') as d:
            work=Path(d);harness=work/'harness.cpp';harness.write_text(MAIN)
            lua=SOURCE/LUA_SOURCE_RELATIVE
            includes=(str(ROOT/'runtime/src'),str(lua))
            flags=('-std=c++17','-Wall','-Wextra','-Werror','-DLUA_C89_NUMBERS')
            objects=[cached_compile(p,tool='c++',flags=flags,includes=includes) for p in (harness,MODULE)]
            objects+=lua_harness_objects(SOURCE,work)
            binary=work/'registry'
            build=subprocess.run(['c++',*map(str,objects),'-lm','-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            print(result.stdout+result.stderr,flush=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
