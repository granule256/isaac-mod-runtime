#include "interfaces/lua/rplus_health_api.hpp"
#include "interfaces/lua/rplus_health_guards.hpp"
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
namespace layout=rplus_health;
struct GuardCache {std::uintptr_t base{};bool valid{};};
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
}
}

namespace isaac::runtime {
namespace {
GuardCache g_HealthEntries[13]{},g_Golden{},g_Rotten{},g_Full{};
#if !defined(__SWITCH__)
RPlusHealthNativeTestBindings g_HealthTests{};
#endif
template<class Function,std::size_t N> Function HealthMethod(lua_State* state,unsigned index,
    std::uintptr_t offset,const std::array<std::uint8_t,N>& guard) {
#if !defined(__SWITCH__)
    if(g_HealthTests.methods[index])return engine_call::AsFunction<Function>(g_HealthTests.methods[index]);
#endif
    Require(state,CachedGuard(g_HealthEntries[index],offset,guard));
    return engine_call::AsFunction<Function>(LuaRuntime::EngineModuleBase()+offset);
}
int HealthAdd(lua_State* state,unsigned index,std::uintptr_t entry,
    const std::array<std::uint8_t,16>& guard,bool withBoolean) {
    const auto player=Player(state);const auto count=Integer32(state);
    if(withBoolean)HealthMethod<void (*)(void*,std::int32_t,bool)>(state,index,entry,guard)(
        engine_memory::AsObject(player),count,lua_toboolean(state,3)!=0);
    else HealthMethod<void (*)(void*,std::int32_t)>(state,index,entry,guard)(engine_memory::AsObject(player),count);
    return 0;
}
int HealthCanPick(lua_State* state,unsigned index,std::uintptr_t entry,
    const std::array<std::uint8_t,16>& guard) {
    const auto player=Player(state);
    const bool result=HealthMethod<bool (*)(void*)>(state,index,entry,guard)(engine_memory::AsObject(player));
    lua_pushboolean(state,result);return 1;
}
int HealthIndex(lua_State* state,unsigned index,std::uintptr_t entry,
    const std::array<std::uint8_t,16>& guard) {
    const auto player=Player(state);const auto heart=Integer32(state);
    const bool result=HealthMethod<bool (*)(const void*,std::int32_t)>(state,index,entry,guard)(engine_memory::AsObject(player),heart);
    lua_pushboolean(state,result);return 1;
}
}
#if !defined(__SWITCH__)
void SetRPlusHealthNativeTestBindings(RPlusHealthNativeTestBindings bindings) noexcept {g_HealthTests=bindings;}
#endif
int RPlusPlayerAddBlackHearts(lua_State* s){return HealthAdd(s,0,layout::kAddBlackHeartsEntry,layout::kAddBlackHeartsGuard,false);}
int RPlusPlayerAddMaxHearts(lua_State* s){return HealthAdd(s,1,layout::kAddMaxHeartsEntry,layout::kAddMaxHeartsGuard,true);}
int RPlusPlayerAddRottenHearts(lua_State* s){return HealthAdd(s,2,layout::kAddRottenHeartsEntry,layout::kAddRottenHeartsGuard,true);}
int RPlusPlayerAddSoulHearts(lua_State* s){return HealthAdd(s,3,layout::kAddSoulHeartsEntry,layout::kAddSoulHeartsGuard,false);}
int RPlusPlayerCanPickBlackHearts(lua_State* s){return HealthCanPick(s,4,layout::kCanPickBlackHeartsEntry,layout::kCanPickBlackHeartsGuard);}
int RPlusPlayerCanPickBoneHearts(lua_State* s){return HealthCanPick(s,5,layout::kCanPickBoneHeartsEntry,layout::kCanPickBoneHeartsGuard);}
int RPlusPlayerCanPickGoldenHearts(lua_State* s){return HealthCanPick(s,6,layout::kCanPickGoldenHeartsEntry,layout::kCanPickGoldenHeartsGuard);}
int RPlusPlayerCanPickRottenHearts(lua_State* s){return HealthCanPick(s,7,layout::kCanPickRottenHeartsEntry,layout::kCanPickRottenHeartsGuard);}
int RPlusPlayerGetGoldenHearts(lua_State* state) {
    const auto player=Player(state);Require(state,CachedGuard(g_Golden,layout::kGoldenReaderEntry,layout::kGoldenReaderGuard));
    lua_pushinteger(state,ReadCounter(state,player,layout::kGoldenHeartsOffset));return 1;
}
int RPlusPlayerGetHeartLimit(lua_State* state) {
    const auto player=Player(state);
    const auto result=HealthMethod<std::int32_t (*)(const void*,bool)>(state,8,
        layout::kGetHeartLimitEntry,layout::kGetHeartLimitGuard)(engine_memory::AsObject(player),lua_toboolean(state,2)!=0);
    lua_pushinteger(state,result);return 1;
}
int RPlusPlayerGetRottenHearts(lua_State* state) {
    const auto player=Player(state);Require(state,CachedGuard(g_Rotten,layout::kRottenReaderEntry,layout::kRottenReaderGuard));
    lua_pushinteger(state,ReadCounter(state,player,layout::kRottenHeartsOffset));return 1;
}
int RPlusPlayerHasFullHeartsAndSoulHearts(lua_State* state) {
    const auto player=Player(state);Require(state,CachedGuard(g_Full,layout::kFullHealthReaderEntry,layout::kFullHealthReaderGuard));
    // PC7FA960和NS442464同一判据；32位加法回绕后signed比较，不能引入C++signed溢出。
    const auto red=static_cast<std::uint32_t>(ReadCounter(state,player,kEntityPlayerHeartsOffset));
    const auto soul=static_cast<std::uint32_t>(ReadCounter(state,player,kEntityPlayerSoulHeartsOffset));
    const auto total=red+soul;std::int32_t signedTotal{};std::memcpy(&signedTotal,&total,4);
    lua_pushboolean(state,signedTotal>=ReadCounter(state,player,kEntityPlayerRedHeartContainersOffset));return 1;
}
int RPlusPlayerIsBlackHeart(lua_State* s){return HealthIndex(s,9,layout::kIsBlackHeartEntry,layout::kIsBlackHeartGuard);}
int RPlusPlayerIsBoneHeart(lua_State* s){return HealthIndex(s,10,layout::kIsBoneHeartEntry,layout::kIsBoneHeartGuard);}
int RPlusPlayerRemoveBlackHeart(lua_State* s){return HealthAdd(s,11,layout::kRemoveBlackHeartEntry,layout::kRemoveBlackHeartGuard,false);}
int RPlusPlayerSetFullHearts(lua_State* state) {
    const auto player=Player(state);
    HealthMethod<void (*)(void*)>(state,12,layout::kSetFullHeartsEntry,layout::kSetFullHeartsGuard)(engine_memory::AsObject(player));return 0;
}
}
