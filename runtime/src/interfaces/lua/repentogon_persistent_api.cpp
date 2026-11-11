#include "interfaces/lua/repentogon_persistent_api.hpp"

#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"

#include <cstdint>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {
constexpr std::uint32_t kPersistentGameDataCounterOffset = 0x2a8;
constexpr std::uint32_t kPersistentGameDataCollectionOffset = 0xa68;
constexpr std::uint32_t kEventCounterMax = 522;
constexpr std::uint32_t kCollectibleMax = 732;

std::uintptr_t PersistentObject(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread())
        luaL_error(state, "PersistentGameData access requires the game thread");
    const auto object = PersistentGameDataObjectArgument(state, 1);
    if (object == 0) luaL_error(state, "PersistentGameData is no longer available");
    return object;
}
}

int RepentogonPersistentGameDataGetEventCounter(lua_State* state) {
    const auto object = PersistentObject(state);
    lua_Integer requested = 0;
    if (lua_gettop(state) != 2 || !IntegerArgumentAt(state, 2, &requested) ||
        requested < 0 || static_cast<std::uint64_t>(requested) > kEventCounterMax)
        return luaL_argerror(state, 2, "EventCounter must be between 0 and 522");
    std::int32_t value = 0;
    if (!engine_memory::ReadField(
            object,
            kPersistentGameDataCounterOffset + static_cast<std::uintptr_t>(requested) * 4,
            &value, engine_memory::EngineMemoryReadable))
        return luaL_error(state, "PersistentGameData event counter is not readable");
    lua_pushinteger(state, value);
    return 1;
}

int RepentogonPersistentGameDataIsItemInCollection(lua_State* state) {
    const auto object = PersistentObject(state);
    lua_Integer requested = 0;
    if (lua_gettop(state) != 2 || !IntegerArgumentAt(state, 2, &requested) ||
        requested < 0 || static_cast<std::uint64_t>(requested) > kCollectibleMax)
        return luaL_argerror(state, 2, "CollectibleType must be between 0 and 732");
    std::uint8_t present = 0;
    if (!engine_memory::ReadField(
            object,
            kPersistentGameDataCollectionOffset + static_cast<std::uintptr_t>(requested),
            &present, engine_memory::EngineMemoryReadable))
        return luaL_error(state, "PersistentGameData collection is not readable");
    lua_pushboolean(state, requested != 0 && present != 0);
    return 1;
}
}
