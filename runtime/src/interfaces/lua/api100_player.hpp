#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api100PlayerAddBombs(lua_State*);
int Api100PlayerAddGigaBombs(lua_State*);
int Api100PlayerAddJarFlies(lua_State*);
int Api100PlayerAddPoopMana(lua_State*);
int Api100PlayerAddDeadEyeCharge(lua_State*);
int Api100PlayerClearDeadEyeCharge(lua_State*);
int Api100PlayerClearCostumes(lua_State*);
int Api100PlayerClearTemporaryEffects(lua_State*);
int Api100PlayerGetEffectiveBloodCharge(lua_State*);
int Api100PlayerGetEffectiveSoulCharge(lua_State*);
int Api100PlayerGetMaxPocketItems(lua_State*);
int Api100PlayerGetMaxPoopMana(lua_State*);
int Api100PlayerHasTimedItem(lua_State*);
int Api100PlayerIsHeldItemVisible(lua_State*);
int Api100PlayerRemoveBlueFly(lua_State*);
int Api100PlayerRemoveBlueSpider(lua_State*);
int Api100PlayerCanAddCollectible(lua_State*);
int Api100PlayerAnimateLightTravel(lua_State*);
int Api100PlayerTryUseKey(lua_State*);
int Api100PlayerGetGreedDonationBreakChance(lua_State*);
enum class Api100PlayerNative : unsigned { AddBombs,AddGigaBombs,AddJarFlies,AddPoopMana,AddDeadEyeCharge,ClearDeadEyeCharge,ClearCostumes,ClearTemporaryEffects,GetEffectiveBloodCharge,GetEffectiveSoulCharge,GetMaxPocketItems,GetMaxPoopMana,HasTimedItem,IsHeldItemVisible,RemoveBlueFly,RemoveBlueSpider,CanAddCollectible,AnimateLightTravel,TryUseKey,GetGreedDonationBreakChance,Count };
#if !defined(__SWITCH__)
struct Api100PlayerNativeTestBindings {std::uintptr_t methods[static_cast<unsigned>(Api100PlayerNative::Count)];};
void SetApi100PlayerNativeTestBindings(Api100PlayerNativeTestBindings) noexcept;
#endif
}
