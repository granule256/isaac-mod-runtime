"""66 实际 Lua 与双内部钩：值快照、低32位返回、嵌套和部分安装。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'runtime/source'
HEADER = SOURCE / 'trinket_internal_hook.hpp'

HARNESS = r'''
#include "trinket_internal_hook.hpp"
#include "lua_runtime.hpp"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

using namespace isaac::runtime;
using namespace isaac::runtime::relay;
alignas(16) static std::array<unsigned char,0x900> pool{},nestedPool{};
alignas(16) static unsigned char managers[2][64]{};
static std::uintptr_t manager = reinterpret_cast<std::uintptr_t>(managers[0]);
static std::uintptr_t managerVariable = reinterpret_cast<std::uintptr_t>(&manager);
static std::string scenario;
static unsigned randomCalls=0,unlockedCalls=0;
static bool recurse=false,allowNested=false;
static TrinketNativeBindings native{};
static unsigned Seed(const void* p){unsigned s;std::memcpy(&s,p,4);return s;}
static void Seed(void* p,unsigned s){std::memcpy(p,&s,4);}
static void HostSetSeed(void* p,unsigned seed,unsigned shift){unsigned fields[4]={seed,shift,shift+1,shift+2};std::memcpy(p,fields,16);}
static unsigned RunFlow(void* originalPool,bool dontAdvance,bool first,bool second,unsigned selected=41);
static void HostNext(void* p){
 unsigned fields[4];std::memcpy(fields,p,sizeof(fields));
 if(fields[2]!=fields[1]+1||fields[3]!=fields[1]+2)std::abort();
 Seed(p,Seed(p)+1);
 if(allowNested&&!recurse){
  recurse=true;
  if(RunFlow(nestedPool.data(),true,true,true)!=47)std::abort();
  recurse=false;
 }
 if(scenario=="manager")manager=reinterpret_cast<std::uintptr_t>(managers[1]);
}
static unsigned Random(void* p,unsigned maximum){
 if(maximum!=13)std::abort();++randomCalls;Seed(p,Seed(p)+1);return 7;
}
static bool Unlocked(const void* p,unsigned achievement){
 if(p!=reinterpret_cast<void*>(manager+0x18)||achievement!=617)std::abort();
 ++unlockedCalls;return true;
}
static unsigned RunFlow(void* originalPool,bool dontAdvance,bool first,bool second,unsigned selected){
 auto* bytes=static_cast<unsigned char*>(originalPool);
 alignas(16) unsigned char frame[0x90],before[0x90];
 std::memset(frame,0xa5,sizeof(frame));
 std::memcpy(frame+0x20,bytes+0x8d4,16);
 std::memcpy(before,frame,sizeof(frame));
 InternalHookContext c{};c.originalSp=reinterpret_cast<std::uintptr_t>(frame);c.x[29]=c.originalSp+0x30;
 c.x[20]=reinterpret_cast<std::uintptr_t>(bytes);c.x[21]=dontAdvance?1:0;
 c.x[19]=reinterpret_cast<std::uintptr_t>(dontAdvance?frame+0x20:bytes+0x8d4);
 c.x[0]=c.x[19];c.x[1]=13;c.x[23]=0xfedcba9876543210ULL;
 if(first){
  if(TrinketFirstRandomInternalCallback(c,&native)!=0||c.x[0]!=7)std::abort();
  if((c.x[21]&1)!=(dontAdvance?1U:0U)||
     (c.x[21]&~std::uintptr_t{1})!=reinterpret_cast<std::uintptr_t>(bytes))std::abort();
 }else c.x[0]=Random(reinterpret_cast<void*>(c.x[0]),13);
 // 仅原 Random 可以改它自己的 RNG，钩本身不能写帧的其它任何位置。
 if(dontAdvance)std::memcpy(before+0x20,frame+0x20,16);
 if(std::memcmp(frame,before,sizeof(frame)))std::abort();
 c.x[20]=selected;c.x[0]=manager+0x18;c.x[1]=617;
 unsigned resume=0;
 if(second)resume=TrinketSelectedInternalCallback(c,&native);
 else c.x[0]=Unlocked(reinterpret_cast<void*>(c.x[0]),617);
 if(c.x[23]!=0xfedcba9876543210ULL||c.x[19]!=(dontAdvance?reinterpret_cast<std::uintptr_t>(frame+0x20):reinterpret_cast<std::uintptr_t>(bytes+0x8d4)))std::abort();
 if(std::memcmp(frame,before,sizeof(frame)))std::abort();
 if(resume==0){if(c.x[0]!=1)std::abort();return static_cast<unsigned>(c.x[20])|0x8000U;}
 if(resume!=1||c.x[20]==0)std::abort();
 return static_cast<unsigned>(c.x[20]);
}
int main(int argc,char**argv){
 if(argc!=2)return 99;scenario=argv[1];
 const bool dont=scenario.find("dont")!=std::string::npos;
 const bool first=scenario!="second_only",second=scenario!="first_only";
 native.random=Random;native.unlocked=Unlocked;native.managerGotSlot=reinterpret_cast<std::uintptr_t>(&managerVariable);
 HostSetSeed(pool.data()+0x8d4,100,7);HostSetSeed(nestedPool.data()+0x8d4,200,7);
 LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&HostSetSeed),reinterpret_cast<std::uintptr_t>(&HostNext));
 std::string body="return nil";
 if(scenario=="override"||scenario=="override_dont")body="return 47";
 else if(scenario=="zero")body="return 0";
 else if(scenario=="minus_one")body="return -1";
 else if(scenario=="low32_zero")body="return 4294967296";
 else if(scenario=="low32_nonzero")body="return 4294967343";
 else if(scenario=="float_integer")body="return 47.0";
 else if(scenario=="float_fraction")body="return 47.5";
 else if(scenario=="string_integer")body="return '47'";
 else if(scenario=="string_invalid")body="return 'nope'";
 else if(scenario=="false")body="return false";
 else if(scenario=="error")body="error('callback66 error')";
 else if(scenario=="nested")body="return 47";
 else if(scenario=="manager")body="return 0";
 std::string script=R"lua(
 local m=RegisterMod('native-trinket',1);local saved
 _probe={count=0,tail=0,after=0,retained=0}
 m:AddCallback(1,function() if saved then assert(saved:GetSeed()==777);saved:Next();_probe.retained=1 end end)
 m:AddCallback(66,function(_,selected,rng)
   assert(selected==41 and type(rng)=='userdata')
   assert(rng:GetSeed()==)lua"+std::to_string(dont?100:101)+R"lua( or rng:GetSeed()==200)
   _probe.count=_probe.count+1;saved=rng
   rng:Next();assert(rng:GetSeed()==)lua"+std::to_string(dont?101:102)+R"lua( or rng:GetSeed()==201)
 )lua";
 if(scenario=="shared"||scenario=="shared_dont")script+=R"lua(
  return nil end)
 m:AddCallback(66,function(_,selected,rng)
  assert(rng==saved and selected==41);assert(rng:GetSeed()==)lua"+std::to_string(dont?101:102)+R"lua()
  rng:SetSeed(777,3);_probe.tail=_probe.tail+1;return 47 end)
 )lua";
 else script+=body+" end)\nm:AddCallback(66,function() _probe.tail=_probe.tail+1;return 99 end)";
 script+="\nm:AddCallback(66,function() _probe.after=_probe.after+1;return 88 end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@trinket66.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(scenario=="unaligned"||scenario=="zero_pool"||scenario=="overflow_pool"){
  alignas(16) unsigned char rng[16];HostSetSeed(rng,100,7);
  InternalHookContext c{};c.x[20]=scenario=="unaligned"?3:(scenario=="zero_pool"?0:UINTPTR_MAX-7);
  c.x[21]=1;c.x[0]=reinterpret_cast<std::uintptr_t>(rng);c.x[1]=13;
  if(TrinketFirstRandomInternalCallback(c,&native)||c.x[21]!=1||c.x[0]!=7||Seed(rng)!=101)return 10;
  c.x[20]=41;
  if(TrinketSelectedInternalCallback(c,&native)||c.x[20]!=41||c.x[0]!=1||unlockedCalls!=1)return 11;
  double count=0;if(LuaRuntime::ReadLuaTableNumber("_probe","count",&count)||count!=0)return 12;
  return LuaRuntime::TakeCallbackError()?13:0;
 }
 allowNested=scenario=="nested";
 const auto result=RunFlow(pool.data(),dont,first,second);
 const bool invalid=scenario=="float_fraction"||scenario=="string_invalid"||scenario=="false"||scenario=="error";
 const bool noOverride=scenario=="zero"||scenario=="low32_zero"||invalid||!first||!second||scenario=="manager";
 const unsigned want=scenario=="minus_one"?0xffffffffU:(noOverride?0x8029U:(scenario=="nil"?99U:47U));
 if(result!=want){std::printf("result=%u want=%u\n",result,want);return 2;}
 if(Seed(pool.data()+0x8d4)!=(dont?100U:101U)||Seed(nestedPool.data()+0x8d4)!=200)return 3;
 const unsigned originalState[4]={dont?100U:101U,7,8,9};
 if(std::memcmp(pool.data()+0x8d4,originalState,16))return 14;
 double count=0,tail=0,after=0;
 if(LuaRuntime::ReadLuaTableNumber("_probe","count",&count)||LuaRuntime::ReadLuaTableNumber("_probe","tail",&tail)||LuaRuntime::ReadLuaTableNumber("_probe","after",&after))return 4;
 if(count!=(!first||!second?0:(scenario=="nested"?2:1)))return 5;
 if(after!=0)return 6;
 if(tail!=(scenario=="shared"||scenario=="shared_dont"||scenario=="nil"?1:0))return 7;
 if(unlockedCalls!=(noOverride?1U:0U)||randomCalls!=(scenario=="nested"?2U:1U))return 8;
 if(LuaRuntime::TakeCallbackError()!=invalid)return 9;
 if(scenario=="shared"||scenario=="shared_dont"){
  std::memset(pool.data()+0x8d4,0,16); // 原池状态已改/清空，保留userdata仍读写自有值。
  LuaRuntime::DispatchPostUpdate();
  double retained=0;if(LuaRuntime::TakeCallbackError()||LuaRuntime::ReadLuaTableNumber("_probe","retained",&retained)||retained!=1)return 15;
 }
 return 0;
}
'''

class TrinketInternalBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = None
        if not HEADER.exists():
            return
        cls.tmp = tempfile.TemporaryDirectory(prefix='isaac-trinket66-')
        cls.binary = build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name),
            harness_source=HARNESS,extra_sources=(SOURCE/'trinket_internal_hook.cpp',))

    @classmethod
    def tearDownClass(cls):
        if cls.binary is not None:
            cls.tmp.cleanup()

    def test_native_bridge_is_implemented(self):
        self.assertTrue(HEADER.exists(), 'MC_GET_TRINKET66 双内部钩尚未实现')

    def test_native_dispatch_does_not_require_room_or_player(self):
        # 宿主 ShouldDispatchManagedCallbacks 恒 true，不能拿行为绿灯证明生产无玩家场景。
        # 直接审查生产入口三项前置：Lua已就绪、状态存在、内建66位启用。
        text=(SOURCE/'lua_runtime.cpp').read_text()
        body=text[text.index('std::uint32_t DispatchGetTrinket('):text.index('std::int32_t DispatchGetPillColor(')]
        self.assertNotIn('ShouldDispatchManagedCallbacks',body)
        for required in ('IsReady()', 'g_LuaState == nullptr', 'BuiltinCallbackEnabled'):
            self.assertIn(required,body)

    def run_scenarios(self, scenarios):
        if self.binary is None:
            self.skipTest('原生桥尚未实现，行为夹具不能编译')
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                r=subprocess.run([str(self.binary),scenario],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr)

    def test_integer_conversion_and_first_non_nil(self):
        self.run_scenarios(('override','zero','minus_one','low32_zero','low32_nonzero','float_integer',
                            'float_fraction','string_integer','string_invalid','false','error','nil','manager'))

    def test_rng_value_shared_within_batch_and_pool_unchanged(self):
        self.run_scenarios(('override_dont','shared','shared_dont'))

    def test_nested_callbacks_keep_each_pool_and_register_context(self):
        self.run_scenarios(('nested',))

    def test_either_partial_install_keeps_original_results(self):
        self.run_scenarios(('first_only','second_only','unaligned','zero_pool','overflow_pool'))

if __name__=='__main__':unittest.main()
