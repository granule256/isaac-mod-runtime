#include "interfaces/lua/api500_entities.hpp"
#include "interfaces/lua/api500_entities.guards.hpp"
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
enum class Kind : unsigned char {Int,UInt,Float,Bool,Vector,ConstVector,Entity};
enum class Family : unsigned char {Npc,Familiar,Effect,Tear,Bomb};
struct Field {const char* name;unsigned offset;Kind kind;Family family;bool writable;};
constexpr Field kFields[] = {
    {"StateFrame",0x400,Kind::Int,Family::Npc,true},
    {"State",0xb70,Kind::UInt,Family::Npc,true},
    {"ProjectileCooldown",0xbd0,Kind::Int,Family::Npc,true},
    {"ProjectileDelay",0xbd4,Kind::Int,Family::Npc,true},
    {"V1",0xbe0,Kind::Vector,Family::Npc,true},
    {"V2",0xbe8,Kind::Vector,Family::Npc,true},
    {"I1",0xbf0,Kind::Int,Family::Npc,true},
    {"I2",0xbf4,Kind::Int,Family::Npc,true},
    {"GroupIdx",0xd28,Kind::Int,Family::Npc,true},
    {"Coins",0xd8c,Kind::Int,Family::Familiar,true},
    {"HeadFrameDelay",0xd64,Kind::Int,Family::Familiar,true},
    {"MoveDirection",0xd68,Kind::Int,Family::Familiar,true},
    {"ShootDirection",0xd6c,Kind::Int,Family::Familiar,true},
    {"LastDirection",0xd70,Kind::Int,Family::Familiar,true},
    {"OrbitAngleOffset",0xd74,Kind::Float,Family::Familiar,true},
    {"IsDelayed",0xd89,Kind::Bool,Family::Familiar,true},
    {"MinRadius",0x44c,Kind::Float,Family::Effect,true},
    {"MaxRadius",0x450,Kind::Float,Family::Effect,true},
    {"LifeSpan",0x458,Kind::Int,Family::Effect,true},
    {"IsFollowing",0x45c,Kind::Bool,Family::Effect,true},
    {"ParentOffset",0x460,Kind::Vector,Family::Effect,true},
    {"DamageSource",0x468,Kind::Int,Family::Effect,true},
    {"Scale",0x470,Kind::Float,Family::Effect,true},
    {"BaseDamage",0x454,Kind::Float,Family::Tear,false},
    {"BaseScale",0x414,Kind::Float,Family::Tear,false},
    {"TearIndex",0x450,Kind::UInt,Family::Tear,false},
    {"HomingFriction",0x40c,Kind::Float,Family::Tear,true},
    {"ContinueVelocity",0x42c,Kind::Vector,Family::Tear,true},
    {"StickTarget",0x478,Kind::Entity,Family::Tear,true},
    {"StickDiff",0x480,Kind::Vector,Family::Tear,true},
    {"StickTimer",0x488,Kind::Int,Family::Tear,true},
    {"CanTriggerStreakEnd",0x8e0,Kind::Bool,Family::Tear,true},
    {"PosDisplacement",0x8e4,Kind::ConstVector,Family::Tear,false},
    {"RadiusMultiplier",0x43c,Kind::Float,Family::Bomb,true},
    {"ParentNPC",0x390,Kind::Entity,Family::Npc,false},
    {"ChildNPC",0x398,Kind::Entity,Family::Npc,false},
};
constexpr api100_native::Entry kLayouts[] = {
    {api500_entities::kNpcLayout,api500_entities::kNpcGuard.data()},
    {api500_entities::kFamiliarLayout,api500_entities::kFamiliarGuard.data()},
    {api500_entities::kEffectLayout,api500_entities::kEffectGuard.data()},
    {api500_entities::kTearLayout,api500_entities::kTearGuard.data()},
    {api500_entities::kBombLayout,api500_entities::kBombGuard.data()},
};
api100_native::Cache g_LayoutCaches[5]{};
constexpr std::uint32_t Hash(const char* p) {
    std::uint32_t h=2166136261U;
    while(*p)h=(h^static_cast<unsigned char>(*p++))*16777619U;
    return h;
}
const Field* Find(std::uintptr_t entity,const char* name) {
    if(!name||!name[0]||!name[1])return nullptr;
    // Unrelated names leave before hashing, native reads or family classification.
    const unsigned prefix=(static_cast<unsigned>(static_cast<unsigned char>(name[0]))<<8)|
        static_cast<unsigned char>(name[1]);
    switch(prefix) {
    case 0x4261:
    case 0x4361:
    case 0x4368:
    case 0x436f:
    case 0x4461:
    case 0x4772:
    case 0x4865:
    case 0x486f:
    case 0x4931:
    case 0x4932:
    case 0x4973:
    case 0x4c61:
    case 0x4c69:
    case 0x4d61:
    case 0x4d69:
    case 0x4d6f:
    case 0x4f72:
    case 0x5061:
    case 0x506f:
    case 0x5072:
    case 0x5261:
    case 0x5363:
    case 0x5368:
    case 0x5374:
    case 0x5465:
    case 0x5631:
    case 0x5632:
        break;
    default:return nullptr;
    }
    const Field* field=nullptr;
    switch(Hash(name)) {
    case Hash("StateFrame"):field=&kFields[0];break;
    case Hash("State"):field=&kFields[1];break;
    case Hash("ProjectileCooldown"):field=&kFields[2];break;
    case Hash("ProjectileDelay"):field=&kFields[3];break;
    case Hash("V1"):field=&kFields[4];break;
    case Hash("V2"):field=&kFields[5];break;
    case Hash("I1"):field=&kFields[6];break;
    case Hash("I2"):field=&kFields[7];break;
    case Hash("GroupIdx"):field=&kFields[8];break;
    case Hash("Coins"):field=&kFields[9];break;
    case Hash("HeadFrameDelay"):field=&kFields[10];break;
    case Hash("MoveDirection"):field=&kFields[11];break;
    case Hash("ShootDirection"):field=&kFields[12];break;
    case Hash("LastDirection"):field=&kFields[13];break;
    case Hash("OrbitAngleOffset"):field=&kFields[14];break;
    case Hash("IsDelayed"):field=&kFields[15];break;
    case Hash("MinRadius"):field=&kFields[16];break;
    case Hash("MaxRadius"):field=&kFields[17];break;
    case Hash("LifeSpan"):field=&kFields[18];break;
    case Hash("IsFollowing"):field=&kFields[19];break;
    case Hash("ParentOffset"):field=&kFields[20];break;
    case Hash("DamageSource"):field=&kFields[21];break;
    case Hash("Scale"):field=&kFields[22];break;
    case Hash("BaseDamage"):field=&kFields[23];break;
    case Hash("BaseScale"):field=&kFields[24];break;
    case Hash("TearIndex"):field=&kFields[25];break;
    case Hash("HomingFriction"):field=&kFields[26];break;
    case Hash("ContinueVelocity"):field=&kFields[27];break;
    case Hash("StickTarget"):field=&kFields[28];break;
    case Hash("StickDiff"):field=&kFields[29];break;
    case Hash("StickTimer"):field=&kFields[30];break;
    case Hash("CanTriggerStreakEnd"):field=&kFields[31];break;
    case Hash("PosDisplacement"):field=&kFields[32];break;
    case Hash("RadiusMultiplier"):field=&kFields[33];break;
    case Hash("ParentNPC"):field=&kFields[34];break;
    case Hash("ChildNPC"):field=&kFields[35];break;
    default:return nullptr;
    }
    if(std::strcmp(name,field->name))return nullptr;
    const auto kind=ClassifyCallbackEntity(entity);
    bool matches=false;
    switch(field->family) {
    case Family::Npc:matches=kind==CallbackEntityClass::Npc;break;
    case Family::Familiar:matches=kind==CallbackEntityClass::Familiar;break;
    case Family::Effect:matches=kind==CallbackEntityClass::Effect;break;
    case Family::Tear:matches=kind==CallbackEntityClass::Tear;break;
    case Family::Bomb:matches=kind==CallbackEntityClass::Bomb;break;
    }
    return matches?field:nullptr;
}
void Guard(lua_State* L,const Field& field) {
    const auto group=static_cast<unsigned>(field.family);
    static_cast<void>(api100_native::Resolve(L,kLayouts[group],g_LayoutCaches[group]));
}
template<class T>T Read(lua_State* L,std::uintptr_t object,unsigned offset) {
    T value{};
    if(!engine_memory::ReadField(object,offset,&value,engine_memory::EngineMemoryReadable))
        luaL_error(L,"api500 entity field is not readable");
    return value;
}
template<class T>void Write(lua_State* L,std::uintptr_t object,unsigned offset,const T& value) {
    if(!engine_memory::WriteField(object,offset,value,engine_memory::EngineMemoryWritable))
        luaL_error(L,"api500 entity field is not writable");
}
}
int TryPushApi500EntityField(lua_State* L,std::uintptr_t entity,const char* name) {
    const auto* field=Find(entity,name);
    if(!field)return 0;
    Guard(L,*field);
    switch(field->kind) {
    case Kind::UInt:lua_pushinteger(L,Read<std::uint32_t>(L,entity,field->offset));break;
    case Kind::Int:lua_pushinteger(L,Read<std::int32_t>(L,entity,field->offset));break;
    case Kind::Float:lua_pushnumber(L,Read<float>(L,entity,field->offset));break;
    case Kind::Bool:lua_pushboolean(L,Read<std::uint8_t>(L,entity,field->offset)!=0);break;
    case Kind::Vector:{const auto v=Read<LuaRuntime::VectorHandle>(L,entity,field->offset);PushLuaVector(L,v.x,v.y);break;}
    case Kind::ConstVector:PushEntityVectorReference(L,entity,field->offset);break;
    case Kind::Entity:{const auto p=Read<std::uintptr_t>(L,entity,field->offset);if(p)PushEntityCallbackArgument(L,p);else lua_pushnil(L);break;}
    }
    return 1;
}
bool TryWriteApi500EntityField(lua_State* L,std::uintptr_t entity,const char* name) {
    const auto* field=Find(entity,name);
    if(!field)return false;
    Guard(L,*field);
    if(!field->writable)luaL_error(L,"%s is read-only",name);
    switch(field->kind) {
    case Kind::UInt:
    case Kind::Int:{const auto low=static_cast<std::uint32_t>(luaL_checkinteger(L,3));Write(L,entity,field->offset,low);break;}
    case Kind::Float:Write(L,entity,field->offset,static_cast<float>(luaL_checknumber(L,3)));break;
    case Kind::Bool:Write(L,entity,field->offset,static_cast<std::uint8_t>(lua_toboolean(L,3)!=0));break;
    case Kind::Vector:Write(L,entity,field->offset,*RequireVectorArgument(L,3));break;
    case Kind::Entity:{std::uintptr_t p{};if(!lua_isnil(L,3)){p=EntityPointerArgument(L,3);if(!p)luaL_argerror(L,3,"live Entity or nil expected");}Write(L,entity,field->offset,p);break;}
    case Kind::ConstVector:break; // read-only branch above always raises
    }
    return true;
}
}
