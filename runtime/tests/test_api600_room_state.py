"""Room8项状态：真实生产Lua方法、标量写入消费者、边界和模块换代。"""
import unittest
from .test_api500_world import run_world
MAIN=r'''
#include "interfaces/lua/api600_room_state.guards.hpp"
#include "interfaces/lua/api600_bindings.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static bool roomAvailable=true;
void* Api500WorldRoom(){return roomAvailable?g_RoomBytes.data():nullptr;}
void* Api500WorldPool(){return nullptr;}
int main(int argc,char**argv){static_cast<void>(argc);static_cast<void>(argv);static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();g_RoomBytes.resize(0x9000);FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
namespace G=api600_room_state;std::memcpy(g_ModuleBytes.data()+G::kInitGuardOffset,G::kInitGuard.data(),16);std::memcpy(g_ModuleBytes.data()+G::kUpdateGuardOffset,G::kUpdateGuard.data(),16);std::memcpy(g_ModuleBytes.data()+G::kDeathGuardOffset,G::kDeathGuard.data(),16);
WriteAt<std::int32_t>(g_RoomBytes,0x76c8,-7);WriteAt<float>(g_RoomBytes,0x7fa0,.625F);WriteAt<std::int32_t>(g_RoomBytes,0x78f0,-1);WriteAt<std::uint8_t>(g_RoomBytes,0x7964,0);WriteAt<std::uint8_t>(g_RoomBytes,0x8160,0);WriteAt<std::int32_t>(g_RoomBytes,0x78d8,0);WriteAt<std::int32_t>(g_RoomBytes,0x78dc,0);
auto expected=g_RoomBytes;WriteAt<std::int32_t>(expected,0x78f0,30);WriteAt<std::uint8_t>(expected,0x7964,0);WriteAt<std::uint8_t>(expected,0x8160,1);WriteAt<std::int32_t>(expected,0x78d8,-3);WriteAt<std::int32_t>(expected,0x78dc,1);
const char*script=R"lua(
local r=Game():GetRoom();assert(r:GetShopLevel()==-7 and r:GetLavaIntensity()==.625)
assert(not r:HasSlowDown());assert(select('#',r:SetSlowDown(30))==0 and r:HasSlowDown());r:SetSlowDown(4);r:SetSlowDown(-8);r:SetSlowDown(0x100000001);assert(r:HasSlowDown())
assert(not pcall(function()r:SetSlowDown(1.5)end));assert(not pcall(function()r:SetSlowDown({})end));assert(not pcall(function()r:SetSlowDown()end))
assert(not r:IsFirstEnemyDead());assert(select('#',r:SetFirstEnemyDead(true))==0 and r:IsFirstEnemyDead());r:SetFirstEnemyDead(false);assert(not r:IsFirstEnemyDead());r:SetFirstEnemyDead(0);assert(r:IsFirstEnemyDead());r:SetFirstEnemyDead({});assert(r:IsFirstEnemyDead());r:SetFirstEnemyDead(nil);assert(not r:IsFirstEnemyDead());r:SetFirstEnemyDead();assert(not r:IsFirstEnemyDead())
assert(select('#',r:InvalidatePickupVision())==0);assert(select('#',r:EmitBloodFromWalls(-3,0x100000001))==0)
assert(not pcall(function()r:EmitBloodFromWalls(1.5,2)end));assert(not pcall(function()r:EmitBloodFromWalls(1,{})end));assert(not pcall(function()r:EmitBloodFromWalls(1)end))
for _,n in ipairs({'GetShopLevel','GetLavaIntensity','HasSlowDown','SetSlowDown','IsFirstEnemyDead','SetFirstEnemyDead','InvalidatePickupVision','EmitBloodFromWalls'})do assert(type(r[n])=='function');assert(not pcall(function()r[n]({},1,2)end),n..' must validate receiver')end
)lua";
if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api600-room-state.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView errors[8]{};auto count=LuaRuntime::CopyLuaErrorHistory(errors,8);for(std::size_t i=0;i<count;++i)std::fprintf(stderr,"%s\n",errors[i].text);return 1;}
assert(g_RoomBytes==expected); // Only the original engine-consumed bytes may change.
auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));luaL_newmetatable(L,LuaRuntime::kRoomMetatable);lua_newtable(L);static_cast<void>(AttachApi600Methods(L,"Room"));lua_setfield(L,-2,"__index");lua_pop(L,1);static_cast<void>(lua_newuserdata(L,sizeof(std::uintptr_t)));luaL_getmetatable(L,LuaRuntime::kRoomMetatable);lua_setmetatable(L,-2);lua_setglobal(L,"r");
if(luaL_dostring(L,"assert(r:GetShopLevel()==-7 and r:HasSlowDown());r:SetSlowDown(40)")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 2;}
std::vector<unsigned char>other=g_ModuleBytes;other[G::kInitGuardOffset]^=1;const auto otherBase=AddressOf(other);LuaRuntime::SetEngineModuleBase(otherBase);
if(luaL_dostring(L,R"lua(for _,n in ipairs({'GetShopLevel','GetLavaIntensity','HasSlowDown','SetSlowDown','IsFirstEnemyDead','SetFirstEnemyDead','InvalidatePickupVision','EmitBloodFromWalls'})do local ok,e=pcall(function()r[n](r,1,2)end);assert(not ok and e:find('guard'),n..':'..tostring(e))end)lua")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 3;}
LuaRuntime::SetEngineModuleBase(g_EngineBase);roomAvailable=false;
if(luaL_dostring(L,"local ok,e=pcall(function()return r:GetShopLevel()end);assert(not ok and e:find('reference'))")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 4;}
lua_close(L);return 0;}
'''
class RoomStateConsumer(unittest.TestCase):
 def test_public_room_state(self):
  r=run_world(main=MAIN);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
