#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

void RegisterRepentogonRemainingBulkViews(lua_State* state);

int RepentogonEntityPlayerGetDamageModifier(lua_State* state);
int RepentogonEntityPlayerGetEdenDamage(lua_State* state);
int RepentogonEntityPlayerGetD8DamageModifier(lua_State* state);
int RepentogonEntityPlayerGetFlippedForm(lua_State* state);
int RepentogonEntityPickupIsBlind(lua_State* state);
int RepentogonItemPoolGetNumItemPools(lua_State* state);
int RepentogonItemPoolGetCollectiblesFromPool(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonRemainingBulkNativeTestBindings {
    void* itemPool{};
};
void SetRepentogonRemainingBulkNativeTestBindings(
    RepentogonRemainingBulkNativeTestBindings value) noexcept;
#endif

}
