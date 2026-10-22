#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api100ItemPoolAddBibleUpgrade(lua_State*);
int Api100ItemPoolForceAddPillEffect(lua_State*);
int Api100ItemPoolGetCard(lua_State*);
int Api100ItemPoolGetPill(lua_State*);
int Api100ItemPoolGetTrinket(lua_State*);
int Api100ItemPoolRemoveTrinket(lua_State*);
int Api100ItemPoolResetRoomBlacklist(lua_State*);
int Api100ItemPoolResetTrinkets(lua_State*);
int Api100LevelApplyBlueMapEffect(lua_State*);
int Api100LevelApplyCompassEffect(lua_State*);
int Api100LevelApplyMapEffect(lua_State*);
int Api100LevelCanOpenChallengeRoom(lua_State*);
int Api100LevelCanSpawnDevilRoom(lua_State*);
int Api100LevelCanStageHaveCurseOfLabyrinth(lua_State*);
int Api100LevelChangeRoom(lua_State*);
int Api100LevelInitializeDevilAngelRoom(lua_State*);
int Api100LevelMakeRedRoomDoor(lua_State*);
int Api100LevelRemoveCompassEffect(lua_State*);
int Api100LevelSetRedHeartDamage(lua_State*);
int Api100LevelShowMap(lua_State*);
int Api100LevelShowName(lua_State*);
int Api100LevelUncoverHiddenDoor(lua_State*);
int Api100RoomDamageGrid(lua_State*);
int Api100RoomGetBrokenWatchState(lua_State*);
int Api100RoomGetDevilRoomChance(lua_State*);
int Api100RoomGetDungeonRockIdx(lua_State*);
int Api100RoomGetLightingAlpha(lua_State*);
int Api100RoomGetRandomTileIndex(lua_State*);
int Api100RoomHasLava(lua_State*);
int Api100RoomHasWater(lua_State*);
int Api100RoomIsLShapedRoom(lua_State*);
int Api100RoomRespawnEnemies(lua_State*);
int Api100RoomSetBrokenWatchState(lua_State*);
int Api100RoomShopReshuffle(lua_State*);
int Api100RoomShopRestockFull(lua_State*);
int Api100RoomShopRestockPartial(lua_State*);
int Api100RoomTriggerClear(lua_State*);
int Api100RoomTrySpawnBlueWombDoor(lua_State*);
int Api100RoomTrySpawnBossRushDoor(lua_State*);
int Api100RoomTrySpawnMegaSatanRoomDoor(lua_State*);
int Api100RoomTrySpawnSecretExit(lua_State*);
int Api100RoomTrySpawnTheVoidDoor(lua_State*);
enum class Api100ScalarNative:unsigned{ItemPoolAddBibleUpgrade,ItemPoolForceAddPillEffect,ItemPoolGetCard,ItemPoolGetPill,ItemPoolGetTrinket,ItemPoolRemoveTrinket,ItemPoolResetRoomBlacklist,ItemPoolResetTrinkets,LevelApplyBlueMapEffect,LevelApplyCompassEffect,LevelApplyMapEffect,LevelCanOpenChallengeRoom,LevelCanSpawnDevilRoom,LevelCanStageHaveCurseOfLabyrinth,LevelChangeRoom,LevelInitializeDevilAngelRoom,LevelMakeRedRoomDoor,LevelRemoveCompassEffect,LevelSetRedHeartDamage,LevelShowMap,LevelShowName,LevelUncoverHiddenDoor,RoomDamageGrid,RoomGetBrokenWatchState,RoomGetDevilRoomChance,RoomGetDungeonRockIdx,RoomGetLightingAlpha,RoomGetRandomTileIndex,RoomHasLava,RoomHasWater,RoomIsLShapedRoom,RoomRespawnEnemies,RoomSetBrokenWatchState,RoomShopReshuffle,RoomShopRestockFull,RoomShopRestockPartial,RoomTriggerClear,RoomTrySpawnBlueWombDoor,RoomTrySpawnBossRushDoor,RoomTrySpawnMegaSatanRoomDoor,RoomTrySpawnSecretExit,RoomTrySpawnTheVoidDoor,Count};
#if !defined(__SWITCH__)
struct Api100ScalarNativeTestBindings{std::uintptr_t methods[static_cast<unsigned>(Api100ScalarNative::Count)];};
void SetApi100ScalarNativeTestBindings(Api100ScalarNativeTestBindings) noexcept;
#endif
}
