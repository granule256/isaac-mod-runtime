"""真实Lua验证PC道具列表操作、实时向量与收藏品类型判据。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_batch343_get_color_and_lists as fixture
from .test_support import build_lua_harness

MAIN = r'''
int main(int argc,char** argv) {
 if(argc!=2)return 90;
 PublishFakeMemory();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const char* script=R"lua(
 local m=RegisterMod('item-lists',1);local step=0;local list,trinkets,old
 m:AddCallback(1,function()
  step=step+1
  if step==1 then
   local config=Isaac.GetItemConfig();list=config:GetCollectibles();trinkets=config:GetTrinkets()
   assert(type(list)=='userdata' and type(trinkets)=='userdata')
   assert(list.Size==2 and #list==2 and trinkets.Size==3 and #trinkets==3)
   assert(type(list:Get(0))=='userdata' and type(trinkets:Get(2))=='userdata')
   assert(getmetatable(CppContainer.Vector.ItemConfigList).__class==getmetatable(list))
   old=list:Get(0)
   assert(not pcall(function() list.Size=9 end))
   assert(not pcall(function() list.Get=false end))
   for _,i in ipairs({-1,2,4294967295,1.5,'bad'}) do assert(not pcall(function() list:Get(i) end)) end
   assert(type(list:Get('0'))=='userdata' and type(list:Get(0.0))=='userdata')
   assert(type(list:Get(4294967296))=='userdata')
  elseif step==2 then
   assert(list.Size==3 and #list==3 and list:Get(2).ID==99)
   assert(old.ID==nil)
  elseif step==3 then
   assert(list:Get(2).ID==100 and list.Size==3 and list:Get(1)==nil)
  elseif step==4 then
   assert(list.Size==0 and #list==0 and not pcall(function() list:Get(0) end))
  elseif step==5 then
   assert(not pcall(function() return list.Size end))
   assert(not pcall(function() return #list end))
  elseif step==6 then
   assert(not pcall(function() return list.Size end))
   assert(not pcall(function() list:Get(0) end))
  end
 end)
 )lua";
 if(std::strcmp(argv[1],"types")==0){
  script=R"lua(
  local m=RegisterMod('item-types',1)
  m:AddCallback(1,function()
   local c=Isaac.GetItemConfig();local i=c:GetCollectible(0);local t=i.Type
   local yes=t==1 or t==3 or t==4
   assert(i:IsCollectible()==yes and c:IsCollectible(0)==yes)
   assert(i:IsTrinket()==(t==2))
  end)
  )lua";
 }
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@item-list-views.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto run=[](){LuaRuntime::DispatchPostUpdate();return !LuaRuntime::TakeCallbackError();};
 if(std::strcmp(argv[1],"types")==0){
  for(std::uint32_t t:{0U,1U,2U,3U,4U,5U,0xffffffffU}){
   WriteAt<std::uint32_t>(g_ItemBytes,kItemConfigItemTypeOffset,t);if(!run())return 20+t;
  }return 0;
 }
 if(!run())return 2;
 std::vector<unsigned char> replacement(3*sizeof(std::uintptr_t),0),item(g_ItemBytes);
 WriteAt<std::uint32_t>(item,kItemConfigItemIdOffset,99);
 for(int i=0;i<3;++i)WriteAt<std::uintptr_t>(replacement,i*sizeof(std::uintptr_t),AddressOf(item));
 WriteAt<std::uintptr_t>(g_ManagerBytes,kManagerItemConfigOffset,AddressOf(replacement));
 WriteAt<std::uintptr_t>(g_ManagerBytes,kManagerItemConfigOffset+8,AddressOf(replacement)+replacement.size());
 if(!run())return 3;
 WriteAt<std::uint32_t>(item,kItemConfigItemIdOffset,100);
 WriteAt<std::uintptr_t>(replacement,sizeof(std::uintptr_t),0);if(!run())return 4;
 WriteAt<std::uintptr_t>(g_ManagerBytes,kManagerItemConfigOffset,0);
 WriteAt<std::uintptr_t>(g_ManagerBytes,kManagerItemConfigOffset+8,0);if(!run())return 5;
 WriteAt<std::uintptr_t>(g_ManagerBytes,kManagerItemConfigOffset,AddressOf(replacement));
 WriteAt<std::uintptr_t>(g_ManagerBytes,kManagerItemConfigOffset+8,AddressOf(replacement)+1);if(!run())return 6;
 WriteAt<std::uintptr_t>(g_ManagerSlotBytes,0,0);if(!run())return 7;
 return 0;
}
'''
class ItemConfigListViewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-item-list-views-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(fixture,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):
   source=source.replace(name,str(getattr(fixture,name)))
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_list_userdata_real_values_and_lifetime(self):self.run_case('list')
 def test_collectible_types_match_pc(self):self.run_case('types')
 def run_case(self,case):
  r=subprocess.run([str(self.binary),case],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
