"""IsPlaying正反结果、32位参数和真实Manager接收者；不把false降级当通过。"""
from pathlib import Path
import subprocess,tempfile,unittest
from . import test_lua_batch408_sfx_play_real as fixture
from .test_support import build_lua_harness
MAIN=r'''
unsigned queryCalls=0;std::int32_t queryIds[2]{};
bool FakePlaying(const void*self,std::int32_t id){assert(reinterpret_cast<std::uintptr_t>(self)==ExpectedSoundEffects());assert(queryCalls<2);queryIds[queryCalls++]=id;return id==7;}
int main(){static_cast<void>(&FakeSfxPlay);static_cast<void>(&BitsToFloat);static_cast<void>(&Near);LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(&FakePlaying)-kSoundEffectsIsPlayingOffset);
const char*script="local s=SFXManager();assert(type(s)=='userdata' and not s:IsPlaying(7));local m=RegisterMod('sfx-playing-contract',1);m:AddCallback(2,function() assert(s:IsPlaying('4294967303')==true);assert(s:IsPlaying(4294967295)==false);assert(not pcall(s.IsPlaying,s,{}));assert(not pcall(s.IsPlaying,s));assert(not pcall(s.IsPlaying,s,7,1)) end)";
assert(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@sfx-playing-contract.lua")==LuaRuntime::LuaInitResult::Success);assert(queryCalls==0);LuaRuntime::DispatchPostRender(reinterpret_cast<std::uintptr_t>(&g_Manager));if(LuaRuntime::TakeCallbackError()){char e[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::puts(e);return 1;}assert(queryCalls==2&&queryIds[0]==7&&queryIds[1]==-1);return 0;}
'''
class RemainingSfxPlaying(unittest.TestCase):
 def test_real_positive_negative_results_receiver_and_arguments(self):
  prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(int argc, char** argv)')]
  source='#include <cassert>\n#include <cstdio>\n'+prefix+MAIN
  with tempfile.TemporaryDirectory(prefix='remaining-sfx-playing-')as d:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=source)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
