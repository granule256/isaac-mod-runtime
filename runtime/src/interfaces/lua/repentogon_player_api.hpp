#pragma once

#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {
int RepentogonEntityPlayerGetHealthType(lua_State* state);
int RepentogonEntityPlayerGetMarkedTarget(lua_State* state);
int RepentogonEntityPlayerIsLocalPlayer(lua_State* state);
int RepentogonEntityPlayerGetDeadEyeCharge(lua_State* state);
int RepentogonEntityPlayerGetPurityState(lua_State* state);
int RepentogonEntityPlayerAddActiveCharge(lua_State* state);
int RepentogonEntitySetDead(lua_State* state);

#if !defined(__SWITCH__)
using RepentogonPlayerIntHost = std::int64_t (*)(void* player);
using RepentogonPlayerPointerHost = std::uintptr_t (*)(void* player);
using RepentogonPlayerAddActiveChargeHost = std::int32_t (*)(
    void* player, std::int32_t charge, std::int32_t slot,
    bool flashHUD, bool overcharge, bool force);
void SetRepentogonPlayerGetHealthTypeHost(RepentogonPlayerIntHost) noexcept;
void SetRepentogonPlayerGetMarkedTargetHost(RepentogonPlayerPointerHost) noexcept;
void SetRepentogonPlayerIsLocalPlayerHost(RepentogonPlayerIntHost) noexcept;
void SetRepentogonPlayerAddActiveChargeHost(
    RepentogonPlayerAddActiveChargeHost) noexcept;
#endif
}
