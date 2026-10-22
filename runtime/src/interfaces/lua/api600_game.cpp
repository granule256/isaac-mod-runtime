#include "interfaces/lua/api600_game.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/bitset128_api.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <array>
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
using Vec=LuaRuntime::VectorHandle;
struct Layout{std::uintptr_t offset;std::array<std::uint8_t,16> bytes;};
constexpr Layout kNatives[]={
{0x354e14,{0xe9,0x23,0xe,0x6d,0xfd,0x7b,0xf,0xa9,0xfd,0xc3,0x3,0x91,0xfc,0x6f,0x10,0xa9}},
{0x355c78,{0xfd,0x7b,0xb,0xa9,0xfd,0xc3,0x2,0x91,0xfc,0x6f,0xc,0xa9,0xfa,0x67,0xd,0xa9}},
{0x35673c,{0xe9,0x23,0x10,0x6d,0xfd,0x7b,0x11,0xa9,0xfd,0x43,0x4,0x91,0xfc,0x6f,0x12,0xa9}},
{0x35bf84,{0xfd,0x7b,0x6,0xa9,0xfd,0x83,0x1,0x91,0xfc,0x6f,0x7,0xa9,0xfa,0x67,0x8,0xa9}},
{0x35232c,{0xfc,0x6f,0xf,0xa9,0xfa,0x67,0x10,0xa9,0xf8,0x5f,0x11,0xa9,0xf6,0x57,0x12,0xa9}},
{0x47fb18,{0xfd,0x7b,0x4,0xa9,0xfd,0x3,0x1,0x91,0xfc,0x6f,0x5,0xa9,0xfa,0x67,0x6,0xa9}},
{0xf5f38,{0x1,0x1,0x27,0x1e,0x0,0x8,0x4,0xbd,0x0,0x28,0x21,0x1e,0x0,0x34,0x1,0xbd}},
{0x63b94,{0xf6,0x57,0x6,0xa9,0xf4,0x4f,0x7,0xa9,0xf5,0x3,0x5,0x2a,0xf7,0x3,0x4,0x2a}},
};
constexpr Layout kFields[]={
{0x5c754,{0x8,0x10,0x41,0xf9,0x9,0x14,0x41,0xf9,0xa,0x18,0x41,0xf9,0x8,0xa4,0x13,0xa9}},
{0xf76b4,{0x68,0x36,0x11,0x91,0xe9,0x1f,0x80,0x52,0x74,0xa,0x5,0xb9,0x60,0x62,0x11,0x91}},
};
api100_native::Cache g_Natives[8]{},g_Fields[2]{};
#if !defined(__SWITCH__)
Api600GameNativeTestBindings g_Tests{};
#endif
template<class F>F Native(lua_State*L,unsigned n){const auto&g=kNatives[n];const auto address=api100_native::Resolve(L,{g.offset,g.bytes.data()},g_Natives[n]);
#if !defined(__SWITCH__)
 if(g_Tests.methods[n])return engine_call::AsFunction<F>(g_Tests.methods[n]);
#endif
 return engine_call::AsFunction<F>(address-16);
}
void FieldGuard(lua_State*L,unsigned n){const auto&g=kFields[n];static_cast<void>(api100_native::Resolve(L,{g.offset,g.bytes.data()},g_Fields[n]));}
void* Game(lua_State*L){luaL_checkudata(L,1,LuaRuntime::kGameMetatable);const auto p=ResolveEngineReceiver(L,FieldReceipt::Level,1);if(!p)luaL_error(L,"Game reference is no longer available");return engine_memory::AsObject(p);}
void* Room(lua_State*L){luaL_checkudata(L,1,LuaRuntime::kRoomMetatable);const auto p=ResolveEngineReceiver(L,FieldReceipt::Room,1);if(!p)luaL_error(L,"Room reference is no longer available");return engine_memory::AsObject(p);}
void* Source(lua_State*L,int index){if(lua_isnoneornil(L,index))return nullptr;const auto p=EntityPointerArgument(L,index);if(!p)luaL_argerror(L,index,"live Entity or nil expected");return engine_memory::AsObject(p);}
float Number(lua_State*L,int i,float fallback){return lua_toboolean(L,i)?static_cast<float>(luaL_checknumber(L,i)):fallback;}
std::uint64_t Integer(lua_State*L,int i,std::uint64_t fallback){return lua_toboolean(L,i)?static_cast<std::uint64_t>(luaL_checkinteger(L,i)):fallback;}
bool Line(lua_State*L,int i){return !(lua_isboolean(L,i)&&!lua_toboolean(L,i));}
BitSet128Value Flags(lua_State*L,int i,bool optional){BitSet128Value f{};if(optional&&!lua_toboolean(L,i))return f;if(ReadBitSet128(L,i,&f))return f;if(lua_isinteger(L,i)){f.low=static_cast<std::uint64_t>(lua_tointeger(L,i));return f;}luaL_argerror(L,i,"BitSet128 or integer expected");return f;}
template<class T>T Read(lua_State*L,std::uintptr_t p,unsigned o){T v{};if(!engine_memory::ReadField(p,o,&v,engine_memory::EngineMemoryReadable))luaL_error(L,"api600 entity field is not readable");return v;}
}
#if !defined(__SWITCH__)
void SetApi600GameNativeTestBindings(Api600GameNativeTestBindings v)noexcept{g_Tests=v;}
#endif
int Api600GameBombDamage(lua_State*L){auto*self=Game(L);const auto&pos=*RequireVectorArgument(L,2);const auto damage=static_cast<float>(luaL_checknumber(L,3)),radius=static_cast<float>(luaL_checknumber(L,4));const auto line=Line(L,5);auto*source=Source(L,6);const auto flags=Flags(L,7,true);const auto df=Integer(L,8,4);const bool ds=lua_toboolean(L,9)!=0;
 Native<void(*)(void*,const Vec&,float,float,bool,void*,BitSet128Value,std::uint64_t,bool)>(L,0)(self,pos,damage,radius,line,source,flags,df,ds);return 0;}
int Api600GameBombExplosionEffects(lua_State*L){auto*self=Game(L);const auto&pos=*RequireVectorArgument(L,2);const auto damage=static_cast<float>(luaL_checknumber(L,3));const auto flags=Flags(L,4,true);auto color=DefaultEngineColorMod();if(lua_toboolean(L,5)&&!FillEngineColorMod(L,5,&color))return luaL_argerror(L,5,"Color expected");auto*source=Source(L,6);const auto radius=Number(L,7,1);const auto line=Line(L,8);const bool ds=lua_toboolean(L,9)!=0;const auto df=Integer(L,10,4);
 Native<void(*)(void*,const Vec&,float,BitSet128Value,const EngineColorMod&,void*,float,bool,std::uint64_t,bool)>(L,1)(self,pos,damage,flags,color,source,radius,line,df,ds);return 0;}
int Api600GameBombTearflagEffects(lua_State*L){auto*self=Game(L);const auto&pos=*RequireVectorArgument(L,2);const auto radius=static_cast<float>(luaL_checknumber(L,3));const auto flags=Flags(L,4,false);auto*source=Source(L,5);const auto mult=Number(L,6,1);Native<void(*)(void*,const Vec&,float,BitSet128Value,void*,float)>(L,2)(self,pos,radius,flags,source,mult);return 0;}
int Api600GameUpdateStrangeAttractor(lua_State*L){auto*self=Game(L);const auto&pos=*RequireVectorArgument(L,2);const auto force=Number(L,3,10),radius=Number(L,4,250);Native<void(*)(void*,const Vec&,float,float,bool(*)(void*))>(L,3)(self,pos,force,radius,nullptr);return 0;}
int Api600GameRender(lua_State*L){auto*self=Game(L);Native<void(*)(void*)>(L,4)(self);return 0;}
int Api600RoomRender(lua_State*L){auto*self=Room(L);Native<void(*)(void*)>(L,5)(self);return 0;}
int TryPushApi600ExtraEntityField(lua_State*L,std::uintptr_t p,const char*n){
 if(!n||!n[0])return 0;
 if(n[0]=='C'&&n[1]=='o'&&!std::strcmp(n,"Color")){FieldGuard(L,0);PushLuaColorFromEngineColorMod(L,Read<EngineColorMod>(L,p,0x220));return 1;}
 const bool angle=n[0]=='A'&&n[1]=='n'&&!std::strcmp(n,"Angle"),sample=n[0]=='S'&&n[1]=='a'&&!std::strcmp(n,"SampleLaser");if(!angle&&!sample)return 0;
 if(ClassifyCallbackEntity(p)!=CallbackEntityClass::Laser)return 0;
 if(angle){static_cast<void>(Native<void(*)(void*,float)>(L,6));lua_pushnumber(L,Read<float>(L,p,0x40c));}else{FieldGuard(L,1);lua_pushboolean(L,Read<std::uint8_t>(L,p,0x44d)!=0);}return 1;
}
bool TryWriteApi600ExtraEntityField(lua_State*L,std::uintptr_t p,const char*n){
 if(!n||!n[0])return false;
 if(n[0]=='C'&&n[1]=='o'&&!std::strcmp(n,"Color")){EngineColorMod color{};if(!FillEngineColorMod(L,3,&color))luaL_argerror(L,3,"Color expected");Native<void(*)(void*,const EngineColorMod*,std::int32_t,std::int32_t,bool,bool)>(L,7)(engine_memory::AsObject(p),&color,-1,255,false,true);return true;}
 const bool angle=n[0]=='A'&&n[1]=='n'&&!std::strcmp(n,"Angle"),sample=n[0]=='S'&&n[1]=='a'&&!std::strcmp(n,"SampleLaser");if(!angle&&!sample)return false;
 if(ClassifyCallbackEntity(p)!=CallbackEntityClass::Laser)return false;
 if(angle){const auto value=static_cast<float>(luaL_checknumber(L,3));Native<void(*)(void*,float)>(L,6)(engine_memory::AsObject(p),value);}else{FieldGuard(L,1);const auto value=static_cast<std::uint8_t>(lua_toboolean(L,3)!=0);if(!engine_memory::WriteField(p,0x44d,value,engine_memory::EngineMemoryWritable))luaL_error(L,"Laser.SampleLaser is not writable");}return true;
}
}
