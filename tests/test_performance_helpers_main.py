"""Standalone addon control: optional dependency, toggling and owned unload."""
from pathlib import Path
import subprocess,tempfile,unittest
from runtime.tests.test_support import lua_harness_objects,LUA_SOURCE_RELATIVE
ROOT=Path(__file__).resolve().parents[1]
MOD=ROOT/'mods/isaac_performance_helpers'
PRELUDE=r'''
ModCallbacks={MC_POST_GAME_STARTED=15,MC_PRE_MOD_UNLOAD=73}
local callbacks={}
RegisterMod=function()local m={};function m:AddCallback(id,fn)callbacks[id]=fn end;return m end
local original=function()return 'original' end
local FF={GetRoomEntities=original};local fake={}
function fake.attach(ff)
 if not ff then return nil,'not_loaded' end
 local p={};local active=false;local wrapper=function()return 'optimized' end
 function p.enable()if ff.GetRoomEntities~=original and ff.GetRoomEntities~=wrapper then return false end;ff.GetRoomEntities=wrapper;active=true;return true end
 function p.disable()if ff.GetRoomEntities==wrapper then ff.GetRoomEntities=original end;active=false end
 function p.status()return {enabled=active,applied=active and ff.GetRoomEntities==wrapper}end
 return p
end
include=function()return fake end
__callbacks=callbacks;__ff=FF;__original=original
'''
DRIVER=r'''
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
int main(int argc,char**argv){if(argc!=2)return 90;auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,"table",luaopen_table,1);lua_pop(L,1);std::ifstream f(argv[1]);std::string s{std::istreambuf_iterator<char>(f),{}};if(luaL_loadbuffer(L,s.data(),s.size(),"addon-control")||lua_pcall(L,0,0,0)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}lua_close(L);}
'''
class AddonMainTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.work=Path(cls.tmp.name);objects=lua_harness_objects(ROOT/'runtime/source',cls.work);p=cls.work/'driver.cpp';p.write_text(DRIVER);cls.bin=cls.work/'test';r=subprocess.run(['c++','-std=c++17','-I'+str(ROOT/'runtime/source'/LUA_SOURCE_RELATIVE),str(p),*[str(x)for x in objects],'-o',str(cls.bin)],capture_output=True,text=True);assert r.returncode==0,r.stderr
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_case(self,body):
  source=(MOD/'main.lua').read_text()if(MOD/'main.lua').exists()else''
  p=self.work/'case.lua';p.write_text(PRELUDE+'\n'+source+'\nassert(IsaacPerformanceHelpers,"addon control was not installed")\n'+body);r=subprocess.run([str(self.bin),str(p)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
 def test_optional_dependency_and_toggle(self):
  self.run_case('''
assert(IsaacPerformanceHelpers:GetStatus().enabled)
__callbacks[15]()
FiendFolio=__ff;__callbacks[15]()
assert(__ff.GetRoomEntities()=='optimized')
IsaacPerformanceHelpers:SetEnabled(false);assert(__ff.GetRoomEntities==__original)
IsaacPerformanceHelpers:SetEnabled(true);assert(__ff.GetRoomEntities()=='optimized')
local ok=pcall(function()IsaacPerformanceHelpers:SetEnabled('yes')end);assert(not ok)
''')
 def test_unload_restores_only_owned_patch(self):
  self.run_case('''
FiendFolio=__ff;__callbacks[15]()
local foreign=function()return 'foreign' end;__ff.GetRoomEntities=foreign
IsaacPerformanceHelpers:SetEnabled(false);assert(__ff.GetRoomEntities==foreign)
''')
 def test_own_unload_disables_but_other_unload_does_not(self):
  self.run_case('''
FiendFolio=__ff;__callbacks[15]()
__callbacks[73](nil,{});assert(__ff.GetRoomEntities()=='optimized')
__callbacks[73](nil,IsaacPerformanceHelpers.Mod);assert(__ff.GetRoomEntities==__original)
''')
if __name__=='__main__':unittest.main()
