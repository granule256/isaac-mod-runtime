#include "interfaces/lua/repentogon_entity_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/pickup_flip_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "lua_object_handles.hpp"
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
#if defined(__SWITCH__)
constexpr std::uint8_t kGiveMinecartGuard[]={0xff,0x03,0x01,0xd1,0xfd,0x7b,0x01,0xa9,0xfd,0x43,0x00,0x91,0xf6,0x57,0x02,0xa9};
#endif
constexpr std::uintptr_t kEntityMinecartHandleOffset=0x3c8;
constexpr std::uintptr_t kEntitySlotPrizeCollectibleOffset=0x570;
constexpr std::uintptr_t kEntityPickupCycleCountOffset=0x604;
constexpr std::uintptr_t kEntityPickupCycleListOffset=0x5e4;
constexpr std::uintptr_t kEntityPickupFlipStateOffset=0x610;
constexpr std::uintptr_t kEntityPickupFlipSubtype=0x8;
// handle_collision +0x5e0 -> QueueItem arg4; DropCollectible restores it from the active slot.
constexpr std::uintptr_t kEntityPickupVarDataOffset=0x5e0;
constexpr std::uint32_t kEntityTypeSlot=6;
constexpr std::uint32_t kEntityPickupVariantCollectible=100;

std::uintptr_t Entity(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread())luaL_error(state,"Entity native access requires the game thread");
    const auto entity=EntityPointerArgument(state,1);
    if (!entity)luaL_argerror(state,1,"live Entity expected");
    return entity;
}

std::uintptr_t TypedEntity(lua_State* state,std::uintptr_t vtableOffset,std::uint32_t type,
                           const char* name) {
    const auto entity=Entity(state);
    const auto base=LuaRuntime::EngineModuleBase();
    std::uintptr_t vtable{};
    std::uint32_t actualType{};
    if (!base||base>UINTPTR_MAX-vtableOffset||
        !engine_memory::ReadField(entity,0,&vtable,engine_memory::EngineMemoryReadable)||
        vtable!=base+vtableOffset||
        !engine_memory::ReadField(entity,kEntityTypeOffset,&actualType,engine_memory::EngineMemoryReadable)||
        actualType!=type)luaL_error(state,"%s receiver is no longer available",name);
    return entity;
}

std::uintptr_t Pickup(lua_State* state) {
    return TypedEntity(state,kEntityPickupVtableOffset,kEntityTypePickup,"EntityPickup");
}

std::uintptr_t Slot(lua_State* state) {
    return TypedEntity(state,kEntitySlotVtableOffset,kEntityTypeSlot,"EntitySlot");
}

#if defined(__SWITCH__)
void Guard(lua_State* state,std::uintptr_t offset,const std::uint8_t* expected,const char* name) {
    const auto base=LuaRuntime::EngineModuleBase();
    if(!base||base>UINTPTR_MAX-offset-16||
       !engine_memory::EngineMemoryReadable(base+offset,16)||
       std::memcmp(engine_memory::AsObject(base+offset),expected,16)!=0)
        luaL_error(state,"%s native binding is unavailable",name);
}
#endif

template<class T>T Read(lua_State* state,std::uintptr_t object,std::uintptr_t offset,const char* name) {
    T value{};
    if(!engine_memory::ReadField(object,offset,&value,engine_memory::EngineMemoryReadable))
        luaL_error(state,"%s is not readable",name);
    return value;
}

void PushEntity(lua_State* state,std::uintptr_t entity) {
    if(!entity||!IsLiveEntityPointer(entity)){lua_pushnil(state);return;}
    PushEntityCallbackArgument(state,entity);
    if(lua_isnil(state,-1))luaL_error(state,"returned Entity is no longer available");
}

#if !defined(__SWITCH__)
RepentogonEntityNativeTestBindings g_Tests{};
#endif
}

int RepentogonEntitySetInvincible(lua_State* state) {
    const auto entity=Entity(state);
    if (!lua_isboolean(state,2)) return luaL_argerror(state,2,"boolean expected");
    const auto value=static_cast<std::uint8_t>(lua_toboolean(state,2)!=0);
    if (!engine_memory::WriteField(entity,kEntityIsInvincibleOffset,value,
                                   engine_memory::EngineMemoryWritable))
        return luaL_error(state,"Entity invincibility flag is not writable");
    return 0;
}

int RepentogonEntityGiveMinecart(lua_State* state) {
    const auto entity=Entity(state);
    if(lua_gettop(state)!=3)return luaL_error(state,"Entity:GiveMinecart expects position and velocity");
    const auto position=*RequireVectorArgument(state,2);
    const auto velocity=*RequireVectorArgument(state,3);
    void* result{};
#if defined(__SWITCH__)
    Guard(state,0x6745c,kGiveMinecartGuard,"Entity:GiveMinecart");
    using Fn=void*(*)(void*,const LuaRuntime::VectorHandle&,const LuaRuntime::VectorHandle&);
    result=engine_call::AsFunction<Fn>(LuaRuntime::EngineModuleBase()+0x6745c)(
        engine_memory::AsObject(entity),position,velocity);
#else
    if(!g_Tests.giveMinecart)return luaL_error(state,"Entity:GiveMinecart host binding is unavailable");
    const RepentogonEntityVector p{position.x,position.y};
    const RepentogonEntityVector v{velocity.x,velocity.y};
    result=g_Tests.giveMinecart(engine_memory::AsObject(entity),p,v);
#endif
    PushEntity(state,engine_memory::AddressOf(result));return 1;
}

int RepentogonEntityGetMinecart(lua_State* state) {
    const auto entity=Entity(state);
    const auto value=Read<std::uintptr_t>(state,entity,kEntityMinecartHandleOffset,"Entity minecart handle");
    PushEntity(state,value);return 1;
}

int RepentogonEntityToSlot(lua_State* state) {
    const auto entity=Entity(state);
    const auto base=LuaRuntime::EngineModuleBase();
    std::uintptr_t vtable{};
    std::uint32_t type{};
    if(!base||!engine_memory::ReadField(entity,0,&vtable,engine_memory::EngineMemoryReadable)||
       !engine_memory::ReadField(entity,kEntityTypeOffset,&type,engine_memory::EngineMemoryReadable)||
       type!=kEntityTypeSlot||vtable!=base+kEntitySlotVtableOffset){lua_pushnil(state);return 1;}
    PushEntityCallbackArgument(state,entity);return 1;
}

int RepentogonEntitySlotGetPrizeCollectible(lua_State* state) {
    const auto slot=Slot(state);
    if(lua_gettop(state)!=1)return luaL_error(state,"EntitySlot:GetPrizeCollectible accepts no arguments");
    lua_pushinteger(state,Read<std::int32_t>(state,slot,kEntitySlotPrizeCollectibleOffset,"EntitySlot prize collectible"));
    return 1;
}

int RepentogonEntityPickupGetCollectibleCycle(lua_State* state) {
    const auto pickup=Pickup(state);
    if(lua_gettop(state)!=1)return luaL_error(state,"EntityPickup:GetCollectibleCycle accepts no arguments");
    const auto count=Read<std::uint32_t>(state,pickup,kEntityPickupCycleCountOffset,"EntityPickup cycle count");
    if(count>8)return luaL_error(state,"EntityPickup cycle count is invalid");
    std::int32_t values[8]{};
    if(!engine_memory::ReadField(pickup,kEntityPickupCycleListOffset,&values,
                                  engine_memory::EngineMemoryReadable))
        return luaL_error(state,"EntityPickup cycle list is not readable");
    lua_createtable(state,static_cast<int>(count),0);
    for(std::uint32_t i=0;i<count;++i){lua_pushinteger(state,values[i]);lua_rawseti(state,-2,static_cast<lua_Integer>(i+1));}
    return 1;
}

int RepentogonEntityPickupGetVarData(lua_State* state) {
    const auto pickup=Pickup(state);
    lua_pushinteger(state,Read<std::int32_t>(state,pickup,kEntityPickupVarDataOffset,
                                           "EntityPickup VarData"));
    return 1;
}

int RepentogonEntityPickupSetVarData(lua_State* state) {
    const auto pickup=Pickup(state);
    const auto value=static_cast<std::int32_t>(luaL_checkinteger(state,2));
    if(!engine_memory::WriteField(pickup,kEntityPickupVarDataOffset,value,
                                  engine_memory::EngineMemoryWritable))
        return luaL_error(state,"EntityPickup VarData is not writable");
    return 0;
}

int RepentogonEntityPickupAddCollectibleCycle(lua_State* state) {
    const auto pickup=Pickup(state);
    const auto id=static_cast<std::int32_t>(luaL_checkinteger(state,2));
    if(!CollectibleConfigExistsForApi(id))
        return luaL_argerror(state,2,lua_pushfstring(state,"Invalid collectible ID %d",static_cast<int>(id)));
    const auto count=Read<std::uint32_t>(state,pickup,kEntityPickupCycleCountOffset,
                                       "EntityPickup cycle count");
    if(count>=8){lua_pushboolean(state,0);return 1;}
    const auto offset=kEntityPickupCycleListOffset+count*sizeof(std::int32_t);
    // Check both writes before changing either field; publish count after the entry.
    if(!engine_memory::EngineMemoryWritable(pickup+offset,sizeof(id))||
       !engine_memory::EngineMemoryWritable(pickup+kEntityPickupCycleCountOffset,sizeof(count))||
       !engine_memory::WriteField(pickup,offset,id,engine_memory::EngineMemoryWritable)||
       !engine_memory::WriteField(pickup,kEntityPickupCycleCountOffset,count+1,
                                  engine_memory::EngineMemoryWritable))
        return luaL_error(state,"EntityPickup cycle list is not writable");
    lua_pushboolean(state,1);return 1;
}

int RepentogonEntityPickupRemoveCollectibleCycle(lua_State* state) {
    const auto pickup=Pickup(state);
    if(lua_gettop(state)!=1)return luaL_error(state,"EntityPickup:RemoveCollectibleCycle accepts no arguments");
    const std::array<std::int32_t,7> zero{};
    if(!engine_memory::WriteField(pickup,kEntityPickupCycleListOffset,zero,
                                  engine_memory::EngineMemoryWritable)||
       !engine_memory::WriteField(pickup,kEntityPickupCycleCountOffset,std::uint32_t{},
                                  engine_memory::EngineMemoryWritable))
        return luaL_error(state,"EntityPickup cycle list is not writable");
    return 0;
}

int RepentogonEntityPickupGetFlipCollectible(lua_State* state) {
    const auto pickup=Pickup(state);
    std::uint32_t variant{};
    const auto save=Read<std::uintptr_t>(state,pickup,kEntityPickupFlipStateOffset,"EntityPickup flip state");
    if(!engine_memory::ReadField(pickup,kEntityVariantOffset,&variant,engine_memory::EngineMemoryReadable)||
       variant!=kEntityPickupVariantCollectible||!save){lua_pushnil(state);return 1;}
    lua_pushinteger(state,Read<std::int32_t>(state,save,kEntityPickupFlipSubtype,"EntityPickup flip subtype"));
    return 1;
}

int RepentogonEntityPickupGetCanRerollOverride(lua_State* state) {
    const auto pickup=Pickup(state);
    bool value{};
    if (TryPickupRerollOverride(pickup,&value)) lua_pushboolean(state,value);
    else lua_pushnil(state);
    return 1;
}

int RepentogonEntityPickupSetCanRerollOverride(lua_State* state) {
    const auto pickup=Pickup(state);
    if (lua_isnil(state,2)) return luaL_argerror(state,2,"non-nil value expected");
    SetPickupRerollOverride(state,pickup,lua_toboolean(state,2)?2:1);
    return 0;
}

int RepentogonEntityPickupClearCanRerollOverride(lua_State* state) {
    SetPickupRerollOverride(state,Pickup(state),0);
    return 0;
}

int RepentogonEntityPickupInitFlipState(lua_State* state) {
    const auto pickup=Pickup(state);
    const auto arguments=lua_gettop(state);
    if(arguments>3)return luaL_error(state,"EntityPickup:InitFlipState accepts up to two arguments");
    const auto collectible=arguments>=2&&!lua_isnil(state,2)
        ?static_cast<std::int32_t>(luaL_checkinteger(state,2)):0;
    const bool setupGraphics=arguments<3||lua_isnil(state,3)||lua_toboolean(state,3)!=0;
    switch(pickup_flip::InitializeFlipState(engine_memory::AsObject(pickup),collectible,setupGraphics)) {
        case pickup_flip::InitResult::Success:
        case pickup_flip::InitResult::Ineligible:
            return 0;
        case pickup_flip::InitResult::RoomUnavailable:
            return luaL_error(state,"EntityPickup:InitFlipState requires a current Room");
        case pickup_flip::InitResult::AllocationFailed:
            return luaL_error(state,"EntityPickup:InitFlipState could not allocate save state");
        case pickup_flip::InitResult::BindingUnavailable:
            return luaL_error(state,"EntityPickup:InitFlipState native binding is unavailable");
    }
    return 0;
}

#if !defined(__SWITCH__)
void SetRepentogonEntityNativeTestBindings(RepentogonEntityNativeTestBindings value) noexcept {g_Tests=value;}
#endif
}
