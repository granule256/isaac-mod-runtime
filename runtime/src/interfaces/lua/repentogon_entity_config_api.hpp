#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
void RegisterRepentogonEntityConfigViews(lua_State*);
int RepentogonEntityConfigGetEntity(lua_State*);
int RepentogonEntityConfigGetPlayer(lua_State*);
int RepentogonEntityConfigGetMaxPlayerType(lua_State*);
int RepentogonEntityConfigPlayerIsHidden(lua_State*);
int RepentogonEntityConfigPlayerIsTainted(lua_State*);
int RepentogonEntityConfigPlayerGetName(lua_State*);
bool RepentogonEntityConfigPlayerTaintedByType(
    std::int32_t type, bool* tainted) noexcept;
int RepentogonEntityConfigEntityCanBeChampion(lua_State*);
int RepentogonEntityConfigEntityGetStageHP(lua_State*);
int RepentogonEntityConfigEntityGetCollisionRadius(lua_State*);
int RepentogonEntityConfigEntityGetAnm2Path(lua_State*);
int RepentogonEntityConfigEntityGetEntityTags(lua_State*);
int RepentogonEntityConfigEntityHasEntityTags(lua_State*);
int RepentogonEntityConfigPlayerGetPortraitPath(lua_State*);
int RepentogonEntityConfigPlayerGetExtraPortraitPath(lua_State*);
int RepentogonEntityConfigPlayerGetNameImagePath(lua_State*);
int RepentogonEntityConfigPlayerGetModdedMenuBackgroundSprite(lua_State*);
int RepentogonEntityConfigPlayerGetModdedMenuPortraitSprite(lua_State*);
int RepentogonEntityConfigPlayerGetModdedGameOverSprite(lua_State*);
int RepentogonEntityConfigPlayerGetModdedCoopMenuSprite(lua_State*);
int RepentogonEntityConfigPlayerGetModdedControlsSprite(lua_State*);
#if !defined(__SWITCH__)
struct RepentogonEntityConfigNativeTestBindings {
    void* (*getEntity)(void*,std::int32_t,std::uint32_t,std::uint32_t){};
    void* (*getPlayer)(void*,std::int32_t){};
};
void SetRepentogonEntityConfigNativeTestBindings(RepentogonEntityConfigNativeTestBindings) noexcept;
#endif
}
