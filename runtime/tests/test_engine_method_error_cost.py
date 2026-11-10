"""Compile the production method prologue: diagnostic names cost nothing on success."""
from pathlib import Path
import subprocess,tempfile,unittest
from .test_lua_api_method_lookup_cost import function
from .test_support import lua_harness_objects,LUA_SOURCE_RELATIVE
ROOT=Path(__file__).resolve().parents[2];SOURCE=ROOT/'runtime/source'
class EngineMethodErrorCost(unittest.TestCase):
 def test_success_does_not_search_catalog_and_errors_keep_names(self):
  body=function((ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text(),'int EngineMethodHandler(')
  body=body[:body.index('    // 接收者：')]+ '\n return 0;\n}\n'
  code=r'''
#include <cstdint>
#include <cstddef>
#include <cassert>
#include <cstring>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
}
struct LuaApiDescriptor{const char*owner;const char*name;};
struct EngineMethodRow{unsigned id;unsigned probeBit;unsigned shape;unsigned argumentCount;};
struct EngineCallShapeRow{unsigned argumentCount;};
static unsigned lookups{};
static const LuaApiDescriptor* FindLuaApiDescriptor(unsigned){++lookups;static LuaApiDescriptor d{"TemporaryEffects","HasCollectibleEffect"};return &d;}
void RecordApiSequenceSecondary(unsigned){}
namespace isaac::runtime{void RecordEngineRowCall(unsigned){}void InvalidateCurrentRoomCache(){}}
const EngineCallShapeRow* EngineCallShapeRows(std::size_t*n){*n=1;static EngineCallShapeRow s{1};return &s;}
''' + body + r'''
int main(){auto*L=luaL_newstate();EngineMethodRow row{0xe0100fa,255,0,1};
 auto call=[&]{lua_pushlightuserdata(L,&row);lua_pushcclosure(L,EngineMethodHandler,1);return lua_pcall(L,0,0,0);};
 for(int i=0;i<1000;++i)assert(call()==LUA_OK);
 assert(lookups==0&&"valid native method scans API catalog for unused error text");
 row.shape=1;assert(call()!=LUA_OK);assert(lookups==1);assert(std::strstr(lua_tostring(L,-1),"TemporaryEffects:HasCollectibleEffect has an unsupported call shape"));lua_pop(L,1);
 row.shape=0;row.argumentCount=2;assert(call()!=LUA_OK);assert(lookups==2);assert(std::strstr(lua_tostring(L,-1),"TemporaryEffects:HasCollectibleEffect row and call shape disagree"));
 lua_close(L);}
'''
  with tempfile.TemporaryDirectory()as td:
   p=Path(td);(p/'p.cpp').write_text(code);objs=lua_harness_objects(SOURCE,p)
   c=subprocess.run(['c++','-std=c++23','-I',str(SOURCE/LUA_SOURCE_RELATIVE),str(p/'p.cpp'),*map(str,objs),'-o',str(p/'p')],capture_output=True,text=True);self.assertEqual(c.returncode,0,c.stderr)
   r=subprocess.run([str(p/'p')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
