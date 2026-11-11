#pragma once

#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {
int RepentogonPlayerManagerAnyoneHasCollectible(lua_State* state);
int RepentogonPlayerManagerAnyoneHasTrinket(lua_State* state);
int RegisterPlayerManagerApi(lua_State* state);

#if !defined(__SWITCH__)
using RepentogonPlayerManagerTrinketHost = bool (*)(void*, std::uint32_t, bool);
void SetRepentogonPlayerManagerTrinketHost(
    RepentogonPlayerManagerTrinketHost function) noexcept;
#endif
}
