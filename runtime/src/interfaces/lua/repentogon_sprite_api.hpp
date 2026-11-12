#pragma once

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

int RepentogonSpriteGetLayerFrameData(lua_State* state);
int RepentogonSpriteGetNullFrame(lua_State* state);
int RepentogonSpriteGetCurrentAnimationData(lua_State* state);
int RepentogonSpriteGetAnimationData(lua_State* state);
int RepentogonSpriteGetLayer(lua_State* state);

int RepentogonAnimationFrameGetStartFrame(lua_State* state);
int RepentogonAnimationFrameGetPivot(lua_State* state);
int RepentogonAnimationFrameGetWidth(lua_State* state);

int RepentogonNullFrameGetPos(lua_State* state);
int RepentogonNullFrameGetScale(lua_State* state);

int RepentogonAnimationDataGetLength(lua_State* state);
int RepentogonAnimationDataGetLayer(lua_State* state);

int RepentogonAnimationLayerGetFrame(lua_State* state);

int RepentogonLayerStateSetVisible(lua_State* state);
int RepentogonLayerStateSetPos(lua_State* state);
int RepentogonLayerStateSetColor(lua_State* state);
int RepentogonLayerStateGetBlendMode(lua_State* state);

int RepentogonBlendModeGetFlag1(lua_State* state);
int RepentogonBlendModeGetFlag2(lua_State* state);
int RepentogonBlendModeGetFlag3(lua_State* state);
int RepentogonBlendModeGetFlag4(lua_State* state);

// Publishes the complete connected Sprite/AnimationData/AnimationLayer/
// AnimationFrame/NullFrame/LayerState/BlendMode view family.
int RegisterRepentogonSpriteViews(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonSpriteNativeTestBindings {
    const void* (*getAnimationData)(const void*, const char*) noexcept{};
    void* (*getLayerInt)(void*, int) noexcept{};
    void* (*getLayerName)(void*, const char*) noexcept{};
    const void* (*getNullFrame)(const void*, const char*) noexcept{};
};
void SetRepentogonSpriteNativeTestBindings(
    RepentogonSpriteNativeTestBindings bindings) noexcept;
#endif

} // namespace isaac::runtime
