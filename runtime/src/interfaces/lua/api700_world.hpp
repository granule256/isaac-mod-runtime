#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime{
int Api700RoomScreenWrapPosition(lua_State*);
int Api700EntityLaserCalculateEndPoint(lua_State*);
int Api700SeedsGetSeedEffect(lua_State*);
int Api700SeedsIsSpecialSeed(lua_State*);
int Api700IsaacAddPillEffectToPool(lua_State*);
int Api700IsaacWorldToScreenDistance(lua_State*);
int Api700RoomGetLRoomAreaDesc(lua_State*);
int Api700RoomGetLRoomTileDesc(lua_State*);
int Api700ItemPoolAddRoomBlacklist(lua_State*);
int Api700LevelGetDevilAngelRoomRNG(lua_State*);
#if !defined(__SWITCH__)
void SetApi700WorldNativeTestBindings(const std::uintptr_t*,unsigned)noexcept;
#endif
}

namespace isaac::runtime{int Api700GameGetFont(lua_State*);int Api700GameGetAmbush(lua_State*);int Api700GameGetItemOverlay(lua_State*);}

namespace isaac::runtime{int Api700GameShowFortune(lua_State*);int Api700GameShowRule(lua_State*);int Api700IsaacGetCurseIdByName(lua_State*);}

namespace isaac::runtime{int Api700IsaacScreenToWorldDistance(lua_State*);int Api700IsaacGetScreenPointScale(lua_State*);}

namespace isaac::runtime{int Api700GameSpawnEntityDesc(lua_State*);}

namespace isaac::runtime {int Api700RoomGetEnemyDamageInflicted(lua_State*);}
