#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

void RegisterRepentogonBocViews(lua_State* state);

int RepentogonEntityPlayerCalculateBagOfCraftingOutput(lua_State* state);
int RepentogonEntityPlayerGetBagOfCraftingContent(lua_State* state);
int RepentogonEntityPlayerGetBagOfCraftingOutput(lua_State* state);
int RepentogonEntityPlayerGetActiveItemDesc(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonBocNativeTestBindings {
    std::int32_t (*calculate)(void*, const void*, bool){};
};
void SetRepentogonBocNativeTestBindings(RepentogonBocNativeTestBindings) noexcept;
#endif

}
