// `EntityRef` 的实现（口径、布局证据与"还没做什么"都写在 `entity_ref_api.hpp`）。

#include "interfaces/lua/entity_ref_api.hpp"

#include <cstring>

extern "C" {
#include <lauxlib.h>
}

#include "interfaces/lua/isaac_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"

namespace isaac::runtime {
namespace {

using LuaRuntime::kEntityRefMetatable;

// 引擎 `Entity::EntityRef` 的格子（偏移的证据见头文件）。
constexpr std::size_t kRefVariantOffset = 0x00;
constexpr std::size_t kRefTypeOffset = 0x08;
constexpr std::size_t kRefEntityOffset = 0x28;

template <typename T>
void WriteAt(std::uint8_t* storage, std::size_t offset, T value) {
    std::memcpy(storage + offset, &value, sizeof(T));
}

template <typename T>
T ReadAt(const std::uint8_t* storage, std::size_t offset) {
    T value{};
    std::memcpy(&value, storage + offset, sizeof(T));
    return value;
}

} // namespace

int CreateEntityRefHandle(lua_State* state) {
    const int argumentCount = lua_gettop(state);
    if (argumentCount > 1) {
        return luaL_error(state, "EntityRef accepts an optional entity");
    }
    auto* handle = static_cast<LuaRuntime::EntityRefHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::EntityRefHandle)));
    std::memset(handle->storage, 0, sizeof(handle->storage));
    if (argumentCount == 1 && !lua_isnoneornil(state, 1)) {
        // `EntityPointerArgument` 是**不抛错**的出口（拿不到就 0）：PC 允许 `EntityRef(nil)`，
        // 而那与"空引用"同义；这里也照此降级，不把模组打断。
        const std::uintptr_t entity = EntityPointerArgument(state, 1);
        if (entity != 0) {
            WriteAt(handle->storage, kRefEntityOffset, entity);
            // `Type`/`Variant` 从实体上读（判可读的那套在 `isaac_api.cpp`，所以走它导出的入口）。
            // 读不到就**留空**：引擎对空值有判空分支，而猜一个值会改变引擎的判断。
            std::uint32_t type = 0;
            std::uint32_t variant = 0;
            if (ReadEntityIdentity(entity, &type, &variant)) {
                WriteAt(handle->storage, kRefTypeOffset, type);
                WriteAt(handle->storage, kRefVariantOffset, variant);
            }
        }
    }
    luaL_getmetatable(state, kEntityRefMetatable);
    lua_setmetatable(state, -2);
    return 1;
}

int EntityRefIndex(lua_State* state) {
    auto* handle = static_cast<LuaRuntime::EntityRefHandle*>(
        luaL_checkudata(state, 1, kEntityRefMetatable));
    if (handle == nullptr || lua_type(state, 2) != LUA_TSTRING) {
        lua_pushnil(state);
        return 1;
    }
    const char* key = lua_tostring(state, 2);
    if (std::strcmp(key, "Type") == 0) {
        lua_pushinteger(state, static_cast<lua_Integer>(ReadAt<std::uint32_t>(handle->storage,
                                                                              kRefTypeOffset)));
        return 1;
    }
    if (std::strcmp(key, "Variant") == 0) {
        lua_pushinteger(state, static_cast<lua_Integer>(
                                   ReadAt<std::uint32_t>(handle->storage, kRefVariantOffset)));
        return 1;
    }
    if (std::strcmp(key, "Entity") == 0) {
        const std::uintptr_t entity =
            ReadAt<std::uintptr_t>(handle->storage, kRefEntityOffset);
        if (entity == 0) {
            lua_pushnil(state);
            return 1;
        }
        PushEntityCallbackArgument(state, entity);
        return 1;
    }
    lua_pushnil(state);
    return 1;
}

void* EntityRefBufferAt(lua_State* state, int index) noexcept {
    void* raw = luaL_testudata(state, index, kEntityRefMetatable);
    if (raw == nullptr) {
        return nullptr;
    }
    return reinterpret_cast<LuaRuntime::EntityRefHandle*>(raw)->storage;
}

} // namespace isaac::runtime
