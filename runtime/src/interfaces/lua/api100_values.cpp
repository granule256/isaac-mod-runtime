#include "interfaces/lua/api100_values.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api100_values.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
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
namespace guards=api100_values;
using Entry=api100_native::Entry;
constexpr Entry kEntries[]={
 {guards::kColorSetOffsetEntry,guards::kColorSetOffsetGuard.data()},
 {guards::kColorSetTintEntry,guards::kColorSetTintGuard.data()},
 {guards::kColorResetEntry,guards::kColorResetGuard.data()},
 {guards::kSpriteReloadEntry,guards::kSpriteReloadGuard.data()},
 {guards::kSpriteRemoveOverlayEntry,guards::kSpriteRemoveOverlayGuard.data()},
 {guards::kMusicManagerFadeinEntry,guards::kMusicManagerFadeinGuard.data()},
 {guards::kMusicManagerFadeoutEntry,guards::kMusicManagerFadeoutGuard.data()},
 };
constexpr auto kCount=static_cast<unsigned>(Api100ValuesNative::Count);
static_assert(sizeof(kEntries)/sizeof(kEntries[0])==kCount);
using GuardCache=api100_native::Cache;
static_assert(std::is_trivial_v<GuardCache>);
GuardCache g_Cache[kCount]{};
#if !defined(__SWITCH__)
Api100ValuesNativeTestBindings g_Tests{};
#endif
template<class Fn>Fn Native(lua_State*state,Api100ValuesNative method){
 const auto index=static_cast<unsigned>(method);
 if(index>=kCount){luaL_error(state,"invalid api100 native method");return nullptr;}
 std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Tests.methods[index];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(state,kEntries[index],g_Cache[index],host));
}
LuaRuntime::ColorHandle* Color(lua_State*state){return RequireColorArgument(state,1);}
float Number(lua_State*state,int index){return static_cast<float>(luaL_checknumber(state,index));}
float NumberOr(lua_State*state,int index,float fallback){return lua_toboolean(state,index)?Number(state,index):fallback;}
std::int32_t Integer(lua_State*state,int index){const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(state,index));std::int32_t value{};std::memcpy(&value,&bits,4);return value;}
void* Music(lua_State*state){
 luaL_checkudata(state,1,LuaRuntime::kMusicMetatable);const auto receiver=ResolveEngineReceiver(state,FieldReceipt::Music,1);
 if(!receiver)luaL_error(state,"MusicManager native receiver unavailable");
 return engine_memory::AsObject(receiver);
}
int SpriteAction(lua_State*state,Api100ValuesNative id){const auto receiver=ResolveSpriteArgument(state,1);
 if(!receiver)return luaL_error(state,"Sprite reference is no longer available");
 Native<void(*)(void*)>(state,id)(receiver);return 0;
}
}
#if !defined(__SWITCH__)
void SetApi100ValuesNativeTestBindings(Api100ValuesNativeTestBindings value) noexcept{g_Tests=value;}
#endif
int Api100ColorSetOffset(lua_State*state){
 auto*self=Color(state);const auto red=Number(state,2),green=Number(state,3),blue=Number(state,4);auto value=EngineColorModFromHandle(*self);
 Native<void(*)(EngineColorMod*,float,float,float)>(state,Api100ValuesNative::ColorSetOffset)(&value,red,green,blue);
 FillLuaColorHandleFromEngineColorMod(*self,value);return 0;
}
int Api100ColorSetTint(lua_State*state){
 auto*self=Color(state);const auto red=Number(state,2),green=Number(state,3),blue=Number(state,4),alpha=Number(state,5);auto value=EngineColorModFromHandle(*self);
 Native<void(*)(EngineColorMod*,float,float,float,float)>(state,Api100ValuesNative::ColorSetTint)(&value,red,green,blue,alpha);
 FillLuaColorHandleFromEngineColorMod(*self,value);return 0;
}
int Api100ColorReset(lua_State*state){
 auto*self=Color(state);auto value=EngineColorModFromHandle(*self);
 Native<void(*)(EngineColorMod*)>(state,Api100ValuesNative::ColorReset)(&value);
 FillLuaColorHandleFromEngineColorMod(*self,value);return 0;
}
int Api100SpriteReload(lua_State*state){return SpriteAction(state,Api100ValuesNative::SpriteReload);}
int Api100SpriteRemoveOverlay(lua_State*state){return SpriteAction(state,Api100ValuesNative::SpriteRemoveOverlay);}
int Api100MusicManagerFadein(lua_State*state){
 auto*receiver=Music(state);const auto id=Integer(state,2);const auto volume=NumberOr(state,3,1.0F),rate=NumberOr(state,4,0.08F);
 Native<void(*)(void*,std::int32_t,float,float)>(state,Api100ValuesNative::MusicManagerFadein)(receiver,id,volume,rate);return 0;
}
int Api100MusicManagerFadeout(lua_State*state){
 auto*receiver=Music(state);const auto rate=NumberOr(state,2,0.08F);
 Native<void(*)(void*,float)>(state,Api100ValuesNative::MusicManagerFadeout)(receiver,rate);return 0;
}
}
