#include "interfaces/lua/api300_player.hpp"
#include "interfaces/lua/api300_player.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/vector_api.hpp"
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
namespace guards=api300_player;
using Vec2=LuaRuntime::VectorHandle;
constexpr api100_native::Entry kEntries[]={
 {guards::kCanTurnHeadEntry,guards::kCanTurnHeadGuard.data()},
 {guards::kGetActiveWeaponEntityEntry,guards::kGetActiveWeaponEntityGuard.data()},
 {guards::kRenderHeadEntry,guards::kRenderHeadGuard.data()},
 {guards::kRenderBodyEntry,guards::kRenderBodyGuard.data()},
};
api100_native::Cache g_Native[4]{},g_Constructor{},g_Init{},g_Active{};
static_assert(std::is_trivial_v<api100_native::Cache>);
#if !defined(__SWITCH__)
Api300PlayerNativeTestBindings g_Tests{};
#endif
__attribute__((noinline)) std::uintptr_t Player(lua_State*state){
 luaL_checkudata(state,1,LuaRuntime::kEntityPlayerMetatable);
 const auto p=ResolveEngineReceiver(state,FieldReceipt::EntityPlayer,1);
 if(!p)luaL_error(state,"EntityPlayer reference is no longer available");
 return p;
}
__attribute__((noinline)) void Layout(lua_State*state){
 static_cast<void>(api100_native::Resolve(state,{guards::kLayoutConstructorEntry,guards::kLayoutConstructorGuard.data()},g_Constructor,0));
 static_cast<void>(api100_native::Resolve(state,{guards::kLayoutInitEntry,guards::kLayoutInitGuard.data()},g_Init,0));
}
template<class T>__attribute__((noinline)) T Read(lua_State*state,std::uintptr_t p,std::uintptr_t offset){
 T value{};if(!engine_memory::ReadField(p,offset,&value,engine_memory::EngineMemoryReadable))luaL_error(state,"EntityPlayer field is not readable");return value;
}
template<class T>__attribute__((noinline)) void Write(lua_State*state,std::uintptr_t p,std::uintptr_t offset,const T&value){
 if(!engine_memory::WriteField(p,offset,value,engine_memory::EngineMemoryWritable))luaL_error(state,"EntityPlayer field is not writable");
}
std::int32_t Int(lua_State*state,int index){const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(state,index));std::int32_t value{};std::memcpy(&value,&bits,4);return value;}
int Slot(lua_State*state){
 const auto slot=lua_toboolean(state,2)?Int(state,2):0;
 // 公开PC bootstrap false/nil/缺省→0；真实四槽结构，非法槽是原件越界访问，不读取相邻字段。
 if(slot<0||slot>3)luaL_argerror(state,2,"active slot must be in range 0..3");
 static_cast<void>(api100_native::Resolve(state,{guards::kActiveLayoutEntry,guards::kActiveLayoutGuard.data()},g_Active,0));
 return slot;
}
template<class Fn>Fn Native(lua_State*state,Api300PlayerNative id){
 const auto n=static_cast<unsigned>(id);std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Tests.methods[n];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(state,kEntries[n],g_Native[n],host));
}
int EntityResult(lua_State*state,void*object){if(object)PushEntityCallbackArgument(state,engine_memory::AddressOf(object));else lua_pushnil(state);return 1;}
}
#if !defined(__SWITCH__)
void SetApi300PlayerNativeTestBindings(Api300PlayerNativeTestBindings value) noexcept{g_Tests=value;}
#endif
int Api300EntityPlayerCanShoot(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushboolean(state,Read<std::uint8_t>(state,p,0x1c9d)!=0);return 1;
}
int Api300EntityPlayerCanTurnHead(lua_State*state){
 const auto p=Player(state);
 lua_pushboolean(state,Native<bool(*)(void*)>(state,Api300PlayerNative::CanTurnHead)(engine_memory::AsObject(p)));return 1;
}
int Api300EntityPlayerRenderBody(lua_State*state){
 const auto p=Player(state);
 const auto&v=*RequireVectorArgument(state,2);Native<void(*)(void*,const Vec2&)>(state,Api300PlayerNative::RenderBody)(engine_memory::AsObject(p),v);return 0;
}
int Api300EntityPlayerGetActiveWeaponEntity(lua_State*state){
 const auto p=Player(state);
 return EntityResult(state,Native<void*(*)(void*)>(state,Api300PlayerNative::GetActiveWeaponEntity)(engine_memory::AsObject(p)));
}
int Api300EntityPlayerGetBatteryCharge(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 const auto slot=Slot(state);lua_pushinteger(state,Read<std::int32_t>(state,p,0x196c+static_cast<std::uintptr_t>(slot)*0x1c));return 1;
}
int Api300EntityPlayerGetBodyColor(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushinteger(state,Read<std::int32_t>(state,p,0x1d10));return 1;
}
int Api300EntityPlayerGetHeadColor(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushinteger(state,Read<std::int32_t>(state,p,0x1d0c));return 1;
}
int Api300EntityPlayerGetItemState(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushinteger(state,Read<std::int32_t>(state,p,0x19d4));return 1;
}
int Api300EntityPlayerGetJarFlies(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushinteger(state,Read<std::int32_t>(state,p,0x16d0));return 1;
}
int Api300EntityPlayerGetLastActionTriggers(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushinteger(state,Read<std::int32_t>(state,p,0x16f0));return 1;
}
int Api300EntityPlayerGetLastDamageFlags(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 const auto bits=Read<std::uint64_t>(state,p,0x1aa0);lua_Integer value{};static_assert(sizeof(value)==sizeof(bits));std::memcpy(&value,&bits,sizeof(value));lua_pushinteger(state,value);return 1;
}
int Api300EntityPlayerGetLastDirection(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 PushEntityVectorReference(state,p,0x1a10);return 1;
}
int Api300EntityPlayerGetMovementVector(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 PushEntityVectorReference(state,p,0x1a18);return 1;
}
int Api300EntityPlayerGetNumBlueFlies(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushinteger(state,Read<std::int32_t>(state,p,0x16e4));return 1;
}
int Api300EntityPlayerGetNumBlueSpiders(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushinteger(state,Read<std::int32_t>(state,p,0x16e8));return 1;
}
int Api300EntityPlayerGetNumGigaBombs(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushinteger(state,Read<std::int32_t>(state,p,0x24a4));return 1;
}
int Api300EntityPlayerGetRecentMovementVector(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 PushEntityVectorReference(state,p,0x1a28);return 1;
}
int Api300EntityPlayerGetSmoothBodyRotation(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushnumber(state,Read<float>(state,p,0x20e0));return 1;
}
int Api300EntityPlayerGetTearPoisonDamage(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushnumber(state,Read<float>(state,p,0x1960));return 1;
}
int Api300EntityPlayerGetTearRangeModifier(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushinteger(state,Read<std::int32_t>(state,p,0x1914));return 1;
}
int Api300EntityPlayerGetTotalDamageTaken(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushinteger(state,static_cast<lua_Integer>(Read<std::uint32_t>(state,p,0x1aac)));return 1;
}
int Api300EntityPlayerGetTractorBeam(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 return EntityResult(state,engine_memory::AsObject(Read<std::uintptr_t>(state,p,0x17c8)));
}
int Api300EntityPlayerGetVelocityBeforeUpdate(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 PushEntityVectorReference(state,p,0x1a34);return 1;
}
int Api300EntityPlayerHasCurseMistEffect(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushboolean(state,Read<std::uint8_t>(state,p,0x27e0)!=0);return 1;
}
int Api300EntityPlayerIsItemQueueEmpty(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushboolean(state,Read<std::uintptr_t>(state,p,0x1c38)==0);return 1;
}
int Api300EntityPlayerIsP2Appearing(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushboolean(state,Read<std::uint32_t>(state,p,kEntityVariantOffset)==1&&Read<std::int32_t>(state,p,0x1734)>0);return 1;
}
int Api300EntityPlayerSetBloodCharge(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 const auto value=Int(state,2);Write(state,p,0x247c,value);return 0;
}
int Api300EntityPlayerSetSoulCharge(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 const auto value=Int(state,2);Write(state,p,0x2478,value);return 0;
}
int Api300EntityPlayerRenderHead(lua_State*state){
 const auto p=Player(state);
 const auto&v=*RequireVectorArgument(state,2);Native<void(*)(void*,const Vec2&)>(state,Api300PlayerNative::RenderHead)(engine_memory::AsObject(p),v);return 0;
}
int Api300EntityPlayerAddControlsCooldown(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 const auto amount=static_cast<std::uint32_t>(Int(state,2));const auto value=Read<std::uint32_t>(state,p,0x404)+amount;Write(state,p,0x404,value);return 0;
}
int Api300EntityPlayerAreControlsEnabled(lua_State*state){
 const auto p=Player(state);
 Layout(state);
 lua_pushboolean(state,Read<std::uint8_t>(state,p,kEntityPlayerControlsEnabledOffset)!=0&&Read<std::int32_t>(state,p,kEntityPlayerControlsCooldownOffset)<=0);return 1;
}
}
