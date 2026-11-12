#include "interfaces/lua/repentogon_room_mutations.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr std::uint8_t kRemoveGuard[]={0x3f,0xfc,0x06,0x71,0x08,0x01,0x00,0x54,0x09,0x4c,0x21,0x8b,0x28,0x0d,0x43,0xf8};
constexpr std::uint8_t kBackdropGuard[]={0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf5,0x13,0x00,0xf9};
api100_native::Cache g_Remove{},g_Backdrop{};
#if !defined(__SWITCH__)
RepentogonRoomMutationNativeTestBindings g_Host{};
#endif
std::uintptr_t Room(lua_State* L) {
    if(!LuaRuntime::IsOnGameThread())luaL_error(L,"Room mutation requires the game thread");
    luaL_checkudata(L,1,LuaRuntime::kRoomMetatable);
    const auto room=ResolveEngineReceiver(L,FieldReceipt::Room,1);
    if(!room)luaL_error(L,"Room reference is no longer available");
    return room;
}
}
int RepentogonRoomRemoveGridEntityImmediate(lua_State* L) {
    const auto room=Room(L);
    const auto index=static_cast<std::int32_t>(luaL_checkinteger(L,2));
    const auto trail=static_cast<std::int32_t>(luaL_checkinteger(L,3));
    const bool keep=lua_toboolean(L,4)!=0;
    std::uintptr_t host{};
#if !defined(__SWITCH__)
    if(!g_Host.removeGrid)return luaL_error(L,"Room grid removal host binding is unavailable");
    host=engine_call::AddressOfFunction(g_Host.removeGrid);
#endif
    using Fn=void(*)(void*,std::int32_t,std::int32_t,bool);
    engine_call::AsFunction<Fn>(api100_native::Resolve(L,{0x4883c0,kRemoveGuard},g_Remove,host))(
        engine_memory::AsObject(room),index,trail,keep);
    return 0;
}
int RepentogonRoomSetBackdropType(lua_State* L) {
    const auto room=Room(L);
    const auto id=luaL_checkinteger(L,2);
    if(id<0)return luaL_error(L,"Invalid backdrop id %I",id);
    const auto decoration=luaL_checkinteger(L,3);
    // Upstream's IDs above 60 require XMLData's custom-backdrop hook, not native fallback to Basement.
    if(id>60)return luaL_error(L,"Custom backdrop XMLData support is not available");
    constexpr std::uintptr_t offset=0x1fe0;
    if(room>UINTPTR_MAX-offset)return luaL_error(L,"Room backdrop address is invalid");
    std::uintptr_t host{};
#if !defined(__SWITCH__)
    if(!g_Host.initBackdrop)return luaL_error(L,"Room backdrop host binding is unavailable");
    host=engine_call::AddressOfFunction(g_Host.initBackdrop);
#endif
    using Fn=void(*)(void*,std::uint32_t,bool);
    engine_call::AsFunction<Fn>(api100_native::Resolve(L,{0x26e80,kBackdropGuard},g_Backdrop,host))(
        engine_memory::AsObject(room+offset),static_cast<std::uint32_t>(id),decoration!=0);
    return 0;
}
#if !defined(__SWITCH__)
void SetRepentogonRoomMutationNativeTestBindings(RepentogonRoomMutationNativeTestBindings value) noexcept {g_Host=value;}
#endif
}
