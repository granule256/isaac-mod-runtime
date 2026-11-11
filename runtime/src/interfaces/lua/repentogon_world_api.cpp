#include "interfaces/lua/repentogon_world_api.hpp"

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

} // namespace

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
