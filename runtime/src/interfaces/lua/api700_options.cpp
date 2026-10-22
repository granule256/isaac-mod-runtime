#include "interfaces/lua/api700_options.hpp"
#include "interfaces/lua/api700_options.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
enum class Kind:unsigned char{Float,Bool,Int};
struct Field{const char*name;unsigned offset;Kind kind;float minimum,maximum;unsigned native;};
constexpr Field kFields[]={
{"MusicVolume",0x18,Kind::Float,0.0F,0.01F,1},
{"SFXVolume",0x1c,Kind::Float,0.0F,0.01F,2},
{"MapOpacity",0x20,Kind::Float,0.0F,0.01F,0},
{"Filter",0x25,Kind::Bool,0.0F,0.0F,0},
{"Gamma",0x28,Kind::Float,0.5F,1.5F,0},
{"DisplayPopups",0x39,Kind::Bool,0.0F,0.0F,0},
{"CameraStyle",0x3c,Kind::Int,1.0F,2.0F,0},
{"ExtraHUDStyle",0x40,Kind::Int,0.0F,2.0F,0},
{"RumbleEnabled",0x4a,Kind::Bool,0.0F,0.0F,0},
{"ChargeBars",0x4b,Kind::Bool,0.0F,0.0F,0},
{"BulletVisibility",0x4c,Kind::Bool,0.0F,0.0F,0},
};
api100_native::Cache g_Caches[3]{};
#if !defined(__SWITCH__)
std::uintptr_t g_TestMethods[2]{};
#endif
constexpr std::uint32_t Hash(const char*p){std::uint32_t h=2166136261U;while(*p)h=(h^static_cast<unsigned char>(*p++))*16777619U;return h;}
const Field* Find(const char*n){
 if(!n||!n[0]||!n[1])return nullptr;
 const auto prefix=(static_cast<unsigned char>(n[0])<<8)|static_cast<unsigned char>(n[1]);
 switch(prefix){
case 0x4275:
case 0x4361:
case 0x4368:
case 0x4469:
case 0x4578:
case 0x4669:
case 0x4761:
case 0x4d61:
case 0x4d75:
case 0x5275:
case 0x5346:
break;default:return nullptr;}
 const Field*f=nullptr;switch(Hash(n)){
case Hash("MusicVolume"):f=&kFields[0];break;
case Hash("SFXVolume"):f=&kFields[1];break;
case Hash("MapOpacity"):f=&kFields[2];break;
case Hash("Filter"):f=&kFields[3];break;
case Hash("Gamma"):f=&kFields[4];break;
case Hash("DisplayPopups"):f=&kFields[5];break;
case Hash("CameraStyle"):f=&kFields[6];break;
case Hash("ExtraHUDStyle"):f=&kFields[7];break;
case Hash("RumbleEnabled"):f=&kFields[8];break;
case Hash("ChargeBars"):f=&kFields[9];break;
case Hash("BulletVisibility"):f=&kFields[10];break;
default:return nullptr;}return std::strcmp(n,f->name)?nullptr:f;
}
template<class T>T Read(lua_State*L,std::uintptr_t p,unsigned o){T v{};if(!engine_memory::ReadField(p,o,&v,engine_memory::EngineMemoryReadable))luaL_error(L,"Options native data is not readable");return v;}
template<class T>void Store(lua_State*L,std::uintptr_t p,unsigned o,const T&v){if(!engine_memory::WriteField(p,o,v,engine_memory::EngineMemoryWritable))luaL_error(L,"Options native data is not writable");}
std::uintptr_t Guard(lua_State*L,unsigned i,std::uintptr_t host=0){const auto&g=api700_options::kGuards[i];return api100_native::Resolve(L,{g.offset,g.bytes.data()},g_Caches[i],host);}
std::uintptr_t Options(lua_State*L){Guard(L,0);const auto base=LuaRuntime::EngineModuleBase();const auto slot=Read<std::uintptr_t>(L,base,kGameManagerGlobalSlotOffset);if(!slot)luaL_error(L,"Options manager is unavailable");const auto manager=Read<std::uintptr_t>(L,slot,0);if(!manager||manager>UINTPTR_MAX-0x364d0)luaL_error(L,"Options manager is unavailable");return manager+0x364d0;}
float Clamp(float value,float lo,float hi){if(value<lo)value=lo;if(value>hi)value=hi;return value;}
}
#if !defined(__SWITCH__)
void SetApi700OptionNativeTestBindings(std::uintptr_t music,std::uintptr_t sound)noexcept{g_TestMethods[0]=music;g_TestMethods[1]=sound;}
#endif
int TryPushApi700Option(lua_State*L,const char*n){const auto*f=Find(n);if(!f)return 0;const auto p=Options(L);switch(f->kind){
case Kind::Float:lua_pushnumber(L,Read<float>(L,p,f->offset));break;
case Kind::Bool:lua_pushboolean(L,Read<std::uint8_t>(L,p,f->offset)!=0);break;
case Kind::Int:lua_pushinteger(L,Read<std::int32_t>(L,p,f->offset));break;
}return 1;}
bool TryWriteApi700Option(lua_State*L,const char*n){const auto*f=Find(n);if(!f)return false;const auto p=Options(L);
if(f->kind==Kind::Float){const auto value=Clamp(static_cast<float>(luaL_checknumber(L,3)),f->minimum,f->maximum);
 if(f->native){std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_TestMethods[f->native-1];if(!host)luaL_error(L,"Options native setter host binding unavailable");
#endif
 const auto target=Guard(L,f->native,host);engine_call::AsFunction<void(*)(void*,float)>(target)(engine_memory::AsObject(p),value);
 }else Store(L,p,f->offset,value);
}else if(f->kind==Kind::Bool)Store(L,p,f->offset,static_cast<std::uint8_t>(lua_toboolean(L,3)!=0));
else{const auto low=static_cast<std::uint32_t>(luaL_checkinteger(L,3));std::int32_t value{};std::memcpy(&value,&low,4);if(value<f->minimum)value=static_cast<std::int32_t>(f->minimum);if(value>f->maximum)value=static_cast<std::int32_t>(f->maximum);Store(L,p,f->offset,value);}return true;
}
}
