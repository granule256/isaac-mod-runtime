#pragma once

#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

struct RepentogonEntityVector {
    float x{},y{};
};

int RepentogonEntityGiveMinecart(lua_State* state);
int RepentogonEntityGetMinecart(lua_State* state);
int RepentogonEntityToSlot(lua_State* state);
int RepentogonEntitySlotGetPrizeCollectible(lua_State* state);
int RepentogonEntityPickupGetCollectibleCycle(lua_State* state);
int RepentogonEntityPickupRemoveCollectibleCycle(lua_State* state);
int RepentogonEntityPickupGetFlipCollectible(lua_State* state);
int RepentogonEntityPickupInitFlipState(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonEntityNativeTestBindings {
    void* (*giveMinecart)(void*,const RepentogonEntityVector&,const RepentogonEntityVector&){};
    void (*initFlipState)(void*){};
};
void SetRepentogonEntityNativeTestBindings(RepentogonEntityNativeTestBindings) noexcept;
#endif
}
