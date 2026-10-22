#pragma once
struct lua_State;
namespace isaac::runtime {
int Api600RoomGetShopLevel(lua_State*);
int Api600RoomGetLavaIntensity(lua_State*);
int Api600RoomHasSlowDown(lua_State*);
int Api600RoomSetSlowDown(lua_State*);
int Api600RoomIsFirstEnemyDead(lua_State*);
int Api600RoomSetFirstEnemyDead(lua_State*);
int Api600RoomInvalidatePickupVision(lua_State*);
int Api600RoomEmitBloodFromWalls(lua_State*);
}
