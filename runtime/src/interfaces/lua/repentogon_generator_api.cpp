#include "interfaces/lua/repentogon_generator_api.hpp"

#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

using LevelGeneratorHandle = ::isaac::runtime::LevelGeneratorHandle;
using LevelGeneratorRoomHandle = ::isaac::runtime::LevelGeneratorRoomHandle;
using BossPoolHandle = ::isaac::runtime::BossPoolHandle;

// Switch layout of LevelGenerator::Room is 0x60 bytes. The PC layout has
// 32-bit pointers, so its field offsets cannot be reused here.
constexpr std::size_t kGeneratorRoomStride = 0x60;
constexpr std::uintptr_t kRoomGenerationIndex = 0x04;
constexpr std::uintptr_t kRoomColumn = 0x08;
constexpr std::uintptr_t kRoomLine = 0x0c;
constexpr std::uintptr_t kRoomShape = 0x18;
constexpr std::uintptr_t kRoomDoors = 0x20;
constexpr std::uintptr_t kRoomNeighborsBegin = 0x38;
constexpr std::uintptr_t kRoomNeighborsRoot = 0x40;
constexpr std::uintptr_t kRoomNeighborsSize = 0x48;
constexpr std::uintptr_t kRoomDeadEnd = 0x54;

constexpr std::uintptr_t kGeneratorRooms = 0x368;
constexpr std::uintptr_t kGeneratorDeadEnds = 0x380;
constexpr std::uintptr_t kGeneratorNonDeadEnds = 0x398;
constexpr std::uintptr_t kGeneratorRoomsEnd = 0x370;

constexpr std::size_t kMaxVectorEntries = 0x10000;
constexpr std::size_t kMaxNeighbors = 0x1000;

constexpr std::uintptr_t kPoolName = 0x00;
constexpr std::uintptr_t kPoolEntries = 0x18;
constexpr std::uintptr_t kPoolEntriesEnd = 0x20;
constexpr std::uintptr_t kPoolTotalWeight = 0x30;
constexpr std::uintptr_t kPoolRng = 0x34;
constexpr std::uintptr_t kPoolDoubleTroubleStart = 0x44;
constexpr std::size_t kPoolStride = 0x48;
constexpr std::size_t kEntryStride = 0x14;

template <class T>
bool Read(std::uintptr_t object, std::uintptr_t offset, T* value) noexcept {
    return value != nullptr &&
           engine_memory::ReadField(object, offset, value,
                                    engine_memory::EngineMemoryReadable);
}

bool Readable(std::uintptr_t object, std::size_t size) noexcept {
    return object != 0 && size != 0 &&
           engine_memory::EngineMemoryReadable(object, size);
}

bool Live(const LevelGeneratorHandle& handle) noexcept {
    return handle.generator != nullptr &&
           handle.moduleBase != 0 &&
           handle.moduleBase == LuaRuntime::EngineModuleBase() &&
           Readable(engine_memory::AddressOf(handle.generator), 0x3b0);
}

bool Live(const LevelGeneratorRoomHandle& handle) noexcept {
    return handle.room != nullptr &&
           handle.moduleBase != 0 &&
           handle.moduleBase == LuaRuntime::EngineModuleBase() &&
           Readable(engine_memory::AddressOf(handle.room), kGeneratorRoomStride);
}

bool Live(const BossPoolHandle& handle) noexcept {
    return handle.pool != nullptr &&
           handle.moduleBase != 0 &&
           handle.moduleBase == LuaRuntime::EngineModuleBase() &&
           Readable(engine_memory::AddressOf(handle.pool), kPoolStride);
}

LevelGeneratorHandle* CheckGenerator(lua_State* state, int index) {
    auto* handle = static_cast<LevelGeneratorHandle*>(
        luaL_checkudata(state, index, kLevelGeneratorMetatable));
    if (!handle || lua_rawlen(state, index) < sizeof(LevelGeneratorHandle) ||
        !Live(*handle)) {
        luaL_error(state, "LevelGenerator reference is no longer available");
    }
    return handle;
}

LevelGeneratorRoomHandle* CheckRoom(lua_State* state, int index) {
    auto* handle = static_cast<LevelGeneratorRoomHandle*>(
        luaL_checkudata(state, index, kLevelGeneratorRoomMetatable));
    if (!handle || lua_rawlen(state, index) < sizeof(LevelGeneratorRoomHandle) ||
        !Live(*handle)) {
        luaL_error(state, "LevelGeneratorRoom reference is no longer available");
    }
    return handle;
}

BossPoolHandle* CheckPool(lua_State* state, int index) {
    auto* handle = static_cast<BossPoolHandle*>(
        luaL_checkudata(state, index, kBossPoolMetatable));
    if (!handle || lua_rawlen(state, index) < sizeof(BossPoolHandle) ||
        !Live(*handle)) {
        luaL_error(state, "BossPool reference is no longer available");
    }
    return handle;
}

void RequireNoArguments(lua_State* state, const char* name) {
    if (lua_gettop(state) != 1) {
        luaL_error(state, "%s accepts no arguments", name);
    }
}

std::uintptr_t RoomAt(LevelGeneratorHandle* generator, std::size_t index) {
    const auto begin = [&]() {
        std::uintptr_t begin{};
        if (!Read(engine_memory::AddressOf(generator->generator),
                  kGeneratorRooms, &begin)) {
            return std::uintptr_t{0};
        }
        return begin;
    }();
    const auto end = [&]() {
        std::uintptr_t end{};
        if (!Read(engine_memory::AddressOf(generator->generator),
                  kGeneratorRoomsEnd, &end)) {
            return std::uintptr_t{0};
        }
        return end;
    }();
    if (begin == 0 && end == 0) {
        return 0;
    }
    if (begin == 0 || end < begin ||
        (end - begin) % kGeneratorRoomStride != 0 ||
        (end - begin) / kGeneratorRoomStride > kMaxVectorEntries) {
        return 0;
    }
    if (index >= (end - begin) / kGeneratorRoomStride) {
        return 0;
    }
    const auto room = begin + index * kGeneratorRoomStride;
    if (!Readable(room, kGeneratorRoomStride)) {
        return 0;
    }
    return room;
}

void PushRoom(lua_State* state, std::uintptr_t generator,
              std::uintptr_t room) {
    PushRepentogonLevelGeneratorRoomHandle(
        state, engine_memory::AsObject(generator), engine_memory::AsObject(room));
}

int PushRooms(lua_State* state, LevelGeneratorHandle* generator,
              std::uintptr_t vector) {
    std::uintptr_t begin{};
    std::uintptr_t end{};
    if (!Read(engine_memory::AddressOf(generator->generator), vector, &begin) ||
        !Read(engine_memory::AddressOf(generator->generator),
              vector + sizeof(std::uintptr_t), &end)) {
        return luaL_error(state, "LevelGenerator room vector is unavailable");
    }
    if (begin == 0 && end == 0) {
        lua_createtable(state, 0, 0);
        return 1;
    }
    if (begin == 0 || end < begin ||
        (end - begin) % kGeneratorRoomStride != 0 ||
        (end - begin) / kGeneratorRoomStride > kMaxVectorEntries) {
        return luaL_error(state, "LevelGenerator room vector is invalid");
    }
    const auto count = (end - begin) / kGeneratorRoomStride;
    lua_createtable(state, static_cast<int>(count), 0);
    for (std::size_t index = 0; index < count; ++index) {
        PushRoom(state, engine_memory::AddressOf(generator->generator),
                 begin + index * kGeneratorRoomStride);
        lua_rawseti(state, -2, static_cast<lua_Integer>(index + 1));
    }
    return 1;
}

int PushRoomIndexList(lua_State* state, LevelGeneratorHandle* generator,
                      std::uintptr_t vector) {
    std::uintptr_t begin{};
    std::uintptr_t end{};
    const auto generatorAddress =
        engine_memory::AddressOf(generator->generator);
    if (!Read(generatorAddress, vector, &begin) ||
        !Read(generatorAddress, vector + sizeof(std::uintptr_t), &end)) {
        return luaL_error(state, "LevelGenerator room index vector is unavailable");
    }
    if (begin == 0 && end == 0) {
        lua_createtable(state, 0, 0);
        return 1;
    }
    if (begin == 0 || end < begin || (end - begin) % sizeof(std::int32_t) != 0 ||
        (end - begin) / sizeof(std::int32_t) > kMaxVectorEntries) {
        return luaL_error(state, "LevelGenerator room index vector is invalid");
    }
    const auto count = (end - begin) / sizeof(std::int32_t);
    lua_createtable(state, static_cast<int>(count), 0);
    for (std::size_t index = 0; index < count; ++index) {
        std::int32_t roomIndex{};
        if (!Read(begin, index * sizeof(std::int32_t), &roomIndex) ||
            roomIndex < 0) {
            return luaL_error(state, "LevelGenerator room index is invalid");
        }
        const auto room = RoomAt(generator, static_cast<std::size_t>(roomIndex));
        if (!room) {
            return luaL_error(state, "LevelGenerator room index is out of range");
        }
        PushRoom(state, generatorAddress, room);
        lua_rawseti(state, -2, static_cast<lua_Integer>(index + 1));
    }
    return 1;
}

int PushNeighbors(lua_State* state, const LevelGeneratorRoomHandle& handle) {
    const auto room = engine_memory::AddressOf(handle.room);
    std::uintptr_t begin{};
    std::uintptr_t end{};
    std::uint64_t size{};
    if (!Read(room, kRoomNeighborsBegin, &begin) ||
        !Read(room, kRoomNeighborsSize, &size)) {
        return luaL_error(state, "LevelGeneratorRoom neighbors are unavailable");
    }
    end = room + kRoomNeighborsRoot;
    if (begin == end || size == 0) {
        lua_createtable(state, 0, 0);
        return 1;
    }
    if (begin == 0 || size > kMaxNeighbors) {
        return luaL_error(state, "LevelGeneratorRoom neighbors are invalid");
    }
    lua_createtable(state, static_cast<int>(size), 0);
    std::uintptr_t node = begin;
    std::size_t emitted = 0;
    while (node != end && emitted < size && emitted < kMaxNeighbors) {
        if (!Readable(node, 0x20)) {
            return luaL_error(state, "LevelGeneratorRoom neighbor node is unreadable");
        }
        std::int32_t value{};
        std::uintptr_t right{};
        std::uintptr_t left{};
        std::uintptr_t parent{};
        if (!Read(node, 0x1c, &value) || !Read(node, 0x08, &right) ||
            !Read(node, 0x00, &left) || !Read(node, 0x10, &parent)) {
            return luaL_error(state, "LevelGeneratorRoom neighbor node is invalid");
        }
        lua_pushinteger(state, static_cast<lua_Integer>(value));
        lua_rawseti(state, -2, static_cast<lua_Integer>(emitted + 1));
        ++emitted;
        if (right != 0) {
            node = right;
            while (true) {
                std::uintptr_t childLeft{};
                if (!Readable(node, 0x20) ||
                    !Read(node, 0x00, &childLeft)) {
                    return luaL_error(state, "LevelGeneratorRoom neighbor tree is invalid");
                }
                if (childLeft == 0) break;
                node = childLeft;
            }
        } else {
            while (parent != end) {
                std::uintptr_t parentRight{};
                if (!Readable(parent, 0x20) ||
                    !Read(parent, 0x08, &parentRight)) {
                    return luaL_error(state, "LevelGeneratorRoom neighbor tree is invalid");
                }
                if (node != parentRight) break;
                node = parent;
                if (!Read(node, 0x10, &parent)) {
                    return luaL_error(state, "LevelGeneratorRoom neighbor tree is invalid");
                }
            }
            node = parent;
        }
    }
    if (emitted != size) {
        return luaL_error(state, "LevelGeneratorRoom neighbor tree size mismatch");
    }
    return 1;
}

bool ReadLibcxxString(std::uintptr_t object, char* output,
                      std::size_t capacity) noexcept {
    if (object == 0 || output == nullptr || capacity < 2) return false;
    std::uint8_t first{};
    if (!Read(object, 0, &first)) return false;
    std::uintptr_t data{};
    std::size_t length{};
    if ((first & kLibcxxStringLongFlag) != 0) {
        std::uintptr_t pointer{};
        std::uint64_t declared{};
        if (!Read(object, kLibcxxStringDataOffset, &pointer) ||
            !Read(object, 8, &declared)) {
            return false;
        }
        data = pointer;
        length = static_cast<std::size_t>(declared);
    } else {
        data = object + kLibcxxStringShortDataOffset;
        length = static_cast<std::size_t>(first >> 1);
    }
    if (data == 0 || length >= capacity || length > 4096) return false;
    for (std::size_t index = 0; index < length; ++index) {
        if (!Read(data, index, output + index)) return false;
    }
    output[length] = '\0';
    return true;
}

std::uintptr_t BossPoolRng(const LuaRuntime::RngHandle* handle) noexcept {
    if (!handle || handle->owner == 0 ||
        handle->container != LuaRuntime::EngineModuleBase() ||
        !Readable(handle->owner, kPoolStride)) {
        return 0;
    }
    return handle->owner + handle->offset;
}

int LevelGeneratorIndex(lua_State* state) {
    auto* handle = CheckGenerator(state, 1);
    const auto key = luaL_checkstring(state, 2);
    if (!std::strcmp(key, "GetAllRooms")) {
        lua_pushcfunction(state, RepentogonLevelGeneratorGetAllRooms);
    } else if (!std::strcmp(key, "GetDeadEnds")) {
        lua_pushcfunction(state, RepentogonLevelGeneratorGetDeadEnds);
    } else if (!std::strcmp(key, "GetNonDeadEnds")) {
        lua_pushcfunction(state, RepentogonLevelGeneratorGetNonDeadEnds);
    } else {
        lua_pushnil(state);
    }
    static_cast<void>(handle);
    return 1;
}

int LevelGeneratorRoomIndex(lua_State* state) {
    auto* handle = CheckRoom(state, 1);
    const auto key = luaL_checkstring(state, 2);
    struct Method {
        const char* name;
        lua_CFunction function;
    };
    static constexpr Method methods[] = {
        {"GenerationIndex", RepentogonLevelGeneratorRoomGenerationIndex},
        {"DoorMask", RepentogonLevelGeneratorRoomDoorMask},
        {"Column", RepentogonLevelGeneratorRoomColumn},
        {"Row", RepentogonLevelGeneratorRoomLine},
        {"Shape", RepentogonLevelGeneratorRoomShape},
        {"Neighbors", RepentogonLevelGeneratorRoomNeighbors},
        {"IsDeadEnd", RepentogonLevelGeneratorRoomIsDeadEnd},
    };
    for (const auto& method : methods) {
        if (!std::strcmp(key, method.name)) {
            lua_pushcfunction(state, method.function);
            static_cast<void>(handle);
            return 1;
        }
    }
    lua_pushnil(state);
    static_cast<void>(handle);
    return 1;
}

int BossPoolIndex(lua_State* state) {
    auto* handle = CheckPool(state, 1);
    const auto key = luaL_checkstring(state, 2);
    struct Method {
        const char* name;
        lua_CFunction function;
    };
    static constexpr Method methods[] = {
        {"GetName", RepentogonBossPoolGetName},
        {"GetEntries", RepentogonBossPoolGetEntries},
        {"GetWeight", RepentogonBossPoolGetWeight},
        {"GetRNG", RepentogonBossPoolGetRNG},
        {"GetDoubleTroubleRoomVariantStart",
         RepentogonBossPoolGetDoubleTroubleRoomVariantStart},
        {"GetDoubleTroubleRoomID",
         RepentogonBossPoolGetDoubleTroubleRoomVariantStart},
    };
    for (const auto& method : methods) {
        if (!std::strcmp(key, method.name)) {
            lua_pushcfunction(state, method.function);
            static_cast<void>(handle);
            return 1;
        }
    }
    lua_pushnil(state);
    static_cast<void>(handle);
    return 1;
}

int ReadIntegerField(lua_State* state, const LevelGeneratorRoomHandle& handle,
                     std::uintptr_t offset, const char* name) {
    std::int32_t value{};
    if (!Read(engine_memory::AddressOf(handle.room), offset, &value)) {
        return luaL_error(state, "LevelGeneratorRoom %s is unreadable", name);
    }
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    return 1;
}

}  // namespace

void PushRepentogonLevelGeneratorHandle(lua_State* state, void* generator) {
    auto* handle = static_cast<LevelGeneratorHandle*>(
        lua_newuserdata(state, sizeof(LevelGeneratorHandle)));
    *handle = {generator, LuaRuntime::EngineModuleBase()};
    luaL_getmetatable(state, kLevelGeneratorMetatable);
    lua_setmetatable(state, -2);
}

void PushRepentogonLevelGeneratorRoomHandle(lua_State* state, void* generator,
                                            void* room) {
    auto* handle = static_cast<LevelGeneratorRoomHandle*>(
        lua_newuserdata(state, sizeof(LevelGeneratorRoomHandle)));
    *handle = {generator, room, LuaRuntime::EngineModuleBase()};
    luaL_getmetatable(state, kLevelGeneratorRoomMetatable);
    lua_setmetatable(state, -2);
}

void PushRepentogonBossPoolPoolHandle(lua_State* state, void* pool) {
    auto* handle = static_cast<BossPoolHandle*>(
        lua_newuserdata(state, sizeof(BossPoolHandle)));
    *handle = {pool, LuaRuntime::EngineModuleBase()};
    luaL_getmetatable(state, kBossPoolMetatable);
    lua_setmetatable(state, -2);
}

void RegisterRepentogonGeneratorViews(lua_State* state) {
    if (!state) return;

    luaL_newmetatable(state, kLevelGeneratorMetatable);
    lua_pushcfunction(state, LevelGeneratorIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    luaL_newmetatable(state, kLevelGeneratorRoomMetatable);
    lua_pushcfunction(state, LevelGeneratorRoomIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);

    luaL_newmetatable(state, kBossPoolMetatable);
    lua_pushcfunction(state, BossPoolIndex);
    lua_setfield(state, -2, "__index");
    lua_pop(state, 1);
}

int RepentogonLevelGeneratorGetAllRooms(lua_State* state) {
    auto* handle = CheckGenerator(state, 1);
    RequireNoArguments(state, "LevelGenerator:GetAllRooms");
    return PushRooms(state, handle, kGeneratorRooms);
}

int RepentogonLevelGeneratorGetDeadEnds(lua_State* state) {
    auto* handle = CheckGenerator(state, 1);
    RequireNoArguments(state, "LevelGenerator:GetDeadEnds");
    return PushRoomIndexList(state, handle, kGeneratorDeadEnds);
}

int RepentogonLevelGeneratorGetNonDeadEnds(lua_State* state) {
    auto* handle = CheckGenerator(state, 1);
    RequireNoArguments(state, "LevelGenerator:GetNonDeadEnds");
    return PushRoomIndexList(state, handle, kGeneratorNonDeadEnds);
}

int RepentogonLevelGeneratorRoomGenerationIndex(lua_State* state) {
    auto* handle = CheckRoom(state, 1);
    RequireNoArguments(state, "LevelGeneratorRoom:GenerationIndex");
    return ReadIntegerField(state, *handle, kRoomGenerationIndex,
                            "GenerationIndex");
}

int RepentogonLevelGeneratorRoomDoorMask(lua_State* state) {
    auto* handle = CheckRoom(state, 1);
    RequireNoArguments(state, "LevelGeneratorRoom:DoorMask");
    std::uint64_t doors{};
    if (!Read(engine_memory::AddressOf(handle->room), kRoomDoors, &doors)) {
        return luaL_error(state, "LevelGeneratorRoom DoorMask is unreadable");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(doors));
    return 1;
}

int RepentogonLevelGeneratorRoomColumn(lua_State* state) {
    auto* handle = CheckRoom(state, 1);
    RequireNoArguments(state, "LevelGeneratorRoom:Column");
    return ReadIntegerField(state, *handle, kRoomColumn, "Column");
}

int RepentogonLevelGeneratorRoomLine(lua_State* state) {
    auto* handle = CheckRoom(state, 1);
    RequireNoArguments(state, "LevelGeneratorRoom:Row");
    return ReadIntegerField(state, *handle, kRoomLine, "Row");
}

int RepentogonLevelGeneratorRoomShape(lua_State* state) {
    auto* handle = CheckRoom(state, 1);
    RequireNoArguments(state, "LevelGeneratorRoom:Shape");
    return ReadIntegerField(state, *handle, kRoomShape, "Shape");
}

int RepentogonLevelGeneratorRoomNeighbors(lua_State* state) {
    auto* handle = CheckRoom(state, 1);
    RequireNoArguments(state, "LevelGeneratorRoom:Neighbors");
    return PushNeighbors(state, *handle);
}

int RepentogonLevelGeneratorRoomIsDeadEnd(lua_State* state) {
    auto* handle = CheckRoom(state, 1);
    RequireNoArguments(state, "LevelGeneratorRoom:IsDeadEnd");
    std::uint8_t value{};
    if (!Read(engine_memory::AddressOf(handle->room), kRoomDeadEnd, &value)) {
        return luaL_error(state, "LevelGeneratorRoom IsDeadEnd is unreadable");
    }
    lua_pushboolean(state, value != 0);
    return 1;
}

int RepentogonBossPoolGetName(lua_State* state) {
    auto* handle = CheckPool(state, 1);
    RequireNoArguments(state, "BossPool:GetName");
    std::array<char, 256> name{};
    if (!ReadLibcxxString(engine_memory::AddressOf(handle->pool) + kPoolName,
                          name.data(), name.size())) {
        lua_pushliteral(state, "");
    } else {
        lua_pushstring(state, name.data());
    }
    return 1;
}

int RepentogonBossPoolGetEntries(lua_State* state) {
    auto* handle = CheckPool(state, 1);
    RequireNoArguments(state, "BossPool:GetEntries");
    const auto pool = engine_memory::AddressOf(handle->pool);
    std::uintptr_t begin{};
    std::uintptr_t end{};
    if (!Read(pool, kPoolEntries, &begin) ||
        !Read(pool, kPoolEntriesEnd, &end)) {
        return luaL_error(state, "BossPool entries are unavailable");
    }
    if (begin == 0 && end == 0) {
        lua_createtable(state, 0, 0);
        return 1;
    }
    if (begin == 0 || end < begin || (end - begin) % kEntryStride != 0 ||
        (end - begin) / kEntryStride > kMaxVectorEntries) {
        return luaL_error(state, "BossPool entries are invalid");
    }
    const auto count = (end - begin) / kEntryStride;
    lua_createtable(state, static_cast<int>(count), 0);
    for (std::size_t index = 0; index < count; ++index) {
        const auto entry = begin + index * kEntryStride;
        if (!Readable(entry, kEntryStride)) {
            return luaL_error(state, "BossPool entry is unreadable");
        }
        std::int32_t id{};
        float initialWeight{};
        float weight{};
        std::int32_t achievement{};
        if (!Read(entry, 0x00, &id) || !Read(entry, 0x04, &initialWeight) ||
            !Read(entry, 0x08, &weight) || !Read(entry, 0x0c, &achievement)) {
            return luaL_error(state, "BossPool entry fields are unreadable");
        }
        lua_createtable(state, 0, 5);
        lua_pushinteger(state, static_cast<lua_Integer>(id));
        lua_setfield(state, -2, "bossID");
        lua_pushnumber(state, static_cast<lua_Number>(initialWeight));
        lua_setfield(state, -2, "initialWeight");
        lua_pushnumber(state, static_cast<lua_Number>(weight));
        lua_setfield(state, -2, "weight");
        // The pinned upstream implementation publishes _weight under both
        // keys; _roomVariantStart is not the documented weightAlt field.
        lua_pushnumber(state, static_cast<lua_Number>(weight));
        lua_setfield(state, -2, "weightAlt");
        lua_pushinteger(state, static_cast<lua_Integer>(achievement));
        lua_setfield(state, -2, "achievementID");
        lua_rawseti(state, -2, static_cast<lua_Integer>(index + 1));
    }
    return 1;
}

int RepentogonBossPoolGetWeight(lua_State* state) {
    auto* handle = CheckPool(state, 1);
    RequireNoArguments(state, "BossPool:GetWeight");
    float value{};
    if (!Read(engine_memory::AddressOf(handle->pool), kPoolTotalWeight, &value)) {
        return luaL_error(state, "BossPool weight is unreadable");
    }
    lua_pushnumber(state, static_cast<lua_Number>(value));
    return 1;
}

int RepentogonBossPoolGetRNG(lua_State* state) {
    auto* handle = CheckPool(state, 1);
    RequireNoArguments(state, "BossPool:GetRNG");
    auto* rng = static_cast<LuaRuntime::RngHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::RngHandle)));
    *rng = {};
    rng->resolver = BossPoolRng;
    rng->owner = engine_memory::AddressOf(handle->pool);
    rng->container = LuaRuntime::EngineModuleBase();
    rng->offset = kPoolRng;
    luaL_getmetatable(state, LuaRuntime::kRngMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int RepentogonBossPoolGetDoubleTroubleRoomVariantStart(lua_State* state) {
    auto* handle = CheckPool(state, 1);
    RequireNoArguments(state, "BossPool:GetDoubleTroubleRoomVariantStart");
    std::int32_t value{};
    if (!Read(engine_memory::AddressOf(handle->pool),
              kPoolDoubleTroubleStart, &value)) {
        return luaL_error(state, "BossPool double-trouble variant is unreadable");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(value));
    return 1;
}

}  // namespace isaac::runtime
