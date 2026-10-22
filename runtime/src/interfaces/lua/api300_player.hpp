#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api300EntityPlayerCanShoot(lua_State*);
int Api300EntityPlayerCanTurnHead(lua_State*);
int Api300EntityPlayerRenderBody(lua_State*);
int Api300EntityPlayerGetActiveWeaponEntity(lua_State*);
int Api300EntityPlayerGetBatteryCharge(lua_State*);
int Api300EntityPlayerGetBodyColor(lua_State*);
int Api300EntityPlayerGetHeadColor(lua_State*);
int Api300EntityPlayerGetItemState(lua_State*);
int Api300EntityPlayerGetJarFlies(lua_State*);
int Api300EntityPlayerGetLastActionTriggers(lua_State*);
int Api300EntityPlayerGetLastDamageFlags(lua_State*);
int Api300EntityPlayerGetLastDirection(lua_State*);
int Api300EntityPlayerGetMovementVector(lua_State*);
int Api300EntityPlayerGetNumBlueFlies(lua_State*);
int Api300EntityPlayerGetNumBlueSpiders(lua_State*);
int Api300EntityPlayerGetNumGigaBombs(lua_State*);
int Api300EntityPlayerGetRecentMovementVector(lua_State*);
int Api300EntityPlayerGetSmoothBodyRotation(lua_State*);
int Api300EntityPlayerGetTearPoisonDamage(lua_State*);
int Api300EntityPlayerGetTearRangeModifier(lua_State*);
int Api300EntityPlayerGetTotalDamageTaken(lua_State*);
int Api300EntityPlayerGetTractorBeam(lua_State*);
int Api300EntityPlayerGetVelocityBeforeUpdate(lua_State*);
int Api300EntityPlayerHasCurseMistEffect(lua_State*);
int Api300EntityPlayerIsItemQueueEmpty(lua_State*);
int Api300EntityPlayerIsP2Appearing(lua_State*);
int Api300EntityPlayerSetBloodCharge(lua_State*);
int Api300EntityPlayerSetSoulCharge(lua_State*);
int Api300EntityPlayerRenderHead(lua_State*);
int Api300EntityPlayerAddControlsCooldown(lua_State*);
int Api300EntityPlayerAreControlsEnabled(lua_State*);
enum class Api300PlayerNative : unsigned { CanTurnHead,GetActiveWeaponEntity,RenderHead,RenderBody,Count };
#if !defined(__SWITCH__)
struct Api300PlayerNativeTestBindings {std::uintptr_t methods[static_cast<unsigned>(Api300PlayerNative::Count)];};
void SetApi300PlayerNativeTestBindings(Api300PlayerNativeTestBindings) noexcept;
#endif
}
