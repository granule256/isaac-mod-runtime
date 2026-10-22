"""实际Lua熔炼列表：全部/筛选、signed16、真实向量变化及失效拒绝。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
from . import test_lua_batch343_get_color_and_lists as fixture
ROOT=Path(__file__).resolve().parents[2]

MAIN=r'''
std::vector<unsigned char> g_Desc,g_Replacement;
std::vector<std::uintptr_t> g_ConfigSlots;
static int mutation=0;
void PublishDesc(std::vector<unsigned char>& bytes){
 WriteAt<std::uintptr_t>(g_PlayerBytes,0x1b60,AddressOf(bytes));
 WriteAt<std::uintptr_t>(g_PlayerBytes,0x1b68,AddressOf(bytes)+bytes.size());
 WriteAt<std::uintptr_t>(g_PlayerBytes,0x1b70,AddressOf(bytes)+bytes.size());
}
void HostSeed(void* p,std::uint32_t seed,std::uint32_t){std::memcpy(p,&seed,4);}
void HostNext(void* p){
 std::uint32_t v=0;std::memcpy(&v,p,4);++v;std::memcpy(p,&v,4);
 if(mutation==1)PublishDesc(g_Replacement);
 if(mutation==2)WriteAt<std::uint8_t>(g_PlayerBytes,kEntityExistsOffset,0);
 if(mutation==3){WriteAt<std::uintptr_t>(g_PlayerBytes,0x1b68,AddressOf(g_Desc)+8);}
 if(mutation==4)WriteAt<std::uintptr_t>(g_ManagerSlotBytes,0,0);
 if(mutation==5)WriteAt<std::uintptr_t>(g_GameBytes,kGamePlayerArrayEndOffset,AddressOf(g_PlayerArrayBytes));
 mutation=0;
}
int main(int argc,char** argv){
 if(argc!=2)return 99;std::string scenario=argv[1];
 PublishFakeMemory();WriteAt<std::uint8_t>(g_PlayerBytes,kEntityExistsOffset,1);
 LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&HostSeed),reinterpret_cast<std::uintptr_t>(&HostNext));
 g_Desc.assign(24,0);g_Replacement.assign(24,0);
 WriteAt<std::int16_t>(g_Desc,4,3);WriteAt<std::int16_t>(g_Desc,6,4);
 WriteAt<std::int16_t>(g_Desc,8,-2);WriteAt<std::int16_t>(g_Desc,10,-3);
 WriteAt<std::int16_t>(g_Desc,20,1);WriteAt<std::int16_t>(g_Desc,22,2);
 WriteAt<std::int16_t>(g_Replacement,4,99);WriteAt<std::int16_t>(g_Replacement,6,88);
 PublishDesc(g_Desc);
 g_ConfigSlots.assign(8,AddressOf(g_ItemBytes));g_ConfigSlots[4]=0;
 const auto configBegin=reinterpret_cast<std::uintptr_t>(g_ConfigSlots.data());
 WriteAt<std::uintptr_t>(g_ManagerBytes,kManagerItemConfigOffset+kItemConfigTrinketBeginOffset,configBegin);
 WriteAt<std::uintptr_t>(g_ManagerBytes,kManagerItemConfigOffset+kItemConfigTrinketEndOffset,configBegin+g_ConfigSlots.size()*8);
 if(scenario=="empty"){for(auto off:{0x1b60,0x1b68,0x1b70})WriteAt<std::uintptr_t>(g_PlayerBytes,off,0);}
 if(scenario=="bad_begin")WriteAt<std::uintptr_t>(g_PlayerBytes,0x1b60,AddressOf(g_Desc)+1);
 if(scenario=="bad_end")WriteAt<std::uintptr_t>(g_PlayerBytes,0x1b68,AddressOf(g_Desc)+3);
 if(scenario=="bad_capacity")WriteAt<std::uintptr_t>(g_PlayerBytes,0x1b70,AddressOf(g_Desc)+4);
 if(scenario=="config_bad")WriteAt<std::uintptr_t>(g_ManagerBytes,kManagerItemConfigOffset+kItemConfigTrinketEndOffset,configBegin+3);
 if(scenario=="reallocate")mutation=1;
 if(scenario=="owner_dead")mutation=2;
 if(scenario=="desc_shrinks")mutation=3;
 if(scenario=="config_dead")mutation=4;
 if(scenario=="owner_removed")mutation=5;
 std::string script=R"lua(
 local m=RegisterMod('smelted',1)
 m:AddCallback(1,function()
  local p=Isaac.GetPlayer(0)
  local function all(t)
   assert(t[0]==nil and t[6]==nil)
   local n=0;for k,v in pairs(t)do n=n+1;assert(type(k)=='number' and type(v)=='table')end
   assert(n==5 and t[1].trinketAmount==3 and t[1].goldenTrinketAmount==4)
   assert(t[2].trinketAmount==-2 and t[2].goldenTrinketAmount==-3)
   assert(t[3].trinketAmount==0 and t[4].goldenTrinketAmount==0 and t[5].trinketAmount==1)
  end
 )lua";
 if(scenario=="all")script+="all(p:GetSmeltedTrinkets());all(p:GetSmeltedTrinkets(nil));all(p:GetSmeltedTrinkets(false,77));all(p:GetSmeltedTrinkets(4));all(p:GetSmeltedTrinkets('x'));assert(REPENTOGON~=true)";
 else if(scenario=="filter")script+=R"lua(
  local t=p:GetSmeltedTrinkets({3,32769,'2',2.0,0,4,65535})
  assert(t[1].trinketAmount==3 and t[2].trinketAmount==-2 and t[3].goldenTrinketAmount==0)
  assert(t[0]==nil and t[4]==nil and t[5]==nil and t[32769]==nil)
  local n=0;for _ in pairs(t)do n=n+1 end;assert(n==3)
  assert(next(p:GetSmeltedTrinkets({}))==nil)
 )lua";
 else if(scenario=="hole")script+="local t={1,2,3};t[2]=nil;local out=p:GetSmeltedTrinkets(t);assert(out[1] and not out[2] and not out[3])";
 else if(scenario=="empty")script+="assert(next(p:GetSmeltedTrinkets())==nil);assert(not pcall(function()p:GetSmeltedTrinkets({1})end))";
 else if(scenario=="invalid")script+="assert(not pcall(function()p:GetSmeltedTrinkets({'bad'})end));assert(not pcall(function()p:GetSmeltedTrinkets({1.5})end));assert(not pcall(function()p:GetSmeltedTrinkets({6})end));all(p:GetSmeltedTrinkets())";
 else if(scenario=="bad_begin"||scenario=="bad_end"||scenario=="bad_capacity")script+="assert(not pcall(function()p:GetSmeltedTrinkets()end))";
 else if(scenario=="config_bad")script+="assert(not pcall(function()p:GetSmeltedTrinkets({1})end));all(p:GetSmeltedTrinkets())";
 else {
  script+=R"lua(
   local t={1,2,3};t[1]=nil
   setmetatable(t,{__index=function(_,i)
    assert(i==1);local r=RNG();r:SetSeed(1,1);r:Next();return 1
   end})
  )lua";
  if(scenario=="reallocate")script+="local out=p:GetSmeltedTrinkets(t);assert(out[1].trinketAmount==99 and out[1].goldenTrinketAmount==88 and out[2].trinketAmount==0);assert(p:GetSmeltedTrinkets()[1].trinketAmount==99)";
  else script+="assert(not pcall(function()p:GetSmeltedTrinkets(t)end))";
 }
 script+=" end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@smelted.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();
 if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::printf("%s\n",e[i].text);return 2;}
}
'''

class SmeltedTrinketTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-smelted-')
  source='#include <string>\n'+fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  for token,value in (("CURRENT_TINT_0","0.25f"),("CURRENT_TINT_1","0.5f"),("CURRENT_TINT_2","0.75f"),("CURRENT_TINT_3","1.0f"),("CURRENT_SHIFT_0","0.0f"),("CURRENT_SHIFT_1","0.0f"),("CURRENT_SHIFT_2","0.0f"),("DEFAULT_TINT_0","1.0f"),("DEFAULT_TINT_1","1.0f"),("DEFAULT_TINT_2","1.0f"),("DEFAULT_TINT_3","1.0f"),("SPLAT_TINT_0","1.0f"),("SPLAT_TINT_1","1.0f"),("SPLAT_TINT_2","1.0f"),("SPLAT_TINT_3","1.0f"),("COLLECTIBLE_COUNT","5"),("TRINKET_COUNT","8"),("ENTITY_DEFAULT_COLOR_OFFSET","0x128"),("ENTITY_SPLAT_COLOR_OFFSET","0x164")):
   source=source.replace(token,value)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_real_lists_filter_signed_fields_and_mutation(self):
  for scenario in ('all','filter','hole','empty','invalid','bad_begin','bad_end','bad_capacity','config_bad','reallocate','owner_dead','desc_shrinks','config_dead','owner_removed'):
   with self.subTest(scenario=scenario):
    result=subprocess.run([str(self.binary),scenario],capture_output=True,text=True)
    self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
