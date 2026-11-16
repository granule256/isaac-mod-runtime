#pragma once

struct lua_State;

namespace isaac::runtime {

// Installs the HUD heart snapshots and the player index used to select a HUD.
void RegisterRepentogonPlayerHudHearts(lua_State* state);

}  // namespace isaac::runtime
