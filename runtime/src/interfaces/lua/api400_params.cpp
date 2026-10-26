#include "interfaces/lua/api400_params.hpp"
#include "interfaces/lua/api400_params.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
constexpr char kMetatable[]="IsaacRuntime.ProjectileParams";
// PC ctor430D70/public property table80417A; NS fire_projectiles reads the same
// public offsets, but its private flags at+A0 are u64. No native C++ object copied.
struct alignas(8) Params {unsigned char bytes[0xA8];};
static_assert(sizeof(Params)==0xA8);
// 元表已由registry识别，无需再扫类型；bytes就是交给NS fire_projectiles的自有native值。
std::uintptr_t ParamsIdentity(lua_State* L,int index) noexcept {
 if(lua_rawlen(L,index)!=sizeof(Params))return 0;
 const auto*value=static_cast<const Params*>(lua_touserdata(L,index));
 return engine_memory::AddressOf(value->bytes);
}
using Vec=LuaRuntime::VectorHandle;
constexpr api100_native::Entry kEntries[]={
{api400_params::kRandomU32Entry,api400_params::kRandomU32Guard.data()},
{api400_params::kFireProjectilesEntry,api400_params::kFireProjectilesGuard.data()},
{api400_params::kFireBossProjectilesEntry,api400_params::kFireBossProjectilesGuard.data()}};
api100_native::Cache g_Caches[3]{};
#if !defined(__SWITCH__)
Api400ParamsNativeTestBindings g_Tests{};
#endif
template<class Fn>Fn Native(lua_State*L,unsigned id){std::uintptr_t host{};
#if !defined(__SWITCH__)
host=g_Tests.methods[id];
#endif
return engine_call::AsFunction<Fn>(api100_native::Resolve(L,kEntries[id],g_Caches[id],host));}
template<class T>T Get(const Params*p,unsigned offset){T value;std::memcpy(&value,p->bytes+offset,sizeof(value));return value;}
template<class T>void Set(Params*p,unsigned offset,const T&value){std::memcpy(p->bytes+offset,&value,sizeof(value));}
Params* Check(lua_State*L,int index){return static_cast<Params*>(luaL_checkudata(L,index,kMetatable));}
std::int32_t Int(lua_State*L,int index){auto u=static_cast<std::uint32_t>(luaL_checkinteger(L,index));std::int32_t i;std::memcpy(&i,&u,4);return i;}
enum class Kind:unsigned char{Bool,Float,Color,U64,Vector,Int};
struct Field{const char*name;unsigned offset;Kind kind;};
constexpr Field kFields[]={
{"GridCollision",0x0,Kind::Bool},
{"HeightModifier",0x4,Kind::Float},
{"FallingSpeedModifier",0x8,Kind::Float},
{"FallingAccelModifier",0xc,Kind::Float},
{"VelocityMulti",0x10,Kind::Float},
{"Scale",0x14,Kind::Float},
{"CircleAngle",0x18,Kind::Float},
{"HomingStrength",0x1c,Kind::Float},
{"CurvingStrength",0x20,Kind::Float},
{"Acceleration",0x24,Kind::Float},
{"Spread",0x28,Kind::Float},
{"Color",0x2c,Kind::Color},
{"BulletFlags",0x58,Kind::U64},
{"PositionOffset",0x60,Kind::Vector},
{"TargetPosition",0x68,Kind::Vector},
{"FireDirectionLimit",0x70,Kind::Vector},
{"DotProductLimit",0x78,Kind::Float},
{"WiggleFrameOffset",0x7c,Kind::Int},
{"ChangeFlags",0x80,Kind::U64},
{"ChangeVelocity",0x88,Kind::Float},
{"ChangeTimeout",0x8c,Kind::Int},
{"DepthOffset",0x90,Kind::Float},
{"Variant",0x94,Kind::Int},
};
const Field*Find(const char*name){if(name)for(const auto&field:kFields)if(!std::strcmp(name,field.name))return &field;return nullptr;}
int Index(lua_State*L){const auto*p=Check(L,1);const auto*f=Find(lua_tostring(L,2));if(!f){lua_pushnil(L);return 1;}
switch(f->kind){
case Kind::Bool:lua_pushboolean(L,Get<std::uint8_t>(p,f->offset));break;
case Kind::Float:lua_pushnumber(L,Get<float>(p,f->offset));break;
case Kind::Int:lua_pushinteger(L,Get<std::int32_t>(p,f->offset));break;
case Kind::U64:{auto u=Get<std::uint64_t>(p,f->offset);lua_Integer i;static_assert(sizeof(i)==8);std::memcpy(&i,&u,8);lua_pushinteger(L,i);break;}
case Kind::Vector:{auto v=Get<Vec>(p,f->offset);PushLuaVector(L,v.x,v.y);break;}
case Kind::Color:PushLuaColorFromEngineColorMod(L,Get<EngineColorMod>(p,f->offset));break;
}return 1;}
int NewIndex(lua_State*L){auto*p=Check(L,1);const auto*f=Find(lua_tostring(L,2));if(!f)return luaL_error(L,"unknown ProjectileParams field");
switch(f->kind){
case Kind::Bool:Set(p,f->offset,static_cast<std::uint8_t>(lua_toboolean(L,3)!=0));break;
case Kind::Float:Set(p,f->offset,static_cast<float>(luaL_checknumber(L,3)));break;
case Kind::Int:Set(p,f->offset,Int(L,3));break;
case Kind::U64:Set(p,f->offset,static_cast<std::uint64_t>(luaL_checkinteger(L,3)));break;
case Kind::Vector:Set(p,f->offset,*RequireVectorArgument(L,3));break;
case Kind::Color:{EngineColorMod c{};if(!FillEngineColorMod(L,3,&c))return luaL_argerror(L,3,"expected Color");Set(p,f->offset,c);break;}
}return 0;}
int Create(lua_State*L){auto random=Native<std::uint32_t(*)()>(L,0);auto*p=static_cast<Params*>(lua_newuserdata(L,sizeof(Params)));std::memset(p,0,sizeof(*p));luaL_getmetatable(L,kMetatable);lua_setmetatable(L,-2);
Set(p,0,std::uint8_t{1});Set(p,0x10,1.0F);Set(p,0x14,1.0F);const float unit=static_cast<float>(random())*0x1p-32F;Set(p,0x18,unit*0x1.921fb6p+1F);Set(p,0x1c,1.0F);Set(p,0x20,0.005F);Set(p,0x24,1.01F);Set(p,0x28,1.0F);Set(p,0x2c,DefaultEngineColorMod());Set(p,0x78,-1000.0F);Set(p,0x8c,std::int32_t{30});Set(p,0x9c,-1.0F);return 1;}
void* Npc(lua_State*L){luaL_checkudata(L,1,LuaRuntime::kEntityNPCMetatable);const auto p=ResolveEngineReceiver(L,FieldReceipt::Entity,1);if(!p||ClassifyCallbackEntity(p)!=CallbackEntityClass::Npc)luaL_error(L,"EntityNPC reference is no longer available");return engine_memory::AsObject(p);}
}
#if !defined(__SWITCH__)
void SetApi400ParamsNativeTestBindings(Api400ParamsNativeTestBindings value)noexcept{g_Tests=value;}
#endif
std::uint32_t Api400NextRandomU32(lua_State*L){return Native<std::uint32_t(*)()>(L,0)();}
void RegisterApi400ProjectileParams(lua_State*L){luaL_newmetatable(L,kMetatable);if(!RegisterNativeObjectIdentity(L,-1,ParamsIdentity))luaL_error(L,"ProjectileParams native identity resolver conflicts");lua_pushcfunction(L,Index);lua_setfield(L,-2,"__index");lua_pushcfunction(L,NewIndex);lua_setfield(L,-2,"__newindex");lua_pop(L,1);PublishNativeClass(L,"ProjectileParams",kMetatable);lua_getglobal(L,"ProjectileParams");lua_getmetatable(L,-1);lua_pushcfunction(L,Create);lua_setfield(L,-2,"__call");lua_pop(L,2);}
int Api400EntityNPCFireProjectiles(lua_State*L){auto*self=Npc(L);const auto*pos=RequireVectorArgument(L,2);const auto*velocity=RequireVectorArgument(L,3);const auto mode=Int(L,4);const auto*params=Check(L,5);Native<std::uintptr_t(*)(void*,const Vec*,const Vec*,std::int32_t,const Params*)>(L,1)(self,pos,velocity,mode,params);return 0;}
int Api400EntityNPCFireBossProjectiles(lua_State*L){auto*self=Npc(L);const auto count=Int(L,2);const auto*target=RequireVectorArgument(L,3);const float trajectory=static_cast<float>(luaL_checknumber(L,4));const auto*params=Check(L,5);const auto entity=Native<std::uintptr_t(*)(void*,std::int32_t,const Vec*,float,const Params*)>(L,2)(self,count,target,trajectory,params);if(entity)PushEntityCallbackArgument(L,entity);else lua_pushnil(L);return 1;}
}
