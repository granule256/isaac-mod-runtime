#include "interfaces/lua/object_identity_registry.hpp"
#include <cstring>
extern "C" {
#include <lua.h>
}

namespace isaac::runtime {
namespace {
// 取本模块独有对象的地址作为raw键；不借用字符串或函数指针地址。
char kResolverKey;

bool StackIndex(int index, int top) noexcept {
    return index != 0 && index <= top && index >= -top;
}

NativeObjectIdentityResolver ResolverAt(lua_State* state, int index) noexcept {
    if (lua_type(state, index) != LUA_TUSERDATA ||
        lua_rawlen(state, index) != sizeof(NativeObjectIdentityResolver)) {
        return nullptr;
    }
    NativeObjectIdentityResolver resolver{};
    std::memcpy(&resolver, lua_touserdata(state, index), sizeof(resolver));
    return resolver;
}
} // namespace

bool RegisterNativeObjectIdentity(lua_State* state, int metatableIndex,
                                  NativeObjectIdentityResolver resolver) noexcept {
    if (state == nullptr || resolver == nullptr) {
        return false;
    }
    const int top = lua_gettop(state);
    if (!StackIndex(metatableIndex, top) || !lua_istable(state, metatableIndex)) {
        return false;
    }
    const int metatable = lua_absindex(state, metatableIndex);
    lua_rawgetp(state, metatable, &kResolverKey);
    if (!lua_isnil(state, -1)) {
        const bool same = ResolverAt(state, -1) == resolver;
        lua_settop(state, top);
        return same;
    }
    lua_pop(state, 1);
    void* storage = lua_newuserdata(state, sizeof(resolver));
    std::memcpy(storage, &resolver, sizeof(resolver));
    lua_rawsetp(state, metatable, &kResolverKey);
    return true;
}

std::uintptr_t ResolveRegisteredObjectIdentity(lua_State* state, int objectIndex,
                                              bool* recognized) noexcept {
    if (recognized != nullptr) {
        *recognized = false;
    }
    if (state == nullptr) {
        return 0;
    }
    const int top = lua_gettop(state);
    if (!StackIndex(objectIndex, top) || lua_type(state, objectIndex) != LUA_TUSERDATA) {
        return 0;
    }
    const int object = lua_absindex(state, objectIndex);
    if (!lua_getmetatable(state, object)) {
        return 0;
    }
    lua_rawgetp(state, -1, &kResolverKey);
    const auto resolver = ResolverAt(state, -1);
    lua_settop(state, top);
    if (resolver == nullptr) {
        return 0;
    }
    if (recognized != nullptr) {
        *recognized = true;
    }
    const auto identity = resolver(state, object);
    lua_settop(state, top);
    return identity;
}
} // namespace isaac::runtime
