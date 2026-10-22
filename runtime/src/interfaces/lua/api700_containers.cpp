#include "interfaces/lua/api700_containers.hpp"
#include "interfaces/lua/api700_bindings.hpp"
#include "interfaces/lua/api700_containers.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include <cstring>
#include <new>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
Api700EntityArray::Api700EntityArray(const Api700EntityArray&v)noexcept{std::memcpy(bytes,v.bytes,24);}
namespace {
constexpr char kEntities[]="IsaacRuntime.EntityList";constexpr char kVectors[]="IsaacRuntime.VectorList";
api100_native::Cache g_Cache[5]{};
#if !defined(__SWITCH__)
std::uintptr_t g_Tests[3]{};
#endif
struct List {std::uintptr_t base,owner,descriptor,object,arena;std::uint32_t arenaCapacity;bool vector,query;LuaRuntime::EntityLifetimeToken*lifetime;Api700EntityArray value;};
template<class T>T Read(lua_State*L,std::uintptr_t p,unsigned offset){T v{};if(!engine_memory::ReadField(p,offset,&v,engine_memory::EngineMemoryReadable)){luaL_error(L,"container memory is not readable");}return v;}
template<class T>T At(const void*p,unsigned offset){T v{};std::memcpy(&v,static_cast<const unsigned char*>(p)+offset,sizeof(v));return v;}
std::int32_t Integer(lua_State*L,int i){const auto u=static_cast<std::uint32_t>(luaL_checkinteger(L,i));std::int32_t s{};std::memcpy(&s,&u,4);return s;}
void Guard(lua_State*L,unsigned i){static_cast<void>(api100_native::Resolve(L,api700_containers::kEntries[i],g_Cache[i]));}
template<class Fn>Fn Native(lua_State*L,unsigned i){std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Tests[i];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(L,api700_containers::kEntries[i],g_Cache[i],host));}
std::uintptr_t Room(lua_State*L){const auto p=ResolveEngineReceiver(L,FieldReceipt::Room);if(!p){luaL_error(L,"current Room reference is unavailable");}return p;}
std::uintptr_t NPC(lua_State*L){luaL_checkudata(L,1,LuaRuntime::kEntityNPCMetatable);const auto p=ResolveEngineReceiver(L,FieldReceipt::Entity);if(!p||ClassifyCallbackEntity(p)!=CallbackEntityClass::Npc){luaL_error(L,"NPC reference is unavailable");}return p;}
void Check(lua_State*L,const List&v){if(v.base!=LuaRuntime::EngineModuleBase()){luaL_error(L,"container module has changed");}
 if(v.vector){if(!EntityLifetimeAlive(v.lifetime)||!IsLiveEntityPointer(v.owner)||ClassifyCallbackEntity(v.owner)!=CallbackEntityClass::Laser){luaL_error(L,"VectorList reference owner is unavailable");}}
 else{if(Room(L)!=v.owner||Read<std::uintptr_t>(L,v.owner,8)!=v.descriptor){luaL_error(L,"EntityList Room owner has changed");}if(v.query&&(Read<std::uintptr_t>(L,v.owner,0x1a28)!=v.arena||Read<std::uint32_t>(L,v.owner,0x1a30)!=v.arenaCapacity)){luaL_error(L,"EntityList arena has changed");}}
}
List* Get(lua_State*L,int index,const char*mt){auto*v=static_cast<List*>(luaL_checkudata(L,index,mt));return v;}
struct Span{std::uintptr_t begin;std::uint64_t count;};
Span Data(lua_State*L,const List&v){Check(L,v);if(v.vector){const auto begin=Read<std::uintptr_t>(L,v.object,0),end=Read<std::uintptr_t>(L,v.object,8),cap=Read<std::uintptr_t>(L,v.object,16);if(end<begin||cap<end||(end-begin)%8||(cap-begin)%8){luaL_error(L,"VectorList native array is invalid");}return{begin,(end-begin)/8};}
 const auto p=v.query?engine_memory::AddressOf(v.value.bytes):v.object;const auto begin=Read<std::uintptr_t>(L,p,8);const auto count=Read<std::uint32_t>(L,p,20),cap=Read<std::uint32_t>(L,p,16);if(count>cap){luaL_error(L,"EntityList native array is invalid");}if(v.query&&(begin<v.arena||(begin-v.arena)%8||(begin-v.arena)/8+count>v.arenaCapacity)){luaL_error(L,"EntityList result is outside arena");}return{begin,count};
}
int ReadOnly(lua_State*L){auto*v=static_cast<List*>(luaL_testudata(L,1,kVectors));if(!v)v=static_cast<List*>(luaL_checkudata(L,1,kEntities));Check(L,*v);return luaL_error(L,"container is read-only");}
List* Push(lua_State*L,const List&value,const char*mt){auto*v=new(lua_newuserdata(L,sizeof(List)))List(value);luaL_getmetatable(L,mt);lua_setmetatable(L,-2);return v;}
int Samples(lua_State*L,unsigned offset){luaL_checkudata(L,1,LuaRuntime::kEntityLaserMetatable);const auto p=ResolveEngineReceiver(L,FieldReceipt::Entity);if(!p||ClassifyCallbackEntity(p)!=CallbackEntityClass::Laser){return luaL_error(L,"Laser reference owner is unavailable");}Guard(L,3);auto*t=PushEntityLifetimeToken(L,p);const int token=lua_gettop(L);List value{};value.base=LuaRuntime::EngineModuleBase();value.owner=p;value.object=p+offset;value.vector=true;value.lifetime=t;Push(L,value,kVectors);lua_pushvalue(L,token);lua_setuservalue(L,-2);lua_remove(L,token);return 1;}
int Query(lua_State*L,unsigned kind){const auto npc=NPC(L);const auto room=Room(L);const auto a=Integer(L,2);Api700EntityArray result{};
 if(kind==0){const auto b=Integer(L,3);result=Native<Api700EntityArray(*)(const void*,std::int32_t,std::int32_t)>(L,0)(engine_memory::AsObject(npc),a,b);}
 else if(kind==1){const auto b=Integer(L,3);const bool only=lua_toboolean(L,4)!=0;result=Native<Api700EntityArray(*)(const void*,std::int32_t,std::int32_t,bool)>(L,1)(engine_memory::AsObject(npc),a,b,only);}
 else{result=Native<Api700EntityArray(*)(void*,std::int32_t)>(L,2)(engine_memory::AsObject(npc),a);}
 // 原生本组三函数返回arena借用flag=1；拒绝未知拥有型结果，不能泄漏或擅自释放。
 if(result.bytes[0]!=1){return luaL_error(L,"EntityList returned an unsupported owned result");}
 List value{};value.base=LuaRuntime::EngineModuleBase();value.owner=room;value.descriptor=Read<std::uintptr_t>(L,room,8);value.query=true;value.arena=Read<std::uintptr_t>(L,room,0x1a28);value.arenaCapacity=Read<std::uint32_t>(L,room,0x1a30);value.value=result;static_cast<void>(Data(L,value));Push(L,value,kEntities);return 1;}
void VectorRead(lua_State*L,int owner,std::uintptr_t address,LuaRuntime::VectorHandle*out){const auto*v=Get(L,owner,kVectors);const auto s=Data(L,*v);if(address<s.begin||(address-s.begin)%8||(address-s.begin)/8>=s.count){luaL_error(L,"Vector reference array has changed");}*out=Read<LuaRuntime::VectorHandle>(L,address,0);}
int Method(lua_State*L){lua_getmetatable(L,1);lua_getfield(L,-1,"__methods");lua_pushvalue(L,2);lua_rawget(L,-2);return 1;}
int EntityIndex(lua_State*L){static_cast<void>(Get(L,1,kEntities));const auto*n=lua_tostring(L,2);if(n&&!std::strcmp(n,"Get")){return Method(L);}else if(n&&!std::strcmp(n,"Size")){lua_pushinteger(L,Data(L,*Get(L,1,kEntities)).count);}else{return Method(L);}return 1;}
int ListVectorIndex(lua_State*L){const auto*v=Get(L,1,kVectors);const auto*n=lua_tostring(L,2);if(n&&!std::strcmp(n,"Get")){return Method(L);}else if(n&&!std::strcmp(n,"Size")){lua_pushinteger(L,Data(L,*v).count);}else{return Method(L);}return 1;}
}
#if !defined(__SWITCH__)
void SetApi700ContainerNatives(const std::uintptr_t(&v)[3])noexcept{std::memcpy(g_Tests,v,sizeof(g_Tests));}
#endif
void RegisterApi700Containers(lua_State*L){for(unsigned i=0;i<2;++i){const auto*mt=i?kVectors:kEntities;luaL_newmetatable(L,mt);lua_pushcfunction(L,i?ListVectorIndex:EntityIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,ReadOnly);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachApi700Methods(L,i?"VectorList":"EntityList"));lua_getfield(L,-1,"__len");if(lua_isnil(L,-1)){lua_pop(L,1);lua_pushcfunction(L,i?Api700VectorListLen:Api700EntityListLen);}lua_setfield(L,-3,"__len");lua_setfield(L,-2,"__methods");lua_pop(L,1);PublishNativeClass(L,i?"VectorList":"EntityList",mt);}
 lua_getglobal(L,"CppContainer");if(!lua_istable(L,-1)){lua_pop(L,1);lua_newtable(L);}lua_getglobal(L,"EntityList");lua_setfield(L,-2,"EntityList");lua_getfield(L,-1,"Vector");if(!lua_istable(L,-1)){lua_pop(L,1);lua_newtable(L);}lua_getglobal(L,"VectorList");lua_setfield(L,-2,"VectorList");lua_setfield(L,-2,"Vector");lua_setglobal(L,"CppContainer");}
int Api700LaserGetSamples(lua_State*L){return Samples(L,0x478);}
int Api700LaserGetNonOptimizedSamples(lua_State*L){return Samples(L,0x490);}
int Api700NPCQueryType(lua_State*L){return Query(L,0);}
int Api700NPCQuerySpawnerType(lua_State*L){return Query(L,1);}
int Api700NPCQueryGroup(lua_State*L){return Query(L,2);}
int Api700RoomGetEntities(lua_State*L){luaL_checkudata(L,1,LuaRuntime::kRoomMetatable);const auto room=Room(L);Guard(L,4);List value{};value.base=LuaRuntime::EngineModuleBase();value.owner=room;value.descriptor=Read<std::uintptr_t>(L,room,8);value.object=room+0x19c0;static_cast<void>(Data(L,value));Push(L,value,kEntities);return 1;}
int Api700EntityListGet(lua_State*L){const auto*v=Get(L,1,kEntities);const auto s=Data(L,*v);const auto i=static_cast<std::uint32_t>(Integer(L,2));if(i>=s.count){return luaL_argerror(L,2,"EntityList index is outside array");}const auto e=Read<std::uintptr_t>(L,s.begin,i*8);if(e){PushEntityCallbackArgument(L,e);}else{lua_pushnil(L);}return 1;}
int Api700EntityListSize(lua_State*L){lua_pushinteger(L,Data(L,*Get(L,1,kEntities)).count);return 1;}
int Api700EntityListLen(lua_State*L){return Api700EntityListSize(L);}
int Api700VectorListGet(lua_State*L){const auto*v=Get(L,1,kVectors);const auto s=Data(L,*v);const auto i=static_cast<std::uint32_t>(Integer(L,2));if(i>=s.count){return luaL_argerror(L,2,"VectorList index is outside array");}PushExternalVectorReference(L,1,s.begin+i*8,VectorRead);return 1;}
int Api700VectorListLen(lua_State*L){lua_pushinteger(L,Data(L,*Get(L,1,kVectors)).count);return 1;}
}
