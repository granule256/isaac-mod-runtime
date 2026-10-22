#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lobject.h"
#include "lstate.h"
#include "ltable.h"
}

namespace isaac::runtime {
namespace {
const unsigned char kRegistryKey{};
Table* s_Map{};
const void* s_Registry{};
lua_State* s_MainState{};

void PushMap(lua_State* state) {
    const auto registry = lua_topointer(state, LUA_REGISTRYINDEX);
    if (registry != s_Registry) ResetEntityLifetimeState();
    lua_rawgetp(state, LUA_REGISTRYINDEX, &kRegistryKey);
    if (lua_isnil(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);
        lua_pushvalue(state, -1);
        lua_rawsetp(state, LUA_REGISTRYINDEX, &kRegistryKey);
    }
    if (!lua_istable(state, -1)) luaL_error(state, "entity lifetime registry is unavailable");
    s_Map = static_cast<Table*>(const_cast<void*>(lua_topointer(state, -1)));
    s_Registry = registry;
    lua_rawgeti(state, LUA_REGISTRYINDEX, LUA_RIDX_MAINTHREAD);
    s_MainState = lua_tothread(state, -1);
    lua_pop(state, 1);
}

// 我方固定Lua5.3.3：已有userdata/table引用的nil删除无需分配或GC写屏障。
Udata* ExistingToken(std::uintptr_t entity, const TValue** slotOut = nullptr) noexcept {
    if (s_Map == nullptr || entity == 0) return nullptr;
    TValue key{};
    setpvalue(&key, engine_memory::AsObject(entity));
    const TValue* slot = luaH_get(s_Map, &key);
    if (ttisnil(slot)) return nullptr;
    if (!ttisfulluserdata(slot)) __builtin_trap();
    Udata* userdata = uvalue(slot);
    if (userdata->len != sizeof(LuaRuntime::EntityLifetimeToken)) __builtin_trap();
    auto* token = static_cast<LuaRuntime::EntityLifetimeToken*>(static_cast<void*>(getudatamem(userdata)));
    if (token->entity != entity) __builtin_trap();
    if (slotOut != nullptr) *slotOut = slot;
    return userdata;
}
void ClearUservalue(Udata* userdata) noexcept {
    TValue nil{};
    setnilvalue(&nil);
    setuservalue(s_MainState, userdata, &nil);
}
}

LuaRuntime::EntityLifetimeToken* PushEntityLifetimeToken(lua_State* state, std::uintptr_t entity) {
    PushMap(state);
    const int map = lua_gettop(state);
    lua_rawgetp(state, map, engine_memory::AsObject(entity));
    if (lua_isnil(state, -1)) {
        lua_pop(state, 1);
        auto* token = static_cast<LuaRuntime::EntityLifetimeToken*>(
            lua_newuserdata(state, sizeof(LuaRuntime::EntityLifetimeToken)));
        *token = {entity, true};
        lua_pushvalue(state, -1);
        lua_rawsetp(state, map, engine_memory::AsObject(entity));
    }
    auto* token = static_cast<LuaRuntime::EntityLifetimeToken*>(lua_touserdata(state, -1));
    if (token == nullptr || lua_rawlen(state, -1) != sizeof(*token) ||
        token->entity != entity || !token->alive)
        luaL_error(state, "entity lifetime token is unavailable");
    lua_remove(state, map);
    return token;
}

bool EntityLifetimeAlive(const LuaRuntime::EntityLifetimeToken* token) noexcept {
    // 兼容宿主直接构造的旧句柄；所有生产PushEntityHandle均附加token。
    return token == nullptr || token->alive;
}

int PushEntityLifetimeData(lua_State* state, std::uintptr_t entity) {
    static_cast<void>(PushEntityLifetimeToken(state, entity));
    const int token = lua_gettop(state);
    lua_getuservalue(state, token);
    if (lua_isnil(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);
        lua_pushvalue(state, -1);
        lua_setuservalue(state, token);
    }
    lua_remove(state, token);
    return 1;
}

void ClearEntityLifetimeData(std::uintptr_t entity) noexcept {
    if (auto* userdata = ExistingToken(entity)) ClearUservalue(userdata);
}
void RetireEntityLifetime(std::uintptr_t entity) noexcept {
    const TValue* slot{};
    if (auto* userdata = ExistingToken(entity, &slot)) {
        auto* token = static_cast<LuaRuntime::EntityLifetimeToken*>(static_cast<void*>(getudatamem(userdata)));
        token->alive = false;
        ClearUservalue(userdata);
        setnilvalue(const_cast<TValue*>(slot));
    }
}
void ResetEntityLifetimeState() noexcept {
    s_Map = nullptr;
    s_Registry = nullptr;
    s_MainState = nullptr;
}
}
