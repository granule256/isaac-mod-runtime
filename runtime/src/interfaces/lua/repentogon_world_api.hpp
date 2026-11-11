#pragma once

extern "C" {
#include "lua.h"
}

namespace isaac::runtime {

// REPENTOGON Level:GetDimension(): current Level dimension at Level + 0x21560.
int RepentogonLevelGetDimension(lua_State* state);

// REPENTOGON GridEntity:ToTrapDoor(): exact TrapDoor vtable/type downcast.
int RepentogonGridToTrapDoor(lua_State* state);

} // namespace isaac::runtime
