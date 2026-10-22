#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api400EntityPlayerRenderGlow(lua_State*);
int Api400EntityNPCKillUnique(lua_State*);
int Api400EntityNPCMakeChampion(lua_State*);
int Api400EntityNPCMakeSplat(lua_State*);
int Api400EntityPickupTryOpenChest(lua_State*);
int Api400EntityGetBossID(lua_State*);
int Api400EntitySetSpriteOverlayFrame(lua_State*);
int Api400EntityEffectFollowParent(lua_State*);
int Api400EntityEffectSetDamageSource(lua_State*);
int Api400EntityEffectSetRadii(lua_State*);
int Api400EntityEffectSetTimeout(lua_State*);
int Api400EntityKnifeGetKnifeDistance(lua_State*);
int Api400EntityKnifeGetKnifeVelocity(lua_State*);
int Api400EntityKnifeSetPathFollowSpeed(lua_State*);
int Api400EntityLaserGetEndPoint(lua_State*);
int Api400EntityLaserIsCircleLaser(lua_State*);
int Api400EntityLaserIsSampleLaser(lua_State*);
int Api400EntityLaserSetBlackHpDropChance(lua_State*);
int Api400EntityLaserSetHomingType(lua_State*);
int Api400EntityLaserSetMultidimensionalTouched(lua_State*);
int Api400EntityLaserSetOneHit(lua_State*);
int Api400EntityLaserSetTimeout(lua_State*);
int Api400EntityNPCResetPathFinderTarget(lua_State*);
int Api400EntityPlayerRenderTop(lua_State*);
int Api400EntityRenderShadowLayer(lua_State*);
int Api400EntityProjectileAddChangeFlags(lua_State*);
int Api400EntityProjectileAddFallingAccel(lua_State*);
int Api400EntityProjectileAddFallingSpeed(lua_State*);
int Api400EntityProjectileAddHeight(lua_State*);
int Api400EntityProjectileAddProjectileFlags(lua_State*);
int Api400EntityProjectileAddScale(lua_State*);
int Api400EntityProjectileClearProjectileFlags(lua_State*);
int Api400EntityTearSetKnockbackMultiplier(lua_State*);
int Api400EntityTearSetParentOffset(lua_State*);
int Api400EntityTearSetWaitFrames(lua_State*);
enum class Api400EntitiesNative : unsigned {
RenderGlow,
KillUnique,
MakeChampion,
MakeSplat,
TryOpenChest,
Overlay,
SetParent,
ResetMovementTarget,
RenderTop,
ShadowEntity,
ShadowEntity_NPC,
ShadowEntity_Laser,
ShadowEntity_Player,
ShadowEntity_Familiar,
EntityLayout,
ConfigLayout,
EffectLayout,
EffectUpdate,
KnifeLayout,
KnifeUpdate,
LaserLayout,
LaserDamage,
LaserUpdate,
LaserInit,
TearLayout,
TearUpdate,
ProjectileLayout,
ProjectileUpdate,
NpcLayout,
TearHitLayout,
Count};
#if !defined(__SWITCH__)
struct Api400EntitiesNativeTestBindings {std::uintptr_t methods[static_cast<unsigned>(Api400EntitiesNative::Count)]{};};
void SetApi400EntitiesNativeTestBindings(Api400EntitiesNativeTestBindings) noexcept;
#endif
}
