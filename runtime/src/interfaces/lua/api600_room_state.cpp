#include "interfaces/lua/api600_room_state.hpp"
#include "interfaces/lua/api600_room_state.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
namespace G=api600_room_state;
constexpr api100_native::Entry kLayouts[]={{G::kInitGuardOffset,G::kInitGuard.data()},{G::kUpdateGuardOffset,G::kUpdateGuard.data()},{G::kDeathGuardOffset,G::kDeathGuard.data()}};
api100_native::Cache g_Cache[3]{};
void Guard(lua_State*L,unsigned i){static_cast<void>(api100_native::Resolve(L,kLayouts[i],g_Cache[i]));}
std::uintptr_t Room(lua_State*L){luaL_checkudata(L,1,LuaRuntime::kRoomMetatable);const auto p=ResolveEngineReceiver(L,FieldReceipt::Room,1);if(!p)luaL_error(L,"Room reference is no longer available");Guard(L,0);Guard(L,1);return p;}
template<class T>T Read(lua_State*L,std::uintptr_t p,unsigned offset){T value{};if(!engine_memory::ReadField(p,offset,&value,engine_memory::EngineMemoryReadable))luaL_error(L,"Room state is not readable");return value;}
template<class T>void Write(lua_State*L,std::uintptr_t p,unsigned offset,const T&value){if(!engine_memory::WriteField(p,offset,value,engine_memory::EngineMemoryWritable))luaL_error(L,"Room state is not writable");}
std::int32_t Int(lua_State*L,int i){const auto u=static_cast<std::uint32_t>(luaL_checkinteger(L,i));std::int32_t value{};std::memcpy(&value,&u,4);return value;}
}
// NS Init的x21=Room+76c8；不是把PC偏移加一个猜测出来的全局差值。
int Api600RoomGetShopLevel(lua_State*L){const auto p=Room(L);lua_pushinteger(L,Read<std::int32_t>(L,p,0x76c8));return 1;}
// Update sp+38保存Room+76cc；+8d4是真正更新并夹取的lava强度。
int Api600RoomGetLavaIntensity(lua_State*L){const auto p=Room(L);lua_pushnumber(L,Read<float>(L,p,0x7fa0));return 1;}
int Api600RoomHasSlowDown(lua_State*L){const auto p=Room(L);lua_pushboolean(L,Read<std::int32_t>(L,p,0x78f0)>0);return 1;}
int Api600RoomSetSlowDown(lua_State*L){const auto p=Room(L);const auto duration=Int(L,2);const auto current=Read<std::int32_t>(L,p,0x78f0);if(duration>current)Write(L,p,0x78f0,duration);return 0;}
// NPC trigger_death_remove同首杀道具分支读取/置1；Init清同字节。
int Api600RoomIsFirstEnemyDead(lua_State*L){const auto p=Room(L);Guard(L,2);lua_pushboolean(L,Read<std::uint8_t>(L,p,0x7964)!=0);return 1;}
int Api600RoomSetFirstEnemyDead(lua_State*L){const auto p=Room(L);Guard(L,2);Write(L,p,0x7964,static_cast<std::uint8_t>(lua_toboolean(L,2)!=0));return 0;}
// Update对该位消费：对Pickup/NPC调用UpdatePickupGhosts，再清0。
int Api600RoomInvalidatePickupVision(lua_State*L){const auto p=Room(L);Write(L,p,0x8160,std::uint8_t{1});return 0;}
// 原PC448050仅赋两个计数，不夹取；Update按Duration递减、按Count生成血迹。
int Api600RoomEmitBloodFromWalls(lua_State*L){const auto p=Room(L);const auto duration=Int(L,2),count=Int(L,3);Write(L,p,0x78d8,duration);Write(L,p,0x78dc,count);return 0;}
}
