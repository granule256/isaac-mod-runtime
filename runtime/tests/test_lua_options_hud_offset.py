"""HUD偏移读取真实NS字段，Lua写入按本项目PC映像的原生setter。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_batch343_get_color_and_lists as fixture
from .test_support import build_lua_harness
MAIN=r'''
int main(){
 PublishFakeMemory();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 // 独立写已取证绝对偏移，同时在邻格摆诱饵，避免只和实现常量相互验证。
 WriteAt<float>(g_ManagerBytes,0x36510,0.123F);WriteAt<float>(g_ManagerBytes,0x36514,0.3F);WriteAt<float>(g_ManagerBytes,0x36518,0.789F);
 const char* script=R"lua(
 local m=RegisterMod('hudoffset',1);local step=0
 local function near(a,b) return math.abs(a-b)<1e-7 end
 m:AddCallback(1,function()
  step=step+1
  if step==1 then
   assert(near(Options.HUDOffset,0.3) and rawget(Options,'HUDOffset')==nil)
   local p=Vector(20,12)*(Options.HUDOffset-1)+Vector(0,3)
   assert(math.abs(p.X+14)<1e-5 and math.abs(p.Y+5.4)<1e-5)
  elseif step==2 then
   assert(near(Options.HUDOffset,0.8))
   Options.HUDOffset='0.007';assert(near(Options.HUDOffset,0.007))
   Options.HUDOffset=1;assert(near(Options.HUDOffset,0.01))
   Options.HUDOffset=-1;assert(Options.HUDOffset==0)
   assert(not pcall(function() Options.HUDOffset={} end))
   assert(rawget(Options,'HUDOffset')==nil)
  elseif step==3 then
   assert(Options.HUDOffset==nil)
   assert(not pcall(function() Options.HUDOffset=0.007 end))
  end
 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@hudoffset.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto run=[](){LuaRuntime::DispatchPostUpdate();return !LuaRuntime::TakeCallbackError();};
 if(!run())return 2;WriteAt<float>(g_ManagerBytes,0x36514,0.8F);if(!run())return 3;
 float v=1;std::memcpy(&v,g_ManagerBytes.data()+0x36514,4);if(v!=0)return 4;
 float decoy=0;std::memcpy(&decoy,g_ManagerBytes.data()+0x36510,4);if(decoy!=0.123F)return 5;
 WriteAt<std::uintptr_t>(g_ManagerSlotBytes,0,0);if(!run())return 6;return 0;
}
'''
class OptionsHudOffsetTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-options-hud-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(fixture,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):source=source.replace(name,str(getattr(fixture,name)))
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_real_dynamic_field_and_pc_setter(self):
  r=subprocess.run([str(self.binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
