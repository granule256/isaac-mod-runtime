"""PlayerManager item queries use the live player list and native item predicates."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = PREFIX + r'''
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/repentogon_player_manager_api.hpp"
#include "application/player/innate_collectibles.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <algorithm>
#include <vector>
static std::vector<unsigned char> moduleBytes,ownerSlot,managerSlot,manager;
static std::vector<unsigned char> game,playerList,player,backup;
static std::vector<unsigned char> collectibles,trinkets;
static std::vector<unsigned char> item5,item6,trinket7,trinket8;
static std::uint32_t playerCounts[8]{0,0,0,0,0,2,1,0};
static std::uint32_t backupCounts[8]{0,0,0,0,0,9,3,0};
static int SeedInnate(lua_State*) {
 innate_collectibles::Change(reinterpret_cast<std::uintptr_t>(player.data()),5,4);
 innate_collectibles::Change(reinterpret_cast<std::uintptr_t>(backup.data()),6,2);
 return 0;
}
static void Extensions(lua_State* state) noexcept {
 lua_pushcfunction(state,SeedInnate);
 lua_setglobal(state,"_testSeedInnate");
}
extern "C" std::uint32_t g_HostEngineCallTrampolineCalls;
extern "C" std::uintptr_t g_HostEngineCallTrampolineLastTarget;
static void Seed(void* object,std::uint32_t seed,std::uint32_t shift) {
 const std::uint32_t values[]{seed,shift};std::memcpy(object,values,sizeof(values));
}
static std::uint32_t Random(void*,std::uint32_t max) {return max-1;}
static bool Has(void* entity,std::uint32_t id,bool ignore){
 (void)ignore;
 if(entity!=player.data()&&entity!=backup.data())return false;
 if(id==5)return entity==player.data();
 if(id==6)return entity==backup.data();
 return false;
}
static bool Trinket(void* entity,std::uint32_t id,bool ignore){
 (void)ignore;
 if(entity!=player.data()&&entity!=backup.data())return false;
 return id==7&&entity==backup.data();
}
static std::int32_t Multiplier(void* entity,std::uint32_t id){
 if(entity==backup.data()&&id==7)return 2;
 return 0;
}
int main(){
 const std::size_t moduleSize=std::max<std::size_t>(kEntityPlayerVtableOffset+16,
   std::max<std::size_t>(kGameOwnerGlobalSlotOffset+sizeof(std::uintptr_t),
     kGameManagerGlobalSlotOffset+sizeof(std::uintptr_t)));
 moduleBytes.assign(moduleSize,0);
 ownerSlot.assign(8,0);managerSlot.assign(8,0);
 manager.assign(kManagerItemConfigOffset+0x100,0);
 game.assign(kGamePlayerArrayCapacityOffset+8,0);
 playerList.assign(8,0);player.assign(0x3000,0);backup.assign(0x3000,0);
 collectibles.assign(8*sizeof(std::uintptr_t),0);
 trinkets.assign(9*sizeof(std::uintptr_t),0);
 item5.assign(0x100,0);item6.assign(0x100,0);
 trinket7.assign(0x100,0);trinket8.assign(0x100,0);
 const auto base=reinterpret_cast<std::uintptr_t>(moduleBytes.data());
 std::memcpy(moduleBytes.data()+kEntityPlayerEvaluateItemsOffset,
   kEntityPlayerEvaluateItemsExpectedBytes.data(),kEntityPlayerEvaluateItemsExpectedBytes.size());
 const auto vptr=base+kEntityPlayerVtableOffset;
 std::memcpy(player.data(),&vptr,8);
 std::memcpy(backup.data(),&vptr,8);
 const std::uint32_t playerType=kEntityTypePlayer;
 std::memcpy(player.data()+kEntityTypeOffset,&playerType,4);
 std::memcpy(backup.data()+kEntityTypeOffset,&playerType,4);
 std::uint32_t playerVariant=0;std::memcpy(player.data()+kEntityVariantOffset,&playerVariant,4);
 std::memcpy(backup.data()+kEntityVariantOffset,&playerVariant,4);
 const auto playerAddress=reinterpret_cast<std::uintptr_t>(player.data());
 std::memcpy(playerList.data(),&playerAddress,8);
 const auto backupAddress=reinterpret_cast<std::uintptr_t>(backup.data());
 std::memcpy(player.data()+0x2588,&backupAddress,sizeof(backupAddress));
 for(auto [entity,counts]:{std::pair{player.data(),playerCounts},std::pair{backup.data(),backupCounts}}){
  const auto first=reinterpret_cast<std::uintptr_t>(counts);
  const auto last=first+sizeof(playerCounts);
  std::memcpy(entity+kEntityPlayerCollectibleBeginOffset,&first,sizeof(first));
  std::memcpy(entity+kEntityPlayerCollectibleEndOffset,&last,sizeof(last));
 }
 const auto begin=reinterpret_cast<std::uintptr_t>(playerList.data());
 std::memcpy(game.data()+kGamePlayerArrayBeginOffset,&begin,8);
 const auto end=begin+8;std::memcpy(game.data()+kGamePlayerArrayEndOffset,&end,8);
 std::memcpy(game.data()+kGamePlayerArrayCapacityOffset,&end,8);
 const auto item5Address=reinterpret_cast<std::uintptr_t>(item5.data());
 const auto item6Address=reinterpret_cast<std::uintptr_t>(item6.data());
 std::memcpy(collectibles.data()+5*sizeof(std::uintptr_t),&item5Address,8);
 std::memcpy(collectibles.data()+6*sizeof(std::uintptr_t),&item6Address,8);
 const auto collectibleBegin=reinterpret_cast<std::uintptr_t>(collectibles.data());
 const auto collectibleEnd=collectibleBegin+collectibles.size();
 std::memcpy(manager.data()+kManagerItemConfigOffset+kItemConfigCollectibleBeginOffset,
   &collectibleBegin,8);
 std::memcpy(manager.data()+kManagerItemConfigOffset+kItemConfigCollectibleEndOffset,
   &collectibleEnd,8);
 const auto trinket7Address=reinterpret_cast<std::uintptr_t>(trinket7.data());
 const auto trinket8Address=reinterpret_cast<std::uintptr_t>(trinket8.data());
 std::memcpy(trinkets.data()+7*sizeof(std::uintptr_t),&trinket7Address,8);
 std::memcpy(trinkets.data()+8*sizeof(std::uintptr_t),&trinket8Address,8);
 const auto trinketBegin=reinterpret_cast<std::uintptr_t>(trinkets.data());
 const auto trinketEnd=trinketBegin+trinkets.size();
 std::memcpy(manager.data()+kManagerItemConfigOffset+kItemConfigTrinketBeginOffset,
   &trinketBegin,8);
 std::memcpy(manager.data()+kManagerItemConfigOffset+kItemConfigTrinketEndOffset,
   &trinketEnd,8);
 const std::uint64_t lazShared=0x80000000ULL;
 std::memcpy(item6.data()+kItemConfigItemTagsOffset,&lazShared,8);
 std::memcpy(trinket7.data()+kItemConfigItemTagsOffset,&lazShared,8);
 const auto gameAddress=reinterpret_cast<std::uintptr_t>(game.data());
 std::memcpy(ownerSlot.data(),&gameAddress,8);
 const auto managerAddress=reinterpret_cast<std::uintptr_t>(manager.data());
 std::memcpy(managerSlot.data(),&managerAddress,8);
 const auto ownerSlotAddress=reinterpret_cast<std::uintptr_t>(ownerSlot.data());
 std::memcpy(moduleBytes.data()+kGameOwnerGlobalSlotOffset,&ownerSlotAddress,
   sizeof(ownerSlotAddress));
 const auto managerSlotAddress=reinterpret_cast<std::uintptr_t>(managerSlot.data());
 std::memcpy(moduleBytes.data()+kGameManagerGlobalSlotOffset,&managerSlotAddress,
   sizeof(managerSlotAddress));
 LuaRuntime::SetEngineModuleBase(base);LuaRuntime::SetGameBindings(
   ownerSlotAddress,0);LuaRuntime::ObserveGameThread();
 LuaRuntime::SetRngBindings(reinterpret_cast<std::uintptr_t>(&Seed),0);
 LuaRuntime::SetRngRandomBindings(reinterpret_cast<std::uintptr_t>(&Random),0);
 std::memset(game.data()+kGamePlayerArrayBeginOffset,0,16);
 assert(ResolveEnginePlayerArray().readable&&ResolveEnginePlayerArray().count==0);
 std::memcpy(game.data()+kGamePlayerArrayBeginOffset,&begin,8);
 std::memcpy(game.data()+kGamePlayerArrayEndOffset,&end,8);
 Files files(true);SetSessionSaveFilePort(&files);
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 SetEntityPlayerHasCollectibleHostImplementation(&Has);
 SetRepentogonPlayerManagerTrinketHost(&Trinket);
 SetRepentogonPlayerManagerTrinketMultiplierHost(&Multiplier);
 LuaRuntime::SetRuntimeExtensionInstaller(&Extensions);
 const auto players=isaac::runtime::ResolveEnginePlayerArray();
 assert(players.readable&&players.count==1);
 const char* script=R"lua(
local players = PlayerManager.GetPlayers()
assert(type(players)=='table' and #players==1)
assert(GetPtrHash(players[1])==GetPtrHash(Isaac.GetPlayer(0)))
players[1]=nil
assert(#PlayerManager.GetPlayers()==1) -- a fresh table, not the engine container
assert(PlayerManager.AnyoneIsPlayerType(PlayerType.PLAYER_ISAAC))
assert(not PlayerManager.AnyoneIsPlayerType(PlayerType.PLAYER_MAGDALENE))
local p=Isaac.GetPlayer(0)
assert(select('#',p:AddCacheFlags(CacheFlag.CACHE_SPEED,false))==0)
assert(select('#',p:AddCacheFlags(CacheFlag.CACHE_DAMAGE,true))==0)
assert(RNG(91,9):GetSeed()==91 and RNG():GetSeed()==0xAA17414F)
assert(not pcall(RNG,0,9) and not pcall(RNG,91,81))
assert(RNG(91):RandomInt(-5,4)==4 and RNG(91):RandomInt(4,4)==4)
assert(RNG(91):RandomInt(4)==3 and not pcall(function() RNG(91):RandomInt(4,3) end))
local item=Isaac.GetItemConfig():GetCollectible(5)
item.MaxCharges=13;item.ChargeType=2
assert(item.MaxCharges==13 and item.ChargeType==2)
assert(not pcall(function() item.MaxCharges=1.5 end))
assert(GetPtrHash(PlayerManager.FirstCollectibleOwner(5))==GetPtrHash(p))
assert(GetPtrHash(PlayerManager.FirstCollectibleOwner(5,false))==GetPtrHash(p))
local backupOwner=PlayerManager.FirstCollectibleOwner(6)
assert(backupOwner and backupOwner:GetPlayerType()==p:GetPlayerType())
assert(GetPtrHash(backupOwner)~=GetPtrHash(p))
assert(PlayerManager.FirstCollectibleOwner(6,false)==nil)
assert(PlayerManager.FirstCollectibleOwner(7)==nil)
assert(not pcall(PlayerManager.FirstCollectibleOwner,5,1))
assert(GetPtrHash(PlayerManager.FirstTrinketOwner(7))==GetPtrHash(backupOwner))
assert(GetPtrHash(PlayerManager.FirstTrinketOwner(7,nil,true))==GetPtrHash(backupOwner))
assert(GetPtrHash(PlayerManager.FirstTrinketOwner(7,RNG(),true))==GetPtrHash(backupOwner))
assert(PlayerManager.FirstTrinketOwner(7,false)==nil)
assert(PlayerManager.FirstTrinketOwner(7,RNG(),false)==nil)
assert(PlayerManager.FirstTrinketOwner(8)==nil)
assert(not pcall(PlayerManager.FirstTrinketOwner,7,1))
assert(PlayerManager.AnyoneHasCollectible(5,false))
assert(PlayerManager.AnyoneHasCollectible(6,false)==true) -- backup with LazShared tag
assert(PlayerManager.GetNumCollectibles(5)==2) -- no LazShared tag, exclude backup's nine
assert(PlayerManager.GetNumCollectibles(6)==4)
_testSeedInnate()
assert(p:GetCollectibleNum(5)==6)
assert(PlayerManager.GetNumCollectibles(5)==6)
assert(PlayerManager.GetNumCollectibles(5,true)==2)
assert(PlayerManager.GetNumCollectibles(6)==6) -- main + tagged backup + innate modifiers
assert(PlayerManager.GetNumCollectibles(6,true)==4)
assert(PlayerManager.GetNumCollectibles(6,nil)==6)
assert(PlayerManager.GetNumCollectibles(7)==0)
assert(not pcall(PlayerManager.GetNumCollectibles,5,1))
assert(PlayerManager.AnyoneHasTrinket(7,true))
assert(PlayerManager.AnyoneHasTrinket(7,false)) -- backup multiplier
assert(not PlayerManager.AnyoneHasTrinket(8,true))
assert(not PlayerManager.AnyoneHasTrinket(8,false))
assert(not pcall(function()PlayerManager.AnyoneHasCollectible(-1)end))
assert(not pcall(function()PlayerManager.AnyoneHasCollectible(1,1)end))
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@player-manager.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(g_HostEngineCallTrampolineCalls==1);
 assert(g_HostEngineCallTrampolineLastTarget==base+kEntityPlayerEvaluateItemsOffset);
 assert(LuaRuntime::ShutdownForModReload());
 repentogon::SetNativePort(nullptr);
 SetEntityPlayerHasCollectibleHostImplementation(nullptr);SetRepentogonPlayerManagerTrinketHost(nullptr);
 SetRepentogonPlayerManagerTrinketMultiplierHost(nullptr);
 LuaRuntime::SetRuntimeExtensionInstaller(nullptr);SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonPlayerManagerTests(unittest.TestCase):
    def test_item_queries_and_optional_ignore_modifiers(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-player-manager-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
