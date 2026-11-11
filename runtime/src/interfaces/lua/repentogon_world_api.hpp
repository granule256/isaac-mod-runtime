#pragma once
#include <cstdint>

extern "C" {
#include "lua.h"
}

namespace isaac::runtime {

// REPENTOGON Level:GetDimension(): current Level dimension at Level + 0x21560.
int RepentogonLevelGetDimension(lua_State* state);

// REPENTOGON GridEntity:ToTrapDoor(): exact TrapDoor vtable/type downcast.
int RepentogonGridToTrapDoor(lua_State* state);
int RepentogonLevelSetStage(lua_State* state);
int RepentogonRoomGetGreedWaveTimer(lua_State* state);
int RepentogonRoomSetGreedWaveTimer(lua_State* state);
#if !defined(__SWITCH__)
void SetRepentogonLevelSetStageHost(void (*)(void*,std::int32_t,std::int32_t)) noexcept;
#endif

} // namespace isaac::runtime
