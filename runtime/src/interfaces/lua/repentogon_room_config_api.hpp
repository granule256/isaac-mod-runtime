#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

int RepentogonRoomConfigGetRoomByStageTypeAndVariant(lua_State* state);
int RegisterRepentogonRoomConfigApi(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonRoomConfigNativeTestBindings {
    void* (*getRoom)(void*, std::uint32_t, std::uint32_t, std::uint32_t,
                     std::int32_t){};
};
void SetRepentogonRoomConfigNativeTestBindings(
    RepentogonRoomConfigNativeTestBindings bindings) noexcept;
#endif

}  // namespace isaac::runtime
