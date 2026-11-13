"""Level room placement follows the upstream neighbor/shape/door transaction."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / "source"
EXTRA_SOURCE = (
    SOURCE.parent
    / "src"
    / "interfaces"
    / "lua"
    / "repentogon_room_placement_api.cpp"
)

DRIVER = PREFIX + r'''
#include "interfaces/lua/repentogon_room_placement_api.hpp"
#include "interfaces/lua/api500_world.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include "infrastructure/call/engine_call_access.hpp"

#include <array>
#include <cstdint>
#include <cstring>
#include <vector>

using namespace isaac::runtime;

namespace {

std::vector<std::uint8_t> moduleBytes(0xC00000);
std::vector<std::uint8_t> gameSlot(8);
std::vector<std::uint8_t> game(0x30000);
std::vector<std::uint8_t> room(0x9000);
std::vector<std::uint8_t> existingConfig(0x100);
std::vector<std::uint8_t> newConfig(0x100);
std::vector<std::uint8_t> currentDoor(0x400);
std::vector<std::uint8_t> redDoorOutline(0x100);

std::uint32_t lastSeed;
std::int32_t lastDimension;
unsigned placeCalls;
unsigned makeDoorCalls;
unsigned visibilityCalls;
unsigned setRoomTypesCalls;
unsigned playAnimationCalls;
unsigned removeEntityCalls;
bool blockAllLocations;

int BlockPlacements(lua_State*) { blockAllLocations = true; return 0; }

template <class T>
void Put(std::vector<std::uint8_t>& bytes, std::size_t offset, T value) {
    assert(offset + sizeof(value) <= bytes.size());
    std::memcpy(bytes.data() + offset, &value, sizeof(value));
}

template <class T>
T Get(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
    T value{};
    assert(offset + sizeof(value) <= bytes.size());
    std::memcpy(&value, bytes.data() + offset, sizeof(value));
    return value;
}

std::uintptr_t Address(const std::vector<std::uint8_t>& bytes) {
    return reinterpret_cast<std::uintptr_t>(bytes.data());
}

const void* HostGetRoomByIdx(const void* level, std::int32_t index,
                             std::int32_t) {
    assert(level == game.data());
    if (index == 84 || blockAllLocations) return game.data() + 0x18;
    return nullptr;
}

const std::int32_t* const* HostOffsets(std::int32_t shape) {
    static const std::int32_t one[8] = {0, 0, -1, -1, 0, 0, 0, 0};
    static const std::int32_t* const values[] = {one, one, one, one, one,
                                                 one, one, one, one, one,
                                                 one, one, one};
    assert(shape >= 0 && shape <= 12);
    return &values[shape];
}

bool HostHasShapeSlot(std::int32_t, std::int32_t slot, bool) {
    return slot == 0 || slot == 2;
}

void HostDoorDirection(const RepentogonRoomPlacementVector* position,
                       std::int32_t slot,
                       RepentogonRoomPlacementVector* target) {
    assert(position != nullptr && target != nullptr);
    *target = *position;
    switch (slot % 4) {
    case 0:
        target->x -= 1;
        break;
    case 1:
        target->y -= 1;
        break;
    case 2:
        target->x += 1;
        break;
    default:
        target->y += 1;
        break;
    }
}

RepentogonRoomPlacementVector HostDoorSource(
    const RepentogonRoomPlacementVector* position, std::int32_t shape,
    std::int32_t slot, bool) {
    assert(position != nullptr);
    if (!HostHasShapeSlot(shape, slot, false)) return {-1, -1};
    return *position;
}

RepentogonRoomPlacementVector HostDoorTarget(
    const RepentogonRoomPlacementVector* position, std::int32_t shape,
    std::int32_t slot, bool) {
    if (!HostHasShapeSlot(shape, slot, false)) return {-1, -1};
    RepentogonRoomPlacementVector target{};
    HostDoorDirection(position, slot, &target);
    return target;
}

bool HostPlaceRoom(void* level, const void* generator, const void* config,
                   std::uint32_t seed, std::int32_t dimension) {
    assert(level == game.data());
    assert(generator != nullptr && config != nullptr);
    ++placeCalls;
    lastSeed = seed;
    lastDimension = dimension;
    const auto count = Get<std::uint32_t>(game, 0x21510);
    assert(count < 507);
    const auto* bytes = static_cast<const std::uint8_t*>(generator);
    std::uint32_t col{}, line{};
    std::memcpy(&col, bytes + 0x08, sizeof(col));
    std::memcpy(&line, bytes + 0x0c, sizeof(line));
    const auto descriptor = 0x18 + static_cast<std::size_t>(count) * 0x100;
    assert(descriptor + 0x100 <= game.size());
    Put(game, descriptor + 0x00, static_cast<std::uint32_t>(line * 13 + col));
    Put(game, descriptor + 0x04, static_cast<std::uint32_t>(line * 13 + col));
    Put(game, descriptor + 0x08, count);
    Put(game, descriptor + 0x0c, dimension < 0 ? 0 : dimension);
    Put<std::uintptr_t>(game, descriptor + 0x10,
                        reinterpret_cast<std::uintptr_t>(config));
    Put<std::uint64_t>(game, descriptor + 0x20, 0);
    Put<std::uint32_t>(game, descriptor + 0x28, 0);
    Put(game, 0x21510, count + 1);
    return true;
}

bool HostHasPhotoDoor(const void*) { return false; }

void HostMakeDoor(void* owner, std::int32_t slot) {
    assert(owner == room.data());
    assert(slot >= 0 && slot < 8);
    ++makeDoorCalls;
    Put<std::uintptr_t>(room, 0xe30 + slot * sizeof(std::uintptr_t),
                        Address(currentDoor));
}

void HostUpdateVisibility(void* level) {
    assert(level == game.data());
    ++visibilityCalls;
}

void HostSetRoomTypes(void* door, std::int32_t currentType,
                      std::int32_t targetType) {
    assert(door == currentDoor.data());
    assert(currentType == 1 && targetType == 1);
    ++setRoomTypesCalls;
}

void HostPlayAnimation(void* door) {
    assert(door == currentDoor.data());
    ++playAnimationCalls;
}

void HostRemoveEntity(void* entity) {
    assert(entity == redDoorOutline.data());
    ++removeEntityCalls;
}

std::int32_t HostFrameCount(const void* value) {
    assert(value == room.data());
    return 1;
}

void HostSetSeed(void* rng, std::uint32_t seed, std::uint32_t shift) {
    assert(rng != nullptr);
    auto* bytes = static_cast<std::uint8_t*>(rng);
    std::memset(bytes, 0, 16);
    std::memcpy(bytes, &seed, sizeof(seed));
    std::memcpy(bytes + 4, &shift, sizeof(shift));
}

void HostNext(void* rng) {
    assert(rng != nullptr);
    auto* bytes = static_cast<std::uint8_t*>(rng);
    std::uint32_t seed{};
    std::memcpy(&seed, bytes, sizeof(seed));
    seed ^= seed << 13;
    seed ^= seed >> 17;
    seed ^= seed << 5;
    std::memcpy(bytes, &seed, sizeof(seed));
}

void PushConfig(lua_State* state, const std::vector<std::uint8_t>& bytes) {
    lua_pushnil(state);
    PushApi500RoomConfig(state, Address(bytes), 0);
}

void PushDescriptor(lua_State* state, std::uintptr_t descriptor) {
    auto* handle = static_cast<LuaRuntime::RoomDescriptorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RoomDescriptorHandle)));
    handle->descriptor = engine_memory::AsObject(descriptor);
    handle->level = game.data();
    handle->moduleBase = LuaRuntime::EngineModuleBase();
    luaL_getmetatable(state, LuaRuntime::kRoomDescriptorMetatable);
    lua_setmetatable(state, -2);
}

void Extensions(lua_State* state) noexcept {
    lua_pushcfunction(state, BlockPlacements);
    lua_setglobal(state, "_blockPlacements");
    assert(RegisterRepentogonRoomPlacementApi(state) == 0);
    luaL_getmetatable(state, LuaRuntime::kLevelMetatable);
    assert(lua_istable(state, -1));
    lua_pushcfunction(state, RepentogonLevelTryPlaceRoom);
    lua_setfield(state, -2, "TryPlaceRoom");
    lua_pushcfunction(state, RepentogonLevelTryPlaceRoomAtDoor);
    lua_setfield(state, -2, "TryPlaceRoomAtDoor");
    lua_pop(state, 1);

    auto* level = static_cast<LuaRuntime::LevelHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::LevelHandle)));
    level->reserved = 0;
    luaL_getmetatable(state, LuaRuntime::kLevelMetatable);
    lua_setmetatable(state, -2);
    lua_setglobal(state, "level");

    PushConfig(state, newConfig);
    lua_setglobal(state, "config");
    PushDescriptor(state, Address(game) + 0x18);
    lua_setglobal(state, "existing");
}

}  // namespace

int main() {
    Put<std::uintptr_t>(gameSlot, 0, Address(game));
    Put<std::uintptr_t>(moduleBytes, kGameOwnerGlobalSlotOffset,
                        Address(gameSlot));
    Put<std::uintptr_t>(game, 0x21550, Address(room));
    Put<std::uintptr_t>(game, 0x21558, 84);
    Put<std::uint32_t>(game, 0x21510, 1);
    Put<std::uint32_t>(game, 0x21514, 84);
    Put<std::uint32_t>(game, 0x21580, 12345);
    Put<std::uint64_t>(game, 0x215f0, std::uint64_t{1} << 10);
    Put<std::uintptr_t>(room, 0x08, Address(game) + 0x18);
    Put<std::uintptr_t>(room, 0x7fa8, Address(redDoorOutline));
    Put<std::uint32_t>(existingConfig, 0x08, 1);
    Put<std::uint32_t>(existingConfig, 0x40, 1);
    Put<std::int32_t>(existingConfig, 0x5c, 1);
    Put<std::uint32_t>(newConfig, 0x08, 1);
    Put<std::uint32_t>(newConfig, 0x40, 4);
    Put<std::int32_t>(newConfig, 0x5c, 1);
    Put<std::uint32_t>(game, 0x18 + 0x00, 84);
    Put<std::uint32_t>(game, 0x18 + 0x04, 84);
    Put<std::uint32_t>(game, 0x18 + 0x08, 0);
    Put<std::uint32_t>(game, 0x18 + 0x0c, 0);
    Put<std::uintptr_t>(game, 0x18 + 0x10, Address(existingConfig));
    Put<std::uint32_t>(game, 0x18 + 0x28, 71);

    const auto guard = [](std::uintptr_t offset, const std::uint8_t* bytes) {
        std::memcpy(moduleBytes.data() + offset, bytes, 16);
    };
    const std::uint8_t getRoom[] = {
        0xff, 0x03, 0x01, 0xd1, 0xfd, 0x7b, 0x01, 0xa9,
        0xfd, 0x43, 0x00, 0x91, 0xf5, 0x13, 0x00, 0xf9};
    const std::uint8_t offsets[] = {
        0xff, 0xc3, 0x00, 0xd1, 0xfd, 0x7b, 0x01, 0xa9,
        0xfd, 0x43, 0x00, 0x91, 0xf4, 0x4f, 0x02, 0xa9};
    const std::uint8_t shapeSlot[] = {
        0xff, 0xc3, 0x00, 0xd1, 0xfd, 0x7b, 0x01, 0xa9,
        0xfd, 0x43, 0x00, 0x91, 0xf3, 0x13, 0x00, 0xf9};
    const std::uint8_t doorSource[] = {
        0xfd, 0x7b, 0xbd, 0xa9, 0xf6, 0x57, 0x01, 0xa9,
        0xfd, 0x03, 0x00, 0x91, 0xf4, 0x4f, 0x02, 0xa9};
    const std::uint8_t doorTarget[] = {
        0xff, 0x43, 0x06, 0xd1, 0xfd, 0x7b, 0x14, 0xa9,
        0xfd, 0x03, 0x05, 0x91, 0xfc, 0xab, 0x00, 0xf9};
    const std::uint8_t placeRoom[] = {
        0xff, 0x03, 0x02, 0xd1, 0xfd, 0x7b, 0x02, 0xa9,
        0xfd, 0x83, 0x00, 0x91, 0xfc, 0x6f, 0x03, 0xa9};
    const std::uint8_t photoDoor[] = {
        0xfd, 0x7b, 0xbe, 0xa9, 0xf4, 0x4f, 0x01, 0xa9,
        0xfd, 0x03, 0x00, 0x91, 0xb4, 0x36, 0x00, 0xf0};
    const std::uint8_t makeDoor[] = {
        0xfd, 0x7b, 0xbc, 0xa9, 0xf7, 0x0b, 0x00, 0xf9,
        0xfd, 0x03, 0x00, 0x91, 0xf6, 0x57, 0x02, 0xa9};
    const std::uint8_t setRoomTypes[] = {
        0xfd, 0x7b, 0xbb, 0xa9, 0xf9, 0x0b, 0x00, 0xf9,
        0xfd, 0x03, 0x00, 0x91, 0xf8, 0x5f, 0x02, 0xa9};
    const std::uint8_t playAnimation[] = {
        0xff, 0x03, 0x02, 0xd1, 0xfd, 0x7b, 0x02, 0xa9,
        0xfd, 0x83, 0x00, 0x91, 0xfc, 0x6f, 0x03, 0xa9};
    const std::uint8_t removeEntity[] = {
        0x08, 0x0c, 0x47, 0x39, 0x1f, 0x08, 0x07, 0x39,
        0x48, 0x00, 0x00, 0x34, 0xc0, 0x03, 0x5f, 0xd6};
    const std::uint8_t visibility[] = {
        0xfd, 0x7b, 0xbb, 0xa9, 0xf9, 0x0b, 0x00, 0xf9,
        0xfd, 0x03, 0x00, 0x91, 0xf8, 0x5f, 0x02, 0xa9};
    guard(0x3dc3b0, getRoom);
    guard(0x3f195c, offsets);
    guard(0x3f1404, shapeSlot);
    guard(0x3f1588, doorSource);
    guard(0x3ef770, doorTarget);
    guard(0x3d0a50, placeRoom);
    guard(0x3d5e44, photoDoor);
    guard(0x454ee4, makeDoor);
    guard(0x385a78, setRoomTypes);
    guard(0x3840ac, playAnimation);
    guard(0x5d3e0, removeEntity);
    guard(0x3d9638, visibility);

    SetRepentogonRoomPlacementNativeTestBindings({
        HostGetRoomByIdx,
        HostOffsets,
        HostHasShapeSlot,
        HostDoorSource,
        HostDoorTarget,
        HostPlaceRoom,
        HostHasPhotoDoor,
        HostMakeDoor,
        HostUpdateVisibility,
        HostSetRoomTypes,
        HostPlayAnimation,
        HostRemoveEntity,
    });
    LuaRuntime::SetEngineModuleBase(Address(moduleBytes));
    LuaRuntime::SetGameBindings(
        Address(moduleBytes) + kGameOwnerGlobalSlotOffset, 0);
    LuaRuntime::SetRngBindings(engine_call::AddressOfFunction(&HostSetSeed),
                               engine_call::AddressOfFunction(&HostNext));
    LuaRuntime::SetRoomGetFrameCountHostFunction(&HostFrameCount);
    LuaRuntime::ObserveGameThread();
    Files files(true);
    SetSessionSaveFilePort(&files);
    const repentogon::NativePort port{Ready, Ready};
    repentogon::SetNativePort(&port);
    LuaRuntime::SetRuntimeExtensionInstaller(Extensions);

    constexpr const char* script = R"lua(
local placed = level:TryPlaceRoom(config, 70, 0, 0x1234, true, true, true)
assert(placed and placed.GridIndex == 70)
assert(placed.DisplayFlags == 5)
print("existing grid", existing.GridIndex)
local byDoor = level:TryPlaceRoomAtDoor(config, existing, 0, 1, true, true)
assert(byDoor and byDoor.GridIndex == 83)
assert(byDoor.DisplayFlags == 5)
assert(level:TryPlaceRoom(config, 169, 0, 1) == false)
assert(level:TryPlaceRoomAtDoor(config, existing, 99, 1) == false)
_blockPlacements()
local failed = table.pack(level:TryPlaceRoom(config, 70, 0, 1, true, true, true))
assert(failed.n == 1 and failed[1] == nil, 'placement failure must return one nil')
failed = table.pack(level:TryPlaceRoomAtDoor(config, existing, 0, 1, true, true))
assert(failed.n == 1 and failed[1] == nil)
)lua";
    const auto result = LuaRuntime::InitializeFromBuffer(
        script, std::strlen(script), "@room-placement.lua");
    if (result != LuaRuntime::LuaInitResult::Success) {
        char error[2048]{};
        static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error, sizeof(error)));
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    assert(placeCalls == 2);
    assert(lastDimension == 0);
    assert(lastSeed == 1);
    assert(makeDoorCalls == 1);
    assert(setRoomTypesCalls == 1);
    assert(playAnimationCalls == 1);
    assert(removeEntityCalls == 1);
    assert(Get<std::uintptr_t>(room, 0x7fa8) == 0);
    assert(visibilityCalls == 2);
    return 0;
}
'''


class RepentogonRoomPlacementApiTests(unittest.TestCase):
    def test_upstream_neighbor_shape_door_dimension_seed_transaction(self):
        with tempfile.TemporaryDirectory(prefix="room-placement-") as folder:
            added = (
                ()
                if EXTRA_SOURCE in test_support.layered_lua_runtime_sources(SOURCE)
                else (EXTRA_SOURCE,)
            )
            binary = test_support.build_lua_harness(
                source_root=SOURCE,
                workdir=Path(folder),
                harness_source=DRIVER,
                extra_sources=added,
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
