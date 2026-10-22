"""CyclingItemsAPI首次安装后继续旧局：不能对不存在的存档解码JSON。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
class CyclingResumeTests(unittest.TestCase):
 def test_first_resume_missing_existing_and_new_game(self):
  source=(ROOT/'runtime/mod-patches/CyclingItemsAPI/main.lua').read_text()
  block=source[source.index('function CyclingItemsAPI:OnGameStart'):source.index('CyclingItemsAPI:AddCallback(ModCallbacks.MC_POST_GAME_STARTED')]
  script="""
  CyclingItemsAPI={}; local has=false; local loads=0; local decodes=0
  Isaac.HasModData=function()return has end;Isaac.LoadModData=function()loads=loads+1;return '{"saved":7}'end
  json={decode=function(data)decodes=decodes+1;assert(has,'missing data must not be decoded');return {saved=7}end}
  """+block+"""
  CyclingItemsAPI:OnGameStart(true);assert(next(CyclingItemsAPI.CyclingItems)==nil);assert(loads==0 and decodes==0)
  has=true;CyclingItemsAPI:OnGameStart(true);assert(CyclingItemsAPI.CyclingItems.saved==7);assert(loads==1 and decodes==1)
  CyclingItemsAPI:OnGameStart(false);assert(next(CyclingItemsAPI.CyclingItems)==nil);assert(loads==1 and decodes==1)
  local m=RegisterMod('ResumeTest',1);m:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)
  """
  harness='''#include "lua_runtime.hpp"
#include <cstring>
#include <cstdio>
int main(){const char* s=R"lua('''+script+''')lua";
auto result=LuaRuntime::InitializeFromBuffer(s,std::strlen(s),"@resume.lua");char e[1024]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::puts(e);return result==LuaRuntime::LuaInitResult::Success?0:1;}
'''
  with tempfile.TemporaryDirectory(prefix='cycling-resume-')as tmp:
   binary=build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(tmp),harness_source=harness)
   result=subprocess.run([str(binary)],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
