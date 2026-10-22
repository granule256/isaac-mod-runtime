"""70实际Lua：原生时机、真值取消、自有参数共享及嵌套上下文。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'
HEADER=SOURCE/'clear_award_internal_hook.hpp'
HARNESS=r'''
#include "clear_award_internal_hook.hpp"
#include "lua_runtime.hpp"
#include <array>
#include <cstring>
#include <string>
#include <cstdio>
#include <cstdlib>
using namespace isaac::runtime;
using namespace isaac::runtime::relay;
static std::string scene;static unsigned calls=0;static bool nested=false;
static ClearAwardNativeBindings native{};
static unsigned Flow(unsigned seed,float x,float y);
static void Ctor(void* p,float x,float y){++calls;float v[2]={x,y};std::memcpy(p,v,8);}
static unsigned Seed(const void*p){unsigned v;std::memcpy(&v,p,4);return v;}
static void SetSeed(void*p,unsigned seed,unsigned shift){unsigned v[4]={seed,shift,shift+1,shift+2};std::memcpy(p,v,16);}
static void Next(void*p){unsigned s=Seed(p)+1;std::memcpy(p,&s,4);
 if(scene=="nested"&&!nested){nested=true;if(Flow(200,7,8)!=1)std::abort();nested=false;}}
static unsigned Flow(unsigned seed,float x,float y){
 alignas(16) std::array<unsigned char,0x120> frame{},before{};
 SetSeed(frame.data()+0x98,seed,35);float position[2]={x,y};std::memcpy(frame.data()+0x90,position,8);
 InternalHookContext c{};c.originalSp=reinterpret_cast<std::uintptr_t>(frame.data());c.x[29]=c.originalSp+0xc0;
 c.x[0]=c.originalSp+0x58;c.x[19]=0xfeed1234;c.x[25]=0x9876543210ULL;
 float zero=0,minus80=-80;std::memcpy(&c.q[0].low,&zero,4);std::memcpy(&c.q[1].low,&minus80,4);
 before=frame;const auto resume=ClearAwardInternalCallback(c,&native);
 float temp[2]={0,-80};std::memcpy(before.data()+0x58,temp,8);
 if(frame!=before||c.x[19]!=0xfeed1234||c.x[25]!=0x9876543210ULL)std::abort();
 if(c.x[0]!=(resume?c.originalSp+0x98:c.originalSp+0x58))std::abort();
 if(resume>1)std::abort();return resume;
}
int main(int argc,char**argv){
 if(argc!=2)return 99;scene=argv[1];native.constructVector=Ctor;
 LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&SetSeed),reinterpret_cast<std::uintptr_t>(&Next));
 std::string body="return true";
 if(scene=="false")body="return false";else if(scene=="nil"||scene=="shared")body="return nil";
 else if(scene=="zero")body="return 0";else if(scene=="string")body="return ''";
 else if(scene=="table")body="return {}";else if(scene=="error")body="error('clear70 error')";
 std::string script=R"lua(
 local m=RegisterMod('clear70',1);m:AddCallback(1,function()end);local lastRng,lastPosition
 _award={count=0,tail=0,after=0}
 m:AddCallback(70,function(_,rng,pos)
  assert(type(rng)=='userdata' and type(pos)=='userdata')
  assert(rng:GetSeed()==100 or rng:GetSeed()==200)
  if rng:GetSeed()==100 then assert(pos.X==12.5 and pos.Y==-40.25)
  else assert(pos.X==7 and pos.Y==8) end
  _award.count=_award.count+1;rng:Next();pos.X=666;lastRng,lastPosition=rng,pos
 )lua"+body+R"lua( end)
 m:AddCallback(70,function(_,rng,pos)
  assert(rng==lastRng and pos==lastPosition and rng:GetSeed()==101 and pos.X==666)
  _award.tail=_award.tail+1;return true end)
 m:AddCallback(70,function()_award.after=_award.after+1 end)
 )lua";
 if(scene=="builtin")script+="\nIsaac.SetBuiltInCallbackState(70,false)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@clear70.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto result=Flow(100,12.5,-40.25);bool want=scene!="false"&&scene!="error"&&scene!="builtin";
 if(result!=want||calls!=(scene=="nested"?2:1))return 2;
 double count=0,tail=0,after=0;
 if(LuaRuntime::ReadLuaTableNumber("_award","count",&count)||LuaRuntime::ReadLuaTableNumber("_award","tail",&tail)||LuaRuntime::ReadLuaTableNumber("_award","after",&after))return 3;
 if(count!=(scene=="builtin"?0:scene=="nested"?2:1)||tail!=(scene=="nil"||scene=="shared"?1:0)||after!=0)return 4;
 if(LuaRuntime::TakeCallbackError()!=(scene=="error"))return 5;
}
'''
class ClearAwardBridgeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.binary=None
  if not HEADER.exists():return
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-clear70-')
  cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name),harness_source=HARNESS,extra_sources=(SOURCE/'clear_award_internal_hook.cpp',))
 @classmethod
 def tearDownClass(cls):
  if cls.binary:cls.tmp.cleanup()
 def test_bridge_exists(self):self.assertTrue(HEADER.exists(),'70真实阶段桥尚未实现')
 def test_truthiness_value_arguments_errors_and_nested_context(self):
  if not self.binary:self.skipTest('桥尚未实现')
  for scene in ['true','false','nil','zero','string','table','error','shared','nested','builtin']:
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
