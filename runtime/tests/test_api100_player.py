"""第一组20玩家方法的真实Lua→原生行为判据。"""
import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
ROOT=Path(__file__).resolve().parents[2]
BASELINE=r'''
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 const char*script="local m=RegisterMod('api100-player',1);m:AddCallback(1,function()local p=Isaac.GetPlayer();for _,name in ipairs({'AddBombs','AddGigaBombs','AddJarFlies','AddPoopMana','AddDeadEyeCharge','ClearDeadEyeCharge','ClearCostumes','ClearTemporaryEffects','GetEffectiveBloodCharge','GetEffectiveSoulCharge','GetMaxPocketItems','GetMaxPoopMana','HasTimedItem','IsHeldItemVisible','RemoveBlueFly','RemoveBlueSpider','CanAddCollectible','AnimateLightTravel','TryUseKey','GetGreedDonationBreakChance'})do assert(type(p[name])=='function',name)end end)";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api100-player.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();return LuaRuntime::TakeCallbackError()?2:0;
}
'''
class Player20Baseline(unittest.TestCase):
 def test_required_methods_registered(self):
  with tempfile.TemporaryDirectory(prefix='api100-player-red-')as d:
   source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+BASELINE
   source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
   extra=ROOT/'runtime/src/interfaces/lua/api100_player.cpp'
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=source,extra_sources=()if extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

MAIN=r'''

#include "interfaces/lua/api100_player.hpp"
#include "lua_object_handles.hpp"
#include "interfaces/lua/api100_player.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <algorithm>
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static void* wanted{};static unsigned calls[20]{},hud{},eye{},costumes{},temporary=1,fly=2,spider=2,travel{};static bool held=true;
template<class T>T Read(void*p,std::size_t o){T t{};std::memcpy(&t,static_cast<unsigned char*>(p)+o,sizeof(t));return t;}
template<class T>void Write(void*p,std::size_t o,T t){std::memcpy(static_cast<unsigned char*>(p)+o,&t,sizeof(t));}
static void Touch(unsigned n,const void*p){assert(p==wanted);++calls[n];}
static void Bombs(void*p,std::int32_t n){Touch(0,p);assert(n==2||n==-1);Write(p,0x16dc,std::clamp(Read<std::int32_t>(p,0x16dc)+n,0,99));++hud;}
static void Giga(void*p,std::int32_t n){Touch(1,p);assert(n==5||n==-1);Write(p,0x24a4,std::clamp(Read<std::int32_t>(p,0x24a4)+n,0,Read<std::int32_t>(p,0x16dc)));++hud;}
static void Flies(void*p,std::int32_t n){Touch(2,p);assert(n==3||n==-1);Write(p,0x16d0,std::min(Read<std::int32_t>(p,0x16d0)+n,20));++hud;}
static void Poop(void*p,std::int32_t n){Touch(3,p);assert(n==5||n==99);Write(p,0x269c,std::clamp(Read<std::int32_t>(p,0x269c)+n,0,9));++hud;}
static void AddEye(void*p){Touch(4,p);++eye;}
static void ClearEye(void*p){Touch(5,p);eye=0;}
static void Costumes(void*p){Touch(6,p);++costumes;held=false;}
static void Temporary(void*p){Touch(7,p);temporary=0;}
static std::int32_t Blood(const void*p){Touch(8,p);return 17;}
static std::int32_t Soul(const void*p){Touch(9,p);return -9;}
static std::uint32_t Pocket(const void*p){Touch(10,p);return 0xf0000000U;}
static std::int32_t MaxPoop(const void*p){Touch(11,p);return 9;}
static bool Timed(void*p){Touch(12,p);return temporary!=0;}
static bool Visible(void*p){Touch(13,p);return held;}
static void Fly(void*p){Touch(14,p);--fly;}
static void Spider(void*p){Touch(15,p);--spider;}
static bool CanAdd(const void*p,std::int32_t id){Touch(16,p);return id==1;}
static void Travel(void*p){Touch(17,p);++travel;}
static bool Key(void*p){Touch(18,p);const auto n=Read<std::int32_t>(p,0x16d4);if(n==0)return false;Write(p,0x16d4,n-1);++hud;return true;}
static float Donation(const void*p){Touch(19,p);return 37.125F;}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;const std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);wanted=g_Entities[kPlayer].data();
 Write(wanted,0x16dc,std::int32_t{0});Write(wanted,0x16d4,std::int32_t{1});
 namespace guards=api100_player;auto guard=[&](auto o,const auto&b){std::memcpy(g_ModuleBytes.data()+o,b.data(),b.size());};
 guard(guards::kAddBombsEntry,guards::kAddBombsGuard);
guard(guards::kAddGigaBombsEntry,guards::kAddGigaBombsGuard);
guard(guards::kAddJarFliesEntry,guards::kAddJarFliesGuard);
guard(guards::kAddPoopManaEntry,guards::kAddPoopManaGuard);
guard(guards::kAddDeadEyeChargeEntry,guards::kAddDeadEyeChargeGuard);
guard(guards::kClearDeadEyeChargeEntry,guards::kClearDeadEyeChargeGuard);
guard(guards::kClearCostumesEntry,guards::kClearCostumesGuard);
guard(guards::kClearTemporaryEffectsEntry,guards::kClearTemporaryEffectsGuard);
guard(guards::kGetEffectiveBloodChargeEntry,guards::kGetEffectiveBloodChargeGuard);
guard(guards::kGetEffectiveSoulChargeEntry,guards::kGetEffectiveSoulChargeGuard);
guard(guards::kGetMaxPocketItemsEntry,guards::kGetMaxPocketItemsGuard);
guard(guards::kGetMaxPoopManaEntry,guards::kGetMaxPoopManaGuard);
guard(guards::kHasTimedItemEntry,guards::kHasTimedItemGuard);
guard(guards::kIsHeldItemVisibleEntry,guards::kIsHeldItemVisibleGuard);
guard(guards::kRemoveBlueFlyEntry,guards::kRemoveBlueFlyGuard);
guard(guards::kRemoveBlueSpiderEntry,guards::kRemoveBlueSpiderGuard);
guard(guards::kCanAddCollectibleEntry,guards::kCanAddCollectibleGuard);
guard(guards::kAnimateLightTravelEntry,guards::kAnimateLightTravelGuard);
guard(guards::kTryUseKeyEntry,guards::kTryUseKeyGuard);
guard(guards::kGetGreedDonationBreakChanceEntry,guards::kGetGreedDonationBreakChanceGuard);
 Api100PlayerNativeTestBindings bindings{};
 bindings.methods[0]=engine_call::AddressOfFunction(&Bombs);
bindings.methods[1]=engine_call::AddressOfFunction(&Giga);
bindings.methods[2]=engine_call::AddressOfFunction(&Flies);
bindings.methods[3]=engine_call::AddressOfFunction(&Poop);
bindings.methods[4]=engine_call::AddressOfFunction(&AddEye);
bindings.methods[5]=engine_call::AddressOfFunction(&ClearEye);
bindings.methods[6]=engine_call::AddressOfFunction(&Costumes);
bindings.methods[7]=engine_call::AddressOfFunction(&Temporary);
bindings.methods[8]=engine_call::AddressOfFunction(&Blood);
bindings.methods[9]=engine_call::AddressOfFunction(&Soul);
bindings.methods[10]=engine_call::AddressOfFunction(&Pocket);
bindings.methods[11]=engine_call::AddressOfFunction(&MaxPoop);
bindings.methods[12]=engine_call::AddressOfFunction(&Timed);
bindings.methods[13]=engine_call::AddressOfFunction(&Visible);
bindings.methods[14]=engine_call::AddressOfFunction(&Fly);
bindings.methods[15]=engine_call::AddressOfFunction(&Spider);
bindings.methods[16]=engine_call::AddressOfFunction(&CanAdd);
bindings.methods[17]=engine_call::AddressOfFunction(&Travel);
bindings.methods[18]=engine_call::AddressOfFunction(&Key);
bindings.methods[19]=engine_call::AddressOfFunction(&Donation);
 SetApi100PlayerNativeTestBindings(bindings);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_MATHLIBNAME,luaopen_math,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));
 // 独立验证模组显式挂20真实handler；生产catalog接线另由真实登记测试核。
 if(scene!="integration"){luaL_getmetatable(L,LuaRuntime::kEntityPlayerMetatable);lua_getfield(L,-1,"__methods");
 lua_pushcfunction(L,Api100PlayerAddBombs);lua_setfield(L,-2,"AddBombs");
lua_pushcfunction(L,Api100PlayerAddGigaBombs);lua_setfield(L,-2,"AddGigaBombs");
lua_pushcfunction(L,Api100PlayerAddJarFlies);lua_setfield(L,-2,"AddJarFlies");
lua_pushcfunction(L,Api100PlayerAddPoopMana);lua_setfield(L,-2,"AddPoopMana");
lua_pushcfunction(L,Api100PlayerAddDeadEyeCharge);lua_setfield(L,-2,"AddDeadEyeCharge");
lua_pushcfunction(L,Api100PlayerClearDeadEyeCharge);lua_setfield(L,-2,"ClearDeadEyeCharge");
lua_pushcfunction(L,Api100PlayerClearCostumes);lua_setfield(L,-2,"ClearCostumes");
lua_pushcfunction(L,Api100PlayerClearTemporaryEffects);lua_setfield(L,-2,"ClearTemporaryEffects");
lua_pushcfunction(L,Api100PlayerGetEffectiveBloodCharge);lua_setfield(L,-2,"GetEffectiveBloodCharge");
lua_pushcfunction(L,Api100PlayerGetEffectiveSoulCharge);lua_setfield(L,-2,"GetEffectiveSoulCharge");
lua_pushcfunction(L,Api100PlayerGetMaxPocketItems);lua_setfield(L,-2,"GetMaxPocketItems");
lua_pushcfunction(L,Api100PlayerGetMaxPoopMana);lua_setfield(L,-2,"GetMaxPoopMana");
lua_pushcfunction(L,Api100PlayerHasTimedItem);lua_setfield(L,-2,"HasTimedItem");
lua_pushcfunction(L,Api100PlayerIsHeldItemVisible);lua_setfield(L,-2,"IsHeldItemVisible");
lua_pushcfunction(L,Api100PlayerRemoveBlueFly);lua_setfield(L,-2,"RemoveBlueFly");
lua_pushcfunction(L,Api100PlayerRemoveBlueSpider);lua_setfield(L,-2,"RemoveBlueSpider");
lua_pushcfunction(L,Api100PlayerCanAddCollectible);lua_setfield(L,-2,"CanAddCollectible");
lua_pushcfunction(L,Api100PlayerAnimateLightTravel);lua_setfield(L,-2,"AnimateLightTravel");
lua_pushcfunction(L,Api100PlayerTryUseKey);lua_setfield(L,-2,"TryUseKey");
lua_pushcfunction(L,Api100PlayerGetGreedDonationBreakChance);lua_setfield(L,-2,"GetGreedDonationBreakChance");
 lua_pop(L,2);}
 const char*script=R"lua(
 p=Isaac.GetPlayer();assert(p~=nil);local npc=Isaac.FindByType(20)[1]
 assert(p:HasTimedItem(true) and p:IsHeldItemVisible('extra'))
 assert(select('#',p:AddBombs('4294967298',false))==0);assert(p:GetNumBombs()==2)
 p:AddBombs(-1);assert(p:GetNumBombs()==1)
 p:AddGigaBombs(5);p:AddGigaBombs(-1)
 p:AddJarFlies(3);p:AddJarFlies('4294967295')
 p:AddPoopMana(5);assert(p:GetPoopMana()==5);p:AddPoopMana(99.0,false);assert(p:GetPoopMana()==9)
 assert(select('#',p:AddDeadEyeCharge({}))==0);assert(select('#',p:ClearDeadEyeCharge(false))==0);assert(select('#',p:ClearCostumes(nil))==0);assert(not p:IsHeldItemVisible())
 assert(select('#',p:ClearTemporaryEffects(1))==0);assert(not p:HasTimedItem())
 assert(p:GetEffectiveBloodCharge('ignored')==17 and p:GetEffectiveSoulCharge()==-9)
 assert(p:GetMaxPocketItems()==4026531840 and p:GetMaxPoopMana()==9)
 assert(select('#',p:RemoveBlueFly())==0);assert(select('#',p:RemoveBlueSpider())==0);assert(select('#',p:AnimateLightTravel())==0)
 assert(p:CanAddCollectible('4294967297') and not p:CanAddCollectible(0))
 assert(p:TryUseKey(true)==true and p:GetNumKeys()==0);assert(p:TryUseKey({})==false)
 assert(p:GetGreedDonationBreakChance('ignored',{})==37.125 and math.type(p:GetGreedDonationBreakChance())=='float')
 for _,name in ipairs({'AddBombs','AddGigaBombs','AddJarFlies','AddPoopMana','CanAddCollectible'})do
  for _,v in ipairs({false,true,1.5,{},'no'})do assert(not pcall(function()p[name](p,v)end))end
  assert(not pcall(function()p[name](p)end));assert(not pcall(function()p[name](p,nil)end))
 end
 local methods={'AddBombs','AddGigaBombs','AddJarFlies','AddPoopMana','AddDeadEyeCharge','ClearDeadEyeCharge','ClearCostumes','ClearTemporaryEffects','GetEffectiveBloodCharge','GetEffectiveSoulCharge','GetMaxPocketItems','GetMaxPoopMana','HasTimedItem','IsHeldItemVisible','RemoveBlueFly','RemoveBlueSpider','CanAddCollectible','AnimateLightTravel','TryUseKey','GetGreedDonationBreakChance'}
 for _,name in ipairs(methods)do local fn=p[name];assert(not pcall(function()fn(npc,1)end));assert(not pcall(function()fn({},1)end));assert(not pcall(function()fn(nil,1)end))end
 )lua";
 if(scene=="badguard"){
  for(unsigned i=0;i<20;++i)bindings.methods[i]=0;SetApi100PlayerNativeTestBindings(bindings);
  script="local p=Isaac.GetPlayer();assert(not pcall(function()p:GetMaxPoopMana()end))";
  g_ModuleBytes[guards::kGetMaxPoopManaEntry]^=1;
 }
 if(luaL_loadstring(L,script)||lua_pcall(L,0,0,0)){fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}
 if(scene=="badguard"){lua_close(L);return 0;}
 const unsigned expected[]={2,2,2,2,1,1,1,1,1,1,1,1,2,2,1,1,2,1,2,2};
 for(unsigned i=0;i<20;++i)if(calls[i]!=expected[i])return 2;
 if(hud!=9||eye!=0||costumes!=1||temporary!=0||fly!=1||spider!=1||travel!=1||Read<std::int32_t>(wanted,0x16d0)!=2||Read<std::int32_t>(wanted,0x24a4)!=0)return 3;
 if(scene=="crossbase"){
  std::vector<unsigned char> changed=g_ModuleBytes;const auto newBase=AddressOf(changed);changed[guards::kGetMaxPoopManaEntry]^=1;
  WriteWord(g_Entities[kPlayer],0,newBase+kEntityPlayerVtableOffset);LuaRuntime::SetEngineModuleBase(newBase);
  if(luaL_dostring(L,"assert(not pcall(function()p:GetMaxPoopMana()end))"))return 4;
  if(calls[11]!=1)return 5;
 }
 if(scene=="dead"){
  RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));
  if(luaL_dostring(L,"assert(not pcall(function()p:TryUseKey()end));assert(not pcall(function()p:AddBombs(2)end))"))return 6;
  if(calls[18]!=2||calls[0]!=2)return 7;
 }
 lua_close(L);return 0;
}

'''
class Player20Behavior(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='api100-player-behavior-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  extra=ROOT/'runtime/src/interfaces/lua/api100_player.cpp'
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source,extra_sources=()if extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_20_native_consumers_parameters_guards_and_lifetime(self):
  for scene in ('normal','badguard','crossbase','dead'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

class Player20Integration(Player20Behavior):
 def test_20_native_consumers_parameters_guards_and_lifetime(self):
  r=subprocess.run([str(self.binary),'integration'],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
