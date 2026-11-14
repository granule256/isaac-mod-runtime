#include "interfaces/lua/repentogon_player_api.hpp"
#include "interfaces/lua/api100_native.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstdint>
#include <cstring>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {
// Native Add/ClearDeadEyeCharge and update_purity_sprite identify these fields.
constexpr std::uint8_t kDeadEyeGuard[]={0x08,0x28,0x5d,0xb9,0xf3,0x03,0x00,0xaa,0x1f,0x1d,0x00,0x71,0x0c,0x01,0x00,0x54};
constexpr std::uint8_t kPurityGuard[]={0x08,0xa4,0x5d,0xb9,0xf3,0x03,0x00,0xaa,0x1f,0x11,0x00,0x71,0xab,0x00,0x00,0x54};
api100_native::Cache g_DeadEyeLayout{},g_PurityLayout{};
#if defined(__SWITCH__)
struct Method {
    std::uintptr_t offset;
    std::array<std::uint8_t, 16> guard;
};
constexpr Method kHealthType{0x27d3a4,{0x08,0x38,0x57,0xb9,0x08,0x11,0x00,0x51,0x1f,0x91,0x00,0x71,0xa8,0x01,0x00,0x54}};
constexpr Method kMarkedTarget{0x2b7ffc,{0x00,0xcc,0x4b,0xf9,0xc0,0x03,0x5f,0xd6,0xff,0x83,0x06,0xd1,0xfd,0x7b,0x16,0xa9}};
constexpr Method kIsLocalPlayer{0x27cf3c,{0x20,0x00,0x80,0x52,0xc0,0x03,0x5f,0xd6,0xfd,0x7b,0xbe,0xa9,0xf3,0x0b,0x00,0xf9}};
constexpr Method kAddActiveCharge{0x2ac41c,{0xff,0x43,0x02,0xd1,0xfd,0x7b,0x03,0xa9,0xfd,0xc3,0x00,0x91,0xfc,0x6f,0x04,0xa9}};
#else
RepentogonPlayerIntHost g_HealthTypeHost{};
RepentogonPlayerPointerHost g_MarkedTargetHost{};
RepentogonPlayerIntHost g_IsLocalPlayerHost{};
RepentogonPlayerAddActiveChargeHost g_AddActiveChargeHost{};
#endif

std::uintptr_t Player(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread())
        luaL_error(state, "EntityPlayer native access requires the game thread");
    const auto player=ResolveEngineReceiver(state,FieldReceipt::EntityPlayer,1);
    if (!player) luaL_error(state, "EntityPlayer is no longer available");
    return player;
}

#if defined(__SWITCH__)
std::uintptr_t MethodAddress(lua_State* state,const Method& method,const char* name) {
    const auto base=LuaRuntime::EngineModuleBase();
    if (!base || base>UINTPTR_MAX-method.offset ||
        !engine_memory::EngineMemoryReadable(base+method.offset,method.guard.size()) ||
        std::memcmp(engine_memory::AsObject(base+method.offset),method.guard.data(),method.guard.size())!=0)
        luaL_error(state,"EntityPlayer:%s native binding is unavailable",name);
    return base+method.offset;
}
#endif

bool OptionalBoolean(lua_State* state, int index, bool fallback) {
    if (lua_isnoneornil(state, index)) return fallback;
    return lua_toboolean(state, index) != 0;
}
}

int RepentogonEntityPlayerGetHealthType(lua_State* state) {
    if (lua_gettop(state)!=1) return luaL_error(state,"EntityPlayer:GetHealthType accepts no arguments");
    const auto player=Player(state);
    std::int32_t value=0;
#if defined(__SWITCH__)
    using Fn=std::int32_t (*)(void*);
    value=engine_call::AsFunction<Fn>(MethodAddress(state,kHealthType,"GetHealthType"))(
        engine_memory::AsObject(player));
#else
    if (!g_HealthTypeHost) return luaL_error(state,"EntityPlayer:GetHealthType host binding is unavailable");
    value=static_cast<std::int32_t>(g_HealthTypeHost(engine_memory::AsObject(player)));
#endif
    lua_pushinteger(state,value);
    return 1;
}

int RepentogonEntityPlayerGetMarkedTarget(lua_State* state) {
    if (lua_gettop(state)!=1) return luaL_error(state,"EntityPlayer:GetMarkedTarget accepts no arguments");
    const auto player=Player(state);
    std::uintptr_t target=0;
#if defined(__SWITCH__)
    using Fn=std::uintptr_t (*)(void*);
    target=engine_call::AsFunction<Fn>(MethodAddress(state,kMarkedTarget,"GetMarkedTarget"))(
        engine_memory::AsObject(player));
#else
    if (!g_MarkedTargetHost) return luaL_error(state,"EntityPlayer:GetMarkedTarget host binding is unavailable");
    target=g_MarkedTargetHost(engine_memory::AsObject(player));
#endif
    if (!target) {
        lua_pushnil(state);
        return 1;
    }
    PushEntityCallbackArgument(state,target);
    if (lua_isnil(state,-1)) return luaL_error(state,"EntityPlayer marked target is no longer available");
    return 1;
}

int RepentogonEntityPlayerIsLocalPlayer(lua_State* state) {
    if (lua_gettop(state)!=1) return luaL_error(state,"EntityPlayer:IsLocalPlayer accepts no arguments");
    const auto player=Player(state);
    std::int32_t value=0;
#if defined(__SWITCH__)
    using Fn=std::int32_t (*)(void*);
    value=engine_call::AsFunction<Fn>(MethodAddress(state,kIsLocalPlayer,"IsLocalPlayer"))(
        engine_memory::AsObject(player));
#else
    if (!g_IsLocalPlayerHost) return luaL_error(state,"EntityPlayer:IsLocalPlayer host binding is unavailable");
    value=static_cast<std::int32_t>(g_IsLocalPlayerHost(engine_memory::AsObject(player)));
#endif
    lua_pushboolean(state,value!=0);
    return 1;
}

int RepentogonEntityPlayerGetDeadEyeCharge(lua_State* state) {
    const auto player=Player(state);
    static_cast<void>(api100_native::Resolve(state,{0x2fbf38,kDeadEyeGuard},g_DeadEyeLayout));
    std::uint32_t value{};
    if (!engine_memory::ReadField(player,0x1d28,&value,engine_memory::EngineMemoryReadable))
        return luaL_error(state,"EntityPlayer Dead Eye charge is not readable");
    lua_pushinteger(state,value);return 1;
}

int RepentogonEntityPlayerGetPurityState(lua_State* state) {
    const auto player=Player(state);
    static_cast<void>(api100_native::Resolve(state,{0x29a9fc,kPurityGuard},g_PurityLayout));
    std::int32_t value{};
    if (!engine_memory::ReadField(player,0x1da4,&value,engine_memory::EngineMemoryReadable))
        return luaL_error(state,"EntityPlayer Purity state is not readable");
    lua_pushinteger(state,value);return 1;
}

int RepentogonEntityPlayerAddActiveCharge(lua_State* state) {
    const auto player=Player(state);
    const int argumentCount=lua_gettop(state);
    if (argumentCount<2)
        return luaL_error(
            state,
            "EntityPlayer:AddActiveCharge expects Charge and optional Slot, FlashHUD, Overcharge, Force");
    const auto charge=static_cast<std::int32_t>(luaL_checkinteger(state,2));
    const auto slot=luaL_optinteger(state,3,0);
    if (slot>3)
        return luaL_argerror(state,3,"Invalid ActiveSlot");
    const bool flashHUD=OptionalBoolean(state,4,true);
    const bool overcharge=OptionalBoolean(state,5,false);
    const bool force=OptionalBoolean(state,6,false);
    const auto invoke=[&](std::int32_t targetSlot)->std::int32_t {
#if defined(__SWITCH__)
        using Fn=std::int32_t (*)(void*,std::int32_t,std::int32_t,bool,bool,bool);
        return engine_call::AsFunction<Fn>(
            MethodAddress(state,kAddActiveCharge,"AddActiveCharge"))(
                engine_memory::AsObject(player),charge,targetSlot,
                flashHUD,overcharge,force);
#else
        if (!g_AddActiveChargeHost) {
            luaL_error(state,"EntityPlayer:AddActiveCharge host binding is unavailable");
            return 0;
        }
        return g_AddActiveChargeHost(
            engine_memory::AsObject(player),charge,targetSlot,
            flashHUD,overcharge,force);
#endif
    };
    std::int32_t added=0;
    if (slot<0) {
        // REPENTOGON patches the native negative-slot loop because the game
        // forwards its booleans in the wrong order. Re-enter the native
        // single-slot method in the correct order and keep its return sum.
        for (std::int32_t targetSlot=0;targetSlot<4;++targetSlot)
            added+=invoke(targetSlot);
    } else {
        added=invoke(static_cast<std::int32_t>(slot));
    }
    lua_pushinteger(state,added);
    return 1;
}

int RepentogonEntitySetDead(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread())
        return luaL_error(state,"Entity:SetDead requires the game thread");
    const auto entity=EntityPointerArgument(state,1);
    if (!entity) return luaL_argerror(state,1,"live Entity expected");
    if (!lua_isboolean(state,2)) return luaL_argerror(state,2,"boolean expected");
    const auto dead=static_cast<std::uint8_t>(lua_toboolean(state,2)!=0);
    if (!engine_memory::WriteField(entity,0x1c3,dead,engine_memory::EngineMemoryWritable))
        return luaL_error(state,"Entity dead flag is not writable");
    return 0;
}

#if !defined(__SWITCH__)
void SetRepentogonPlayerGetHealthTypeHost(RepentogonPlayerIntHost value) noexcept {g_HealthTypeHost=value;}
void SetRepentogonPlayerGetMarkedTargetHost(RepentogonPlayerPointerHost value) noexcept {g_MarkedTargetHost=value;}
void SetRepentogonPlayerIsLocalPlayerHost(RepentogonPlayerIntHost value) noexcept {g_IsLocalPlayerHost=value;}
void SetRepentogonPlayerAddActiveChargeHost(
    RepentogonPlayerAddActiveChargeHost value) noexcept {g_AddActiveChargeHost=value;}
#endif
}
