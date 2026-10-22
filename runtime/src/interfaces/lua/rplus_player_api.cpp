#include "interfaces/lua/rplus_player_api.hpp"
#include "interfaces/lua/rplus_player_guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
namespace layout=rplus_player;
#if !defined(__SWITCH__)
RPlusPlayerNativeTestBindings g_TestNative{};
#endif
struct GuardCache {std::uintptr_t base{};bool valid{};};
GuardCache g_Sub{},g_Cooldown{},g_Jar{},g_Soul{},g_Blood{},g_AddJar{};
template<std::size_t N> bool Guard(std::uintptr_t base,std::uintptr_t offset,
    const std::array<std::uint8_t,N>& bytes) noexcept {
    return base && base<=UINTPTR_MAX-offset-N && engine_memory::EngineMemoryReadable(base+offset,N) &&
        std::memcmp(engine_memory::AsObject(base+offset),bytes.data(),N)==0;
}
template<std::size_t N> bool CachedGuard(GuardCache& cache,std::uintptr_t offset,
    const std::array<std::uint8_t,N>& bytes) noexcept {
    const auto base=LuaRuntime::EngineModuleBase();
    if(cache.base!=base||!cache.valid){cache.base=base;cache.valid=Guard(base,offset,bytes);}
    return cache.valid;
}
template<std::size_t N,std::size_t M> bool CachedPair(GuardCache& cache,
    std::uintptr_t first,const std::array<std::uint8_t,N>& firstBytes,
    std::uintptr_t second,const std::array<std::uint8_t,M>& secondBytes) noexcept {
    const auto base=LuaRuntime::EngineModuleBase();
    if(cache.base!=base||!cache.valid){cache.base=base;
        cache.valid=Guard(base,first,firstBytes)&&Guard(base,second,secondBytes);}
    return cache.valid;
}
std::uintptr_t Player(lua_State* state) {
    luaL_checkudata(state,1,LuaRuntime::kEntityPlayerMetatable);
    const auto player=EntityPointerArgument(state,1);
    std::uint32_t type{},variant{};
    if(!player||!ReadEntityIdentity(player,&type,&variant)||type!=1)
        luaL_error(state,"EntityPlayer reference is no longer available");
    return player;
}
std::int32_t Integer32(lua_State* state) {
    // PC整数参数消费低32位；数字字符串和整数浮点由luaL_checkinteger同样接受。
    const auto low=static_cast<std::uint32_t>(luaL_checkinteger(state,2));
    std::int32_t result{};std::memcpy(&result,&low,sizeof(result));return result;
}
void Require(lua_State* state,bool valid) {
    if(!valid)luaL_error(state,"EntityPlayer native layout guard mismatch");
}
std::int32_t ReadCounter(lua_State* state,std::uintptr_t player,std::uintptr_t offset) {
    std::int32_t value{};
    if(!engine_memory::ReadField(player,offset,&value,engine_memory::EngineMemoryReadable))luaL_error(state,"EntityPlayer counter is unavailable");
    return value;
}
void WriteCounter(lua_State* state,std::uintptr_t player,std::uintptr_t offset,std::int32_t value) {
    if(!engine_memory::WriteField(player,offset,value,engine_memory::EngineMemoryWritable))luaL_error(state,"EntityPlayer counter is not writable");
}
using Add=void (*)(void*,std::int32_t);
int InvokeAdd(lua_State* state,GuardCache& cache,std::uintptr_t entry,
    const std::array<std::uint8_t,16>& bytes,Add test) {
    const auto player=Player(state);const auto amount=Integer32(state);
    Add method=test;
    if(!method){Require(state,CachedGuard(cache,entry,bytes));
        method=engine_call::AsFunction<Add>(LuaRuntime::EngineModuleBase()+entry);}
    method(engine_memory::AsObject(player),amount);return 0;
}
}
#if !defined(__SWITCH__)
void SetRPlusPlayerNativeTestBindings(RPlusPlayerNativeTestBindings bindings) noexcept {g_TestNative=bindings;}
#endif
int RPlusPlayerGetSubPlayer(lua_State* state) {
    const auto player=Player(state);
    Require(state,CachedPair(g_Sub,layout::kSubReaderEntry,layout::kSubReaderGuard,
        layout::kSubInitEntry,layout::kSubInitGuard));
    std::uintptr_t sub{};
    if(!engine_memory::ReadField(player,layout::kSubPlayerOffset,&sub,engine_memory::EngineMemoryReadable))
        return luaL_error(state,"EntityPlayer subplayer field is unavailable");
    if(!sub){lua_pushnil(state);return 1;}
    if(!IsLiveEntityPointer(sub)||ClassifyCallbackEntity(sub)!=CallbackEntityClass::Player)
        return luaL_error(state,"EntityPlayer subplayer reference is no longer available");
    PushEntityCallbackArgument(state,sub);return 1;
}
int RPlusPlayerGetDamageCooldown(lua_State* state) {
    const auto player=Player(state);Require(state,CachedGuard(g_Cooldown,layout::kCooldownReaderEntry,layout::kCooldownReaderGuard));
    lua_pushinteger(state,ReadCounter(state,player,layout::kDamageCooldownOffset));return 1;
}
int RPlusPlayerSetMinDamageCooldown(lua_State* state) {
    const auto player=Player(state);const auto requested=Integer32(state);
    Require(state,CachedGuard(g_Cooldown,layout::kCooldownReaderEntry,layout::kCooldownReaderGuard)&&
        Guard(LuaRuntime::EngineModuleBase(),layout::kCooldownMaxEntry,layout::kCooldownMaxGuard));
    const auto current=ReadCounter(state,player,layout::kDamageCooldownOffset);
    if(current<requested)WriteCounter(state,player,layout::kDamageCooldownOffset,requested);
    return 0;
}
int RPlusPlayerResetDamageCooldown(lua_State* state) {
    const auto player=Player(state);Require(state,CachedGuard(g_Cooldown,layout::kCooldownReaderEntry,layout::kCooldownReaderGuard)&&
        Guard(LuaRuntime::EngineModuleBase(),layout::kCooldownInitEntry,layout::kCooldownInitGuard));
    WriteCounter(state,player,layout::kDamageCooldownOffset,0);return 0;
}
int RPlusPlayerGetJarHearts(lua_State* state) {
    const auto player=Player(state);Require(state,CachedGuard(g_Jar,layout::kJarReaderEntry,layout::kJarReaderGuard));
    lua_pushinteger(state,ReadCounter(state,player,layout::kJarHeartsOffset));return 1;
}
int RPlusPlayerAddSoulCharge(lua_State* state) {
    Add test=nullptr;
#if !defined(__SWITCH__)
    test=g_TestNative.addSoul;
#endif
    return InvokeAdd(state,g_Soul,layout::kAddSoulEntry,layout::kAddSoulGuard,test);
}
int RPlusPlayerAddBloodCharge(lua_State* state) {
    Add test=nullptr;
#if !defined(__SWITCH__)
    test=g_TestNative.addBlood;
#endif
    return InvokeAdd(state,g_Blood,layout::kAddBloodEntry,layout::kAddBloodGuard,test);
}
int RPlusPlayerAddJarHearts(lua_State* state) {
    Add test=nullptr;
#if !defined(__SWITCH__)
    test=g_TestNative.addJar;
#endif
    return InvokeAdd(state,g_AddJar,layout::kAddJarEntry,layout::kAddJarGuard,test);
}
}
