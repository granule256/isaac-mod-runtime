"""角色模板真实缓存字段：泪弹高度/下降速度/加速度/颜色均读写原格。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_batch343_get_color_and_lists as f
from .test_support import build_lua_harness
MAIN=r'''
int main(){PublishFakeMemory();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 WriteAt<float>(g_PlayerBytes,0x1848,-23.75f);WriteAt<float>(g_PlayerBytes,0x184c,1.0f);WriteAt<float>(g_PlayerBytes,0x1850,0.5f);
 const char* s=R"lua(
 local m=RegisterMod('tear-stats',1);local p=Isaac.GetPlayer(0)
 local function near(a,b) return math.abs(a-b)<0.00001 end
 m:AddCallback(1,function()
  p.TearHeight=p.TearHeight-5
  p.TearFallingSpeed=p.TearFallingSpeed+2
  p.TearFallingAcceleration=p.TearFallingAcceleration+0.25
  assert(near(p.TearHeight,-28.75) and near(p.TearFallingSpeed,3) and near(p.TearFallingAcceleration,0.75))
  p.TearColor=Color(0.2,0.3,0.4,0.5,0.1,0.2,0.3)
  local c=p.TearColor;assert(near(c.R,0.2) and near(c.A,0.5) and near(c.RO,0.1))
  c.R=0.9;assert(near(p.TearColor.R,0.2))
  assert(not pcall(function() p.TearColor=1 end))
  assert(not pcall(function() p.TearHeight='bad' end))
 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(s,std::strlen(s),"@tear-stats.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){char e[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::puts(e);return 2;}
 for(auto pair: {std::pair<std::size_t,float>{0x1848,-28.75f},{0x184c,3.0f},{0x1850,0.75f}}){float v=0;std::memcpy(&v,g_PlayerBytes.data()+pair.first,4);if(v!=pair.second)return 3;}
 float colors[11]{};std::memcpy(colors,g_PlayerBytes.data()+0x1868,sizeof(colors));const float expected[11]={0.2f,0.3f,0.4f,0.5f,0.1f,0.2f,0.3f,0,0,0,0};if(std::memcmp(colors,expected,sizeof(colors)))return 4;
 return 0;
}
'''
class PlayerTearStatsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-player-tear-stats-');source=f.HARNESS[:f.HARNESS.index('int main(')]+MAIN
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(f,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):source=source.replace(name,str(getattr(f,name)))
  cls.binary=build_lua_harness(source_root=f.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_real_tear_stats_writes_and_color_value_copy(self):
  r=subprocess.run([str(self.binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
