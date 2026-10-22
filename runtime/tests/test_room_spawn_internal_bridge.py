"""实际71桥：转换时机、覆盖后的301真实RNG/GetCard及嵌套恢复。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_event_callbacks import HARNESS, SOURCE
MAIN = r'''
#include "room_spawn_internal_hook.hpp"
#include <cstdlib>
#include <vector>
using namespace isaac::runtime;
using namespace isaac::runtime::relay;
static std::uint32_t nextCalls=0,cardCalls=0,ctorCalls=0,randomCalls=0;
static bool randomZero=false;
static void* expectedRng=nullptr;static const void* expectedPool=nullptr;
alignas(16) static unsigned char nestedEntry[16]{};
alignas(16) static unsigned char nestedFrame[64]{};
static const RoomSpawnNativeBindings* currentNative=nullptr;
static void Put(void* p,unsigned offset,unsigned value,unsigned bytes){std::memcpy(static_cast<unsigned char*>(p)+offset,&value,bytes);}
static unsigned Get(const void* p,unsigned offset,unsigned bytes){unsigned v=0;std::memcpy(&v,static_cast<const unsigned char*>(p)+offset,bytes);return v;}
static void Construct(void* rng,std::uint32_t seed,std::uint32_t shift){
 if(shift!=7||(rng!=expectedRng&&rng!=nestedFrame+16))std::abort();
 ++ctorCalls;Put(rng,0,seed,4);Put(rng,4,1,4);Put(rng,8,21,4);Put(rng,12,20,4);
}
static std::uint32_t Random(void* rng,std::uint32_t max){
 if(rng!=expectedRng||max!=40||Get(rng,0,4)!=0xffffffffU)std::abort();
 ++randomCalls;Put(rng,0,0,4);return randomZero?0:17;
}
static std::uint32_t Next(void* rng){
 if(rng!=expectedRng)std::abort();++nextCalls;Put(rng,0,Get(rng,0,4)+1,4);return 0xdead1234;
}
static std::uint32_t Card(const void* pool,std::uint32_t seed,bool a,bool b,bool c){
 if(pool!=expectedPool||seed!=0xdead1234||a||!b||!c)std::abort();++cardCalls;
 // 真引擎helper可以重入Lua；这里用实际71桥重新进入不同栈帧/条目。
 InternalHookContext nested{};nested.x[19]=reinterpret_cast<std::uintptr_t>(nestedEntry);
 nested.x[25]=43;nested.x[23]=9;nested.x[1]=9;nested.x[2]=7;
 nested.x[29]=reinterpret_cast<std::uintptr_t>(nestedFrame+32);nested.x[0]=nested.x[29]-0x10;
 if(RoomFixSpawnCtorInternalCallback(nested,currentNative)!=0)std::abort();
 return 65537;
}
int main(int argc,char** argv){
 if(argc!=2)return 99;
 std::string scenario=argv[1];
 std::string script=R"lua(
 local m=RegisterMod('room-native',1);m:AddCallback(1,function() end)
 _probe={outer=0,nested=0}
 m:AddCallback(71,function(_,t,v,s,index,seed)
  if index==43 then assert(t==33 and v==0 and s==0 and seed==9);_probe.nested=_probe.nested+1;return {} end
  assert(index==42 and seed==4294967295);_probe.outer=_probe.outer+1
 )lua";
 if(scenario=="converted"||scenario=="1400zero")script+="assert(t==33 and v==1 and s==7);return {}";
 else if(scenario=="1400nonzero")script+="assert(t==33 and v==0 and s==7);return {}";
 else if(scenario=="return301")script+="assert(t==5 and v==100 and s==7);return {5,301,99}";
 else if(scenario=="replace301")script+="assert(t==5 and v==301 and s==7);return {nil,100}";
 else if(scenario=="same")script+="assert(t==5 and v==100 and s==7);return {5}";
 else if(scenario=="empty"||scenario=="field4")script+="assert(t==5 and v==301 and s==7);return "+std::string(scenario=="empty"?"{}":"{[4]=123}");
 else return 98;
 script+=" end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@native-room.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 alignas(16) unsigned char entry[16]{},frame[64]{};
 std::vector<unsigned char> game(0x242c0+32);std::uintptr_t gameAddress=reinterpret_cast<std::uintptr_t>(game.data());
 const bool is1400=scenario=="1400zero"||scenario=="1400nonzero";
 Put(entry,0,scenario=="converted"?1410:(is1400?1400:5),4);Put(entry,4,(scenario=="replace301"||scenario=="empty"||scenario=="field4")?301:100,2);Put(entry,6,7,2);
 Put(nestedEntry,0,33,4);expectedRng=frame+16;Put(expectedRng,0,123,4);expectedPool=game.data()+0x242c0;
 InternalHookContext context{};
 context.x[19]=reinterpret_cast<std::uintptr_t>(entry);context.x[29]=reinterpret_cast<std::uintptr_t>(frame+32);
 std::uintptr_t gameSlotAddress=reinterpret_cast<std::uintptr_t>(&gameAddress);
 context.x[28]=0xdead;context.x[25]=42;context.x[23]=0xffffffffU;
 context.x[0]=context.x[29]-0x10;context.x[1]=0xffffffffU;context.x[2]=7;
 context.x[8]=0xabcdef;
 RoomSpawnNativeBindings native{Next,Card,Construct,Random,reinterpret_cast<std::uintptr_t>(&gameSlotAddress)};
 currentNative=&native;randomZero=scenario=="1400zero";
 const auto resume=RoomFixSpawnCtorInternalCallback(context,&native);
 if(LuaRuntime::TakeCallbackError())return 2;
 const bool special=scenario=="return301"||scenario=="empty"||scenario=="field4";
 const bool replaced=scenario=="return301"||scenario=="replace301"||scenario=="same";
 if(resume!=(replaced?1U:0U))return 3;
 if(nextCalls!=(special?1U:0U)||cardCalls!=nextCalls||Get(expectedRng,0,4)!=((special||is1400)?0U:0xffffffffU))return 4;
 if(ctorCalls!=(special?2U:1U)||randomCalls!=(is1400?1U:0U)||context.x[28]!=gameSlotAddress||context.x[23]!=0xffffffffU||context.x[25]!=42)return 9;
 if(Get(entry,0,4)!=((scenario=="converted"||is1400)?33U:5U)||context.x[8]!=Get(entry,0,4))return 5;
 if(Get(entry,4,2)!=(scenario=="1400nonzero"?0U:((scenario=="converted"||is1400)?1U:(special?300U:100U))))return 6;
 if(Get(entry,6,2)!=(special?1U:7U))return 7;
 double n=0;if(!Counter("outer",&n)||n!=1||!Counter("nested",&n)||n!=(special?1:0))return 8;
 bool unused=false;static_cast<void>(Flag("unused",&unused));static_cast<void>(Player());static_cast<void>(Collider());
}
'''
class RoomSpawnInternalBridgeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-room-native-')
  cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name),
    harness_source='#include <string>\n'+HARNESS[:HARNESS.index('int main(')]+MAIN,
    extra_sources=(SOURCE/'room_spawn_internal_hook.cpp',))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_special_native_calls_and_nested_real_lua(self):
  for scenario in ('converted','1400zero','1400nonzero','return301','replace301','empty','field4','same'):
   with self.subTest(scenario=scenario):
    result=subprocess.run([str(self.binary),scenario],capture_output=True,text=True)
    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
if __name__=='__main__':unittest.main()
