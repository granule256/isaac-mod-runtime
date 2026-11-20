"""EntityPlayer extension methods validate player identity and native results."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = PREFIX + r'''
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/api600_player.hpp"
#include "interfaces/lua/api600_player.guards.hpp"
#include "interfaces/lua/api700_player.guards.hpp"
#include "interfaces/lua/repentogon_player_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <vector>
#include <thread>
#include "interfaces/lua/entity_lifetime.hpp"
static std::vector<unsigned char> moduleBytes,player;
static int calls;
static std::int64_t Health(void* p){assert(p==player.data());++calls;return 4;}
static std::uintptr_t Marked(void* p){assert(p==player.data());++calls;return reinterpret_cast<std::uintptr_t>(player.data());}
static std::int64_t Local(void* p){assert(p==player.data());++calls;return 1;}
static isaac::runtime::Api600MultiShotParams Multi(void* p,std::int32_t weapon){
 assert(p==player.data()&&weapon==1);++calls;
 isaac::runtime::Api600MultiShotParams value{};
 const std::int16_t tears=5;
 const std::int16_t lanes=37;
 const std::int32_t eyes=2;
 const float eyeAngle=17.5F;
 const float spreadAngle=2.5F;
 const std::int16_t randomTears=3;
 std::memcpy(value.bytes+0x00,&tears,sizeof(tears));
 std::memcpy(value.bytes+0x02,&lanes,sizeof(lanes));
 std::memcpy(value.bytes+0x04,&spreadAngle,sizeof(spreadAngle));
 std::memcpy(value.bytes+0x14,&eyes,sizeof(eyes));
 std::memcpy(value.bytes+0x18,&eyeAngle,sizeof(eyeAngle));
 value.bytes[0x1c]=1;
 std::memcpy(value.bytes+0x20,&randomTears,sizeof(randomTears));
 return value;
}
static int Mutate(lua_State*){
 const std::int32_t id=93,type=1,purity=0;const std::uint32_t eye=7;
 std::memcpy(player.data()+0x1c10,&id,4);std::memcpy(player.data()+0x1c14,&type,4);
 std::memcpy(player.data()+0x1da4,&purity,4);std::memcpy(player.data()+0x1d28,&eye,4);
 return 0;
}
static int Retire(lua_State*){RetireEntityLifetime(reinterpret_cast<std::uintptr_t>(player.data()));return 0;}
static int ShortParams(lua_State* state){
 lua_newuserdata(state,1);luaL_getmetatable(state,"IsaacRuntime.MultiShotParams");lua_setmetatable(state,-2);return 1;
}
static void Extensions(lua_State* state) noexcept{
 isaac::runtime::PushEntityCallbackArgument(state,reinterpret_cast<std::uintptr_t>(player.data()));
 lua_setglobal(state,"player");
 lua_pushcfunction(state,Mutate);lua_setglobal(state,"_mutate");
 lua_pushcfunction(state,Retire);lua_setglobal(state,"_retire");
 lua_pushcfunction(state,ShortParams);lua_setglobal(state,"_shortParams");
}
int main(){
 moduleBytes.assign(kEntityPlayerVtableOffset+16,0);
 player.assign(0x3000,0);
 const auto base=reinterpret_cast<std::uintptr_t>(moduleBytes.data());
 const auto vptr=base+kEntityPlayerVtableOffset;
 std::memcpy(player.data(),&vptr,sizeof(vptr));
 const std::uint32_t playerType=kEntityTypePlayer;std::memcpy(player.data()+kEntityTypeOffset,&playerType,4);
 const std::int32_t pocketId=41,pocketType=2;std::memcpy(player.data()+0x1c10,&pocketId,4);std::memcpy(player.data()+0x1c14,&pocketType,4);
 std::memcpy(moduleBytes.data()+api600_player::kMultiGuardOffset,api600_player::kMultiGuard.data(),16);
 std::memcpy(moduleBytes.data()+api700_player::kPocketEntry.offset,api700_player::kPocketEntry.guard,16);
 const std::uint32_t deadEye=0xf0000001U;const std::int32_t purity=3;
 std::memcpy(player.data()+0x1d28,&deadEye,4);std::memcpy(player.data()+0x1da4,&purity,4);
 const unsigned char deadGuard[]={0x08,0x28,0x5d,0xb9,0xf3,0x03,0x00,0xaa,0x1f,0x1d,0x00,0x71,0x0c,0x01,0x00,0x54};
 const unsigned char purityGuard[]={0x08,0xa4,0x5d,0xb9,0xf3,0x03,0x00,0xaa,0x1f,0x11,0x00,0x71,0xab,0x00,0x00,0x54};
 std::memcpy(moduleBytes.data()+0x2fbf38,deadGuard,16);std::memcpy(moduleBytes.data()+0x29a9fc,purityGuard,16);
 LuaRuntime::SetEngineModuleBase(base);LuaRuntime::ObserveGameThread();
 Files files(true);SetSessionSaveFilePort(&files);
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 SetRepentogonPlayerGetHealthTypeHost(&Health);
 SetRepentogonPlayerGetMarkedTargetHost(&Marked);
 SetRepentogonPlayerIsLocalPlayerHost(&Local);
 SetApi600PlayerNativeTestBindings({{0,engine_call::AddressOfFunction(&Multi),0,0}});
 LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
 const char* script=R"lua(
assert(player:GetHealthType()==4)
assert(GetPtrHash(player:GetMarkedTarget())==GetPtrHash(player))
assert(player:IsLocalPlayer())
assert(player:GetDeadEyeCharge()==0xf0000001)
assert(player:GetPurityState()==3)
assert(not player:IsDead())
player:SetDead(true);assert(player:IsDead())
player:SetDead(false);assert(not player:IsDead())
assert(not pcall(function()player:SetDead(1)end))
local pocket=player:GetPocketItem(0)
assert(pocket:GetSlot()==41 and pocket:GetType()==2)
local params=player:GetMultiShotParams()
assert(params:GetNumTears()==5)
assert(params:GetNumLanesPerEye()==37)
assert(params:GetNumEyesActive()==2)
assert(params:GetMultiEyeAngle()==17.5)
assert(params:GetMultiEyeAngle(WeaponType.WEAPON_TEARS)==17.5)
assert(params:GetNumRandomDirTears()==3)
assert(params:GetSpreadAngle(WeaponType.WEAPON_TEARS)==2.5)
assert(params:IsCrossEyed()==true)
params:SetSpreadAngle(WeaponType.WEAPON_TEARS, 40)
assert(params:GetSpreadAngle(WeaponType.WEAPON_TEARS)==40)
params:SetNumTears(0x100000001)
assert(params:GetNumTears()==1)
local lanes=params.GetNumLanesPerEye
assert(not pcall(lanes,_shortParams()))
assert(not pcall(function()pocket:GetSlot(1)end))
assert(not pcall(function()pocket:GetType(1)end))
_mutate();assert(pocket:GetSlot()==93 and pocket:GetType()==1)
assert(player:GetPurityState()==0 and player:GetDeadEyeCharge()==7)
assert(params:GetNumLanesPerEye()==37)
assert(not pcall(function()player:GetHealthType(1)end))
assert(not pcall(function()player:GetMarkedTarget(1)end))
assert(not pcall(function()player:IsLocalPlayer(1)end))
local getSlot=pocket.GetSlot
_retire();assert(not pcall(getSlot,pocket))
assert(not pcall(function()player:GetDeadEyeCharge()end))
assert(not pcall(function()player:GetPurityState()end))
assert(not pcall(function()player:SetDead(true)end))
assert(params:GetNumLanesPerEye()==37)
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@player-extension.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 assert(calls==4);
 std::thread worker([]{
  auto* isolated=luaL_newstate();
  for(auto function:{RepentogonEntityPlayerGetDeadEyeCharge,RepentogonEntityPlayerGetPurityState,RepentogonEntitySetDead}){
   lua_pushcfunction(isolated,function);assert(lua_pcall(isolated,0,0,0)!=LUA_OK);
   assert(std::strstr(lua_tostring(isolated,-1),"game thread"));lua_pop(isolated,1);
  }
  lua_close(isolated);
 });worker.join();
 assert(LuaRuntime::ShutdownForModReload());
 SetRepentogonPlayerGetHealthTypeHost(nullptr);SetRepentogonPlayerGetMarkedTargetHost(nullptr);
 SetRepentogonPlayerIsLocalPlayerHost(nullptr);repentogon::SetNativePort(nullptr);
 SetApi600PlayerNativeTestBindings({{0,0,0,0}});
 SetSessionSaveFilePort(nullptr);LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
}
'''


class RepentogonPlayerApiTests(unittest.TestCase):
    def test_native_getters_and_argument_gate(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-player-api-') as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
