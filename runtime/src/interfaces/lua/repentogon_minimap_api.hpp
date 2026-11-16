#pragma once

struct lua_State;

namespace isaac::runtime {

struct RepentogonMinimapVector {
    float x;
    float y;
};

void RegisterRepentogonMinimapApi(lua_State* state);

#if !defined(__SWITCH__)
void SetRepentogonMinimapNativeTestBinding(
    RepentogonMinimapVector (*displayedSize)(void*)) noexcept;
#endif

}  // namespace isaac::runtime
