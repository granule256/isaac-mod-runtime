#include "interfaces/lua/repentogon_pickup_loot_list.hpp"

#include "class_metadata.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/rng_api.hpp"
#include "lua_object_handles.hpp"

#if defined(__SWITCH__)
#include "lua_runtime.hpp"
#endif

#include <array>
#include <cstdint>
#include <cstring>
#include <limits>

extern "C" {
#include <lauxlib.h>
#include <lua.h>
}

namespace isaac::runtime {
namespace {

using AddBackCapacityFn = void (*)(void*) noexcept;
using DestroyFn = void (*)(void*) noexcept;

struct NativeLootEntry {
    std::uint32_t type{};
    std::uint32_t variant{};
    std::uint32_t subtype{};
    std::uint32_t seed{};
    std::uintptr_t rng{};
};
static_assert(sizeof(NativeLootEntry) == kRepentogonLootListEntrySize);

struct LootListHeader {
    std::uintptr_t mapFirst{};
    std::uintptr_t mapBegin{};
    std::uintptr_t mapEnd{};
    std::uintptr_t mapCapacity{};
    std::uintptr_t start{};
    std::uintptr_t size{};
};
static_assert(sizeof(LootListHeader) == kRepentogonLootListNativeSize);

struct LootListUserdata {
    alignas(8) std::array<std::uint8_t, kRepentogonLootListNativeSize> storage{};
    std::uintptr_t dropRng{};
    std::uint32_t generation{1};
    std::uint32_t initialized{};
};
static_assert(sizeof(LootListUserdata::storage) == kRepentogonLootListNativeSize);

struct LootListEntryUserdata {
    LootListUserdata* owner{};
    std::uintptr_t entry{};
    std::uint32_t generation{};
    std::uint32_t reserved{};
};
static_assert(sizeof(LootListEntryUserdata) == 0x18);

#if defined(__SWITCH__)
constexpr std::array<std::uint8_t, 16> kLootListDestroyGuard = {
    0xfd, 0x7b, 0xbd, 0xa9, 0xf5, 0x0b, 0x00, 0xf9,
    0xfd, 0x03, 0x00, 0x91, 0xf4, 0x4f, 0x02, 0xa9,
};
constexpr std::uintptr_t kLootListDestroyOffset = 0x110efc;
constexpr std::array<std::uint8_t, 16> kLootListAddBackGuard = {
    0xfd, 0x7b, 0xba, 0xa9, 0xfb, 0x0b, 0x00, 0xf9,
    0xfd, 0x03, 0x00, 0x91, 0xfa, 0x67, 0x02, 0xa9,
};
constexpr std::uintptr_t kLootListAddBackOffset = 0x124b28;

struct NativeOps {
    std::uintptr_t base{};
    AddBackCapacityFn addBackCapacity{};
    DestroyFn destroy{};
};
NativeOps g_NativeOps{};
#else
RepentogonPickupLootListTestBindings g_TestBindings{};
#endif

std::uintptr_t g_CurrentDropRng{};

[[nodiscard]] bool IsReadable(std::uintptr_t address, std::size_t size) noexcept {
    return address != 0 && address <= UINTPTR_MAX - size &&
           engine_memory::EngineMemoryReadable(address, size);
}

[[nodiscard]] bool IsWritable(std::uintptr_t address, std::size_t size) noexcept {
    return address != 0 && address <= UINTPTR_MAX - size &&
           engine_memory::EngineMemoryWritable(address, size);
}

[[nodiscard]] bool ReadHeader(std::uintptr_t object,
                              LootListHeader* header) noexcept {
    if (!header || !IsReadable(object, kRepentogonLootListNativeSize) ||
        !engine_memory::ReadAt(object, header,
                               engine_memory::EngineMemoryReadable)) {
        return false;
    }
    if ((header->mapBegin == 0) != (header->mapEnd == 0)) {
        return false;
    }
    if (header->mapBegin == 0) {
        return header->mapFirst == 0 && header->mapCapacity == 0 &&
               header->start == 0 && header->size == 0;
    }
    if (header->mapBegin > header->mapEnd ||
        header->mapFirst > header->mapBegin ||
        header->mapEnd > header->mapCapacity ||
        (header->mapEnd - header->mapBegin) % sizeof(std::uintptr_t) != 0) {
        return false;
    }
    const auto slots =
        (header->mapEnd - header->mapBegin) / sizeof(std::uintptr_t);
    if (slots == 0 || slots > 0x10000 ||
        slots > std::numeric_limits<std::uintptr_t>::max() /
                    kRepentogonLootListBlockEntries) {
        return false;
    }
    const auto capacity = slots * kRepentogonLootListBlockEntries - 1;
    return header->start <= capacity &&
           header->size <= capacity - header->start;
}

[[nodiscard]] bool ReadHeader(const LootListUserdata* list,
                              LootListHeader* header) noexcept {
    return list && header &&
           ReadHeader(engine_memory::AddressOf(list->storage.data()), header);
}

[[nodiscard]] bool IsZeroObject(std::uintptr_t object) noexcept {
    std::array<std::uint8_t, kRepentogonLootListNativeSize> bytes{};
    return IsReadable(object, bytes.size()) &&
           engine_memory::ReadAt(object, &bytes,
                                 engine_memory::EngineMemoryReadable) &&
           bytes == decltype(bytes){};
}

[[nodiscard]] bool CopyObjectBytes(std::uintptr_t source,
                                   std::uint8_t* destination) noexcept {
    std::array<std::uint8_t, kRepentogonLootListNativeSize> bytes{};
    if (!destination || !IsReadable(source, bytes.size()) ||
        !engine_memory::ReadAt(source, &bytes,
                               engine_memory::EngineMemoryReadable)) {
        return false;
    }
    std::memcpy(destination, bytes.data(), bytes.size());
    return true;
}

[[nodiscard]] bool WriteObjectBytes(
    std::uintptr_t destination,
    const std::array<std::uint8_t, kRepentogonLootListNativeSize>& bytes) noexcept {
    return IsWritable(destination, bytes.size()) &&
           engine_memory::WriteAt(destination, bytes,
                                  engine_memory::EngineMemoryWritable);
}

[[nodiscard]] bool ResolveNativeOps() noexcept {
#if defined(__SWITCH__)
    const auto base = LuaRuntime::EngineModuleBase();
    if (base == 0) {
        return false;
    }
    if (g_NativeOps.base == base && g_NativeOps.addBackCapacity &&
        g_NativeOps.destroy) {
        return true;
    }
    g_NativeOps = {};
    if (!engine_call::VerifyEntryBytes(
            base + kLootListAddBackOffset, kLootListAddBackGuard.data(),
            kLootListAddBackGuard.size(), engine_memory::EngineMemoryReadable) ||
        !engine_call::VerifyEntryBytes(
            base + kLootListDestroyOffset, kLootListDestroyGuard.data(),
            kLootListDestroyGuard.size(), engine_memory::EngineMemoryReadable)) {
        return false;
    }
    g_NativeOps.base = base;
    g_NativeOps.addBackCapacity =
        engine_call::AsFunction<AddBackCapacityFn>(base + kLootListAddBackOffset);
    g_NativeOps.destroy =
        engine_call::AsFunction<DestroyFn>(base + kLootListDestroyOffset);
    return g_NativeOps.addBackCapacity && g_NativeOps.destroy;
#else
    return g_TestBindings.addBackCapacity != nullptr &&
           g_TestBindings.destroy != nullptr;
#endif
}

[[nodiscard]] AddBackCapacityFn AddBackCapacity() noexcept {
    return ResolveNativeOps()
#if defined(__SWITCH__)
        ? g_NativeOps.addBackCapacity
#else
        ? g_TestBindings.addBackCapacity
#endif
        : nullptr;
}

[[nodiscard]] DestroyFn DestroyLootListFn() noexcept {
    return ResolveNativeOps()
#if defined(__SWITCH__)
        ? g_NativeOps.destroy
#else
        ? g_TestBindings.destroy
#endif
        : nullptr;
}

[[nodiscard]] bool IsSafeListRng(const LootListUserdata* list,
                                std::uintptr_t rng) noexcept {
    return rng == 0 ||
           (list && rng == list->dropRng &&
            IsReadable(rng, kRngObjectSize));
}

[[nodiscard]] bool IsCurrentDropRng(std::uintptr_t rng) noexcept {
    return rng != 0 && rng == g_CurrentDropRng &&
           IsReadable(rng, kRngObjectSize);
}

[[nodiscard]] std::uintptr_t EntryAddress(const LootListHeader& header,
                                          std::uintptr_t index) noexcept {
    if (index > UINTPTR_MAX - header.start) {
        return 0;
    }
    const auto position = header.start + index;
    const auto mapIndex = position / kRepentogonLootListBlockEntries;
    const auto blockOffset = position % kRepentogonLootListBlockEntries;
    const auto mapBytes = header.mapEnd - header.mapBegin;
    if (mapIndex >= mapBytes / sizeof(std::uintptr_t) ||
        header.mapBegin > UINTPTR_MAX -
            mapIndex * sizeof(std::uintptr_t)) {
        return 0;
    }
    std::uintptr_t block{};
    if (!engine_memory::ReadAt(
            header.mapBegin + mapIndex * sizeof(std::uintptr_t), &block,
            engine_memory::EngineMemoryReadable) ||
        block == 0 ||
        blockOffset > (UINTPTR_MAX / sizeof(NativeLootEntry))) {
        return 0;
    }
    const auto address = block + blockOffset * sizeof(NativeLootEntry);
    return IsWritable(address, sizeof(NativeLootEntry)) ? address : 0;
}

[[nodiscard]] bool AppendNativeEntry(LootListUserdata* list,
                                     const NativeLootEntry& entry,
                                     const char* errorName) noexcept {
    if (!list || !list->initialized) {
        return false;
    }
    const auto object = engine_memory::AddressOf(list->storage.data());
    LootListHeader header{};
    if (!ReadHeader(list, &header)) {
        return false;
    }
    const auto capacity =
        (header.mapEnd - header.mapBegin) / sizeof(std::uintptr_t) *
            kRepentogonLootListBlockEntries -
        (header.mapBegin == 0 ? 0 : 1);
    if (header.start + header.size >= capacity) {
        const auto addBack = AddBackCapacity();
        if (!addBack) {
            return false;
        }
        addBack(engine_memory::AsObject(object));
        if (!ReadHeader(list, &header)) {
            return false;
        }
    }
    const auto address = EntryAddress(header, header.size);
    if (!address ||
        !engine_memory::WriteAt(address, entry,
                                engine_memory::EngineMemoryWritable) ||
        !engine_memory::WriteField(
            object, offsetof(LootListHeader, size), header.size + 1,
            engine_memory::EngineMemoryWritable)) {
        return false;
    }
    ++list->generation;
    if (list->generation == 0) {
        list->generation = 1;
    }
    static_cast<void>(errorName);
    return true;
}

[[nodiscard]] bool ValidateSourceEntries(
    const LootListUserdata* list, const LootListHeader& header) noexcept {
    for (std::uintptr_t index = 0; index < header.size; ++index) {
        const auto entry = EntryAddress(header, index);
        if (!entry) {
            return false;
        }
        std::uintptr_t rng{};
        if (!engine_memory::ReadField(
                entry, offsetof(NativeLootEntry, rng), &rng,
                engine_memory::EngineMemoryReadable) ||
            (rng != 0 &&
             (!IsCurrentDropRng(rng) || !IsSafeListRng(list, rng)))) {
            return false;
        }
    }
    return true;
}

[[nodiscard]] LootListUserdata* CheckList(lua_State* state, int index) {
    auto* list = static_cast<LootListUserdata*>(
        luaL_checkudata(state, index, kRepentogonLootListMetatable));
    if (lua_rawlen(state, index) != sizeof(LootListUserdata) ||
        !list || !list->initialized) {
        luaL_error(state, "LootList is no longer available");
    }
    return list;
}

[[nodiscard]] LootListEntryUserdata* CheckEntry(lua_State* state, int index) {
    auto* entry = static_cast<LootListEntryUserdata*>(
        luaL_checkudata(state, index, kRepentogonLootListEntryMetatable));
    if (lua_rawlen(state, index) != sizeof(LootListEntryUserdata) ||
        !entry || !entry->owner || !entry->owner->initialized ||
        entry->generation != entry->owner->generation ||
        !IsReadable(entry->entry, sizeof(NativeLootEntry))) {
        luaL_error(state, "LootListEntry is no longer available");
    }
    return entry;
}

int LootListConstructor(lua_State* state) {
    auto* list = new (lua_newuserdata(state, sizeof(LootListUserdata)))
        LootListUserdata{};
    list->dropRng = g_CurrentDropRng;
    list->initialized = 1;
    luaL_setmetatable(state, kRepentogonLootListMetatable);
    return 1;
}

int LootListGc(lua_State* state) {
    auto* list = static_cast<LootListUserdata*>(
        lua_touserdata(state, 1));
    if (!list || lua_rawlen(state, 1) != sizeof(LootListUserdata) ||
        !list->initialized) {
        return 0;
    }
    const auto object = engine_memory::AddressOf(list->storage.data());
    if (!IsZeroObject(object)) {
        if (const auto destroy = DestroyLootListFn()) {
            destroy(engine_memory::AsObject(object));
        }
    }
    list->storage.fill(0);
    list->initialized = 0;
    return 0;
}

int LootListPushEntry(lua_State* state) {
    auto* list = CheckList(state, 1);
    const auto type = static_cast<std::uint64_t>(
        luaL_checkinteger(state, 2));
    const auto variant = static_cast<std::uint64_t>(
        luaL_checkinteger(state, 3));
    const auto subtype = static_cast<std::uint64_t>(
        luaL_checkinteger(state, 4));
    if (type > UINT32_MAX || variant > UINT32_MAX || subtype > UINT32_MAX) {
        return luaL_error(state, "LootList entry fields must fit uint32");
    }

    std::uint32_t seed{};
    if (lua_isnoneornil(state, 5)) {
        if (!TryEngineRandomU32(&seed)) {
            return luaL_error(state, "LootList random seed is unavailable");
        }
    } else {
        const auto value = static_cast<std::uint64_t>(
            luaL_checkinteger(state, 5));
        if (value > UINT32_MAX) {
            return luaL_error(state, "LootList seed must fit uint32");
        }
        seed = static_cast<std::uint32_t>(value);
    }

    std::uintptr_t rng = 0;
    if (!lua_isnoneornil(state, 6)) {
        auto* handle = static_cast<LuaRuntime::RngHandle*>(
            luaL_testudata(state, 6, LuaRuntime::kRngMetatable));
        if (!handle || lua_rawlen(state, 6) != sizeof(LuaRuntime::RngHandle)) {
            return luaL_error(state,
                              "LootList RNG must be a valid RNG userdata");
        }
        auto* resolved = TryResolveRngObject(handle, false);
        const auto address = engine_memory::AddressOf(resolved);
        if (!address || address != list->dropRng ||
            !IsReadable(address, kRngObjectSize)) {
            return luaL_error(
                state,
                "LootList RNG is restricted to the current pickup DropRNG");
        }
        rng = address;
    }

    const NativeLootEntry entry{
        static_cast<std::uint32_t>(type),
        static_cast<std::uint32_t>(variant),
        static_cast<std::uint32_t>(subtype),
        seed,
        rng,
    };
    if (!AppendNativeEntry(list, entry, "LootList::PushEntry")) {
        return luaL_error(state, "LootList native storage is unavailable");
    }
    return 0;
}

int LootListGetEntries(lua_State* state) {
    auto* list = CheckList(state, 1);
    LootListHeader header{};
    if (!ReadHeader(list, &header) || header.size > 0x10000) {
        return luaL_error(state, "LootList storage is invalid");
    }
    lua_createtable(state, static_cast<int>(header.size), 0);
    const int table = lua_gettop(state);
    for (std::uintptr_t index = 0; index < header.size; ++index) {
        const auto entry = EntryAddress(header, index);
        if (!entry) {
            return luaL_error(state, "LootList entry is unavailable");
        }
        auto* handle = new (lua_newuserdata(
            state, sizeof(LootListEntryUserdata))) LootListEntryUserdata{};
        handle->owner = list;
        handle->entry = entry;
        handle->generation = list->generation;
        luaL_setmetatable(state, kRepentogonLootListEntryMetatable);
        lua_pushvalue(state, 1);
        lua_setuservalue(state, -2);
        lua_rawseti(state, table, static_cast<lua_Integer>(index + 1));
    }
    return 1;
}

template <class T>
[[nodiscard]] T ReadEntryField(lua_State* state,
                               const LootListEntryUserdata& entry,
                               std::uintptr_t offset) {
    T value{};
    if (!engine_memory::ReadField(
            entry.entry, offset, &value,
            engine_memory::EngineMemoryReadable)) {
        luaL_error(state, "LootListEntry field is unavailable");
    }
    return value;
}

int LootListEntryGetType(lua_State* state) {
    const auto& entry = *CheckEntry(state, 1);
    lua_pushinteger(state, ReadEntryField<std::uint32_t>(state, entry, 0));
    return 1;
}

int LootListEntryGetVariant(lua_State* state) {
    const auto& entry = *CheckEntry(state, 1);
    lua_pushinteger(state, ReadEntryField<std::uint32_t>(state, entry, 4));
    return 1;
}

int LootListEntryGetSubType(lua_State* state) {
    const auto& entry = *CheckEntry(state, 1);
    lua_pushinteger(state, ReadEntryField<std::uint32_t>(state, entry, 8));
    return 1;
}

int LootListEntryGetSeed(lua_State* state) {
    const auto& entry = *CheckEntry(state, 1);
    lua_pushinteger(state, ReadEntryField<std::uint32_t>(state, entry, 12));
    return 1;
}

int LootListEntryGetRng(lua_State* state) {
    const auto& entry = *CheckEntry(state, 1);
    const auto rng = ReadEntryField<std::uintptr_t>(state, entry, 16);
    if (!rng || !IsSafeListRng(entry.owner, rng)) {
        lua_pushnil(state);
        return 1;
    }
    auto* handle = new (lua_newuserdata(state, sizeof(LuaRuntime::RngHandle)))
        LuaRuntime::RngHandle{};
    std::memcpy(handle->storage.data(), engine_memory::AsObject(rng),
                kRngObjectSize);
    luaL_getmetatable(state, LuaRuntime::kRngMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

void RegisterMetatableWithMethods(lua_State* state, const char* metatable,
                                  const luaL_Reg* methods) {
    luaL_newmetatable(state, metatable);
    lua_newtable(state);
    luaL_setfuncs(state, methods, 0);
    lua_pushvalue(state, -1);
    lua_setfield(state, -3, "__methods");
    lua_pushvalue(state, -1);
    lua_setfield(state, -3, "__index");
    lua_pop(state, 1);
    lua_pop(state, 1);
}

}  // namespace

std::uintptr_t SetRepentogonPickupLootListDropRng(
    std::uintptr_t dropRng) noexcept {
    const auto previous = g_CurrentDropRng;
    g_CurrentDropRng = dropRng;
    return previous;
}

void RegisterRepentogonPickupLootList(lua_State* state) {
    if (!state) {
        return;
    }
    constexpr luaL_Reg listMethods[] = {
        {"PushEntry", LootListPushEntry},
        {"GetEntries", LootListGetEntries},
        {nullptr, nullptr},
    };
    constexpr luaL_Reg entryMethods[] = {
        {"GetType", LootListEntryGetType},
        {"GetVariant", LootListEntryGetVariant},
        {"GetSubType", LootListEntryGetSubType},
        {"GetSeed", LootListEntryGetSeed},
        {"GetRNG", LootListEntryGetRng},
        {nullptr, nullptr},
    };

    RegisterMetatableWithMethods(state, kRepentogonLootListMetatable,
                                 listMethods);
    luaL_getmetatable(state, kRepentogonLootListMetatable);
    lua_pushcfunction(state, LootListGc);
    lua_setfield(state, -2, "__gc");
    lua_pop(state, 1);

    RegisterMetatableWithMethods(state, kRepentogonLootListEntryMetatable,
                                 entryMethods);
    PublishNativeClass(state, "LootList", kRepentogonLootListMetatable);
    lua_getglobal(state, "LootList");
    lua_getmetatable(state, -1);
    lua_pushcfunction(state, LootListConstructor);
    lua_setfield(state, -2, "__call");
    lua_pop(state, 2);

    PublishNativeClass(state, "LootListEntry",
                       kRepentogonLootListEntryMetatable);
}

bool PushRepentogonPickupLootList(lua_State* state, std::uintptr_t nativeList,
                                  std::uintptr_t dropRng) noexcept {
    if (!state) {
        return false;
    }
    std::array<std::uint8_t, kRepentogonLootListNativeSize> bytes{};
    LootListHeader header{};
    if (!CopyObjectBytes(nativeList, bytes.data()) ||
        !ReadHeader(nativeList, &header)) {
        return false;
    }
    if (!IsZeroObject(nativeList) &&
        !IsWritable(nativeList, bytes.size())) {
        return false;
    }

    auto* list = new (lua_newuserdata(state, sizeof(LootListUserdata)))
        LootListUserdata{};
    list->storage = bytes;
    list->dropRng = dropRng;
    list->initialized = 1;
    luaL_setmetatable(state, kRepentogonLootListMetatable);
    if (!IsZeroObject(nativeList)) {
        std::array<std::uint8_t, kRepentogonLootListNativeSize> zero{};
        if (!WriteObjectBytes(nativeList, zero)) {
            list->storage.fill(0);
            list->initialized = 0;
            lua_pop(state, 1);
            return false;
        }
    }
    return true;
}

bool MoveRepentogonPickupLootListToNative(lua_State* state, int index,
                                          std::uintptr_t destination) noexcept {
    if (!state) {
        return false;
    }
    const int absoluteIndex = lua_absindex(state, index);
    if (absoluteIndex == 0 ||
        !IsWritable(destination, kRepentogonLootListNativeSize)) {
        return false;
    }
    auto* source = static_cast<LootListUserdata*>(
        luaL_testudata(state, absoluteIndex, kRepentogonLootListMetatable));
    if (!source ||
        lua_rawlen(state, absoluteIndex) != sizeof(LootListUserdata) ||
        !source->initialized) {
        return false;
    }
    LootListHeader sourceHeader{};
    LootListHeader destinationHeader{};
    if (!ReadHeader(source, &sourceHeader) ||
        !ValidateSourceEntries(source, sourceHeader) ||
        !ReadHeader(destination, &destinationHeader)) {
        return false;
    }
    std::array<std::uint8_t, kRepentogonLootListNativeSize> bytes{};
    if (!CopyObjectBytes(engine_memory::AddressOf(source->storage.data()),
                         bytes.data())) {
        return false;
    }
    if (!IsZeroObject(destination)) {
        const auto destroy = DestroyLootListFn();
        if (!destroy) {
            return false;
        }
        destroy(engine_memory::AsObject(destination));
    }
    if (!WriteObjectBytes(destination, bytes)) {
        return false;
    }
    source->storage.fill(0);
    source->initialized = 0;
    return true;
}

#if !defined(__SWITCH__)
void SetRepentogonPickupLootListTestBindings(
    RepentogonPickupLootListTestBindings bindings) noexcept {
    g_TestBindings = bindings;
}
#endif

}  // namespace isaac::runtime
