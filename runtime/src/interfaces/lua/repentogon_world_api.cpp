#include "interfaces/lua/repentogon_world_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"

#include "infrastructure/memory/engine_field_access.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

#include <cstdint>

extern "C" {
#include "lauxlib.h"
}

namespace isaac::runtime {
namespace {

// _ZTVN15IsaacRepentance19GridEntity_TrapDoorE is at NRO file offset 0xA38110.
// The object's first word points at the first virtual function slot (+0x10),
// so the exact runtime vptr is 0xA38120. Verify with:
//   python3 source/public/tools/nro_vtable_slot.py GridEntity_TrapDoor --find Update
// Pass --nro with the original Repentance.nro path.
// The same table reports Update in slot 3 for this class.
constexpr std::uintptr_t kGridEntityTrapDoorVtableOffset = 0xA38120;
// REPENTOGON's Lua_GridToGridTrapDoor checks GetDesc()->_type == 17
// (GridEntityTrapDoor is the GRID_TRAPDOOR type).
constexpr std::uint32_t kGridEntityTypeTrapDoor = 17;
constexpr std::uint8_t kSetStageGuard[]={0xfd,0x7b,0xbd,0xa9,0xf6,0x57,0x01,0xa9,0xfd,0x03,0x00,0x91,0xf4,0x4f,0x02,0xa9};
#if !defined(__SWITCH__)
void (*g_SetStageHost)(void*,std::int32_t,std::int32_t){};
#endif

} // namespace

int RepentogonLevelSetStage(lua_State* state) {
    if(!LuaRuntime::IsOnGameThread())return luaL_error(state,"Level:SetStage requires the game thread");
    luaL_checkudata(state,1,LuaRuntime::kLevelMetatable);
    const auto level=ResolveEngineReceiver(state,FieldReceipt::Level,1);
    if(!level)return luaL_error(state,"Level reference is no longer available");
    const auto stage=static_cast<std::int32_t>(luaL_checkinteger(state,2));
    const auto type=static_cast<std::int32_t>(luaL_checkinteger(state,3));
    const auto base=LuaRuntime::EngineModuleBase();
    if(!base||base>UINTPTR_MAX-kLevelSetStageOffset||
       !engine_call::VerifyEntryBytes(base+kLevelSetStageOffset,kSetStageGuard,sizeof(kSetStageGuard),
                                     engine_memory::EngineMemoryReadable))
        return luaL_error(state,"Level:SetStage native binding is unavailable");
    using Fn=void(*)(void*,std::int32_t,std::int32_t);
    auto method=engine_call::AsFunction<Fn>(base+kLevelSetStageOffset);
#if !defined(__SWITCH__)
    if(!g_SetStageHost)return luaL_error(state,"Level:SetStage host binding is unavailable");
    method=g_SetStageHost;
#endif
    method(engine_memory::AsObject(level),stage,type);return 0;
}
#if !defined(__SWITCH__)
void SetRepentogonLevelSetStageHost(void (*method)(void*,std::int32_t,std::int32_t)) noexcept {
    g_SetStageHost=method;
}
#endif

int RepentogonLevelGetDimension(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) return luaL_error(state, "Level:GetDimension requires the game thread");
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "Level:GetDimension accepts no arguments");
    }
    luaL_checkudata(state, 1, LuaRuntime::kLevelMetatable);
    const std::uintptr_t level =
        ResolveEngineReceiver(state, FieldReceipt::Level, 1);
    if (level == 0) {
        return luaL_error(state, "Level reference is no longer available");
    }

    std::uint32_t dimension = 0;
    if (!engine_memory::ReadField(level, kLevelCurrentRoomDimensionOffset,
                                  &dimension,
                                  engine_memory::EngineMemoryReadable)) {
        return luaL_error(state, "Level dimension is not readable");
    }
    lua_pushinteger(state, static_cast<lua_Integer>(dimension));
    return 1;
}

int RepentogonGridToTrapDoor(lua_State* state) {
    if (!LuaRuntime::IsOnGameThread()) return luaL_error(state, "GridEntity:ToTrapDoor requires the game thread");
    if (lua_gettop(state) != 1) {
        return luaL_error(state, "GridEntity:ToTrapDoor accepts no arguments");
    }
    void* raw = GridEntityHandleArgument(state, 1);
    if (raw == nullptr) {
        return luaL_error(state, "GridEntity:ToTrapDoor expects a grid entity");
    }

    const std::uintptr_t entity = engine_memory::AddressOf(raw);
    if (!IsLiveGridEntityPointer(entity)) {
        lua_pushnil(state);
        return 1;
    }

    const std::uintptr_t base = LuaRuntime::EngineModuleBase();
    if (base == 0 ||
        base > UINTPTR_MAX - kGridEntityTrapDoorVtableOffset) {
        lua_pushnil(state);
        return 1;
    }

    std::uintptr_t vtable = 0;
    std::uint32_t type = 0;
    if (!engine_memory::ReadField(entity, 0, &vtable,
                                  engine_memory::EngineMemoryReadable) ||
        vtable != base + kGridEntityTrapDoorVtableOffset ||
        !engine_memory::ReadField(entity, kGridEntityTypeOffset, &type,
                                  engine_memory::EngineMemoryReadable) ||
        type != kGridEntityTypeTrapDoor) {
        lua_pushnil(state);
        return 1;
    }

    PushGridEntityHandle(state, entity);
    return 1;
}

} // namespace isaac::runtime
