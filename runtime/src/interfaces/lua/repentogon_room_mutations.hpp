#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int RepentogonRoomRemoveGridEntityImmediate(lua_State*);
int RepentogonRoomSetBackdropType(lua_State*);
#if !defined(__SWITCH__)
struct RepentogonRoomMutationNativeTestBindings {
    void (*removeGrid)(void*,std::int32_t,std::int32_t,bool){};
    void (*initBackdrop)(void*,std::uint32_t,bool){};
};
void SetRepentogonRoomMutationNativeTestBindings(RepentogonRoomMutationNativeTestBindings) noexcept;
#endif
}
