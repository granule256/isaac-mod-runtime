"""星象房模组真实坐标表达式需要number*Vector，且不能修改输入向量。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
SCRIPT=r'''
local v=Vector(20,12)
local left=0.25*v
assert(left.X==5 and left.Y==3)
local right=v*0.25
assert(right.X==5 and right.Y==3)
local both=v*Vector(2,3)
assert(both.X==40 and both.Y==36 and v.X==20 and v.Y==12)
local zero=0*v;assert(zero.X==0 and zero.Y==0)
local coords=Vector(0,184)+(0.25*Vector(20,12))
assert(coords.X==5 and coords.Y==187)
local m=RegisterMod('planetarium-vector',1);m:AddCallback(1,function()end)
'''
class PlanetariumVectorPositionTests(unittest.TestCase):
 def test_actual_scalar_left_hud_position_and_existing_overloads(self):
  harness='''#include "lua_runtime.hpp"
#include <cstring>
#include <cstdio>
int main(){const char*s=R"lua('''+SCRIPT+''')lua";auto r=LuaRuntime::InitializeFromBuffer(s,std::strlen(s),"@planetarium-position.lua");char e[1024]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::puts(e);return r==LuaRuntime::LuaInitResult::Success?0:1;}
'''
  with tempfile.TemporaryDirectory(prefix='planet-vector-')as d:
   binary=build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(d),harness_source=harness)
   r=subprocess.run([str(binary)],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
