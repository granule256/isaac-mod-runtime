#pragma once
struct lua_State;
namespace isaac::runtime {
int Api600SpriteGetOverlayAnimation(lua_State*);
int Api600SpriteSetOverlayRenderPriority(lua_State*);
int Api600RandomVector(lua_State*);
}
