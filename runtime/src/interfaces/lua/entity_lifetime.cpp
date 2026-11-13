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
std::size_t s_RerollOverrideCount{};
std::uint32_t s_RerollEpoch{1};

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
    if (s_MainState == nullptr) {
        lua_rawgeti(state, LUA_REGISTRYINDEX, LUA_RIDX_MAINTHREAD);
        s_MainState = lua_tothread(state, -1);
        lua_pop(state, 1);
    }
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
void ClearRerollOverride(Udata* userdata) noexcept {
    auto* token = static_cast<LuaRuntime::EntityLifetimeToken*>(
        static_cast<void*>(getudatamem(userdata)));
    if (token->pickupRerollOverride) {
        if (token->pickupRerollEpoch==s_RerollEpoch) --s_RerollOverrideCount;
        token->pickupRerollOverride = 0;
    }
}
}

LuaRuntime::EntityLifetimeToken* PushEntityLifetimeToken(lua_State* state, std::uintptr_t entity) {
    PushMap(state);
    // 固定 Lua 5.3.3：复用表中已存在的 token，直接替换栈顶的 map 根。
    // 不分配、不触发 GC；仍以本次取得的 registry map 为准。
    TValue key{};
    setpvalue(&key, engine_memory::AsObject(entity));
    const TValue* slot = luaH_get(s_Map, &key);
    if (ttisfulluserdata(slot)) {
        Udata* userdata = uvalue(slot);
        if (userdata->len == sizeof(LuaRuntime::EntityLifetimeToken)) {
            auto* token = static_cast<LuaRuntime::EntityLifetimeToken*>(
                static_cast<void*>(getudatamem(userdata)));
            if (token->entity == entity && token->alive) {
                setuvalue(state, state->top - 1, userdata);
                return token;
            }
        }
    }
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
void ReinitializeEntityLifetime(std::uintptr_t entity) noexcept {
    if (auto* userdata = ExistingToken(entity)) {
        ClearUservalue(userdata);
        ClearRerollOverride(userdata);
    }
}
void RetireEntityLifetime(std::uintptr_t entity) noexcept {
    const TValue* slot{};
    if (auto* userdata = ExistingToken(entity, &slot)) {
        auto* token = static_cast<LuaRuntime::EntityLifetimeToken*>(static_cast<void*>(getudatamem(userdata)));
        token->alive = false;
        ClearRerollOverride(userdata);
        ClearUservalue(userdata);
        setnilvalue(const_cast<TValue*>(slot));
    }
}
void ResetEntityLifetimeState() noexcept {
    s_Map = nullptr;
    s_Registry = nullptr;
    s_MainState = nullptr;
    s_RerollOverrideCount = 0;
    // A lua_close finalizer can reattach the same registry after this reset.
    // Invalidate extension bytes without walking a possibly closed Lua heap.
    if (++s_RerollEpoch==0) ++s_RerollEpoch;
}

void SetPickupRerollOverride(lua_State* state, std::uintptr_t entity, std::int8_t value) {
    auto* token = PushEntityLifetimeToken(state, entity);
    if (token->pickupRerollEpoch!=s_RerollEpoch) {
        token->pickupRerollOverride=0;
        token->pickupRerollEpoch=s_RerollEpoch;
    }
    if (!token->pickupRerollOverride && value) ++s_RerollOverrideCount;
    else if (token->pickupRerollOverride && !value) --s_RerollOverrideCount;
    token->pickupRerollOverride = value;
    lua_pop(state, 1);
}

bool TryPickupRerollOverride(std::uintptr_t entity, bool* result) noexcept {
    if (!s_RerollOverrideCount || !result) return false;
    auto* userdata = ExistingToken(entity);
    if (!userdata) return false;
    const auto* token = static_cast<const LuaRuntime::EntityLifetimeToken*>(
        static_cast<const void*>(getudatamem(userdata)));
    if (!token->alive || token->pickupRerollEpoch!=s_RerollEpoch ||
        !token->pickupRerollOverride) return false;
    *result = token->pickupRerollOverride == 2;
    return true;
}
}
