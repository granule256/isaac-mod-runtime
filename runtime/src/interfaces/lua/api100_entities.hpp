#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api100EntityFamiliarAddCoins(lua_State*);
int Api100EntityFamiliarAddHearts(lua_State*);
int Api100EntityFamiliarAddKeys(lua_State*);
int Api100EntityFamiliarRemoveFromFollowers(lua_State*);
int Api100EntityFamiliarRemoveFromDelayed(lua_State*);
int Api100EntityFamiliarAddToDelayed(lua_State*);
int Api100EntityFamiliarMoveDelayed(lua_State*);
int Api100EntityFamiliarMoveDiagonally(lua_State*);
int Api100EntityFamiliarPlayChargeAnim(lua_State*);
int Api100EntityFamiliarPlayFloatAnim(lua_State*);
int Api100EntityFamiliarPlayShootAnim(lua_State*);
int Api100EntityFamiliarShoot(lua_State*);
int Api100EntityPickupPlayPickupSound(lua_State*);
int Api100EntityPickupPlayDropSound(lua_State*);
int Api100EntityPickupAppearFast(lua_State*);
int Api100EntityPickupGetCoinValue(lua_State*);
int Api100GridEntityHurt(lua_State*);
int Api100GridEntityDoorCanBlowOpen(lua_State*);
int Api100GridEntityDoorSetLocked(lua_State*);
int Api100GridEntityDoorSetRoomTypes(lua_State*);
int Api100GridEntityDoorSpawnDust(lua_State*);
int Api100GridEntityRockGetBigRockFrame(lua_State*);
int Api100GridEntityRockSetBigRockFrame(lua_State*);
int Api100GridEntityRockUpdateAnimFrame(lua_State*);
enum class Api100EntitiesNative:unsigned {EntityFamiliarAddCoins,EntityFamiliarAddHearts,EntityFamiliarAddKeys,EntityFamiliarRemoveFromFollowers,EntityFamiliarRemoveFromDelayed,EntityFamiliarAddToDelayed,EntityFamiliarMoveDelayed,EntityFamiliarMoveDiagonally,EntityFamiliarPlayChargeAnim,EntityFamiliarPlayFloatAnim,EntityFamiliarPlayShootAnim,EntityFamiliarShoot,EntityPickupPlayPickupSound,EntityPickupPlayDropSound,EntityPickupAppearFast,EntityPickupGetCoinValue,GridEntityHurt,GridEntityDoorCanBlowOpen,GridEntityDoorSetLocked,GridEntityDoorSetRoomTypes,GridEntityDoorSpawnDust,GridEntityRockGetBigRockFrame,GridEntityRockSetBigRockFrame,GridEntityRockUpdateAnimFrame,Count};
#if !defined(__SWITCH__)
struct Api100EntitiesNativeTestBindings {std::uintptr_t methods[static_cast<unsigned>(Api100EntitiesNative::Count)];};
void SetApi100EntitiesNativeTestBindings(Api100EntitiesNativeTestBindings) noexcept;
#endif
}
