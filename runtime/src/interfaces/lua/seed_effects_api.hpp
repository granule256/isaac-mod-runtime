#pragma once
#include "infrastructure/memory/seed_effect_tree.hpp"
struct lua_State;
namespace isaac::runtime {
int MutateSeedEffect(lua_State*,std::uintptr_t game,std::int32_t effect,bool add);
#if !defined(__SWITCH__)
void SetSeedEffectNativeTestBindings(seed_effects::Bindings)noexcept;
#endif
}
