"""REPENTOGON menu/world STATIC APIs use validated Switch layouts and native calls."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

PUBLIC_ROOT = Path(__file__).resolve().parents[2]
SOURCE = PUBLIC_ROOT / "runtime" / "source"
EXTRA_SOURCE = (
    PUBLIC_ROOT
    / "runtime"
    / "src"
    / "interfaces"
    / "lua"
    / "repentogon_menu_world_api.cpp"
)

DRIVER = PREFIX + r'''
#include "interfaces/lua/repentogon_menu_world_api.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "runtime_constants.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"

#include <array>
#include <vector>

namespace {

constexpr std::uintptr_t kMenuManagerSlot = 0xAAD1B0;
constexpr std::uintptr_t kGameRoomTransition = 0x25810;
constexpr std::uintptr_t kGameStartingRoomIndex = 0x21514;
constexpr std::uintptr_t kGameAmbush = 0x26FAA8;
constexpr std::uintptr_t kMenuSavePage = 0x7D8;
constexpr std::uintptr_t kMenuSaveDeletePopup = 0x6E0;
constexpr std::uintptr_t kMenuGamePage = 0x813A0;
constexpr std::uintptr_t kMenuGameContinueWidget = 0x168;
constexpr std::uintptr_t kMenuCollectionPage = 0x1A3DA8;
constexpr std::uintptr_t kMenuViewPosition = 0x3C;
constexpr std::uintptr_t kMenuViewPositionSet = 0x1AFF08;

template <class T>
void Put(std::vector<unsigned char>& bytes, std::uintptr_t offset, T value) {
    assert(offset + sizeof(value) <= bytes.size());
    std::memcpy(bytes.data() + offset, &value, sizeof(value));
}

template <class T>
T Read(const std::vector<unsigned char>& bytes, std::uintptr_t offset) {
    T value{};
    assert(offset + sizeof(value) <= bytes.size());
    std::memcpy(&value, bytes.data() + offset, sizeof(value));
    return value;
}

std::uintptr_t Address(const std::vector<unsigned char>& bytes) {
    return reinterpret_cast<std::uintptr_t>(bytes.data());
}

void Bind(lua_State* state, const char* table, const char* name, lua_CFunction function) {
    lua_getglobal(state, table);
    assert(lua_istable(state, -1));
    lua_pushcfunction(state, function);
    lua_setfield(state, -2, name);
    lua_pop(state, 1);
}

}  // namespace

static std::vector<unsigned char> moduleBytes;
static std::vector<unsigned char> gameSlot;
static std::vector<unsigned char> managerSlot;
static std::vector<unsigned char> menuSlot;
static std::vector<unsigned char> game;
static std::vector<unsigned char> manager;
static std::vector<unsigned char> menuManager;
static std::vector<unsigned char> room;
static std::vector<unsigned char> descriptor;
static bool renderingBossIntro = true;
static unsigned startBossIntroCalls;
static std::uint32_t lastBossId1;
static std::uint32_t lastBossId2;
static std::array<int, 12> completionFrames{};
static std::uintptr_t completionSprite{};

static void SetCompletionLayerFrame(void* sprite, int layer, int frame) {
    assert(layer >= 0 && layer < 12);
    completionSprite = reinterpret_cast<std::uintptr_t>(sprite);
    completionFrames[static_cast<std::size_t>(layer)] = frame;
}

static bool RenderingBossIntro(const void* transition) {
    assert(reinterpret_cast<std::uintptr_t>(transition) ==
           Address(game) + kGameRoomTransition);
    return renderingBossIntro;
}

static void StartBossIntro(void* transition, std::uint32_t bossId1,
                           std::uint32_t bossId2) {
    assert(reinterpret_cast<std::uintptr_t>(transition) ==
           Address(game) + kGameRoomTransition);
    assert(Read<std::int32_t>(game, kGameRoomTransition + 0x14) == 17);
    if (startBossIntroCalls == 0) {
        assert(bossId1 == 42 && bossId2 == 0);
    }
    lastBossId1 = bossId1;
    lastBossId2 = bossId2;
    ++startBossIntroCalls;
}

static int SetPauseState(lua_State* state) {
    Put<std::int32_t>(game, 0x1AE128, static_cast<int>(luaL_checkinteger(state,1)));
    return 0;
}
static std::int32_t CompletionCounterId(std::int32_t event, std::int32_t player) {
    assert(event >= 0 && event <= 14 && player >= 0 && player <= 40);
    return player == 40 ? 490 : player == 39 ? 634 : 100 + player + event;
}
static int ClearCompletionPort(lua_State*) {
    isaac::runtime::SetRepentogonMenuWorldNativeTestBindings({});return 0;
}
static void Extensions(lua_State* state) noexcept {
    lua_pushcfunction(state, SetPauseState);lua_setglobal(state, "_pause");
    lua_pushcfunction(state, ClearCompletionPort);lua_setglobal(state, "_clearCompletionPort");
    assert(isaac::runtime::RegisterRepentogonMenuWorldApi(state) == 0);

    Bind(state, "MenuManager", "GetActiveMenu",
         isaac::runtime::RepentogonMenuManagerGetActiveMenu);
    Bind(state, "MenuManager", "IsActive",
         isaac::runtime::RepentogonMenuManagerIsActive);
    Bind(state, "MenuManager", "GetViewPosition",
         isaac::runtime::RepentogonMenuManagerGetViewPosition);
    Bind(state, "CollectionMenu", "GetSelectedPage",
         isaac::runtime::RepentogonCollectionMenuGetSelectedPage);
    Bind(state, "CollectionMenu", "GetSelectedElement",
         isaac::runtime::RepentogonCollectionMenuGetSelectedElement);
    Bind(state, "SaveMenu", "GetDeletePopupSprite",
         isaac::runtime::RepentogonSaveMenuGetDeletePopupSprite);
    Bind(state, "MainMenu", "GetContinueWidgetSprite",
         isaac::runtime::RepentogonMainMenuGetContinueWidgetSprite);
    Bind(state, "RoomTransition", "IsRenderingBossIntro",
         isaac::runtime::RepentogonRoomTransitionIsRenderingBossIntro);
    Bind(state, "RoomTransition", "StartBossIntro",
         isaac::runtime::RepentogonRoomTransitionStartBossIntro);
    Bind(state, "RoomTransition", "GetVersusScreenSprite",
         isaac::runtime::RepentogonRoomTransitionGetVersusScreenSprite);
    Bind(state, "Ambush", "GetCurrentWave",
         isaac::runtime::RepentogonAmbushGetCurrentWave);
    Bind(state, "NightmareScene", "IsDogmaNightmare",
         isaac::runtime::RepentogonNightmareSceneIsDogmaNightmare);

    Bind(state, "Isaac", "WorldToMenuPosition",
         isaac::runtime::RepentogonWorldToMenuPosition);
    Bind(state, "Isaac", "SetCompletionMarks",
         isaac::runtime::RepentogonIsaacSetCompletionMarks);

    auto* handle = static_cast<LuaRuntime::RoomDescriptorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RoomDescriptorHandle)));
    handle->descriptor =
        isaac::runtime::engine_memory::AsObject(Address(descriptor));
    handle->level = isaac::runtime::engine_memory::AsObject(Address(game));
    handle->moduleBase = LuaRuntime::EngineModuleBase();
    luaL_getmetatable(state, LuaRuntime::kRoomDescriptorMetatable);
    lua_setmetatable(state, -2);
    lua_setglobal(state, "roomDesc");
}

int main() {
    moduleBytes.assign(kMenuManagerSlot + sizeof(std::uintptr_t), 0);
    gameSlot.assign(sizeof(std::uintptr_t), 0);
    managerSlot.assign(sizeof(std::uintptr_t), 0);
    menuSlot.assign(sizeof(std::uintptr_t), 0);
    game.assign(0x26FB00, 0);
    manager.assign(0x2D200, 0);
    menuManager.assign(0x1B0000, 0);
    room.assign(0x40, 0);
    descriptor.assign(0x100, 0);

    Put<std::uintptr_t>(gameSlot, 0, Address(game));
    Put<std::uintptr_t>(managerSlot, 0, Address(manager));
    Put<std::uintptr_t>(menuSlot, 0, Address(menuManager));
    Put<std::uintptr_t>(moduleBytes, kGameOwnerGlobalSlotOffset,
                        Address(gameSlot));
    Put<std::uintptr_t>(moduleBytes, kGameManagerGlobalSlotOffset,
                        Address(managerSlot));
    Put<std::uintptr_t>(moduleBytes, kMenuManagerSlot, Address(menuSlot));

    Put<std::uintptr_t>(game, kGameRoomPointerOffset, Address(room));
    Put<std::uint32_t>(game, kLevelCurrentRoomIndexOffset, 3);
    Put<std::uint32_t>(game, kLevelCurrentRoomDimensionOffset, 0);
    Put<std::uintptr_t>(room, kRoomDescriptorPointerOffset,
                        Address(descriptor));
    Put<std::uint32_t>(descriptor, 0x08, 3);
    Put<std::uint32_t>(descriptor, 0x0C, 1);
    Put<std::int16_t>(descriptor, 0x5E, 10);

    Put<std::int32_t>(menuManager, 0x38, 8);
    Put<float>(menuManager, kMenuViewPosition, 100.0F);
    Put<float>(menuManager, kMenuViewPosition + 4, 200.0F);
    Put<float>(menuManager, kMenuViewPositionSet + 8 * 8, 10.0F);
    Put<float>(menuManager, kMenuViewPositionSet + 8 * 8 + 4, 20.0F);
    Put<std::int32_t>(menuManager, kMenuCollectionPage + 0x04, 2);
    Put<std::int32_t>(menuManager, kMenuCollectionPage + 0x10, 11);
    Put<std::uint32_t>(game, kGameRoomTransition, 2);
    Put<std::uint32_t>(game, kGameStartingRoomIndex, 17);
    Put<std::uint8_t>(game, kGameRoomTransition + 0x3E8, 1);
    Put<std::int32_t>(game, kGameAmbush + 0x3C, 5);
    Put<std::uint8_t>(manager, kManagerNightmareSceneOffset + 0x5E8, 1);
    const unsigned char startBossIntroGuard[] = {
        0xff, 0x03, 0x03, 0xd1, 0xe8, 0x2b, 0x00, 0xfd,
        0xfd, 0x7b, 0x06, 0xa9, 0xfd, 0x83, 0x01, 0x91,
    };
    std::memcpy(moduleBytes.data() + 0x4984c4, startBossIntroGuard,
                sizeof(startBossIntroGuard));

    const unsigned char completionGuard[] = {
        0x3f,0xa0,0x00,0x71,0x6d,0x00,0x00,0x54,
        0xe0,0x03,0x1f,0x2a,0xc0,0x03,0x5f,0xd6};
    std::memcpy(moduleBytes.data()+0x439844,completionGuard,16);
    Put<std::uint32_t>(manager,0x18+0x2a8+(100+21+12)*4,6);
    Put<std::uint32_t>(manager,0x18+0x2a8+(100+0+7)*4,1);
    Put<std::uint32_t>(manager,0x18+0x2a8+490*4,2);
    LuaRuntime::SetEngineModuleBase(Address(moduleBytes));
    LuaRuntime::SetGameBindings(
        Address(moduleBytes) + kGameOwnerGlobalSlotOffset, 0);
    LuaRuntime::LuaSpriteBindings spriteBindings{};
    spriteBindings.setLayerFrame = &SetCompletionLayerFrame;
    LuaRuntime::SetSpriteBindings(spriteBindings);
    LuaRuntime::ObserveGameThread();
    Files files(true);
    SetSessionSaveFilePort(&files);
    const isaac::runtime::repentogon::NativePort port{
        Ready, Ready, isaac::runtime::RepentogonMenuWorldSpriteAlive};
    isaac::runtime::repentogon::SetNativePort(&port);
    isaac::runtime::SetRepentogonMenuWorldNativeTestBindings(
        {RenderingBossIntro, StartBossIntro, CompletionCounterId});
    LuaRuntime::SetRuntimeExtensionInstaller(Extensions);

    constexpr const char* script = R"lua(
assert(type(Isaac.GetCompletionMark) == 'function', 'missing completion marks')
assert(type(Game().IsPauseMenuOpen) == 'function', 'missing pause-menu state')
assert(not Game():IsPauseMenuOpen())
_pause(1);assert(Game():IsPauseMenuOpen() and PauseMenu.GetState()==1)
_pause(2);assert(Game():IsPauseMenuOpen() and PauseMenu.GetState()==2)
local pauseSprites = {PauseMenu.GetSprite(), PauseMenu.GetStatsSprite(),
    PauseMenu.GetMyStuffSprite(), PauseMenu.GetCompletionMarksSprite()}
for i, sprite in ipairs(pauseSprites) do
    assert(type(sprite)=='userdata')
    for j=1,i-1 do assert(sprite ~= pauseSprites[j]) end
end
_pause(0);assert(not Game():IsPauseMenuOpen() and PauseMenu.GetState()==0)
assert(not pcall(function() Game().IsPauseMenuOpen({}) end))
assert(Isaac.GetCompletionMark(21,12)==2, 'offline mark must exclude online bits')
assert(Isaac.GetCompletionMark(0,11)==1, 'Greedier shares the offline event value')
assert(Isaac.GetCompletionMark(40,12)==2, 'native counter490 is valid')
assert(not pcall(Isaac.GetCompletionMark,39,12))
assert(Isaac.GetCompletionMark(1,12)==0)
assert(Isaac.GetCompletionMark(41,12)==0)
assert(not pcall(Isaac.GetCompletionMark,-1,12))
assert(not pcall(Isaac.GetCompletionMark,0,8))
assert(type(Isaac.SetCompletionMarks) == 'function', 'missing completion setter')
Isaac.SetCompletionMarks({
    PlayerType=41, MomsHeart=2, Isaac=1, Satan=1, BossRush=2,
    BlueBaby=1, Lamb=1, MegaSatan=2, UltraGreed=1, Hush=2,
    Delirium=1, Mother=2, Beast=1,
})
assert(Isaac.GetCompletionMark(41,0)==2)
assert(Isaac.GetCompletionMark(41,3)==2)
assert(Isaac.GetCompletionMark(41,12)==1)
assert(Isaac.GetCompletionMark(41,14)==1)
assert(Isaac.GetCompletionMark(42,0)==0)
assert(not pcall(Isaac.SetCompletionMarks, nil))
assert(not pcall(Isaac.SetCompletionMarks, {PlayerType=41, MomsHeart=3}))
assert(not pcall(Isaac.SetCompletionMarks, {PlayerType=41, Unknown=1}))
assert(type(NightmareScene.GetBackgroundSprite) == 'function', 'missing nightmare background')
assert(type(NightmareScene.GetBackgroundSprite()) == 'userdata')
assert(type(NightmareScene.GetProgressBarSprite()) == 'userdata')
assert(type(MenuManager) == 'table')
assert(MenuManager.IsActive())
local viewPosition = MenuManager.GetViewPosition()
assert(type(viewPosition) == 'userdata')
assert(viewPosition.X == 100 and viewPosition.Y == 200)
local colonViewPosition = MenuManager:GetViewPosition()
assert(colonViewPosition.X == 100 and colonViewPosition.Y == 200)
assert(MenuManager.GetViewPosition('ignored').X == 100)
assert(MenuManager.GetActiveMenu() == 8)
assert(MenuManager:GetActiveMenu() == 8)
assert(MenuManager.GetActiveMenu('ignored', 42) == 8)

local pos = Isaac.WorldToMenuPosition(8, Vector(3, 4))
assert(pos.X == 132 and pos.Y == 199, tostring(pos.X) .. ',' .. tostring(pos.Y))
local wrapped = Isaac.WorldToMenuPosition(4294967304, Vector(3, 4))
assert(wrapped.X == pos.X and wrapped.Y == pos.Y)
assert(not pcall(function() Isaac.WorldToMenuPosition(0, Vector(3, 4)) end))
assert(not pcall(function() Isaac.WorldToMenuPosition(23, Vector(3, 4)) end))
assert(not pcall(function() Isaac.WorldToMenuPosition(8, {}) end))

assert(CollectionMenu.GetSelectedPage() == 2)
assert(CollectionMenu.GetSelectedElement() == 11)
assert(not pcall(function() CollectionMenu:GetSelectedPage() end))
assert(not pcall(function() CollectionMenu.GetSelectedElement(1) end))

assert(type(SaveMenu.GetDeletePopupSprite()) == 'userdata')
assert(type(MainMenu.GetContinueWidgetSprite()) == 'userdata')
assert(type(RoomTransition.GetVersusScreenSprite()) == 'userdata')
assert(not pcall(function() SaveMenu:GetDeletePopupSprite() end))

assert(RoomTransition.IsRenderingBossIntro())
RoomTransition.StartBossIntro(42)
assert(select('#', RoomTransition.StartBossIntro(7, 9)) == 0)
assert(not pcall(function() RoomTransition.StartBossIntro() end))
assert(not pcall(function() RoomTransition.StartBossIntro({}) end))
assert(not pcall(function() RoomTransition:IsRenderingBossIntro() end))

assert(Ambush.GetCurrentWave() == 5)
assert(not pcall(function() Ambush.GetCurrentWave(1) end))
assert(NightmareScene.IsDogmaNightmare())
assert(not pcall(function() NightmareScene:IsDogmaNightmare() end))

assert(roomDesc:GetDimension() == 1)
assert(roomDesc:GetTaintedKeeperCoinSpawns() == 10)
roomDesc:SetTaintedKeeperCoinSpawns(7)
assert(roomDesc:GetTaintedKeeperCoinSpawns() == 7)
roomDesc:SetTaintedKeeperCoinSpawns(-1)
assert(roomDesc:GetTaintedKeeperCoinSpawns() == -1)
assert(not pcall(function() roomDesc:GetDimension(1) end))
_clearCompletionPort()
assert(not pcall(Isaac.GetCompletionMark,0,12))
)lua";

    const auto result = LuaRuntime::InitializeFromBuffer(
        script, std::strlen(script), "@repentogon-menu-world.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    assert(Read<std::int16_t>(descriptor, 0x5E) == -1);
    assert(startBossIntroCalls == 2 && lastBossId1 == 7 && lastBossId2 == 9);
    assert(isaac::runtime::RepentogonApplyCustomCompletionMarks(
        41, static_cast<std::uintptr_t>(0x7000)));
    assert(completionSprite == 0x7000);
    const std::array<int, 12> expectedFrames{
        1, 2, 1, 1, 2, 1, 1, 2, 1, 2, 2, 1};
    assert(completionFrames == expectedFrames);
    Put<std::int32_t>(descriptor, 0x0C, -1);
    const char* reset_dimension = "assert(roomDesc:GetDimension()==-1, 'reset Dimension must remain signed')";
    if (LuaRuntime::InitializeFromBuffer(reset_dimension, std::strlen(reset_dimension),
            "@repentogon-reset-dimension.lua") != LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);return 4;
    }

    assert(isaac::runtime::RepentogonMenuWorldSpriteAlive(
        Address(menuManager) + kMenuSavePage + kMenuSaveDeletePopup));
    assert(isaac::runtime::RepentogonMenuWorldSpriteAlive(
        Address(menuManager) + kMenuGamePage + kMenuGameContinueWidget));
    assert(isaac::runtime::RepentogonMenuWorldSpriteAlive(
        Address(game) + kGameRoomTransition + 0x48));
    const auto pause = Address(game) + 0x1AE128;
    assert(isaac::runtime::RepentogonMenuWorldSpriteAlive(pause + 0x80B90 + 8));
    assert(!isaac::runtime::RepentogonMenuWorldSpriteAlive(pause + 0x8B90 + 8));
    assert(!isaac::runtime::RepentogonMenuWorldSpriteAlive(
        Address(menuManager) + kMenuSavePage + kMenuSaveDeletePopup + 8));

    Put<std::uintptr_t>(menuSlot, 0, 0);
    Put<std::uintptr_t>(gameSlot, 0, 0);
    constexpr const char* stale_sprites = R"lua(
assert(not pcall(function() SaveMenu.GetDeletePopupSprite() end))
assert(not pcall(function() MainMenu.GetContinueWidgetSprite() end))
assert(not pcall(function() RoomTransition.GetVersusScreenSprite() end))
)lua";
    if (LuaRuntime::InitializeFromBuffer(
            stale_sprites, std::strlen(stale_sprites),
            "@repentogon-menu-world-stale-sprites.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 2;
    }

    constexpr const char* inactive_menu = R"lua(
assert(not MenuManager.IsActive())
assert(not pcall(function() MenuManager.GetActiveMenu() end))
assert(not pcall(function() MenuManager.GetViewPosition() end))
)lua";
    if (LuaRuntime::InitializeFromBuffer(
            inactive_menu, std::strlen(inactive_menu),
            "@repentogon-menu-world-inactive.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 3;
    }

    assert(LuaRuntime::ShutdownForModReload());
    std::array<std::uint8_t, 15> persisted_marks{};
    bool persisted_tainted = false;
    assert(!isaac::runtime::RepentogonGetCustomCompletionMarks(
        41, &persisted_marks, &persisted_tainted));
    LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
    isaac::runtime::SetRepentogonMenuWorldNativeTestBindings({});
    isaac::runtime::repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonMenuWorldApiTests(unittest.TestCase):
    def test_native_branch_compiles_with_null_host_address(self) -> None:
        with tempfile.TemporaryDirectory(
                prefix="repentogon-menu-world-compile-") as folder:
            compatibility = Path(folder) / "compatibility"
            compatibility.mkdir()
            (compatibility / "stdfloat").write_text(
                "#pragma once\n"
                "namespace std { using float16_t = float; "
                "using float128_t = long double; }\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "c++", "-std=c++23", "-D__SWITCH__",
                    "-DEXL_LAYERED_RUNTIME=1", "-DEXL_DIAGNOSTIC_STAGE=14",
                    "-DEXL_LOAD_KIND=Module", "-DEXL_LOAD_KIND_ENUM=2",
                    "-DEXL_PROGRAM_ID=0", "-fsyntax-only",
                    f"-I{compatibility}", f"-I{PUBLIC_ROOT / 'runtime' / 'src'}",
                    f"-I{SOURCE}",
                    f"-I{SOURCE / 'third_party' / 'lua-5.3.3' / 'src'}",
                    str(EXTRA_SOURCE),
                ],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_static_menu_world_surface(self) -> None:
        with tempfile.TemporaryDirectory(prefix="repentogon-menu-world-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
                extra_sources=() if EXTRA_SOURCE in test_support.layered_lua_runtime_sources(SOURCE) else (EXTRA_SOURCE,),
            )
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
