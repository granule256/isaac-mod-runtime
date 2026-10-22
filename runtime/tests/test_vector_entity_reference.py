"""只读向量是实体字段活引用：变化可见、所有值运算可消费、销毁后拒绝。"""
import unittest, subprocess, tempfile
from pathlib import Path
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
HARNESS=r'''#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
static unsigned char entity[0x2fa0];
int Ref(lua_State*L){isaac::runtime::PushEntityVectorReference(L,reinterpret_cast<std::uintptr_t>(entity),0x1a04);return 1;}
int Change(lua_State*){float v[2]={4,5};memcpy(entity+0x1a04,v,8);return 0;}
int Retire(lua_State*){isaac::runtime::RetireEntityLifetime(reinterpret_cast<std::uintptr_t>(entity));return 0;}
int main(){auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);auto base=std::uintptr_t(0x10000000);LuaRuntime::SetEngineModuleBase(base);auto vt=base+kEntityPlayerVtableOffset;memcpy(entity,&vt,8);entity[kEntityExistsOffset]=1;unsigned type=1;memcpy(entity+kEntityTypeOffset,&type,4);float start[2]={1,2};memcpy(entity+0x1a04,start,8);
 isaac::runtime::RegisterVectorReferenceMetatable(L);
 luaL_newmetatable(L,LuaRuntime::kVectorMetatable);lua_pushcfunction(L,isaac::runtime::VectorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,isaac::runtime::VectorNewIndex);lua_setfield(L,-2,"__newindex");lua_pushcfunction(L,isaac::runtime::VectorAdd);lua_setfield(L,-2,"__add");lua_newtable(L);static_cast<void>(isaac::runtime::AttachVectorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 for(auto pair:{std::pair<const char*,lua_CFunction>{"getref",Ref},{"change",Change},{"retire",Retire},{"Vector",isaac::runtime::CreateVectorHandle}}){lua_pushcfunction(L,pair.second);lua_setglobal(L,pair.first);}
 const char* s=R"lua(local v=getref();assert(v.X==1 and v.Y==2);change();assert(v.X==4 and v.Y==5);local q=Vector(1,2)+v;assert(q.X==5 and q.Y==7);assert(Vector(4,5):Distance(v)==0);assert(v:LengthSquared()==41);assert(not pcall(function()v.X=0 end));assert(not pcall(function()v:Normalize()end));retire();assert(not pcall(function()return v.X end));assert(not pcall(function()return Vector(1,2)+v end)))lua";
 if(luaL_dostring(L,s)){fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}lua_close(L);isaac::runtime::ResetEntityLifetimeState();return 0;
}'''
class ReferenceVectorTests(unittest.TestCase):
 def test_live_readonly_arithmetic_and_lifetime(self):
  with tempfile.TemporaryDirectory(prefix='isaac-vector-ref-') as d:
   exe=build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(d),harness_source=HARNESS)
   r=subprocess.run([str(exe)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
