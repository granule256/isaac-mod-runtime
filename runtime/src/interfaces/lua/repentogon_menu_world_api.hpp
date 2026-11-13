#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

int RepentogonMenuManagerGetActiveMenu(lua_State* state);
int RepentogonMenuManagerIsActive(lua_State* state);
int RepentogonCollectionMenuGetSelectedPage(lua_State* state);
int RepentogonCollectionMenuGetSelectedElement(lua_State* state);
int RepentogonSaveMenuGetDeletePopupSprite(lua_State* state);
int RepentogonMainMenuGetContinueWidgetSprite(lua_State* state);

int RepentogonWorldToMenuPosition(lua_State* state);

int RepentogonRoomTransitionIsRenderingBossIntro(lua_State* state);
int RepentogonRoomTransitionGetVersusScreenSprite(lua_State* state);
int RepentogonRoomTransitionStartBossIntro(lua_State* state);

int RepentogonAmbushGetCurrentWave(lua_State* state);
int RepentogonNightmareSceneIsDogmaNightmare(lua_State* state);
int RepentogonNightmareSceneGetProgressBarSprite(lua_State* state);
int RepentogonNightmareSceneGetBackgroundSprite(lua_State* state);
int RepentogonGameIsPauseMenuOpen(lua_State* state);
int RepentogonIsaacGetCompletionMark(lua_State* state);

int RepentogonRoomDescriptorGetDimension(lua_State* state);
int RepentogonRoomDescriptorGetTaintedKeeperCoinSpawns(lua_State* state);
int RepentogonRoomDescriptorSetTaintedKeeperCoinSpawns(lua_State* state);

[[nodiscard]] bool RepentogonMenuWorldSpriteAlive(
    std::uintptr_t sprite) noexcept;

int RegisterRepentogonMenuWorldApi(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonMenuWorldNativeTestBindings {
    bool (*isRenderingBossIntro)(const void*){};
    void (*startBossIntro)(void*, std::uint32_t, std::uint32_t){};
    std::int32_t (*completionCounterId)(std::int32_t, std::int32_t){};
};
void SetRepentogonMenuWorldNativeTestBindings(
    RepentogonMenuWorldNativeTestBindings bindings) noexcept;
#endif

}  // namespace isaac::runtime
