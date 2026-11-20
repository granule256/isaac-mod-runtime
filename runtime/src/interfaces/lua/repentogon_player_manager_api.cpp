#include "interfaces/lua/repentogon_player_manager_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "lua_object_handles.hpp"
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
constexpr std::uintptr_t kBackupPlayerOffset=0x2588;
constexpr std::uint64_t kLazSharedTag=0x80000000ULL;

#if !defined(__SWITCH__)
RepentogonPlayerManagerTrinketHost g_TrinketHost{};
RepentogonPlayerManagerTrinketMultiplierHost g_TrinketMultiplierHost{};
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
    if (!ignoreModifiers) {
#if defined(__SWITCH__)
        const auto base=LuaRuntime::EngineModuleBase();
        if (!base || base>UINTPTR_MAX-kEntityPlayerGetTrinketMultiplierOffset ||
            !engine_memory::EngineMemoryReadable(
                base+kEntityPlayerGetTrinketMultiplierOffset,
                kEntityPlayerGetTrinketMultiplierExpectedBytes.size()) ||
            std::memcmp(engine_memory::AsObject(
                            base+kEntityPlayerGetTrinketMultiplierOffset),
                        kEntityPlayerGetTrinketMultiplierExpectedBytes.data(),
                        kEntityPlayerGetTrinketMultiplierExpectedBytes.size())!=0)
            luaL_error(state,"PlayerManager trinket multiplier binding is unavailable");
        using Fn=std::int32_t (*)(void*,std::uint32_t);
        return engine_call::AsFunction<Fn>(
                   base+kEntityPlayerGetTrinketMultiplierOffset)(
                   engine_memory::AsObject(player),id)>0;
#else
        if (!g_TrinketMultiplierHost)
            luaL_error(state,"PlayerManager trinket multiplier host binding is unavailable");
        return g_TrinketMultiplierHost(engine_memory::AsObject(player),id)>0;
#endif
    }
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

bool IsOrdinaryPlayer(std::uintptr_t player) {
    std::uint32_t variant=UINT32_MAX;
    return player && engine_memory::ReadField(player,kEntityVariantOffset,&variant,
        engine_memory::EngineMemoryReadable) && variant==0;
}

bool PlayerHasQuery(lua_State* state,std::uintptr_t player,std::uint32_t id,
                    bool trinket,bool ignore) {
    if (!IsOrdinaryPlayer(player)) return false;
    return trinket?HasTrinket(state,player,id,ignore)
                  :EntityPlayerHasCollectibleForApi(player,id,ignore);
}

bool ItemHasLazSharedTag(bool trinket,std::uint32_t id) {
    return (ItemConfigItemTagsForApi(trinket,id)&kLazSharedTag)!=0;
}

std::uintptr_t MatchingBackup(lua_State* state,std::uintptr_t player,bool trinket,
                              std::uint32_t id,bool ignore) {
    std::uintptr_t backup{};
    if (!player || !engine_memory::ReadField(player,kBackupPlayerOffset,&backup,
            engine_memory::EngineMemoryReadable) || !backup) return 0;
    return PlayerHasQuery(state,backup,id,trinket,ignore)?backup:0;
}

int FirstOwner(lua_State* state,bool trinket) {
    const auto id=ItemId(state);
    int option=2;
    // The older trinket signature accepted an unused RNG before the flag.
    if (trinket && (lua_isnil(state,2) ||
                    luaL_testudata(state,2,LuaRuntime::kRngMetatable))) option=3;
    if (!lua_isnoneornil(state,option) && !lua_isboolean(state,option))
        return luaL_argerror(state,option,"lazSharedGlobalTag must be boolean");
    const bool useBackup=lua_isnoneornil(state,option)||lua_toboolean(state,option);
    const auto players=ResolveEnginePlayerArray();
    if (!players.readable) return luaL_error(state,"PlayerManager player list is unavailable");
    bool checkedTag=false,shared=false;
    for (std::size_t i=0;i<players.count;++i) {
        const auto player=ResolveEnginePlayerAt(i);
        auto owner=player;
        if (!PlayerHasQuery(state,player,id,trinket,false)) {
            if (!checkedTag) {
                shared=useBackup&&ItemHasLazSharedTag(trinket,id);
                checkedTag=true;
            }
            owner=shared?MatchingBackup(state,player,trinket,id,false):0;
        }
        if (owner) {
            PushEntityCallbackArgument(state,owner);
            return 1;
        }
    }
    lua_pushnil(state);
    return 1;
}
}

int RepentogonPlayerManagerFirstCollectibleOwner(lua_State* state) {
    return FirstOwner(state,false);
}

int RepentogonPlayerManagerFirstTrinketOwner(lua_State* state) {
    return FirstOwner(state,true);
}

int RepentogonPlayerManagerGetNumCollectibles(lua_State* state) {
    const auto id = ItemId(state);
    if (!lua_isnoneornil(state, 2) && !lua_isboolean(state, 2))
        return luaL_argerror(state, 2, "ignoreModifiers must be boolean");
    const bool ignore = lua_toboolean(state, 2);
    const auto players = ResolveEnginePlayerArray();
    if (!players.readable) return luaL_error(state, "PlayerManager player list is unavailable");
    const bool shared = players.count != 0 && ItemHasLazSharedTag(false, id);
    std::int64_t count = 0;
    for (std::size_t i = 0; i < players.count; ++i) {
        const auto player = ResolveEnginePlayerAt(i);
        if (!player) break;
        count += EntityPlayerCollectibleCountForApi(player, id, ignore);
        std::uintptr_t backup = 0;
        if (shared && engine_memory::ReadField(player, kBackupPlayerOffset, &backup,
                engine_memory::EngineMemoryReadable) && IsEnginePlayerPointer(backup)) {
            count += EntityPlayerCollectibleCountForApi(backup, id, ignore);
        }
    }
    lua_pushinteger(state, count);
    return 1;
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
        if (PlayerHasQuery(state,player,id,false,ignore) ||
            (ItemHasLazSharedTag(false,id) &&
             MatchingBackup(state,player,false,id,ignore))) {
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
        if (PlayerHasQuery(state,player,id,true,ignore) ||
            (ItemHasLazSharedTag(true,id) &&
             MatchingBackup(state,player,true,id,ignore))) {
            lua_pushboolean(state,1);
            return 1;
        }
    }
    lua_pushboolean(state,0);
    return 1;
}

int RepentogonPlayerManagerGetPlayers(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread())
        return luaL_error(state,"PlayerManager queries require the game thread");
    const auto players=ResolveEnginePlayerArray();
    if (!players.readable)
        return luaL_error(state,"PlayerManager player list is unavailable");
    lua_createtable(state,static_cast<int>(players.count),0);
    for (std::size_t i=0;i<players.count;++i) {
        PushEntityCallbackArgument(state,ResolveEnginePlayerAt(i));
        lua_rawseti(state,-2,static_cast<lua_Integer>(i+1));
    }
    return 1;
}

int RepentogonPlayerManagerAnyoneIsPlayerType(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread())
        return luaL_error(state,"PlayerManager queries require the game thread");
    const auto wanted=static_cast<std::uint32_t>(luaL_checkinteger(state,1));
    const auto players=ResolveEnginePlayerArray();
    if (!players.readable) return luaL_error(state,"PlayerManager player list is unavailable");
    for (std::size_t i=0;i<players.count;++i) {
        const auto player=ResolveEnginePlayerAt(i);
        std::uint32_t type{};
        if (IsOrdinaryPlayer(player)&&engine_memory::ReadField(player,kEntityPlayerTypeOffset,&type,
                engine_memory::EngineMemoryReadable)&&type==wanted) {
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
void SetRepentogonPlayerManagerTrinketMultiplierHost(
    RepentogonPlayerManagerTrinketMultiplierHost function) noexcept {
    g_TrinketMultiplierHost=function;
}
#endif
}
