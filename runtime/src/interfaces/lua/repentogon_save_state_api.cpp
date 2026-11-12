#include "interfaces/lua/repentogon_save_state_api.hpp"

#include "interfaces/lua/owner_binding.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"

#include <cstdint>
#include <cstring>
#include <type_traits>

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {

constexpr std::uintptr_t kSavedGridEntitiesOffset = 0x78;
constexpr std::uintptr_t kSavedEntitiesOffset = 0x90;
constexpr std::uintptr_t kSavedEffectsOffset = 0xc0;
constexpr std::size_t kEntitySaveStateStride = 0x78;
constexpr std::size_t kGridEntityDescStride = 0x20;
constexpr std::uintptr_t kEntitySaveStateType = 0x00;
constexpr std::uintptr_t kEntitySaveStateVariant = 0x04;
constexpr std::uintptr_t kEntitySaveStateSubType = 0x08;
constexpr std::uintptr_t kEntitySaveStateI3 = 0x14;
constexpr std::uintptr_t kGridDescType = 0x00;
constexpr std::uintptr_t kGridDescVariant = 0x04;
constexpr std::uintptr_t kGridDescSpawnCount = 0x0c;
constexpr std::uintptr_t kGridDescState = 0x10;
constexpr std::uintptr_t kGridDescVarData = 0x14;
constexpr std::uintptr_t kGridDescInitialized = 0x18;

constexpr char kEntityVectorMetatable[] = "IsaacRuntime.EntitiesSaveStateVector";
constexpr char kGridVectorMetatable[] = "IsaacRuntime.GridEntitiesSaveStateVector";
constexpr char kEntityStateMetatable[] = "IsaacRuntime.EntitiesSaveState";
constexpr char kGridDescMetatable[] = "IsaacRuntime.GridEntityDescSaveState";

enum class VectorKind : std::uint32_t { Entity = 1, Grid = 2 };

struct VectorHandle {
    void* descriptor;
    void* vector;
    std::uint32_t kind;
    std::uint32_t reserved;
};

struct EntityStateHandle {
    void* vector;
    void* element;
    std::uint32_t index;
    std::uint32_t reserved;
};

struct GridDescHandle {
    void* vector;
    void* element;
    std::uint32_t index;
    std::uint32_t reserved;
};

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
void Write(lua_State* state, std::uintptr_t object, std::uintptr_t offset,
           T value, const char* name) {
    if (!engine_memory::WriteField(object, offset, value,
                                   engine_memory::EngineMemoryWritable)) {
        luaL_error(state, "%s is not writable", name);
    }
}

std::uintptr_t Descriptor(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) {
        luaL_error(state, "REPENTOGON save-state access requires the game thread");
    }
    luaL_checkudata(state, 1, LuaRuntime::kRoomDescriptorMetatable);
    if (lua_rawlen(state, 1) != sizeof(LuaRuntime::RoomDescriptorHandle)) {
        luaL_error(state, "RoomDescriptor reference is invalid");
    }
    const auto* handle = static_cast<const LuaRuntime::RoomDescriptorHandle*>(
        lua_touserdata(state, 1));
    if (!handle || !handle->descriptor ||
        handle->moduleBase != LuaRuntime::EngineModuleBase()) {
        luaL_error(state, "RoomDescriptor reference is no longer available");
    }
    return engine_memory::AddressOf(handle->descriptor);
}

struct VectorView {
    std::uintptr_t begin{};
    std::uintptr_t end{};
    std::size_t stride{};
};

VectorView ReadVector(lua_State* state, std::uintptr_t vector,
                      std::size_t stride, const char* name) {
    VectorView view{
        Read<std::uintptr_t>(state, vector, 0, name),
        Read<std::uintptr_t>(state, vector, sizeof(std::uintptr_t), name),
        stride,
    };
    if (!view.begin || view.end < view.begin ||
        (view.end - view.begin) % view.stride != 0 ||
        (view.end - view.begin) / view.stride > 0x10000) {
        luaL_error(state, "%s vector is invalid", name);
    }
    return view;
}

std::uintptr_t PushVector(lua_State* state, std::uintptr_t descriptor,
                          std::uintptr_t offset, VectorKind kind) {
    const auto vector = descriptor + offset;
    auto* handle = static_cast<VectorHandle*>(
        lua_newuserdata(state, sizeof(VectorHandle)));
    *handle = {engine_memory::AsObject(descriptor),
               engine_memory::AsObject(vector),
               static_cast<std::uint32_t>(kind), 0};
    luaL_getmetatable(state, kind == VectorKind::Grid ? kGridVectorMetatable
                                                       : kEntityVectorMetatable);
    lua_setmetatable(state, -2);
    return vector;
}

template <class Handle>
std::uintptr_t LiveVectorElement(lua_State* state, Handle* handle,
                                 char const* name) {
    if (!handle || !handle->vector) {
        luaL_error(state, "%s is no longer available", name);
    }
    const auto vector = engine_memory::AddressOf(handle->vector);
    const auto stride = std::is_same_v<Handle, GridDescHandle>
                            ? kGridEntityDescStride
                            : kEntitySaveStateStride;
    const auto view = ReadVector(state, vector, stride, name);
    if (handle->index >= (view.end - view.begin) / view.stride) {
        luaL_error(state, "%s is no longer available", name);
    }
    const auto element = view.begin + handle->index * view.stride;
    if (element != engine_memory::AddressOf(handle->element)) {
        luaL_error(state, "%s is no longer available", name);
    }
    return element;
}

int EntityVectorIndex(lua_State* state) {
    const auto* key = luaL_checkstring(state, 2);
    if (!std::strcmp(key, "Get")) {
        lua_pushcfunction(state, RepentogonEntitiesSaveStateVectorGet);
    } else if (!std::strcmp(key, "Clear")) {
        lua_pushnil(state);
    } else {
        luaL_getmetatable(state, kEntityVectorMetatable);
        lua_getfield(state, -1, key);
        lua_remove(state, -2);
    }
    return 1;
}

int GridVectorIndex(lua_State* state) {
    const auto* key = luaL_checkstring(state, 2);
    if (!std::strcmp(key, "Get")) {
        lua_pushcfunction(state, RepentogonGridEntitiesSaveStateVectorGet);
    } else {
        luaL_getmetatable(state, kGridVectorMetatable);
        lua_getfield(state, -1, key);
        lua_remove(state, -2);
    }
    return 1;
}

int EntityStateIndex(lua_State* state) {
    const auto* key = luaL_checkstring(state, 2);
    const struct {
        const char* name;
        lua_CFunction function;
    } functions[] = {
        {"GetType", RepentogonEntitiesSaveStateGetType},
        {"GetVariant", RepentogonEntitiesSaveStateGetVariant},
        {"GetSubType", RepentogonEntitiesSaveStateGetSubType},
        {"GetI3", RepentogonEntitiesSaveStateGetI3},
    };
    for (const auto& function : functions) {
        if (!std::strcmp(key, function.name)) {
            lua_pushcfunction(state, function.function);
            return 1;
        }
    }
    lua_pushnil(state);
    return 1;
}

int GridDescIndex(lua_State* state) {
    auto* handle = static_cast<GridDescHandle*>(lua_touserdata(state, 1));
    const auto element = LiveVectorElement(state, handle, "GridEntityDesc");
    const auto* key = luaL_checkstring(state, 2);
    if (!std::strcmp(key, "Initialized")) {
        lua_pushboolean(state, Read<std::uint8_t>(
                                  state, element, kGridDescInitialized,
                                  "GridEntityDesc Initialized") != 0);
    } else if (!std::strcmp(key, "SpawnCount")) {
        lua_pushinteger(state, Read<std::int32_t>(
                                   state, element, kGridDescSpawnCount,
                                   "GridEntityDesc SpawnCount"));
    } else if (!std::strcmp(key, "State")) {
        lua_pushinteger(state, Read<std::int32_t>(
                                   state, element, kGridDescState,
                                   "GridEntityDesc State"));
    } else if (!std::strcmp(key, "Type")) {
        lua_pushinteger(state, Read<std::int32_t>(
                                   state, element, kGridDescType,
                                   "GridEntityDesc Type"));
    } else if (!std::strcmp(key, "Variant")) {
        lua_pushinteger(state, Read<std::int32_t>(
                                   state, element, kGridDescVariant,
                                   "GridEntityDesc Variant"));
    } else if (!std::strcmp(key, "VarData")) {
        lua_pushinteger(state, Read<std::int32_t>(
                                   state, element, kGridDescVarData,
                                   "GridEntityDesc VarData"));
    } else {
        lua_pushnil(state);
    }
    return 1;
}

int GridDescNewIndex(lua_State* state) {
    auto* handle = static_cast<GridDescHandle*>(lua_touserdata(state, 1));
    const auto element = LiveVectorElement(state, handle, "GridEntityDesc");
    const auto* key = luaL_checkstring(state, 2);
    if (!std::strcmp(key, "Initialized")) {
        Write<std::uint8_t>(state, element, kGridDescInitialized,
                            lua_toboolean(state, 3) != 0,
                            "GridEntityDesc Initialized");
    } else if (!std::strcmp(key, "SpawnCount")) {
        Write<std::int32_t>(state, element, kGridDescSpawnCount,
                            static_cast<std::int32_t>(luaL_checkinteger(state, 3)),
                            "GridEntityDesc SpawnCount");
    } else if (!std::strcmp(key, "State")) {
        Write<std::int32_t>(state, element, kGridDescState,
                            static_cast<std::int32_t>(luaL_checkinteger(state, 3)),
                            "GridEntityDesc State");
    } else if (!std::strcmp(key, "Type")) {
        Write<std::int32_t>(state, element, kGridDescType,
                            static_cast<std::int32_t>(luaL_checkinteger(state, 3)),
                            "GridEntityDesc Type");
    } else if (!std::strcmp(key, "Variant")) {
        Write<std::int32_t>(state, element, kGridDescVariant,
                            static_cast<std::int32_t>(luaL_checkinteger(state, 3)),
                            "GridEntityDesc Variant");
    } else if (!std::strcmp(key, "VarData")) {
        Write<std::int32_t>(state, element, kGridDescVarData,
                            static_cast<std::int32_t>(luaL_checkinteger(state, 3)),
                            "GridEntityDesc VarData");
    } else {
        luaL_error(state, "unknown GridEntityDesc field");
    }
    return 0;
}

void NewMetatable(lua_State* state, const char* name, lua_CFunction index,
                  lua_CFunction newIndex, lua_CFunction length) {
    luaL_newmetatable(state, name);
    lua_pushcfunction(state, index);
    lua_setfield(state, -2, "__index");
    if (newIndex) {
        lua_pushcfunction(state, newIndex);
        lua_setfield(state, -2, "__newindex");
    }
    if (length) {
        lua_pushcfunction(state, length);
        lua_setfield(state, -2, "__len");
    }
    lua_pop(state, 1);
}

}  // namespace

void RegisterRepentogonSaveStateViews(lua_State* state) {
    if (!state) return;
    luaL_getmetatable(state, LuaRuntime::kRoomDescriptorMetatable);
    if (!lua_istable(state, -1)) {
        luaL_error(state, "RoomDescriptor metatable is unavailable");
    }
    lua_getfield(state, -1, "__methods");
    if (!lua_istable(state, -1)) {
        luaL_error(state, "RoomDescriptor method table is unavailable");
    }
    static_cast<void>(AttachOwnerMethods(state, "RoomDescriptor", nullptr, 0));
    lua_pop(state, 2);

    NewMetatable(state, kEntityVectorMetatable, EntityVectorIndex, nullptr,
                 RepentogonEntitiesSaveStateVectorLen);
    NewMetatable(state, kGridVectorMetatable, GridVectorIndex, nullptr,
                 RepentogonGridEntitiesSaveStateVectorLen);
    NewMetatable(state, kEntityStateMetatable, EntityStateIndex, nullptr,
                 nullptr);
    NewMetatable(state, kGridDescMetatable, GridDescIndex, GridDescNewIndex,
                 nullptr);
    luaL_getmetatable(state, kEntityVectorMetatable);
    static_cast<void>(AttachOwnerMethods(state, "EntitiesSaveStateVector", nullptr, 0));
    lua_pop(state, 1);
    luaL_getmetatable(state, kGridVectorMetatable);
    static_cast<void>(AttachOwnerMethods(state, "GridEntitiesSaveStateVector", nullptr, 0));
    lua_pop(state, 1);
    luaL_getmetatable(state, kEntityStateMetatable);
    static_cast<void>(AttachOwnerMethods(state, "EntitiesSaveState", nullptr, 0));
    lua_pop(state, 1);
}

int RepentogonRoomDescriptorGetEntitiesSaveState(lua_State* state) {
    const auto descriptor = Descriptor(state);
    if (lua_gettop(state) != 1) return luaL_error(state, "accepts no arguments");
    PushVector(state, descriptor, kSavedEntitiesOffset, VectorKind::Entity);
    return 1;
}

int RepentogonRoomDescriptorGetDecoSaveState(lua_State* state) {
    const auto descriptor = Descriptor(state);
    if (lua_gettop(state) != 1) return luaL_error(state, "accepts no arguments");
    PushVector(state, descriptor, kSavedEffectsOffset, VectorKind::Entity);
    return 1;
}

int RepentogonRoomDescriptorGetGridEntitiesSaveState(lua_State* state) {
    const auto descriptor = Descriptor(state);
    if (lua_gettop(state) != 1) return luaL_error(state, "accepts no arguments");
    PushVector(state, descriptor, kSavedGridEntitiesOffset, VectorKind::Grid);
    return 1;
}

int RepentogonEntitiesSaveStateVectorGet(lua_State* state) {
    auto* handle = static_cast<VectorHandle*>(luaL_checkudata(
        state, 1, kEntityVectorMetatable));
    const auto index = static_cast<std::uint32_t>(luaL_checkinteger(state, 2));
    const auto vector = engine_memory::AddressOf(handle->vector);
    const auto view = ReadVector(state, vector, kEntitySaveStateStride,
                                 "EntitiesSaveStateVector");
    const auto count = (view.end - view.begin) / view.stride;
    if (index >= count) return luaL_argerror(state, 2, "index out of range");
    auto* element = static_cast<EntityStateHandle*>(
        lua_newuserdata(state, sizeof(EntityStateHandle)));
    *element = {handle->vector,
                engine_memory::AsObject(view.begin + index * view.stride),
                index, 0};
    luaL_getmetatable(state, kEntityStateMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int RepentogonEntitiesSaveStateVectorLen(lua_State* state) {
    auto* handle = static_cast<VectorHandle*>(luaL_checkudata(
        state, 1, kEntityVectorMetatable));
    const auto vector = engine_memory::AddressOf(handle->vector);
    const auto view = ReadVector(state, vector, kEntitySaveStateStride,
                                 "EntitiesSaveStateVector");
    lua_pushinteger(state, static_cast<lua_Integer>(
                               (view.end - view.begin) / view.stride));
    return 1;
}

int RepentogonEntitiesSaveStateGetType(lua_State* state) {
    auto* handle = static_cast<EntityStateHandle*>(
        luaL_checkudata(state, 1, kEntityStateMetatable));
    const auto element = LiveVectorElement(state, handle, "EntitiesSaveState");
    lua_pushinteger(state, Read<std::uint32_t>(
                               state, element, kEntitySaveStateType,
                               "EntitiesSaveState Type"));
    return 1;
}

int RepentogonEntitiesSaveStateGetVariant(lua_State* state) {
    auto* handle = static_cast<EntityStateHandle*>(
        luaL_checkudata(state, 1, kEntityStateMetatable));
    const auto element = LiveVectorElement(state, handle, "EntitiesSaveState");
    lua_pushinteger(state, Read<std::uint32_t>(
                               state, element, kEntitySaveStateVariant,
                               "EntitiesSaveState Variant"));
    return 1;
}

int RepentogonEntitiesSaveStateGetSubType(lua_State* state) {
    auto* handle = static_cast<EntityStateHandle*>(
        luaL_checkudata(state, 1, kEntityStateMetatable));
    const auto element = LiveVectorElement(state, handle, "EntitiesSaveState");
    lua_pushinteger(state, Read<std::uint32_t>(
                               state, element, kEntitySaveStateSubType,
                               "EntitiesSaveState SubType"));
    return 1;
}

int RepentogonEntitiesSaveStateGetI3(lua_State* state) {
    auto* handle = static_cast<EntityStateHandle*>(
        luaL_checkudata(state, 1, kEntityStateMetatable));
    const auto element = LiveVectorElement(state, handle, "EntitiesSaveState");
    lua_pushinteger(state, Read<std::int32_t>(
                               state, element, kEntitySaveStateI3,
                               "EntitiesSaveState I3"));
    return 1;
}

int RepentogonGridEntitiesSaveStateVectorGet(lua_State* state) {
    auto* handle = static_cast<VectorHandle*>(luaL_checkudata(
        state, 1, kGridVectorMetatable));
    const auto index = static_cast<std::uint32_t>(luaL_checkinteger(state, 2));
    const auto vector = engine_memory::AddressOf(handle->vector);
    const auto view = ReadVector(state, vector, kGridEntityDescStride,
                                 "GridEntitiesSaveStateVector");
    const auto count = (view.end - view.begin) / view.stride;
    if (index >= count) return luaL_argerror(state, 2, "index out of range");
    auto* element = static_cast<GridDescHandle*>(
        lua_newuserdata(state, sizeof(GridDescHandle)));
    *element = {handle->vector,
                engine_memory::AsObject(view.begin + index * view.stride),
                index, 0};
    luaL_getmetatable(state, kGridDescMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int RepentogonGridEntitiesSaveStateVectorLen(lua_State* state) {
    auto* handle = static_cast<VectorHandle*>(luaL_checkudata(
        state, 1, kGridVectorMetatable));
    const auto vector = engine_memory::AddressOf(handle->vector);
    const auto view = ReadVector(state, vector, kGridEntityDescStride,
                                 "GridEntitiesSaveStateVector");
    lua_pushinteger(state, static_cast<lua_Integer>(
                               (view.end - view.begin) / view.stride));
    return 1;
}

}
