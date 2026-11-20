#pragma once

#include <cstdint>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {
int RepentogonEntitySetInvincible(lua_State* state);

struct RepentogonEntityVector {
    float x{},y{};
};

int RepentogonEntityGiveMinecart(lua_State* state);
int RepentogonEntityGetMinecart(lua_State* state);
int RepentogonEntityToSlot(lua_State* state);
int RepentogonEntitySlotGetPrizeCollectible(lua_State* state);
int RepentogonEntityPickupGetCollectibleCycle(lua_State* state);
int RepentogonEntityPickupGetPickupGhost(lua_State* state);
int RepentogonEntityPickupRemoveCollectibleCycle(lua_State* state);
int RepentogonEntityPickupGetFlipCollectible(lua_State* state);
int RepentogonEntityPickupInitFlipState(lua_State* state);
int RepentogonEntityPickupGetVarData(lua_State* state);
int RepentogonEntityPickupSetVarData(lua_State* state);
int RepentogonEntityPickupAddCollectibleCycle(lua_State* state);
int RepentogonEntityPickupGetCanRerollOverride(lua_State* state);
int RepentogonEntityPickupSetCanRerollOverride(lua_State* state);
int RepentogonEntityPickupClearCanRerollOverride(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonEntityNativeTestBindings {
    void* (*giveMinecart)(void*,const RepentogonEntityVector&,const RepentogonEntityVector&){};
};
void SetRepentogonEntityNativeTestBindings(RepentogonEntityNativeTestBindings) noexcept;
#endif
}
