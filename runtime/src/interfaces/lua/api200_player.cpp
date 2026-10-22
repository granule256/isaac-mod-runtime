#include "interfaces/lua/api200_player.hpp"
#include "interfaces/lua/api200_player.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/bitset128_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
#include <type_traits>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
using Vec2=LuaRuntime::VectorHandle;
namespace guards=api200_player;
constexpr api100_native::Entry kEntries[]={
 {guards::kAddCurseMistEffectEntry,guards::kAddCurseMistEffectGuard.data()},
 {guards::kAddDollarBillEffectEntry,guards::kAddDollarBillEffectGuard.data()},
 {guards::kAddPlayerFormCostumeEntry,guards::kAddPlayerFormCostumeGuard.data()},
 {guards::kAnimatePitfallInEntry,guards::kAnimatePitfallInGuard.data()},
 {guards::kAnimatePitfallOutEntry,guards::kAnimatePitfallOutGuard.data()},
 {guards::kAnimateTeleportEntry,guards::kAnimateTeleportGuard.data()},
 {guards::kDoZitEffectEntry,guards::kDoZitEffectGuard.data()},
 {guards::kDropPocketItemEntry,guards::kDropPocketItemGuard.data()},
 {guards::kFireBrimstoneEntry,guards::kFireBrimstoneGuard.data()},
 {guards::kFireDelayedBrimstoneEntry,guards::kFireDelayedBrimstoneGuard.data()},
 {guards::kFireKnifeEntry,guards::kFireKnifeGuard.data()},
 {guards::kFireTechXLaserEntry,guards::kFireTechXLaserGuard.data()},
 {guards::kGetBombFlagsEntry,guards::kGetBombFlagsGuard.data()},
 {guards::kGetFlyingOffsetEntry,guards::kGetFlyingOffsetGuard.data()},
 {guards::kGetLaserOffsetEntry,guards::kGetLaserOffsetGuard.data()},
 {guards::kGetNPCTargetEntry,guards::kGetNPCTargetGuard.data()},
 {guards::kHasInvincibilityEntry,guards::kHasInvincibilityGuard.data()},
 {guards::kInitBabySkinEntry,guards::kInitBabySkinGuard.data()},
 {guards::kIsFullSpriteRenderingEntry,guards::kIsFullSpriteRenderingGuard.data()},
 {guards::kIsPosInSpotLightEntry,guards::kIsPosInSpotLightGuard.data()},
 {guards::kPlayExtraAnimationEntry,guards::kPlayExtraAnimationGuard.data()},
 {guards::kQueueItemEntry,guards::kQueueItemGuard.data()},
 {guards::kRemoveCurseMistEffectEntry,guards::kRemoveCurseMistEffectGuard.data()},
 {guards::kRemoveSkinCostumeEntry,guards::kRemoveSkinCostumeGuard.data()},
 {guards::kResetItemStateEntry,guards::kResetItemStateGuard.data()},
 {guards::kRespawnFamiliarsEntry,guards::kRespawnFamiliarsGuard.data()},
 {guards::kShootRedCandleEntry,guards::kShootRedCandleGuard.data()},
 {guards::kSpawnMawOfVoidEntry,guards::kSpawnMawOfVoidGuard.data()},
 {guards::kThrowFriendlyDipEntry,guards::kThrowFriendlyDipGuard.data()},
 {guards::kTriggerBookOfVirtuesEntry,guards::kTriggerBookOfVirtuesGuard.data()},
 {guards::kTryHoldEntityEntry,guards::kTryHoldEntityGuard.data()},
 {guards::kTryHoldTrinketEntry,guards::kTryHoldTrinketGuard.data()},
 {guards::kUpdateCanShootEntry,guards::kUpdateCanShootGuard.data()},
 {guards::kUsePoopSpellEntry,guards::kUsePoopSpellGuard.data()},
};
constexpr unsigned kCount=static_cast<unsigned>(Api200PlayerNative::Count);
static_assert(sizeof(kEntries)/sizeof(kEntries[0])==kCount);
static_assert(std::is_trivial_v<api100_native::Cache>);
static_assert(sizeof(Vec2)==8&&sizeof(BitSet128Value)==16);
api100_native::Cache g_Cache[kCount]{};
#if !defined(__SWITCH__)
Api200PlayerNativeTestBindings g_Tests{};
#endif
void* Player(lua_State*state){
 luaL_checkudata(state,1,LuaRuntime::kEntityPlayerMetatable);
 const auto p=ResolveEngineReceiver(state,FieldReceipt::EntityPlayer,1);
 if(!p)luaL_error(state,"EntityPlayer reference is no longer available");
 return engine_memory::AsObject(p);
}
std::int32_t Int(lua_State*state,int index){const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(state,index));std::int32_t value{};std::memcpy(&value,&bits,4);return value;}
bool Bool(lua_State*state,int index){return lua_toboolean(state,index)!=0;}
std::int32_t IntOr(lua_State*state,int index,std::int32_t fallback){return Bool(state,index)?Int(state,index):fallback;}
lua_Integer IntegerOr(lua_State*state,int index,lua_Integer fallback){return Bool(state,index)?luaL_checkinteger(state,index):fallback;}
float Number(lua_State*state,int index){return static_cast<float>(luaL_checknumber(state,index));}
float NumberOr(lua_State*state,int index,float fallback){return Bool(state,index)?Number(state,index):fallback;}
const Vec2& Vector(lua_State*state,int index){return *RequireVectorArgument(state,index);}
void* Entity(lua_State*state,int index,bool omitted){
 // PC lua_type==LUA_TNIL接受nullptr；bootstrap可选source也允许缺省。
 if(lua_isnil(state,index)||(omitted&&lua_isnone(state,index)))return nullptr;
 const auto p=EntityPointerArgument(state,index);
 if(!p)luaL_argerror(state,index,"live Entity or nil expected");
 return engine_memory::AsObject(p);
}
void* RequiredEntity(lua_State*state,int index){
 const auto p=EntityPointerArgument(state,index);
 if(!p)luaL_argerror(state,index,"live Entity expected (native requires non-null)");
 return engine_memory::AsObject(p);
}
const void* Item(lua_State*state,int index){
 // 固定PC848696的nil清队列；公开bootstrap将缺省item补nil，false仍类型报错。
 if(lua_isnoneornil(state,index))return nullptr;
 const auto p=ItemConfigPointerArgument(state,index);
 if(!p)luaL_argerror(state,index,"live ItemConfigItem or nil expected");
 return engine_memory::AsObject(p);
}
template<class Fn>Fn Native(lua_State*state,Api200PlayerNative method){
 const auto index=static_cast<unsigned>(method);std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Tests.methods[index];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(state,kEntries[index],g_Cache[index],host));
}
}
#if !defined(__SWITCH__)
void SetApi200PlayerNativeTestBindings(Api200PlayerNativeTestBindings value) noexcept{g_Tests=value;}
#endif
int Api200EntityPlayerAddCurseMistEffect(lua_State*state){
 auto*p=Player(state);
 Native<void(*)(void*)>(state,Api200PlayerNative::AddCurseMistEffect)(p);return 0;
}
int Api200EntityPlayerAddDollarBillEffect(lua_State*state){
 auto*p=Player(state);
 Native<void(*)(void*)>(state,Api200PlayerNative::AddDollarBillEffect)(p);return 0;
}
int Api200EntityPlayerAddPlayerFormCostume(lua_State*state){
 auto*p=Player(state);
 std::int32_t a0=Int(state,2);
 Native<void(*)(void*,std::int32_t)>(state,Api200PlayerNative::AddPlayerFormCostume)(p,a0);return 0;
}
int Api200EntityPlayerAnimatePitfallIn(lua_State*state){
 auto*p=Player(state);
 bool a0=Bool(state,2);
 Native<void(*)(void*,bool)>(state,Api200PlayerNative::AnimatePitfallIn)(p,a0);return 0;
}
int Api200EntityPlayerAnimatePitfallOut(lua_State*state){
 auto*p=Player(state);
 Native<void(*)(void*)>(state,Api200PlayerNative::AnimatePitfallOut)(p);return 0;
}
int Api200EntityPlayerAnimateTeleport(lua_State*state){
 auto*p=Player(state);
 bool a0=Bool(state,2);
 Native<void(*)(void*,bool)>(state,Api200PlayerNative::AnimateTeleport)(p,a0);return 0;
}
int Api200EntityPlayerDoZitEffect(lua_State*state){
 auto*p=Player(state);
 const Vec2& a0=Vector(state,2);
 Native<void(*)(void*,const Vec2&)>(state,Api200PlayerNative::DoZitEffect)(p,a0);return 0;
}
int Api200EntityPlayerDropPocketItem(lua_State*state){
 auto*p=Player(state);
 std::uint32_t a0=static_cast<std::uint32_t>(Int(state,2));
 const Vec2& a1=Vector(state,3);
 Native<void(*)(void*,std::uint32_t,const Vec2&)>(state,Api200PlayerNative::DropPocketItem)(p,a0,a1);return 0;
}
int Api200EntityPlayerFireBrimstone(lua_State*state){
 auto*p=Player(state);
 const Vec2& a0=Vector(state,2);
 void* a1=Entity(state,3,true);
 float a2=NumberOr(state,4,1.0F);
 const auto result=Native<void*(*)(void*,const Vec2&,void*,float)>(state,Api200PlayerNative::FireBrimstone)(p,a0,a1,a2);if(result)PushEntityCallbackArgument(state,engine_memory::AddressOf(result));else lua_pushnil(state);return 1;
}
int Api200EntityPlayerFireDelayedBrimstone(lua_State*state){
 auto*p=Player(state);
 float a0=Number(state,2);
 void* a1=RequiredEntity(state,3);
 const auto result=Native<void*(*)(void*,float,void*)>(state,Api200PlayerNative::FireDelayedBrimstone)(p,a0,a1);if(result)PushEntityCallbackArgument(state,engine_memory::AddressOf(result));else lua_pushnil(state);return 1;
}
int Api200EntityPlayerFireKnife(lua_State*state){
 auto*p=Player(state);
 void* a0=Entity(state,2,true);
 std::uint32_t a1=static_cast<std::uint32_t>(IntOr(state,6,0));
 float a2=NumberOr(state,3,0.0F);
 bool a3=Bool(state,4);
 std::uint32_t a4=static_cast<std::uint32_t>(IntOr(state,5,0));
 const auto result=Native<void*(*)(void*,void*,std::uint32_t,float,bool,std::uint32_t)>(state,Api200PlayerNative::FireKnife)(p,a0,a1,a2,a3,a4);if(result)PushEntityCallbackArgument(state,engine_memory::AddressOf(result));else lua_pushnil(state);return 1;
}
int Api200EntityPlayerFireTechXLaser(lua_State*state){
 auto*p=Player(state);
 const Vec2& a0=Vector(state,2);
 const Vec2& a1=Vector(state,3);
 float a2=Number(state,4);
 void* a3=Entity(state,5,true);
 float a4=NumberOr(state,6,1.0F);
 const auto result=Native<void*(*)(void*,const Vec2&,const Vec2&,float,void*,float)>(state,Api200PlayerNative::FireTechXLaser)(p,a0,a1,a2,a3,a4);if(result)PushEntityCallbackArgument(state,engine_memory::AddressOf(result));else lua_pushnil(state);return 1;
}
int Api200EntityPlayerGetBombFlags(lua_State*state){
 auto*p=Player(state);
 bool a0=Bool(state,2);
 const auto result=Native<BitSet128Value(*)(void*,bool)>(state,Api200PlayerNative::GetBombFlags)(p,a0);PushBitSet128(state,result);return 1;
}
int Api200EntityPlayerGetFlyingOffset(lua_State*state){
 auto*p=Player(state);
 const auto result=Native<Vec2(*)(void*)>(state,Api200PlayerNative::GetFlyingOffset)(p);PushLuaVector(state,result.x,result.y);return 1;
}
int Api200EntityPlayerGetLaserOffset(lua_State*state){
 auto*p=Player(state);
 std::int32_t a0=Int(state,2);
 const Vec2& a1=Vector(state,3);
 const auto result=Native<Vec2(*)(void*,std::int32_t,const Vec2&)>(state,Api200PlayerNative::GetLaserOffset)(p,a0,a1);PushLuaVector(state,result.x,result.y);return 1;
}
int Api200EntityPlayerGetNPCTarget(lua_State*state){
 auto*p=Player(state);
 const auto result=Native<void*(*)(void*)>(state,Api200PlayerNative::GetNPCTarget)(p);if(result)PushEntityCallbackArgument(state,engine_memory::AddressOf(result));else lua_pushnil(state);return 1;
}
int Api200EntityPlayerHasInvincibility(lua_State*state){
 auto*p=Player(state);
 std::uint64_t a0=static_cast<std::uint64_t>(IntegerOr(state,2,0));
 lua_pushboolean(state,Native<bool(*)(void*,std::uint64_t)>(state,Api200PlayerNative::HasInvincibility)(p,a0));return 1;
}
int Api200EntityPlayerInitBabySkin(lua_State*state){
 auto*p=Player(state);
 Native<void(*)(void*)>(state,Api200PlayerNative::InitBabySkin)(p);return 0;
}
int Api200EntityPlayerIsFullSpriteRendering(lua_State*state){
 auto*p=Player(state);
 lua_pushboolean(state,Native<bool(*)(void*)>(state,Api200PlayerNative::IsFullSpriteRendering)(p));return 1;
}
int Api200EntityPlayerIsPosInSpotLight(lua_State*state){
 auto*p=Player(state);
 const Vec2& a0=Vector(state,2);
 lua_pushboolean(state,Native<bool(*)(void*,const Vec2&)>(state,Api200PlayerNative::IsPosInSpotLight)(p,a0));return 1;
}
int Api200EntityPlayerPlayExtraAnimation(lua_State*state){
 auto*p=Player(state);
 const char* a0=luaL_checkstring(state,2);
 Native<void(*)(void*,const char*)>(state,Api200PlayerNative::PlayExtraAnimation)(p,a0);return 0;
}
int Api200EntityPlayerQueueItem(lua_State*state){
 auto*p=Player(state);
 const void* a0=Item(state,2);
 std::int32_t a1=IntOr(state,3,0);
 std::uint8_t a2=static_cast<std::uint8_t>((Bool(state,4)?1:0)|(Bool(state,5)?2:0));
 std::int32_t a3=IntOr(state,6,0);
 Native<void(*)(void*,const void*,std::int32_t,std::uint8_t,std::int32_t)>(state,Api200PlayerNative::QueueItem)(p,a0,a1,a2,a3);return 0;
}
int Api200EntityPlayerRemoveCurseMistEffect(lua_State*state){
 auto*p=Player(state);
 Native<void(*)(void*)>(state,Api200PlayerNative::RemoveCurseMistEffect)(p);return 0;
}
int Api200EntityPlayerRemoveSkinCostume(lua_State*state){
 auto*p=Player(state);
 Native<void(*)(void*)>(state,Api200PlayerNative::RemoveSkinCostume)(p);return 0;
}
int Api200EntityPlayerResetItemState(lua_State*state){
 auto*p=Player(state);
 Native<void(*)(void*)>(state,Api200PlayerNative::ResetItemState)(p);return 0;
}
int Api200EntityPlayerRespawnFamiliars(lua_State*state){
 auto*p=Player(state);
 Native<void(*)(void*)>(state,Api200PlayerNative::RespawnFamiliars)(p);return 0;
}
int Api200EntityPlayerShootRedCandle(lua_State*state){
 auto*p=Player(state);
 const Vec2& a0=Vector(state,2);
 Native<void(*)(void*,const Vec2&)>(state,Api200PlayerNative::ShootRedCandle)(p,a0);return 0;
}
int Api200EntityPlayerSpawnMawOfVoid(lua_State*state){
 auto*p=Player(state);
 std::int32_t a0=Int(state,2);
 const auto result=Native<void*(*)(void*,std::int32_t)>(state,Api200PlayerNative::SpawnMawOfVoid)(p,a0);if(result)PushEntityCallbackArgument(state,engine_memory::AddressOf(result));else lua_pushnil(state);return 1;
}
int Api200EntityPlayerThrowFriendlyDip(lua_State*state){
 auto*p=Player(state);
 std::int32_t a0=Int(state,2);
 const Vec2& a1=Vector(state,3);
 const Vec2& a2=Vector(state,4);
 const auto result=Native<void*(*)(void*,std::int32_t,const Vec2&,const Vec2&)>(state,Api200PlayerNative::ThrowFriendlyDip)(p,a0,a1,a2);if(result)PushEntityCallbackArgument(state,engine_memory::AddressOf(result));else lua_pushnil(state);return 1;
}
int Api200EntityPlayerTriggerBookOfVirtues(lua_State*state){
 auto*p=Player(state);
 std::int32_t a0=IntOr(state,2,0);
 std::int32_t a1=IntOr(state,3,0);
 Native<void(*)(void*,std::int32_t,std::int32_t)>(state,Api200PlayerNative::TriggerBookOfVirtues)(p,a0,a1);return 0;
}
int Api200EntityPlayerTryHoldEntity(lua_State*state){
 auto*p=Player(state);
 void* a0=RequiredEntity(state,2);
 lua_pushboolean(state,Native<bool(*)(void*,void*)>(state,Api200PlayerNative::TryHoldEntity)(p,a0));return 1;
}
int Api200EntityPlayerTryHoldTrinket(lua_State*state){
 auto*p=Player(state);
 std::int32_t a0=Int(state,2);
 lua_pushboolean(state,Native<bool(*)(void*,std::int32_t)>(state,Api200PlayerNative::TryHoldTrinket)(p,a0));return 1;
}
int Api200EntityPlayerUpdateCanShoot(lua_State*state){
 auto*p=Player(state);
 Native<void(*)(void*)>(state,Api200PlayerNative::UpdateCanShoot)(p);return 0;
}
int Api200EntityPlayerUsePoopSpell(lua_State*state){
 auto*p=Player(state);
 std::int32_t a0=Int(state,2);
 Native<void(*)(void*,std::int32_t)>(state,Api200PlayerNative::UsePoopSpell)(p,a0);return 0;
}
}
