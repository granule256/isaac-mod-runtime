#include "interfaces/lua/repentogon_runtime_api.hpp"

#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"

extern "C" {
#include <lauxlib.h>
}

namespace isaac::runtime {
namespace {
// HasWater reads the actual water amount; update_water_current uses this Vector2.
constexpr std::uint8_t kWaterAmountGuard[]={0x88,0x22,0x8f,0x52,0x00,0x68,0x68,0xbc,0x08,0x20,0x20,0x1e,0xe0,0xd7,0x9f,0x1a};
constexpr std::uint8_t kWaterCurrentGuard[]={0x08,0x8f,0x8f,0x52,0x14,0x00,0x08,0x8b,0xf3,0x03,0x00,0xaa,0xe0,0x03,0x14,0xaa};
constexpr api100_native::Entry kWaterLayouts[]={
    {0x487fa0,kWaterAmountGuard},{0x4714b4,kWaterCurrentGuard},
};
api100_native::Cache g_WaterLayouts[2]{};

std::uintptr_t WaterRoom(lua_State* state,unsigned layout) {
    if(!LuaRuntime::IsOnGameThread())luaL_error(state,"Room water access requires the game thread");
    luaL_checkudata(state,1,LuaRuntime::kRoomMetatable);
    const auto room=ResolveEngineReceiver(state,FieldReceipt::Room,1);
    if(!room)luaL_error(state,"Room reference is no longer available");
    static_cast<void>(api100_native::Resolve(state,kWaterLayouts[layout],g_WaterLayouts[layout]));
    return room;
}
}

int RepentogonIsaacIsInGame(lua_State* state) {
    if(!LuaRuntime::IsOnGameThread())return luaL_error(state,"Isaac.IsInGame requires the game thread");
    const auto base=LuaRuntime::EngineModuleBase();
    std::uintptr_t slot{},manager{};
    std::uint32_t scene{};
    // Manager::Render uses this same scene discriminator, including during menus.
    const bool readable=base&&
        engine_memory::ReadField(base,kGameManagerGlobalSlotOffset,&slot,engine_memory::EngineMemoryReadable)&&
        slot&&engine_memory::ReadAt(slot,&manager,engine_memory::EngineMemoryReadable)&&
        manager&&engine_memory::ReadField(manager,kManagerRenderSceneOffset,&scene,engine_memory::EngineMemoryReadable);
    lua_pushboolean(state,readable&&scene==kManagerGameplayScene);
    return 1;
}

int RepentogonRoomSetWaterAmount(lua_State* state) {
    const auto room=WaterRoom(state,0);
    const auto amount=static_cast<float>(luaL_checknumber(state,2));
    // Pinned NS HasWater @0x487FA0 reads +0x7914, not the old +0x7894 annotation.
    if(!engine_memory::WriteField(room,0x7914,amount,engine_memory::EngineMemoryWritable))
        return luaL_error(state,"Room water amount is not writable");
    return 0;
}

int RepentogonRoomSetWaterCurrent(lua_State* state) {
    const auto room=WaterRoom(state,1);
    const auto vector=*RequireVectorArgument(state,2);
    if(!engine_memory::WriteField(room,kApi300RoomGetWaterCurrentFieldOffset,vector,
        engine_memory::EngineMemoryWritable))return luaL_error(state,"Room water current is not writable");
    return 0;
}
}
