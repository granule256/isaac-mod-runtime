#pragma once

#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {
int RepentogonEntityPlayerGetHealthType(lua_State* state);
int RepentogonEntityPlayerGetMarkedTarget(lua_State* state);
int RepentogonEntityPlayerIsLocalPlayer(lua_State* state);

#if !defined(__SWITCH__)
using RepentogonPlayerIntHost = std::int64_t (*)(void* player);
using RepentogonPlayerPointerHost = std::uintptr_t (*)(void* player);
void SetRepentogonPlayerGetHealthTypeHost(RepentogonPlayerIntHost) noexcept;
void SetRepentogonPlayerGetMarkedTargetHost(RepentogonPlayerPointerHost) noexcept;
void SetRepentogonPlayerIsLocalPlayerHost(RepentogonPlayerIntHost) noexcept;
#endif
}
