"""执行生产输入函数的完整早退路径：不支持的键码保留false且不刷新快照。"""
from pathlib import Path
import subprocess,tempfile,unittest
from .test_support import lua_harness_objects
from .test_lua_api_method_lookup_cost import function
ROOT=Path(__file__).resolve().parents[2]
class UnsupportedQueryCostTests(unittest.TestCase):
 def test_keyboard_queries_validate_but_skip_snapshot_refresh(self):
  source=(ROOT/'runtime/src/interfaces/lua/input_api.cpp').read_text()
  prefix=function(source,'int InputIsButtonTriggered(lua_State* state) {').split('const ResolvedInputDevice target',1)[0]+'lua_pushboolean(state,0);return 1;}\n'
  helper=function(source,'void CheckInputButtonArguments(') if 'void CheckInputButtonArguments(' in source else function(source,'InputButtonArguments CheckInputButtonArguments(')
  body=r'''
#include "interfaces/lua/lua_integer_argument.hpp"
#include <cstdio>
extern "C" {
#include "lauxlib.h"
}
int refreshes=0;void RefreshInputSnapshot(){++refreshes;}
namespace console{bool ConsoleCapturesInput(){return false;}}
constexpr unsigned kKageControllerButtonMaximum=17;
struct InputButtonArguments{lua_Integer code;lua_Integer controller;};
'''+helper+function(source,'bool IsControllerButtonCode(')+prefix+r'''
int main(){auto*L=luaL_newstate();lua_pushcfunction(L,InputIsButtonTriggered);lua_setglobal(L,"query");
 for(const char*s:{"return query(32,0)","return query(400,4)","return query(32.0,'0',1.0)","return query(-1,0)"}){
  lua_settop(L,0);refreshes=0;if(luaL_loadstring(L,s)||lua_pcall(L,0,1,0)||lua_type(L,-1)!=LUA_TBOOLEAN||lua_toboolean(L,-1))return 2;
  if(refreshes){std::fprintf(stderr,"unsupported key refreshed snapshot %d times",refreshes);return 1;}
 }
 for(const char*s:{"return query(32,0.5)","return query(32,0,true)","return query(32)","return query(1.5,0)"}){
  lua_settop(L,0);refreshes=0;if(luaL_loadstring(L,s)||lua_pcall(L,0,1,0)==LUA_OK||refreshes)return 3;
 }
 lua_settop(L,0);refreshes=0;if(luaL_loadstring(L,"return query(13,1)")||lua_pcall(L,0,1,0)||refreshes!=1)return 4;
 lua_close(L);return 0;}
'''
  body=body.replace('#include <cstdio>','#include <cstdio>\n#include <initializer_list>')
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp);objects=lua_harness_objects(ROOT/'runtime/source',p);(p/'h.cpp').write_text(body)
   r=subprocess.run(['c++','-std=c++17','-I'+str(ROOT/'runtime/src'),'-I'+str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(p/'h.cpp'),*[str(o)for o in objects],'-o',str(p/'h')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'h')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
