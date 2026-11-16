#include "interfaces/lua/repentogon_playerhud_hearts_api.hpp"

#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

constexpr char kPlayerHud[] = "IsaacRuntime.PlayerHUD";
constexpr char kPlayerHudHeart[] = "IsaacRuntime.PlayerHUDHeart";
// HUD::get_player_hud (0x3AAA0C) visits eight inline PlayerHUD slots.
constexpr std::size_t kPlayerHudCount = 8;
constexpr std::uintptr_t kPlayerHudStride = 0x908;
// PlayerHUD::Update (0x3A0E00) passes this inline array to UpdateHearts.
constexpr std::uintptr_t kHeartsOffset = 0x18;
constexpr std::size_t kHeartCount = 24;

struct PlayerHudHandle {
    std::uintptr_t hud;
    std::size_t index;
};

// PlayerHUD::RenderHearts reads these fields from its 0x18-byte heart slots.
struct Heart {
    std::uint8_t visible;
    std::uint8_t eternal;
    std::uint8_t golden;
    std::uint8_t fading;
    std::uint8_t flash;
    std::array<std::byte, 3> unused;
    std::uintptr_t animation;
    std::uintptr_t overlayAnimation;
};

static_assert(offsetof(Heart, animation) == 8);
static_assert(offsetof(Heart, overlayAnimation) == 0x10);
static_assert(sizeof(Heart) == 0x18);

std::uintptr_t CurrentHud(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        luaL_error(state, "PlayerHUD access requires the game thread");
    }
    std::uintptr_t owner{};
    std::uintptr_t game{};
    if (!engine_memory::ReadAt(
            LuaRuntime::GameOwnerSlot(), &owner, engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadAt(owner, &game, engine_memory::EngineMemoryReadable) ||
        !game || game > UINTPTR_MAX - kGameHudObjectOffset - kPlayerHudCount * kPlayerHudStride) {
        luaL_error(state, "HUD is unavailable");
    }
    return game + kGameHudObjectOffset;
}

int GetPlayerHud(lua_State* state) {
    luaL_checkudata(state, 1, LuaRuntime::kHudMetatable);
    const auto index = luaL_optinteger(state, 2, 0);
    if (index < 0 || static_cast<std::size_t>(index) >= kPlayerHudCount) {
        return luaL_argerror(state, 2, "player HUD index must be between 0 and 7");
    }
    const auto hud = CurrentHud(state);
    auto* handle = static_cast<PlayerHudHandle*>(lua_newuserdata(state, sizeof(PlayerHudHandle)));
    *handle = {hud, static_cast<std::size_t>(index)};
    luaL_setmetatable(state, kPlayerHud);
    return 1;
}

int GetHearts(lua_State* state) {
    const auto* handle = static_cast<const PlayerHudHandle*>(luaL_checkudata(state, 1, kPlayerHud));
    const auto hud = CurrentHud(state);
    std::array<Heart, kHeartCount> hearts{};
    if (handle->hud != hud || handle->index >= kPlayerHudCount ||
        !engine_memory::ReadField(hud, handle->index * kPlayerHudStride + kHeartsOffset,
                                  &hearts, engine_memory::EngineMemoryReadable)) {
        return luaL_error(state, "PlayerHUD heart data is unavailable");
    }
    lua_createtable(state, kHeartCount, 0);
    for (std::size_t index = 0; index < hearts.size(); ++index) {
        auto* heart = static_cast<Heart*>(lua_newuserdata(state, sizeof(Heart)));
        *heart = hearts[index];
        luaL_setmetatable(state, kPlayerHudHeart);
        lua_rawseti(state, -2, static_cast<lua_Integer>(index + 1));
    }
    return 1;
}

const Heart& CheckHeart(lua_State* state) {
    return *static_cast<const Heart*>(luaL_checkudata(state, 1, kPlayerHudHeart));
}

template<std::uint8_t Heart::*Field>
int HeartFlag(lua_State* state) {
    lua_pushboolean(state, (CheckHeart(state).*Field) != 0);
    return 1;
}

int FlashType(lua_State* state) {
    lua_pushinteger(state, CheckHeart(state).flash);
    return 1;
}

template<std::uintptr_t Heart::*Field>
int AnimationName(lua_State* state) {
    const auto address = CheckHeart(state).*Field;
    if (!address) {
        lua_pushnil(state);
        return 1;
    }
    // The renderer stores pointers to its static animation-name strings.
    constexpr std::size_t kMaximumName = 64;
    for (std::size_t index = 0; index < kMaximumName; ++index) {
        char value{};
        if (!engine_memory::ReadField(address, index, &value, engine_memory::EngineMemoryReadable)) {
            break;
        }
        if (value == '\0') {
            const auto* name = static_cast<const char*>(engine_memory::AsObject(address));
            lua_pushlstring(state, name, index);
            return 1;
        }
    }
    return luaL_error(state, "PlayerHUDHeart animation name is unavailable");
}

int GetPlayerIndex(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        return luaL_error(state, "EntityPlayer access requires the game thread");
    }
    const auto player = ResolveEngineReceiver(state, FieldReceipt::EntityPlayer);
    std::uint32_t index{};
    if (!engine_memory::ReadField(
            player, kEntityPlayerIndexOffset, &index, engine_memory::EngineMemoryReadable)) {
        return luaL_error(state, "EntityPlayer index is unavailable");
    }
    lua_pushinteger(state, index);
    return 1;
}

void RegisterClass(lua_State* state, const char* name, const luaL_Reg* methods) {
    luaL_newmetatable(state, name);
    luaL_setfuncs(state, methods, 0);
    lua_pushvalue(state, -1);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);
}

void AttachMethod(lua_State* state, const char* type, const char* name, lua_CFunction method) {
    luaL_getmetatable(state, type);
    lua_getfield(state, -1, "__methods");
    lua_pushcfunction(state, method);
    lua_setfield(state, -2, name);
    lua_pop(state, 2);
}

}  // namespace

void RegisterRepentogonPlayerHudHearts(lua_State* state) {
    constexpr luaL_Reg hudMethods[] = {{"GetHearts", GetHearts}, {nullptr, nullptr}};
    constexpr luaL_Reg heartMethods[] = {
        {"IsVisible", HeartFlag<&Heart::visible>},
        {"IsEternalHeartOverlayVisible", HeartFlag<&Heart::eternal>},
        {"IsGoldenHeartOverlayVisible", HeartFlag<&Heart::golden>},
        {"IsFadingHeart", HeartFlag<&Heart::fading>},
        {"GetFlashType", FlashType},
        {"GetHeartAnim", AnimationName<&Heart::animation>},
        {"GetHeartOverlayAnim", AnimationName<&Heart::overlayAnimation>},
        {nullptr, nullptr},
    };
    RegisterClass(state, kPlayerHud, hudMethods);
    RegisterClass(state, kPlayerHudHeart, heartMethods);
    AttachMethod(state, LuaRuntime::kHudMetatable, "GetPlayerHUD", GetPlayerHud);
    AttachMethod(state, LuaRuntime::kEntityPlayerMetatable, "GetPlayerIndex", GetPlayerIndex);
}

}  // namespace isaac::runtime
