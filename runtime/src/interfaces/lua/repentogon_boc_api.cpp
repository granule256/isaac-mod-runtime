#include "interfaces/lua/repentogon_boc_api.hpp"

#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
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

constexpr std::uintptr_t kBagContentOffset = 0x2690;
constexpr std::uintptr_t kBagOutputOffset = 0x2698;
constexpr std::uintptr_t kActiveDescItem = 0x00;
constexpr std::uintptr_t kActiveDescCharge = 0x04;
constexpr std::uintptr_t kActiveDescSubCharge = 0x0c;
constexpr std::uintptr_t kActiveDescBatteryCharge = 0x08;
constexpr std::uintptr_t kActiveDescTimedCooldown = 0x10;
constexpr std::uintptr_t kActiveDescPartialCharge = 0x14;
constexpr std::uintptr_t kActiveDescVarData = 0x18;
#if defined(__SWITCH__)
constexpr std::array<std::uint8_t, 16> kCalculateGuard = {
    0xff, 0x03, 0x04, 0xd1, 0xe9, 0x23, 0x09, 0x6d,
    0xfd, 0x7b, 0x0a, 0xa9, 0xfd, 0x83, 0x02, 0x91,
};
constexpr std::uintptr_t kCalculateOffset = 0x2ff7c0;
#endif
constexpr char kActiveItemDescMetatable[] = "IsaacRuntime.ActiveItemDesc";

struct ActiveItemDescHandle {
    void* player;
    LuaRuntime::EntityLifetimeToken* lifetime;
    std::uintptr_t moduleBase;
    std::uint32_t slot;
    std::uint32_t reserved;
};

#if !defined(__SWITCH__)
RepentogonBocNativeTestBindings g_TestBindings{};
#endif

std::uintptr_t Player(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        luaL_error(state,
                   "REPENTOGON bag-of-crafting access requires the game thread");
    }
    const auto player = ResolveEngineReceiver(state, FieldReceipt::EntityPlayer, 1);
    const auto base = LuaRuntime::EngineModuleBase();
    std::uintptr_t vtable{};
    std::uint32_t type{};
    if (!player || !base || base > UINTPTR_MAX - kEntityPlayerVtableOffset ||
        !engine_memory::ReadField(player, 0, &vtable,
                                  engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadField(player, kEntityTypeOffset, &type,
                                  engine_memory::EngineMemoryReadable) ||
        vtable != base + kEntityPlayerVtableOffset ||
        type != kEntityTypePlayer) {
        luaL_error(state, "EntityPlayer reference is no longer available");
    }
    return player;
}

void NoArgs(lua_State* state, const char* name) {
    if (lua_gettop(state) != 1) {
        luaL_error(state, "%s accepts no arguments", name);
    }
}

template <class T>
T Read(lua_State* state, std::uintptr_t object, std::uintptr_t offset,
       const char* name) {
    T value{};
    if (!engine_memory::ReadField(object, offset, &value,
                                  engine_memory::EngineMemoryReadable)) {
        luaL_error(state, "%s is not readable", name);
    }
    return value;
}

template <class T>
void Write(lua_State* state, std::uintptr_t object, std::uintptr_t offset,
           T value, const char* name) {
    if (!engine_memory::WriteField(object, offset, value,
                                   engine_memory::EngineMemoryWritable)) {
        luaL_error(state, "%s is not writable", name);
    }
}

std::uintptr_t ActiveSlot(lua_State* state) {
    const auto slot = luaL_optinteger(state, 2, 0);
    if (slot < 0 || slot >= 4) {
        luaL_argerror(state, 2, "invalid active slot");
    }
    return static_cast<std::uintptr_t>(slot);
}

ActiveItemDescHandle* ActiveDesc(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread())
        luaL_error(state,"ActiveItemDesc access requires the game thread");
    auto* handle=static_cast<ActiveItemDescHandle*>(
        luaL_checkudata(state,1,kActiveItemDescMetatable));
    if (lua_rawlen(state,1)!=sizeof(*handle))
        luaL_error(state,"invalid ActiveItemDesc reference");
    const auto base=LuaRuntime::EngineModuleBase();
    std::uintptr_t vtable{};
    std::uint32_t type{};
    if (!handle->player || handle->slot>=4 || handle->moduleBase!=base ||
        !EntityLifetimeAlive(handle->lifetime) ||
        !engine_memory::ReadField(engine_memory::AddressOf(handle->player),0,&vtable,
                                  engine_memory::EngineMemoryReadable) ||
        vtable!=base+kEntityPlayerVtableOffset ||
        !engine_memory::ReadField(engine_memory::AddressOf(handle->player),
                                  kEntityTypeOffset,&type,engine_memory::EngineMemoryReadable) ||
        type!=kEntityTypePlayer)
        luaL_error(state,"ActiveItemDesc owner is no longer available");
    return handle;
}

int ActiveDescIndex(lua_State* state) {
    auto* handle = ActiveDesc(state);
    const auto base = engine_memory::AddressOf(handle->player) +
                      kEntityPlayerActiveItemOffset +
                      static_cast<std::uintptr_t>(handle->slot) *
                          kEntityPlayerActiveItemStride;
    const auto* key = luaL_checkstring(state, 2);
    if (!std::strcmp(key, "VarData")) {
        lua_pushinteger(state, Read<std::int32_t>(
                                   state, base, kActiveDescVarData,
                                   "ActiveItemDesc VarData"));
    } else if (!std::strcmp(key, "TimedRechargeCooldown")) {
        lua_pushinteger(state, Read<std::int32_t>(
                                   state, base, kActiveDescTimedCooldown,
                                   "ActiveItemDesc TimedRechargeCooldown"));
    } else if (!std::strcmp(key, "PartialCharge")) {
        lua_pushnumber(state, Read<float>(
                                  state, base, kActiveDescPartialCharge,
                                  "ActiveItemDesc PartialCharge"));
    } else if (!std::strcmp(key, "BatteryCharge")) {
        lua_pushinteger(state, Read<std::int32_t>(
                                   state, base, kActiveDescBatteryCharge,
                                   "ActiveItemDesc BatteryCharge"));
    } else if (!std::strcmp(key, "SubCharge")) {
        lua_pushinteger(state, Read<std::int32_t>(
                                   state, base, kActiveDescSubCharge,
                                   "ActiveItemDesc SubCharge"));
    } else if (!std::strcmp(key, "Charge")) {
        lua_pushinteger(state, Read<std::int32_t>(
                                   state, base, kActiveDescCharge,
                                   "ActiveItemDesc Charge"));
    } else if (!std::strcmp(key, "Item")) {
        lua_pushinteger(state, Read<std::int32_t>(
                                   state, base, kActiveDescItem,
                                   "ActiveItemDesc Item"));
    } else {
        lua_pushnil(state);
    }
    return 1;
}

int ActiveDescNewIndex(lua_State* state) {
    auto* handle = ActiveDesc(state);
    const auto base = engine_memory::AddressOf(handle->player) +
                      kEntityPlayerActiveItemOffset +
                      static_cast<std::uintptr_t>(handle->slot) *
                          kEntityPlayerActiveItemStride;
    const auto* key = luaL_checkstring(state, 2);
    if (!std::strcmp(key, "VarData")) {
        Write<std::int32_t>(state, base, kActiveDescVarData,
                            static_cast<std::int32_t>(luaL_checkinteger(state, 3)),
                            "ActiveItemDesc VarData");
    } else if (!std::strcmp(key, "TimedRechargeCooldown")) {
        Write<std::int32_t>(state, base, kActiveDescTimedCooldown,
                            static_cast<std::int32_t>(luaL_checkinteger(state, 3)),
                            "ActiveItemDesc TimedRechargeCooldown");
    } else if (!std::strcmp(key, "PartialCharge")) {
        Write<float>(state, base, kActiveDescPartialCharge,
                     static_cast<float>(luaL_checknumber(state, 3)),
                     "ActiveItemDesc PartialCharge");
    } else if (!std::strcmp(key, "BatteryCharge")) {
        Write<std::int32_t>(state, base, kActiveDescBatteryCharge,
                            static_cast<std::int32_t>(luaL_checkinteger(state, 3)),
                            "ActiveItemDesc BatteryCharge");
    } else if (!std::strcmp(key, "SubCharge")) {
        Write<std::int32_t>(state, base, kActiveDescSubCharge,
                            static_cast<std::int32_t>(luaL_checkinteger(state, 3)),
                            "ActiveItemDesc SubCharge");
    } else if (!std::strcmp(key, "Charge")) {
        Write<std::int32_t>(state, base, kActiveDescCharge,
                            static_cast<std::int32_t>(luaL_checkinteger(state, 3)),
                            "ActiveItemDesc Charge");
    } else if (!std::strcmp(key, "Item")) {
        Write<std::int32_t>(state, base, kActiveDescItem,
                            static_cast<std::int32_t>(luaL_checkinteger(state, 3)),
                            "ActiveItemDesc Item");
    } else {
        luaL_error(state, "unknown ActiveItemDesc field");
    }
    return 0;
}

}  // namespace

void RegisterRepentogonBocViews(lua_State* state) {
    if (!state) return;
    luaL_newmetatable(state, kActiveItemDescMetatable);
    lua_pushcfunction(state, ActiveDescIndex);
    lua_setfield(state, -2, "__index");
    lua_pushcfunction(state, ActiveDescNewIndex);
    lua_setfield(state, -2, "__newindex");
    lua_pushliteral(state, "ActiveItemDesc");
    lua_setfield(state, -2, "__type");
    lua_pushliteral(state, "ActiveItemDesc");
    lua_setfield(state, -2, "__class");
    lua_pop(state, 1);

    lua_getglobal(state, "EntityPlayer");
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);
    }
    static_cast<void>(AttachOwnerMethods(state, "EntityPlayer", nullptr, 0));
    lua_setglobal(state, "EntityPlayer");
}

int RepentogonEntityPlayerGetBagOfCraftingContent(lua_State* state) {
    const auto player = Player(state);
    NoArgs(state, "EntityPlayer:GetBagOfCraftingContent");
    lua_createtable(state, 8, 0);
    for (int index = 0; index < 8; ++index) {
        lua_pushinteger(state, Read<std::int8_t>(
                                   state, player, kBagContentOffset + index,
                                   "EntityPlayer bag content"));
        lua_rawseti(state, -2, index + 1);
    }
    return 1;
}

int RepentogonEntityPlayerGetBagOfCraftingOutput(lua_State* state) {
    const auto player = Player(state);
    NoArgs(state, "EntityPlayer:GetBagOfCraftingOutput");
    lua_pushinteger(state, Read<std::int32_t>(
                               state, player, kBagOutputOffset,
                               "EntityPlayer bag output"));
    return 1;
}

int RepentogonEntityPlayerGetActiveItemDesc(lua_State* state) {
    const auto player = Player(state);
    const auto slot = ActiveSlot(state);
    auto* lifetime=PushEntityLifetimeToken(state,player);
    const auto tokenIndex=lua_gettop(state);
    auto* handle = static_cast<ActiveItemDescHandle*>(
        lua_newuserdata(state, sizeof(ActiveItemDescHandle)));
    *handle = {engine_memory::AsObject(player),lifetime,LuaRuntime::EngineModuleBase(),
               static_cast<std::uint32_t>(slot), 0};
    lua_pushvalue(state,tokenIndex);
    lua_setuservalue(state,-2);
    luaL_getmetatable(state, kActiveItemDescMetatable);
    lua_setmetatable(state, -2);
    lua_remove(state,tokenIndex);
    return 1;
}

int RepentogonEntityPlayerCalculateBagOfCraftingOutput(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread())
        return luaL_error(state,"CalculateBagOfCraftingOutput requires the game thread");
    if (!lua_istable(state, 1)) return luaL_argerror(state, 1, "expected a table");
    if (lua_rawlen(state, 1) != 8) {
        return luaL_error(state, "CalculateBagOfCraftingOutput expects exactly 8 pickups");
    }
    std::array<std::int8_t, 8> pickups{};
    for (int index = 0; index < 8; ++index) {
        lua_rawgeti(state, 1, index + 1);
        const auto pickup = static_cast<int>(luaL_checkinteger(state, -1));
        lua_pop(state, 1);
        if (pickup < 0 || pickup > 29) {
            return luaL_error(state, "invalid BagOfCraftingPickup %d", pickup);
        }
        pickups[index] = static_cast<std::int8_t>(pickup);
    }
    std::int32_t output{};
#if defined(__SWITCH__)
    const auto base = LuaRuntime::EngineModuleBase();
    if (!base || base > UINTPTR_MAX - kCalculateOffset ||
        !engine_call::VerifyEntryBytes(base + kCalculateOffset,
            kCalculateGuard.data(), kCalculateGuard.size(),
            engine_memory::EngineMemoryReadable)) {
        return luaL_error(state, "CalculateBagOfCraftingOutput native binding is unavailable");
    }
    using Fn = std::int32_t (*)(void*, const void*, bool);
    output = engine_call::AsFunction<Fn>(base + kCalculateOffset)(
        nullptr, pickups.data(), false);
#else
    if (!g_TestBindings.calculate) {
        return luaL_error(state, "CalculateBagOfCraftingOutput host binding is unavailable");
    }
    output = g_TestBindings.calculate(nullptr, pickups.data(), false);
#endif
    lua_pushinteger(state, output);
    // The Switch player layout stores only the collectible. PC's second
    // ItemPoolType component has no corresponding field; leave it absent
    // rather than fabricating a pool id.
    return 1;
}

#if !defined(__SWITCH__)
void SetRepentogonBocNativeTestBindings(
    RepentogonBocNativeTestBindings bindings) noexcept {
    g_TestBindings = bindings;
}
#endif

}
