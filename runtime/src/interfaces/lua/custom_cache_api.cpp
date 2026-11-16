#include "interfaces/lua/custom_cache_api.hpp"

#include "application/custom_cache/custom_cache_runtime.hpp"
#include "lua_object_handles.hpp"

#include <string_view>
#include <vector>

extern "C" {
#include <lauxlib.h>
#include <lua.h>
}

namespace isaac::runtime {
namespace {

std::uintptr_t Player(lua_State* state) {
    auto* handle = static_cast<LuaRuntime::EntityHandle*>(
        luaL_checkudata(state, 1, LuaRuntime::kEntityPlayerMetatable));
    if (handle == nullptr || handle->entity == nullptr ||
        (handle->lifetime != nullptr && !handle->lifetime->alive)) {
        luaL_error(state, "EntityPlayer receiver is no longer available");
    }
    return reinterpret_cast<std::uintptr_t>(handle->entity);
}

void Attach(lua_State* state, const char* name, lua_CFunction function) {
    lua_pushcfunction(state, function);
    lua_setfield(state, -2, name);
}

int GetMaximum(lua_State* state, std::string_view tag) {
    const auto player = Player(state);
    lua_pushinteger(state, custom_cache::GetConsumableMaximumForPlayer(player, tag));
    return 1;
}

void AttachMethods(lua_State* state) {
    Attach(state, "AddCustomCacheTag", &CustomCacheAddTag);
    Attach(state, "GetCustomCacheValue", &CustomCacheGetValue);
    Attach(state, "GetMaxCoins", [](lua_State* lua) { return GetMaximum(lua, "maxcoins"); });
    Attach(state, "GetMaxKeys", [](lua_State* lua) { return GetMaximum(lua, "maxkeys"); });
    Attach(state, "GetMaxBombs", [](lua_State* lua) { return GetMaximum(lua, "maxbombs"); });
}

}  // namespace

int CustomCacheAddTag(lua_State* state) {
    const auto player = Player(state);
    if (!lua_isnoneornil(state, 3)) luaL_checktype(state, 3, LUA_TBOOLEAN);
    const auto immediate = lua_toboolean(state, 3) != 0;
    if (lua_istable(state, 2)) {
        const auto top = lua_gettop(state);
        const auto rawLength = lua_rawlen(state, 2);
        // Keep checked strings rooted on the Lua stack until the store copies
        // them. Type errors therefore occur before constructing native storage.
        for (std::size_t index = 1; index <= rawLength; ++index) {
            luaL_checkstack(state, 1, "custom cache tags");
            lua_geti(state, 2, static_cast<lua_Integer>(index));
            if (lua_isnil(state, -1)) {
                lua_pop(state, 1);
                break;
            }
            static_cast<void>(luaL_checkstring(state, -1));
        }
        std::vector<std::string_view> tags;
        tags.reserve(lua_gettop(state) - top);
        for (int index = top + 1; index <= lua_gettop(state); ++index) {
            tags.emplace_back(lua_tostring(state, index));
        }
        custom_cache::AddCustomCacheTagForPlayer(player, tags, immediate);
        lua_settop(state, top);
    } else {
        const std::string_view tag(luaL_checkstring(state, 2));
        custom_cache::AddCustomCacheTagForPlayer(player, std::span{&tag, 1}, immediate);
    }
    return 0;
}

int CustomCacheGetValue(lua_State* state) {
    const auto player = Player(state);
    const auto* tag = luaL_checkstring(state, 2);
    lua_pushnumber(
        state, custom_cache::GetCustomCacheValueForPlayer(player, tag));
    return 1;
}

int RegisterCustomCacheApi(lua_State* state) {
    luaL_getmetatable(state, LuaRuntime::kEntityPlayerMetatable);
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        return luaL_error(state, "EntityPlayer metatable is unavailable");
    }
    const int metatable = lua_gettop(state);
    lua_getfield(state, metatable, "__methods");
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);
        lua_pushvalue(state, -1);
        lua_setfield(state, metatable, "__methods");
    }
    AttachMethods(state);
    lua_pop(state, 1);

    lua_getfield(state, metatable, "__class");
    if (lua_istable(state, -1)) {
        AttachMethods(state);
    }
    lua_pop(state, 2);
    return 0;
}

}  // namespace isaac::runtime
