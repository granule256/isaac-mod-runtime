"""Exercise the real handle recognizer, including mutable metatables and lookup cost."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from .test_support import lua_harness_objects
from .test_lua_api_method_lookup_cost import function

ROOT = Path(__file__).resolve().parents[2]


class EntityHandleLookupCostTests(unittest.TestCase):
    def test_identity_checks_remain_live_without_linear_npc_probing(self):
        source = (ROOT / 'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
        body = function(source, 'EntityHandle* TryGetEntityHandle(')
        header = (ROOT / 'runtime/source/lua_object_handles.hpp').read_text()
        names = list(dict.fromkeys(re.findall(r'kEntity\w*Metatable', body)))
        constants = '\n'.join(re.search(
            r'inline constexpr char ' + name + r'\[\] = "[^"]+";', header
        ).group() for name in names)
        prefix = r'''
#include <cstddef>
#include <cstdio>
#include <cstring>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
struct EntityHandle {void* entity;void* lifetime;};
unsigned probes{};
void* CountedTest(lua_State* L,int index,const char* name) {
 ++probes;return luaL_testudata(L,index,name);
}
#define luaL_testudata CountedTest
'''
        main = r'''
int main() {
 auto* L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);lua_checkstack(L,64);
 lua_pushvalue(L,LUA_REGISTRYINDEX);lua_setglobal(L,"registry");
 const char* names[]={NAMES};
 for(const auto* name:names){luaL_newmetatable(L,name);lua_pop(L,1);}
 for(const auto* name:names){
  auto* p=static_cast<EntityHandle*>(lua_newuserdata(L,sizeof(EntityHandle)));
  luaL_getmetatable(L,name);lua_setmetatable(L,-2);
  const int top=lua_gettop(L);
  if(TryGetEntityHandle(L,1)!=p||TryGetEntityHandle(L,-1)!=p||lua_gettop(L)!=top)return 1;
  lua_pop(L,1);
 }
 lua_pushnil(L);if(TryGetEntityHandle(L,1))return 2;lua_pop(L,1);
 lua_newtable(L);if(TryGetEntityHandle(L,1))return 3;lua_pop(L,1);
 lua_newuserdata(L,sizeof(EntityHandle));if(TryGetEntityHandle(L,1))return 4;lua_pop(L,1);
 lua_newuserdata(L,sizeof(EntityHandle));lua_newtable(L);
 lua_pushliteral(L,"IsaacRuntime.EntityNPC");lua_setfield(L,-2,"__name");lua_setmetatable(L,-2);
 if(TryGetEntityHandle(L,1))return 21;lua_pop(L,1);
 lua_pushlightuserdata(L,reinterpret_cast<void*>(1));if(TryGetEntityHandle(L,1))return 5;lua_pop(L,1);
 if(TryGetEntityHandle(nullptr,1)||TryGetEntityHandle(L,0))return 6;

 auto* p=static_cast<EntityHandle*>(lua_newuserdata(L,sizeof(EntityHandle)));
 luaL_getmetatable(L,kEntityNPCMetatable);lua_setmetatable(L,-2);
 lua_pushvalue(L,1);lua_setglobal(L,"npc");
 luaL_getmetatable(L,kEntityNPCMetatable);lua_setglobal(L,"original");
 luaL_getmetatable(L,kEntityPickupMetatable);lua_setglobal(L,"pickup");
 const auto eval=[&](const char* text){
  if(luaL_dostring(L,text)){std::fprintf(stderr,"%s",lua_tostring(L,-1));return false;}return true;
 };
 if(!eval("original.__name='renamed'"))return 7;
 if(TryGetEntityHandle(L,1)!=p)return 8;
 if(!eval("original.__name=12"))return 9;
 if(TryGetEntityHandle(L,1)!=p)return 10;
 if(!eval("original.__name='IsaacRuntime.EntityPickup'"))return 11;
 if(TryGetEntityHandle(L,1)!=p)return 12;
 if(!eval("original.__name='IsaacRuntime.EntityNPC';registry['IsaacRuntime.EntityNPC']={__name='IsaacRuntime.EntityNPC'}"))return 13;
 if(TryGetEntityHandle(L,1))return 14;
 if(!eval("registry['IsaacRuntime.EntityPickup']=original"))return 15;
 if(TryGetEntityHandle(L,1)!=p)return 16;
 if(!eval("registry['IsaacRuntime.EntityNPC']=original;registry['IsaacRuntime.EntityPickup']=pickup"))return 17;
 if(TryGetEntityHandle(L,1)!=p)return 18;
 if(!eval("savedProjectile=registry['IsaacRuntime.EntityProjectile'];registry['IsaacRuntime.EntityPickup']=nil;registry['IsaacRuntime.EntityProjectile']=nil;registryLookups=0;setmetatable(registry,{__index=function(_,k) if k=='IsaacRuntime.EntityPickup' or k=='IsaacRuntime.EntityProjectile' then registryLookups=registryLookups+1 end end})"))return 22;
 if(TryGetEntityHandle(L,1)!=p)return 23;
 if(!eval("assert(registryLookups==2);setmetatable(registry,nil);registry['IsaacRuntime.EntityPickup']=pickup;registry['IsaacRuntime.EntityProjectile']=savedProjectile"))return 24;
 lua_pop(L,1);

 for(const auto* name:{kEntityPlayerMetatable,kEntityMetatable,kEntityNPCMetatable,kEntityFamiliarMetatable}){
  auto* value=static_cast<EntityHandle*>(lua_newuserdata(L,sizeof(EntityHandle)));
  luaL_getmetatable(L,name);lua_setmetatable(L,-2);probes=0;
  if(TryGetEntityHandle(L,1)!=value||lua_gettop(L)!=1)return 19;
  const unsigned limit=!std::strcmp(name,kEntityPlayerMetatable)?1:2;
  if(probes>limit){std::fprintf(stderr,"%s needs %u metatable probes (limit %u)",name,probes,limit);return 20;}
  lua_pop(L,1);
 }
 lua_close(L);
}
'''.replace('NAMES', ','.join(names))
        with tempfile.TemporaryDirectory(prefix='entity-handle-cost-') as tmp:
            work = Path(tmp)
            cpp = work / 'check.cpp'
            cpp.write_text('#include <initializer_list>\n' + prefix + constants + '\n' + body + '\n' + main)
            objects = lua_harness_objects(ROOT / 'runtime/source', work)
            result = subprocess.run([
                'c++', '-std=c++17', '-I' + str(ROOT / 'runtime/source/third_party/lua-5.3.3/src'),
                str(cpp), *map(str, objects), '-o', str(work / 'check'),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / 'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
