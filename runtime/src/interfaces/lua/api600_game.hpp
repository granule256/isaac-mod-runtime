#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api600GameBombDamage(lua_State*);
int Api600GameBombExplosionEffects(lua_State*);
int Api600GameBombTearflagEffects(lua_State*);
int Api600GameUpdateStrangeAttractor(lua_State*);
int Api600GameRender(lua_State*);
int Api600RoomRender(lua_State*);
int TryPushApi600ExtraEntityField(lua_State*,std::uintptr_t,const char*);
bool TryWriteApi600ExtraEntityField(lua_State*,std::uintptr_t,const char*);
#if !defined(__SWITCH__)
struct Api600GameNativeTestBindings{std::uintptr_t methods[8];};
void SetApi600GameNativeTestBindings(Api600GameNativeTestBindings)noexcept;
#endif
}
