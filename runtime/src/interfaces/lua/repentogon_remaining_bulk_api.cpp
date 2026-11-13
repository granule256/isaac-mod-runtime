#include "interfaces/lua/repentogon_remaining_bulk_api.hpp"

#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "game_observer.hpp"
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

constexpr std::uintptr_t kPlayerDamageModifierOffset = 0x1910;
constexpr std::uintptr_t kPlayerEdenDamageOffset = 0x1938;
constexpr std::uintptr_t kPlayerD8DamageModifierOffset = 0x1db4;
constexpr std::uintptr_t kPlayerBackupPlayerOffset = 0x2588;
constexpr std::uintptr_t kItemPoolPoolStride = 0x48;
constexpr std::uintptr_t kItemPoolPoolListBeginOffset = 0x08;
constexpr std::uintptr_t kItemPoolPoolListEndOffset = 0x10;
constexpr std::size_t kItemPoolPoolItemStride = 0x18;
constexpr std::int32_t kItemPoolCount = 31;

#if !defined(__SWITCH__)
RepentogonRemainingBulkNativeTestBindings g_TestBindings{};
#endif

void RequireThread(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        luaL_error(state, "REPENTOGON native access requires the game thread");
    }
}

void RequireNoArgs(lua_State* state, const char* name) {
    if (lua_gettop(state) != 1) {
        luaL_error(state, "%s accepts no arguments", name);
    }
}

std::uintptr_t Player(lua_State* state) {
    RequireThread(state);
    const auto player = ResolveEngineReceiver(state, FieldReceipt::EntityPlayer, 1);
    if (!player) {
        luaL_error(state, "EntityPlayer reference is no longer available");
    }
    const auto base = LuaRuntime::EngineModuleBase();
    std::uintptr_t vtable{};
    std::uint32_t type{};
    if (!base || base > UINTPTR_MAX - kEntityPlayerVtableOffset ||
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

std::uintptr_t Pickup(lua_State* state) {
    RequireThread(state);
    luaL_checkudata(state, 1, LuaRuntime::kEntityPickupMetatable);
    const auto pickup = EntityPointerArgument(state, 1);
    if (!pickup || !IsPickupEntity(pickup)) {
        luaL_error(state, "EntityPickup reference is no longer available");
    }
    return pickup;
}

std::uintptr_t ItemPool(lua_State* state) {
    RequireThread(state);
    luaL_checkudata(state, 1, LuaRuntime::kItemPoolMetatable);
#if !defined(__SWITCH__)
    if (g_TestBindings.itemPool) {
        return engine_memory::AddressOf(g_TestBindings.itemPool);
    }
#endif
    void* pool{};
    if (ReadCurrentGameItemPool(LuaRuntime::GameOwnerSlot(), &pool) !=
            GameItemPoolObservation::Success ||
        !pool) {
        luaL_error(state, "ItemPool is no longer available");
    }
    return engine_memory::AddressOf(pool);
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

bool HasQuestionmarkSheet(lua_State* state, std::uintptr_t pickup) {
    constexpr char expected[] = "gfx/Items/Collectibles/questionmark.png";
    const auto sprite = pickup + kEntitySpriteOffset;
    const auto count = Read<std::int32_t>(state, sprite, kAnim2LayerCountOffset,
                                          "Pickup Sprite layer count");
    if (count < 0) luaL_error(state, "Pickup Sprite layer count is invalid");
    if (count < 2) return false;
    const auto layers = Read<std::uintptr_t>(state, sprite, 0xa8,
                                              "Pickup Sprite layer states");
    // ANM2::GetLayer uses a 0xb0 stride; LayerState::Reset copies the
    // spritesheet path into its native libc++ string at +0x10.
    if (!layers || layers > UINTPTR_MAX - 0xb0 - 0x10) {
        luaL_error(state, "Pickup Sprite layer states are unavailable");
    }
    const auto path = layers + 0xb0 + 0x10;
    const auto words = Read<std::array<std::uintptr_t, 3>>(
        state, path, 0, "Pickup spritesheet path");
    const bool isLong = (words[0] & kLibcxxStringLongFlag) != 0;
    const auto length = isLong ? words[1] : (words[0] & 0xffU) >> 1;
    if (!isLong && length >= sizeof(words)) {
        luaL_error(state, "Pickup spritesheet string is invalid");
    }
    if (length != sizeof(expected) - 1) return false;
    const auto data = isLong ? words[2] : path + kLibcxxStringShortDataOffset;
    const auto text = Read<std::array<char, sizeof(expected) - 1>>(
        state, data, 0, "Pickup spritesheet bytes");
    return std::memcmp(text.data(), expected, text.size()) == 0;
}

void PushItemPoolTable(lua_State* state, std::uintptr_t itemPool) {
    if (itemPool > UINTPTR_MAX - kItemPoolCount * kItemPoolPoolStride -
                       kItemPoolPoolListEndOffset) {
        luaL_error(state, "ItemPool table address is invalid");
    }
    const auto type = static_cast<std::uint32_t>(luaL_checkinteger(state, 2));
    if (type >= static_cast<std::uint32_t>(kItemPoolCount)) {
        luaL_argerror(state, 2, "Invalid ItemPoolType");
    }

    const auto pool = itemPool + kItemPoolPoolListBeginOffset +
                      static_cast<std::uintptr_t>(type) * kItemPoolPoolStride;
    const auto begin = Read<std::uintptr_t>(state, pool, 0x00,
                                            "ItemPool pool list begin");
    const auto end = Read<std::uintptr_t>(state, pool,
                                          kItemPoolPoolListEndOffset -
                                              kItemPoolPoolListBeginOffset,
                                          "ItemPool pool list end");
    if (!begin || end < begin || (end - begin) % kItemPoolPoolItemStride != 0) {
        luaL_error(state, "ItemPool pool list is invalid");
    }
    const auto count = (end - begin) / kItemPoolPoolItemStride;
    if (count > 0x10000) {
        luaL_error(state, "ItemPool pool list is too large");
    }
    lua_createtable(state, static_cast<int>(count), 0);
    for (std::size_t index = 0; index < count; ++index) {
        const auto entry = begin + index * kItemPoolPoolItemStride;
        if (!engine_memory::EngineMemoryReadable(entry,
                                                 kItemPoolPoolItemStride)) {
            luaL_error(state, "ItemPool entry is not readable");
        }
        lua_createtable(state, 0, 6);
        lua_pushinteger(state, static_cast<lua_Integer>(
                                  Read<std::int32_t>(state, entry, 0x00,
                                                     "ItemPool itemID")));
        lua_setfield(state, -2, "itemID");
        lua_pushnumber(state, Read<float>(state, entry, 0x04,
                                          "ItemPool initialWeight"));
        lua_setfield(state, -2, "initialWeight");
        lua_pushnumber(state, Read<float>(state, entry, 0x08,
                                          "ItemPool weight"));
        lua_setfield(state, -2, "weight");
        lua_pushnumber(state, Read<float>(state, entry, 0x0c,
                                          "ItemPool decreaseBy"));
        lua_setfield(state, -2, "decreaseBy");
        lua_pushnumber(state, Read<float>(state, entry, 0x10,
                                          "ItemPool removeOn"));
        lua_setfield(state, -2, "removeOn");
        lua_pushboolean(state, Read<std::uint8_t>(state, entry, 0x14,
                                                  "ItemPool isUnlocked") != 0);
        lua_setfield(state, -2, "isUnlocked");
        lua_rawseti(state, -2, static_cast<lua_Integer>(index + 1));
    }
}

}  // namespace

void RegisterRepentogonRemainingBulkViews(lua_State* state) {
    if (!state) {
        return;
    }
    luaL_getmetatable(state, LuaRuntime::kEntityPlayerMetatable);
    if (!lua_istable(state, -1)) {
        luaL_error(state, "EntityPlayer metatable is unavailable");
    }
    static_cast<void>(AttachOwnerMethods(state, "EntityPlayer", nullptr, 0));
    lua_pop(state, 1);

    luaL_getmetatable(state, LuaRuntime::kEntityPickupMetatable);
    if (!lua_istable(state, -1)) {
        luaL_error(state, "EntityPickup metatable is unavailable");
    }
    static_cast<void>(AttachOwnerMethods(state, "EntityPickup", nullptr, 0));
    lua_pop(state, 1);

    luaL_getmetatable(state, LuaRuntime::kItemPoolMetatable);
    if (!lua_istable(state, -1)) {
        luaL_error(state, "ItemPool metatable is unavailable");
    }
    static_cast<void>(AttachOwnerMethods(state, "ItemPool", nullptr, 0));
    lua_pop(state, 1);
}

int RepentogonEntityPlayerGetDamageModifier(lua_State* state) {
    const auto player = Player(state);
    RequireNoArgs(state, "EntityPlayer:GetDamageModifier");
    lua_pushinteger(state, Read<std::int32_t>(
                               state, player, kPlayerDamageModifierOffset,
                               "EntityPlayer damage modifier"));
    return 1;
}

int RepentogonEntityPlayerGetEdenDamage(lua_State* state) {
    const auto player = Player(state);
    RequireNoArgs(state, "EntityPlayer:GetEdenDamage");
    lua_pushnumber(state, Read<float>(state, player, kPlayerEdenDamageOffset,
                                      "EntityPlayer Eden damage"));
    return 1;
}

int RepentogonEntityPlayerGetD8DamageModifier(lua_State* state) {
    const auto player = Player(state);
    RequireNoArgs(state, "EntityPlayer:GetD8DamageModifier");
    lua_pushnumber(state, Read<float>(
                               state, player, kPlayerD8DamageModifierOffset,
                               "EntityPlayer D8 damage modifier"));
    return 1;
}

int RepentogonEntityPlayerGetFlippedForm(lua_State* state) {
    const auto player = Player(state);
    RequireNoArgs(state, "EntityPlayer:GetFlippedForm");
    const auto backup = Read<std::uintptr_t>(state, player,
                                             kPlayerBackupPlayerOffset,
                                             "EntityPlayer flipped form");
    if (!backup) {
        lua_pushnil(state);
        return 1;
    }
    if (!IsLiveEntityPointer(backup)) {
        return luaL_error(state, "EntityPlayer flipped form is no longer available");
    }
    PushEntityCallbackArgument(state, backup);
    if (lua_isnil(state, -1)) {
        return luaL_error(state, "EntityPlayer flipped form is no longer available");
    }
    return 1;
}

int RepentogonEntityPickupIsBlind(lua_State* state) {
    const auto pickup = Pickup(state);
    if (lua_gettop(state) > 2) {
        return luaL_error(state, "EntityPickup:IsBlind accepts at most one argument");
    }
    const auto variant = Read<std::uint32_t>(state, pickup,
                                             kEntityVariantOffset,
                                             "EntityPickup variant");
    if (variant != 100) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const auto force = Read<std::uint8_t>(
        state, pickup, kEntityPickupForceBlindOffset,
        "EntityPickup force-blind flag");
    const bool forcedOnly = lua_isnoneornil(state, 2) || lua_toboolean(state, 2);
    lua_pushboolean(state, force != 0 || (!forcedOnly && HasQuestionmarkSheet(state, pickup)));
    return 1;
}

int RepentogonItemPoolGetNumItemPools(lua_State* state) {
    static_cast<void>(ItemPool(state));
    RequireNoArgs(state, "ItemPool:GetNumItemPools");
    lua_pushinteger(state, kItemPoolCount);
    return 1;
}

int RepentogonItemPoolGetCollectiblesFromPool(lua_State* state) {
    const auto itemPool = ItemPool(state);
    PushItemPoolTable(state, itemPool);
    return 1;
}

#if !defined(__SWITCH__)
void SetRepentogonRemainingBulkNativeTestBindings(
    RepentogonRemainingBulkNativeTestBindings value) noexcept {
    g_TestBindings = value;
}
#endif

}
