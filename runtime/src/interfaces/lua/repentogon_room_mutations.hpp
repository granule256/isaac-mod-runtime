#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int RepentogonRoomRemoveGridEntityImmediate(lua_State*);
int RepentogonRoomGetBackdropType(lua_State*);
int RepentogonRoomSetBackdropType(lua_State*);
int RepentogonRoomSetRail(lua_State*);
using RepentogonBackdropInitNative = void (*)(void*,std::uint32_t,bool);
// Applies XMLData's BackdropConfig fields, then runs the native Backdrop::Init.
// Returns false when a matching XML record is invalid or a referenced ANM2
// path does not exist.
bool ApplyRepentogonBackdropInit(void*,std::uint32_t,bool,RepentogonBackdropInitNative) noexcept;
void SetRepentogonBackdropInitFallback(RepentogonBackdropInitNative) noexcept;
RepentogonBackdropInitNative RepentogonBackdropInitFallback() noexcept;
#if !defined(__SWITCH__)
struct RepentogonRoomMutationNativeTestBindings {
    void (*removeGrid)(void*,std::int32_t,std::int32_t,bool){};
    void (*initBackdrop)(void*,std::uint32_t,bool){};
    void (*assignBackdropString)(void*,const char*){};
    bool (*backdropPathExists)(const char*){};
};
void SetRepentogonRoomMutationNativeTestBindings(RepentogonRoomMutationNativeTestBindings) noexcept;
#endif
}
