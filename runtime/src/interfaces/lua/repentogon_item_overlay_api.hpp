#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int RepentogonItemOverlayShow(lua_State*);
int RepentogonItemOverlayGetSprite(lua_State*);
int RepentogonItemOverlayGetMegaMushPlayerSprite(lua_State*);
int RepentogonItemOverlayGetOverlayID(lua_State*);
int RepentogonItemOverlayGetDelay(lua_State*);
int RepentogonItemOverlayGetPlayer(lua_State*);
int RegisterRepentogonItemOverlayApi(lua_State*);
#if !defined(__SWITCH__)
void SetRepentogonItemOverlayNativeTestBinding(std::uintptr_t) noexcept;
#endif
}
