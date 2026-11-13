#include "interfaces/lua/repentogon_room_placement_api.hpp"

#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api500_world.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/owner_binding.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <map>
#include <vector>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

using PlacementVector = RepentogonRoomPlacementVector;

// Native adapters are the engine primitives used by upstream RoomPlacement.cpp.
// None of these is a replacement red-room operation.
constexpr std::uintptr_t kGetRoomByIdxOffset = 0x3dc3b0;
constexpr std::array<std::uint8_t, 16> kGetRoomByIdxGuard = {
    0xff, 0x03, 0x01, 0xd1, 0xfd, 0x7b, 0x01, 0xa9,
    0xfd, 0x43, 0x00, 0x91, 0xf5, 0x13, 0x00, 0xf9,
};
constexpr std::uintptr_t kPlacementOffsetsOffset = 0x3f195c;
constexpr std::array<std::uint8_t, 16> kPlacementOffsetsGuard = {
    0xff, 0xc3, 0x00, 0xd1, 0xfd, 0x7b, 0x01, 0xa9,
    0xfd, 0x43, 0x00, 0x91, 0xf4, 0x4f, 0x02, 0xa9,
};
constexpr std::uintptr_t kHasShapeSlotOffset = 0x3f1404;
constexpr std::array<std::uint8_t, 16> kHasShapeSlotGuard = {
    0xff, 0xc3, 0x00, 0xd1, 0xfd, 0x7b, 0x01, 0xa9,
    0xfd, 0x43, 0x00, 0x91, 0xf3, 0x13, 0x00, 0xf9,
};
constexpr std::uintptr_t kGetDoorSourceOffset = 0x3f1588;
constexpr std::array<std::uint8_t, 16> kGetDoorSourceGuard = {
    0xfd, 0x7b, 0xbd, 0xa9, 0xf6, 0x57, 0x01, 0xa9,
    0xfd, 0x03, 0x00, 0x91, 0xf4, 0x4f, 0x02, 0xa9,
};
constexpr std::uintptr_t kGetDoorTargetOffset = 0x3ef770;
constexpr std::array<std::uint8_t, 16> kGetDoorTargetGuard = {
    0xff, 0x43, 0x06, 0xd1, 0xfd, 0x7b, 0x14, 0xa9,
    0xfd, 0x03, 0x05, 0x91, 0xfc, 0xab, 0x00, 0xf9,
};
constexpr std::uintptr_t kPlaceRoomOffset = 0x3d0a50;
constexpr std::array<std::uint8_t, 16> kPlaceRoomGuard = {
    0xff, 0x03, 0x02, 0xd1, 0xfd, 0x7b, 0x02, 0xa9,
    0xfd, 0x83, 0x00, 0x91, 0xfc, 0x6f, 0x03, 0xa9,
};
constexpr std::uintptr_t kHasPhotoDoorOffset = 0x3d5e44;
constexpr std::array<std::uint8_t, 16> kHasPhotoDoorGuard = {
    0xfd, 0x7b, 0xbe, 0xa9, 0xf4, 0x4f, 0x01, 0xa9,
    0xfd, 0x03, 0x00, 0x91, 0xb4, 0x36, 0x00, 0xf0,
};
constexpr std::uintptr_t kMakeDoorOffset = 0x454ee4;
constexpr std::array<std::uint8_t, 16> kMakeDoorGuard = {
    0xfd, 0x7b, 0xbc, 0xa9, 0xf7, 0x0b, 0x00, 0xf9,
    0xfd, 0x03, 0x00, 0x91, 0xf6, 0x57, 0x02, 0xa9,
};
constexpr std::uintptr_t kGridEntityDoorSetRoomTypesOffset = 0x385a78;
constexpr std::array<std::uint8_t, 16> kGridEntityDoorSetRoomTypesGuard = {
    0xfd, 0x7b, 0xbb, 0xa9, 0xf9, 0x0b, 0x00, 0xf9,
    0xfd, 0x03, 0x00, 0x91, 0xf8, 0x5f, 0x02, 0xa9,
};
constexpr std::uintptr_t kGridEntityDoorPlayAnimationOffset = 0x3840ac;
constexpr std::array<std::uint8_t, 16> kGridEntityDoorPlayAnimationGuard = {
    0xff, 0x03, 0x02, 0xd1, 0xfd, 0x7b, 0x02, 0xa9,
    0xfd, 0x83, 0x00, 0x91, 0xfc, 0x6f, 0x03, 0xa9,
};
constexpr std::uintptr_t kEntityRemoveOffset = 0x5d3e0;
constexpr std::array<std::uint8_t, 16> kEntityRemoveGuard = {
    0x08, 0x0c, 0x47, 0x39, 0x1f, 0x08, 0x07, 0x39,
    0x48, 0x00, 0x00, 0x34, 0xc0, 0x03, 0x5f, 0xd6,
};
constexpr std::uintptr_t kUpdateVisibilityOffset = 0x3d9638;
constexpr std::array<std::uint8_t, 16> kUpdateVisibilityGuard = {
    0xfd, 0x7b, 0xbb, 0xa9, 0xf9, 0x0b, 0x00, 0xf9,
    0xfd, 0x03, 0x00, 0x91, 0xf8, 0x5f, 0x02, 0xa9,
};

constexpr std::uintptr_t kDescriptorArrayBase = 0x18;
constexpr std::uintptr_t kDescriptorStride = 0x100;
constexpr std::uintptr_t kDescriptorCountOffset = 0x21510;
constexpr std::uintptr_t kGameRoomPointerOffset = 0x21550;
constexpr std::uintptr_t kGameStartingRoomIndexOffset = 0x21514;
constexpr std::uintptr_t kGameDungeonPlacementSeedOffset = 0x21580;
constexpr std::uintptr_t kDescriptorDimensionOffset = 0x0c;
constexpr std::uintptr_t kDescriptorDataOffset = 0x10;
constexpr std::uintptr_t kDescriptorAllowedDoorsOffset = 0x20;
// NS RoomDescriptor: AllowedDoors (64-bit) at +0x20, Doors[8] at +0x28.
constexpr std::uintptr_t kDescriptorDoorsOffset = 0x28;
constexpr std::uintptr_t kDescriptorSafeGridIndexOffset = 0x04;
constexpr std::uintptr_t kDescriptorDisplayFlagsOffset = 0x48;
constexpr std::uintptr_t kRoomConfigTypeOffset = 0x08;
constexpr std::uintptr_t kRoomConfigDoorsOffset = 0x40;
constexpr std::uintptr_t kRoomConfigShapeOffset = 0x5c;
constexpr std::uintptr_t kRoomDoorObjectTableOffset = 0xe30;
constexpr std::uintptr_t kRoomRedDoorOutlinesOffset = 0x7fa8;
constexpr std::uintptr_t kLevelStateFlagsOffset = 0x215f0;

constexpr std::int32_t kDoorSlotCount = 8;
constexpr std::int32_t kGridWidth = 13;
constexpr std::int32_t kMaxGridIndex = 168;
constexpr std::uint32_t kMaximumPlacementCount = 0x10000;

using GetRoomByIdx = const void* (*)(const void*, std::int32_t,
                                     std::int32_t);
using GetPlacementOffsets = const std::int32_t* const* (*)(std::int32_t);
using HasShapeSlot = bool (*)(std::int32_t, std::int32_t, bool);
using GetDoorPosition = PlacementVector (*)(const PlacementVector*,
                                            std::int32_t, std::int32_t, bool);
using PlaceRoom = bool (*)(void*, const void*, const void*, std::uint32_t,
                           std::int32_t);
using HasPhotoDoor = bool (*)(const void*);
using MakeDoor = void (*)(void*, std::int32_t);
using UpdateVisibility = void (*)(void*);
using SetRoomTypes = void (*)(void*, std::int32_t, std::int32_t);
using PlayAnimation = void (*)(void*);
using RemoveEntity = void (*)(void*);

api100_native::Cache g_GetRoomByIdxCache{};
api100_native::Cache g_PlacementOffsetsCache{};
api100_native::Cache g_HasShapeSlotCache{};
api100_native::Cache g_GetDoorSourceCache{};
api100_native::Cache g_GetDoorTargetCache{};
api100_native::Cache g_PlaceRoomCache{};
api100_native::Cache g_HasPhotoDoorCache{};
api100_native::Cache g_MakeDoorCache{};
api100_native::Cache g_UpdateVisibilityCache{};
api100_native::Cache g_SetRoomTypesCache{};
api100_native::Cache g_PlayAnimationCache{};
api100_native::Cache g_RemoveEntityCache{};

struct Natives {
    GetRoomByIdx getRoomByIdx{};
    GetPlacementOffsets getPlacementOffsets{};
    HasShapeSlot hasShapeSlot{};
    GetDoorPosition getDoorSource{};
    GetDoorPosition getDoorTarget{};
    PlaceRoom placeRoom{};
    HasPhotoDoor hasPhotoDoor{};
    MakeDoor makeDoor{};
    UpdateVisibility updateVisibility{};
    SetRoomTypes setRoomTypes{};
    PlayAnimation playAnimation{};
    RemoveEntity removeEntity{};
};

#if !defined(__SWITCH__)
RepentogonRoomPlacementNativeTestBindings g_TestBindings{};
#endif

template <class Fn>
Fn Resolve(lua_State* state, std::uintptr_t offset,
           const std::array<std::uint8_t, 16>& guard,
           api100_native::Cache& cache, Fn host, const char* name) {
    std::uintptr_t hostAddress{};
#if !defined(__SWITCH__)
    if (!host) {
        luaL_error(state, "RoomPlacement native adapter is unavailable: %s", name);
    }
    hostAddress = engine_call::AddressOfFunction(host);
#else
    static_cast<void>(host);
    static_cast<void>(name);
#endif
    return engine_call::AsFunction<Fn>(
        api100_native::Resolve(state, {offset, guard.data()}, cache, hostAddress));
}

Natives LoadNatives(lua_State* state) {
#if !defined(__SWITCH__)
    const auto& bindings = g_TestBindings;
    return {
        Resolve(state, kGetRoomByIdxOffset, kGetRoomByIdxGuard,
                g_GetRoomByIdxCache, bindings.getRoomByIdx, "GetRoomByIdx"),
        Resolve(state, kPlacementOffsetsOffset, kPlacementOffsetsGuard,
                g_PlacementOffsetsCache, bindings.getRoomPlacementOffsets,
                "get_room_placement_offsets"),
        Resolve(state, kHasShapeSlotOffset, kHasShapeSlotGuard,
                g_HasShapeSlotCache, bindings.hasShapeSlot, "has_shape_slot"),
        Resolve(state, kGetDoorSourceOffset, kGetDoorSourceGuard,
                g_GetDoorSourceCache, bindings.getDoorSource,
                "get_door_source_position"),
        Resolve(state, kGetDoorTargetOffset, kGetDoorTargetGuard,
                g_GetDoorTargetCache, bindings.getDoorTarget,
                "get_door_target_position"),
        Resolve(state, kPlaceRoomOffset, kPlaceRoomGuard, g_PlaceRoomCache,
                bindings.placeRoom, "Level::place_room"),
        Resolve(state, kHasPhotoDoorOffset, kHasPhotoDoorGuard,
                g_HasPhotoDoorCache, bindings.hasPhotoDoor, "HasPhotoDoor"),
        Resolve(state, kMakeDoorOffset, kMakeDoorGuard, g_MakeDoorCache,
                bindings.makeDoor, "Room::make_door"),
        Resolve(state, kUpdateVisibilityOffset, kUpdateVisibilityGuard,
                g_UpdateVisibilityCache, bindings.updateVisibility,
                "Level::UpdateVisibility"),
        Resolve(state, kGridEntityDoorSetRoomTypesOffset,
                kGridEntityDoorSetRoomTypesGuard, g_SetRoomTypesCache,
                bindings.setRoomTypes, "GridEntity_Door::SetRoomTypes"),
        Resolve(state, kGridEntityDoorPlayAnimationOffset,
                kGridEntityDoorPlayAnimationGuard, g_PlayAnimationCache,
                bindings.playAnimation, "GridEntity_Door::play_animation"),
        Resolve(state, kEntityRemoveOffset, kEntityRemoveGuard,
                g_RemoveEntityCache, bindings.removeEntity, "Entity::Remove"),
    };
#else
    return {
        Resolve(state, kGetRoomByIdxOffset, kGetRoomByIdxGuard,
                g_GetRoomByIdxCache, GetRoomByIdx{}, "GetRoomByIdx"),
        Resolve(state, kPlacementOffsetsOffset, kPlacementOffsetsGuard,
                g_PlacementOffsetsCache, GetPlacementOffsets{},
                "get_room_placement_offsets"),
        Resolve(state, kHasShapeSlotOffset, kHasShapeSlotGuard,
                g_HasShapeSlotCache, HasShapeSlot{}, "has_shape_slot"),
        Resolve(state, kGetDoorSourceOffset, kGetDoorSourceGuard,
                g_GetDoorSourceCache, GetDoorPosition{},
                "get_door_source_position"),
        Resolve(state, kGetDoorTargetOffset, kGetDoorTargetGuard,
                g_GetDoorTargetCache, GetDoorPosition{},
                "get_door_target_position"),
        Resolve(state, kPlaceRoomOffset, kPlaceRoomGuard, g_PlaceRoomCache,
                PlaceRoom{}, "Level::place_room"),
        Resolve(state, kHasPhotoDoorOffset, kHasPhotoDoorGuard,
                g_HasPhotoDoorCache, HasPhotoDoor{}, "HasPhotoDoor"),
        Resolve(state, kMakeDoorOffset, kMakeDoorGuard, g_MakeDoorCache,
                MakeDoor{}, "Room::make_door"),
        Resolve(state, kUpdateVisibilityOffset, kUpdateVisibilityGuard,
                g_UpdateVisibilityCache, UpdateVisibility{},
                "Level::UpdateVisibility"),
        Resolve(state, kGridEntityDoorSetRoomTypesOffset,
                kGridEntityDoorSetRoomTypesGuard, g_SetRoomTypesCache,
                SetRoomTypes{}, "GridEntity_Door::SetRoomTypes"),
        Resolve(state, kGridEntityDoorPlayAnimationOffset,
                kGridEntityDoorPlayAnimationGuard, g_PlayAnimationCache,
                PlayAnimation{}, "GridEntity_Door::play_animation"),
        Resolve(state, kEntityRemoveOffset, kEntityRemoveGuard,
                g_RemoveEntityCache, RemoveEntity{}, "Entity::Remove"),
    };
#endif
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

template <class T>
bool TryRead(std::uintptr_t object, std::uintptr_t offset, T* value) noexcept {
    return value != nullptr &&
           engine_memory::ReadField(object, offset, value,
                                    engine_memory::EngineMemoryReadable);
}

int64_t RoomIndexToLine(std::int32_t index) noexcept {
    return static_cast<std::int64_t>(index) / kGridWidth;
}

int32_t RoomIndexToColumn(std::int32_t index) noexcept {
    return index % kGridWidth;
}

int32_t RoomCoordsToIndex(int32_t column, int32_t line) noexcept {
    return line * kGridWidth + column;
}

int32_t NormalizeShape(int32_t shape) noexcept {
    if (shape == 2 || shape == 3) return 1;
    if (shape == 5) return 4;
    if (shape == 7) return 6;
    return shape;
}

std::array<int32_t, 2> ShapeDimensions(int32_t shape) noexcept {
    switch (shape) {
    case 1:
    case 2:
    case 3:
        return {1, 1};
    case 4:
    case 5:
        return {1, 2};
    case 6:
    case 7:
        return {2, 1};
    default:
        return {2, 2};
    }
}

struct RoomData {
    std::uintptr_t descriptor{};
    std::uintptr_t data{};
    std::int32_t gridIndex{};
    std::int32_t dimension{};
    std::int32_t type{};
    std::int32_t shape{};
    std::uint32_t doors{};
};

bool TryRoomData(std::uintptr_t descriptor, RoomData* result) noexcept {
    if (!result || descriptor == 0 ||
        !engine_memory::EngineMemoryReadable(descriptor, kDescriptorStride)) {
        return false;
    }
    std::uintptr_t data{};
    std::int32_t type{}, shape{};
    std::uint32_t doors{};
    if (!TryRead(descriptor, kDescriptorDataOffset, &data) || data == 0 ||
        !TryRead(data, kRoomConfigTypeOffset, &type) ||
        !TryRead(data, kRoomConfigDoorsOffset, &doors) ||
        !TryRead(data, kRoomConfigShapeOffset, &shape)) {
        return false;
    }
    RoomData value{};
    value.descriptor = descriptor;
    value.data = data;
    TryRead(descriptor, 0, &value.gridIndex);
    TryRead(descriptor, kDescriptorDimensionOffset, &value.dimension);
    value.type = type;
    value.shape = shape;
    value.doors = doors;
    *result = value;
    return true;
}

struct DoorSourceTarget {
    PlacementVector source{-1, -1};
    PlacementVector target{-1, -1};
};

bool ValidPosition(const PlacementVector& value) noexcept {
    return value.x >= 0 && value.x < kGridWidth &&
           value.y >= 0 && value.y < kGridWidth;
}

bool Adjacent(const PlacementVector& a, const PlacementVector& b) noexcept {
    return (a.x == b.x || a.y == b.y) &&
           (std::abs(a.x - b.x) == 1 || std::abs(a.y - b.y) == 1);
}

bool ValidDoorTarget(const DoorSourceTarget& value) noexcept {
    return ValidPosition(value.source) && ValidPosition(value.target) &&
           Adjacent(value.source, value.target);
}

bool Connects(const DoorSourceTarget& a, const DoorSourceTarget& b) noexcept {
    return a.source.x == b.target.x && a.source.y == b.target.y &&
           a.target.x == b.source.x && a.target.y == b.source.y;
}

int32_t DoorTargetIndex(const DoorSourceTarget& value) noexcept {
    return RoomCoordsToIndex(value.target.x, value.target.y);
}

void* AsObject(std::uintptr_t address) noexcept {
    return engine_memory::AsObject(address);
}

DoorSourceTarget GetDoorSourceTarget(const Natives& natives,
                                     std::int32_t gridIndex,
                                     std::int32_t shape,
                                     std::int32_t doorSlot,
                                     bool normalize) {
    const auto normalized = normalize ? NormalizeShape(shape) : shape;
    const PlacementVector position{RoomIndexToColumn(gridIndex),
                                   static_cast<std::int32_t>(
                                       RoomIndexToLine(gridIndex))};
    const auto source = natives.getDoorSource(&position, normalized, doorSlot,
                                              false);
    const auto target = natives.getDoorTarget(&position, normalized, doorSlot,
                                              false);
    return {source, target};
}

std::map<std::int32_t, RoomData> GetNeighbors(const Natives& natives,
                                               std::uintptr_t level,
                                               std::int32_t gridIndex,
                                               std::int32_t shape,
                                               std::int32_t dimension) {
    std::map<std::int32_t, RoomData> result;
    for (std::int32_t slot = 0; slot < kDoorSlotCount; ++slot) {
        const auto target =
            GetDoorSourceTarget(natives, gridIndex, shape, slot, true);
        if (!ValidDoorTarget(target)) continue;
        const auto* descriptor = natives.getRoomByIdx(
            AsObject(level), DoorTargetIndex(target), dimension);
        RoomData data{};
        if (descriptor &&
            TryRoomData(engine_memory::AddressOf(descriptor), &data)) {
            result.emplace(slot, data);
        }
    }
    return result;
}

std::array<std::int32_t, 2> PossibleReturnSlots(std::int32_t slot) noexcept {
    const auto base = (slot + 2) % 4;
    return {base, base + 4};
}

std::uint32_t DoorMask(std::int32_t slot) noexcept {
    return 1U << static_cast<std::uint32_t>(slot);
}

bool CanPlace(lua_State* state, const Natives& natives, std::uintptr_t level,
              const RoomData& room, std::int32_t column, std::int32_t line,
              std::int32_t dimension, bool allowMultipleDoors,
              bool allowSpecialNeighbors, bool allowNoNeighbors) {
    if (column < 0 || column >= kGridWidth || line < 0 || line >= kGridWidth ||
        room.shape < 1 || room.shape > 12) {
        return false;
    }
    const auto* offsets = *natives.getPlacementOffsets(room.shape);
    if (!offsets) return false;
    for (int i = 0; i < 4; ++i) {
        const auto x = offsets[i * 2];
        const auto y = offsets[i * 2 + 1];
        if (x == -1 || y == -1) break;
        if (x < 0 || y < 0 || x > 1 || y > 1) return false;
        const auto newColumn = column + x;
        const auto newLine = line + y;
        if (newColumn >= kGridWidth || newLine >= kGridWidth) return false;
        RoomData occupied{};
        const auto* descriptor = natives.getRoomByIdx(
            AsObject(level), RoomCoordsToIndex(newColumn, newLine), dimension);
        if (descriptor && TryRoomData(engine_memory::AddressOf(descriptor),
                                      &occupied) &&
            occupied.data != 0) {
            return false;
        }
    }

    const auto gridIndex = RoomCoordsToIndex(column, line);
    const auto neighbors =
        GetNeighbors(natives, level, gridIndex, room.shape, dimension);
    if (!allowNoNeighbors && neighbors.empty()) return false;

    auto doorMask = static_cast<std::int32_t>(room.doors);
    if (doorMask < 0) {
        doorMask = 0;
        for (std::int32_t slot = 0; slot < kDoorSlotCount; ++slot) {
            if (natives.hasShapeSlot(room.shape, slot, false)) {
                doorMask |= static_cast<std::int32_t>(DoorMask(slot));
            }
        }
    }

    int doors = 0;
    bool hasSecretNeighbor = false;
    bool hasNonSecretNeighbor = false;
    const auto startingRoom =
        Read<std::uint32_t>(state, level, kGameStartingRoomIndexOffset,
                            "Game starting room index");
    const auto stage =
        Read<std::int32_t>(state, level, 0, "Level stage");
    const bool photoDoor = natives.hasPhotoDoor(AsObject(level));
    for (const auto& [slot, neighbor] : neighbors) {
        if ((doorMask & DoorMask(slot)) == 0) return false;
        if (neighbor.type == 5) return false;
        if (!allowSpecialNeighbors && neighbor.type > 1 &&
            neighbor.type != 7) {
            return false;
        }
        const auto source =
            GetDoorSourceTarget(natives, gridIndex, room.shape, slot, true);
        bool connects = false;
        for (const auto returnSlot : PossibleReturnSlots(slot)) {
            if ((neighbor.doors & DoorMask(returnSlot)) == 0) continue;
            const auto target = GetDoorSourceTarget(
                natives, neighbor.gridIndex, neighbor.shape, returnSlot, true);
            if (!Connects(source, target)) continue;
            const bool forbidden =
                returnSlot == 1 &&
                static_cast<std::uint32_t>(neighbor.gridIndex) == startingRoom &&
                (photoDoor || stage == 11);
            if (!forbidden) {
                connects = true;
                break;
            }
        }
        if (!connects) return false;
        if (neighbor.type == 7 || neighbor.type == 8) {
            hasSecretNeighbor = true;
        } else {
            hasNonSecretNeighbor = true;
            ++doors;
        }
    }
    if (!allowMultipleDoors && doors > 1) return false;
    if (hasSecretNeighbor && !hasNonSecretNeighbor &&
        !allowSpecialNeighbors) {
        return false;
    }
    return true;
}

RoomData RequireConfig(lua_State* state) {
    std::uintptr_t config{};
    if (!ResolveApi500RoomConfig(state, 2, &config) || !config) {
        luaL_error(state, "RoomConfig reference is no longer available");
    }
    RoomData result{};
    result.data = config;
    result.shape = Read<std::int32_t>(state, config, kRoomConfigShapeOffset,
                                      "RoomConfig shape");
    result.doors = Read<std::uint32_t>(state, config, kRoomConfigDoorsOffset,
                                       "RoomConfig doors");
    return result;
}

int32_t CheckDimension(lua_State* state, int argument) {
    const auto value = static_cast<std::int32_t>(
        luaL_optinteger(state, argument, -1));
    if (value < -1 || value > 2) {
        luaL_argerror(state, argument, "Invalid Dimension");
    }
    return value;
}

std::uint32_t CheckSeed(lua_State* state, int argument, std::int32_t shape,
                        std::int32_t x, std::int32_t y,
                        std::uintptr_t level) {
    const auto supplied = luaL_optinteger(state, argument, 0);
    if (supplied < 0) {
        luaL_argerror(state, argument, "Invalid Seed");
    }
    if (supplied != 0) return static_cast<std::uint32_t>(supplied);

    const auto dungeonSeed =
        Read<std::uint32_t>(state, level, kGameDungeonPlacementSeedOffset,
                            "Game dungeon placement seed");
    const auto seed =
        (dungeonSeed + static_cast<std::uint32_t>(y) * 929U) *
        (static_cast<std::uint32_t>(x) + static_cast<std::uint32_t>(shape));
    const auto setSeed = LuaRuntime::RngSetSeedThunk();
    const auto next = LuaRuntime::RngNextThunk();
    if (!setSeed || !next || !LuaRuntime::ValidateRngSetSeedBinding(setSeed) ||
        !LuaRuntime::ValidateRngNextBinding(next)) {
        luaL_error(state, "Room placement RNG bindings are unavailable");
    }
    LuaRuntime::RngHandle rng{};
    using SetSeedFn = void (*)(void*, std::uint32_t, std::uint32_t);
    using NextFn = void (*)(void*);
    engine_call::AsFunction<SetSeedFn>(setSeed)(rng.storage.data(), seed, 35);
    engine_call::AsFunction<NextFn>(next)(rng.storage.data());
    std::uint32_t result{};
    std::memcpy(&result, rng.storage.data(), sizeof(result));
    return std::max(result, 1U);
}

int PushRoomDescriptor(lua_State* state, std::uintptr_t descriptor,
                       std::uintptr_t level) {
    auto* handle = static_cast<LuaRuntime::RoomDescriptorHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RoomDescriptorHandle)));
    handle->descriptor = AsObject(descriptor);
    handle->level = AsObject(level);
    handle->moduleBase = LuaRuntime::EngineModuleBase();
    luaL_getmetatable(state, LuaRuntime::kRoomDescriptorMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

bool WriteU32(std::uintptr_t object, std::uintptr_t offset,
              std::uint32_t value) noexcept {
    return engine_memory::WriteField(object, offset, value,
                                     engine_memory::EngineMemoryWritable);
}

bool WritePointer(std::uintptr_t object, std::uintptr_t offset,
                  std::uintptr_t value) noexcept {
    return engine_memory::WriteField(object, offset, value,
                                     engine_memory::EngineMemoryWritable);
}

int32_t CurrentRoomFrameCount(std::uintptr_t room) noexcept {
#if !defined(__SWITCH__)
    if (const auto host = LuaRuntime::GetRoomGetFrameCountHostFunction()) {
        return host(engine_memory::AsObject(room));
    }
#endif
    const auto method = LuaRuntime::RoomGetFrameCountThunk();
    if (!method) return 0;
    using GetFrameCount = std::int32_t (*)(const void*);
    return engine_call::AsFunction<GetFrameCount>(method)(
        engine_memory::AsObject(room));
}

std::uintptr_t PlaceDescriptor(lua_State* state, const Natives& natives,
                               std::uintptr_t level, std::uintptr_t config,
                               std::int32_t column, std::int32_t line,
                               std::int32_t dimension, std::uint32_t seed,
                               bool allowMultipleDoors,
                               bool allowSpecialNeighbors,
                               bool allowNoNeighbors) {
    RoomData configData{};
    configData.data = config;
    configData.shape = Read<std::int32_t>(
        state, config, kRoomConfigShapeOffset, "RoomConfig shape");
    configData.doors = Read<std::uint32_t>(
        state, config, kRoomConfigDoorsOffset, "RoomConfig doors");
    if (!CanPlace(state, natives, level, configData, column, line, dimension,
                  allowMultipleDoors, allowSpecialNeighbors,
                  allowNoNeighbors)) {
        lua_pushnil(state);
        return 0;
    }

    std::array<std::uint8_t, 0x60> generatorRoom{};
    const auto dimensions = ShapeDimensions(configData.shape);
    const auto put32 = [&](std::uintptr_t offset, std::uint32_t value) {
        std::memcpy(generatorRoom.data() + offset, &value, sizeof(value));
    };
    put32(0x08, static_cast<std::uint32_t>(column));
    put32(0x0c, static_cast<std::uint32_t>(line));
    put32(0x10, static_cast<std::uint32_t>(dimensions[0]));
    put32(0x14, static_cast<std::uint32_t>(dimensions[1]));
    put32(0x18, static_cast<std::uint32_t>(configData.shape));
    if (!natives.placeRoom(AsObject(level), generatorRoom.data(),
                           AsObject(config), seed, dimension)) {
        lua_pushnil(state);
        return 0;
    }

    const auto count = Read<std::uint32_t>(
        state, level, kDescriptorCountOffset, "Level room count");
    if (count == 0 || count > kMaximumPlacementCount) {
        lua_pushnil(state);
        return 0;
    }
    const auto descriptor =
        level + kDescriptorArrayBase + static_cast<std::uintptr_t>(count - 1) *
                                           kDescriptorStride;
    RoomData placed{};
    if (!TryRoomData(descriptor, &placed) || placed.data == 0) {
        lua_pushnil(state);
        return 0;
    }
    if (!WriteU32(descriptor, kDescriptorAllowedDoorsOffset, 0)) {
        luaL_error(state, "RoomDescriptor AllowedDoors is not writable");
    }

    const auto currentRoom =
        Read<std::uintptr_t>(state, level, kGameRoomPointerOffset,
                             "current Room");
    std::uintptr_t currentDescriptor{};
    if (currentRoom) {
        TryRead(currentRoom, kRoomDescriptorPointerOffset, &currentDescriptor);
    }
    const auto neighbors = GetNeighbors(natives, level, placed.gridIndex,
                                        placed.shape, placed.dimension);
    for (const auto& [slot, neighbor] : neighbors) {
        const auto source =
            GetDoorSourceTarget(natives, placed.gridIndex, placed.shape, slot,
                                false);
        if ((placed.doors & DoorMask(slot)) == 0 || !ValidDoorTarget(source)) {
            continue;
        }
        for (const auto returnSlot : PossibleReturnSlots(slot)) {
            const auto target = GetDoorSourceTarget(
                natives, neighbor.gridIndex, neighbor.shape, returnSlot,
                false);
            if (!Connects(source, target)) continue;

            const auto targetIndex = static_cast<std::uint32_t>(
                DoorTargetIndex(source));
            if (!WriteU32(descriptor, kDescriptorDoorsOffset +
                                      static_cast<std::uintptr_t>(slot) * 4,
                          targetIndex) ||
                !WriteU32(neighbor.descriptor,
                          kDescriptorDoorsOffset +
                              static_cast<std::uintptr_t>(returnSlot) * 4,
                          static_cast<std::uint32_t>(
                              DoorTargetIndex(target)))) {
                luaL_error(state, "RoomDescriptor doors are not writable");
            }
            const auto placedAllowed = Read<std::uint32_t>(
                state, descriptor, kDescriptorAllowedDoorsOffset,
                "RoomDescriptor AllowedDoors");
            const auto neighborAllowed = Read<std::uint32_t>(
                state, neighbor.descriptor, kDescriptorAllowedDoorsOffset,
                "neighbor RoomDescriptor AllowedDoors");
            if (!WriteU32(descriptor, kDescriptorAllowedDoorsOffset,
                          placedAllowed | DoorMask(slot)) ||
                !WriteU32(neighbor.descriptor, kDescriptorAllowedDoorsOffset,
                          neighborAllowed | DoorMask(returnSlot))) {
                luaL_error(state, "RoomDescriptor AllowedDoors is not writable");
            }
            if (currentDescriptor && neighbor.descriptor == currentDescriptor) {
                std::uintptr_t door{};
                const auto doorSlotOffset =
                    kRoomDoorObjectTableOffset +
                    static_cast<std::uintptr_t>(returnSlot) *
                        sizeof(std::uintptr_t);
                static_cast<void>(
                    TryRead(currentRoom, doorSlotOffset, &door));
                if (!door) {
                    natives.makeDoor(AsObject(currentRoom), returnSlot);
                    static_cast<void>(
                        TryRead(currentRoom, doorSlotOffset, &door));
                }
                if (door) {
                    const auto safeGridIndex = Read<std::int32_t>(
                        state, descriptor, kDescriptorSafeGridIndexOffset,
                        "RoomDescriptor SafeGridIndex");
                    if (!engine_memory::WriteField(
                            door, kGridEntityDoorTargetRoomIndexOffset,
                            safeGridIndex,
                            engine_memory::EngineMemoryWritable)) {
                        luaL_error(state,
                                   "GridEntity_Door target room is not writable");
                    }
                    natives.setRoomTypes(engine_memory::AsObject(door),
                                         neighbor.type, placed.type);
                    if (CurrentRoomFrameCount(currentRoom) > 0) {
                        natives.playAnimation(engine_memory::AsObject(door));
                    }
                    const auto outlineOffset =
                        kRoomRedDoorOutlinesOffset +
                        static_cast<std::uintptr_t>(returnSlot) *
                            sizeof(std::uintptr_t);
                    std::uintptr_t outline{};
                    if (TryRead(currentRoom, outlineOffset, &outline) &&
                        outline != 0) {
                        natives.removeEntity(
                            engine_memory::AsObject(outline));
                        if (!WritePointer(currentRoom, outlineOffset, 0)) {
                            luaL_error(state,
                                       "Room red-door outline is not writable");
                        }
                    }
                }
            }
        }
    }
    const auto displayFlags = Read<std::uint32_t>(
        state, descriptor, kDescriptorDisplayFlagsOffset,
        "RoomDescriptor DisplayFlags");
    const auto levelState = Read<std::uint64_t>(
        state, level, kLevelStateFlagsOffset, "Level state flags");
    const bool compass = (levelState & (std::uint64_t{1} << 7)) != 0;
    const bool map = (levelState & (std::uint64_t{1} << 8)) != 0;
    const bool blueMap = (levelState & (std::uint64_t{1} << 9)) != 0;
    const bool fullMap = (levelState & (std::uint64_t{1} << 10)) != 0;
    const bool secret = placed.type == 7;
    const bool superSecret = placed.type == 8;
    const bool ultraSecret = placed.type == 29;
    auto updatedDisplayFlags = displayFlags;
    if (fullMap || (blueMap && (secret || superSecret)) ||
        (compass && placed.type > 1 && !secret && !superSecret &&
         !ultraSecret)) {
        updatedDisplayFlags |= 5;
    } else if (map) {
        updatedDisplayFlags |= 1;
    }
    if (updatedDisplayFlags != displayFlags &&
        !WriteU32(descriptor, kDescriptorDisplayFlagsOffset,
                  updatedDisplayFlags)) {
        luaL_error(state, "RoomDescriptor DisplayFlags is not writable");
    }
    natives.updateVisibility(AsObject(level));
    return PushRoomDescriptor(state, descriptor, level);
}

}  // namespace

int RepentogonLevelTryPlaceRoom(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        return luaL_error(state, "Level.TryPlaceRoom requires the game thread");
    }
    const auto level = ResolveEngineReceiver(state, FieldReceipt::Level, 1);
    if (!level) return luaL_error(state, "Level reference is no longer available");
    const auto config = RequireConfig(state);
    const auto gridIndex =
        static_cast<std::int32_t>(luaL_checkinteger(state, 3));
    if (gridIndex < 0 || gridIndex > kMaxGridIndex) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const auto dimension = CheckDimension(state, 4);
    const auto column = RoomIndexToColumn(gridIndex);
    const auto line = static_cast<std::int32_t>(RoomIndexToLine(gridIndex));
    // The seed shape must be read before the native placement transaction.
    const auto seed = CheckSeed(state, 5, config.shape, column, line, level);
    const bool allowMultipleDoors =
        lua_toboolean(state, 6) != 0 || lua_isnoneornil(state, 6);
    const bool allowSpecialNeighbors =
        lua_toboolean(state, 7) != 0;
    const bool allowNoNeighbors =
        lua_toboolean(state, 8) != 0;
    const auto natives = LoadNatives(state);
    const int pushed = static_cast<int>(PlaceDescriptor(
        state, natives, level, config.data, column, line, dimension, seed,
        allowMultipleDoors, allowSpecialNeighbors, allowNoNeighbors));
    return pushed;
}

int RepentogonLevelTryPlaceRoomAtDoor(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        return luaL_error(state,
                          "Level.TryPlaceRoomAtDoor requires the game thread");
    }
    const auto level = ResolveEngineReceiver(state, FieldReceipt::Level, 1);
    if (!level) return luaL_error(state, "Level reference is no longer available");
    const auto config = RequireConfig(state);
    const auto descriptor = ResolveRoomDescriptorArgument(state, 3);
    if (!descriptor) {
        lua_pushboolean(state, 0);
        return 1;
    }
    RoomData existing{};
    if (!TryRoomData(descriptor, &existing) || existing.data == 0) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const auto doorSlot =
        static_cast<std::int32_t>(luaL_checkinteger(state, 4));
    const auto natives = LoadNatives(state);
    const auto door = GetDoorSourceTarget(
        natives, existing.gridIndex, existing.shape, doorSlot, false);
    if (!ValidDoorTarget(door)) {
        lua_pushboolean(state, 0);
        return 1;
    }
    const auto seed = CheckSeed(state, 5, config.shape, door.target.x,
                                door.target.y, level);
    const bool allowMultipleDoors =
        lua_toboolean(state, 6) != 0 || lua_isnoneornil(state, 6);
    const bool allowSpecialNeighbors = lua_toboolean(state, 7) != 0;

    std::vector<PlacementVector> placements;
    for (const auto returnSlot : PossibleReturnSlots(doorSlot)) {
        const auto returnDoor = GetDoorSourceTarget(
            natives, DoorTargetIndex(door), config.shape, returnSlot, false);
        if (!ValidDoorTarget(returnDoor)) continue;
        const auto offsetX = door.target.x - returnDoor.source.x;
        const auto offsetY = door.target.y - returnDoor.source.y;
        placements.push_back({door.target.x + offsetX,
                              door.target.y + offsetY});
    }
    if ((seed & 1U) == 0 && placements.size() > 1) {
        std::swap(placements[0], placements[1]);
    }
    for (const auto& placement : placements) {
        if (!ValidPosition(placement)) continue;
        const auto room =
            PlaceDescriptor(state, natives, level, config.data, placement.x,
                            placement.y, existing.dimension, seed,
                            allowMultipleDoors, allowSpecialNeighbors, false);
        if (room != 0) return room;
    }
    lua_pushnil(state);
    return 1;
}

int RegisterRepentogonRoomPlacementApi(lua_State* state) {
    if (!state) return 0;
    luaL_getmetatable(state, LuaRuntime::kLevelMetatable);
    if (!lua_istable(state, -1)) {
        luaL_error(state, "Level metatable is unavailable");
    }
    static_cast<void>(AttachOwnerMethods(state, "Level", nullptr, 0));
    lua_pop(state, 1);
    return 0;
}

#if !defined(__SWITCH__)
void SetRepentogonRoomPlacementNativeTestBindings(
    RepentogonRoomPlacementNativeTestBindings bindings) noexcept {
    g_TestBindings = bindings;
}
#endif

}  // namespace isaac::runtime
