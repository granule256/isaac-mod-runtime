#pragma once

#include <cstddef>

extern "C" {
#include <lua.h>
}

namespace isaac::runtime {

inline constexpr char kRepentogonColorModifierMetatable[] =
    "IsaacRuntime.ColorModifier";

// Layout transcribed from REPENTOGON's ColorModState and confirmed by the
// fixed Switch NRO MenuManager::SetColorModifier @0x3FF9B8, which copies three
// 64-bit words from its const& argument.
struct RepentogonColorModifierValue {
    float r;
    float g;
    float b;
    float a;
    float brightness;
    float contrast;
};

static_assert(sizeof(RepentogonColorModifierValue) == 0x18);
static_assert(offsetof(RepentogonColorModifierValue, r) == 0x00);
static_assert(offsetof(RepentogonColorModifierValue, g) == 0x04);
static_assert(offsetof(RepentogonColorModifierValue, b) == 0x08);
static_assert(offsetof(RepentogonColorModifierValue, a) == 0x0c);
static_assert(offsetof(RepentogonColorModifierValue, brightness) == 0x10);
static_assert(offsetof(RepentogonColorModifierValue, contrast) == 0x14);

// Returns the typed userdata storage directly. The pointer remains valid for
// the lifetime of the Lua value and has the native ColorModState layout.
[[nodiscard]] RepentogonColorModifierValue* TryRepentogonColorModifierArgument(
    lua_State* state, int index) noexcept;
[[nodiscard]] RepentogonColorModifierValue* RequireRepentogonColorModifierArgument(
    lua_State* state, int index);

int CreateRepentogonColorModifierHandle(lua_State* state);
int RepentogonColorModifierIndex(lua_State* state);
int RepentogonColorModifierNewIndex(lua_State* state);
int RepentogonGameSetColorModifier(lua_State* state);
int RepentogonRoomUpdateColorModifier(lua_State* state);

// Publishes the callable global ColorModifier class and its value metatable.
int RegisterRepentogonColorModifierApi(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonColorModifierNativeTestBindings {
    void (*set)(void*, const RepentogonColorModifierValue&, bool, float){};
    RepentogonColorModifierValue (*compute)(const void*){};
};
void SetRepentogonColorModifierNativeTestBindings(
    RepentogonColorModifierNativeTestBindings bindings) noexcept;
#endif

} // namespace isaac::runtime
