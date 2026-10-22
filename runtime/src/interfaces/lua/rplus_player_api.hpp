#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int RPlusPlayerGetSubPlayer(lua_State*);
int RPlusPlayerGetDamageCooldown(lua_State*);
int RPlusPlayerSetMinDamageCooldown(lua_State*);
int RPlusPlayerResetDamageCooldown(lua_State*);
int RPlusPlayerAddSoulCharge(lua_State*);
int RPlusPlayerAddBloodCharge(lua_State*);
int RPlusPlayerAddJarHearts(lua_State*);
int RPlusPlayerGetJarHearts(lua_State*);
#if !defined(__SWITCH__)
// 宿主不能执行AArch64原件；仅宿主测试显式注入带附加效果的引擎替身。
struct RPlusPlayerNativeTestBindings {
    void (*addSoul)(void*,std::int32_t){};
    void (*addBlood)(void*,std::int32_t){};
    void (*addJar)(void*,std::int32_t){};
};
void SetRPlusPlayerNativeTestBindings(RPlusPlayerNativeTestBindings) noexcept;
#endif
}
