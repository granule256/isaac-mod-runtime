#include "interfaces/lua/api400_fields.hpp"
#include "interfaces/lua/homing_laser_value.hpp"
#include "interfaces/lua/api400_fields.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
enum class Kind:unsigned char{Float,Int,UInt,U64,Bool,Vector,Entity,Homing};
enum class Group:unsigned char{Laser,Projectile,Knife,Tear};
struct Field {const char*name;unsigned offset;Kind kind;Group group;};
constexpr Field kFields[]={
{"ParentOffset",0x400,Kind::Vector,Group::Laser},
{"StartAngleDegrees",0x408,Kind::Float,Group::Laser},
{"AngleDegrees",0x40c,Kind::Float,Group::Laser},
{"LastAngleDegrees",0x410,Kind::Float,Group::Laser},
{"Timeout",0x448,Kind::Int,Group::Laser},
{"FirstUpdate",0x44c,Kind::Bool,Group::Laser},
{"Shrink",0x44e,Kind::Bool,Group::Laser},
{"LaserLength",0x450,Kind::Float,Group::Laser},
{"Radius",0x4e4,Kind::Float,Group::Laser},
{"IsActiveRotating",0x4e8,Kind::Bool,Group::Laser},
{"RotationDelay",0x4ec,Kind::UInt,Group::Laser},
{"RotationDegrees",0x4f0,Kind::Float,Group::Laser},
{"RotationSpd",0x4f4,Kind::Float,Group::Laser},
{"MaxDistance",0x4f8,Kind::Float,Group::Laser},
{"EndPoint",0x500,Kind::Vector,Group::Laser},
{"DisableFollowParent",0x50c,Kind::Bool,Group::Laser},
{"BlackHpDropChance",0x524,Kind::Float,Group::Laser},
{"OneHit",0x561,Kind::Bool,Group::Laser},
{"GridHit",0x562,Kind::Bool,Group::Laser},
{"Acceleration",0x41c,Kind::Float,Group::Projectile},
{"ChangeFlags",0x438,Kind::U64,Group::Projectile},
{"ChangeTimeout",0x444,Kind::Int,Group::Projectile},
{"ChangeVelocity",0x440,Kind::Float,Group::Projectile},
{"CurvingStrength",0x418,Kind::Float,Group::Projectile},
{"BounceLaser",0x510,Kind::Entity,Group::Laser},
{"Damage",0x40c,Kind::Float,Group::Projectile},
{"FallingAccel",0x408,Kind::Float,Group::Projectile},
{"HomingStrength",0x414,Kind::Float,Group::Projectile},
{"Scale",0x410,Kind::Float,Group::Projectile},
{"WiggleFrameOffset",0x434,Kind::Int,Group::Projectile},
// 固定PC直接成员/访问器与NS具名Update消费者独立互证，见半数API接续证据。
{"HomingType",0x4fc,Kind::Int,Group::Laser},
{"HomingLaser",0x458,Kind::Homing,Group::Laser},
{"CurveStrength",0x4e0,Kind::Float,Group::Laser},
{"Scale",0x420,Kind::Float,Group::Knife},
{"Rotation",0x430,Kind::Float,Group::Knife},
{"RotationOffset",0x42c,Kind::Float,Group::Knife},
{"MaxDistance",0x44c,Kind::Float,Group::Knife},
{"Charge",0x450,Kind::Float,Group::Knife},
{"PathOffset",0x4e8,Kind::Float,Group::Knife},
{"PathFollowSpeed",0x4ec,Kind::Float,Group::Knife},
{"WaitFrames",0x428,Kind::Int,Group::Tear},
{"ParentOffset",0x8ec,Kind::Vector,Group::Tear},
};
constexpr api100_native::Entry kEntries[]={
{api400_fields::kLaserEntry,api400_fields::kLaserGuard.data()},
{api400_fields::kProjectileEntry,api400_fields::kProjectileGuard.data()},
{api400_fields::kKnifeEntry,api400_fields::kKnifeGuard.data()},
{api400_fields::kTearEntry,api400_fields::kTearGuard.data()}};
api100_native::Cache g_Caches[4]{};
// Hash names first: an unrelated method/field never classifies or touches native
// memory, and each matching candidate checks the full name after the hash switch.
constexpr std::uint32_t Hash(const char*s){std::uint32_t h=2166136261U;if(s)while(*s){h=(h^static_cast<unsigned char>(*s++))*16777619U;}return h;}
bool Candidate(const char*name){
 if(!name||!name[0]||!name[1]){return false;}
 const auto prefix=(static_cast<unsigned>(static_cast<unsigned char>(name[0]))<<8)|static_cast<unsigned char>(name[1]);
 switch(prefix){
 case 0x4163:
 case 0x416e:
 case 0x426c:
 case 0x426f:
 case 0x4368:
 case 0x4375:
 case 0x4461:
 case 0x4469:
 case 0x456e:
 case 0x4661:
 case 0x4669:
 case 0x4772:
 case 0x486f:
 case 0x4973:
 case 0x4c61:
 case 0x4d61:
 case 0x4f6e:
 case 0x5061:
 case 0x5261:
 case 0x526f:
 case 0x5363:
 case 0x5368:
 case 0x5374:
 case 0x5469:
 case 0x5761:
 case 0x5769:
  break;
 default:return false;
 }
 switch(Hash(name)){
case Hash("Acceleration"):return name&&!std::strcmp(name,"Acceleration");
case Hash("AngleDegrees"):return name&&!std::strcmp(name,"AngleDegrees");
case Hash("BlackHpDropChance"):return name&&!std::strcmp(name,"BlackHpDropChance");
case Hash("ChangeFlags"):return name&&!std::strcmp(name,"ChangeFlags");
case Hash("ChangeTimeout"):return name&&!std::strcmp(name,"ChangeTimeout");
case Hash("ChangeVelocity"):return name&&!std::strcmp(name,"ChangeVelocity");
case Hash("Charge"):return name&&!std::strcmp(name,"Charge");
case Hash("CurveStrength"):return name&&!std::strcmp(name,"CurveStrength");
case Hash("Damage"):return name&&!std::strcmp(name,"Damage");
case Hash("CurvingStrength"):return name&&!std::strcmp(name,"CurvingStrength");
case Hash("BounceLaser"):return name&&!std::strcmp(name,"BounceLaser");
case Hash("DisableFollowParent"):return name&&!std::strcmp(name,"DisableFollowParent");
case Hash("EndPoint"):return name&&!std::strcmp(name,"EndPoint");
case Hash("FallingAccel"):return name&&!std::strcmp(name,"FallingAccel");
case Hash("FirstUpdate"):return name&&!std::strcmp(name,"FirstUpdate");
case Hash("GridHit"):return name&&!std::strcmp(name,"GridHit");
case Hash("HomingStrength"):return name&&!std::strcmp(name,"HomingStrength");
case Hash("HomingLaser"):return name&&!std::strcmp(name,"HomingLaser");
case Hash("HomingType"):return name&&!std::strcmp(name,"HomingType");
case Hash("IsActiveRotating"):return name&&!std::strcmp(name,"IsActiveRotating");
case Hash("LaserLength"):return name&&!std::strcmp(name,"LaserLength");
case Hash("LastAngleDegrees"):return name&&!std::strcmp(name,"LastAngleDegrees");
case Hash("MaxDistance"):return name&&!std::strcmp(name,"MaxDistance");
case Hash("OneHit"):return name&&!std::strcmp(name,"OneHit");
case Hash("ParentOffset"):return name&&!std::strcmp(name,"ParentOffset");
case Hash("PathFollowSpeed"):return name&&!std::strcmp(name,"PathFollowSpeed");
case Hash("PathOffset"):return name&&!std::strcmp(name,"PathOffset");
case Hash("Radius"):return name&&!std::strcmp(name,"Radius");
case Hash("Rotation"):return name&&!std::strcmp(name,"Rotation");
case Hash("RotationDegrees"):return name&&!std::strcmp(name,"RotationDegrees");
case Hash("RotationDelay"):return name&&!std::strcmp(name,"RotationDelay");
case Hash("RotationOffset"):return name&&!std::strcmp(name,"RotationOffset");
case Hash("RotationSpd"):return name&&!std::strcmp(name,"RotationSpd");
case Hash("Scale"):return name&&!std::strcmp(name,"Scale");
case Hash("Shrink"):return name&&!std::strcmp(name,"Shrink");
case Hash("StartAngleDegrees"):return name&&!std::strcmp(name,"StartAngleDegrees");
case Hash("Timeout"):return name&&!std::strcmp(name,"Timeout");
case Hash("WaitFrames"):return name&&!std::strcmp(name,"WaitFrames");
case Hash("WiggleFrameOffset"):return name&&!std::strcmp(name,"WiggleFrameOffset");
default:return false;}}
const Field* Find(std::uintptr_t entity,const char*name){
 if(!Candidate(name))return nullptr;
 const auto type=ClassifyCallbackEntity(entity);Group group;
 switch(type){case CallbackEntityClass::Laser:group=Group::Laser;break;case CallbackEntityClass::Projectile:group=Group::Projectile;break;case CallbackEntityClass::Knife:group=Group::Knife;break;case CallbackEntityClass::Tear:group=Group::Tear;break;default:return nullptr;}
 for(const auto&field:kFields)if(field.group==group&&!std::strcmp(name,field.name))return &field;
 return nullptr;
}
void Guard(lua_State*L,const Field&f){
 const auto id=static_cast<unsigned>(f.group);static_cast<void>(api100_native::Resolve(L,kEntries[id],g_Caches[id]));
 if(f.group==Group::Projectile&&f.offset==0x40c){
  static constexpr std::uint8_t first[]={1,16,60,30,8,240,167,82,104,18,4,185,168,153,153,82},second[]={104,82,16,145,0,8,33,30,127,10,4,185,96,34,17,145};
  static api100_native::Cache firstCache{},secondCache{};
  static_cast<void>(api100_native::Resolve(L,{0x31f198,first},firstCache));
  static_cast<void>(api100_native::Resolve(L,{0x31f1c4,second},secondCache));
 }
 if(f.group==Group::Laser&&f.offset==0x4e0){
  // PC8C79AA与NS F7700同一子对象边界清零；同时核Radius邻接初始化。
  static constexpr std::uint8_t layout[]={104,230,4,185,104,186,66,249,127,82,4,185,127,226,4,185};
  static api100_native::Cache cache{};
  static_cast<void>(api100_native::Resolve(L,{0xf76f4,layout},cache));
 }
}
template<class T>__attribute__((noinline)) T Read(lua_State*L,std::uintptr_t p,unsigned offset){T v{};if(!engine_memory::ReadField(p,offset,&v,engine_memory::EngineMemoryReadable))luaL_error(L,"api400 field is not readable");return v;}
template<class T>__attribute__((noinline)) void Write(lua_State*L,std::uintptr_t p,unsigned offset,const T&v){if(!engine_memory::WriteField(p,offset,v,engine_memory::EngineMemoryWritable))luaL_error(L,"api400 field is not writable");}
}
int TryPushApi400EntityField(lua_State*L,std::uintptr_t p,const char*name){const auto*f=Find(p,name);if(!f)return 0;Guard(L,*f);
switch(f->kind){
case Kind::Homing:return PushHomingLaserValue(L,p);
case Kind::Float:lua_pushnumber(L,Read<float>(L,p,f->offset));break;
case Kind::Int:lua_pushinteger(L,Read<std::int32_t>(L,p,f->offset));break;
case Kind::UInt:lua_pushinteger(L,Read<std::uint32_t>(L,p,f->offset));break;
case Kind::Bool:lua_pushboolean(L,Read<std::uint8_t>(L,p,f->offset)!=0);break;
case Kind::U64:{const auto u=Read<std::uint64_t>(L,p,f->offset);lua_Integer v;static_assert(sizeof(v)==8);std::memcpy(&v,&u,8);lua_pushinteger(L,v);break;}
case Kind::Vector:{const auto v=Read<LuaRuntime::VectorHandle>(L,p,f->offset);PushLuaVector(L,v.x,v.y);break;}
case Kind::Entity:{const auto entity=Read<std::uintptr_t>(L,p,f->offset);if(entity){PushEntityCallbackArgument(L,entity);}else{lua_pushnil(L);}break;}
}return 1;}
bool TryWriteApi400EntityField(lua_State*L,std::uintptr_t p,const char*name){const auto*f=Find(p,name);if(!f)return false;Guard(L,*f);
switch(f->kind){
case Kind::Homing:WriteHomingLaserValue(L,p,3);break;
case Kind::Float:Write(L,p,f->offset,static_cast<float>(luaL_checknumber(L,3)));break;
case Kind::Int:case Kind::UInt:{const auto v=static_cast<std::uint32_t>(luaL_checkinteger(L,3));Write(L,p,f->offset,v);break;}
case Kind::U64:Write(L,p,f->offset,static_cast<std::uint64_t>(luaL_checkinteger(L,3)));break;
case Kind::Bool:Write(L,p,f->offset,static_cast<std::uint8_t>(lua_toboolean(L,3)!=0));break;
case Kind::Vector:Write(L,p,f->offset,*RequireVectorArgument(L,3));break;
case Kind::Entity:{std::uintptr_t value{};if(!lua_isnil(L,3)){value=EntityPointerArgument(L,3);if(!value)luaL_argerror(L,3,"live Entity or nil expected");}Write(L,p,f->offset,value);break;}
}return true;}
}
