#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
int Api700EntityPlayerAnimatePill(lua_State*);
int Api700EntityPlayerAnimateTrinket(lua_State*);
int Api700EntityPlayerSwapActiveItems(lua_State*);
int Api700EntityPlayerTryRemoveCollectibleCostume(lua_State*);
int Api700EntityPlayerGetCostumeNullPos(lua_State*);
int Api700EntityPlayerReplaceCostumeSprite(lua_State*);
int Api700EntityPlayerQueueExtraAnimation(lua_State*);
void RegisterApi700PlayerTypes(lua_State*);
void* Api700ConstEntityRefBufferAt(lua_State*,int)noexcept;
int Api700EntityPlayerGetLastDamageSource(lua_State*);
int Api700EntityPlayerGetPocketItem(lua_State*);
#if !defined(__SWITCH__)
struct Api700PlayerNativeTestBindings{std::uintptr_t methods[6];};
void SetApi700PlayerNativeTestBindings(Api700PlayerNativeTestBindings)noexcept;
#endif
}
