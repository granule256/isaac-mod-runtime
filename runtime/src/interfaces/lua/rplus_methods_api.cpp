#include "interfaces/lua/rplus_methods_api.hpp"
#include "interfaces/lua/rplus_methods_guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/entity_ref_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/bitset128_api.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "interfaces/lua/field_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
namespace guards=rplus_methods;
using Vec2=LuaRuntime::VectorHandle;
struct Cache {std::uintptr_t base{};bool valid{};};
Cache g_Native[static_cast<unsigned>(RPlusMethodsNative::Count)]{},g_Aim{},g_Countdown{},g_Grid{},g_Hearts{},g_Award{};
#if !defined(__SWITCH__)
RPlusMethodsNativeTestBindings g_Tests{};
#endif
template<std::size_t N> void CheckGuard(lua_State* state,Cache& cache,
    std::uintptr_t offset,const std::array<std::uint8_t,N>& bytes) {
    const auto base=LuaRuntime::EngineModuleBase();
    if(cache.base!=base||!cache.valid){cache.base=base;
        cache.valid=base&&base<=UINTPTR_MAX-offset-N&&engine_memory::EngineMemoryReadable(base+offset,N)&&
            !std::memcmp(engine_memory::AsObject(base+offset),bytes.data(),N);}
    if(!cache.valid)luaL_error(state,"native method guard mismatch");
}
template<class Function,std::size_t N> Function Native(lua_State* state,RPlusMethodsNative id,
    std::uintptr_t entry,const std::array<std::uint8_t,N>& bytes) {
    const auto index=static_cast<unsigned>(id);
#if !defined(__SWITCH__)
    if(g_Tests.methods[index])return engine_call::AsFunction<Function>(g_Tests.methods[index]);
#endif
    CheckGuard(state,g_Native[index],entry,bytes);
    return engine_call::AsFunction<Function>(LuaRuntime::EngineModuleBase()+entry);
}
void* Receiver(lua_State* state,FieldReceipt kind,const char* metatable=nullptr) {
    if(metatable)luaL_checkudata(state,1,metatable);
    const auto pointer=ResolveEngineReceiver(state,kind,1);
    if(!pointer)luaL_error(state,"receiver reference is no longer available");
    return engine_memory::AsObject(pointer);
}
void* Player(lua_State* state){return Receiver(state,FieldReceipt::EntityPlayer,LuaRuntime::kEntityPlayerMetatable);}
std::int32_t Int(lua_State* state,int index) {
    const auto value=static_cast<std::uint32_t>(luaL_checkinteger(state,index));
    std::int32_t result{};std::memcpy(&result,&value,4);return result;
}
std::int32_t IntOr(lua_State* state,int index,std::int32_t fallback){return lua_toboolean(state,index)?Int(state,index):fallback;}
float NumberOr(lua_State* state,int index,float fallback){return lua_toboolean(state,index)?static_cast<float>(luaL_checknumber(state,index)):fallback;}
const char* StringOr(lua_State* state,int index,const char* fallback){return lua_toboolean(state,index)?luaL_checkstring(state,index):fallback;}
const Vec2& Vector(lua_State* state,int index){return *RequireVectorArgument(state,index);}
void* SourceRef(lua_State* state){const auto ref=EntityRefBufferAt(state,2);if(!ref)luaL_argerror(state,2,"EntityRef expected");return ref;}
void* OptionalEntity(lua_State* state,int index) {
    if(lua_isnoneornil(state,index))return nullptr;
    const auto pointer=EntityPointerArgument(state,index);
    if(!pointer)luaL_argerror(state,index,"live Entity expected");
    return engine_memory::AsObject(pointer);
}
EngineColorMod Color(lua_State* state,int index,bool optional) {
    if(optional&&!lua_toboolean(state,index))return DefaultEngineColorMod();
    EngineColorMod color{};if(!FillEngineColorMod(state,index,&color))luaL_argerror(state,index,"Color expected");return color;
}
void* Item(lua_State* state,int index){const auto pointer=ItemConfigPointerArgument(state,index);if(!pointer)luaL_argerror(state,index,"live ItemConfigItem expected");return engine_memory::AsObject(pointer);}
int PushEntity(lua_State* state,void* pointer){if(!pointer)lua_pushnil(state);else PushEntityCallbackArgument(state,engine_memory::AddressOf(pointer));return 1;}
template<class Value> Value Read(lua_State* state,std::uintptr_t object,std::uintptr_t offset){Value value{};
    if(!engine_memory::ReadField(object,offset,&value,engine_memory::EngineMemoryReadable))luaL_error(state,"native field unavailable");
    return value;}
template<class Value> void Write(lua_State* state,std::uintptr_t object,std::uintptr_t offset,const Value& value){
    if(!engine_memory::WriteField(object,offset,value,engine_memory::EngineMemoryWritable))luaL_error(state,"native field not writable");}
int AddFlags(lua_State* state,const char* field) {
    // 固定PC main.lua的真实方法：getter|f再交给原setter，保留SetTearFlags的附加效果。
    lua_getfield(state,1,field);
    // PC BitSet128.__bor先tobitset128：仅number转构造器，字符串不偷偷转整数。
    if(lua_type(state,2)==LUA_TNUMBER)PushBitSet128(state,{static_cast<std::uint64_t>(luaL_checkinteger(state,2)),0});
    else lua_pushvalue(state,2);
    lua_arith(state,LUA_OPBOR);lua_setfield(state,1,field);return 0;
}
}
#if !defined(__SWITCH__)
void SetRPlusMethodsNativeTestBindings(RPlusMethodsNativeTestBindings value) noexcept {g_Tests=value;}
#endif
#define METHOD(type,name) Native<type>(state,RPlusMethodsNative::name,guards::k##name##Entry,guards::k##name##Guard)
int RPlusEntityAddBurn(lua_State* state) {
    auto* entity=Receiver(state,FieldReceipt::Entity);const auto* ref=SourceRef(state);const auto duration=Int(state,3);const auto damage=static_cast<float>(luaL_checknumber(state,4));
    using Fn=void (*)(void*,const void*,std::int32_t,float);METHOD(Fn,AddBurn)(entity,ref,duration,damage);return 0;
}
int RPlusEntityAddConfusion(lua_State* state) {
    auto* entity=Receiver(state,FieldReceipt::Entity);const auto* ref=SourceRef(state);const auto duration=Int(state,3);
    using Fn=void (*)(void*,const void*,std::int32_t,bool);METHOD(Fn,AddConfusion)(entity,ref,duration,lua_toboolean(state,4)!=0);return 0;
}
int RPlusEntityAddMidasFreeze(lua_State* state) {
    auto* entity=Receiver(state,FieldReceipt::Entity);const auto* ref=SourceRef(state);const auto duration=Int(state,3);
    using Fn=void (*)(void*,const void*,std::int32_t);METHOD(Fn,AddMidasFreeze)(entity,ref,duration);return 0;
}
int RPlusEntityAddShrink(lua_State* state) {
    auto* entity=Receiver(state,FieldReceipt::Entity);const auto* ref=SourceRef(state);const auto duration=Int(state,3);
    using Fn=void (*)(void*,const void*,std::int32_t);METHOD(Fn,AddShrink)(entity,ref,duration);return 0;
}
int RPlusEntityAddSlowing(lua_State* state) {
    auto* entity=Receiver(state,FieldReceipt::Entity);const auto* ref=SourceRef(state);const auto duration=Int(state,3);const auto slow=static_cast<float>(luaL_checknumber(state,4));const auto color=Color(state,5,false);
    using Fn=void (*)(void*,const void*,std::int32_t,float,EngineColorMod);METHOD(Fn,AddSlowing)(entity,ref,duration,slow,color);return 0;
}
int RPlusEntityHasMortalDamage(lua_State* state){auto* e=Receiver(state,FieldReceipt::Entity);using Fn=bool (*)(void*);lua_pushboolean(state,METHOD(Fn,HasMortalDamage)(e));return 1;}
int RPlusBombAddTearFlags(lua_State* s){return AddFlags(s,"Flags");}
int RPlusKnifeAddTearFlags(lua_State* s){return AddFlags(s,"TearFlags");}
int RPlusLaserAddTearFlags(lua_State* s){return AddFlags(s,"TearFlags");}
int RPlusTearAddTearFlags(lua_State* s){return AddFlags(s,"TearFlags");}
int RPlusBombSetExplosionCountdown(lua_State* state) {
    const auto bomb=engine_memory::AddressOf(Receiver(state,FieldReceipt::Entity,LuaRuntime::kEntityBombMetatable));
    const auto count=Int(state,2);CheckGuard(state,g_Countdown,guards::kBombCountdownWriterEntry,guards::kBombCountdownWriterGuard);
    struct Pair {std::int32_t remaining,initial;};Write(state,bomb,kRPlusBombCountdownOffset,Pair{count,count});return 0;
}
int RPlusPlayerAddCostume(lua_State* state) {
    auto* player=Player(state);auto* item=Item(state,2);using Fn=void (*)(void*,const void*,bool);METHOD(Fn,AddCostume)(player,item,lua_toboolean(state,3)!=0);return 0;
}
int RPlusPlayerAddWisp(lua_State* state) {
    auto* player=Player(state);const auto type=Int(state,2);const auto& pos=Vector(state,3);
    using Fn=void* (*)(void*,std::int32_t,const Vec2&,bool,bool);return PushEntity(state,METHOD(Fn,AddWisp)(player,type,pos,lua_toboolean(state,4)!=0,lua_toboolean(state,5)!=0));
}
int RPlusPlayerAnimateCard(lua_State* state){auto* p=Player(state);const auto card=Int(state,2);const auto* anim=StringOr(state,3,"Pickup");using Fn=void (*)(void*,std::int32_t,const char*);METHOD(Fn,AnimateCard)(p,card,anim);return 0;}
int RPlusPlayerAnimatePickup(lua_State* state) {
    auto* p=Player(state);const auto* sprite=ResolveSpriteArgument(state,2);if(!sprite)return luaL_argerror(state,2,"live Sprite expected");
    const auto* anim=StringOr(state,4,"Pickup");using Fn=void (*)(void*,const void*,bool,const char*);METHOD(Fn,AnimatePickup)(p,sprite,lua_toboolean(state,3)!=0,anim);return 0;
}
int RPlusPlayerCanPickupItem(lua_State* state){auto* p=Player(state);using Fn=bool (*)(const void*);lua_pushboolean(state,METHOD(Fn,CanPickupItem)(p));return 1;}
int RPlusPlayerFireBomb(lua_State* state){auto* p=Player(state);const auto& pos=Vector(state,2);const auto& vel=Vector(state,3);auto* source=OptionalEntity(state,4);using Fn=void* (*)(void*,const Vec2&,const Vec2&,void*);return PushEntity(state,METHOD(Fn,FireBomb)(p,pos,vel,source));}
int RPlusPlayerFlushQueueItem(lua_State* state){auto* p=Player(state);using Fn=bool (*)(void*);lua_pushboolean(state,METHOD(Fn,FlushQueueItem)(p));return 1;}
int RPlusPlayerFullCharge(lua_State* state){auto* p=Player(state);const auto slot=IntOr(state,2,0);using Fn=std::int32_t (*)(void*,std::int32_t,bool);lua_pushboolean(state,METHOD(Fn,FullCharge)(p,slot,lua_toboolean(state,3)!=0)!=0);return 1;}
int RPlusPlayerGetAimDirection(lua_State* state){const auto p=engine_memory::AddressOf(Player(state));CheckGuard(state,g_Aim,guards::kAimWriterEntry,guards::kAimWriterGuard);PushEntityVectorReference(state,p,kRPlusAimDirectionOffset);return 1;}
int RPlusPlayerGetMaxTrinkets(lua_State* state){auto* p=Player(state);using Fn=std::int32_t (*)(const void*);lua_pushinteger(state,METHOD(Fn,GetMaxTrinkets)(p));return 1;}
int RPlusPlayerGetTearMovementInheritance(lua_State* state){auto* p=Player(state);const auto& direction=Vector(state,2);using Fn=Vec2 (*)(const void*,const Vec2&,bool);const auto value=METHOD(Fn,GetTearMovementInheritance)(p,direction,lua_toboolean(state,3)!=0);PushLuaVector(state,value.x,value.y);return 1;}
int RPlusPlayerRemoveCostume(lua_State* state){auto* p=Player(state);auto* item=Item(state,2);using Fn=void (*)(void*,const void*);METHOD(Fn,RemoveCostume)(p,item);return 0;}
int RPlusPlayerSetPill(lua_State* state){auto* p=Player(state);const auto slot=Int(state,2),pill=Int(state,3);using Fn=void (*)(void*,std::int32_t,std::int32_t);METHOD(Fn,SetPill)(p,slot,pill);return 0;}
int RPlusPlayerSetPocketActiveItem(lua_State* state){auto* p=Player(state);const auto id=Int(state,2),slot=IntOr(state,3,2);using Fn=void (*)(void*,std::int32_t,std::uint32_t,bool);METHOD(Fn,SetPocketActiveItem)(p,id,static_cast<std::uint32_t>(slot),lua_toboolean(state,4)!=0);return 0;}
int RPlusPlayerThrowBlueSpider(lua_State* state){auto* p=Player(state);const auto& pos=Vector(state,2);const auto& target=Vector(state,3);using Fn=void* (*)(void*,const Vec2&,const Vec2&);return PushEntity(state,METHOD(Fn,ThrowBlueSpider)(p,pos,target));}
int RPlusPlayerWillPlayerRevive(lua_State* state){auto* p=Player(state);using Fn=bool (*)(void*);lua_pushboolean(state,METHOD(Fn,WillPlayerRevive)(p));return 1;}
int RPlusProjectileHasProjectileFlags(lua_State* state){lua_getfield(state,1,"ProjectileFlags");lua_pushvalue(state,2);lua_arith(state,LUA_OPBAND);lua_pushinteger(state,0);const bool has=lua_compare(state,-2,-1,LUA_OPEQ)==0;lua_pushboolean(state,has);return 1;}
int RPlusGameClearStagesWithoutHeartsPicked(lua_State* state){const auto game=engine_memory::AddressOf(Receiver(state,FieldReceipt::Level,LuaRuntime::kGameMetatable));CheckGuard(state,g_Hearts,guards::kHeartStagesWriterEntry,guards::kHeartStagesWriterGuard);Write(state,game,kRPlusHeartStagesOffset,std::uint32_t{0});return 0;}
int RPlusGameFart(lua_State* state){auto* game=Receiver(state,FieldReceipt::Level,LuaRuntime::kGameMetatable);const auto& pos=Vector(state,2);const auto radius=NumberOr(state,3,85),scale=NumberOr(state,5,1);auto* source=OptionalEntity(state,4);const auto subtype=static_cast<std::uint32_t>(IntOr(state,6,0));const auto color=Color(state,7,true);using Fn=void (*)(void*,const Vec2&,float,void*,float,std::uint32_t,const EngineColorMod&);METHOD(Fn,Fart)(game,pos,radius,source,scale,subtype,color);return 0;}
int RPlusGameShakeScreen(lua_State* state){auto* game=Receiver(state,FieldReceipt::Level,LuaRuntime::kGameMetatable);const auto count=Int(state,2);using Fn=void (*)(void*,std::int32_t);METHOD(Fn,ShakeScreen)(game,count);return 0;}
int RPlusGridSetVariant(lua_State* state){const auto grid=engine_memory::AddressOf(CheckGridEntityHandle(state,1));const auto variant=Int(state,2);CheckGuard(state,g_Grid,guards::kGridDescWriterEntry,guards::kGridDescWriterGuard);Write(state,grid,kGridEntityVariantOffset,variant);return 0;}
int RPlusDoorBar(lua_State* state){auto* door=Receiver(state,FieldReceipt::GridEntity,LuaRuntime::kGridEntityDoorMetatable);using Fn=void (*)(void*);METHOD(Fn,Bar)(door);return 0;}
int RPlusPathFindGridPath(lua_State* state){auto* path=Receiver(state,FieldReceipt::PathFinder,LuaRuntime::kPathFinderMetatable);const auto& pos=Vector(state,2);const auto speed=static_cast<float>(luaL_checknumber(state,3));const auto marker=Int(state,4);using Fn=void (*)(void*,const Vec2&,float,std::int32_t,bool);METHOD(Fn,FindGridPath)(path,pos,speed,marker,lua_toboolean(state,5)!=0);return 0;}
int RPlusRoomGetAwardSeed(lua_State* state){luaL_checkudata(state,1,LuaRuntime::kRoomMetatable);CheckGuard(state,g_Award,guards::kAwardSeedReaderEntry,guards::kAwardSeedReaderGuard);const auto desc=ResolveEngineReceiver(state,FieldReceipt::RoomDescriptor,1);if(!desc){lua_pushinteger(state,0);return 1;}lua_pushinteger(state,Read<std::uint32_t>(state,desc,kRPlusAwardSeedOffset));return 1;}
#undef METHOD
}
