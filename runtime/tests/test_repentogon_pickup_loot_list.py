"""Host contract for the native-backed 1334 LootList adapter."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from . import test_support


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/interfaces/lua/repentogon_pickup_loot_list.cpp"


DRIVER = r'''
#include "interfaces/lua/repentogon_pickup_loot_list.hpp"
#include "lua_object_handles.hpp"

#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <new>

extern "C" {
#include <lauxlib.h>
#include <lua.h>
#include <lualib.h>
}

namespace isaac::runtime {

bool TryEngineRandomU32(std::uint32_t* value) noexcept {
    if (value == nullptr) return false;
    *value = 0x12345678;
    return true;
}

void* TryResolveRngObject(LuaRuntime::RngHandle* handle, bool writable) noexcept {
    (void)writable;
    return handle ? handle->storage.data() : nullptr;
}

}  // namespace isaac::runtime

namespace {

struct Header {
    std::uintptr_t mapFirst;
    std::uintptr_t mapBegin;
    std::uintptr_t mapEnd;
    std::uintptr_t mapCapacity;
    std::uintptr_t start;
    std::uintptr_t size;
};
static_assert(sizeof(Header) == 0x30);

struct Block {
    std::array<std::array<unsigned char, 0x18>, 170> entries{};
};

struct StoredEntry {
    std::uint32_t type;
    std::uint32_t variant;
    std::uint32_t subtype;
    std::uint32_t seed;
    std::uintptr_t rng;
};
static_assert(sizeof(StoredEntry) == 0x18);

unsigned addCalls;
unsigned destroyCalls;

LuaRuntime::RngHandle* PushRng(lua_State* state, std::uint32_t seed) {
    auto* handle = new (lua_newuserdata(state, sizeof(LuaRuntime::RngHandle)))
        LuaRuntime::RngHandle{};
    std::memcpy(handle->storage.data(), &seed, sizeof(seed));
    luaL_getmetatable(state, LuaRuntime::kRngMetatable);
    lua_setmetatable(state, -2);
    return handle;
}

void AddBack(void* object) noexcept {
    ++addCalls;
    auto* header = static_cast<Header*>(object);
    const auto oldSlots =
        header->mapBegin == 0
            ? std::size_t{0}
            : (header->mapEnd - header->mapBegin) / sizeof(std::uintptr_t);
    auto** oldMap = reinterpret_cast<void**>(header->mapFirst);
    auto** map = new void*[oldSlots + 1]{};
    for (std::size_t index = 0; index < oldSlots; ++index) {
        map[index] = oldMap[index];
    }
    auto* block = new Block;
    map[oldSlots] = block;
    header->mapFirst = reinterpret_cast<std::uintptr_t>(map);
    header->mapBegin = header->mapFirst;
    header->mapEnd = reinterpret_cast<std::uintptr_t>(map + oldSlots + 1);
    header->mapCapacity = header->mapEnd;
    if (oldSlots == 0) {
        header->start = 0;
        header->size = 0;
    }
    delete[] oldMap;
}

void Destroy(void* object) noexcept {
    ++destroyCalls;
    auto* header = static_cast<Header*>(object);
    if (header->mapFirst == 0) return;
    auto** map = reinterpret_cast<void**>(header->mapFirst);
    const auto slots =
        (header->mapEnd - header->mapBegin) / sizeof(std::uintptr_t);
    for (std::size_t index = 0; index < slots; ++index) {
        delete reinterpret_cast<Block*>(map[index]);
    }
    delete[] map;
    std::memset(header, 0, sizeof(*header));
}

}  // namespace

int main() {
    lua_State* state = luaL_newstate();
    assert(state != nullptr);
    luaL_requiref(state, "_G", luaopen_base, 1);
    lua_pop(state, 1);

    luaL_newmetatable(state, LuaRuntime::kRngMetatable);
    lua_pop(state, 1);

    constexpr std::uint32_t dropSeed = 0x44556677;
    isaac::runtime::SetRepentogonPickupLootListTestBindings(
        {0, &AddBack, &Destroy});
    isaac::runtime::RegisterRepentogonPickupLootList(state);
    auto* dropRngHandle = PushRng(state, dropSeed);
    lua_setglobal(state, "drop_rng");
    auto* otherRngHandle = PushRng(state, 0x55667788);
    lua_setglobal(state, "other_rng");
    const auto previous = isaac::runtime::SetRepentogonPickupLootListDropRng(
        reinterpret_cast<std::uintptr_t>(dropRngHandle->storage.data()));
    assert(previous == 0);

    constexpr char script[] = R"lua(
local a = LootList()
a:PushEntry(5, 100, 1, 123)
a:PushEntry(5, 101, 2, 456, drop_rng)
local entries = a:GetEntries()
assert(#entries == 2)
assert(entries[1]:GetType() == 5)
assert(entries[1]:GetVariant() == 100)
assert(entries[1]:GetSubType() == 1)
assert(entries[1]:GetSeed() == 123)
assert(entries[1]:GetRNG() == nil)
assert(entries[2]:GetRNG() ~= nil)

local b = LootList()
b:PushEntry(5, 102, 3)
assert(b:GetEntries()[1]:GetSeed() == 0x12345678)
assert(b:GetEntries()[1]:GetRNG() == nil)

assert(not pcall(function()
    b:PushEntry(5, 103, 4, 9, other_rng)
end))
assert(not pcall(function()
    b:PushEntry(5, 103, 4, 9, {})
end))

moved = LootList()
moved:PushEntry(5, 104, 5, 77)

cached = LootList()
cached:PushEntry(5, 105, 6, 88, drop_rng)
)lua";

    alignas(8) std::array<unsigned char, 0x30> native{};

    // Execute the builder portion first; the move/push bridge is exercised
    // below through the exported C API.
    if (luaL_dostring(state, script) != LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        return 1;
    }

    lua_getglobal(state, "moved");
    assert(lua_isuserdata(state, -1));
    const auto moved = isaac::runtime::MoveRepentogonPickupLootListToNative(
        state, -1, reinterpret_cast<std::uintptr_t>(native.data()));
    assert(moved);
    lua_pop(state, 1);

    assert(isaac::runtime::PushRepentogonPickupLootList(
        state, reinterpret_cast<std::uintptr_t>(native.data()),
        reinterpret_cast<std::uintptr_t>(dropRngHandle->storage.data())));
    lua_setglobal(state, "native_list");
    if (luaL_dostring(state,
                      "assert(native_list:GetEntries()[1]:GetVariant() == 104)") !=
        LUA_OK) {
        std::fprintf(stderr, "%s\n", lua_tostring(state, -1));
        return 1;
    }

    alignas(8) std::array<unsigned char, 0x30> cachedDestination{};
    const auto beforeCached = cachedDestination;
    const auto beforeCachedDestroy = destroyCalls;
    lua_getglobal(state, "cached");
    assert(isaac::runtime::SetRepentogonPickupLootListDropRng(
               reinterpret_cast<std::uintptr_t>(
                   otherRngHandle->storage.data())) ==
           reinterpret_cast<std::uintptr_t>(dropRngHandle->storage.data()));
    assert(!isaac::runtime::MoveRepentogonPickupLootListToNative(
        state, -1,
        reinterpret_cast<std::uintptr_t>(cachedDestination.data())));
    lua_pop(state, 1);
    assert(cachedDestination == beforeCached);
    assert(destroyCalls == beforeCachedDestroy);
    assert(isaac::runtime::SetRepentogonPickupLootListDropRng(
               reinterpret_cast<std::uintptr_t>(dropRngHandle->storage.data())) ==
           reinterpret_cast<std::uintptr_t>(otherRngHandle->storage.data()));

    std::array<unsigned char, 16> unsafeRng{};
    alignas(8) std::array<unsigned char, 0x30> unsafeNative{};
    AddBack(unsafeNative.data());
    auto* unsafeHeader = reinterpret_cast<Header*>(unsafeNative.data());
    auto** unsafeMap = reinterpret_cast<void**>(unsafeHeader->mapFirst);
    auto* unsafeEntryBytes = static_cast<unsigned char*>(unsafeMap[0]);
    const StoredEntry unsafeEntry{
        5, 105, 6, 88,
        reinterpret_cast<std::uintptr_t>(unsafeRng.data()),
    };
    std::memcpy(unsafeEntryBytes, &unsafeEntry, sizeof(unsafeEntry));
    unsafeHeader->size = 1;
    assert(isaac::runtime::PushRepentogonPickupLootList(
        state, reinterpret_cast<std::uintptr_t>(unsafeNative.data()),
        reinterpret_cast<std::uintptr_t>(dropRngHandle->storage.data())));
    lua_setglobal(state, "unsafe_list");

    alignas(8) std::array<unsigned char, 0x30> blockedDestination{};
    const auto beforeBlocked = blockedDestination;
    const auto beforeDestroy = destroyCalls;
    lua_getglobal(state, "unsafe_list");
    assert(!isaac::runtime::MoveRepentogonPickupLootListToNative(
        state, -1,
        reinterpret_cast<std::uintptr_t>(blockedDestination.data())));
    lua_pop(state, 1);
    assert(blockedDestination == beforeBlocked);
    assert(destroyCalls == beforeDestroy);

    lua_newuserdata(state, 64);
    lua_setglobal(state, "fake_list");
    alignas(8) std::array<unsigned char, 0x30> fakeDestination{};
    const auto beforeFake = fakeDestination;
    lua_getglobal(state, "fake_list");
    assert(!isaac::runtime::MoveRepentogonPickupLootListToNative(
        state, -1, reinterpret_cast<std::uintptr_t>(fakeDestination.data())));
    lua_pop(state, 1);
    assert(fakeDestination == beforeFake);

    static_cast<void>(
        isaac::runtime::SetRepentogonPickupLootListDropRng(previous));
    lua_close(state);
    assert(addCalls > 0);
    assert(destroyCalls > 0);
}
'''


class RepentogonPickupLootListTests(unittest.TestCase):
    def test_native_builder_and_ownership(self):
        with tempfile.TemporaryDirectory(prefix="repentogon-loot-list-") as folder:
            directory = Path(folder)
            driver = directory / "driver.cpp"
            driver.write_text(DRIVER, encoding="utf-8")
            binary = directory / "driver"
            lua_root = ROOT / "source/third_party/lua-5.3.3/src"
            lua_objects = test_support.lua_harness_objects(
                ROOT / "source", directory)
            build = subprocess.run(
                [
                    "c++",
                    "-std=c++20",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(ROOT / "src"),
                    "-I",
                    str(ROOT / "source"),
                    "-I",
                    str(lua_root),
                    str(driver),
                    str(SOURCE),
                    *map(str, lua_objects),
                    "-lm",
                    "-o",
                    str(binary),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
