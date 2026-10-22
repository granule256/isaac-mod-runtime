#include "interfaces/lua/api100_scalar.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api100_scalar.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "card_hook.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
#include <type_traits>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
using Entry=api100_native::Entry;
namespace guards=api100_scalar;
constexpr Entry kEntries[]={
{guards::kItemPoolAddBibleUpgradeEntry,guards::kItemPoolAddBibleUpgradeGuard.data()},
{guards::kItemPoolForceAddPillEffectEntry,guards::kItemPoolForceAddPillEffectGuard.data()},
{guards::kItemPoolGetCardEntry,guards::kItemPoolGetCardGuard.data()},
{guards::kItemPoolGetPillEntry,guards::kItemPoolGetPillGuard.data()},
{guards::kItemPoolGetTrinketEntry,guards::kItemPoolGetTrinketGuard.data()},
{guards::kItemPoolRemoveTrinketEntry,guards::kItemPoolRemoveTrinketGuard.data()},
{guards::kItemPoolResetRoomBlacklistEntry,guards::kItemPoolResetRoomBlacklistGuard.data()},
{guards::kItemPoolResetTrinketsEntry,guards::kItemPoolResetTrinketsGuard.data()},
{guards::kLevelApplyBlueMapEffectEntry,guards::kLevelApplyBlueMapEffectGuard.data()},
{guards::kLevelApplyCompassEffectEntry,guards::kLevelApplyCompassEffectGuard.data()},
{guards::kLevelApplyMapEffectEntry,guards::kLevelApplyMapEffectGuard.data()},
{guards::kLevelCanOpenChallengeRoomEntry,guards::kLevelCanOpenChallengeRoomGuard.data()},
{guards::kLevelCanSpawnDevilRoomEntry,guards::kLevelCanSpawnDevilRoomGuard.data()},
{guards::kLevelCanStageHaveCurseOfLabyrinthEntry,guards::kLevelCanStageHaveCurseOfLabyrinthGuard.data()},
{guards::kLevelChangeRoomEntry,guards::kLevelChangeRoomGuard.data()},
{guards::kLevelInitializeDevilAngelRoomEntry,guards::kLevelInitializeDevilAngelRoomGuard.data()},
{guards::kLevelMakeRedRoomDoorEntry,guards::kLevelMakeRedRoomDoorGuard.data()},
{guards::kLevelRemoveCompassEffectEntry,guards::kLevelRemoveCompassEffectGuard.data()},
{guards::kLevelSetRedHeartDamageEntry,guards::kLevelSetRedHeartDamageGuard.data()},
{guards::kLevelShowMapEntry,guards::kLevelShowMapGuard.data()},
{guards::kLevelShowNameEntry,guards::kLevelShowNameGuard.data()},
{guards::kLevelUncoverHiddenDoorEntry,guards::kLevelUncoverHiddenDoorGuard.data()},
{guards::kRoomDamageGridEntry,guards::kRoomDamageGridGuard.data()},
{guards::kRoomGetBrokenWatchStateEntry,guards::kRoomGetBrokenWatchStateGuard.data()},
{guards::kRoomGetDevilRoomChanceEntry,guards::kRoomGetDevilRoomChanceGuard.data()},
{guards::kRoomGetDungeonRockIdxEntry,guards::kRoomGetDungeonRockIdxGuard.data()},
{guards::kRoomGetLightingAlphaEntry,guards::kRoomGetLightingAlphaGuard.data()},
{guards::kRoomGetRandomTileIndexEntry,guards::kRoomGetRandomTileIndexGuard.data()},
{guards::kRoomHasLavaEntry,guards::kRoomHasLavaGuard.data()},
{guards::kRoomHasWaterEntry,guards::kRoomHasWaterGuard.data()},
{guards::kRoomIsLShapedRoomEntry,guards::kRoomIsLShapedRoomGuard.data()},
{guards::kRoomRespawnEnemiesEntry,guards::kRoomRespawnEnemiesGuard.data()},
{guards::kRoomSetBrokenWatchStateEntry,guards::kRoomSetBrokenWatchStateGuard.data()},
{guards::kRoomShopReshuffleEntry,guards::kRoomShopReshuffleGuard.data()},
{guards::kRoomShopRestockFullEntry,guards::kRoomShopRestockFullGuard.data()},
{guards::kRoomShopRestockPartialEntry,guards::kRoomShopRestockPartialGuard.data()},
{guards::kRoomTriggerClearEntry,guards::kRoomTriggerClearGuard.data()},
{guards::kRoomTrySpawnBlueWombDoorEntry,guards::kRoomTrySpawnBlueWombDoorGuard.data()},
{guards::kRoomTrySpawnBossRushDoorEntry,guards::kRoomTrySpawnBossRushDoorGuard.data()},
{guards::kRoomTrySpawnMegaSatanRoomDoorEntry,guards::kRoomTrySpawnMegaSatanRoomDoorGuard.data()},
{guards::kRoomTrySpawnSecretExitEntry,guards::kRoomTrySpawnSecretExitGuard.data()},
{guards::kRoomTrySpawnTheVoidDoorEntry,guards::kRoomTrySpawnTheVoidDoorGuard.data()},
};
constexpr auto kCount=static_cast<unsigned>(Api100ScalarNative::Count);
static_assert(sizeof(kEntries)/sizeof(kEntries[0])==kCount);
using GuardCache=api100_native::Cache;
static_assert(std::is_trivial_v<GuardCache>);
GuardCache g_Cache[kCount]{};
#if !defined(__SWITCH__)
Api100ScalarNativeTestBindings g_Tests{};
#endif
void* Receiver(lua_State*state,const char*metatable,FieldReceipt receipt){
 luaL_checkudata(state,1,metatable);
 auto p=ResolveEngineReceiver(state,receipt,1);
 if(!p)luaL_error(state,"API reference is no longer available");
 return engine_memory::AsObject(p);
}
std::int32_t Integer(lua_State*state,int index){
 const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(state,index));
 std::int32_t value{};std::memcpy(&value,&bits,4);return value;
}
template<class Fn>Fn Native(lua_State*state,Api100ScalarNative method){
 const auto index=static_cast<unsigned>(method);
 if(index>=kCount){luaL_error(state,"invalid api100 native method");return nullptr;}
 std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Tests.methods[index];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(state,kEntries[index],g_Cache[index],host));
}
template<class R,class...Args>int Call(lua_State*state,Api100ScalarNative method,void*receiver,Args...args){
 auto fn=Native<R(*)(void*,Args...)>(state,method);
 if constexpr(std::is_void_v<R>){fn(receiver,args...);return 0;}
 else{auto v=fn(receiver,args...);if constexpr(std::is_same_v<R,bool>)lua_pushboolean(state,v);else if constexpr(std::is_same_v<R,float>)lua_pushnumber(state,v);else lua_pushinteger(state,v);return 1;}
}
}
#if !defined(__SWITCH__)
void SetApi100ScalarNativeTestBindings(Api100ScalarNativeTestBindings value)noexcept{g_Tests=value;}
#endif
int Api100ItemPoolAddBibleUpgrade(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kItemPoolMetatable,FieldReceipt::ItemPool);
 const auto arg0=Integer(state,2);
 const auto arg1=Integer(state,3);
 return Call<void>(state,Api100ScalarNative::ItemPoolAddBibleUpgrade,receiver ,arg0,arg1);
}
int Api100ItemPoolForceAddPillEffect(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kItemPoolMetatable,FieldReceipt::ItemPool);
 const auto arg0=Integer(state,2);
 return Call<std::int32_t>(state,Api100ScalarNative::ItemPoolForceAddPillEffect,receiver ,arg0);
}
int Api100ItemPoolGetCard(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kItemPoolMetatable,FieldReceipt::ItemPool);
 const auto arg0=static_cast<std::uint32_t>(luaL_checkinteger(state,2));
 const auto arg1=lua_toboolean(state,3)!=0;
 const auto arg2=lua_toboolean(state,4)!=0;
 const auto arg3=lua_toboolean(state,5)!=0;
 auto fn=Native<CardNativeBindings::GetCard>(state,Api100ScalarNative::ItemPoolGetCard);
#if defined(__SWITCH__)
 fn=ResolveCardApiEntry(LuaRuntime::EngineModuleBase());
 if(!fn)return luaL_error(state,"GetCard callback binding is unavailable");
#endif
 lua_pushinteger(state,fn(receiver,arg0,arg1,arg2,arg3));return 1;
}
int Api100ItemPoolGetPill(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kItemPoolMetatable,FieldReceipt::ItemPool);
 const auto arg0=static_cast<std::uint32_t>(luaL_checkinteger(state,2));
 return Call<std::int32_t>(state,Api100ScalarNative::ItemPoolGetPill,receiver ,arg0);
}
int Api100ItemPoolGetTrinket(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kItemPoolMetatable,FieldReceipt::ItemPool);
 const auto arg0=lua_toboolean(state,2)!=0;
 return Call<std::int32_t>(state,Api100ScalarNative::ItemPoolGetTrinket,receiver ,arg0);
}
int Api100ItemPoolRemoveTrinket(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kItemPoolMetatable,FieldReceipt::ItemPool);
 const auto arg0=Integer(state,2);
 return Call<bool>(state,Api100ScalarNative::ItemPoolRemoveTrinket,receiver ,arg0);
}
int Api100ItemPoolResetRoomBlacklist(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kItemPoolMetatable,FieldReceipt::ItemPool);
 return Call<void>(state,Api100ScalarNative::ItemPoolResetRoomBlacklist,receiver);
}
int Api100ItemPoolResetTrinkets(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kItemPoolMetatable,FieldReceipt::ItemPool);
 return Call<void>(state,Api100ScalarNative::ItemPoolResetTrinkets,receiver);
}
int Api100LevelApplyBlueMapEffect(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 return Call<void>(state,Api100ScalarNative::LevelApplyBlueMapEffect,receiver);
}
int Api100LevelApplyCompassEffect(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 const auto arg0=lua_toboolean(state,2)!=0;
 return Call<void>(state,Api100ScalarNative::LevelApplyCompassEffect,receiver ,arg0);
}
int Api100LevelApplyMapEffect(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 return Call<void>(state,Api100ScalarNative::LevelApplyMapEffect,receiver);
}
int Api100LevelCanOpenChallengeRoom(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 const auto arg0=Integer(state,2);
 return Call<bool>(state,Api100ScalarNative::LevelCanOpenChallengeRoom,receiver ,arg0);
}
int Api100LevelCanSpawnDevilRoom(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 return Call<bool>(state,Api100ScalarNative::LevelCanSpawnDevilRoom,receiver);
}
int Api100LevelCanStageHaveCurseOfLabyrinth(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 const auto arg0=Integer(state,2);
 return Call<bool>(state,Api100ScalarNative::LevelCanStageHaveCurseOfLabyrinth,receiver ,arg0);
}
int Api100LevelChangeRoom(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 const auto arg0=Integer(state,2);
 // 固定PC启动包装使用dim or -1；Lua的0为真，显式0不能改成当前维度。
 const auto arg1=lua_toboolean(state,3)!=0?Integer(state,3):std::int32_t{-1};
 return Call<void>(state,Api100ScalarNative::LevelChangeRoom,receiver ,arg0,arg1);
}
int Api100LevelInitializeDevilAngelRoom(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 const auto arg0=lua_toboolean(state,2)!=0;
 const auto arg1=lua_toboolean(state,3)!=0;
 return Call<void>(state,Api100ScalarNative::LevelInitializeDevilAngelRoom,receiver ,arg0,arg1);
}
int Api100LevelMakeRedRoomDoor(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 const auto arg0=Integer(state,2);
 const auto arg1=Integer(state,3);
 return Call<bool>(state,Api100ScalarNative::LevelMakeRedRoomDoor,receiver ,arg0,arg1);
}
int Api100LevelRemoveCompassEffect(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 return Call<void>(state,Api100ScalarNative::LevelRemoveCompassEffect,receiver);
}
int Api100LevelSetRedHeartDamage(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 return Call<void>(state,Api100ScalarNative::LevelSetRedHeartDamage,receiver);
}
int Api100LevelShowMap(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 return Call<void>(state,Api100ScalarNative::LevelShowMap,receiver);
}
int Api100LevelShowName(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 const auto arg0=lua_toboolean(state,2)!=0;
 return Call<void>(state,Api100ScalarNative::LevelShowName,receiver ,arg0);
}
int Api100LevelUncoverHiddenDoor(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 const auto arg0=Integer(state,2);
 const auto arg1=Integer(state,3);
 return Call<void>(state,Api100ScalarNative::LevelUncoverHiddenDoor,receiver ,arg0,arg1);
}
int Api100RoomDamageGrid(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=Integer(state,2);
 const auto arg1=Integer(state,3);
 return Call<bool>(state,Api100ScalarNative::RoomDamageGrid,receiver ,arg0,arg1);
}
int Api100RoomGetBrokenWatchState(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 return Call<std::int32_t>(state,Api100ScalarNative::RoomGetBrokenWatchState,receiver);
}
int Api100RoomGetDevilRoomChance(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 return Call<float>(state,Api100ScalarNative::RoomGetDevilRoomChance,receiver);
}
int Api100RoomGetDungeonRockIdx(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 return Call<std::int32_t>(state,Api100ScalarNative::RoomGetDungeonRockIdx,receiver);
}
int Api100RoomGetLightingAlpha(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 return Call<float>(state,Api100ScalarNative::RoomGetLightingAlpha,receiver);
}
int Api100RoomGetRandomTileIndex(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=Integer(state,2);
 return Call<std::int32_t>(state,Api100ScalarNative::RoomGetRandomTileIndex,receiver ,arg0);
}
int Api100RoomHasLava(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 return Call<bool>(state,Api100ScalarNative::RoomHasLava,receiver);
}
int Api100RoomHasWater(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 return Call<bool>(state,Api100ScalarNative::RoomHasWater,receiver);
}
int Api100RoomIsLShapedRoom(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 return Call<bool>(state,Api100ScalarNative::RoomIsLShapedRoom,receiver);
}
int Api100RoomRespawnEnemies(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 return Call<void>(state,Api100ScalarNative::RoomRespawnEnemies,receiver);
}
int Api100RoomSetBrokenWatchState(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=Integer(state,2);
 return Call<void>(state,Api100ScalarNative::RoomSetBrokenWatchState,receiver ,arg0);
}
int Api100RoomShopReshuffle(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=lua_toboolean(state,2)!=0;
 const auto arg1=lua_toboolean(state,3)!=0;
 return Call<void>(state,Api100ScalarNative::RoomShopReshuffle,receiver ,arg0,arg1);
}
int Api100RoomShopRestockFull(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 return Call<void>(state,Api100ScalarNative::RoomShopRestockFull,receiver);
}
int Api100RoomShopRestockPartial(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 return Call<void>(state,Api100ScalarNative::RoomShopRestockPartial,receiver);
}
int Api100RoomTriggerClear(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=lua_toboolean(state,2)!=0;
 return Call<void>(state,Api100ScalarNative::RoomTriggerClear,receiver ,arg0);
}
int Api100RoomTrySpawnBlueWombDoor(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=lua_isnoneornil(state,2)||lua_toboolean(state,2)!=0;
 const auto arg1=lua_toboolean(state,3)!=0;
 const auto arg2=lua_toboolean(state,4)!=0;
 return Call<bool>(state,Api100ScalarNative::RoomTrySpawnBlueWombDoor,receiver ,arg0,arg1,arg2);
}
int Api100RoomTrySpawnBossRushDoor(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=lua_toboolean(state,2)!=0;
 const auto arg1=lua_toboolean(state,3)!=0;
 return Call<bool>(state,Api100ScalarNative::RoomTrySpawnBossRushDoor,receiver ,arg0,arg1);
}
int Api100RoomTrySpawnMegaSatanRoomDoor(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=lua_toboolean(state,2)!=0;
 return Call<bool>(state,Api100ScalarNative::RoomTrySpawnMegaSatanRoomDoor,receiver ,arg0);
}
int Api100RoomTrySpawnSecretExit(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=lua_toboolean(state,2)!=0;
 const auto arg1=lua_toboolean(state,3)!=0;
 return Call<bool>(state,Api100ScalarNative::RoomTrySpawnSecretExit,receiver ,arg0,arg1);
}
int Api100RoomTrySpawnTheVoidDoor(lua_State*state){
 auto*receiver=Receiver(state,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=lua_toboolean(state,2)!=0;
 return Call<bool>(state,Api100ScalarNative::RoomTrySpawnTheVoidDoor,receiver ,arg0);
}
}
