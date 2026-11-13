#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

int RepentogonCharacterMenuGetActiveStatus(lua_State* state);
int RepentogonCharacterMenuGetDifficulty(lua_State* state);
int RepentogonCharacterMenuGetIsCharacterUnlocked(lua_State* state);
int RepentogonCharacterMenuGetPageSwapWidgetSprite(lua_State* state);
int RepentogonCharacterMenuGetSelectedCharacterID(lua_State* state);
int RepentogonCharacterMenuGetSelectedCharacterMenu(lua_State* state);
int RepentogonCharacterMenuGetSelectedCharacterPlayerType(lua_State* state);
int RepentogonCharacterMenuGetPlayerTypeFromCharacterMenuID(lua_State* state);

int RepentogonMenuManagerSetInputMask(lua_State* state);
int RepentogonMenuManagerSetColorModifier(lua_State* state);

// Input actions use the PC ButtonAction numbering exposed to mods. While a
// mask is active, only explicitly selected bits answer true.
[[nodiscard]] bool RepentogonMenuManagerInputMaskAllows(
    std::uint32_t buttonAction) noexcept;
[[nodiscard]] bool RepentogonMenuManagerInputMaskActive() noexcept;
void BeginRepentogonMainMenuRenderInputMaskScope() noexcept;
void EndRepentogonMainMenuRenderInputMaskScope() noexcept;
void ClearRepentogonMenuInputMask() noexcept;

// Exact live members owned by the character scene and completion widget.
// The private NativePort folds this predicate into callback sprite validation.
[[nodiscard]] bool RepentogonCharacterMenuSpriteAlive(
    std::uintptr_t sprite) noexcept;

// Private native hooks publish through these O(1) dispatchers. The central
// callback layer owns the Lua argument representation for each event.
[[nodiscard]] bool DispatchRepentogonPreCompletionMarksRender(
    std::uintptr_t sprite, const void* renderPos, const void* renderScale,
    std::int32_t playerType) noexcept;
void DispatchRepentogonPostCompletionMarksRender(
    std::uintptr_t sprite, const void* renderPos, const void* renderScale,
    std::int32_t playerType) noexcept;
void DispatchRepentogonPreRenderCustomCharacterMenu(
    std::int32_t playerType, const void* renderPos,
    std::uintptr_t vanillaSprite) noexcept;
void DispatchRepentogonPostRoomTransitionUpdate(
    std::int32_t transitionMode) noexcept;

int RegisterRepentogonCharacterMenuApi(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonCharacterMenuNativeTestBindings {
    std::int32_t (*selectedPlayerType)(const void*, std::int32_t){};
    void (*menuSetColorModifier)(void*, const void*, bool, float){};
};
void SetRepentogonCharacterMenuNativeTestBindings(
    RepentogonCharacterMenuNativeTestBindings bindings) noexcept;
#endif

}  // namespace isaac::runtime
