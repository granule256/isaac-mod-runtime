#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int RPlusPlayerAddBlackHearts(lua_State*);
int RPlusPlayerAddMaxHearts(lua_State*);
int RPlusPlayerAddRottenHearts(lua_State*);
int RPlusPlayerAddSoulHearts(lua_State*);
int RPlusPlayerCanPickBlackHearts(lua_State*);
int RPlusPlayerCanPickBoneHearts(lua_State*);
int RPlusPlayerCanPickGoldenHearts(lua_State*);
int RPlusPlayerCanPickRottenHearts(lua_State*);
int RPlusPlayerGetGoldenHearts(lua_State*);
int RPlusPlayerGetHeartLimit(lua_State*);
int RPlusPlayerGetRottenHearts(lua_State*);
int RPlusPlayerHasFullHeartsAndSoulHearts(lua_State*);
int RPlusPlayerIsBlackHeart(lua_State*);
int RPlusPlayerIsBoneHeart(lua_State*);
int RPlusPlayerRemoveBlackHeart(lua_State*);
int RPlusPlayerSetFullHearts(lua_State*);
#if !defined(__SWITCH__)
struct RPlusHealthNativeTestBindings { std::uintptr_t methods[13]{}; };
void SetRPlusHealthNativeTestBindings(RPlusHealthNativeTestBindings) noexcept;
#endif
}
