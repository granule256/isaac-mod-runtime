#include "interfaces/lua/repentogon_player_manager_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstdint>
#include <cstring>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {
#if defined(__SWITCH__)
constexpr std::array<std::uint8_t,16> kHasTrinketGuard={
    0xfd,0x7b,0xbe,0xa9,0xf4,0x4f,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf3,0x03,0x01,0x2a};
#endif

#if !defined(__SWITCH__)
RepentogonPlayerManagerTrinketHost g_TrinketHost{};
#endif

std::uint32_t ItemId(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread())
        luaL_error(state, "PlayerManager queries require the game thread");
    lua_Integer value=0;
    if (!IntegerArgumentAt(state,1,&value) || value<0 ||
        static_cast<std::uint64_t>(value)>UINT32_MAX)
        luaL_argerror(state,1,"item id must be inside uint32 range");
    return static_cast<std::uint32_t>(value);
}

bool HasTrinket(lua_State* state,std::uintptr_t player,std::uint32_t id,bool ignoreModifiers) {
#if defined(__SWITCH__)
    const auto base=LuaRuntime::EngineModuleBase();
    if (!base || base>UINTPTR_MAX-kEntityPlayerHasTrinketOffset ||
        !engine_memory::EngineMemoryReadable(base+kEntityPlayerHasTrinketOffset,kHasTrinketGuard.size()) ||
        std::memcmp(engine_memory::AsObject(base+kEntityPlayerHasTrinketOffset),
                    kHasTrinketGuard.data(),kHasTrinketGuard.size())!=0)
        luaL_error(state,"PlayerManager trinket native binding is unavailable");
    using Fn=bool (*)(void*,std::uint32_t,bool);
    return engine_call::AsFunction<Fn>(base+kEntityPlayerHasTrinketOffset)(
        engine_memory::AsObject(player),id,ignoreModifiers);
#else
    if (!g_TrinketHost)
        luaL_error(state,"PlayerManager trinket host binding is unavailable");
    return g_TrinketHost(engine_memory::AsObject(player),id,ignoreModifiers);
#endif
}
}

int RepentogonPlayerManagerAnyoneHasCollectible(lua_State* state) {
    const auto id=ItemId(state);
    if (lua_gettop(state)>=2 && !lua_isboolean(state,2))
        return luaL_argerror(state,2,"ignoreModifiers must be boolean");
    const bool ignore=lua_toboolean(state,2)!=0;
    const auto players=ResolveEnginePlayerArray();
    if (!players.readable) return luaL_error(state,"PlayerManager player list is unavailable");
    for (std::size_t i=0;i<players.count;++i) {
        const auto player=ResolveEnginePlayerAt(i);
        std::uint32_t variant=UINT32_MAX;
        if (!player || !engine_memory::ReadField(player,kEntityVariantOffset,&variant,
                engine_memory::EngineMemoryReadable)) continue;
        if (variant==0 && EntityPlayerHasCollectibleForApi(player,id,ignore)) {
            lua_pushboolean(state,1);
            return 1;
        }
    }
    lua_pushboolean(state,0);
    return 1;
}

int RepentogonPlayerManagerAnyoneHasTrinket(lua_State* state) {
    const auto id=ItemId(state);
    if (lua_gettop(state)>=2 && !lua_isboolean(state,2))
        return luaL_argerror(state,2,"ignoreModifiers must be boolean");
    const bool ignore=lua_toboolean(state,2)!=0;
    const auto players=ResolveEnginePlayerArray();
    if (!players.readable) return luaL_error(state,"PlayerManager player list is unavailable");
    for (std::size_t i=0;i<players.count;++i) {
        const auto player=ResolveEnginePlayerAt(i);
        std::uint32_t variant=UINT32_MAX;
        if (!player || !engine_memory::ReadField(player,kEntityVariantOffset,&variant,
                engine_memory::EngineMemoryReadable)) continue;
        if (variant==0 && HasTrinket(state,player,id,ignore)) {
            lua_pushboolean(state,1);
            return 1;
        }
    }
    lua_pushboolean(state,0);
    return 1;
}

int RegisterPlayerManagerApi(lua_State* state) {
    lua_newtable(state);
    static_cast<void>(AttachOwnerMethods(state,"PlayerManager",nullptr,0));
    lua_setglobal(state,"PlayerManager");
    return 0;
}

#if !defined(__SWITCH__)
void SetRepentogonPlayerManagerTrinketHost(
    RepentogonPlayerManagerTrinketHost function) noexcept {g_TrinketHost=function;}
#endif
}
