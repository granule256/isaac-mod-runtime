#include "interfaces/lua/api700_player.hpp"
#include "interfaces/lua/api700_player.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/api700_string.hpp"
#include "interfaces/lua/vector_api.hpp"
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
api100_native::Cache g_Cache[6]{};
#if !defined(__SWITCH__)
Api700PlayerNativeTestBindings g_Tests{};
#endif
void* Player(lua_State*L){
 luaL_checkudata(L,1,LuaRuntime::kEntityPlayerMetatable);
 const auto p=ResolveEngineReceiver(L,FieldReceipt::EntityPlayer,1);
 if(!p){luaL_error(L,"EntityPlayer reference is no longer available");}
 return engine_memory::AsObject(p);
}
std::int32_t Integer(lua_State*L,int i){const auto u=static_cast<std::uint32_t>(luaL_checkinteger(L,i));std::int32_t s;std::memcpy(&s,&u,4);return s;}
// PC main.lua1033..1042补公开默认值；NS ANM2::Play会strcmp，不能把缺省名传nullptr。
const char* OptionalString(lua_State*L,int i,const char*fallback){return lua_toboolean(L,i)?luaL_checkstring(L,i):fallback;}
template<class Fn>Fn Native(lua_State*L,unsigned n){
 std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Tests.methods[n];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(L,api700_player::kEntries[n],g_Cache[n],host));
}
}
#if !defined(__SWITCH__)
void SetApi700PlayerNativeTestBindings(Api700PlayerNativeTestBindings b)noexcept{g_Tests=b;}
#endif
int Api700EntityPlayerAnimatePill(lua_State*L){auto*p=Player(L);const auto id=Integer(L,2);const auto*a=OptionalString(L,3,"Pickup");Native<void(*)(void*,std::int32_t,const char*)>(L,0)(p,id,a);return 0;}
int Api700EntityPlayerAnimateTrinket(lua_State*L){auto*p=Player(L);const auto id=Integer(L,2);const auto*a=OptionalString(L,3,"Pickup");const auto*b=OptionalString(L,4,"PlayerPickupSparkle");Native<void(*)(void*,std::int32_t,const char*,const char*)>(L,1)(p,id,a,b);return 0;}
int Api700EntityPlayerSwapActiveItems(lua_State*L){auto*p=Player(L);Native<void(*)(void*)>(L,2)(p);return 0;}
int Api700EntityPlayerTryRemoveCollectibleCostume(lua_State*L){auto*p=Player(L);const auto id=Integer(L,2);const bool keep=lua_toboolean(L,3)!=0;Native<void(*)(void*,std::int32_t,bool)>(L,3)(p,id,keep);return 0;}

namespace {
struct CostumePos{void*player;bool head;LuaRuntime::VectorHandle direction;std::uintptr_t fn;};
int CostumePosition(lua_State*L,const void*text,void*context){auto&c=*static_cast<CostumePos*>(context);const auto v=engine_call::AsFunction<LuaRuntime::VectorHandle(*)(const void*,const void*,bool,const LuaRuntime::VectorHandle&)>(c.fn)(c.player,text,c.head,c.direction);PushLuaVector(L,v.x,v.y);return 1;}
struct CostumeSprite{void*player;const void*item;std::int32_t priority;std::uintptr_t fn;};
int CostumeReplacement(lua_State*,const void*text,void*context){auto&c=*static_cast<CostumeSprite*>(context);engine_call::AsFunction<void(*)(void*,const void*,const void*,std::int32_t)>(c.fn)(c.player,c.item,text,c.priority);return 0;}
}
int Api700EntityPlayerGetCostumeNullPos(lua_State*L){auto*p=Player(L);const auto direction=*RequireVectorArgument(L,4);CostumePos c{p,lua_toboolean(L,3)!=0,direction,engine_call::AddressOfFunction(Native<LuaRuntime::VectorHandle(*)(const void*,const void*,bool,const LuaRuntime::VectorHandle&)>(L,4))};return WithApi700NativeString(L,2,CostumePosition,&c);}
int Api700EntityPlayerReplaceCostumeSprite(lua_State*L){auto*p=Player(L);const auto item=ItemConfigPointerArgument(L,2);if(lua_toboolean(L,2)&&!item){return luaL_argerror(L,2,"live ItemConfigItem or nil expected");}const auto priority=Integer(L,4);CostumeSprite c{p,engine_memory::AsObject(item),priority,engine_call::AddressOfFunction(Native<void(*)(void*,const void*,const void*,std::int32_t)>(L,5))};return WithApi700NativeString(L,3,CostumeReplacement,&c);}
int Api700EntityPlayerQueueExtraAnimation(lua_State*L){auto*p=Player(L);static api100_native::Cache cache{};static_cast<void>(api100_native::Resolve(L,api700_player::kQueueEntry,cache));AssignApi700NativeString(L,engine_memory::AddressOf(p)+0x1718,2);return 0;}

namespace {
constexpr char kConstRef[]="IsaacRuntime.ConstEntityRef";
constexpr char kPocket[]="IsaacRuntime.ConstPlayerPocketItem";
struct View{LuaRuntime::EntityLifetimeToken*lifetime;std::uintptr_t entity,base;unsigned offset;};
std::uintptr_t ViewAddress(lua_State*L,View*v){if(!EntityLifetimeAlive(v->lifetime)||v->base!=LuaRuntime::EngineModuleBase()||!IsLiveEntityPointer(v->entity)){luaL_error(L,"player view reference owner is no longer available");}return v->entity+v->offset;}
template<class T>T ViewRead(lua_State*L,std::uintptr_t p,unsigned offset){T value{};if(!engine_memory::ReadField(p,offset,&value,engine_memory::EngineMemoryReadable)){luaL_error(L,"player view memory is not readable");}return value;}
int ConstIndex(lua_State*L){const auto p=ViewAddress(L,static_cast<View*>(luaL_checkudata(L,1,kConstRef)));const auto*n=lua_tostring(L,2);if(!n){lua_pushnil(L);return 1;}
 if(!std::strcmp(n,"Position")){const auto v=ViewRead<LuaRuntime::VectorHandle>(L,p,0x10);PushLuaVector(L,v.x,v.y);}
 else if(!std::strcmp(n,"IsFriendly")||!std::strcmp(n,"IsCharmed")){const auto flags=ViewRead<std::uint32_t>(L,p,0x20);lua_pushboolean(L,(flags&(n[2]=='F'?2U:1U))!=0);}
 else if(!std::strcmp(n,"Type")){lua_pushinteger(L,ViewRead<std::uint32_t>(L,p,0));}
 else if(!std::strcmp(n,"Variant")){lua_pushinteger(L,ViewRead<std::uint32_t>(L,p,4));}
 else if(!std::strcmp(n,"SpawnerType")){lua_pushinteger(L,ViewRead<std::int32_t>(L,p,8));}
 else if(!std::strcmp(n,"SpawnerVariant")){lua_pushinteger(L,ViewRead<std::uint32_t>(L,p,12));}
 else if(!std::strcmp(n,"Entity")){const auto e=ViewRead<std::uintptr_t>(L,p,0x28);if(e){PushEntityCallbackArgument(L,e);}else{lua_pushnil(L);}}
 else{lua_pushnil(L);}return 1;
}
int PocketIndex(lua_State*L){static_cast<void>(ViewAddress(L,static_cast<View*>(luaL_checkudata(L,1,kPocket))));lua_pushnil(L);return 1;}
int ConstNewIndex(lua_State*L){View*v=static_cast<View*>(luaL_testudata(L,1,kConstRef));if(!v)v=static_cast<View*>(luaL_checkudata(L,1,kPocket));static_cast<void>(ViewAddress(L,v));return luaL_error(L,"player view is const");}
void PushView(lua_State*L,std::uintptr_t p,unsigned offset,const char*mt){auto*t=PushEntityLifetimeToken(L,p);const int token=lua_gettop(L);auto*v=static_cast<View*>(lua_newuserdata(L,sizeof(View)));*v={t,p,LuaRuntime::EngineModuleBase(),offset};luaL_getmetatable(L,mt);lua_setmetatable(L,-2);lua_pushvalue(L,token);lua_setuservalue(L,-2);lua_remove(L,token);}
}
void RegisterApi700PlayerTypes(lua_State*L){
 if(luaL_newmetatable(L,kConstRef)){lua_pushcfunction(L,ConstIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,ConstNewIndex);lua_setfield(L,-2,"__newindex");lua_pushliteral(L,"EntityRef");lua_setfield(L,-2,"__type");luaL_getmetatable(L,LuaRuntime::kEntityRefMetatable);lua_getfield(L,-1,"__class");lua_setfield(L,-3,"__class");lua_pop(L,1);}lua_pop(L,1);
 if(luaL_newmetatable(L,kPocket)){lua_pushcfunction(L,PocketIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,ConstNewIndex);lua_setfield(L,-2,"__newindex");lua_pushliteral(L,"PlayerPocketItem");lua_setfield(L,-2,"__type");lua_pushvalue(L,-1);lua_setfield(L,-2,"__class");}lua_pop(L,1);
}
void* Api700ConstEntityRefBufferAt(lua_State*L,int index)noexcept{auto*v=static_cast<View*>(luaL_testudata(L,index,kConstRef));if(!v)return nullptr;const auto p=ViewAddress(L,v);if(!engine_memory::EngineMemoryReadable(p,0x30)){luaL_error(L,"EntityRef memory is not readable");}return engine_memory::AsObject(p);}
int Api700EntityPlayerGetLastDamageSource(lua_State*L){auto*p=Player(L);static api100_native::Cache cache{};static_cast<void>(api100_native::Resolve(L,api700_player::kLastDamageEntry,cache));PushView(L,engine_memory::AddressOf(p),0x1a70,kConstRef);return 1;}
int Api700EntityPlayerGetPocketItem(lua_State*L){auto*p=Player(L);const auto slot=static_cast<std::uint32_t>(Integer(L,2));if(slot>=4){return luaL_argerror(L,2,"pocket slot must be in 0..3");}static api100_native::Cache cache{};static_cast<void>(api100_native::Resolve(L,api700_player::kPocketEntry,cache));PushView(L,engine_memory::AddressOf(p),0x1c10+slot*8,kPocket);return 1;}
}
