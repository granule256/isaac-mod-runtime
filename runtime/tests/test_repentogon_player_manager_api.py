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
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <algorithm>
#include <vector>
static std::vector<unsigned char> moduleBytes,ownerSlot,game,playerList,player;
static bool Has(void* entity,std::uint32_t id,bool ignore){
 assert(entity==player.data());assert(id==5||id==6);assert(!ignore);return id==5;
}
static bool Trinket(void* entity,std::uint32_t id,bool ignore){
 assert(entity==player.data());assert(id==7||id==8);assert(ignore);return id==7;
}
int main(){
 const std::size_t moduleSize=std::max<std::size_t>(kEntityPlayerVtableOffset+16,
   kGameOwnerGlobalSlotOffset+sizeof(std::uintptr_t));
 moduleBytes.assign(moduleSize,0);
 ownerSlot.assign(8,0);game.assign(kGamePlayerArrayCapacityOffset+8,0);
 playerList.assign(8,0);player.assign(0x3000,0);
 const auto base=reinterpret_cast<std::uintptr_t>(moduleBytes.data());
 const auto vptr=base+kEntityPlayerVtableOffset;
 std::memcpy(player.data(),&vptr,8);
 const std::uint32_t playerType=kEntityTypePlayer;
 std::memcpy(player.data()+kEntityTypeOffset,&playerType,4);
 std::uint32_t playerVariant=0;std::memcpy(player.data()+kEntityVariantOffset,&playerVariant,4);
 const auto playerAddress=reinterpret_cast<std::uintptr_t>(player.data());
 std::memcpy(playerList.data(),&playerAddress,8);
 const auto begin=reinterpret_cast<std::uintptr_t>(playerList.data());
 std::memcpy(game.data()+kGamePlayerArrayBeginOffset,&begin,8);
 const auto end=begin+8;std::memcpy(game.data()+kGamePlayerArrayEndOffset,&end,8);
 std::memcpy(game.data()+kGamePlayerArrayCapacityOffset,&end,8);
 const auto gameAddress=reinterpret_cast<std::uintptr_t>(game.data());
 std::memcpy(ownerSlot.data(),&gameAddress,8);
 const auto ownerSlotAddress=reinterpret_cast<std::uintptr_t>(ownerSlot.data());
 std::memcpy(moduleBytes.data()+kGameOwnerGlobalSlotOffset,&ownerSlotAddress,
   sizeof(ownerSlotAddress));
 LuaRuntime::SetEngineModuleBase(base);LuaRuntime::SetGameBindings(
   ownerSlotAddress,0);LuaRuntime::ObserveGameThread();
 Files files(true);SetSessionSaveFilePort(&files);
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 SetEntityPlayerHasCollectibleHostImplementation(&Has);
 SetRepentogonPlayerManagerTrinketHost(&Trinket);
 const auto players=isaac::runtime::ResolveEnginePlayerArray();
 assert(players.readable&&players.count==1);
 const char* script=R"lua(
assert(PlayerManager.AnyoneHasCollectible(5,false))
assert(not PlayerManager.AnyoneHasCollectible(6,false))
assert(PlayerManager.AnyoneHasTrinket(7,true))
assert(not PlayerManager.AnyoneHasTrinket(8,true))
assert(not pcall(function()PlayerManager.AnyoneHasCollectible(-1)end))
assert(not pcall(function()PlayerManager.AnyoneHasCollectible(1,1)end))
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@player-manager.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(LuaRuntime::ShutdownForModReload());
 repentogon::SetNativePort(nullptr);
 SetEntityPlayerHasCollectibleHostImplementation(nullptr);SetRepentogonPlayerManagerTrinketHost(nullptr);
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
