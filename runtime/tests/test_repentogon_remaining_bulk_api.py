"""Bulk player, pickup, and item-pool APIs use real engine layouts."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / "source"
DRIVER = PREFIX + r'''
#include "interfaces/lua/repentogon_remaining_bulk_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "game_observer.hpp"
#include "lua_object_handles.hpp"
#include "ports/save_file_port.hpp"
#include "runtime_constants.hpp"
#include "lua_runtime.hpp"

#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace isaac::runtime;

static std::vector<unsigned char> module;
static std::vector<unsigned char> game;
static std::vector<unsigned char> player;
static std::vector<unsigned char> backup;
static std::vector<unsigned char> pickup;
static std::vector<unsigned char> poolItems;
static std::vector<unsigned char> pickupLayers;

static std::uintptr_t Address(const std::vector<unsigned char>& bytes) {
    return reinterpret_cast<std::uintptr_t>(bytes.data());
}

static void SetIdentity(std::vector<unsigned char>& bytes, std::uintptr_t vtable,
                        std::uint32_t type, std::uint32_t variant = 0) {
    std::memcpy(bytes.data(), &vtable, sizeof(vtable));
    std::memcpy(bytes.data() + kEntityTypeOffset, &type, sizeof(type));
    std::memcpy(bytes.data() + kEntityVariantOffset, &variant, sizeof(variant));
}

static void Put(std::vector<unsigned char>& bytes, std::size_t offset,
                const void* value, std::size_t size) {
    assert(offset + size <= bytes.size());
    std::memcpy(bytes.data() + offset, value, size);
}

static int Mutate(lua_State* state) {
    const auto value = static_cast<std::uint8_t>(luaL_checkinteger(state, 1));
    pickup[kEntityPickupForceBlindOffset] = value;
    return 0;
}

static int SetBlindSheet(lua_State* state) {
    static constexpr char question[] = "gfx/Items/Collectibles/questionmark.png";
    static constexpr char different[] = "gfx/items/collectibles/questionmark.png";
    const auto mode = luaL_checkinteger(state, 1);
    const auto path = mode == 2 ? different : question;
    std::uintptr_t words[3]{1, sizeof(question) - 1,
        reinterpret_cast<std::uintptr_t>(path)};
    if (mode == 3) std::memset(words, 0, sizeof(words));
    if (mode == 4) {
        std::memset(words, 0, sizeof(words));
        auto* bytes = reinterpret_cast<unsigned char*>(words);
        bytes[0] = 14;
        std::memcpy(bytes + 1, "foo.png", 7);
    }
    if (mode == 7) words[2] = 0;
    Put(pickupLayers, 0xb0 + 0x10, words, sizeof(words));
    const auto layers = mode == 5 ? 0 : Address(pickupLayers);
    const std::int32_t count = mode == 5 ? 0 : mode == 6 ? 1 : 2;
    Put(pickup, kEntitySpriteOffset + 0xa8, &layers, sizeof(layers));
    Put(pickup, kEntitySpriteOffset + 0xb0, &count, sizeof(count));
    const std::uint32_t variant = mode == 8 ? 20 : 100;
    Put(pickup, kEntityVariantOffset, &variant, sizeof(variant));
    return 0;
}

static void Extensions(lua_State* state) noexcept {
    RegisterRepentogonRemainingBulkViews(state);
    PushEntityCallbackArgument(state, Address(player));
    lua_setglobal(state, "player");
    PushEntityCallbackArgument(state, Address(pickup));
    lua_setglobal(state, "pickup");

    auto* pool = static_cast<LuaRuntime::ItemPoolHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::ItemPoolHandle)));
    *pool = {};
    luaL_getmetatable(state, LuaRuntime::kItemPoolMetatable);
    lua_setmetatable(state, -2);
    lua_setglobal(state, "pool");
    lua_pushcfunction(state, Mutate);
    lua_setglobal(state, "mutate");
    lua_pushcfunction(state, SetBlindSheet);
    lua_setglobal(state, "_blindSheet");
}

int main() {
    module.assign(0xaac698 + 0x100, 0);
    game.assign(0x242c0 + 0x908, 0);
    player.assign(0x2700, 0);
    backup.assign(0x2700, 0);
    pickup.assign(0x800, 0);
    poolItems.assign(2 * 0x18, 0);
    pickupLayers.assign(2 * 0xb0, 0);

    const auto base = Address(module);
    SetIdentity(player, base + kEntityPlayerVtableOffset, kEntityTypePlayer);
    SetIdentity(backup, base + kEntityPlayerVtableOffset, kEntityTypePlayer);
    SetIdentity(pickup, base + kEntityPickupVtableOffset, kEntityTypePickup, 100);

    std::int32_t damageModifier = 17;
    float edenDamage = 2.5f;
    float d8Damage = 1.25f;
    Put(player, 0x1910, &damageModifier, sizeof(damageModifier));
    Put(player, 0x1938, &edenDamage, sizeof(edenDamage));
    Put(player, 0x1db4, &d8Damage, sizeof(d8Damage));
    const auto backupAddress = Address(backup);
    Put(player, 0x2588, &backupAddress, sizeof(backupAddress));
    pickup[0x562] = 1;

    const auto pool = Address(game) + 0x242c0;
    const std::uint64_t removedWords[]{6, 1};
    const std::uintptr_t removedBits = reinterpret_cast<std::uintptr_t>(removedWords);
    const std::size_t removedCount = 66, removedCapacity = 2;
    std::memcpy(reinterpret_cast<void*>(pool + 0x8f0), &removedBits, 8);
    std::memcpy(reinterpret_cast<void*>(pool + 0x8f8), &removedCount, 8);
    std::memcpy(reinterpret_cast<void*>(pool + 0x900), &removedCapacity, 8);
    const auto begin = Address(poolItems);
    const auto end = begin + poolItems.size();
    // GetPool @ 0x3c5580 returns this + 8 + type * 0x48;
    // pick_collectible @ 0x3c5d54 reads that Pool's vector at +8/+16.
    const float totalWeight = 123.5f;
    std::memcpy(reinterpret_cast<void*>(pool + 0x08), &totalWeight, sizeof(totalWeight));
    std::memcpy(reinterpret_cast<void*>(pool + 0x10), &begin, sizeof(begin));
    std::memcpy(reinterpret_cast<void*>(pool + 0x18), &end, sizeof(end));
    std::memcpy(reinterpret_cast<void*>(pool + 30 * 0x48 + 0x10), &begin, sizeof(begin));
    std::memcpy(reinterpret_cast<void*>(pool + 30 * 0x48 + 0x18), &end, sizeof(end));
    // Pool 2 is malformed (half-null); pool 3 has a non-element-sized range.
    std::memcpy(reinterpret_cast<void*>(pool + 2 * 0x48 + 0x18), &end, sizeof(end));
    const auto unalignedEnd = begin + 1;
    std::memcpy(reinterpret_cast<void*>(pool + 3 * 0x48 + 0x10), &begin, sizeof(begin));
    std::memcpy(reinterpret_cast<void*>(pool + 3 * 0x48 + 0x18), &unalignedEnd, sizeof(unalignedEnd));

    std::int32_t itemId = 42;
    float initialWeight = 1.5f;
    float weight = 0.75f;
    float decreaseBy = 0.25f;
    float removeOn = -1.0f;
    std::uint8_t unlocked = 1;
    Put(poolItems, 0x00, &itemId, sizeof(itemId));
    Put(poolItems, 0x04, &initialWeight, sizeof(initialWeight));
    Put(poolItems, 0x08, &weight, sizeof(weight));
    Put(poolItems, 0x0c, &decreaseBy, sizeof(decreaseBy));
    Put(poolItems, 0x10, &removeOn, sizeof(removeOn));
    Put(poolItems, 0x14, &unlocked, sizeof(unlocked));
    SetRepentogonRemainingBulkNativeTestBindings(
        {reinterpret_cast<void*>(pool)});

    LuaRuntime::SetEngineModuleBase(base);
    LuaRuntime::ObserveGameThread();
    Files files(true);
    SetSessionSaveFilePort(&files);
    const repentogon::NativePort port{Ready, Ready};
    repentogon::SetNativePort(&port);
    LuaRuntime::SetRuntimeExtensionInstaller(Extensions);

    const char* script = R"lua(
assert(player:GetDamageModifier() == 17)
assert(player:GetEdenDamage() == 2.5)
assert(player:GetD8DamageModifier() == 1.25)
local flipped = player:GetFlippedForm()
assert(type(flipped) == 'userdata' and flipped.Type == 1)
assert(pickup:IsBlind())
mutate(0)
assert(not pickup:IsBlind())
_blindSheet(1)
assert(pickup:IsBlind(false), 'questionmark layer is blind when not forced-only')
assert(not pickup:IsBlind() and not pickup:IsBlind(true) and not pickup:IsBlind(nil))
for _,mode in ipairs({2,3,4,5,6}) do
    _blindSheet(mode)
    assert(not pickup:IsBlind(false))
end
_blindSheet(7)
assert(not pcall(function() pickup:IsBlind(false) end))
assert(not pickup:IsBlind(), 'forced-only must not inspect the Sprite')
mutate(1)
assert(pickup:IsBlind(false) and pickup:IsBlind())
_blindSheet(8)
assert(not pickup:IsBlind(false) and not pickup:IsBlind())
assert(pool:GetNumItemPools() == 31)
local removed = pool:GetRemovedCollectibles()
assert(#removed == 65 and removed[0] == nil and removed[66] == nil)
assert(removed[1] and removed[2] and not removed[3] and removed[64] and not removed[65])
local items = pool:GetCollectiblesFromPool(0)
assert(#items == 2 and items[1].itemID == 42)
assert(items[1].initialWeight == 1.5 and items[1].weight == 0.75)
assert(items[1].decreaseBy == 0.25 and items[1].removeOn == -1 and items[1].isUnlocked)
assert(pool:GetCollectiblesFromPool(30)[1].itemID == 42)
assert(#pool:GetCollectiblesFromPool(1) == 0, 'constructor-empty vector is valid')
assert(not pcall(function() pool:GetCollectiblesFromPool(2) end))
assert(not pcall(function() pool:GetCollectiblesFromPool(3) end))
items[1].itemID = -1
assert(pool:GetCollectiblesFromPool(0)[1].itemID == 42, 'result is an independent snapshot')
assert(not pcall(function() player:GetDamageModifier(1) end))
assert(not pcall(function() pool:GetCollectiblesFromPool(31) end))
)lua";
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script),
                                         "@remaining-bulk-api.lua") !=
        LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    assert(LuaRuntime::ShutdownForModReload());
    LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
    repentogon::SetNativePort(nullptr);
    SetRepentogonRemainingBulkNativeTestBindings({});
    SetSessionSaveFilePort(nullptr);
}
'''


class RemainingBulkApiTests(unittest.TestCase):
    def test_player_pickup_and_item_pool_layouts(self):
        with tempfile.TemporaryDirectory(prefix="repentogon-remaining-api-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
