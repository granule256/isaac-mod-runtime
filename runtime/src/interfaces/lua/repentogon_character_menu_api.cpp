#include "interfaces/lua/repentogon_character_menu_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/repentogon_callbacks.hpp"
#include "interfaces/lua/repentogon_color_modifier_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstdint>
#include <cstring>
#include <limits>

extern "C" {
#include "lauxlib.h"
}

namespace isaac::runtime {
namespace {

// Pinned NS image 91C73FDD575061318D68886316AFEAC72388B2AB.
// Menu_Character is embedded at MenuManager+0x1A2658 (MenuManager::Render
// passes exactly that address to Menu_Character::Render).
constexpr std::uintptr_t kMenuManagerSlot = 0xAAD1B0;
constexpr std::uintptr_t kMenuCharacterOffset = 0x1A2658;
constexpr std::uintptr_t kCharacterStatus = 0x38;
constexpr std::uintptr_t kCharacterUnlocked = 0x3D;
constexpr std::uintptr_t kCharacterDifficulty = 0x40;
constexpr std::uintptr_t kCharacterSelectedId = 0x48;
constexpr std::uintptr_t kCharacterBigCharPage = 0x78;
constexpr std::uintptr_t kCharacterShownPage = 0x1138;
constexpr std::uintptr_t kCharacterPageSwapWidget = 0x1140;
constexpr std::uintptr_t kCharacterCompletionWidget = 0x5D8;
constexpr std::uintptr_t kCompletionWidgetAnm2 = 0x08;
constexpr std::uintptr_t kCharacterModMap = 0x1400;

// Menu_Character::get_playertype_from_selection reads this table for vanilla
// ids: page * 0x240 + characterId * 0x20 + 8.
constexpr std::uintptr_t kVanillaPlayerTable = 0xA38840;
constexpr std::uintptr_t kVanillaPageStride = 0x240;
constexpr std::uintptr_t kVanillaEntryStride = 0x20;
constexpr std::uintptr_t kVanillaPlayerType = 0x08;

#if defined(__SWITCH__)
constexpr std::uintptr_t kSelectedPlayerTypeOffset = 0x4063CC;
constexpr std::array<std::uint8_t, 16> kSelectedPlayerTypeGuard = {
    0x28, 0x48, 0x00, 0x71, 0xeb, 0x00, 0x00, 0x54,
    0x09, 0x00, 0x4a, 0xf9, 0x28, 0x4d, 0x28, 0x8b,
};

constexpr std::uintptr_t kSetColorModifierOffset = 0x3FF9B8;
constexpr std::array<std::uint8_t, 16> kSetColorModifierGuard = {
    0x2d, 0x08, 0x40, 0xf9, 0x89, 0xf7, 0x9f, 0x52,
    0x49, 0x03, 0xa0, 0x72, 0x2b, 0x30, 0x40, 0xa9,
};

api100_native::Cache g_SelectedPlayerTypeCache{};
api100_native::Cache g_SetColorModifierCache{};
#endif

std::uint32_t g_InputMask = 0xFFFFFFFFu;
bool g_InputMaskEnabled = false;
bool g_InputMaskSuspended = false;

#if !defined(__SWITCH__)
RepentogonCharacterMenuNativeTestBindings g_TestBindings{};
#endif

[[nodiscard]] std::uintptr_t TryReadSingleton(
    std::uintptr_t slotOffset) noexcept {
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

void RequireGameThread(lua_State* state, const char* api) {
    if (!LuaRuntime::IsOnGameThread()) {
        luaL_error(state, "%s requires the game thread", api);
    }
}

[[nodiscard]] std::uintptr_t RequireMenuManager(lua_State* state) {
    const auto menu = TryReadSingleton(kMenuManagerSlot);
    if (menu == 0) {
        luaL_error(state, "MenuManager is unavailable");
    }
    return menu;
}

[[nodiscard]] std::uintptr_t RequireCharacterMenu(lua_State* state) {
    const auto menu = RequireMenuManager(state);
    if (menu > UINTPTR_MAX - kMenuCharacterOffset) {
        luaL_error(state, "CharacterMenu is unavailable");
    }
    const auto character = menu + kMenuCharacterOffset;
    if (!engine_memory::EngineMemoryReadable(character,
                                             kCharacterModMap + 0x18)) {
        luaL_error(state, "CharacterMenu is unavailable");
    }
    return character;
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

void PushSceneSprite(lua_State* state, std::uintptr_t sprite,
                     const char* api) {
    if (sprite == 0 ||
        !engine_memory::EngineMemoryReadable(sprite, kSpriteObjectSize)) {
        luaL_error(state, "%s sprite is unavailable", api);
    }
    if (!repentogon::HasSpriteValidator() ||
        !repentogon::CallbackSpriteAlive(sprite)) {
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

[[nodiscard]] bool ReadModPlayerType(lua_State* state, std::uintptr_t menu,
                                     std::int32_t characterId, bool tainted,
                                     std::int32_t* out) {
    if (out == nullptr || characterId < 18) return false;
    std::uintptr_t begin{};
    std::uintptr_t end{};
    if (!engine_memory::ReadField(menu, kCharacterModMap,
                                  &begin,
                                  engine_memory::EngineMemoryReadable) ||
        !engine_memory::ReadField(menu, kCharacterModMap + 0x08,
                                  &end,
                                  engine_memory::EngineMemoryReadable) ||
        begin == 0 || end < begin || ((end - begin) & 7U) != 0) {
        luaL_error(state, "CharacterMenu mod character map is unavailable");
    }
    const auto index = static_cast<std::uintptr_t>(characterId - 18);
    const auto count = (end - begin) / sizeof(std::uint64_t);
    if (index >= count) return false;
    if (index > (UINTPTR_MAX - begin) / sizeof(std::uint64_t)) return false;
    const auto address = begin + index * sizeof(std::uint64_t) +
                         (tainted ? sizeof(std::int32_t) : 0U);
    if (!engine_memory::ReadAt(address, out,
                               engine_memory::EngineMemoryReadable)) {
        luaL_error(state, "CharacterMenu mod character entry is unavailable");
    }
    return true;
}

}  // namespace

int RepentogonCharacterMenuGetActiveStatus(lua_State* state) {
    RequireGameThread(state, "CharacterMenu.GetActiveStatus");
    const auto character = RequireCharacterMenu(state);
    lua_pushinteger(
        state,
        static_cast<lua_Integer>(ReadField<std::int32_t>(
            state, character, kCharacterStatus,
            "CharacterMenu status is unavailable")));
    return 1;
}

int RepentogonCharacterMenuGetDifficulty(lua_State* state) {
    RequireGameThread(state, "CharacterMenu.GetDifficulty");
    const auto character = RequireCharacterMenu(state);
    lua_pushinteger(
        state,
        static_cast<lua_Integer>(ReadField<std::int32_t>(
            state, character, kCharacterDifficulty,
            "CharacterMenu difficulty is unavailable")));
    return 1;
}

int RepentogonCharacterMenuGetIsCharacterUnlocked(lua_State* state) {
    RequireGameThread(state, "CharacterMenu.GetIsCharacterUnlocked");
    const auto character = RequireCharacterMenu(state);
    lua_pushboolean(
        state,
        ReadField<std::uint8_t>(
            state, character, kCharacterUnlocked,
            "CharacterMenu unlock state is unavailable") != 0);
    return 1;
}

int RepentogonCharacterMenuGetPageSwapWidgetSprite(lua_State* state) {
    RequireGameThread(state, "CharacterMenu.GetPageSwapWidgetSprite");
    const auto character = RequireCharacterMenu(state);
    PushSceneSprite(state, character + kCharacterPageSwapWidget,
                    "CharacterMenu.GetPageSwapWidgetSprite");
    return 1;
}

int RepentogonCharacterMenuGetSelectedCharacterID(lua_State* state) {
    RequireGameThread(state, "CharacterMenu.GetSelectedCharacterID");
    const auto character = RequireCharacterMenu(state);
    lua_pushinteger(
        state,
        static_cast<lua_Integer>(ReadField<std::int32_t>(
            state, character, kCharacterSelectedId,
            "CharacterMenu selected id is unavailable")));
    return 1;
}

int RepentogonCharacterMenuGetSelectedCharacterMenu(lua_State* state) {
    RequireGameThread(state, "CharacterMenu.GetSelectedCharacterMenu");
    const auto character = RequireCharacterMenu(state);
    lua_pushinteger(
        state,
        static_cast<lua_Integer>(ReadField<std::int32_t>(
            state, character, kCharacterShownPage,
            "CharacterMenu selected page is unavailable")));
    return 1;
}

int RepentogonCharacterMenuGetSelectedCharacterPlayerType(lua_State* state) {
    RequireGameThread(state,
                      "CharacterMenu.GetSelectedCharacterPlayerType");
    const auto character = RequireCharacterMenu(state);
    const auto selectedId = ReadField<std::int32_t>(
        state, character, kCharacterSelectedId,
        "CharacterMenu selected id is unavailable");
    std::int32_t playerType = -1;
#if defined(__SWITCH__)
    using SelectedPlayerType = std::int32_t (*)(const void*, std::int32_t);
    const auto method = api100_native::Resolve(
        state, {kSelectedPlayerTypeOffset, kSelectedPlayerTypeGuard.data()},
        g_SelectedPlayerTypeCache, 0);
    if (method == 0) {
        return luaL_error(
            state,
            "CharacterMenu.GetSelectedCharacterPlayerType native binding is unavailable");
    }
    playerType = engine_call::AsFunction<SelectedPlayerType>(method)(
        engine_memory::AsObject(character), selectedId);
#else
    if (g_TestBindings.selectedPlayerType == nullptr) {
        return luaL_error(
            state,
            "CharacterMenu.GetSelectedCharacterPlayerType host binding is unavailable");
    }
    playerType = g_TestBindings.selectedPlayerType(
        engine_memory::AsObject(character), selectedId);
#endif
    if (playerType < 0) {
        lua_pushnil(state);
    } else {
        lua_pushinteger(state, static_cast<lua_Integer>(playerType));
    }
    return 1;
}

int RepentogonCharacterMenuGetPlayerTypeFromCharacterMenuID(
    lua_State* state) {
    RequireGameThread(state,
                      "CharacterMenu.GetPlayerTypeFromCharacterMenuID");
    const auto rawId =
        static_cast<std::int64_t>(luaL_checkinteger(state, 1));
    const auto character = RequireCharacterMenu(state);
    const bool tainted =
        lua_isnoneornil(state, 2)
            ? ReadField<std::int32_t>(
                  state, character, kCharacterShownPage,
                  "CharacterMenu selected page is unavailable") == 1
            : lua_toboolean(state, 2) != 0;

    std::int32_t playerType = -1;
    bool found = false;
    if (rawId >= 0 && rawId < 18) {
        const auto base = LuaRuntime::EngineModuleBase();
        if (base == 0 ||
            base > UINTPTR_MAX - kVanillaPlayerTable - kVanillaPageStride) {
            return luaL_error(state,
                              "CharacterMenu player table is unavailable");
        }
        const auto address =
            base + kVanillaPlayerTable +
            (tainted ? kVanillaPageStride : 0U) +
            static_cast<std::uintptr_t>(rawId) * kVanillaEntryStride +
            kVanillaPlayerType;
        found = engine_memory::ReadAt(
            address, &playerType, engine_memory::EngineMemoryReadable);
        if (!found) {
            return luaL_error(state,
                              "CharacterMenu player table is unavailable");
        }
    } else if (rawId >= 18 &&
               rawId <= std::numeric_limits<std::int32_t>::max()) {
        found = ReadModPlayerType(
            state, character, static_cast<std::int32_t>(rawId), tainted,
            &playerType);
    }
    if (!found || playerType < 0) {
        lua_pushnil(state);
    } else {
        lua_pushinteger(state, static_cast<lua_Integer>(playerType));
    }
    return 1;
}

int RepentogonMenuManagerSetInputMask(lua_State* state) {
    RequireGameThread(state, "MenuManager.SetInputMask");
    static_cast<void>(RequireMenuManager(state));
    g_InputMask =
        static_cast<std::uint32_t>(luaL_checkinteger(state, 1));
    g_InputMaskEnabled = true;
    return 0;
}

bool RepentogonMenuManagerInputMaskAllows(
    std::uint32_t buttonAction) noexcept {
    if (!g_InputMaskEnabled || g_InputMaskSuspended) return true;
    return buttonAction < 32 &&
           (g_InputMask & (std::uint32_t{1} << buttonAction)) != 0;
}

bool RepentogonMenuManagerInputMaskActive() noexcept {
    return g_InputMaskEnabled && !g_InputMaskSuspended;
}

void BeginRepentogonMainMenuRenderInputMaskScope() noexcept {
    g_InputMaskSuspended = true;
}

void EndRepentogonMainMenuRenderInputMaskScope() noexcept {
    // Upstream leaves the mask disabled while MenuManager bit 8 reports a
    // scene transition. Every other main-menu render restores filtering.
    std::int32_t state{};
    const auto menu = TryReadSingleton(kMenuManagerSlot);
    g_InputMaskSuspended =
        menu != 0 &&
        engine_memory::ReadField(menu, 0x38, &state,
                                 engine_memory::EngineMemoryReadable) &&
        (state & 0x100) != 0;
}

void ClearRepentogonMenuInputMask() noexcept {
    g_InputMask = 0xFFFFFFFFu;
    g_InputMaskEnabled = false;
    g_InputMaskSuspended = false;
}

int RepentogonMenuManagerSetColorModifier(lua_State* state) {
    RequireGameThread(state, "MenuManager.SetColorModifier");
    const auto menu = RequireMenuManager(state);
    const auto* modifier = RequireRepentogonColorModifierArgument(state, 1);
    const bool lerp =
        lua_isnoneornil(state, 2) ? true : lua_toboolean(state, 2) != 0;
    const float rate = static_cast<float>(
        lua_isnoneornil(state, 3) ? 0.015 : luaL_checknumber(state, 3));
#if defined(__SWITCH__)
    using SetColorModifier = void (*)(void*, const void*, bool, float);
    const auto method = api100_native::Resolve(
        state, {kSetColorModifierOffset, kSetColorModifierGuard.data()},
        g_SetColorModifierCache, 0);
    if (method == 0) {
        return luaL_error(
            state, "MenuManager.SetColorModifier native binding is unavailable");
    }
    engine_call::AsFunction<SetColorModifier>(method)(
        engine_memory::AsObject(menu), modifier, lerp, rate);
#else
    if (g_TestBindings.menuSetColorModifier == nullptr) {
        return luaL_error(
            state, "MenuManager.SetColorModifier host binding is unavailable");
    }
    g_TestBindings.menuSetColorModifier(
        engine_memory::AsObject(menu), modifier, lerp, rate);
#endif
    return 0;
}

bool RepentogonCharacterMenuSpriteAlive(std::uintptr_t sprite) noexcept {
    if (sprite == 0 ||
        !engine_memory::EngineMemoryReadable(sprite, kSpriteObjectSize)) {
        return false;
    }
    const auto menu = TryReadSingleton(kMenuManagerSlot);
    if (menu == 0 || menu > UINTPTR_MAX - kMenuCharacterOffset) return false;
    const auto character = menu + kMenuCharacterOffset;
    if (character > UINTPTR_MAX - kCharacterPageSwapWidget &&
        character > UINTPTR_MAX - kCharacterCompletionWidget) {
        return false;
    }
    return sprite == character + kCharacterBigCharPage ||
           sprite == character + kCharacterPageSwapWidget ||
           sprite == character + kCharacterCompletionWidget +
                         kCompletionWidgetAnm2;
}

bool DispatchRepentogonPreCompletionMarksRender(
    std::uintptr_t sprite, const void* renderPos, const void* renderScale,
    std::int32_t playerType) noexcept {
    if (!repentogon::Listening(1216)) return false;
    const auto result = repentogon::Dispatch(
        {1216, repentogon::EventKind::Global, sprite,
         engine_memory::AddressOf(renderPos),
         static_cast<const repentogon::Vector*>(renderScale), false, nullptr,
         playerType});
    // Upstream treats either boolean result as cancellation; nil/non-boolean renders.
    return result.hasBoolean;
}

void DispatchRepentogonPostCompletionMarksRender(
    std::uintptr_t sprite, const void* renderPos, const void* renderScale,
    std::int32_t playerType) noexcept {
    if (!repentogon::Listening(1217)) return;
    static_cast<void>(repentogon::Dispatch(
        {1217, repentogon::EventKind::Global, sprite,
         engine_memory::AddressOf(renderPos),
         static_cast<const repentogon::Vector*>(renderScale), false, nullptr,
         playerType}));
}

void DispatchRepentogonPreRenderCustomCharacterMenu(
    std::int32_t playerType, const void* renderPos,
    std::uintptr_t vanillaSprite) noexcept {
    if (!repentogon::Listening(1333)) return;
    static_cast<void>(repentogon::Dispatch(
        {1333, repentogon::EventKind::Global, vanillaSprite,
         engine_memory::AddressOf(renderPos), nullptr, false, nullptr,
         playerType}));
}

void DispatchRepentogonPostRoomTransitionUpdate(
    std::int32_t transitionMode) noexcept {
    if (!repentogon::Listening(1271)) return;
    static_cast<void>(repentogon::Dispatch(
        {1271, repentogon::EventKind::Global, 0, 0, nullptr, false, nullptr,
         transitionMode}));
}

int RegisterRepentogonCharacterMenuApi(lua_State* state) {
    if (state == nullptr) return 0;
    CreateGlobalOwnerTable(state, "CharacterMenu");
    CreateGlobalOwnerTable(state, "MenuManager");
    return 0;
}

#if !defined(__SWITCH__)
void SetRepentogonCharacterMenuNativeTestBindings(
    RepentogonCharacterMenuNativeTestBindings bindings) noexcept {
    g_TestBindings = bindings;
}
#endif

}  // namespace isaac::runtime
