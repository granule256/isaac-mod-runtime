#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int RPlusEntityAddBurn(lua_State*);
int RPlusEntityAddConfusion(lua_State*);
int RPlusEntityAddMidasFreeze(lua_State*);
int RPlusEntityAddShrink(lua_State*);
int RPlusEntityAddSlowing(lua_State*);
int RPlusEntityHasMortalDamage(lua_State*);
int RPlusBombAddTearFlags(lua_State*);
int RPlusKnifeAddTearFlags(lua_State*);
int RPlusLaserAddTearFlags(lua_State*);
int RPlusTearAddTearFlags(lua_State*);
int RPlusBombSetExplosionCountdown(lua_State*);
int RPlusPlayerAddCostume(lua_State*);
int RPlusPlayerAddWisp(lua_State*);
int RPlusPlayerAnimateCard(lua_State*);
int RPlusPlayerAnimatePickup(lua_State*);
int RPlusPlayerCanPickupItem(lua_State*);
int RPlusPlayerFireBomb(lua_State*);
int RPlusPlayerFlushQueueItem(lua_State*);
int RPlusPlayerFullCharge(lua_State*);
int RPlusPlayerGetAimDirection(lua_State*);
int RPlusPlayerGetMaxTrinkets(lua_State*);
int RPlusPlayerGetTearMovementInheritance(lua_State*);
int RPlusPlayerRemoveCostume(lua_State*);
int RPlusPlayerSetPill(lua_State*);
int RPlusPlayerSetPocketActiveItem(lua_State*);
int RPlusPlayerThrowBlueSpider(lua_State*);
int RPlusPlayerWillPlayerRevive(lua_State*);
int RPlusProjectileHasProjectileFlags(lua_State*);
int RPlusGameClearStagesWithoutHeartsPicked(lua_State*);
int RPlusGameFart(lua_State*);
int RPlusGameShakeScreen(lua_State*);
int RPlusGridSetVariant(lua_State*);
int RPlusDoorBar(lua_State*);
int RPlusPathFindGridPath(lua_State*);
int RPlusRoomGetAwardSeed(lua_State*);
enum class RPlusMethodsNative : unsigned {
    AddBurn,
    AddConfusion,
    AddMidasFreeze,
    AddShrink,
    AddSlowing,
    HasMortalDamage,
    AddCostume,
    AddWisp,
    AnimateCard,
    AnimatePickup,
    CanPickupItem,
    FireBomb,
    FlushQueueItem,
    FullCharge,
    GetMaxTrinkets,
    GetTearMovementInheritance,
    RemoveCostume,
    SetPill,
    SetPocketActiveItem,
    ThrowBlueSpider,
    WillPlayerRevive,
    Fart,
    ShakeScreen,
    Bar,
    FindGridPath,
    Count
};
#if !defined(__SWITCH__)
struct RPlusMethodsNativeTestBindings {std::uintptr_t methods[static_cast<unsigned>(RPlusMethodsNative::Count)]{};};
void SetRPlusMethodsNativeTestBindings(RPlusMethodsNativeTestBindings) noexcept;
#endif
}
