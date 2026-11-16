#include "interfaces/lua/repentogon_color_modifier_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"

#include <cstring>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

struct ColorModifierField {
    const char* name;
    std::size_t offset;
};

constexpr ColorModifierField kFields[] = {
    {"R", offsetof(RepentogonColorModifierValue, r)},
    {"G", offsetof(RepentogonColorModifierValue, g)},
    {"B", offsetof(RepentogonColorModifierValue, b)},
    {"A", offsetof(RepentogonColorModifierValue, a)},
    {"Brightness", offsetof(RepentogonColorModifierValue, brightness)},
    {"Contrast", offsetof(RepentogonColorModifierValue, contrast)},
};

constexpr std::uint8_t kSetGameColorGuard[] = {
    0x2d, 0x08, 0x40, 0xf9, 0x89, 0xd0, 0x8b, 0x52,
    0x89, 0x06, 0xa0, 0x72, 0x2b, 0x30, 0x40, 0xa9,
};
constexpr api100_native::Entry kSetGameColor{0x35ca3c, kSetGameColorGuard};
api100_native::Cache g_SetGameColor{};

constexpr std::uint8_t kComputeRoomColorGuard[] = {
    0xef, 0x3b, 0xb9, 0x6d, 0xed, 0x33, 0x01, 0x6d,
    0xf5, 0x2b, 0x00, 0xf9, 0xeb, 0x2b, 0x02, 0x6d,
};
constexpr api100_native::Entry kComputeRoomColor{0x48a5ec, kComputeRoomColorGuard};
api100_native::Cache g_ComputeRoomColor{};

// Room::ComputeColorModifier copies the first six floats of FXParams from
// Room+0x1f30 before applying room-specific changes to the result in x8.
constexpr std::uintptr_t kRoomFxColor = 0x1f30;
constexpr float kDefaultLerpRate = 0.015F;

using SetGameColor = void (*)(void*, const RepentogonColorModifierValue&, bool, float);
using ComputeRoomColor = RepentogonColorModifierValue (*)(const void*);

#if !defined(__SWITCH__)
RepentogonColorModifierNativeTestBindings g_TestBindings{};
#endif

float OptionalNumber(lua_State* state, int index, float fallback) {
    if (lua_isnoneornil(state, index)) {
        return fallback;
    }
    return static_cast<float>(luaL_checknumber(state, index));
}

bool OptionalTrue(lua_State* state, int index) {
    if (lua_isnoneornil(state, index)) return true;
    luaL_checktype(state, index, LUA_TBOOLEAN);
    return lua_toboolean(state, index) != 0;
}

std::uintptr_t CurrentGame(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        luaL_error(state, "Game color modifier requires the game thread");
    }
    // Level starts at the Game address on the pinned image.
    const auto game = ResolveEngineReceiver(state, FieldReceipt::Level, 0);
    if (!game) luaL_error(state, "Game is unavailable");
    return game;
}

void ApplyGameColor(lua_State* state, std::uintptr_t game,
                    const RepentogonColorModifierValue& color, bool lerp, float rate) {
    std::uintptr_t host{};
#if !defined(__SWITCH__)
    if (!g_TestBindings.set) luaL_error(state, "Game color native binding is unavailable");
    host = engine_call::AddressOfFunction(g_TestBindings.set);
#endif
    const auto method = api100_native::Resolve(state, kSetGameColor, g_SetGameColor, host);
    engine_call::AsFunction<SetGameColor>(method)(engine_memory::AsObject(game), color, lerp, rate);
}

RepentogonColorModifierValue ComputeColor(lua_State* state, std::uintptr_t room) {
    std::uintptr_t host{};
#if !defined(__SWITCH__)
    if (!g_TestBindings.compute) luaL_error(state, "Room color native binding is unavailable");
    host = engine_call::AddressOfFunction(g_TestBindings.compute);
#endif
    const auto method = api100_native::Resolve(state, kComputeRoomColor, g_ComputeRoomColor, host);
    return engine_call::AsFunction<ComputeRoomColor>(method)(engine_memory::AsObject(room));
}

int ColorModifierFirstArgument(lua_State* state) {
    if (lua_gettop(state) >= 1 && lua_istable(state, 1)) {
        lua_getglobal(state, "ColorModifier");
        const bool classCall = lua_istable(state, -1) && lua_rawequal(state, 1, -1);
        lua_pop(state, 1);
        if (classCall) {
            return 2;
        }
    }
    return 1;
}

} // namespace

RepentogonColorModifierValue* TryRepentogonColorModifierArgument(
    lua_State* state, int index) noexcept {
    void* value = luaL_testudata(
        state, index, kRepentogonColorModifierMetatable);
    if (value == nullptr ||
        lua_rawlen(state, index) != sizeof(RepentogonColorModifierValue)) {
        return nullptr;
    }
    return static_cast<RepentogonColorModifierValue*>(value);
}

RepentogonColorModifierValue* RequireRepentogonColorModifierArgument(
    lua_State* state, int index) {
    auto* value = TryRepentogonColorModifierArgument(state, index);
    if (value == nullptr) {
        luaL_argerror(state, index, "ColorModifier expected");
    }
    return value;
}

int RepentogonColorModifierIndex(lua_State* state) {
    auto* value = RequireRepentogonColorModifierArgument(state, 1);
    const char* field = luaL_checkstring(state, 2);
    for (const auto& candidate : kFields) {
        if (std::strcmp(candidate.name, field) != 0) {
            continue;
        }
        const auto* number = reinterpret_cast<const float*>(
            reinterpret_cast<const unsigned char*>(value) + candidate.offset);
        lua_pushnumber(state, *number);
        return 1;
    }
    lua_pushnil(state);
    return 1;
}

int RepentogonColorModifierNewIndex(lua_State* state) {
    auto* value = RequireRepentogonColorModifierArgument(state, 1);
    const char* field = luaL_checkstring(state, 2);
    for (const auto& candidate : kFields) {
        if (std::strcmp(candidate.name, field) != 0) {
            continue;
        }
        auto* number = reinterpret_cast<float*>(
            reinterpret_cast<unsigned char*>(value) + candidate.offset);
        *number = static_cast<float>(luaL_checknumber(state, 3));
        return 0;
    }
    return luaL_error(state, "ColorModifier has no writable field named %s", field);
}

int RepentogonGameSetColorModifier(lua_State* state) {
    luaL_checkudata(state, 1, LuaRuntime::kGameMetatable);
    const auto* color = RequireRepentogonColorModifierArgument(state, 2);
    const bool lerp = OptionalTrue(state, 3);
    const auto rate = OptionalNumber(state, 4, kDefaultLerpRate);
    ApplyGameColor(state, CurrentGame(state), *color, lerp, rate);
    return 0;
}

int RepentogonRoomUpdateColorModifier(lua_State* state) {
    luaL_checkudata(state, 1, LuaRuntime::kRoomMetatable);
    const bool process = OptionalTrue(state, 2);
    const bool lerp = OptionalTrue(state, 3);
    const auto rate = OptionalNumber(state, 4, kDefaultLerpRate);
    const auto game = CurrentGame(state);
    const auto room = ResolveEngineReceiver(state, FieldReceipt::Room, 1);
    if (!room) return luaL_error(state, "Room is unavailable");

    RepentogonColorModifierValue color{};
    if (process) {
        color = ComputeColor(state, room);
    } else if (!engine_memory::ReadField(room, kRoomFxColor, &color,
                                         engine_memory::EngineMemoryReadable)) {
        return luaL_error(state, "Room FX color is unavailable");
    }
    ApplyGameColor(state, game, color, lerp, rate);
    return 0;
}

int CreateRepentogonColorModifierHandle(lua_State* state) {
    const int first = ColorModifierFirstArgument(state);
    const int argumentCount = lua_gettop(state) - (first - 1);
    if (argumentCount < 0 || argumentCount > 6) {
        return luaL_error(
            state,
            "ColorModifier accepts R, G, B, A, Brightness and Contrast");
    }
    const float r = OptionalNumber(state, first, 1.0F);
    const float g = OptionalNumber(state, first + 1, 1.0F);
    const float b = OptionalNumber(state, first + 2, 1.0F);
    const float a = OptionalNumber(state, first + 3, 0.0F);
    const float brightness = OptionalNumber(state, first + 4, 0.0F);
    const float contrast = OptionalNumber(state, first + 5, 1.0F);
    auto* value = static_cast<RepentogonColorModifierValue*>(
        lua_newuserdata(state, sizeof(RepentogonColorModifierValue)));
    value->r = r;
    value->g = g;
    value->b = b;
    value->a = a;
    value->brightness = brightness;
    value->contrast = contrast;
    luaL_getmetatable(state, kRepentogonColorModifierMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int RegisterRepentogonColorModifierApi(lua_State* state) {
    if (state == nullptr) {
        return 0;
    }
    const bool created =
        luaL_newmetatable(state, kRepentogonColorModifierMetatable) != 0;
    const int metatable = lua_gettop(state);
    if (created) {
        lua_pushliteral(state, "ColorModifier");
        lua_setfield(state, metatable, "__name");
        lua_pushliteral(state, "ColorModifier");
        lua_setfield(state, metatable, "__type");
        lua_pushcfunction(state, RepentogonColorModifierIndex);
        lua_setfield(state, metatable, "__index");
        lua_pushcfunction(state, RepentogonColorModifierNewIndex);
        lua_setfield(state, metatable, "__newindex");
        lua_pushvalue(state, metatable);
        lua_setfield(state, metatable, "__class");
    }
    lua_pop(state, 1);

    lua_getglobal(state, "ColorModifier");
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);
        lua_newtable(state);
        lua_pushcfunction(state, CreateRepentogonColorModifierHandle);
        lua_setfield(state, -2, "__call");
        luaL_getmetatable(state, kRepentogonColorModifierMetatable);
        lua_setfield(state, -2, "__class");
        lua_setmetatable(state, -2);
        lua_setglobal(state, "ColorModifier");
    } else {
        lua_pop(state, 1);
    }
    return 0;
}

#if !defined(__SWITCH__)
void SetRepentogonColorModifierNativeTestBindings(
    RepentogonColorModifierNativeTestBindings bindings) noexcept {
    g_TestBindings = bindings;
    g_SetGameColor = {};
    g_ComputeRoomColor = {};
}
#endif

} // namespace isaac::runtime
