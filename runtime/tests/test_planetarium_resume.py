"""实际作者init的续局分支：缺失/已有数据/非表JSON，且有数据只解码一次。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
class PlanetariumResumeTests(unittest.TestCase):
 def test_original_resume_branch(self):
  s=(ROOT/'runtime/mod-patches/PlanetariumChance/main.lua').read_text()
  block=s.split('elseif continued then',1)[1].split('\n\tend',1)[0]
  script="""
  local exists=false;local decodes=0;local loads=0;local encoded='saved'
  local mod={HasData=function()return exists end,LoadData=function()loads=loads+1;return exists and encoded or ''end}
  local json={decode=function(data)assert(data~='','missing save must not be decoded');decodes=decodes+1;return data=='saved' and {Available=1,CanSpawn=0}or 5 end}
  local function resume(self)
  """+block+"""
  end
  local self={storage={available=1}}
  resume(self);assert(self.storage.available==1 and self.storage.canPlanetariumsSpawn==1 and decodes==0 and loads==0)
  exists=true;resume(self);assert(self.storage.available==1 and self.storage.canPlanetariumsSpawn==0 and decodes==1 and loads==1)
  encoded='other';resume(self);assert(self.storage.canPlanetariumsSpawn==1 and decodes==2 and loads==2)
  local m=RegisterMod('planet-resume',1);m:AddCallback(1,function()end)
  """
  harness='''#include "lua_runtime.hpp"
#include <cstring>
#include <cstdio>
int main(){const char* s=R"lua('''+script+''')lua";auto r=LuaRuntime::InitializeFromBuffer(s,std::strlen(s),"@planet-resume.lua");char e[1024]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::puts(e);return r==LuaRuntime::LuaInitResult::Success?0:1;}
'''
  with tempfile.TemporaryDirectory(prefix='planet-resume-')as d:
   binary=build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(d),harness_source=harness)
   r=subprocess.run([str(binary)],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
