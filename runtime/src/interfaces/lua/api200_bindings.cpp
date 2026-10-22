#include "interfaces/lua/api200_bindings.hpp"
#include "interfaces/lua/api200_main.hpp"
#include "interfaces/lua/api200_player.hpp"
#include "interfaces/lua/api200_game.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {constexpr LuaHandlerBinding kBindings[]={
{0x0E011300, &Api200EntityHasCommonParentWithEntity},
{0x0E011301, &Api200EntitySetSize},
{0x0E011302, &Api200EntityFamiliarGetOrbitDistance},
{0x0E011303, &Api200EntityFamiliarPickEnemyTarget},
{0x0E011304, &Api200EntityKnifeReset},
{0x0E011305, &Api200EntityKnifeShoot},
{0x0E011306, &Api200EntityPlayerAddCurseMistEffect},
{0x0E011307, &Api200EntityPlayerAddDollarBillEffect},
{0x0E011308, &Api200EntityPlayerAddPlayerFormCostume},
{0x0E011309, &Api200EntityPlayerAnimatePitfallIn},
{0x0E01130A, &Api200EntityPlayerAnimatePitfallOut},
{0x0E01130B, &Api200EntityPlayerAnimateTeleport},
{0x0E01130C, &Api200EntityPlayerDoZitEffect},
{0x0E01130D, &Api200EntityPlayerDropPocketItem},
{0x0E01130E, &Api200EntityPlayerFireBrimstone},
{0x0E01130F, &Api200EntityPlayerFireDelayedBrimstone},
{0x0E011310, &Api200EntityPlayerFireKnife},
{0x0E011311, &Api200EntityPlayerFireTechXLaser},
{0x0E011312, &Api200EntityPlayerGetBombFlags},
{0x0E011313, &Api200EntityPlayerGetFlyingOffset},
{0x0E011314, &Api200EntityPlayerGetLaserOffset},
{0x0E011315, &Api200EntityPlayerGetNPCTarget},
{0x0E011316, &Api200EntityPlayerHasInvincibility},
{0x0E011317, &Api200EntityPlayerInitBabySkin},
{0x0E011318, &Api200EntityPlayerIsFullSpriteRendering},
{0x0E011319, &Api200EntityPlayerIsPosInSpotLight},
{0x0E01131A, &Api200EntityPlayerPlayExtraAnimation},
{0x0E01131B, &Api200EntityPlayerQueueItem},
{0x0E01131C, &Api200EntityPlayerRemoveCurseMistEffect},
{0x0E01131D, &Api200EntityPlayerRemoveSkinCostume},
{0x0E01131E, &Api200EntityPlayerResetItemState},
{0x0E01131F, &Api200EntityPlayerRespawnFamiliars},
{0x0E011320, &Api200EntityPlayerShootRedCandle},
{0x0E011321, &Api200EntityPlayerSpawnMawOfVoid},
{0x0E011322, &Api200EntityPlayerThrowFriendlyDip},
{0x0E011323, &Api200EntityPlayerTriggerBookOfVirtues},
{0x0E011324, &Api200EntityPlayerTryHoldEntity},
{0x0E011325, &Api200EntityPlayerTryHoldTrinket},
{0x0E011326, &Api200EntityPlayerUpdateCanShoot},
{0x0E011327, &Api200EntityPlayerUsePoopSpell},
{0x0E011328, &Api200EntityTearSetDeadEyeIntensity},
{0x02011329, &Api200GameAddEncounteredBoss},
{0x0201132A, &Api200GameButterBeanFart},
{0x0201132B, &Api200GameDonateAngel},
{0x0201132C, &Api200GameDonateGreed},
{0x0201132D, &Api200GameEnd},
{0x0201132E, &Api200GameFadein},
{0x0201132F, &Api200GameFadeout},
{0x02011330, &Api200GameFinishChallenge},
{0x02011331, &Api200GameGetGreedWavesNum},
{0x02011332, &Api200GameGetNearestPlayer},
{0x02011333, &Api200GameGetRandomPlayer},
{0x02011334, &Api200GameHasEncounteredBoss},
{0x02011335, &Api200GameMakeShockwave},
{0x02011336, &Api200GameNextVictoryLap},
{0x02011337, &Api200GameRerollEnemy},
{0x02011338, &Api200GameRerollLevelCollectibles},
{0x02011339, &Api200GameRerollLevelPickups},
{0x0201133A, &Api200GameStartStageTransition},
{0x0E01133B, &Api200GridEntityDoorTryBlowOpen},
{0x0E01133C, &Api200GridEntityDoorTryUnlock},
{0x0E01133D, &Api200GridEntityPitMakeBridge},
{0x0E01133E, &Api200GridEntityPitSetLadder},
{0x0E01133F, &Api200GridEntityPitUpdateCollision},
{0x0E011340, &Api200GridEntityPoopRespawnRedPoop},
{0x0E011341, &Api200GridEntityPressurePlateReward},
{0x11011342, &Api200HUDAssignPlayerHUDs},
{0x11011343, &Api200HUDFlashChargeBar},
{0x11011344, &Api200HUDInvalidateActiveItem},
{0x11011345, &Api200HUDInvalidateCraftingItem},
{0x11011346, &Api200HUDPostUpdate},
{0x11011347, &Api200HUDUpdate},
{0x0E011348, &Api200ItemConfigGetNullItem},
{0x03011349, &Api200LevelForceHorsemanBoss},
{0x0301134A, &Api200LevelGetEnterPosition},
{0x0301134B, &Api200LevelGetNonCompleteRoomIndex},
{0x0E01134C, &Api200PathFinderEvadeTarget},
{0x0E01134D, &Api200PathFinderGetGridIndex},
{0x0E01134E, &Api200PathFinderMoveRandomly},
{0x0E01134F, &Api200PathFinderMoveRandomlyAxisAligned},
{0x0E011350, &Api200PathFinderMoveRandomlyBoss},
{0x0E011351, &Api200PathFinderReset},
{0x0E011352, &Api200PathFinderResetMovementTarget},
{0x0E011353, &Api200PathFinderUpdateGridIndex},
{0x04011354, &Api200RoomCheckLine},
{0x04011355, &Api200RoomGetClampedGridIndex},
{0x04011356, &Api200RoomGetLaserTarget},
{0x04011357, &Api200RoomGetSeededCollectible},
{0x04011358, &Api200RoomMamaMegaExplosion},
{0x04011359, &Api200RoomTryMakeBridge},
{0x0401135A, &Api200RoomTrySpawnDevilRoomDoor},
{0x0401135B, &Api200RoomTrySpawnSecretShop},
{0x0401135C, &Api200RoomTrySpawnSpecialQuestDoor},
{0x0F01135D, &Api200SeedsCanAddSeedEffect},
{0x0F01135E, &Api200SeedsCountUnlockedSeedEffects},
{0x0F01135F, &Api200SeedsInitSeedInfo},
{0x0F011360, &Api200SeedsRemoveBlockingSeedEffects},
{0x0F011361, &Api200SeedsReset},
{0x0F011362, &Api200SeedsRestart},
{0x0D011363, &Api200SpriteSetOverlayAnimation},
};}
std::size_t AttachApi200Methods(lua_State*state,const char*owner)noexcept{return AttachOwnerMethods(state,owner,kBindings,sizeof(kBindings)/sizeof(kBindings[0]));}
void PublishApi200Statics(lua_State*state,const char*owner){
 const char*names[2]{};unsigned count{};
 if(!std::strcmp(owner,"EntityFamiliar")){names[0]="GetOrbitDistance";count=1;}
 else if(!std::strcmp(owner,"Seeds")){names[0]="CountUnlockedSeedEffects";names[1]="InitSeedInfo";count=2;}
 if(!count)return;
 lua_getglobal(state,owner);if(!lua_istable(state,-1)){lua_pop(state,1);return;}
 const int global=lua_gettop(state);
 if(!lua_getmetatable(state,global)){lua_pop(state,1);return;}
 lua_getfield(state,-1,"__class");
 for(unsigned i=0;i<count;i++){lua_getfield(state,-1,names[i]);lua_setfield(state,global,names[i]);}
 lua_pop(state,3);
}

}
