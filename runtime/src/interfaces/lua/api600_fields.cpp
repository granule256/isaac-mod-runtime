#include "interfaces/lua/api600_fields.hpp"
#include "interfaces/lua/api600_fields.guards.hpp"
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
enum class Kind:unsigned char{Float,Int,Bool,Vector,ConstVector};
struct Field{const char*name;unsigned offset;Kind kind;bool writable;unsigned layout;};
constexpr Field kFields[]={
{"Mass",0x350,Kind::Float,true,2},
{"RenderZOffset",0x328,Kind::Int,true,3},
{"SortingLayer",0x330,Kind::Int,true,3},
{"SpawnGridIndex",0x340,Kind::Int,false,0},
{"SpriteRotation",0x134,Kind::Float,true,4},
{"FlipX",0x1c1,Kind::Bool,true,4},
{"SizeMulti",0x348,Kind::Vector,true,1},
{"TargetPosition",0x320,Kind::ConstVector,true,0},
};
api100_native::Cache g_Layouts[5]{};
constexpr std::uint32_t Hash(const char*p){std::uint32_t h=2166136261U;while(*p)h=(h^static_cast<unsigned char>(*p++))*16777619U;return h;}
const Field* Find(const char*name){
 if(!name||!name[0]||!name[1])return nullptr;
 const unsigned prefix=(static_cast<unsigned char>(name[0])<<8)|static_cast<unsigned char>(name[1]);
 switch(prefix){
case 0x466c:
case 0x4d61:
case 0x5265:
case 0x5369:
case 0x536f:
case 0x5370:
case 0x5461:
break;default:return nullptr;}
const Field*field=nullptr;switch(Hash(name)){
case Hash("Mass"):field=&kFields[0];break;
case Hash("RenderZOffset"):field=&kFields[1];break;
case Hash("SortingLayer"):field=&kFields[2];break;
case Hash("SpawnGridIndex"):field=&kFields[3];break;
case Hash("SpriteRotation"):field=&kFields[4];break;
case Hash("FlipX"):field=&kFields[5];break;
case Hash("SizeMulti"):field=&kFields[6];break;
case Hash("TargetPosition"):field=&kFields[7];break;
default:return nullptr;}return std::strcmp(name,field->name)?nullptr:field;}
void Check(lua_State*L,const Field&f){const auto&g=api600_fields::kLayouts[f.layout];static_cast<void>(api100_native::Resolve(L,{g.offset,g.bytes.data()},g_Layouts[f.layout]));}
template<class T>T Read(lua_State*L,std::uintptr_t p,unsigned o){T v{};if(!engine_memory::ReadField(p,o,&v,engine_memory::EngineMemoryReadable))luaL_error(L,"api600 Entity field is not readable");return v;}
template<class T>void Write(lua_State*L,std::uintptr_t p,unsigned o,const T&v){if(!engine_memory::WriteField(p,o,v,engine_memory::EngineMemoryWritable))luaL_error(L,"api600 Entity field is not writable");}
}
int TryPushApi600EntityField(lua_State*L,std::uintptr_t p,const char*n){const auto*f=Find(n);if(!f)return 0;Check(L,*f);
 switch(f->kind){
 case Kind::Float:lua_pushnumber(L,Read<float>(L,p,f->offset));break;
 case Kind::Int:lua_pushinteger(L,Read<std::int32_t>(L,p,f->offset));break;
 case Kind::Bool:lua_pushboolean(L,Read<std::uint8_t>(L,p,f->offset)!=0);break;
 case Kind::Vector:{const auto v=Read<LuaRuntime::VectorHandle>(L,p,f->offset);PushLuaVector(L,v.x,v.y);break;}
 case Kind::ConstVector:PushEntityVectorReference(L,p,f->offset);break;
 }return 1;}
bool TryWriteApi600EntityField(lua_State*L,std::uintptr_t p,const char*n){const auto*f=Find(n);if(!f)return false;Check(L,*f);if(!f->writable)luaL_error(L,"%s is read-only",n);
 switch(f->kind){
 case Kind::Float:Write(L,p,f->offset,static_cast<float>(luaL_checknumber(L,3)));break;
 case Kind::Int:Write(L,p,f->offset,static_cast<std::uint32_t>(luaL_checkinteger(L,3)));break;
 case Kind::Bool:Write(L,p,f->offset,static_cast<std::uint8_t>(lua_toboolean(L,3)!=0));break;
 case Kind::Vector:case Kind::ConstVector:Write(L,p,f->offset,*RequireVectorArgument(L,3));break;
 }return true;}
}
