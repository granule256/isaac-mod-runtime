#include "interfaces/lua/repentogon_menu_world_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/repentogon_entity_config_api.hpp"
#include "interfaces/lua/api100_native.hpp"
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
constexpr std::uintptr_t kRoomTransitionRoomIndex = 0x14;
constexpr std::uintptr_t kRoomTransitionBossIntroFlag = 0x3E8;
constexpr std::uintptr_t kGameStartingRoomIndex = 0x21514;
constexpr std::uintptr_t kGameAmbush = 0x26FAA8;
constexpr std::uintptr_t kAmbushCurrentWave = 0x3C;
// LoadConfig @ 0x42813c parses progressAnm2, loaded into this ANM2 @ 0x4285f0.
constexpr std::uintptr_t kNightmareProgressBarSprite = 0x2E8;
// NightmareScene::Render +0x84 forms this ANM2 and reads its animation state.
constexpr std::uintptr_t kNightmareBackgroundSprite = 0x38;
// Game::Render forms this PauseScreen; Show/Update write its leading state.
constexpr std::uintptr_t kGamePauseScreen = 0x1AE128;
constexpr std::uintptr_t kCompletionCounterId = 0x439844;
constexpr std::array<std::uint8_t, 16> kCompletionCounterIdGuard = {
    0x3f,0xa0,0x00,0x71,0x6d,0x00,0x00,0x54,
    0xe0,0x03,0x1f,0x2a,0xc0,0x03,0x5f,0xd6,
};
api100_native::Cache g_CompletionCounterIdCache{};

constexpr std::size_t kCompletionMarkCount = 15;
constexpr std::int32_t kMaximumCustomPlayerType = 255;
struct CustomCompletionMarkEntry {
    std::array<std::uint8_t, kCompletionMarkCount> marks{};
    bool valid{};
    bool tainted{};
};
std::array<CustomCompletionMarkEntry, kMaximumCustomPlayerType + 1>
    g_CustomCompletionMarks{};

constexpr std::array<std::int32_t, 12> kRenderedCompletionMarks = {
    12, 0, 1, 2, 3, 4, 5, 6, 7, 9, 13, 14};

[[nodiscard]] int CompletionMarkIndex(const char* key) noexcept {
    if (std::strcmp(key, "MOMS_HEART") == 0 ||
        std::strcmp(key, "MomsHeart") == 0)
        return 0;
    if (std::strcmp(key, "ISAAC") == 0 || std::strcmp(key, "Isaac") == 0)
        return 1;
    if (std::strcmp(key, "SATAN") == 0 || std::strcmp(key, "Satan") == 0)
        return 2;
    if (std::strcmp(key, "BOSS_RUSH") == 0 ||
        std::strcmp(key, "BossRush") == 0)
        return 3;
    if (std::strcmp(key, "BLUE_BABY") == 0 ||
        std::strcmp(key, "BlueBaby") == 0 ||
        std::strcmp(key, "???") == 0 || std::strcmp(key, "????") == 0)
        return 4;
    if (std::strcmp(key, "LAMB") == 0 || std::strcmp(key, "Lamb") == 0)
        return 5;
    if (std::strcmp(key, "MEGA_SATAN") == 0 ||
        std::strcmp(key, "MegaSatan") == 0)
        return 6;
    if (std::strcmp(key, "ULTRA_GREED") == 0 ||
        std::strcmp(key, "UltraGreed") == 0 ||
        std::strcmp(key, "Greed") == 0 || std::strcmp(key, "GREED") == 0)
        return 7;
    if (std::strcmp(key, "HUSH") == 0 || std::strcmp(key, "Hush") == 0)
        return 9;
    if (std::strcmp(key, "ULTRA_GREEDIER") == 0 ||
        std::strcmp(key, "UltraGreedier") == 0 ||
        std::strcmp(key, "GREEDIER") == 0 ||
        std::strcmp(key, "Greedier") == 0)
        return 11;
    if (std::strcmp(key, "DELIRIUM") == 0 ||
        std::strcmp(key, "Delirium") == 0)
        return 12;
    if (std::strcmp(key, "MOTHER") == 0 || std::strcmp(key, "Mother") == 0)
        return 13;
    if (std::strcmp(key, "BEAST") == 0 || std::strcmp(key, "Beast") == 0)
        return 14;
    return -1;
}

constexpr std::uintptr_t kRoomDescriptorDimension = 0x0C;
constexpr std::uintptr_t kRoomDescriptorTaintedKeeperCoinSpawns = 0x5E;

constexpr std::int32_t kMinimumMainMenu = 1;
constexpr std::int32_t kMaximumMainMenu = 22;

constexpr std::uintptr_t kStartBossIntroOffset = 0x4984c4;
constexpr std::array<std::uint8_t, 16> kStartBossIntroGuard = {
    0xff, 0x03, 0x03, 0xd1, 0xe8, 0x2b, 0x00, 0xfd,
    0xfd, 0x7b, 0x06, 0xa9, 0xfd, 0x83, 0x01, 0x91,
};
api100_native::Cache g_StartBossIntroCache{};

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
    // Upstream ignores the argument stack, including a colon-call's self.
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

int RepentogonMenuManagerGetViewPosition(lua_State* state) {
    RequireGameThread(state, "MenuManager.GetViewPosition");
    const auto menu = RequireMenuManager(state);
    const auto position = ReadField<Vector2>(
        state, menu, kMenuManagerViewPosition,
        "MenuManager view position is unavailable");
    PushLuaVector(state, position.x, position.y);
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

int RepentogonRoomTransitionStartBossIntro(lua_State* state) {
    RequireGameThread(state, "RoomTransition.StartBossIntro");
    const auto bossId1 = static_cast<std::uint32_t>(
        luaL_checkinteger(state, 1));
    const auto bossId2 = static_cast<std::uint32_t>(
        luaL_optinteger(state, 2, 0));
    const auto transition = RequireRoomTransition(state);
    const auto game = RequireGame(state);
    const auto startingRoom = ReadField<std::uint32_t>(
        state, game, kGameStartingRoomIndex,
        "Game starting room index is unavailable");
    if (!engine_memory::WriteField(
            transition, kRoomTransitionRoomIndex, startingRoom,
            engine_memory::EngineMemoryWritable)) {
        return luaL_error(state, "RoomTransition room index is not writable");
    }
    std::uintptr_t host{};
#if !defined(__SWITCH__)
    if (!g_TestBindings.startBossIntro) {
        return luaL_error(state,
                          "RoomTransition.StartBossIntro host binding is unavailable");
    }
    host = engine_call::AddressOfFunction(g_TestBindings.startBossIntro);
#endif
    using StartBossIntro = void (*)(void*, std::uint32_t, std::uint32_t);
    const auto start = engine_call::AsFunction<StartBossIntro>(
        api100_native::Resolve(state,
                               {kStartBossIntroOffset,
                                kStartBossIntroGuard.data()},
                               g_StartBossIntroCache, host));
    start(engine_memory::AsObject(transition), bossId1, bossId2);
    return 0;
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

int RepentogonNightmareSceneGetBackgroundSprite(lua_State* state) {
    RequireGameThread(state, "NightmareScene.GetBackgroundSprite");
    RequireNoArguments(state, "NightmareScene.GetBackgroundSprite");
    const auto manager = RequireManager(state);
    PushSceneSprite(state, manager + kManagerNightmareSceneOffset +
                        kNightmareBackgroundSprite,
                    "NightmareScene.GetBackgroundSprite");
    return 1;
}

int RepentogonGameIsPauseMenuOpen(lua_State* state) {
    RequireGameThread(state, "Game:IsPauseMenuOpen");
    luaL_checkudata(state, 1, LuaRuntime::kGameMetatable);
    if (lua_gettop(state) != 1)
        return luaL_error(state, "Game:IsPauseMenuOpen accepts no arguments");
    lua_pushboolean(state, ReadField<std::int32_t>(state, RequireGame(state),
        kGamePauseScreen, "PauseScreen state is unavailable") != 0);
    return 1;
}

namespace {

[[nodiscard]] std::int32_t ResolveCompletionCounterId(
    lua_State* state, std::int32_t event, std::int32_t player) {
    std::uintptr_t host{};
#if !defined(__SWITCH__)
    if (!g_TestBindings.completionCounterId)
        luaL_error(state, "Completion counter host binding is unavailable");
    host = engine_call::AddressOfFunction(g_TestBindings.completionCounterId);
#endif
    using CounterId = std::int32_t (*)(std::int32_t, std::int32_t);
    const auto counterId = engine_call::AsFunction<CounterId>(
        api100_native::Resolve(state, {kCompletionCounterId,
            kCompletionCounterIdGuard.data()}, g_CompletionCounterIdCache, host))(
                event, player);
    if (counterId < 0 || counterId > 522)
        luaL_error(state, "Completion event counter is invalid");
    return counterId;
}

void WriteNativeCompletionMark(
    lua_State* state, std::int32_t player, std::int32_t mark,
    std::uint8_t value) {
    const auto event = static_cast<std::int32_t>(mark == 11 ? 7 : mark);
    const auto counterId = ResolveCompletionCounterId(state, event, player);
    const auto manager = RequireManager(state);
    const auto offset = std::uintptr_t{0x18 + 0x2a8} +
                        static_cast<std::uintptr_t>(counterId) * 4;
    std::uint32_t current{};
    if (!engine_memory::ReadField(manager, offset, &current,
                                  engine_memory::EngineMemoryReadable))
        luaL_error(state, "Completion event counter is unavailable");
    current = (current & ~std::uint32_t{3}) | value;
    if (!engine_memory::WriteField(manager, offset, current,
                                   engine_memory::EngineMemoryWritable))
        luaL_error(state, "Completion event counter is not writable");
}

}  // namespace

bool RepentogonGetCustomCompletionMarks(
    int playerType, std::array<std::uint8_t, 15>* marks,
    bool* tainted) noexcept {
    if (playerType < 0 || playerType > kMaximumCustomPlayerType ||
        marks == nullptr || tainted == nullptr)
        return false;
    const auto& entry =
        g_CustomCompletionMarks[static_cast<std::size_t>(playerType)];
    if (!entry.valid) return false;
    *marks = entry.marks;
    *tainted = entry.tainted;
    return true;
}

bool RepentogonApplyCustomCompletionMarks(
    int playerType, std::uintptr_t sprite) noexcept {
    std::array<std::uint8_t, 15> marks{};
    bool tainted{};
    if (sprite == 0 || playerType <= 40 ||
        !RepentogonGetCustomCompletionMarks(playerType, &marks, &tainted))
        return false;
    const auto setLayerFrame = LuaRuntime::SpriteSetLayerFrameThunk();
    if (setLayerFrame == nullptr) return false;
    for (std::size_t layer = 0; layer < kRenderedCompletionMarks.size();
         ++layer) {
        const auto mark = kRenderedCompletionMarks[layer];
        auto frame = static_cast<int>(marks[static_cast<std::size_t>(mark)]);
        if (layer == 0 && tainted) frame += 5;
        setLayerFrame(engine_memory::AsObject(sprite),
                      static_cast<int>(layer), frame);
    }
    return true;
}

int RepentogonIsaacGetCompletionMark(lua_State* state) {
    RequireGameThread(state, "Isaac.GetCompletionMark");
    const auto player = luaL_checkinteger(state, 1);
    const auto mark = luaL_checkinteger(state, 2);
    if (player < 0 || player > kMaximumCustomPlayerType)
        return luaL_error(state, "Completion player type is invalid");
    if (mark < 0 || mark > 14 || mark == 8 || mark == 10)
        return luaL_error(state, "Unsupported CompletionType");
    if (player > 40) {
        std::array<std::uint8_t, 15> marks{};
        bool tainted{};
        if (RepentogonGetCustomCompletionMarks(
                static_cast<int>(player), &marks, &tainted))
            lua_pushinteger(state, marks[static_cast<std::size_t>(mark)]);
        else
            lua_pushinteger(state, 0);
        return 1;
    }
    // Greedier is stored in the hard Greed mark in the native NS profile.
    const auto event = static_cast<std::int32_t>(mark == 11 ? 7 : mark);
    const auto counterId = ResolveCompletionCounterId(
        state, event, static_cast<std::int32_t>(player));
    // CompletionWidget::Update reads Manager+0x18 (PGD), then +0x2a8+id*4.
    const auto value = ReadField<std::uint32_t>(state, RequireManager(state),
        0x18 + 0x2a8 + static_cast<std::uintptr_t>(counterId) * 4,
        "Completion event counter is unavailable") & 3U;
    lua_pushinteger(state, value);
    return 1;
}

int RepentogonIsaacSetCompletionMarks(lua_State* state) {
    RequireGameThread(state, "Isaac.SetCompletionMarks");
    luaL_checktype(state, 1, LUA_TTABLE);
    std::array<std::uint8_t, 15> marks{};
    std::int32_t playerType{};
    lua_pushnil(state);
    while (lua_next(state, 1) != 0) {
        if (lua_type(state, -2) == LUA_TSTRING) {
            const char* key = lua_tostring(state, -2);
            const auto value =
                static_cast<std::int32_t>(lua_tointeger(state, -1));
            if (std::strcmp(key, "PlayerType") == 0) {
                playerType = value;
            } else {
                const auto mark = CompletionMarkIndex(key);
                if (mark < 0)
                    return luaL_error(
                        state, "Invalid Completion Marks table index: %s",
                        key);
                if (value < 0 || value > 2)
                    return luaL_error(
                        state, "Invalid Completion Marks value for %s: %d",
                        key, static_cast<int>(value));
                marks[static_cast<std::size_t>(mark)] =
                    static_cast<std::uint8_t>(value);
            }
        }
        lua_pop(state, 1);
    }
    if (playerType < 0 || playerType > kMaximumCustomPlayerType)
        return luaL_error(state, "Invalid Player Type");
    if (marks[7] == 2) marks[11] = 2;
    if (marks[11] > 0) marks[7] = 2;
    if (playerType > 40) {
        auto& entry =
            g_CustomCompletionMarks[static_cast<std::size_t>(playerType)];
        entry.marks = marks;
        entry.valid = true;
        bool tainted = false;
        entry.tainted =
            RepentogonEntityConfigPlayerTaintedByType(playerType, &tainted) &&
            tainted;
        return 0;
    }
    for (std::int32_t mark = 0; mark < 15; ++mark) {
        if (mark == 8 || mark == 10 || mark == 11) continue;
        WriteNativeCompletionMark(state, playerType, mark,
                                  marks[static_cast<std::size_t>(mark)]);
    }
    return 0;
}

int RepentogonNightmareSceneGetProgressBarSprite(lua_State* state) {
    RequireGameThread(state, "NightmareScene.GetProgressBarSprite");
    const auto manager = RequireManager(state);
    if (manager > UINTPTR_MAX - kManagerNightmareSceneOffset - kNightmareProgressBarSprite) {
        return luaL_error(state, "NightmareScene progress sprite is unavailable");
    }
    PushSceneSprite(state, manager + kManagerNightmareSceneOffset + kNightmareProgressBarSprite,
                    "NightmareScene.GetProgressBarSprite");
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
    const auto manager = TryReadSingleton(kGameManagerGlobalSlotOffset);
    if (manager && manager<=UINTPTR_MAX-0x2d338-0x40 &&
        sprite==manager+0x2d338+0x40) return true;
    if (manager != 0 && manager <= UINTPTR_MAX - kManagerNightmareSceneOffset -
        kNightmareProgressBarSprite &&
        (sprite == manager + kManagerNightmareSceneOffset + kNightmareProgressBarSprite ||
         sprite == manager + kManagerNightmareSceneOffset + kNightmareBackgroundSprite)) {
        return true;
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
    if (game && game<=UINTPTR_MAX-0x25db0-0x1488 &&
        (sprite==game+0x25db0+8 || sprite==game+0x25db0+0x1488)) return true;
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
