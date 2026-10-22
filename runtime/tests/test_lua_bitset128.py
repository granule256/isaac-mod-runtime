"""角色模板实际128位标志表达式以及跨64位运算，拒绝截成64位。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
SOURCE=Path(__file__).resolve().parents[1]/'source'
HARNESS=r'''
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"
#include <cstdio>
#include <cstring>
int main(){const char* s=R"lua(
 assert(type(BitSet128)=='table' and type(TearFlags)=='table')
 local flags=TearFlags.TEAR_POISON|TearFlags.TEAR_FREEZE
 assert(flags.l==48 and flags.h==0 and flags:Get(4) and flags:Get(5) and not flags:Get(6))
 local a=BitSet128(1,0);local b=a<<64
 assert(b.l==0 and b.h==1 and (b>>64)==a)
 assert((BitSet128(-1,-1)&a)==a and (a~a)==BitSet128())
 assert((a|0)==a and (0|a)==a and (b|3)==BitSet128(3,1))
 assert((3&BitSet128(1,2))==a and (BitSet128(1,2)~1)==BitSet128(0,2))
 assert((a|{l=2,h=4})==BitSet128(3,4))
 assert(BitSet128(false,false)==BitSet128())
 assert(BitSet128(0,-1)<BitSet128(0,0))
 assert((~BitSet128()).l==-1 and (~BitSet128()).h==-1)
 local c=BitSet128();c:Set(127,true);assert(c:Get(127) and c.h==(-9223372036854775807-1))
 c:Set(127,false);assert(c==BitSet128())
 assert(tostring(BitSet128(1,2))=='BitSet128: 00000000000000020000000000000001')
 assert(TearFlags.TEAR_LUDOVICO:Get(127) and TearFlags.TEAR_GOLDEN_BOMB:Get(125))
 assert(TearFlags.TEAR_MIGAN==TearFlags.TEAR_MULLIGAN and TearFlags.TEAR_BOMBERANG==TearFlags.TEAR_BOOMERANG)
 assert((a:__bor(b))==(a|b))
 assert(TearFlags.TEAR_EFFECT_COUNT==84 and TearFlags.TEAR_NORMAL==BitSet128())
 assert((a<<127):Get(127) and (a<<128)==BitSet128() and (b<<(-64))==BitSet128())
 assert((a>>(-64))==BitSet128() and (a<<(-9223372036854775807-1))==BitSet128())
 assert(a<b and a<=a and not (b<a))
 local boundary=BitSet128();for _,i in ipairs({0,31,32,63,64,95,96,127}) do boundary:Set(i,true);assert(boundary:Get(i)) end
 boundary.l=-1;boundary.h=2;assert(boundary:Get(63) and boundary:Get(65) and not boundary:Get(64))
 assert(not pcall(function() c:Get(-1) end) and not pcall(function() c:Set(1.5,true) end))
 assert(not pcall(function() c.unknown=1 end) and not pcall(function() return a|true end))
 TearFlags.TEAR_MIGAN:Set(0,true);assert(TearFlags.TEAR_MULLIGAN:Get(0));TearFlags.TEAR_MIGAN:Set(0,false)
 assert(not pcall(function() c:Set(128,true) end))
 assert(getmetatable(BitSet128).__class==getmetatable(a))
 local mod=RegisterMod('bitset-test',1);mod:AddCallback(1,function() end)
 )lua";auto result=LuaRuntime::InitializeFromBuffer(s,std::strlen(s),"@bitset128.lua");if(result!=LuaRuntime::LuaInitResult::Success){char error[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::printf("result=%u error=%s\n",static_cast<unsigned>(result),error);return 1;}return 0;}
'''
class BitSet128Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-bitset128-');cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name),harness_source=HARNESS)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_full_width_flags_and_template_expression(self):
  r=subprocess.run([str(self.binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
