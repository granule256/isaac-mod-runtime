"""FoundHUD与原生属性栏共用同一个字节；读写不能覆盖邻格或固定返回true。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_batch343_get_color_and_lists as fixture
from .test_support import build_lua_harness
MAIN=r'''
int main(){
 PublishFakeMemory();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 WriteAt<std::uint8_t>(g_ManagerBytes,0x36509,0xA5);WriteAt<std::uint8_t>(g_ManagerBytes,0x3650a,1);WriteAt<std::uint8_t>(g_ManagerBytes,0x3650b,0x5A);
 const char* script=R"lua(
 local m=RegisterMod('foundhud',1);local step=0
 m:AddCallback(1,function()
  step=step+1
  if step==1 then
   assert(Options.FoundHUD==true,'FoundHUD must read native stat HUD switch')
   assert(rawget(Options,'FoundHUD')==nil)
  elseif step==2 then
   assert(Options.FoundHUD==false,'native changes must be visible')
   Options.FoundHUD=true;assert(Options.FoundHUD==true)
   Options.FoundHUD=false;assert(Options.FoundHUD==false)
   assert(rawget(Options,'FoundHUD')==nil)
  else
   assert(Options.FoundHUD==nil)
   assert(not pcall(function() Options.FoundHUD=true end))
  end
 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@foundhud.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto run=[](){LuaRuntime::DispatchPostUpdate();if(!LuaRuntime::TakeCallbackError())return true;char e[1024]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::fprintf(stderr,"%s\n",e);return false;};
 if(!run())return 2;WriteAt<std::uint8_t>(g_ManagerBytes,0x3650a,0);if(!run())return 3;
 if(g_ManagerBytes[0x36509]!=0xA5||g_ManagerBytes[0x3650b]!=0x5A||g_ManagerBytes[0x3650a]!=0)return 4;
 WriteAt<std::uintptr_t>(g_ManagerSlotBytes,0,0);return run()?0:5;
}
'''
class FoundHudTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-foundhud-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(fixture,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):source=source.replace(name,str(getattr(fixture,name)))
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_native_field_dynamic_read_write_and_missing_owner(self):
  r=subprocess.run([str(self.binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
