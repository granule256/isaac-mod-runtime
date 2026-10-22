#include "interfaces/lua/api600_grid_methods.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api500_config.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <array>
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
struct Layout{std::uintptr_t offset;std::array<std::uint8_t,16> bytes;};
constexpr Layout kLayouts[]={
{0x385f7c,{0x88,0x29,0x0,0x90,0x8,0x41,0x0,0x91,0x1,0xac,0x1,0xb9,0x8,0xd9,0x61,0xb8}},
{0x66e4,{0x60,0x52,0x3,0x91,0x7f,0xb2,0x0,0xb9,0x7f,0x5e,0x0,0xf9,0x7f,0xc2,0x0,0xb9}},
{0x34dae0,{0xb,0x0,0xb,0x8b,0x7f,0x7d,0x0,0xa9,0x8a,0x10,0x8e,0x52,0x8a,0x6,0xa0,0x72}},
{0x34dad0,{0x15,0x0,0xa,0x8b,0xbf,0x2,0x0,0xb9,0x1f,0x61,0x0,0x39,0x1f,0x1,0x0,0xb9}},
{0x392e68,{0x1a,0x80,0x6,0x91,0xf3,0x3,0x0,0xaa,0x41,0x28,0x0,0xf0,0x21,0x1c,0xa,0x91}},
{0x3e1200,{0xe2,0x3,0x14,0x2a,0xbf,0x6a,0xa,0x94,0x8,0xf4,0x40,0xb9,0x1f,0x1,0x0,0x71}},
};
api100_native::Cache g_Layouts[6]{};
void Guard(lua_State*L,unsigned n){const auto&g=kLayouts[n];static_cast<void>(api100_native::Resolve(L,{g.offset,g.bytes.data()},g_Layouts[n]));}
template<class T>T Read(lua_State*L,std::uintptr_t p,unsigned o){T v{};if(!engine_memory::ReadField(p,o,&v,engine_memory::EngineMemoryReadable))luaL_error(L,"api600 native field is not readable");return v;}
std::uintptr_t Grid(lua_State*L,std::uintptr_t vt){const auto p=ResolveEngineReceiver(L,FieldReceipt::GridEntity,1);if(!p||Read<std::uintptr_t>(L,p,0)!=LuaRuntime::EngineModuleBase()+vt)luaL_error(L,"GridEntity reference expired or wrong family");return p;}
std::uintptr_t Door(lua_State*L){const auto p=Grid(L,kGridEntity_DoorVtableOffset);Guard(L,0);return p;}
int GameField(lua_State*L,unsigned o,unsigned g){luaL_checkudata(L,1,LuaRuntime::kGameMetatable);const auto p=ResolveEngineReceiver(L,FieldReceipt::Level,1);if(!p)luaL_error(L,"Game reference is no longer available");Guard(L,g);lua_pushinteger(L,Read<std::int32_t>(L,p,o));return 1;}
}
int Api600GridEntityDoorIsBusted(lua_State*L){const auto p=Door(L);lua_pushboolean(L,Read<std::uint8_t>(L,p,0x309)!=0);return 1;}
int Api600GridEntityDoorIsLocked(lua_State*L){const auto p=Door(L);const auto v=Read<std::uint32_t>(L,p,0xc);lua_pushboolean(L,v>=1&&v<=5);return 1;}
int Api600GridEntityDoorIsKeyFamiliarTarget(lua_State*L){const auto p=Door(L);lua_pushboolean(L,Read<std::uint32_t>(L,p,0xc)==5);return 1;}
int Api600GridEntityDoorGetSpriteOffset(lua_State*L){const auto p=Door(L);Guard(L,1);PushGridVectorReference(L,p,0x11c);return 1;}
int Api600GridEntityRockGetRubbleAnim(lua_State*L){const auto p=Grid(L,kGridEntity_RockVtableOffset);Guard(L,4);Api500PushConfigString(L,p+0x1b8);std::size_t size{};const auto*text=lua_tolstring(L,-1,&size);const auto*zero=static_cast<const char*>(std::memchr(text,0,size));if(zero){lua_pushlstring(L,text,static_cast<std::size_t>(zero-text));lua_remove(L,-2);}return 1;}
int Api600GameGetLastDevilRoomStage(lua_State*L){return GameField(L,0x26fa5c,2);}
int Api600GameGetLastLevelWithDamage(lua_State*L){return GameField(L,0x2f002c,3);}
int Api600GameGetLastLevelWithoutHalfHp(lua_State*L){return GameField(L,0x2f0020,3);}
int Api600RoomGetDeliriumDistance(lua_State*L){
 luaL_checkudata(L,1,LuaRuntime::kRoomMetatable);const auto room=ResolveEngineReceiver(L,FieldReceipt::Room,1);if(!room)luaL_error(L,"Room reference is no longer available");Guard(L,5);
 const auto desc=Read<std::uintptr_t>(L,room,8);lua_pushinteger(L,desc?Read<std::int32_t>(L,desc,0xf4):0);return 1;
}

}
