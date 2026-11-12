#include "interfaces/lua/repentogon_menu_world_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstdint>
#include <cstring>

extern "C" {
#include "lauxlib.h"
}

namespace isaac::runtime {
namespace {

// All offsets below were independently checked against the pinned Switch NRO
// (build ID 91C73FDD575061318D68886316AFEAC72388B2AB).
constexpr std::uintptr_t kMenuManagerSlot = 0xAAD1B0;
constexpr std::uintptr_t kMenuManagerState = 0x38;
constexpr std::uintptr_t kMenuManagerViewPosition = 0x3C;
constexpr std::uintptr_t kMenuManagerViewPositionSet = 0x1AFF08;
constexpr std::uintptr_t kMenuSavePage = 0x7D8;
constexpr std::uintptr_t kMenuSaveDeletePopupSprite = 0x6E0;
constexpr std::uintptr_t kMenuGamePage = 0x813A0;
constexpr std::uintptr_t kMenuGameContinueWidgetSprite = 0x168;
constexpr std::uintptr_t kMenuCollectionPage = 0x1A3DA8;
constexpr std::uintptr_t kMenuCollectionSelectedPage = 0x04;
constexpr std::uintptr_t kMenuCollectionSelectedElement = 0x10;

constexpr std::uintptr_t kGameRoomTransition = 0x25810;
constexpr std::uintptr_t kRoomTransitionVersusSprite = 0x48;
constexpr std::uintptr_t kRoomTransitionBossIntroFlag = 0x3E8;
constexpr std::uintptr_t kGameAmbush = 0x26FAA8;
constexpr std::uintptr_t kAmbushCurrentWave = 0x3C;

constexpr std::uintptr_t kRoomDescriptorDimension = 0x0C;
constexpr std::uintptr_t kRoomDescriptorTaintedKeeperCoinSpawns = 0x5E;

constexpr std::int32_t kMinimumMainMenu = 1;
constexpr std::int32_t kMaximumMainMenu = 22;

#if defined(__SWITCH__)
constexpr std::array<std::uint8_t, 16> kIsRenderingBossIntroGuard = {
    0x08, 0xA0, 0x4F, 0x39, 0xA8, 0x00, 0x00, 0x34,
    0x08, 0x00, 0x40, 0xB9, 0x1F, 0x09, 0x00, 0x71,
};
#else
RepentogonMenuWorldNativeTestBindings g_TestBindings{};
#endif

struct Vector2 {
    float x{};
    float y{};
};

[[nodiscard]] std::uintptr_t TryReadSingleton(std::uintptr_t slotOffset) noexcept {
    const auto base = LuaRuntime::EngineModuleBase();
    std::uintptr_t slot{};
    std::uintptr_t object{};
    if (base == 0 || base > UINTPTR_MAX - slotOffset ||
        !engine_memory::ReadField(base, slotOffset, &slot,
                                  engine_memory::EngineMemoryReadable) ||
        slot == 0 ||
        !engine_memory::ReadAt(slot, &object,
                               engine_memory::EngineMemoryReadable) ||
        object == 0) {
        return 0;
    }
    return object;
}

[[nodiscard]] std::uintptr_t TryCurrentGame() noexcept {
    const auto slot = LuaRuntime::GameOwnerSlot();
    std::uintptr_t ownerSlot{};
    std::uintptr_t game{};
    if (slot == 0 ||
        !engine_memory::ReadAt(slot, &ownerSlot,
                               engine_memory::EngineMemoryReadable) ||
        ownerSlot == 0 ||
        !engine_memory::ReadAt(ownerSlot, &game,
                               engine_memory::EngineMemoryReadable)) {
        return 0;
    }
    return game;
}

void RequireGameThread(lua_State* state, const char* api) {
    if (!LuaRuntime::IsOnGameThread()) {
        luaL_error(state, "%s requires the game thread", api);
    }
}

void RequireNoArguments(lua_State* state, const char* api) {
    if (lua_gettop(state) != 0) {
        luaL_error(state, "%s accepts no arguments", api);
    }
}

[[nodiscard]] std::uintptr_t RequireGame(lua_State* state) {
    const auto game = TryCurrentGame();
    if (game == 0) {
        luaL_error(state, "Game is unavailable");
    }
    return game;
}

[[nodiscard]] std::uintptr_t RequireMenuManager(lua_State* state) {
    const auto menu = TryReadSingleton(kMenuManagerSlot);
    if (menu == 0) {
        luaL_error(state, "MenuManager is unavailable");
    }
    return menu;
}

[[nodiscard]] std::uintptr_t RequireManager(lua_State* state) {
    const auto manager = TryReadSingleton(kGameManagerGlobalSlotOffset);
    if (manager == 0) {
        luaL_error(state, "Manager is unavailable");
    }
    return manager;
}

template <class T>
[[nodiscard]] T ReadField(lua_State* state, std::uintptr_t object,
                          std::uintptr_t offset, const char* message) {
    T value{};
    if (!engine_memory::ReadField(object, offset, &value,
                                  engine_memory::EngineMemoryReadable)) {
        luaL_error(state, "%s", message);
    }
    return value;
}

[[nodiscard]] std::uintptr_t RequireRoomTransition(lua_State* state) {
    const auto game = RequireGame(state);
    if (game > UINTPTR_MAX - kGameRoomTransition) {
        luaL_error(state, "RoomTransition is unavailable");
    }
    const auto transition = game + kGameRoomTransition;
    if (!engine_memory::EngineMemoryReadable(
            transition, kRoomTransitionBossIntroFlag + sizeof(std::uint8_t))) {
        luaL_error(state, "RoomTransition is unavailable");
    }
    return transition;
}

void PushSceneSprite(lua_State* state, std::uintptr_t sprite,
                     const char* api) {
    if (sprite == 0 ||
        !engine_memory::EngineMemoryReadable(sprite, kSpriteObjectSize)) {
        luaL_error(state, "%s sprite is unavailable", api);
    }
    if (!repentogon::HasSpriteValidator()) {
        luaL_error(state, "%s sprite lifetime validation is unavailable", api);
    }
    if (!repentogon::CallbackSpriteAlive(sprite)) {
        luaL_error(state, "%s sprite owner is no longer alive", api);
    }
    PushCallbackSpriteHandle(state, sprite, LUA_NOREF);
    if (lua_isnil(state, -1)) {
        luaL_error(state, "%s sprite owner is no longer alive", api);
    }
}

void CreateGlobalOwnerTable(lua_State* state, const char* owner) {
    lua_getglobal(state, owner);
    if (!lua_istable(state, -1)) {
        lua_pop(state, 1);
        lua_newtable(state);
    }
    static_cast<void>(AttachOwnerMethods(state, owner, nullptr, 0));
    lua_setglobal(state, owner);
}

}  // namespace

int RepentogonMenuManagerGetActiveMenu(lua_State* state) {
    RequireGameThread(state, "MenuManager.GetActiveMenu");
    RequireNoArguments(state, "MenuManager.GetActiveMenu");
    const auto menu = RequireMenuManager(state);
    lua_pushinteger(
        state,
        static_cast<lua_Integer>(ReadField<std::int32_t>(
            state, menu, kMenuManagerState, "MenuManager state is unavailable")));
    return 1;
}

int RepentogonMenuManagerIsActive(lua_State* state) {
    RequireGameThread(state, "MenuManager.IsActive");
    RequireNoArguments(state, "MenuManager.IsActive");
    lua_pushboolean(state, TryReadSingleton(kMenuManagerSlot) != 0);
    return 1;
}

int RepentogonCollectionMenuGetSelectedPage(lua_State* state) {
    RequireGameThread(state, "CollectionMenu.GetSelectedPage");
    RequireNoArguments(state, "CollectionMenu.GetSelectedPage");
    const auto menu = RequireMenuManager(state);
    lua_pushinteger(
        state,
        static_cast<lua_Integer>(ReadField<std::int32_t>(
            state, menu, kMenuCollectionPage + kMenuCollectionSelectedPage,
            "CollectionMenu selected page is unavailable")));
    return 1;
}

int RepentogonCollectionMenuGetSelectedElement(lua_State* state) {
    RequireGameThread(state, "CollectionMenu.GetSelectedElement");
    RequireNoArguments(state, "CollectionMenu.GetSelectedElement");
    const auto menu = RequireMenuManager(state);
    lua_pushinteger(
        state,
        static_cast<lua_Integer>(ReadField<std::int32_t>(
            state, menu, kMenuCollectionPage + kMenuCollectionSelectedElement,
            "CollectionMenu selected element is unavailable")));
    return 1;
}

int RepentogonSaveMenuGetDeletePopupSprite(lua_State* state) {
    RequireGameThread(state, "SaveMenu.GetDeletePopupSprite");
    RequireNoArguments(state, "SaveMenu.GetDeletePopupSprite");
    const auto menu = RequireMenuManager(state);
    PushSceneSprite(state,
                    menu + kMenuSavePage + kMenuSaveDeletePopupSprite,
                    "SaveMenu.GetDeletePopupSprite");
    return 1;
}

int RepentogonMainMenuGetContinueWidgetSprite(lua_State* state) {
    RequireGameThread(state, "MainMenu.GetContinueWidgetSprite");
    RequireNoArguments(state, "MainMenu.GetContinueWidgetSprite");
    const auto menu = RequireMenuManager(state);
    PushSceneSprite(state,
                    menu + kMenuGamePage + kMenuGameContinueWidgetSprite,
                    "MainMenu.GetContinueWidgetSprite");
    return 1;
}

int RepentogonWorldToMenuPosition(lua_State* state) {
    RequireGameThread(state, "Isaac.WorldToMenuPosition");
    if (lua_gettop(state) != 2) {
        luaL_error(state,
                   "Isaac.WorldToMenuPosition expects menu id and position");
    }
    const auto rawMenuId = static_cast<std::int32_t>(luaL_checkinteger(state, 1));
    if (rawMenuId < kMinimumMainMenu || rawMenuId > kMaximumMainMenu) {
        luaL_error(state, "Invalid Menu Id %d",
                   static_cast<int>(rawMenuId));
    }
    const auto menuId = static_cast<std::uint32_t>(rawMenuId);
    const auto* position = RequireVectorArgument(state, 2);
    if (position == nullptr) {
        return luaL_error(state,
                          "Isaac.WorldToMenuPosition expects a Vector");
    }
    const auto menu = RequireMenuManager(state);
    const auto current = ReadField<Vector2>(
        state, menu, kMenuManagerViewPosition,
        "MenuManager view position is unavailable");
    const auto target = ReadField<Vector2>(
        state, menu,
        kMenuManagerViewPositionSet +
            static_cast<std::uintptr_t>(menuId) * sizeof(Vector2),
        "Menu target position is unavailable");
    PushLuaVector(state,
                  current.x + 39.0F - target.x + position->x,
                  current.y + 15.0F - target.y + position->y);
    return 1;
}

int RepentogonRoomTransitionIsRenderingBossIntro(lua_State* state) {
    RequireGameThread(state, "RoomTransition.IsRenderingBossIntro");
    RequireNoArguments(state, "RoomTransition.IsRenderingBossIntro");
    const auto transition = RequireRoomTransition(state);
#if defined(__SWITCH__)
    const auto base = LuaRuntime::EngineModuleBase();
    constexpr std::uintptr_t kMethod = 0x49AE7C;
    if (base == 0 || base > UINTPTR_MAX - kMethod ||
        !engine_call::VerifyEntryBytes(
            base + kMethod, kIsRenderingBossIntroGuard.data(),
            kIsRenderingBossIntroGuard.size(),
            engine_memory::EngineMemoryReadable)) {
        return luaL_error(state,
                          "RoomTransition.IsRenderingBossIntro native binding is unavailable");
    }
    using Fn = bool (*)(const void*);
    lua_pushboolean(
        state,
        engine_call::AsFunction<Fn>(base + kMethod)(
            engine_memory::AsObject(transition)));
#else
    if (!g_TestBindings.isRenderingBossIntro) {
        return luaL_error(
            state, "RoomTransition.IsRenderingBossIntro host binding is unavailable");
    }
    lua_pushboolean(
        state,
        g_TestBindings.isRenderingBossIntro(
            engine_memory::AsObject(transition)));
#endif
    return 1;
}

int RepentogonRoomTransitionGetVersusScreenSprite(lua_State* state) {
    RequireGameThread(state, "RoomTransition.GetVersusScreenSprite");
    RequireNoArguments(state, "RoomTransition.GetVersusScreenSprite");
    const auto transition = RequireRoomTransition(state);
    PushSceneSprite(state, transition + kRoomTransitionVersusSprite,
                    "RoomTransition.GetVersusScreenSprite");
    return 1;
}

int RepentogonAmbushGetCurrentWave(lua_State* state) {
    RequireGameThread(state, "Ambush.GetCurrentWave");
    RequireNoArguments(state, "Ambush.GetCurrentWave");
    const auto game = RequireGame(state);
    lua_pushinteger(
        state,
        static_cast<lua_Integer>(ReadField<std::int32_t>(
            state, game, kGameAmbush + kAmbushCurrentWave,
            "Ambush current wave is unavailable")));
    return 1;
}

int RepentogonNightmareSceneIsDogmaNightmare(lua_State* state) {
    RequireGameThread(state, "NightmareScene.IsDogmaNightmare");
    RequireNoArguments(state, "NightmareScene.IsDogmaNightmare");
    const auto manager = RequireManager(state);
    const auto value = ReadField<std::uint8_t>(
        state, manager, kManagerNightmareSceneOffset + 0x5E8,
        "NightmareScene Dogma state is unavailable");
    lua_pushboolean(state, value != 0);
    return 1;
}

int RepentogonRoomDescriptorGetDimension(lua_State* state) {
    RequireGameThread(state, "RoomDescriptor.GetDimension");
    if (lua_gettop(state) != 1) {
        return luaL_error(
            state, "RoomDescriptor.GetDimension accepts no arguments");
    }
    const auto descriptor = ResolveRoomDescriptorArgument(state, 1);
    if (descriptor == 0) {
        return luaL_error(
            state, "RoomDescriptor reference is no longer available");
    }
    lua_pushinteger(
        state,
        static_cast<lua_Integer>(ReadField<std::int32_t>(
            state, descriptor, kRoomDescriptorDimension,
            "RoomDescriptor dimension is unavailable")));
    return 1;
}

int RepentogonRoomDescriptorGetTaintedKeeperCoinSpawns(lua_State* state) {
    RequireGameThread(state,
                      "RoomDescriptor.GetTaintedKeeperCoinSpawns");
    if (lua_gettop(state) != 1) {
        return luaL_error(
            state,
            "RoomDescriptor.GetTaintedKeeperCoinSpawns accepts no arguments");
    }
    const auto descriptor = ResolveRoomDescriptorArgument(state, 1);
    if (descriptor == 0) {
        return luaL_error(
            state, "RoomDescriptor reference is no longer available");
    }
    lua_pushinteger(
        state,
        static_cast<lua_Integer>(ReadField<std::int16_t>(
            state, descriptor, kRoomDescriptorTaintedKeeperCoinSpawns,
            "RoomDescriptor Tainted Keeper coin counter is unavailable")));
    return 1;
}

int RepentogonRoomDescriptorSetTaintedKeeperCoinSpawns(lua_State* state) {
    RequireGameThread(state,
                      "RoomDescriptor.SetTaintedKeeperCoinSpawns");
    if (lua_gettop(state) != 2) {
        return luaL_error(
            state,
            "RoomDescriptor.SetTaintedKeeperCoinSpawns expects one integer");
    }
    const auto descriptor = ResolveRoomDescriptorArgument(state, 1);
    if (descriptor == 0) {
        return luaL_error(
            state, "RoomDescriptor reference is no longer available");
    }
    const auto value =
        static_cast<std::int16_t>(luaL_checkinteger(state, 2));
    if (!engine_memory::WriteField(
            descriptor, kRoomDescriptorTaintedKeeperCoinSpawns, value,
            engine_memory::EngineMemoryWritable)) {
        return luaL_error(
            state, "RoomDescriptor Tainted Keeper coin counter is not writable");
    }
    return 0;
}

bool RepentogonMenuWorldSpriteAlive(std::uintptr_t sprite) noexcept {
    if (sprite == 0 ||
        !engine_memory::EngineMemoryReadable(sprite, kSpriteObjectSize)) {
        return false;
    }
    const auto menu = TryReadSingleton(kMenuManagerSlot);
    if (menu != 0) {
        if (menu <= UINTPTR_MAX - kMenuSavePage -
                        kMenuSaveDeletePopupSprite &&
            sprite == menu + kMenuSavePage +
                          kMenuSaveDeletePopupSprite) {
            return true;
        }
        if (menu <= UINTPTR_MAX - kMenuGamePage -
                        kMenuGameContinueWidgetSprite &&
            sprite == menu + kMenuGamePage +
                          kMenuGameContinueWidgetSprite) {
            return true;
        }
    }
    const auto game = TryCurrentGame();
    return game != 0 &&
           game <= UINTPTR_MAX - kGameRoomTransition -
                       kRoomTransitionVersusSprite &&
           sprite == game + kGameRoomTransition +
                         kRoomTransitionVersusSprite;
}

int RegisterRepentogonMenuWorldApi(lua_State* state) {
    if (state == nullptr) {
        return 0;
    }
    for (const auto* owner :
         {"MenuManager", "CollectionMenu", "SaveMenu", "MainMenu",
          "RoomTransition", "Ambush", "NightmareScene"}) {
        CreateGlobalOwnerTable(state, owner);
    }
    return 0;
}

#if !defined(__SWITCH__)
void SetRepentogonMenuWorldNativeTestBindings(
    RepentogonMenuWorldNativeTestBindings bindings) noexcept {
    g_TestBindings = bindings;
}
#endif

}  // namespace isaac::runtime
