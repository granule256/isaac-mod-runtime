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
using RepentogonPlayerManagerTrinketMultiplierHost =
    std::int32_t (*)(void*, std::uint32_t);
void SetRepentogonPlayerManagerTrinketHost(
    RepentogonPlayerManagerTrinketHost function) noexcept;
void SetRepentogonPlayerManagerTrinketMultiplierHost(
    RepentogonPlayerManagerTrinketMultiplierHost function) noexcept;
#endif
}
