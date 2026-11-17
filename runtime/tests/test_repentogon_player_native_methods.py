"""Host coverage for the three MGO player methods added to the extension surface."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / "source"

DRIVER = PREFIX + r'''
#include "interfaces/lua/api500_config.hpp"
#include "interfaces/lua/api500_config.guards.hpp"
#include "interfaces/lua/repentogon_player.guards.hpp"
#include "interfaces/lua/repentogon_player_api.hpp"
#include "interfaces/lua/repentogon_innate_collectible_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "application/player/innate_collectibles.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"

#include <algorithm>
#include <cassert>
#include <cstring>
#include <vector>

static std::vector<unsigned char> moduleBytes;
static std::vector<unsigned char> player;
static unsigned shootCalls;
static unsigned fireCalls;
static unsigned stringCalls;
static unsigned innateCostumeCalls;
static unsigned innateEvaluateCalls;
static char lastHeadAnim[16]{};
static std::vector<unsigned char> item;
static std::vector<unsigned char> effect;

// Frozen return-patch image from Repentance.nro build 91C73FDD...

static std::uintptr_t ShootBlueCandle(void* object, const void* direction) {
    const auto* vector = static_cast<const LuaRuntime::VectorHandle*>(direction);
    assert(object == player.data());
    assert(vector != nullptr && vector->x == 3.0F && vector->y == 4.0F);
    ++shootCalls;
    return reinterpret_cast<std::uintptr_t>(effect.data());
}

static std::uintptr_t FireBrimstoneBall(
    void* object, const void* position, const void* velocity, const void* offset,
    std::uint32_t first, std::uint32_t second, void* source) {
    const auto* p = static_cast<const LuaRuntime::VectorHandle*>(position);
    const auto* v = static_cast<const LuaRuntime::VectorHandle*>(velocity);
    const auto* o = static_cast<const LuaRuntime::VectorHandle*>(offset);
    assert(object == player.data());
    assert(p != nullptr && p->x == 3.0F && p->y == 4.0F);
    assert(v != nullptr && v->x == 5.0F && v->y == 6.0F);
    assert(o != nullptr);
    if (fireCalls == 0) {
        assert(o->x == 7.0F && o->y == 8.0F);
    } else {
        assert(o->x == 0.0F && o->y == 0.0F);
    }
    assert(first == 0 && second == 0 && source == nullptr);
    ++fireCalls;
    return 0;
}

struct BorrowedString {
    std::uint64_t capacity;
    std::uint64_t length;
    const char* data;
};

static void* AssignString(void* target, const void* source) {
    const auto* text = static_cast<const BorrowedString*>(source);
    assert(target == player.data() + repentogon::player::kHeadAnimOffset);
    assert(text != nullptr && text->data != nullptr);
    const auto length = std::min<std::size_t>(text->length, sizeof(lastHeadAnim) - 1);
    std::memcpy(lastHeadAnim, text->data, length);
    lastHeadAnim[length] = '\0';
    ++stringCalls;
    return target;
}

static std::uintptr_t Collectible(std::int32_t id) {
    return id == 20 ? reinterpret_cast<std::uintptr_t>(item.data()) : 0;
}

static void AddInnateCostume(void* object, const void*, bool) {
    assert(object == player.data());
    ++innateCostumeCalls;
}

static void EvaluateInnate(void* object) {
    assert(object == player.data());
    ++innateEvaluateCalls;
}

static int ReadLockTime(lua_State* state) {
    std::int32_t value{};
    std::memcpy(&value, player.data() + repentogon::player::kHeadDirectionTimeOffset,
                sizeof(value));
    lua_pushinteger(state, value);
    return 1;
}

static int ReadHeadAnim(lua_State* state) {
    lua_pushstring(state, lastHeadAnim);
    return 1;
}

static int ReadInnateCount(lua_State* state) {
    lua_pushinteger(
        state, isaac::runtime::innate_collectibles::Count(
                   reinterpret_cast<std::uintptr_t>(player.data()), 20));
    return 1;
}

static int CorruptCandleSource(lua_State*) {
    moduleBytes[repentogon::player::kShootBlueCandleReturnSourceOffset] ^= 0x80;
    return 0;
}

static int CorruptCandleIsland(lua_State* state) {
    const auto index = static_cast<std::size_t>(luaL_checkinteger(state, 1));
    assert(index < repentogon::player::kShootBlueCandleReturnIslandGuard.size());
    moduleBytes[repentogon::player::kShootBlueCandleReturnIslandOffset + index] ^= 0x80;
    return 0;
}

static int RestoreCandlePatch(lua_State*) {
    std::memcpy(
        moduleBytes.data() + repentogon::player::kShootBlueCandleReturnSourceOffset,
        repentogon::player::kShootBlueCandleReturnSourceGuard.data(),
        repentogon::player::kShootBlueCandleReturnSourceGuard.size());
    std::memcpy(
        moduleBytes.data() + repentogon::player::kShootBlueCandleReturnIslandOffset,
        repentogon::player::kShootBlueCandleReturnIslandGuard.data(),
        repentogon::player::kShootBlueCandleReturnIslandGuard.size());
    return 0;
}

static void Extensions(lua_State* state) noexcept {
    PushEntityCallbackArgument(state,
                               reinterpret_cast<std::uintptr_t>(player.data()));
    lua_setglobal(state, "player");
    lua_pushcfunction(state, ReadLockTime);
    lua_setglobal(state, "_lock_time");
    lua_pushcfunction(state, ReadHeadAnim);
    lua_setglobal(state, "_head_anim");
    lua_pushcfunction(state, ReadInnateCount);
    lua_setglobal(state, "_innate_count");
    lua_pushcfunction(state, CorruptCandleSource);
    lua_setglobal(state, "_corrupt_candle_source");
    lua_pushcfunction(state, CorruptCandleIsland);
    lua_setglobal(state, "_corrupt_candle_island");
    lua_pushcfunction(state, RestoreCandlePatch);
    lua_setglobal(state, "_restore_candle_patch");
}

int main() {
    const auto moduleSize = std::max<std::size_t>(
        0x680000, kEntityPlayerVtableOffset + 16);
    moduleBytes.assign(moduleSize, 0);
    player.assign(0x3000, 0);
    item.assign(0x200, 0);
    effect.assign(0x1000, 0);
    const auto base = reinterpret_cast<std::uintptr_t>(moduleBytes.data());
    const auto vptr = base + kEntityPlayerVtableOffset;
    const std::uint32_t entityType = kEntityTypePlayer;
    std::memcpy(player.data(), &vptr, sizeof(vptr));
    std::memcpy(player.data() + kEntityTypeOffset, &entityType, sizeof(entityType));
    const auto effectVptr = base + kEntityEffectVtableOffset;
    const std::uint32_t effectType = kEntityTypeEffect;
    std::memcpy(effect.data(), &effectVptr, sizeof(effectVptr));
    std::memcpy(effect.data() + kEntityTypeOffset, &effectType, sizeof(effectType));
    const std::int32_t initialHeadDirectionTime = -1;
    std::memcpy(player.data() + repentogon::player::kHeadDirectionTimeOffset,
                &initialHeadDirectionTime, sizeof(initialHeadDirectionTime));
    const std::uint32_t innateFlags = 0x40;
    const std::uint8_t innateCostume = 1;
    std::memcpy(item.data() + kItemConfigItemCacheFlagsOffset, &innateFlags,
                sizeof(innateFlags));
    std::memcpy(item.data() + kApi600ItemConfigShouldAddCostumeOnPickupFieldOffset,
                &innateCostume, sizeof(innateCostume));
    std::memcpy(player.data() + kEntityPlayerTypeOffset, &entityType, sizeof(entityType));

    std::memcpy(moduleBytes.data() + repentogon::player::kShootBlueCandleOffset,
                repentogon::player::kShootBlueCandleGuard.data(),
                repentogon::player::kShootBlueCandleGuard.size());
    std::memcpy(moduleBytes.data() + repentogon::player::kFireBrimstoneBallOffset,
                repentogon::player::kFireBrimstoneBallGuard.data(),
                repentogon::player::kFireBrimstoneBallGuard.size());
    std::memcpy(moduleBytes.data() + isaac::runtime::api500_config::kStringAssignOffset,
                isaac::runtime::api500_config::kStringAssignGuard.data(),
                isaac::runtime::api500_config::kStringAssignGuard.size());
    RestoreCandlePatch(nullptr);

    LuaRuntime::SetEngineModuleBase(base);
    LuaRuntime::ObserveGameThread();
    Files files(true);
    SetSessionSaveFilePort(&files);
    const isaac::runtime::repentogon::NativePort port{Ready, Ready};
    isaac::runtime::repentogon::SetNativePort(&port);
    LuaRuntime::SetRuntimeExtensionInstaller(Extensions);
    isaac::runtime::SetRepentogonPlayerShootBlueCandleHost(&ShootBlueCandle);
    isaac::runtime::SetRepentogonPlayerFireBrimstoneBallHost(&FireBrimstoneBall);
    isaac::runtime::SetApi500ConfigStringAssignmentForTesting(&AssignString);
    isaac::runtime::InnateCollectibleTestBindings innateBindings{};
    innateBindings.collectible = &Collectible;
    innateBindings.addCostume = &AddInnateCostume;
    innateBindings.evaluate = &EvaluateInnate;
    isaac::runtime::SetInnateCollectibleTestBindings(innateBindings);

    const char* script = R"lua(
assert(type(player.ShootBlueCandle) == "function")
assert(type(player.FireBrimstoneBall) == "function")
assert(type(player.SetHeadDirection) == "function")
assert(type(player.AddInnateCollectible) == "function")
local candle = player:ShootBlueCandle(Vector(3,4))
assert(candle and candle:ToEffect())
local function reject_patch()
  local ok, err = pcall(function() player:ShootBlueCandle(Vector(3,4)) end)
  assert(not ok and string.find(tostring(err), "return patch guard"), tostring(err))
end
for i = 0, 11 do
  _corrupt_candle_island(i)
  reject_patch()
  _restore_candle_patch()
end
_corrupt_candle_source()
reject_patch()
_restore_candle_patch()
local candle2 = player:ShootBlueCandle(Vector(3,4))
assert(candle2 and candle2:ToEffect())
assert(GetPtrHash(candle) == GetPtrHash(candle2))
assert(player:FireBrimstoneBall(Vector(3,4), Vector(5,6), Vector(7,8)) == nil)
assert(player:FireBrimstoneBall(Vector(3,4), Vector(5,6)) == nil)
assert(player:SetHeadDirection(2,17) == nil)
assert(_lock_time() == 17 and _head_anim() == "HeadRight")
assert(player:SetHeadDirection(1,25) == nil)
assert(_lock_time() == 17 and _head_anim() == "HeadRight")
assert(player:SetHeadDirection(1,25,true) == nil)
assert(_lock_time() == 25 and _head_anim() == "HeadUp")
assert(player:AddInnateCollectible(20,2) == nil)
assert(_innate_count() == 2)
assert(player:AddInnateCollectible(20,-1) == nil)
assert(_innate_count() == 1)
assert(player:AddInnateCollectible(20,1) == nil)
assert(_innate_count() == 2)
assert(not pcall(function() player:SetHeadDirection(4,1,true) end))
assert(not pcall(function() player:ShootBlueCandle() end))
assert(not pcall(function() player:FireBrimstoneBall({},Vector(1,1)) end))
)lua";

    const auto result = LuaRuntime::InitializeFromBuffer(
        script, std::strlen(script), "@mgo-player-methods.lua");
        if (result != LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(
            error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    assert(shootCalls == 2 && fireCalls == 2 && stringCalls == 2);
    assert(innateCostumeCalls == 2 && innateEvaluateCalls == 3);
    assert(std::strcmp(lastHeadAnim, "HeadUp") == 0);
    assert(LuaRuntime::ShutdownForModReload());
    isaac::runtime::SetRepentogonPlayerShootBlueCandleHost(nullptr);
    isaac::runtime::SetRepentogonPlayerFireBrimstoneBallHost(nullptr);
    isaac::runtime::SetApi500ConfigStringAssignmentForTesting(nullptr);
    isaac::runtime::SetInnateCollectibleTestBindings({});
    isaac::runtime::innate_collectibles::Reset();
    LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
    isaac::runtime::repentogon::SetNativePort(nullptr);
    SetSessionSaveFilePort(nullptr);
}
'''


class RepentogonPlayerNativeMethodTests(unittest.TestCase):
    def test_mgo_player_methods_use_the_native_entries(self):
        with tempfile.TemporaryDirectory(prefix="repentogon-player-methods-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
            )
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
