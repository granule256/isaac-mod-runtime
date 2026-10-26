#include "interfaces/lua/api600_player.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/font_api.hpp"
#include "interfaces/lua/api700_world.hpp"
#include "interfaces/lua/api700_world.guards.hpp"
#include "interfaces/lua/api700_string.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/rng_api.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <cstring>
#include <new>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime{
namespace{
using Vec=LuaRuntime::VectorHandle;
struct Descriptor{std::int32_t words[8];};
static_assert(sizeof(Descriptor)==32&&alignof(Descriptor)==4);
api100_native::Cache g_Cache[15]{};
#if !defined(__SWITCH__)
std::uintptr_t g_Host[8]{};
#endif
std::uintptr_t Guard(lua_State*L,unsigned n){const auto&g=api700_world::kGuards[n];return api100_native::Resolve(L,{g.offset,g.bytes.data()},g_Cache[n]);}
template<class F>F Native(lua_State*L,unsigned n){const auto address=Guard(L,n);const auto&g=api700_world::kGuards[n];
#if !defined(__SWITCH__)
 if(n<6&&g_Host[n])return engine_call::AsFunction<F>(g_Host[n]);
 if(n==11&&g_Host[6])return engine_call::AsFunction<F>(g_Host[6]);
 if(n==14&&g_Host[7])return engine_call::AsFunction<F>(g_Host[7]);
 luaL_error(L,"api700 world native host binding unavailable");
#endif
 return engine_call::AsFunction<F>(address-(g.offset-g.entry));
}
template<class T>T Read(lua_State*L,std::uintptr_t p,unsigned offset){T v{};if(!engine_memory::ReadField(p,offset,&v,engine_memory::EngineMemoryReadable))luaL_error(L,"api700 native field is not readable");return v;}
std::uintptr_t Receiver(lua_State*L,FieldReceipt family,const char*mt){luaL_checkudata(L,1,mt);const auto p=ResolveEngineReceiver(L,family,1);if(!p)luaL_error(L,"native receiver is no longer available");return p;}
std::uintptr_t Pool(lua_State*L){const auto p=ResolveEngineReceiver(L,FieldReceipt::ItemPool,1);if(!p)luaL_error(L,"ItemPool is no longer available");return p;}
std::int32_t Int(lua_State*L,int i){const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(L,i));std::int32_t v{};std::memcpy(&v,&bits,4);return v;}
int ReadOnly(lua_State*L){return luaL_error(L,"native descriptor is read-only");}
std::uintptr_t DescriptorIdentity(lua_State*L,int index)noexcept {
 return lua_rawlen(L,index)==sizeof(Descriptor)?engine_memory::AddressOf(lua_touserdata(L,index)):0;
}
void PushDescriptor(lua_State*L,const Descriptor&value,const char*mt,const char*name){auto*p=static_cast<Descriptor*>(lua_newuserdata(L,sizeof(Descriptor)));*p=value;
 if(luaL_newmetatable(L,mt)){if(!RegisterNativeObjectIdentity(L,-1,DescriptorIdentity))luaL_error(L,"descriptor identity resolver conflicts");lua_pushstring(L,name);lua_setfield(L,-2,"__type");lua_pushstring(L,name);lua_setfield(L,-2,"__name");lua_pushvalue(L,-1);lua_setfield(L,-2,"__class");lua_pushcfunction(L,ReadOnly);lua_setfield(L,-2,"__newindex");}lua_setmetatable(L,-2);
}
int Seed(lua_State*L,const void*text,void*boolean){const auto value=Native<std::int32_t(*)(const void*)>(L,2)(text);if(boolean)lua_pushboolean(L,value!=0);else lua_pushinteger(L,value);return 1;}
std::uintptr_t LevelRng(const LuaRuntime::RngHandle*h)noexcept{
 if(h->index!=LuaRuntime::EngineModuleBase())return 0;
 const auto base=LuaRuntime::EngineModuleBase();std::uintptr_t slot{},game{};
 if(!base||base>UINTPTR_MAX-kGameOwnerGlobalSlotOffset||!engine_memory::ReadAt(base+kGameOwnerGlobalSlotOffset,&slot,engine_memory::EngineMemoryReadable)||!slot||!engine_memory::ReadAt(slot,&game,engine_memory::EngineMemoryReadable)||game!=h->owner)return 0;
 return game+h->offset;
}
struct OpaqueView{std::uintptr_t pointer,game,module;};
std::uintptr_t GameObjectIdentity(lua_State*L,int index)noexcept {
 if(lua_rawlen(L,index)!=sizeof(OpaqueView))return 0;
 const auto*v=static_cast<const OpaqueView*>(lua_touserdata(L,index));
 const auto current=ResolveEngineReceiver(L,FieldReceipt::Level,index);
 return current&&v->module==LuaRuntime::EngineModuleBase()&&v->game==current&&
   engine_memory::EngineMemoryReadable(v->pointer,1)?v->pointer:0;
}
int OpaqueIndex(lua_State*L){auto*v=static_cast<OpaqueView*>(lua_touserdata(L,1));const auto current=ResolveEngineReceiver(L,FieldReceipt::Level,1);if(!v||v->module!=LuaRuntime::EngineModuleBase()||v->game!=current)luaL_error(L,"Game object reference owner is no longer available");lua_pushnil(L);return 1;}
int OpaqueWrite(lua_State*L){static_cast<void>(OpaqueIndex(L));return luaL_error(L,"Game object field is not writable");}
int Opaque(lua_State*L,unsigned offset,unsigned guard,const char*name){const auto p=Receiver(L,FieldReceipt::Level,LuaRuntime::kGameMetatable);Guard(L,guard);auto*v=static_cast<OpaqueView*>(lua_newuserdata(L,sizeof(OpaqueView)));*v={p+offset,p,LuaRuntime::EngineModuleBase()};
 if(luaL_newmetatable(L,name)){if(!RegisterNativeObjectIdentity(L,-1,GameObjectIdentity))luaL_error(L,"Game object identity resolver conflicts");lua_pushstring(L,name);lua_setfield(L,-2,"__type");lua_pushvalue(L,-1);lua_setfield(L,-2,"__class");lua_pushcfunction(L,OpaqueIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,OpaqueWrite);lua_setfield(L,-2,"__newindex");}lua_setmetatable(L,-2);return 1;
}

}
#if !defined(__SWITCH__)
void SetApi700WorldNativeTestBindings(const std::uintptr_t*p,unsigned count)noexcept{for(unsigned i=0;i<8;++i)g_Host[i]=p&&i<count?p[i]:0;}
#endif
int Api700RoomScreenWrapPosition(lua_State*L){const auto p=Receiver(L,FieldReceipt::Room,LuaRuntime::kRoomMetatable);const auto pos=*RequireVectorArgument(L,2);const auto margin=static_cast<float>(luaL_checknumber(L,3));const auto value=Native<Vec(*)(const void*,const Vec&,float,float,float,float)>(L,0)(engine_memory::AsObject(p),pos,margin,margin,margin,margin);PushLuaVector(L,value.x,value.y);return 1;}
int Api700EntityLaserCalculateEndPoint(lua_State*L){const auto start=*RequireVectorArgument(L,1),dir=*RequireVectorArgument(L,2),offset=*RequireVectorArgument(L,3);std::uintptr_t parent{};if(lua_toboolean(L,4)){parent=EntityPointerArgument(L,4);if(!parent)luaL_argerror(L,4,"live Entity or nil expected");}const auto margin=static_cast<float>(luaL_checknumber(L,5));const auto value=Native<Vec(*)(const Vec&,const Vec&,const Vec&,const void*,float)>(L,1)(start,dir,offset,engine_memory::AsObject(parent),margin);PushLuaVector(L,value.x,value.y);return 1;}
int Api700SeedsGetSeedEffect(lua_State*L){return WithApi700NativeString(L,1,Seed,nullptr);}
int Api700SeedsIsSpecialSeed(lua_State*L){return WithApi700NativeString(L,1,Seed,reinterpret_cast<void*>(1));}
int Api700IsaacAddPillEffectToPool(lua_State*L){const auto effect=Int(L,1);const auto p=Pool(L);lua_pushinteger(L,Native<std::int32_t(*)(void*,std::int32_t)>(L,3)(engine_memory::AsObject(p),effect));return 1;}
int Api700IsaacWorldToScreenDistance(lua_State*L){const auto v=*RequireVectorArgument(L,1);PushLuaVector(L,v.x*kWorldToRenderScale,v.y*kWorldToRenderScale);return 1;}
int Api700RoomGetLRoomAreaDesc(lua_State*L){const auto p=Receiver(L,FieldReceipt::Room,LuaRuntime::kRoomMetatable);const auto v=Native<Descriptor(*)(const void*)>(L,4)(engine_memory::AsObject(p));PushDescriptor(L,v,"IsaacRuntime.LRoomAreaDesc","LRoomAreaDesc");return 1;}
int Api700RoomGetLRoomTileDesc(lua_State*L){const auto p=Receiver(L,FieldReceipt::Room,LuaRuntime::kRoomMetatable);const auto v=Native<Descriptor(*)(const void*)>(L,5)(engine_memory::AsObject(p));PushDescriptor(L,v,"IsaacRuntime.LRoomTileDesc","LRoomTileDesc");return 1;}
int Api700ItemPoolAddRoomBlacklist(lua_State*L){const auto p=Receiver(L,FieldReceipt::ItemPool,LuaRuntime::kItemPoolMetatable);const auto item=static_cast<std::uint32_t>(Int(L,2));Guard(L,6);const auto bits=Read<std::uintptr_t>(L,p,0x908);const auto size=Read<std::uint64_t>(L,p,0x910);if(item>=size||!bits)luaL_argerror(L,2,"collectible index out of range");const auto offset=static_cast<std::uintptr_t>(item/64)*8;const auto value=Read<std::uint64_t>(L,bits,offset)|(std::uint64_t{1}<<(item%64));if(!engine_memory::WriteField(bits,offset,value,engine_memory::EngineMemoryWritable))luaL_error(L,"ItemPool room blacklist is not writable");return 0;}
int Api700LevelGetDevilAngelRoomRNG(lua_State*L){const auto p=Receiver(L,FieldReceipt::Level,LuaRuntime::kLevelMetatable);Guard(L,7);auto*h=new(lua_newuserdata(L,sizeof(LuaRuntime::RngHandle)))LuaRuntime::RngHandle{};h->resolver=LevelRng;h->owner=p;h->offset=0x21528;h->index=LuaRuntime::EngineModuleBase();luaL_getmetatable(L,LuaRuntime::kRngMetatable);lua_setmetatable(L,-2);return 1;}
}

namespace isaac::runtime{
int Api700GameGetFont(lua_State*L){const auto p=Receiver(L,FieldReceipt::Level,LuaRuntime::kGameMetatable);Guard(L,8);return PushBorrowedGameFont(L,p,0x24f9c8);}
int Api700GameGetAmbush(lua_State*L){return Opaque(L,0x26faa8,9,"Ambush");}
int Api700GameGetItemOverlay(lua_State*L){return Opaque(L,0x25db0,10,"ItemOverlay");}
}

namespace isaac::runtime{
namespace{
int Fortune(lua_State*L,const char*name){const auto p=Receiver(L,FieldReceipt::Level,LuaRuntime::kGameMetatable);Native<void(*)(void*,const char*)>(L,11)(engine_memory::AsObject(p+0x25c30),name);return 0;}
bool StringEqual(lua_State*L,std::uintptr_t object,const char*text,std::size_t size){const auto header=Read<std::array<unsigned char,24>>(L,object,0);std::uint64_t length=header[0]>>1;std::uintptr_t data=object+1;
 if(header[0]&1U){std::memcpy(&length,header.data()+8,8);std::memcpy(&data,header.data()+16,8);}else if(length>22)luaL_error(L,"invalid native curse name");
 if(length!=size)return false;
 if(!size)return true;
 if(!data||!engine_memory::EngineMemoryReadable(data,size))luaL_error(L,"native curse name is not readable");
 return !std::memcmp(engine_memory::AsObject(data),text,size);
}
}
int Api700GameShowFortune(lua_State*L){return Fortune(L,"Fortune_General");}
int Api700GameShowRule(lua_State*L){return Fortune(L,"Fortune_Rules");}
int Api700IsaacGetCurseIdByName(lua_State*L){std::size_t size{};const auto*name=luaL_checklstring(L,1,&size);Guard(L,12);Guard(L,13);const auto base=LuaRuntime::EngineModuleBase();const auto slot=Read<std::uintptr_t>(L,base,kGameManagerGlobalSlotOffset);if(!slot)luaL_error(L,"curse manager is unavailable");const auto manager=Read<std::uintptr_t>(L,slot,0);if(!manager||manager>UINTPTR_MAX-0x24080)luaL_error(L,"curse manager is unavailable");const auto begin=Read<std::uintptr_t>(L,manager,0x24078),end=Read<std::uintptr_t>(L,manager,0x24080);
 if(end<begin||(end-begin)%32||(!begin&&end))luaL_error(L,"native curse array is invalid");
 for(auto item=end;item>begin;){item-=32;if(StringEqual(L,item+8,name,size)){lua_pushinteger(L,Read<std::int32_t>(L,item,0));return 1;}}
 lua_pushinteger(L,-1);return 1;
}
}

namespace isaac::runtime{
int Api700IsaacScreenToWorldDistance(lua_State*L){const auto v=*RequireVectorArgument(L,1);PushLuaVector(L,v.x/kWorldToRenderScale,v.y/kWorldToRenderScale);return 1;}
int Api700IsaacGetScreenPointScale(lua_State*L){float scale{};if(!ReadFloatGlobalSlot(kIsaacPointScaleSlotOffset,&scale))return luaL_error(L,"screen point scale native value is unavailable");lua_pushnumber(L,scale);return 1;}
}

namespace isaac::runtime{
int Api700GameSpawnEntityDesc(lua_State*L){const auto game=Receiver(L,FieldReceipt::Level,LuaRuntime::kGameMetatable);const auto desc=Api600EntityDescArgument(L,2);const auto position=*RequireVectorArgument(L,3);std::uintptr_t source{};if(lua_toboolean(L,4)){source=EntityPointerArgument(L,4);if(!source)luaL_argerror(L,4,"live Entity or nil expected");}const auto result=Native<std::uintptr_t(*)(void*,const void*,const Vec&,void*)>(L,14)(engine_memory::AsObject(game),engine_memory::AsObject(desc),position,engine_memory::AsObject(source));if(result)PushEntityCallbackArgument(L,result);else lua_pushnil(L);return 1;}
}

namespace isaac::runtime {
int Api700RoomGetEnemyDamageInflicted(lua_State* L){
 const auto room=Receiver(L,FieldReceipt::Room,LuaRuntime::kRoomMetatable);
 struct Layout{std::uintptr_t offset;std::uint8_t bytes[16];};
 static constexpr Layout layouts[]={{0x767c0,{255,3,3,209,236,27,0,253,235,43,4,109,233,35,5,109}},{0x76d38,{1,1,39,30,0,144,54,30,224,67,0,145,104,30,1,189}},{0x468a7c,{8,72,89,185,9,42,131,82,10,5,0,17,10,72,25,185}}};
 static api100_native::Cache caches[3]{};
 for(unsigned i=0;i<3;++i)static_cast<void>(api100_native::Resolve(L,{layouts[i].offset,layouts[i].bytes},caches[i]));
 // PC Room+1218+BC；NS Room+1950+11C。现有EntityList::Update每帧重算，禁止影子累计。
 lua_pushnumber(L,Read<float>(L,room,kRoomEntityListOffset+0x11c));return 1;
}
}
