#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

int RegisterRepentogonTimerApi(lua_State* state);
void ResetRepentogonTimerApi() noexcept;
int RepentogonIsaacCreateTimer(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonTimerNativeTestBindings {
    void* (*createTimer)(void (*)(void*), std::uint32_t, std::int32_t, bool){};
};
void SetRepentogonTimerNativeTestBindings(
    RepentogonTimerNativeTestBindings bindings) noexcept;
#endif

}
