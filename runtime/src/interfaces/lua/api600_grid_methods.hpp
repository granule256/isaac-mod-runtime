#pragma once
struct lua_State;
namespace isaac::runtime {
int Api600RoomGetDeliriumDistance(lua_State*);
int Api600GridEntityDoorIsBusted(lua_State*);
int Api600GridEntityDoorIsLocked(lua_State*);
int Api600GridEntityDoorIsKeyFamiliarTarget(lua_State*);
int Api600GridEntityDoorGetSpriteOffset(lua_State*);
int Api600GridEntityRockGetRubbleAnim(lua_State*);
int Api600GameGetLastDevilRoomStage(lua_State*);
int Api600GameGetLastLevelWithDamage(lua_State*);
int Api600GameGetLastLevelWithoutHalfHp(lua_State*);
}
