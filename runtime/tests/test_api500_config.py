"""第五批配置字段：真实生产入口、原生宽度、借用服装寿命。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include "interfaces/lua/api500_config.hpp"
#include <cassert>
static std::vector<std::vector<unsigned char>> g_Strings;
static std::vector<std::uintptr_t> g_AssignmentTargets;
static void*Assign(void*dst,const void*src){g_AssignmentTargets.push_back(reinterpret_cast<std::uintptr_t>(dst));const auto*p=static_cast<const std::uint64_t*>(src);const auto n=p[1];const auto*t=reinterpret_cast<const unsigned char*>(p[2]);g_Strings.emplace_back(t,t+n);auto&v=g_Strings.back();auto*d=static_cast<unsigned char*>(dst);std::memset(d,0,24);if(n<=22){d[0]=n*2;std::memcpy(d+1,t,n);}else{std::uint64_t a[3]={(n+1)|1,n,reinterpret_cast<std::uintptr_t>(v.data())};std::memcpy(d,a,24);}return dst;}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 std::vector<unsigned char> manager(kManagerItemConfigOffset+0x100),slot(8),item(0x200),card(0x80),pill(0x80),items(16),cards(16),pills(16);
 WriteWord(slot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(slot));
 auto publish=[&](auto&v,auto&o,std::size_t off){WriteWord(v,8,AddressOf(o));WriteWord(manager,kManagerItemConfigOffset+off,AddressOf(v));WriteWord(manager,kManagerItemConfigOffset+off+8,AddressOf(v)+16);};
 publish(items,item,0);publish(cards,card,0x48);publish(pills,pill,0x60);
 WriteAt<std::int32_t>(item,0,1);WriteAt<std::int32_t>(item,4,1);
 WriteAt<std::uint32_t>(item,0x54,0x80000001U);WriteAt<std::int32_t>(item,0x78,-11);WriteAt<std::int16_t>(item,0x7c,-2);WriteAt<std::int16_t>(item,0x7e,-3);WriteAt<std::int32_t>(item,0xd0,-1);
 item[0xb5]=1;item[0xb6]=1;item[0xb8]=1;item[0xb9]=1;
 WriteAt<std::int32_t>(item,0x80,17);item[0x88]=8;std::memcpy(item.data()+0x89,"test",4);WriteAt<std::int32_t>(item,0xa0,-19);item[0xa4]=1;item[0xa5]=1;item[0xa6]=1;item[0xac]=1;
 WriteAt<std::int32_t>(card,0,1);WriteAt<std::int32_t>(card,4,-101);card[0x38]=8;std::memcpy(card.data()+0x39,"card",4);card[0x50]=1;WriteAt<std::uint32_t>(card,0x54,0x8000001fU);WriteAt<std::int32_t>(card,0x58,1);WriteAt<std::int32_t>(card,0x5c,33);WriteAt<std::int32_t>(card,0x60,-34);
 WriteAt<std::int32_t>(pill,0,1);WriteAt<std::int32_t>(pill,4,-102);pill[0x38]=1;WriteAt<std::int32_t>(pill,0x3c,41);WriteAt<std::int32_t>(pill,0x40,42);WriteAt<std::int32_t>(pill,0x44,-43);
 /*GUARDS*/
 isaac::runtime::SetApi500ConfigStringAssignmentForTesting(Assign);
 const char*body=R"lua(
 if _config500 then assert(not pcall(function()return _held500.Priority end));assert(not pcall(function()return _item500.MaxCooldown end));_config500={done=2};return end
 local c=Isaac.GetItemConfig();local i=c:GetCollectible(1);local a=c:GetCard(1);local p=c:GetPillEffect(1)
 assert(i.CacheFlags==2147483649 and i.MaxCooldown==-11 and i.DevilPrice==-2 and i.ShopPrice==-3 and i.InitCharge==-1)
 assert(i.PassiveCache and i.AddCostumeOnPickup and i.PersistentEffect and i.ClearEffectsOnRemove)
 local s=i.Costume;assert(type(s)=='userdata' and s.ID==17 and s.Anm2Path=='test' and s.Priority==-19 and s.HasOverlay and s.IsFlying and s.HasSkinAlt and s.OverwriteColor)
 local mt=getmetatable(s);assert(mt.__type=='ItemConfigCostume');assert(mt.__class.__index(s,'ID')==s.ID);mt.__class.__newindex(s,'Priority',-23);assert(s.Priority==-23)
 assert(a.HudAnim=='card' and a.GreedModeAllowed and a.PickupSubtype==2147483679 and a.CardType==1 and a.AnnouncerVoice==33 and a.AnnouncerDelay==-34 and a:IsCard())
 assert(p.GreedModeAllowed and p.AnnouncerVoice==41 and p.AnnouncerVoiceSuper==42 and p.AnnouncerDelay==-43)
 assert(a.ID==1 and a.AchievementID==-101 and p.ID==1 and p.AchievementID==-102)
 assert(i.AnnouncerVoice==nil and a.Costume==nil and p.CardType==nil)
 i.DevilPrice=65537;i.MaxCooldown='29';i.CacheFlags=4294967297;i.PassiveCache=nil
 assert(i.DevilPrice==1 and i.MaxCooldown==29 and i.CacheFlags==1 and not i.PassiveCache and i.ShopPrice==-3)
 assert(not pcall(function()i.MaxCooldown=1.5 end));assert(not pcall(function()i.Costume={}end))
 a.HudAnim="abc\0def";assert(a.HudAnim=="abc\0def");s.Anm2Path=string.rep("x",100);assert(s.Anm2Path==string.rep("x",100));a.HudAnim="";assert(a.HudAnim=="")
 s.Priority=31;s.HasOverlay=false;s.IsFlying=0;s.HasSkinAlt=nil;s.OverwriteColor=false;assert(s.Priority==31 and not s.HasOverlay and s.IsFlying and not s.HasSkinAlt and not s.OverwriteColor)
 a.PickupSubtype=4294967297;assert(a.PickupSubtype==1)
 for n=0,7 do a.CardType=n;assert(a:IsCard()==(n==0 or n==1 or n==3 or n==5)) end
 local f=a.IsCard;assert(not pcall(function()f(i)end))
 _config500={done=1};_held500=s;_item500=i
 )lua";
 if(scene=="badguard")body="local i=Isaac.GetItemConfig():GetCollectible(1);assert(not pcall(function()return i.MaxCooldown end));_config500={done=1}";
 if(scene=="badguard")g_ModuleBytes[0x3b5e68]^=1;
 const auto script=std::string("local m=RegisterMod('config500',1);m:AddCallback(1,function()")+body+"end)";
 if(LuaRuntime::InitializeFromBuffer(script.c_str(),script.size(),"@config500.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView errors[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(errors,8);for(unsigned j=0;j<n;++j)fprintf(stderr,"%s\n",errors[j].text);return 2;}
 double done{};if(LuaRuntime::ReadLuaTableNumber("_config500","done",&done)||done!=1)return 3;
 if(scene!="badguard"){
  std::uint32_t cache{};std::int32_t cooldown{};std::int16_t price{},shop{};
  std::memcpy(&cache,item.data()+0x54,4);std::memcpy(&cooldown,item.data()+0x78,4);std::memcpy(&price,item.data()+0x7c,2);std::memcpy(&shop,item.data()+0x7e,2);
  if(cache!=1||cooldown!=29||price!=1||shop!=-3||item[0xb5]!=0||item[0xa4]!=0||item[0xa5]!=1||item[0xa6]!=0||item[0xac]!=0)return 6;
  if(g_AssignmentTargets.size()!=3||g_AssignmentTargets[0]!=AddressOf(card)+0x38||g_AssignmentTargets[1]!=AddressOf(item)+0x88||g_AssignmentTargets[2]!=AddressOf(card)+0x38)return 7;
 }
 if(scene=="lifetime"||scene=="crossbase"){
  if(scene=="lifetime"){WriteWord(items,8,0);}else{LuaRuntime::SetEngineModuleBase(g_EngineBase+8);}
  LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 4;
  if(LuaRuntime::ReadLuaTableNumber("_config500","done",&done)||done!=2)return 5;
 }
 return 0;
}
'''
class ConfigConsumers(unittest.TestCase):
 def test_production_config_fields(self):
  with tempfile.TemporaryDirectory(prefix='isaac-api500-config-') as d:
   source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
   source=source.replace('/*GUARDS*/',guard_setup())
   extra=ROOT/'runtime/src/interfaces/lua/api500_config.cpp'
   if extra.exists():source='#include "interfaces/lua/api500_config.guards.hpp"\n'+source
   source=__import__('re').sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=source,extra_sources=()if not extra.exists()or extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
   for scene in ('normal','badguard','lifetime','crossbase'):
    with self.subTest(scene=scene):
     r=subprocess.run([str(binary),scene],text=True,capture_output=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
def guard_setup():
 p=ROOT/'runtime/src/interfaces/lua/api500_config.guards.hpp'
 if not p.exists():return ''
 return 'std::memcpy(g_ModuleBytes.data()+isaac::runtime::api500_config::kStringAssignOffset,isaac::runtime::api500_config::kStringAssignGuard.data(),16);for(const auto&g:isaac::runtime::api500_config::kGuards)std::memcpy(g_ModuleBytes.data()+g.offset,g.bytes.data(),16);'
