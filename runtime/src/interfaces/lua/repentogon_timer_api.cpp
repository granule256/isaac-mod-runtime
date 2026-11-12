#include "interfaces/lua/repentogon_timer_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstdint>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

constexpr char kTimerRegistryKey[] = "IsaacRuntime.TimerFunctions";
#if defined(__SWITCH__)
constexpr std::uintptr_t kCreateTimerOffset = 0xa58fc;
constexpr std::array<std::uint8_t, 16> kCreateTimerGuard = {
    0xff, 0x43, 0x01, 0xd1, 0xfd, 0x7b, 0x01, 0xa9,
    0xfd, 0x43, 0x00, 0x91, 0xf7, 0x13, 0x00, 0xf9,
};
#endif

lua_State* g_TimerState{};
#if !defined(__SWITCH__)
RepentogonTimerNativeTestBindings g_TestBindings{};
#endif

int TimerRegistry(lua_State* state) {
    lua_getfield(state, LUA_REGISTRYINDEX, kTimerRegistryKey);
    if (lua_istable(state, -1)) return 1;
    lua_pop(state, 1);
    lua_newtable(state);
    lua_pushvalue(state, -1);
    lua_setfield(state, LUA_REGISTRYINDEX, kTimerRegistryKey);
    return 1;
}

void TimerCallback(void* effect) noexcept {
    auto* state = g_TimerState;
    if (!state || !effect || !LuaRuntime::IsOnGameThread()) return;
    const int top = lua_gettop(state);
    if (!lua_checkstack(state, 5)) {
        LuaRuntime::ReportCallbackError(nullptr);
        return;
    }
    TimerRegistry(state);
    lua_pushlightuserdata(state, effect);
    lua_rawget(state, -2);
    if (!lua_isfunction(state, -1)) {
        lua_settop(state, top);
        return;
    }
    PushEntityCallbackArgument(state, engine_memory::AddressOf(effect));
    if (lua_pcall(state, 1, 0, 0) != LUA_OK) {
        LuaRuntime::ReportCallbackError(state);
        lua_pop(state, 1);
    }
    lua_settop(state, top);
}

void* CreateTimer(void (*callback)(void*), std::uint32_t delay,
                  std::int32_t times, bool persistent, lua_State* state) {
#if defined(__SWITCH__)
    const auto base = LuaRuntime::EngineModuleBase();
    if (!base || base > UINTPTR_MAX - kCreateTimerOffset ||
        !engine_call::VerifyEntryBytes(
            base + kCreateTimerOffset, kCreateTimerGuard.data(),
            kCreateTimerGuard.size(), engine_memory::EngineMemoryReadable)) {
        luaL_error(state, "Isaac.CreateTimer native binding is unavailable");
    }
    using Fn = void* (*)(void (*)(void*), std::uint32_t, std::int32_t, bool);
    return engine_call::AsFunction<Fn>(base + kCreateTimerOffset)(
        callback, delay, times, persistent);
#else
    if (!g_TestBindings.createTimer) {
        luaL_error(state, "Isaac.CreateTimer host binding is unavailable");
    }
    return g_TestBindings.createTimer(callback, delay, times, persistent);
#endif
}

}  // namespace

int RegisterRepentogonTimerApi(lua_State* state) {
    g_TimerState = state;
    lua_newtable(state);
    lua_setfield(state, LUA_REGISTRYINDEX, kTimerRegistryKey);
    lua_getglobal(state, "Isaac");
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);
    }
    static_cast<void>(AttachOwnerMethods(state, "Isaac", nullptr, 0));
    lua_setglobal(state, "Isaac");
    return 0;
}

void ResetRepentogonTimerApi() noexcept {
    g_TimerState = nullptr;
}

int RepentogonIsaacCreateTimer(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        return luaL_error(state, "Isaac.CreateTimer requires the game thread");
    }
    if (!lua_isfunction(state, 1)) {
        return luaL_argerror(state, 1, "expected a function");
    }
    auto delay = static_cast<std::int64_t>(luaL_checkinteger(state, 2));
    if (delay <= 0) delay = 1;
    if (delay > UINT32_MAX) {
        return luaL_argerror(state, 2, "delay is outside uint32 range");
    }
    auto times = static_cast<std::int64_t>(luaL_optinteger(state, 3, 0));
    if (times < 0) times = 1;
    if (times > INT32_MAX) {
        return luaL_argerror(state, 3, "times is outside int32 range");
    }
    const bool persistent = lua_gettop(state) < 4 || lua_isnil(state, 4) ||
                            lua_toboolean(state, 4) != 0;
    auto* effect = CreateTimer(&TimerCallback, static_cast<std::uint32_t>(delay),
                               static_cast<std::int32_t>(times), persistent, state);
    if (!effect) {
        lua_pushnil(state);
        return 1;
    }
    TimerRegistry(state);
    lua_pushlightuserdata(state, effect);
    lua_pushvalue(state, 1);
    lua_rawset(state, -3);
    lua_pop(state, 1);
    PushEntityCallbackArgument(state, engine_memory::AddressOf(effect));
    return 1;
}

#if !defined(__SWITCH__)
void SetRepentogonTimerNativeTestBindings(
    RepentogonTimerNativeTestBindings bindings) noexcept {
    g_TestBindings = bindings;
}
#endif

}
