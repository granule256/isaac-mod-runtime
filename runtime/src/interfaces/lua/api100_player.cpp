#include "interfaces/lua/api100_player.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api100_player.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
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
namespace guards=api100_player;
using Entry=api100_native::Entry;
constexpr Entry kEntries[]={
 {guards::kAddBombsEntry,guards::kAddBombsGuard.data()},
 {guards::kAddGigaBombsEntry,guards::kAddGigaBombsGuard.data()},
 {guards::kAddJarFliesEntry,guards::kAddJarFliesGuard.data()},
 {guards::kAddPoopManaEntry,guards::kAddPoopManaGuard.data()},
 {guards::kAddDeadEyeChargeEntry,guards::kAddDeadEyeChargeGuard.data()},
 {guards::kClearDeadEyeChargeEntry,guards::kClearDeadEyeChargeGuard.data()},
 {guards::kClearCostumesEntry,guards::kClearCostumesGuard.data()},
 {guards::kClearTemporaryEffectsEntry,guards::kClearTemporaryEffectsGuard.data()},
 {guards::kGetEffectiveBloodChargeEntry,guards::kGetEffectiveBloodChargeGuard.data()},
 {guards::kGetEffectiveSoulChargeEntry,guards::kGetEffectiveSoulChargeGuard.data()},
 {guards::kGetMaxPocketItemsEntry,guards::kGetMaxPocketItemsGuard.data()},
 {guards::kGetMaxPoopManaEntry,guards::kGetMaxPoopManaGuard.data()},
 {guards::kHasTimedItemEntry,guards::kHasTimedItemGuard.data()},
 {guards::kIsHeldItemVisibleEntry,guards::kIsHeldItemVisibleGuard.data()},
 {guards::kRemoveBlueFlyEntry,guards::kRemoveBlueFlyGuard.data()},
 {guards::kRemoveBlueSpiderEntry,guards::kRemoveBlueSpiderGuard.data()},
 {guards::kCanAddCollectibleEntry,guards::kCanAddCollectibleGuard.data()},
 {guards::kAnimateLightTravelEntry,guards::kAnimateLightTravelGuard.data()},
 {guards::kTryUseKeyEntry,guards::kTryUseKeyGuard.data()},
 {guards::kGetGreedDonationBreakChanceEntry,guards::kGetGreedDonationBreakChanceGuard.data()},
};
constexpr auto kCount=static_cast<unsigned>(Api100PlayerNative::Count);
static_assert(sizeof(kEntries)/sizeof(kEntries[0])==kCount);
using GuardCache=api100_native::Cache;
static_assert(std::is_trivial_v<GuardCache>);
GuardCache g_Cache[kCount]{};
#if !defined(__SWITCH__)
Api100PlayerNativeTestBindings g_Tests{};
#endif
void* Player(lua_State*state){
 luaL_checkudata(state,1,LuaRuntime::kEntityPlayerMetatable);
 const auto pointer=ResolveEngineReceiver(state,FieldReceipt::EntityPlayer,1);
 if(!pointer)luaL_error(state,"EntityPlayer reference is no longer available");
 return engine_memory::AsObject(pointer);
}
std::int32_t Integer(lua_State*state){
 const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(state,2));
 std::int32_t value{};std::memcpy(&value,&bits,4);return value;
}
template<class Fn>Fn Native(lua_State*state,Api100PlayerNative method){
 const auto index=static_cast<unsigned>(method);
 if(index>=kCount){luaL_error(state,"invalid api100 native method");return nullptr;}
 std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Tests.methods[index];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(state,kEntries[index],g_Cache[index],host));
}
int Add(lua_State*state,Api100PlayerNative id){
 auto*player=Player(state);const auto amount=Integer(state);
 Native<void(*)(void*,std::int32_t)>(state,id)(player,amount);return 0;
}
int Action(lua_State*state,Api100PlayerNative id){
 auto*player=Player(state);Native<void(*)(void*)>(state,id)(player);return 0;
}
int Signed(lua_State*state,Api100PlayerNative id){
 auto*player=Player(state);const auto value=Native<std::int32_t(*)(const void*)>(state,id)(player);
 lua_pushinteger(state,value);return 1;
}
int Boolean(lua_State*state,Api100PlayerNative id){
 auto*player=Player(state);const auto value=Native<bool(*)(void*)>(state,id)(player);
 lua_pushboolean(state,value);return 1;
}
}
#if !defined(__SWITCH__)
void SetApi100PlayerNativeTestBindings(Api100PlayerNativeTestBindings value) noexcept{g_Tests=value;}
#endif
int Api100PlayerAddBombs(lua_State*state){return Add(state,Api100PlayerNative::AddBombs);}
int Api100PlayerAddGigaBombs(lua_State*state){return Add(state,Api100PlayerNative::AddGigaBombs);}
int Api100PlayerAddJarFlies(lua_State*state){return Add(state,Api100PlayerNative::AddJarFlies);}
int Api100PlayerAddPoopMana(lua_State*state){return Add(state,Api100PlayerNative::AddPoopMana);}
int Api100PlayerAddDeadEyeCharge(lua_State*state){return Action(state,Api100PlayerNative::AddDeadEyeCharge);}
int Api100PlayerClearDeadEyeCharge(lua_State*state){return Action(state,Api100PlayerNative::ClearDeadEyeCharge);}
int Api100PlayerClearCostumes(lua_State*state){return Action(state,Api100PlayerNative::ClearCostumes);}
int Api100PlayerClearTemporaryEffects(lua_State*state){return Action(state,Api100PlayerNative::ClearTemporaryEffects);}
int Api100PlayerGetEffectiveBloodCharge(lua_State*state){return Signed(state,Api100PlayerNative::GetEffectiveBloodCharge);}
int Api100PlayerGetEffectiveSoulCharge(lua_State*state){return Signed(state,Api100PlayerNative::GetEffectiveSoulCharge);}
int Api100PlayerGetMaxPocketItems(lua_State*state){
 auto*player=Player(state);const auto value=Native<std::uint32_t(*)(const void*)>(state,Api100PlayerNative::GetMaxPocketItems)(player);
 lua_pushinteger(state,static_cast<lua_Integer>(value));return 1;
}
int Api100PlayerGetMaxPoopMana(lua_State*state){return Signed(state,Api100PlayerNative::GetMaxPoopMana);}
int Api100PlayerHasTimedItem(lua_State*state){return Boolean(state,Api100PlayerNative::HasTimedItem);}
int Api100PlayerIsHeldItemVisible(lua_State*state){return Boolean(state,Api100PlayerNative::IsHeldItemVisible);}
int Api100PlayerRemoveBlueFly(lua_State*state){return Action(state,Api100PlayerNative::RemoveBlueFly);}
int Api100PlayerRemoveBlueSpider(lua_State*state){return Action(state,Api100PlayerNative::RemoveBlueSpider);}
int Api100PlayerCanAddCollectible(lua_State*state){
 auto*player=Player(state);const auto type=Integer(state);
 // 固定PC848B00直接checkinteger(2)，文档缺省0在本映像中没有实现。
 const auto value=Native<bool(*)(const void*,std::int32_t)>(state,Api100PlayerNative::CanAddCollectible)(player,type);
 lua_pushboolean(state,value);return 1;
}
int Api100PlayerAnimateLightTravel(lua_State*state){return Action(state,Api100PlayerNative::AnimateLightTravel);}
int Api100PlayerTryUseKey(lua_State*state){return Boolean(state,Api100PlayerNative::TryUseKey);}
int Api100PlayerGetGreedDonationBreakChance(lua_State*state){
 auto*player=Player(state);const auto value=Native<float(*)(const void*)>(state,Api100PlayerNative::GetGreedDonationBreakChance)(player);
 lua_pushnumber(state,value);return 1;
}
}
