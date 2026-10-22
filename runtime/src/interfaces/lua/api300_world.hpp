#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api300LevelGetRoomCount(lua_State*);
int Api300LevelIsDevilRoomDisabled(lua_State*);
int Api300LevelDisableDevilRoom(lua_State*);
int Api300LevelSetHeartPicked(lua_State*);
int Api300LevelGetHeartPicked(lua_State*);
int Api300LevelSetCanSeeEverything(lua_State*);
int Api300LevelGetDungeonPlacementSeed(lua_State*);
int Api300LevelAddAngelRoomChance(lua_State*);
int Api300LevelGetAngelRoomChance(lua_State*);
int Api300PathFinderHasDirectPath(lua_State*);
int Api300PathFinderGetEvadeMovementCountdown(lua_State*);
int Api300PathFinderSetCanCrushRocks(lua_State*);
int Api300SeedsClearStartSeed(lua_State*);
int Api300SeedsIsInitialized(lua_State*);
int Api300SeedsGetPlayerInitSeed(lua_State*);
int Api300SeedsCountSeedEffects(lua_State*);
int Api300EntityKnifeGetRenderZ(lua_State*);
int Api300EntityLaserGetRenderZ(lua_State*);
int Api300EntityNPCGetAliveEnemyCount(lua_State*);
int Api300EntityEffectIsPlayerCreep(lua_State*);
int Api300ItemConfigIsValidCollectible(lua_State*);
int Api300EntityNPCCalcTargetPosition(lua_State*);
int Api300EntityNPCCanBeDamagedFromVelocity(lua_State*);
int Api300EntityNPCCanReroll(lua_State*);
int Api300SeedsClearSeedEffects(lua_State*);
int Api300SeedsGetStartSeedString(lua_State*);
int Api300SeedsIsSeedComboBanned(lua_State*);
int Api300EntityTearClearTearFlags(lua_State*);
int Api300EntityTearHasTearFlags(lua_State*);
int Api300EntityBombClearTearFlags(lua_State*);
int Api300EntityBombHasTearFlags(lua_State*);
int Api300EntityKnifeClearTearFlags(lua_State*);
int Api300EntityKnifeHasTearFlags(lua_State*);
int Api300EntityLaserClearTearFlags(lua_State*);
int Api300EntityLaserHasTearFlags(lua_State*);

enum class Api300WorldNative:unsigned{EntityEffectIsPlayerCreep,ItemConfigIsValidCollectible,EntityNPCCalcTargetPosition,EntityNPCCanBeDamagedFromVelocity,EntityNPCCanReroll,EntityNPCGetAliveEnemyCount,EntityKnifeGetRenderZ,EntityLaserGetRenderZ,TearFlagsSetter,BombFlagsSetter,Seed2String,SeedTreeDestroy,EntityGetRenderZ,Count};
#if !defined(__SWITCH__)
struct Api300WorldNativeTestBindings{std::uintptr_t methods[static_cast<unsigned>(Api300WorldNative::Count)];};
void SetApi300WorldNativeTestBindings(Api300WorldNativeTestBindings)noexcept;
#endif
}
