#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
void RegisterRepentogonEntityConfigViews(lua_State*);
int RepentogonEntityConfigGetEntity(lua_State*);
int RepentogonEntityConfigGetPlayer(lua_State*);
int RepentogonEntityConfigEntityCanBeChampion(lua_State*);
int RepentogonEntityConfigEntityGetStageHP(lua_State*);
int RepentogonEntityConfigEntityGetCollisionRadius(lua_State*);
int RepentogonEntityConfigPlayerGetPortraitPath(lua_State*);
int RepentogonEntityConfigPlayerGetExtraPortraitPath(lua_State*);
int RepentogonEntityConfigPlayerGetNameImagePath(lua_State*);
#if !defined(__SWITCH__)
struct RepentogonEntityConfigNativeTestBindings {
    void* (*getEntity)(void*,std::int32_t,std::uint32_t,std::uint32_t){};
    void* (*getPlayer)(void*,std::int32_t){};
};
void SetRepentogonEntityConfigNativeTestBindings(RepentogonEntityConfigNativeTestBindings) noexcept;
#endif
}
