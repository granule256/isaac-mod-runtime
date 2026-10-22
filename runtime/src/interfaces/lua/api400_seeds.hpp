#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api400SeedsSeed2String(lua_State*);
int Api400SeedsString2Seed(lua_State*);
int Api400SeedsIsStringValidSeed(lua_State*);
void PublishApi400SeedsStatics(lua_State*);
#if !defined(__SWITCH__)
void SetApi400SeedsNativeTestBindings(std::uintptr_t toString,std::uintptr_t toSeed,std::uintptr_t isValid=0)noexcept;
#endif
}
