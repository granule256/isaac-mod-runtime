#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "interfaces/lua/rng_api.hpp"
#include "interfaces/lua/procedural_item_api.hpp"
#include "interfaces/lua/repentogon_world_api.hpp"
#include "interfaces/lua/repentogon_runtime_api.hpp"
#include "interfaces/lua/repentogon_persistent_api.hpp"
#include "interfaces/lua/repentogon_player_api.hpp"
#include "interfaces/lua/repentogon_player_manager_api.hpp"
#include "interfaces/lua/api600_player.hpp"
#include "interfaces/lua/api700_player.hpp"
#include "interfaces/lua/repentogon_entity_api.hpp"
#include "interfaces/lua/repentogon_entity_config_api.hpp"
#include "interfaces/lua/repentogon_sprite_api.hpp"
#include "interfaces/lua/repentogon_menu_world_api.hpp"
#include "interfaces/lua/repentogon_room_mutations.hpp"
#include "interfaces/lua/repentogon_remaining_bulk_api.hpp"
#include "application/callback/extended_callback_runtime.hpp"
#include "lua_runtime.hpp"
#include <array>
extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime::repentogon {
namespace {
const NativePort* g_NativePort{};
constexpr RepentogonCallbackBinding kCallbacks[]={
    {1005,"MC_POST_ADD_COLLECTIBLE"},
    {1020,"MC_HUD_UPDATE"},
    {1021,"MC_POST_HUD_UPDATE"},
    {1022,"MC_HUD_RENDER"},
    {1023,"MC_MAIN_MENU_RENDER"},
    {1024,"MC_POST_HUD_RENDER"},
    {1026,"MC_PRE_UPDATE"},
    {1030,"MC_PRE_SFX_PLAY"},
    {1031,"MC_POST_SFX_PLAY"},
    {1060,"MC_PRE_LEVEL_INIT"},
    {1061,"MC_PRE_CHANGE_ROOM"},
    {1080,"MC_PRE_FAMILIAR_RENDER"},
    {1081,"MC_PRE_NPC_RENDER"},
    {1082,"MC_PRE_PLAYER_RENDER"},
    {1083,"MC_PRE_PICKUP_RENDER"},
    {1084,"MC_PRE_TEAR_RENDER"},
    {1085,"MC_PRE_PROJECTILE_RENDER"},
    {1086,"MC_PRE_KNIFE_RENDER"},
    {1087,"MC_PRE_EFFECT_RENDER"},
    {1088,"MC_PRE_BOMB_RENDER"},
    {1089,"MC_PRE_SLOT_RENDER"},
    {1090,"MC_POST_SLOT_RENDER"},
    {1101,"MC_POST_GRID_ENTITY_SPAWN"},
    {1102,"MC_POST_NIGHTMARE_SCENE_RENDER"},
    {1104,"MC_PRE_LEVEL_SELECT"},
    {1121,"MC_POST_SLOT_INIT"},
    {1122,"MC_POST_SLOT_UPDATE"},
    {1160,"MC_PRE_PLAYER_UPDATE"},
    {1161,"MC_PRE_TEAR_UPDATE"},
    {1162,"MC_PRE_FAMILIAR_UPDATE"},
    {1163,"MC_PRE_BOMB_UPDATE"},
    {1164,"MC_PRE_PICKUP_UPDATE"},
    {1165,"MC_PRE_KNIFE_UPDATE"},
    {1166,"MC_PRE_PROJECTILE_UPDATE"},
    {1167,"MC_PRE_LASER_UPDATE"},
    {1168,"MC_PRE_EFFECT_UPDATE"},
    {1169,"MC_PRE_SLOT_UPDATE"},
    {1200,"MC_PRE_NEW_ROOM"},
    {1210,"MC_POST_MODS_LOADED"},
    {1218,"MC_PRE_PAUSE_SCREEN_RENDER"},
    {1219,"MC_POST_PAUSE_SCREEN_RENDER"},
    {1231,"MC_POST_PLAYER_COLLISION"},
    {1233,"MC_POST_TEAR_COLLISION"},
    {1235,"MC_POST_FAMILIAR_COLLISION"},
    {1237,"MC_POST_BOMB_COLLISION"},
    {1239,"MC_POST_PICKUP_COLLISION"},
    {1270,"MC_POST_BOSS_INTRO_SHOW"},
    {1400,"MC_PRE_GRID_ENTITY_DECORATION_UPDATE"},
    {1401,"MC_POST_GRID_ENTITY_DECORATION_UPDATE"},
    {1402,"MC_PRE_GRID_ENTITY_DOOR_UPDATE"},
    {1403,"MC_POST_GRID_ENTITY_DOOR_UPDATE"},
    {1404,"MC_PRE_GRID_ENTITY_FIRE_UPDATE"},
    {1405,"MC_POST_GRID_ENTITY_FIRE_UPDATE"},
    {1406,"MC_PRE_GRID_ENTITY_GRAVITY_UPDATE"},
    {1407,"MC_POST_GRID_ENTITY_GRAVITY_UPDATE"},
    {1408,"MC_PRE_GRID_ENTITY_LOCK_UPDATE"},
    {1409,"MC_POST_GRID_ENTITY_LOCK_UPDATE"},
    {1410,"MC_PRE_GRID_ENTITY_PIT_UPDATE"},
    {1411,"MC_POST_GRID_ENTITY_PIT_UPDATE"},
    {1412,"MC_PRE_GRID_ENTITY_POOP_UPDATE"},
    {1413,"MC_POST_GRID_ENTITY_POOP_UPDATE"},
    {1414,"MC_PRE_GRID_ENTITY_PRESSUREPLATE_UPDATE"},
    {1415,"MC_POST_GRID_ENTITY_PRESSUREPLATE_UPDATE"},
    {1416,"MC_PRE_GRID_ENTITY_ROCK_UPDATE"},
    {1417,"MC_POST_GRID_ENTITY_ROCK_UPDATE"},
    {1418,"MC_PRE_GRID_ENTITY_SPIKES_UPDATE"},
    {1419,"MC_POST_GRID_ENTITY_SPIKES_UPDATE"},
    {1420,"MC_PRE_GRID_ENTITY_STAIRCASE_UPDATE"},
    {1421,"MC_POST_GRID_ENTITY_STAIRCASE_UPDATE"},
    {1422,"MC_PRE_GRID_ENTITY_STATUE_UPDATE"},
    {1423,"MC_POST_GRID_ENTITY_STATUE_UPDATE"},
    {1424,"MC_PRE_GRID_ENTITY_TELEPORTER_UPDATE"},
    {1425,"MC_POST_GRID_ENTITY_TELEPORTER_UPDATE"},
    {1426,"MC_PRE_GRID_ENTITY_TRAPDOOR_UPDATE"},
    {1427,"MC_POST_GRID_ENTITY_TRAPDOOR_UPDATE"},
    {1428,"MC_PRE_GRID_ENTITY_WEB_UPDATE"},
    {1429,"MC_POST_GRID_ENTITY_WEB_UPDATE"},
    {1430,"MC_PRE_GRID_ENTITY_TNT_UPDATE"},
    {1431,"MC_POST_GRID_ENTITY_TNT_UPDATE"},
    {1432,"MC_PRE_GRID_ENTITY_SPIKES_RENDER"},
    {1433,"MC_POST_GRID_ENTITY_SPIKES_RENDER"},
    {1434,"MC_PRE_GRID_ENTITY_WEB_RENDER"},
    {1435,"MC_POST_GRID_ENTITY_WEB_RENDER"},
    {1436,"MC_PRE_GRID_ENTITY_TNT_RENDER"},
    {1437,"MC_POST_GRID_ENTITY_TNT_RENDER"},
    {1438,"MC_PRE_GRID_ENTITY_TRAPDOOR_RENDER"},
    {1439,"MC_POST_GRID_ENTITY_TRAPDOOR_RENDER"},
    {1440,"MC_PRE_GRID_ENTITY_STAIRCASE_RENDER"},
    {1441,"MC_POST_GRID_ENTITY_STAIRCASE_RENDER"},
    {1444,"MC_PRE_GRID_ENTITY_DECORATION_RENDER"},
    {1445,"MC_POST_GRID_ENTITY_DECORATION_RENDER"},
    {1446,"MC_PRE_GRID_ENTITY_DOOR_RENDER"},
    {1447,"MC_POST_GRID_ENTITY_DOOR_RENDER"},
    {1448,"MC_PRE_GRID_ENTITY_FIRE_RENDER"},
    {1449,"MC_POST_GRID_ENTITY_FIRE_RENDER"},
    {1450,"MC_PRE_GRID_ENTITY_LOCK_RENDER"},
    {1451,"MC_POST_GRID_ENTITY_LOCK_RENDER"},
    {1452,"MC_PRE_GRID_ENTITY_TELEPORTER_RENDER"},
    {1453,"MC_POST_GRID_ENTITY_TELEPORTER_RENDER"},
    {1454,"MC_PRE_GRID_ENTITY_PIT_RENDER"},
    {1455,"MC_POST_GRID_ENTITY_PIT_RENDER"},
    {1456,"MC_PRE_GRID_ENTITY_POOP_RENDER"},
    {1457,"MC_POST_GRID_ENTITY_POOP_RENDER"},
    {1458,"MC_PRE_GRID_ENTITY_ROCK_RENDER"},
    {1459,"MC_POST_GRID_ENTITY_ROCK_RENDER"},
    {1460,"MC_PRE_GRID_ENTITY_PRESSUREPLATE_RENDER"},
    {1461,"MC_POST_GRID_ENTITY_PRESSUREPLATE_RENDER"},
    {1462,"MC_PRE_GRID_ENTITY_WALL_RENDER"},
    {1463,"MC_POST_GRID_ENTITY_WALL_RENDER"},
    {1464,"MC_MENU_INPUT_ACTION"},
    {1470,"MC_POST_SAVESLOT_LOAD"},
};
static_assert(sizeof(kCallbacks)/sizeof(kCallbacks[0])==111);
constexpr RepentogonEnumBinding kAliases[]={{"ModCallbacks","MC_HUD_POST_UPDATE",1021}};
constexpr RepentogonApiBinding kApis[]={
    {{0x07020001,ApiDomain::Rng,"RNG","SetSeed",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRngSetSeed,nullptr,nullptr,true},
    {{0x03020001,ApiDomain::Level,"Level","GetDimension",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonLevelGetDimension},
    {{0x03020002,ApiDomain::Level,"Level","SetStage",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonLevelSetStage,nullptr,nullptr,true},
    {{0x0E020001,ApiDomain::Isaac,"GridEntity","ToTrapDoor",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonGridToTrapDoor},
    {{0x0E020002,ApiDomain::Isaac,"Isaac","IsInGame",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonIsaacIsInGame,nullptr,nullptr,true},
    {{0x0E020003,ApiDomain::Isaac,"PersistentGameData","GetEventCounter",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonPersistentGameDataGetEventCounter},
    {{0x0E020004,ApiDomain::Isaac,"PersistentGameData","IsItemInCollection",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonPersistentGameDataIsItemInCollection},
    {{0x0E020005,ApiDomain::Isaac,"EntityPlayer","GetHealthType",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPlayerGetHealthType},
    {{0x0E020006,ApiDomain::Isaac,"EntityPlayer","GetMarkedTarget",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPlayerGetMarkedTarget},
    {{0x0E020007,ApiDomain::Isaac,"EntityPlayer","IsLocalPlayer",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPlayerIsLocalPlayer},
    {{0x0E020008,ApiDomain::Isaac,"PlayerManager","AnyoneHasCollectible",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonPlayerManagerAnyoneHasCollectible},
    {{0x0E020009,ApiDomain::Isaac,"PlayerManager","AnyoneHasTrinket",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonPlayerManagerAnyoneHasTrinket},
    {{0x0E02000A,ApiDomain::Isaac,"EntityPlayer","GetDeadEyeCharge",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPlayerGetDeadEyeCharge},
    {{0x0E02000B,ApiDomain::Isaac,"EntityPlayer","GetPurityState",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPlayerGetPurityState},
    {{0x0E02000C,ApiDomain::Isaac,"Entity","SetDead",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntitySetDead},
    {{0x04020001,ApiDomain::Room,"Room","SetWaterAmount",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomSetWaterAmount},
    {{0x04020002,ApiDomain::Room,"Room","SetWaterCurrent",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomSetWaterCurrent},
    {{0x04020003,ApiDomain::Room,"Room","GetGreedWaveTimer",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomGetGreedWaveTimer},
    {{0x04020004,ApiDomain::Room,"Room","SetGreedWaveTimer",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomSetGreedWaveTimer},
    {{0x0E020100,ApiDomain::Isaac,"ProceduralItemManager","GetProceduralItem",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemManagerGetProceduralItem},
    {{0x0E020101,ApiDomain::Isaac,"ProceduralItem","GetTargetItem",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetTargetItem},
    {{0x0E020102,ApiDomain::Isaac,"ProceduralItem","GetEffectCount",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetEffectCount},
    {{0x0E020103,ApiDomain::Isaac,"ProceduralItem","GetEffect",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetEffect},
    {{0x0E020104,ApiDomain::Isaac,"ProceduralItem","GetSpeed",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetSpeed},
    {{0x0E020105,ApiDomain::Isaac,"ProceduralItem","GetFireDelay",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetFireDelay},
    {{0x0E020106,ApiDomain::Isaac,"ProceduralItem","GetDamage",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetDamage},
    {{0x0E020107,ApiDomain::Isaac,"ProceduralItem","GetRange",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetRange},
    {{0x0E020108,ApiDomain::Isaac,"ProceduralItem","GetShotSpeed",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetShotSpeed},
    {{0x0E020109,ApiDomain::Isaac,"ProceduralItem","GetLuck",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralItemGetLuck},
    {{0x0E02010A,ApiDomain::Isaac,"ProceduralEffect","GetConditionType",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralEffectGetConditionType},
    {{0x0E02010B,ApiDomain::Isaac,"ProceduralEffect","GetConditionProperty",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralEffectGetConditionProperty},
    {{0x0E02010C,ApiDomain::Isaac,"ProceduralEffect","GetActionType",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralEffectGetActionType},
    {{0x0E02010D,ApiDomain::Isaac,"ProceduralEffect","GetActionProperty",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},ProceduralEffectGetActionProperty},
    {{0x0E02010E,ApiDomain::Isaac,"PocketItem","GetSlot",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},Api700PocketItemGetSlot},
    {{0x0E02010F,ApiDomain::Isaac,"PocketItem","GetType",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},Api700PocketItemGetType},
    {{0x0E020110,ApiDomain::Isaac,"MultiShotParams","GetNumLanesPerEye",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},Api600MultiShotParamsGetNumLanesPerEye},
    {{0x0E020111,ApiDomain::Isaac,"Entity","GiveMinecart",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityGiveMinecart},
    {{0x0E020112,ApiDomain::Isaac,"Entity","GetMinecart",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityGetMinecart},
    {{0x0E020113,ApiDomain::Isaac,"Entity","ToSlot",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityToSlot},
    {{0x0E020114,ApiDomain::Isaac,"EntitySlot","GetPrizeCollectible",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntitySlotGetPrizeCollectible},
    {{0x0E020115,ApiDomain::Isaac,"EntityPickup","GetCollectibleCycle",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPickupGetCollectibleCycle},
    {{0x0E020116,ApiDomain::Isaac,"EntityPickup","RemoveCollectibleCycle",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPickupRemoveCollectibleCycle},
    {{0x0E020117,ApiDomain::Isaac,"EntityPickup","GetFlipCollectible",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPickupGetFlipCollectible},
    {{0x0E020118,ApiDomain::Isaac,"EntityPickup","InitFlipState",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPickupInitFlipState},
    {{0x0E020119,ApiDomain::Isaac,"EntityPickup","GetVarData",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPickupGetVarData},
    {{0x0E02011A,ApiDomain::Isaac,"EntityPickup","SetVarData",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPickupSetVarData},
    {{0x0E02011B,ApiDomain::Isaac,"EntityPickup","AddCollectibleCycle",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPickupAddCollectibleCycle},
    {{0x0E023000,ApiDomain::Isaac,"EntityConfig","GetEntity",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityConfigGetEntity},
    {{0x0E023001,ApiDomain::Isaac,"EntityConfig","GetPlayer",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityConfigGetPlayer},
    {{0x0E023002,ApiDomain::Isaac,"EntityConfigEntity","CanBeChampion",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityConfigEntityCanBeChampion},
    {{0x0E023003,ApiDomain::Isaac,"EntityConfigEntity","GetStageHP",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityConfigEntityGetStageHP},
    {{0x0E023004,ApiDomain::Isaac,"EntityConfigEntity","GetCollisionRadius",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityConfigEntityGetCollisionRadius},
    {{0x0E023005,ApiDomain::Isaac,"EntityConfigPlayer","GetPortraitPath",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityConfigPlayerGetPortraitPath},
    {{0x0E023006,ApiDomain::Isaac,"EntityConfigPlayer","GetExtraPortraitPath",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityConfigPlayerGetExtraPortraitPath},
    {{0x0E023007,ApiDomain::Isaac,"EntityConfigPlayer","GetNameImagePath",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityConfigPlayerGetNameImagePath},
    {{0x0E026000,ApiDomain::Isaac,"EntityPlayer","GetDamageModifier",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPlayerGetDamageModifier},
    {{0x0E026001,ApiDomain::Isaac,"EntityPlayer","GetEdenDamage",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPlayerGetEdenDamage},
    {{0x0E026002,ApiDomain::Isaac,"EntityPlayer","GetD8DamageModifier",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPlayerGetD8DamageModifier},
    {{0x0E026003,ApiDomain::Isaac,"EntityPlayer","GetFlippedForm",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPlayerGetFlippedForm},
    {{0x0E026004,ApiDomain::Isaac,"EntityPickup","IsBlind",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonEntityPickupIsBlind},
    {{0x05010007,ApiDomain::ItemPool,"ItemPool","GetNumItemPools",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonItemPoolGetNumItemPools},
    {{0x05010008,ApiDomain::ItemPool,"ItemPool","GetCollectiblesFromPool",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonItemPoolGetCollectiblesFromPool},
    {{0x0E024000,ApiDomain::Isaac,"MenuManager","GetActiveMenu",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonMenuManagerGetActiveMenu},
    {{0x0E024001,ApiDomain::Isaac,"MenuManager","IsActive",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonMenuManagerIsActive},
    {{0x0E024002,ApiDomain::Isaac,"CollectionMenu","GetSelectedPage",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonCollectionMenuGetSelectedPage},
    {{0x0E024003,ApiDomain::Isaac,"CollectionMenu","GetSelectedElement",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonCollectionMenuGetSelectedElement},
    {{0x0E024004,ApiDomain::Isaac,"SaveMenu","GetDeletePopupSprite",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonSaveMenuGetDeletePopupSprite},
    {{0x0E024005,ApiDomain::Isaac,"MainMenu","GetContinueWidgetSprite",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonMainMenuGetContinueWidgetSprite},
    {{0x0E024006,ApiDomain::Isaac,"Isaac","WorldToMenuPosition",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonWorldToMenuPosition},
    {{0x0E024007,ApiDomain::Isaac,"RoomTransition","IsRenderingBossIntro",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomTransitionIsRenderingBossIntro},
    {{0x0E024008,ApiDomain::Isaac,"RoomTransition","GetVersusScreenSprite",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomTransitionGetVersusScreenSprite},
    {{0x0E024009,ApiDomain::Isaac,"Ambush","GetCurrentWave",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonAmbushGetCurrentWave},
    {{0x0E02400A,ApiDomain::Isaac,"NightmareScene","IsDogmaNightmare",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonNightmareSceneIsDogmaNightmare},
    {{0x0E02400B,ApiDomain::Isaac,"RoomDescriptor","GetDimension",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomDescriptorGetDimension},
    {{0x0E02400C,ApiDomain::Isaac,"RoomDescriptor","GetTaintedKeeperCoinSpawns",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomDescriptorGetTaintedKeeperCoinSpawns},
    {{0x0E02400D,ApiDomain::Isaac,"RoomDescriptor","SetTaintedKeeperCoinSpawns",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomDescriptorSetTaintedKeeperCoinSpawns},
    {{0x0E025000,ApiDomain::Isaac,"Sprite","GetLayerFrameData",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonSpriteGetLayerFrameData},
    {{0x0E025001,ApiDomain::Isaac,"Sprite","GetNullFrame",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonSpriteGetNullFrame},
    {{0x0E025002,ApiDomain::Isaac,"Sprite","GetCurrentAnimationData",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonSpriteGetCurrentAnimationData},
    {{0x0E025003,ApiDomain::Isaac,"Sprite","GetAnimationData",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonSpriteGetAnimationData},
    {{0x0E025004,ApiDomain::Isaac,"Sprite","GetLayer",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonSpriteGetLayer},
    {{0x0E025005,ApiDomain::Isaac,"AnimationFrame","GetStartFrame",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonAnimationFrameGetStartFrame},
    {{0x0E025006,ApiDomain::Isaac,"AnimationFrame","GetPivot",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonAnimationFrameGetPivot},
    {{0x0E025007,ApiDomain::Isaac,"AnimationFrame","GetWidth",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonAnimationFrameGetWidth},
    {{0x0E025008,ApiDomain::Isaac,"NullFrame","GetPos",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonNullFrameGetPos},
    {{0x0E025009,ApiDomain::Isaac,"NullFrame","GetScale",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonNullFrameGetScale},
    {{0x0E02500A,ApiDomain::Isaac,"AnimationData","GetLength",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonAnimationDataGetLength},
    {{0x0E02500B,ApiDomain::Isaac,"AnimationData","GetLayer",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonAnimationDataGetLayer},
    {{0x0E02500C,ApiDomain::Isaac,"AnimationLayer","GetFrame",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonAnimationLayerGetFrame},
    {{0x0E02500D,ApiDomain::Isaac,"LayerState","SetVisible",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonLayerStateSetVisible},
    {{0x0E02500E,ApiDomain::Isaac,"LayerState","SetPos",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonLayerStateSetPos},
    {{0x0E02500F,ApiDomain::Isaac,"LayerState","SetColor",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonLayerStateSetColor},
    {{0x0E025010,ApiDomain::Isaac,"LayerState","GetBlendMode",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonLayerStateGetBlendMode},
    {{0x0E025011,ApiDomain::Isaac,"BlendMode","Flag1",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonBlendModeGetFlag1},
    {{0x0E025012,ApiDomain::Isaac,"BlendMode","Flag2",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonBlendModeGetFlag2},
    {{0x0E025013,ApiDomain::Isaac,"BlendMode","Flag3",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonBlendModeGetFlag3},
    {{0x0E025014,ApiDomain::Isaac,"BlendMode","Flag4",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonBlendModeGetFlag4},
    {{0x04020010,ApiDomain::Room,"Room","RemoveGridEntityImmediate",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomRemoveGridEntityImmediate},
    {{0x04020011,ApiDomain::Room,"Room","SetBackdropType",{},0,ThreadAffinity::ManagedCallback,
      ApiMaturity::Experimental},RepentogonRoomSetBackdropType},
};
// A bounded read-only ID map addresses the cached states, not the ordinary ID array.
constexpr auto MakeStateIndices() noexcept {
    std::array<std::uint8_t,1472-1000> indices{};
    for(auto& index:indices)index=255;
    for(std::size_t i=0;i<111;++i)indices[kCallbacks[i].id-1000]=static_cast<std::uint8_t>(i);
    return indices;
}
constexpr auto kStateIndices=MakeStateIndices();
std::array<ExtendedCallbackState*,111> g_States{};
void Reset() noexcept {g_States.fill(nullptr);}

bool Ready() noexcept {
    return g_NativePort&&g_NativePort->ready&&g_NativePort->install&&g_NativePort->ready();
}
int Initialize(lua_State* state) {
    for(std::size_t i=0;i<g_States.size();++i) {
        g_States[i]=FindExtendedCallback(kCallbacks[i].id);
        if(!g_States[i])return luaL_error(state,"REPENTOGON callback state unavailable");
    }
    if(!g_NativePort||!g_NativePort->install||!g_NativePort->install())
        return luaL_error(state,"REPENTOGON callback hooks unavailable");
    RegisterProceduralItemApi(state);
    RegisterPlayerManagerApi(state);
    RegisterRepentogonEntityConfigViews(state);
    RegisterRepentogonSpriteViews(state);
    RegisterRepentogonMenuWorldApi(state);
    RegisterRepentogonRemainingBulkViews(state);
    return 0;
}
}
void SetNativePort(const NativePort* port) noexcept { g_NativePort=port; }
bool UpdatePaused() noexcept {
    return g_ExtendedCallbackDelivery&&g_NativePort&&g_NativePort->updatePaused&&g_NativePort->updatePaused();
}
bool HasSpriteValidator() noexcept {return g_NativePort&&g_NativePort->spriteAlive;}
bool CallbackSpriteAlive(std::uintptr_t address) noexcept {
    return address&&HasSpriteValidator()&&g_NativePort->spriteAlive(address);
}
bool HasNativePort() noexcept { return g_NativePort!=nullptr; }
constinit const RepentogonBatch kCallbackBatch{"callbacks",kApis,sizeof(kApis)/sizeof(kApis[0]),kAliases,1,kCallbacks,111,Initialize,Reset,Ready};
const RepentogonBatch& CallbackBatch() noexcept {return kCallbackBatch;}
const ExtendedCallbackState* FindCallbackState(std::uint32_t id) noexcept {
    if(id>=1000&&id<1472) {
        const auto index=kStateIndices[id-1000];
        if(index!=255&&g_States[index])return g_States[index];
    }
    return FindExtendedCallback(id);
}
bool Listening(std::uint32_t id) noexcept {
    if(!g_ExtendedCallbackDelivery||!g_ExtendedCallbackEnabledCount)return false;
    const auto* state=FindCallbackState(id);
    return state&&state->enabled;
}
Result Dispatch(const Event& event) noexcept {
    if(!Listening(event.id))return {};
    return LuaRuntime::DispatchRepentogonCallback(event);
}
} // namespace isaac::runtime::repentogon
