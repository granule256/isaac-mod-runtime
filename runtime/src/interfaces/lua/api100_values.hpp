#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api100ColorSetOffset(lua_State*);
int Api100ColorSetTint(lua_State*);
int Api100ColorReset(lua_State*);
int Api100SpriteReload(lua_State*);
int Api100SpriteRemoveOverlay(lua_State*);
int Api100MusicManagerFadein(lua_State*);
int Api100MusicManagerFadeout(lua_State*);
enum class Api100ValuesNative:unsigned {ColorSetOffset,ColorSetTint,ColorReset,SpriteReload,SpriteRemoveOverlay,MusicManagerFadein,MusicManagerFadeout,Count};
#if !defined(__SWITCH__)
struct Api100ValuesNativeTestBindings {std::uintptr_t methods[static_cast<unsigned>(Api100ValuesNative::Count)];};
void SetApi100ValuesNativeTestBindings(Api100ValuesNativeTestBindings) noexcept;
#endif
}
