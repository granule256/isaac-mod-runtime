#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api200EntityPlayerAddCurseMistEffect(lua_State*);
int Api200EntityPlayerAddDollarBillEffect(lua_State*);
int Api200EntityPlayerAddPlayerFormCostume(lua_State*);
int Api200EntityPlayerAnimatePitfallIn(lua_State*);
int Api200EntityPlayerAnimatePitfallOut(lua_State*);
int Api200EntityPlayerAnimateTeleport(lua_State*);
int Api200EntityPlayerDoZitEffect(lua_State*);
int Api200EntityPlayerDropPocketItem(lua_State*);
int Api200EntityPlayerFireBrimstone(lua_State*);
int Api200EntityPlayerFireDelayedBrimstone(lua_State*);
int Api200EntityPlayerFireKnife(lua_State*);
int Api200EntityPlayerFireTechXLaser(lua_State*);
int Api200EntityPlayerGetBombFlags(lua_State*);
int Api200EntityPlayerGetFlyingOffset(lua_State*);
int Api200EntityPlayerGetLaserOffset(lua_State*);
int Api200EntityPlayerGetNPCTarget(lua_State*);
int Api200EntityPlayerHasInvincibility(lua_State*);
int Api200EntityPlayerInitBabySkin(lua_State*);
int Api200EntityPlayerIsFullSpriteRendering(lua_State*);
int Api200EntityPlayerIsPosInSpotLight(lua_State*);
int Api200EntityPlayerPlayExtraAnimation(lua_State*);
int Api200EntityPlayerQueueItem(lua_State*);
int Api200EntityPlayerRemoveCurseMistEffect(lua_State*);
int Api200EntityPlayerRemoveSkinCostume(lua_State*);
int Api200EntityPlayerResetItemState(lua_State*);
int Api200EntityPlayerRespawnFamiliars(lua_State*);
int Api200EntityPlayerShootRedCandle(lua_State*);
int Api200EntityPlayerSpawnMawOfVoid(lua_State*);
int Api200EntityPlayerThrowFriendlyDip(lua_State*);
int Api200EntityPlayerTriggerBookOfVirtues(lua_State*);
int Api200EntityPlayerTryHoldEntity(lua_State*);
int Api200EntityPlayerTryHoldTrinket(lua_State*);
int Api200EntityPlayerUpdateCanShoot(lua_State*);
int Api200EntityPlayerUsePoopSpell(lua_State*);
enum class Api200PlayerNative : unsigned { AddCurseMistEffect,AddDollarBillEffect,AddPlayerFormCostume,AnimatePitfallIn,AnimatePitfallOut,AnimateTeleport,DoZitEffect,DropPocketItem,FireBrimstone,FireDelayedBrimstone,FireKnife,FireTechXLaser,GetBombFlags,GetFlyingOffset,GetLaserOffset,GetNPCTarget,HasInvincibility,InitBabySkin,IsFullSpriteRendering,IsPosInSpotLight,PlayExtraAnimation,QueueItem,RemoveCurseMistEffect,RemoveSkinCostume,ResetItemState,RespawnFamiliars,ShootRedCandle,SpawnMawOfVoid,ThrowFriendlyDip,TriggerBookOfVirtues,TryHoldEntity,TryHoldTrinket,UpdateCanShoot,UsePoopSpell,Count };
#if !defined(__SWITCH__)
struct Api200PlayerNativeTestBindings {std::uintptr_t methods[static_cast<unsigned>(Api200PlayerNative::Count)];};
void SetApi200PlayerNativeTestBindings(Api200PlayerNativeTestBindings) noexcept;
#endif
}
