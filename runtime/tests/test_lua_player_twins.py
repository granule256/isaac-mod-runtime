"""真实Lua验证配对身体、主身按signed编号选择及副玩家最高位。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_batch343_get_color_and_lists as fixture
from .test_support import build_lua_harness
MAIN=r'''
int main(){
 PublishFakeMemory();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 std::vector<unsigned char> twin=g_PlayerBytes;
 WriteAt<std::uint32_t>(g_PlayerBytes,0x19f0,2);
 WriteAt<std::uint32_t>(twin,0x19f0,1);
 const char* script=R"lua(
 local m=RegisterMod('twins',1);local step=0;local p=Isaac.GetPlayer(0)
 m:AddCallback(1,function()
  step=step+1
  if step==1 then assert(p:GetOtherTwin()==nil and p:GetMainTwin()==p and not p:IsSubPlayer())
  elseif step==2 then
   local other=p:GetOtherTwin();assert(type(other)=='userdata' and other~=p)
   assert(GetPtrHash(other:GetOtherTwin())==GetPtrHash(p) and GetPtrHash(p:GetMainTwin())==GetPtrHash(other) and other:GetMainTwin()==other)
  elseif step==3 then assert(p:GetMainTwin()==p)
  elseif step==4 then assert(GetPtrHash(p:GetMainTwin())==GetPtrHash(p:GetOtherTwin()) and p:GetOtherTwin():IsSubPlayer() and not p:IsSubPlayer())
  elseif step==5 then assert(p:GetOtherTwin()==nil and p:GetMainTwin()==p)
  elseif step==6 then
   assert(p:GetOtherTwin()==nil and p:GetMainTwin()==nil and not p:IsSubPlayer())
  end
 end)
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@twins.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto run=[](){LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::printf("%s\n",e[i].text);return false;}return true;};
 if(!run())return 2;
 WriteAt<std::uintptr_t>(g_PlayerBytes,0x2580,AddressOf(twin));
 WriteAt<std::uintptr_t>(twin,0x2580,AddressOf(g_PlayerBytes));if(!run())return 3;
 WriteAt<std::uint32_t>(twin,0x19f0,2);if(!run())return 4;
 WriteAt<std::uint32_t>(twin,0x19f0,0x80000000);if(!run())return 5;
 WriteAt<std::uintptr_t>(twin,0,0);if(!run())return 6;
 WriteAt<std::uintptr_t>(g_PlayerBytes,0,0);if(!run())return 7;
 return 0;
}
'''
class PlayerTwinTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-player-twins-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(fixture,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):source=source.replace(name,str(getattr(fixture,name)))
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_native_pairing_and_signed_main_selection(self):
  r=subprocess.run([str(self.binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
