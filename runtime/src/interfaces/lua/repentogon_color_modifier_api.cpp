#include "interfaces/lua/repentogon_color_modifier_api.hpp"

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

float OptionalNumber(lua_State* state, int index, float fallback) {
    if (lua_isnoneornil(state, index)) {
        return fallback;
    }
    return static_cast<float>(luaL_checknumber(state, index));
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

} // namespace isaac::runtime
