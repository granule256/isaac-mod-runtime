#include "interfaces/lua/api600_world.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api500_config.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/rng_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
#include <array>
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
enum class Kind:unsigned char{Int,UInt,I16,U16,Vector,String,Rng};
struct Field{const char*owner;const char*name;unsigned offset;Kind kind;unsigned layout;};
constexpr Field kFields[]={
{"RoomDescriptor","DeliriumDistance",0xf4,Kind::Int,12},
{"Game","BossRushParTime",0x24f9a4,Kind::Int,0},
{"Game","BlueWombParTime",0x24f9a8,Kind::Int,1},
{"Level","LeaveDoor",0x2156c,Kind::Int,2},
{"Level","DungeonReturnPosition",0x21574,Kind::Vector,3},
{"Level","GreedModeWave",0x21588,Kind::UInt,4},
{"RoomDescriptor","ClearCount",0x56,Kind::U16,5},
{"RoomDescriptor","PoopCount",0x5c,Kind::I16,6},
{"RoomDescriptor","PitsCount",0x60,Kind::Int,6},
{"RoomDescriptor","ShopItemIdx",0xf0,Kind::I16,7},
{"GridEntityDoor","OpenAnimation",0x320,Kind::String,8},
{"GridEntityDoor","CloseAnimation",0x338,Kind::String,8},
{"GridEntityDoor","LockedAnimation",0x350,Kind::String,8},
{"GridEntityDoor","OpenLockedAnimation",0x368,Kind::String,8},
{"GridEntityPoop","StateAnimation",0x1a8,Kind::String,9},
{"GridEntityPressurePlate","GreedModeRNG",0x300,Kind::Rng,10},
{"GridEntityRock","Anim",0x1a0,Kind::String,11},
{"GridEntityRock","RubbleAnim",0x1b8,Kind::String,11},
{"GridEntityRock","FrameCnt",0x1e8,Kind::Int,11},
};
struct Layout{std::uintptr_t offset;std::array<std::uint8_t,16> bytes;};
constexpr Layout kLayouts[]={
{0x466b30,{0x89,0x34,0x9f,0x52,0x89,0x4,0xa0,0x72,0x2,0x69,0x69,0xb8,0x41,0x22,0x0,0xb0}},
{0x472104,{0x89,0x33,0x9f,0x52,0x89,0x4,0xa0,0x72,0x9,0x0,0x9,0x8b,0x2a,0x1,0x40,0xb9}},
{0x3d9b80,{0x28,0xa3,0xd9,0x39,0x29,0x23,0xb,0x29,0x28,0x5b,0x46,0xb9,0x28,0x67,0x0,0xb9}},
{0x3e09c0,{0x88,0xae,0x82,0x52,0x48,0x0,0xa0,0x72,0x60,0x2,0x8,0x8b,0xe1,0xa3,0x0,0x91}},
{0x3e0654,{0x8,0xb1,0x82,0x52,0x48,0x0,0xa0,0x72,0x8,0x68,0x68,0xb8,0x8,0x5,0x0,0x51}},
{0x470b84,{0x9,0xad,0x40,0x79,0xb5,0x4e,0x43,0xf9,0x29,0x5,0x0,0x11,0x9,0xad,0x0,0x79}},
{0x37030c,{0xe1,0x82,0x1,0x91,0x82,0x0,0x80,0x52,0x23,0x0,0x80,0x52,0x8,0x0,0x40,0xf9}},
{0x370be0,{0xe1,0xc2,0x3,0x91,0x42,0x0,0x80,0x52,0x23,0x0,0x80,0x52,0x8,0x0,0x40,0xf9}},
{0x386154,{0x8,0xa0,0x4d,0x39,0xf3,0x3,0x0,0xaa,0xe8,0x1,0x0,0x37,0x68,0x42,0x4d,0x39}},
{0x3897bc,{0x8,0xa0,0x46,0x39,0xf3,0x3,0x0,0xaa,0x68,0x0,0x0,0x36,0x60,0xde,0x40,0xf9}},
{0x38f244,{0x61,0x1a,0x40,0xb9,0x60,0x2,0xc,0x91,0xe2,0x3,0x80,0x52,0xc8,0x85,0xb,0x94}},
{0x392e68,{0x1a,0x80,0x6,0x91,0xf3,0x3,0x0,0xaa,0x41,0x28,0x0,0xf0,0x21,0x1c,0xa,0x91}},
{0x3e1200,{0xe2,0x3,0x14,0x2a,0xbf,0x6a,0xa,0x94,0x8,0xf4,0x40,0xb9,0x1f,0x1,0x0,0x71}},
};
api100_native::Cache g_Layouts[13]{};
constexpr std::uint32_t Hash(const char*p){std::uint32_t h=2166136261U;while(*p)h=(h^static_cast<unsigned char>(*p++))*16777619U;return h;}
const Field* Find(const char*owner,const char*name){
 if(!owner||!name||!name[0]||!name[1])return nullptr;
 const unsigned prefix=(static_cast<unsigned char>(name[0])<<8)|static_cast<unsigned char>(name[1]);
 switch(prefix){
case 0x416e:
case 0x426c:
case 0x426f:
case 0x436c:
case 0x4465:
case 0x4475:
case 0x4672:
case 0x4772:
case 0x4c65:
case 0x4c6f:
case 0x4f70:
case 0x5069:
case 0x506f:
case 0x5275:
case 0x5368:
case 0x5374:
break;default:return nullptr;}
const Field*f=nullptr;switch(Hash(name)){
case Hash("DeliriumDistance"):f=&kFields[0];break;
case Hash("BossRushParTime"):f=&kFields[1];break;
case Hash("BlueWombParTime"):f=&kFields[2];break;
case Hash("LeaveDoor"):f=&kFields[3];break;
case Hash("DungeonReturnPosition"):f=&kFields[4];break;
case Hash("GreedModeWave"):f=&kFields[5];break;
case Hash("ClearCount"):f=&kFields[6];break;
case Hash("PoopCount"):f=&kFields[7];break;
case Hash("PitsCount"):f=&kFields[8];break;
case Hash("ShopItemIdx"):f=&kFields[9];break;
case Hash("OpenAnimation"):f=&kFields[10];break;
case Hash("CloseAnimation"):f=&kFields[11];break;
case Hash("LockedAnimation"):f=&kFields[12];break;
case Hash("OpenLockedAnimation"):f=&kFields[13];break;
case Hash("StateAnimation"):f=&kFields[14];break;
case Hash("GreedModeRNG"):f=&kFields[15];break;
case Hash("Anim"):f=&kFields[16];break;
case Hash("RubbleAnim"):f=&kFields[17];break;
case Hash("FrameCnt"):f=&kFields[18];break;
default:return nullptr;}return std::strcmp(owner,f->owner)||std::strcmp(name,f->name)?nullptr:f;
}
void Check(lua_State*L,const Field&f){const auto&g=kLayouts[f.layout];static_cast<void>(api100_native::Resolve(L,{g.offset,g.bytes.data()},g_Layouts[f.layout]));}
template<class T>T Read(lua_State*L,std::uintptr_t p,unsigned o){T v{};if(!engine_memory::ReadField(p,o,&v,engine_memory::EngineMemoryReadable))luaL_error(L,"api600 world field is not readable");return v;}
template<class T>void Write(lua_State*L,std::uintptr_t p,unsigned o,const T&v){if(!engine_memory::WriteField(p,o,v,engine_memory::EngineMemoryWritable))luaL_error(L,"api600 world field is not writable");}
}
bool IsApi600WorldField(const char*o,const char*n)noexcept{return Find(o,n)!=nullptr;}
int TryPushApi600WorldField(lua_State*L,std::uintptr_t p,const char*owner,const char*name){const auto*f=Find(owner,name);if(!f)return 0;Check(L,*f);
 switch(f->kind){
 case Kind::Int:lua_pushinteger(L,Read<std::int32_t>(L,p,f->offset));break;
 case Kind::UInt:lua_pushinteger(L,Read<std::uint32_t>(L,p,f->offset));break;
 case Kind::I16:lua_pushinteger(L,Read<std::int16_t>(L,p,f->offset));break;
 case Kind::U16:lua_pushinteger(L,Read<std::uint16_t>(L,p,f->offset));break;
 case Kind::Vector:{const auto v=Read<LuaRuntime::VectorHandle>(L,p,f->offset);PushLuaVector(L,v.x,v.y);break;}
 case Kind::String:return Api500PushConfigString(L,p+f->offset);
 case Kind::Rng:{auto*h=static_cast<LuaRuntime::RngHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::RngHandle)));*h={};h->storage=Read<std::array<std::uint8_t,kRngObjectSize>>(L,p,f->offset);luaL_getmetatable(L,LuaRuntime::kRngMetatable);lua_setmetatable(L,-2);break;}
 }return 1;}
bool TryWriteApi600WorldField(lua_State*L,std::uintptr_t p,const char*owner,const char*name){const auto*f=Find(owner,name);if(!f)return false;Check(L,*f);
 switch(f->kind){
 case Kind::Int:case Kind::UInt:Write(L,p,f->offset,static_cast<std::uint32_t>(luaL_checkinteger(L,3)));break;
 case Kind::I16:case Kind::U16:Write(L,p,f->offset,static_cast<std::uint16_t>(luaL_checkinteger(L,3)));break;
 case Kind::Vector:Write(L,p,f->offset,*RequireVectorArgument(L,3));break;
 case Kind::String:Api500AssignConfigString(L,p+f->offset);break;
 case Kind::Rng:{auto*r=static_cast<LuaRuntime::RngHandle*>(luaL_checkudata(L,3,LuaRuntime::kRngMetatable));std::array<std::uint8_t,kRngObjectSize> value{};std::memcpy(value.data(),ResolveRngObject(L,r,false),value.size());Write(L,p,f->offset,value);break;}
 }return true;}
namespace {
const char* GridOwner(lua_State*L,std::uintptr_t p,const char*name){
 if(!name||!name[0])return nullptr;
 switch(name[0]){case 'O':case 'C':case 'L':case 'S':case 'G':case 'A':case 'R':case 'F':break;default:return nullptr;}
 bool candidate=false;for(const auto&f:kFields)if(f.owner[0]=='G'&&f.owner[1]=='r'&&!std::strcmp(name,f.name)){candidate=true;break;}
 if(!candidate)return nullptr;
 if(!IsLiveGridEntityPointer(p))luaL_error(L,"GridEntity reference is no longer available");
 const auto vt=Read<std::uintptr_t>(L,p,0),base=LuaRuntime::EngineModuleBase();
 if(vt==base+kGridEntity_DoorVtableOffset)return "GridEntityDoor";
 if(vt==base+kGridEntity_PoopVtableOffset)return "GridEntityPoop";
 if(vt==base+kGridEntity_PressurePlateVtableOffset)return "GridEntityPressurePlate";
 if(vt==base+kGridEntity_RockVtableOffset)return "GridEntityRock";
 return nullptr;
}
}
int TryPushApi600GridField(lua_State*L,std::uintptr_t p,const char*name){const auto*owner=GridOwner(L,p,name);return owner?TryPushApi600WorldField(L,p,owner,name):0;}
bool TryWriteApi600GridField(lua_State*L,std::uintptr_t p,const char*name){const auto*owner=GridOwner(L,p,name);return owner&&TryWriteApi600WorldField(L,p,owner,name);}
}
