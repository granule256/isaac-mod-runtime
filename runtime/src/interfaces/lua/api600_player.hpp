#pragma once
#include <cstdint>
struct lua_State;
namespace isaac::runtime {
// POD与引擎返回/按值传参ABI一致；没有std::string/vector跨ABI。
struct alignas(8) Api600TearParams {unsigned char bytes[0x68];};
struct alignas(4) Api600MultiShotParams {unsigned char bytes[0x24];};
struct Api600PosVel {float positionX,positionY,velocityX,velocityY;};
static_assert(sizeof(Api600TearParams)==0x68);
static_assert(sizeof(Api600MultiShotParams)==0x24);
static_assert(alignof(Api600MultiShotParams)==4);
static_assert(sizeof(Api600PosVel)==0x10);
void RegisterApi600PlayerTypes(lua_State*);
int TryPushApi600PlayerField(lua_State*,std::uintptr_t,const char*);
bool TryWriteApi600PlayerField(lua_State*,std::uintptr_t,const char*);
int Api600EntityPlayerGetTearHitParams(lua_State*);
int Api600EntityPlayerGetActiveSubCharge(lua_State*);
int Api600EntityPlayerGetBombVariant(lua_State*);
int Api600EntityPlayerAreOpposingShootDirectionsPressed(lua_State*);
int Api600EntityPlayerHasWeaponType(lua_State*);
int Api600EntityPlayerGetMultiShotParams(lua_State*);
int Api600EntityPlayerGetMultiShotPositionVelocity(lua_State*);
#if !defined(__SWITCH__)
struct Api600PlayerNativeTestBindings {std::uintptr_t methods[4];};
void SetApi600PlayerNativeTestBindings(Api600PlayerNativeTestBindings)noexcept;
#endif
}

namespace isaac::runtime {std::uintptr_t Api600EntityDescArgument(lua_State*,int);}
