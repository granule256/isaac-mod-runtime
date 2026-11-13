#pragma once

#include <cstdint>

struct lua_State;

namespace isaac::runtime {

void RegisterRepentogonSaveStateViews(lua_State* state);

int RepentogonRoomDescriptorGetEntitiesSaveState(lua_State* state);
int RepentogonRoomDescriptorGetDecoSaveState(lua_State* state);
int RepentogonRoomDescriptorGetGridEntitiesSaveState(lua_State* state);
int RepentogonEntitiesSaveStateVectorGet(lua_State* state);
int RepentogonEntitiesSaveStateVectorLen(lua_State* state);
int RepentogonEntitiesSaveStateVectorClear(lua_State* state);
int RepentogonEntitiesSaveStateGetType(lua_State* state);
int RepentogonEntitiesSaveStateGetVariant(lua_State* state);
int RepentogonEntitiesSaveStateGetSubType(lua_State* state);
int RepentogonEntitiesSaveStateGetI3(lua_State* state);
int RepentogonGridEntitiesSaveStateVectorGet(lua_State* state);
int RepentogonGridEntitiesSaveStateVectorLen(lua_State* state);
int RepentogonGridEntitiesSaveStateVectorClear(lua_State* state);

#if !defined(__SWITCH__)
struct RepentogonSaveStateNativeTestBindings {
    void (*entityAssign)(void*, const void*, const void*){};
};
void SetRepentogonSaveStateNativeTestBindings(
    RepentogonSaveStateNativeTestBindings bindings) noexcept;
#endif

}
