#include "interfaces/lua/repentogon_room_config_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api500_world.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "lua_runtime.hpp"
#include "mod_room_guards.hpp"

#include <array>
#include <cstdint>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

// `_ZN15IsaacRepentance10RoomConfig7GetRoomENS0_6eStageENS_9eRoomTypeEjNS0_5eModeE`
// on build 91C73FDD575061318D68886316AFEAC72388B2AB.
constexpr std::uintptr_t kGetRoomOffset = 0x49340c;
constexpr std::array<std::uint8_t, 16> kGetRoomGuard = {
    0xfd, 0x7b, 0xbc, 0xa9, 0xf7, 0x0b, 0x00, 0xf9,
    0xfd, 0x03, 0x00, 0x91, 0xf6, 0x57, 0x02, 0xa9,
};
constexpr std::uint32_t kStageCount = 37;
api100_native::Cache g_GetRoomCache{};

#if !defined(__SWITCH__)
RepentogonRoomConfigNativeTestBindings g_Host{};
#endif

std::uintptr_t CurrentReceiver(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        luaL_error(state, "RoomConfig native access requires the game thread");
    }

    const auto slot = LuaRuntime::GameOwnerSlot();
    std::uintptr_t ownerSlot{};
    std::uintptr_t game{};
    if (slot == 0 ||
        !engine_memory::ReadAt(slot, &ownerSlot,
                               engine_memory::EngineMemoryReadable) ||
        ownerSlot == 0 ||
        !engine_memory::ReadAt(ownerSlot, &game,
                               engine_memory::EngineMemoryReadable) ||
        game == 0) {
        luaL_error(state, "Game is unavailable");
    }
    if (game > UINTPTR_MAX - mod_rooms::kGameRoomConfigOffset) {
        luaL_error(state, "RoomConfig is unavailable");
    }
    const auto receiver = game + mod_rooms::kGameRoomConfigOffset;
    // The native RoomConfig object starts at Game+0x21b78. Check the prefix
    // before handing its address back to the engine.
    if (!engine_memory::EngineMemoryReadable(receiver, 0x68)) {
        luaL_error(state, "RoomConfig is unavailable");
    }
    return receiver;
}

}  // namespace

int RepentogonRoomConfigGetRoomByStageTypeAndVariant(lua_State* state) {
    const int argumentCount = lua_gettop(state);
    if (argumentCount < 3) {
        return luaL_error(state, "Expected three parameters, got %d",
                          argumentCount);
    }

    const auto receiver = CurrentReceiver(state);
    const auto stage = static_cast<std::int32_t>(luaL_checkinteger(state, 1));
    if (stage < 0 || static_cast<std::uint32_t>(stage) >= kStageCount) {
        return luaL_error(
            state,
            "StageID must be between 0 and 36 (both inclusive), got %d",
            stage);
    }
    const auto type = static_cast<std::int32_t>(luaL_checkinteger(state, 2));
    if (type < 1 || type > 29) {
        return luaL_error(
            state, "Type must be between 1 and 29 (both inclusive), got %d",
            type);
    }
    const auto variant =
        static_cast<std::int32_t>(luaL_checkinteger(state, 3));
    auto mode = static_cast<std::int32_t>(luaL_optinteger(state, 4, -1));
    if (mode < -2 || mode > 1) {
        mode = -1;
    }

    std::uintptr_t host{};
#if !defined(__SWITCH__)
    if (!g_Host.getRoom) {
        return luaL_error(state,
                          "RoomConfig native host binding is unavailable");
    }
    host = engine_call::AddressOfFunction(g_Host.getRoom);
#endif
    using GetRoom = void* (*)(void*, std::uint32_t, std::uint32_t,
                              std::uint32_t, std::int32_t);
    const auto getRoom = engine_call::AsFunction<GetRoom>(
        api100_native::Resolve(state, {kGetRoomOffset, kGetRoomGuard.data()},
                               g_GetRoomCache, host));
    auto* room = getRoom(engine_memory::AsObject(receiver),
                         static_cast<std::uint32_t>(stage),
                         static_cast<std::uint32_t>(type),
                         static_cast<std::uint32_t>(variant), mode);
    if (!room) {
        lua_pushnil(state);
        return 1;
    }
    PushApi500RoomConfig(state, engine_memory::AddressOf(room), 0);
    return 1;
}

int RegisterRepentogonRoomConfigApi(lua_State* state) {
    if (!state) {
        return 0;
    }
    lua_getglobal(state, "RoomConfig");
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);
    }
    static_cast<void>(AttachOwnerMethods(state, "RoomConfig", nullptr, 0));
    lua_setglobal(state, "RoomConfig");
    return 0;
}

#if !defined(__SWITCH__)
void SetRepentogonRoomConfigNativeTestBindings(
    RepentogonRoomConfigNativeTestBindings bindings) noexcept {
    g_Host = bindings;
}
#endif

}  // namespace isaac::runtime
