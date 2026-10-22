#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
std::uint32_t Api400NextRandomU32(lua_State*);
void RegisterApi400ProjectileParams(lua_State*);
int Api400EntityNPCFireProjectiles(lua_State*);
int Api400EntityNPCFireBossProjectiles(lua_State*);
#if !defined(__SWITCH__)
struct Api400ParamsNativeTestBindings {std::uintptr_t methods[3];};
void SetApi400ParamsNativeTestBindings(Api400ParamsNativeTestBindings)noexcept;
#endif
}
