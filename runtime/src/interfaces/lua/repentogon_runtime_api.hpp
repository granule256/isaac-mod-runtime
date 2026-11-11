#pragma once

struct lua_State;

namespace isaac::runtime {
int RepentogonIsaacIsInGame(lua_State* state);
int RepentogonRoomSetWaterAmount(lua_State* state);
int RepentogonRoomSetWaterCurrent(lua_State* state);
}
