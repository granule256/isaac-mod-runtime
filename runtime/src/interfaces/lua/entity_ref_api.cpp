// `EntityRef` 的实现（口径、布局证据与"还没做什么"都写在 `entity_ref_api.hpp`）。

#include "interfaces/lua/entity_ref_api.hpp"
#include "interfaces/lua/api700_player.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"

#include <cstring>

extern "C" {
#include <lauxlib.h>
}

#include "interfaces/lua/isaac_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime_state.hpp"
#include "runtime_constants.hpp"

// 2026-10-16更正：旧Type+8/Variant+0误解了消费者；Game::BombDamage
// 355380..3553BC实际构造后把sp+20作为EntityRef传入TakeDamage：
// Type0/Variant4/SpawnerType8/SpawnerVariantC、两个Vector10/18、标志20、源指针28。
// PC真实字段登记80403B..804057独立证实同样的前四格。原文件逐字归档before-entityref-layout。
namespace isaac::runtime {
namespace {

using LuaRuntime::kEntityRefMetatable;

// 引擎 `Entity::EntityRef` 的格子（偏移的证据见头文件）。
constexpr std::size_t kRefVariantOffset = 0x04;
constexpr std::size_t kRefTypeOffset = 0x00;
constexpr std::size_t kRefSpawnerTypeOffset = 0x08;
constexpr std::size_t kRefSpawnerVariantOffset = 0x0c;
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
                std::uint32_t spawnerType=0,spawnerVariant=0;
                LuaRuntime::VectorHandle position{},nativeOffset{};
                std::uint64_t flags=0;
                if(!engine_memory::ReadField(entity,kEntitySpawnerTypeOffset,&spawnerType,engine_memory::EngineMemoryReadable)||
                   !engine_memory::ReadField(entity,kEntitySpawnerVariantOffset,&spawnerVariant,engine_memory::EngineMemoryReadable)||
                   !engine_memory::ReadField(entity,0x310,&position,engine_memory::EngineMemoryReadable)||
                   !engine_memory::ReadField(entity,0x334,&nativeOffset,engine_memory::EngineMemoryReadable)||
                   !engine_memory::ReadField(entity,kEntityFlagsOffset,&flags,engine_memory::EngineMemoryReadable))
                    return luaL_error(state,"EntityRef source snapshot is not readable");
                WriteAt(handle->storage,kRefSpawnerTypeOffset,spawnerType);
                WriteAt(handle->storage,kRefSpawnerVariantOffset,spawnerVariant);
                WriteAt(handle->storage,0x10,position);WriteAt(handle->storage,0x18,nativeOffset);
                const auto refFlags=static_cast<std::uint32_t>(((flags>>8)&1U)|((flags>>28)&2U)|((flags>>52)&4U));
                WriteAt(handle->storage,0x20,refFlags);
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
    if(std::strcmp(key,"Position")==0){const auto v=ReadAt<LuaRuntime::VectorHandle>(handle->storage,0x10);PushLuaVector(state,v.x,v.y);return 1;}
    if(std::strcmp(key,"IsFriendly")==0||std::strcmp(key,"IsCharmed")==0){const unsigned mask=key[2]=='F'?2U:1U;lua_pushboolean(state,(ReadAt<std::uint32_t>(handle->storage,0x20)&mask)!=0);return 1;}
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
    if (std::strcmp(key,"SpawnerType")==0){lua_pushinteger(state,ReadAt<std::int32_t>(handle->storage,kRefSpawnerTypeOffset));return 1;}
    if (std::strcmp(key,"SpawnerVariant")==0){lua_pushinteger(state,ReadAt<std::uint32_t>(handle->storage,kRefSpawnerVariantOffset));return 1;}
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

void PushEntityRefArgument(lua_State* state, std::uintptr_t engineRef) noexcept {
    auto* handle = static_cast<LuaRuntime::EntityRefHandle*>(
        lua_newuserdata(state, sizeof(LuaRuntime::EntityRefHandle)));
    std::memset(handle->storage, 0, sizeof(handle->storage));
    if (engineRef != 0) {
        // 只搬三个有证据的格子（证据见头文件那段）：指针是引擎自己刚交给我们的函数实参，
        // 必然有效 ⇒ 直接读；其余格子刻意留零（不猜语义）。
        const auto* source = static_cast<const std::uint8_t*>(engine_memory::AsObject(engineRef));
        // 更正：当前原件已经证明前0x30字节；按原生快照逐字复制，不能把生成者误作Type。
        // EntityRef后续引用树寿命仍不据此声称完整等价，未在此发布未核公开字段。
        std::memcpy(handle->storage,source,0x30);
    }
    luaL_getmetatable(state, kEntityRefMetatable);
    lua_setmetatable(state, -2);
}

void* EntityRefBufferAt(lua_State* state, int index) noexcept {
    if(auto* view=Api700ConstEntityRefBufferAt(state,index))return view;
    void* raw = luaL_testudata(state, index, kEntityRefMetatable);
    if (raw == nullptr) {
        return nullptr;
    }
    return static_cast<LuaRuntime::EntityRefHandle*>(raw)->storage;
}

} // namespace isaac::runtime

namespace isaac::runtime {
int EntityRefNewIndex(lua_State*L){auto*h=static_cast<LuaRuntime::EntityRefHandle*>(luaL_checkudata(L,1,kEntityRefMetatable));const auto*key=luaL_checkstring(L,2);
 if(!std::strcmp(key,"Position")){const auto v=*RequireVectorArgument(L,3);WriteAt(h->storage,0x10,v);return 0;}
 if(!std::strcmp(key,"IsFriendly")||!std::strcmp(key,"IsCharmed")){const unsigned mask=key[2]=='F'?2U:1U;auto flags=ReadAt<std::uint32_t>(h->storage,0x20);flags=lua_toboolean(L,3)?flags|mask:flags&~mask;WriteAt(h->storage,0x20,flags);return 0;}
 return luaL_error(L,"EntityRef field is not writable");
}
}
