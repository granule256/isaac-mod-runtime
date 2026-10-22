#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api100EntityBloodExplode(lua_State*);
int Api100EntityGetLastParent(lua_State*);
int Api100EntityGetLastChild(lua_State*);
int Api100EntityHasFullHealth(lua_State*);
int Api100EntityIsFrame(lua_State*);
enum class Api100CoreNative:unsigned{BloodExplode,GetLastParent,GetLastChild,HasFullHealth,IsFrame,Count};
#if !defined(__SWITCH__)
struct Api100CoreNativeTestBindings{std::uintptr_t methods[5];};
void SetApi100CoreNativeTestBindings(Api100CoreNativeTestBindings)noexcept;
#endif
}
