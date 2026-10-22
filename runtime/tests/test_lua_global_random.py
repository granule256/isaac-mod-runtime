"""全局Random：真实Lua初始化、uint32边界及原生绑定失败。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness
ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "lua_runtime.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "runtime_constants.hpp"
#include <cstdio>
#include <cstring>
#include <vector>
static unsigned calls=0;
static std::uint32_t values[]={1U,0U,0x80000000U,0xffffffffU,123456789U};
static std::uint32_t HostRandom(){return values[calls++];}
static void HostSeed(void* rng,std::uint32_t seed,std::uint32_t){std::memcpy(rng,&seed,4);}
static std::uint32_t HostNext(void*){return 1;}
int main(int argc,char** argv) {
 if(argc!=2)return 9;
 std::vector<unsigned char> image(kRandomU32Offset+8);
 std::memcpy(image.data()+kRandomU32Offset,&kRandomU32EntryWord,4);
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(image.data()));
 isaac::runtime::SetRandomU32HostImplementation(HostRandom);
 LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&HostSeed),reinterpret_cast<std::uintptr_t>(&HostNext));
 const bool valid=std::strcmp(argv[1],"valid")==0;
 if(std::strcmp(argv[1],"missing")==0)LuaRuntime::SetEngineModuleBase(0);
 if(std::strcmp(argv[1],"overflow")==0)LuaRuntime::SetEngineModuleBase(UINTPTR_MAX-8);
 if(std::strcmp(argv[1],"corrupt")==0)image[kRandomU32Offset]=0;
 const char* script=valid?R"lua(
 assert(type(Random)=='function','missing global Random')
 -- ChallengeAPI原入口的实际调用形态。
 ChallengeAPI={};ChallengeAPI.Random=RNG();ChallengeAPI.Random:SetSeed(Random(),0)
 assert(ChallengeAPI.Random:GetSeed()==1)
 assert(Random()==0,'zero must survive')
 assert(Random()==2147483648,'high bit must survive')
 assert(Random()==4294967295,'full uint32 must survive')
 assert(Random()==123456789,'must call engine on every invocation')
 local mod=RegisterMod('RandomTest',1);mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)
 )lua":R"lua(
 assert(type(Random)=='function','missing global Random')
 local ok,err=pcall(Random);assert(not ok and tostring(err):find('native random source unavailable'),tostring(err))
 local mod=RegisterMod('RandomTest',1);mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)
 )lua";
 const auto result=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@random.lua");
 char error[1024]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
 std::printf("status=%d calls=%u error=%s\n",static_cast<int>(result),calls,error);
 return result==LuaRuntime::LuaInitResult::Success && calls==(valid?5U:0U)?0:1;
}
'''
class LuaGlobalRandomTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-global-random-')
  cls.binary=build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(cls.tmp.name),harness_source=HARNESS)
 @classmethod
 def tearDownClass(cls): cls.tmp.cleanup()
 def test_random_initialization_uint32_and_unavailable_binding(self):
  for scenario in ('valid','missing','overflow','corrupt'):
   with self.subTest(scenario=scenario):
    result=subprocess.run([str(self.binary),scenario],capture_output=True,text=True)
    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
