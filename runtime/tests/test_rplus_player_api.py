"""CHAPI玩家方法：真实原件证据与Lua消费者，不写占位接口。"""
import unittest,subprocess,tempfile,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
class RPlusPlayerTests(unittest.TestCase):
 def test_native_player_module_exists(self):
  self.assertTrue((ROOT/'runtime/src/interfaces/lua/rplus_player_api.cpp').exists(),'CHAPI八玩家方法尚未实现')
MAIN=r'''
#include "interfaces/lua/rplus_player_api.hpp"
#include "interfaces/lua/rplus_player_guards.hpp"
#include <cassert>
static unsigned soulCalls=0,bloodCalls=0,jarCalls=0,refreshCalls=0;
static std::int32_t soulAmount=0,bloodAmount=0,jarAmount=0;
static std::int32_t Counter(void* p,std::uintptr_t off){std::int32_t v{};memcpy(&v,static_cast<unsigned char*>(p)+off,4);return v;}
static void Store(void* p,std::uintptr_t off,std::int32_t v){memcpy(static_cast<unsigned char*>(p)+off,&v,4);}
static void AddSoul(void* p,std::int32_t n){++soulCalls;soulAmount=n;++refreshCalls;Store(p,kEntityPlayerSoulChargeOffset,std::max(0,std::min(99,Counter(p,kEntityPlayerSoulChargeOffset)+n)));}
static void AddBlood(void* p,std::int32_t n){++bloodCalls;bloodAmount=n;++refreshCalls;Store(p,kEntityPlayerBloodChargeOffset,std::max(0,std::min(99,Counter(p,kEntityPlayerBloodChargeOffset)+n)));}
static void AddJar(void* p,std::int32_t n){++jarCalls;jarAmount=n;++refreshCalls;Store(p,isaac::runtime::rplus_player::kJarHeartsOffset,std::min(8,Counter(p,isaac::runtime::rplus_player::kJarHeartsOffset)+n));}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 namespace fields=isaac::runtime::rplus_player;
 auto guard=[&](auto off,const auto& bytes){memcpy(g_ModuleBytes.data()+off,bytes.data(),bytes.size());};
 guard(fields::kSubReaderEntry,fields::kSubReaderGuard);guard(fields::kSubInitEntry,fields::kSubInitGuard);
 guard(fields::kCooldownReaderEntry,fields::kCooldownReaderGuard);guard(fields::kCooldownInitEntry,fields::kCooldownInitGuard);guard(fields::kCooldownMaxEntry,fields::kCooldownMaxGuard);guard(fields::kJarReaderEntry,fields::kJarReaderGuard);
 auto& player=g_Entities[kPlayer];auto& sub=g_Entities[kEnemyA];sub.assign(kEntityPlayerSize,0);
 WriteWord(sub,0,g_EngineBase+kEntityPlayerVtableOffset);Store(sub.data(),kEntityTypeOffset,1);Store(sub.data(),kEntityPlayerIndexOffset,INT32_MIN);sub[kEntityExistsOffset]=1;
 WriteWord(player,fields::kSubPlayerOffset,scene=="ordinary"?0:AddressOf(sub));
 Store(player.data(),fields::kDamageCooldownOffset,7);Store(player.data(),fields::kJarHeartsOffset,0);
 if(scene=="badguard")g_ModuleBytes[fields::kCooldownReaderEntry]^=1;
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 isaac::runtime::SetRPlusPlayerNativeTestBindings({AddSoul,AddBlood,AddJar});
 std::string script=R"lua(local m=RegisterMod('chapi-native',1);_probe={count=0,step=0};m:AddCallback(1,function()
 local originalAssert=assert;local function assert(condition) _probe.step=_probe.step+1;originalAssert(condition) end
 local player=Isaac.GetPlayer()
 assert(type(player.GetSubPlayer)=='function' and type(player.GetDamageCooldown)=='function')
 )lua";
 if(scene=="ordinary")script+="assert(player:GetSubPlayer()==nil)";
 else if(scene=="badguard")script+="assert(not pcall(function()player:GetDamageCooldown()end))";
 else script+=R"lua(
 local sub=player:GetSubPlayer();assert(sub~=nil and sub:IsSubPlayer() and GetPtrHash(player:GetSubPlayer())==GetPtrHash(sub))
 sub:GetData().CustomHealthAPISavedata={mark=42};assert(player:GetSubPlayer():GetData().CustomHealthAPISavedata.mark==42)
 assert(player:GetDamageCooldown()==7);player:SetMinDamageCooldown(3);assert(player:GetDamageCooldown()==7)
 player:SetMinDamageCooldown('4294967308');assert(player:GetDamageCooldown()==12)
 player:SetMinDamageCooldown(-1);assert(player:GetDamageCooldown()==12)
 if player:GetDamageCooldown() > 0 then
     player:ResetDamageCooldown() -- WHY IS DAMAGE INVINCIBLE NOT WORKING
 end
 assert(player:GetDamageCooldown()==0)
 player:SetMinDamageCooldown(3.0);assert(player:GetDamageCooldown()==3)
 assert(not pcall(function()player:SetMinDamageCooldown(false)end))
 assert(not pcall(function()player:SetMinDamageCooldown(1.5)end))
 assert(not pcall(function()player:SetMinDamageCooldown()end))
 player:AddSoulCharge('4294967300');assert(player:GetSoulCharge()==4)
 player:AddBloodCharge(2.0);assert(player:GetBloodCharge()==2)
 local hpToAdd=3
 player:AddSoulCharge(hpToAdd * 2)
 assert(player:GetSoulCharge()==10)
 local hp=2
 player:AddJarHearts(hp)
 assert(player:GetJarHearts()==2);player:AddJarHearts(100);assert(player:GetJarHearts()==8)
 player:AddJarHearts(-10);assert(player:GetJarHearts()==-2)
 assert(not pcall(function()player:AddSoulCharge()end))
 assert(not pcall(function()player:AddBloodCharge(false)end))
 assert(not pcall(function()player:AddJarHearts(0.5)end))
 )lua";
 script+="\n_probe.count=_probe.count+1 end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@chapi-player-api.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){double step=0;static_cast<void>(LuaRuntime::ReadLuaTableNumber("_probe","step",&step));fprintf(stderr,"CHAPI assertion/preceding method step=%g\n",step);return 2;}
 double count=0;if(LuaRuntime::ReadLuaTableNumber("_probe","count",&count)||count!=1)return 3;
 if(scene=="normal"&&(soulCalls!=2||bloodCalls!=1||jarCalls!=3||refreshCalls!=6||soulAmount!=6||bloodAmount!=2||jarAmount!=-10))return 4;
 return 0;
}
'''
class RPlusPlayerBehaviorTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-rplus-player-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', source,count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_chapi_consumer_integer_native_effects_subplayer_and_guards(self):
  for scene in ('normal','ordinary','badguard'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)