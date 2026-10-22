#include "interfaces/lua/api100_entities.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/api100_entities.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include "runtime_constants.hpp"
#include <cstring>
#include <type_traits>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
namespace guards=api100_entities;
using Entry=api100_native::Entry;
constexpr Entry kEntries[]={
 {guards::kEntityFamiliarAddCoinsEntry,guards::kEntityFamiliarAddCoinsGuard.data()},
 {guards::kEntityFamiliarAddHeartsEntry,guards::kEntityFamiliarAddHeartsGuard.data()},
 {guards::kEntityFamiliarAddKeysEntry,guards::kEntityFamiliarAddKeysGuard.data()},
 {guards::kEntityFamiliarRemoveFromFollowersEntry,guards::kEntityFamiliarRemoveFromFollowersGuard.data()},
 {guards::kEntityFamiliarRemoveFromDelayedEntry,guards::kEntityFamiliarRemoveFromDelayedGuard.data()},
 {guards::kEntityFamiliarAddToDelayedEntry,guards::kEntityFamiliarAddToDelayedGuard.data()},
 {guards::kEntityFamiliarMoveDelayedEntry,guards::kEntityFamiliarMoveDelayedGuard.data()},
 {guards::kEntityFamiliarMoveDiagonallyEntry,guards::kEntityFamiliarMoveDiagonallyGuard.data()},
 {guards::kEntityFamiliarPlayChargeAnimEntry,guards::kEntityFamiliarPlayChargeAnimGuard.data()},
 {guards::kEntityFamiliarPlayFloatAnimEntry,guards::kEntityFamiliarPlayFloatAnimGuard.data()},
 {guards::kEntityFamiliarPlayShootAnimEntry,guards::kEntityFamiliarPlayShootAnimGuard.data()},
 {guards::kEntityFamiliarShootEntry,guards::kEntityFamiliarShootGuard.data()},
 {guards::kEntityPickupPlayPickupSoundEntry,guards::kEntityPickupPlayPickupSoundGuard.data()},
 {guards::kEntityPickupPlayDropSoundEntry,guards::kEntityPickupPlayDropSoundGuard.data()},
 {guards::kEntityPickupAppearFastEntry,guards::kEntityPickupAppearFastGuard.data()},
 {guards::kEntityPickupGetCoinValueEntry,guards::kEntityPickupGetCoinValueGuard.data()},
 {guards::kGridEntityHurtEntry,guards::kGridEntityHurtGuard.data()},
 {guards::kGridEntityDoorCanBlowOpenEntry,guards::kGridEntityDoorCanBlowOpenGuard.data()},
 {guards::kGridEntityDoorSetLockedEntry,guards::kGridEntityDoorSetLockedGuard.data()},
 {guards::kGridEntityDoorSetRoomTypesEntry,guards::kGridEntityDoorSetRoomTypesGuard.data()},
 {guards::kGridEntityDoorSpawnDustEntry,guards::kGridEntityDoorSpawnDustGuard.data()},
 {guards::kGridEntityRockGetBigRockFrameEntry,guards::kGridEntityRockGetBigRockFrameGuard.data()},
 {guards::kGridEntityRockSetBigRockFrameEntry,guards::kGridEntityRockSetBigRockFrameGuard.data()},
 {guards::kGridEntityRockUpdateAnimFrameEntry,guards::kGridEntityRockUpdateAnimFrameGuard.data()},
 {guards::kHurtFireEntry,guards::kHurtFireGuard.data()},
 {guards::kHurtTntEntry,guards::kHurtTntGuard.data()},
 {guards::kHurtPoopEntry,guards::kHurtPoopGuard.data()},
 };
constexpr auto kCount=static_cast<unsigned>(Api100EntitiesNative::Count);
constexpr auto kGuardCount=kCount+3;
static_assert(sizeof(kEntries)/sizeof(kEntries[0])==kGuardCount);
using GuardCache=api100_native::Cache;
static_assert(std::is_trivial_v<GuardCache>);
GuardCache g_Cache[kGuardCount]{};
#if !defined(__SWITCH__)
Api100EntitiesNativeTestBindings g_Tests{};
#endif
std::uintptr_t Check(lua_State*state,unsigned index,std::uintptr_t host=0){
 if(index>=kGuardCount){luaL_error(state,"invalid api100 entities native method");return 0;}
 return api100_native::Resolve(state,kEntries[index],g_Cache[index],host);
}
template<class Fn>Fn Native(lua_State*state,Api100EntitiesNative id){
 const auto index=static_cast<unsigned>(id);
 if(index>=kCount){luaL_error(state,"invalid api100 entities method");return nullptr;}
 std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Tests.methods[index];
#endif
 return engine_call::AsFunction<Fn>(Check(state,index,host));
}
enum class Family {Familiar,Pickup,Grid,Door,Rock};
void* Receiver(lua_State*state,Family family){
 std::uintptr_t pointer{};
 if(family==Family::Familiar){luaL_checkudata(state,1,LuaRuntime::kEntityFamiliarMetatable);pointer=ResolveEngineReceiver(state,FieldReceipt::EntityFamiliar,1);}
 else if(family==Family::Pickup){luaL_checkudata(state,1,LuaRuntime::kEntityPickupMetatable);pointer=EntityPointerArgument(state,1);if(!IsPickupEntity(pointer))pointer=0;}
 else {
  pointer=ResolveEngineReceiver(state,FieldReceipt::GridEntity,1);
  if(pointer&&(family==Family::Door||family==Family::Rock)){
   std::uintptr_t vptr{};const auto wanted=LuaRuntime::EngineModuleBase()+(family==Family::Door?kGridEntity_DoorVtableOffset:kGridEntity_RockVtableOffset);
   if(!engine_memory::ReadField(pointer,0,&vptr,engine_memory::EngineMemoryReadable)||vptr!=wanted)pointer=0;
  }
 }
 if(!pointer)luaL_error(state,"api100 entity receiver is no longer available or has the wrong native type");
 return engine_memory::AsObject(pointer);
}
std::int32_t Integer(lua_State*state,int index=2){const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(state,index));std::int32_t n{};std::memcpy(&n,&bits,4);return n;}
int Action(lua_State*state,Family family,Api100EntitiesNative id){auto*p=Receiver(state,family);Native<void(*)(void*)>(state,id)(p);return 0;}
int IntAction(lua_State*state,Family family,Api100EntitiesNative id){auto*p=Receiver(state,family);const auto n=Integer(state);Native<void(*)(void*,std::int32_t)>(state,id)(p,n);return 0;}
int IntRead(lua_State*state,Family family,Api100EntitiesNative id){auto*p=Receiver(state,family);lua_pushinteger(state,Native<std::int32_t(*)(const void*)>(state,id)(p));return 1;}
}
#if !defined(__SWITCH__)
void SetApi100EntitiesNativeTestBindings(Api100EntitiesNativeTestBindings value) noexcept{g_Tests=value;}
#endif
int Api100EntityFamiliarAddCoins(lua_State*state){return IntAction(state,Family::Familiar,Api100EntitiesNative::EntityFamiliarAddCoins);}
int Api100EntityFamiliarAddHearts(lua_State*state){return IntAction(state,Family::Familiar,Api100EntitiesNative::EntityFamiliarAddHearts);}
int Api100EntityFamiliarAddKeys(lua_State*state){return IntAction(state,Family::Familiar,Api100EntitiesNative::EntityFamiliarAddKeys);}
int Api100EntityFamiliarRemoveFromFollowers(lua_State*state){return Action(state,Family::Familiar,Api100EntitiesNative::EntityFamiliarRemoveFromFollowers);}
int Api100EntityFamiliarRemoveFromDelayed(lua_State*state){return Action(state,Family::Familiar,Api100EntitiesNative::EntityFamiliarRemoveFromDelayed);}
int Api100EntityFamiliarAddToDelayed(lua_State*state){return Action(state,Family::Familiar,Api100EntitiesNative::EntityFamiliarAddToDelayed);}
int Api100EntityFamiliarMoveDelayed(lua_State*state){return IntAction(state,Family::Familiar,Api100EntitiesNative::EntityFamiliarMoveDelayed);}
int Api100EntityFamiliarPlayChargeAnim(lua_State*state){return IntAction(state,Family::Familiar,Api100EntitiesNative::EntityFamiliarPlayChargeAnim);}
int Api100EntityFamiliarPlayFloatAnim(lua_State*state){return IntAction(state,Family::Familiar,Api100EntitiesNative::EntityFamiliarPlayFloatAnim);}
int Api100EntityFamiliarPlayShootAnim(lua_State*state){return IntAction(state,Family::Familiar,Api100EntitiesNative::EntityFamiliarPlayShootAnim);}
int Api100EntityFamiliarShoot(lua_State*state){return Action(state,Family::Familiar,Api100EntitiesNative::EntityFamiliarShoot);}
int Api100EntityPickupPlayPickupSound(lua_State*state){return Action(state,Family::Pickup,Api100EntitiesNative::EntityPickupPlayPickupSound);}
int Api100EntityPickupPlayDropSound(lua_State*state){return Action(state,Family::Pickup,Api100EntitiesNative::EntityPickupPlayDropSound);}
int Api100EntityPickupAppearFast(lua_State*state){return Action(state,Family::Pickup,Api100EntitiesNative::EntityPickupAppearFast);}
int Api100EntityPickupGetCoinValue(lua_State*state){return IntRead(state,Family::Pickup,Api100EntitiesNative::EntityPickupGetCoinValue);}
int Api100GridEntityDoorSpawnDust(lua_State*state){return Action(state,Family::Door,Api100EntitiesNative::GridEntityDoorSpawnDust);}
int Api100GridEntityRockGetBigRockFrame(lua_State*state){return IntRead(state,Family::Rock,Api100EntitiesNative::GridEntityRockGetBigRockFrame);}
int Api100GridEntityRockSetBigRockFrame(lua_State*state){return IntAction(state,Family::Rock,Api100EntitiesNative::GridEntityRockSetBigRockFrame);}
int Api100GridEntityRockUpdateAnimFrame(lua_State*state){return Action(state,Family::Rock,Api100EntitiesNative::GridEntityRockUpdateAnimFrame);}
int Api100EntityFamiliarMoveDiagonally(lua_State*state){auto*p=Receiver(state,Family::Familiar);const auto speed=static_cast<float>(luaL_checknumber(state,2));Native<void(*)(void*,float)>(state,Api100EntitiesNative::EntityFamiliarMoveDiagonally)(p,speed);return 0;}
int Api100GridEntityDoorCanBlowOpen(lua_State*state){auto*p=Receiver(state,Family::Door);lua_pushboolean(state,Native<bool(*)(void*)>(state,Api100EntitiesNative::GridEntityDoorCanBlowOpen)(p));return 1;}
int Api100GridEntityDoorSetLocked(lua_State*state){auto*p=Receiver(state,Family::Door);Native<void(*)(void*,bool)>(state,Api100EntitiesNative::GridEntityDoorSetLocked)(p,lua_toboolean(state,2)!=0);return 0;}
int Api100GridEntityDoorSetRoomTypes(lua_State*state){auto*p=Receiver(state,Family::Door);const auto current=Integer(state,2),target=Integer(state,3);Native<void(*)(void*,std::int32_t,std::int32_t)>(state,Api100EntitiesNative::GridEntityDoorSetRoomTypes)(p,current,target);return 0;}
int Api100GridEntityHurt(lua_State*state){
 auto*p=Receiver(state,Family::Grid);const auto damage=Integer(state);const auto address=engine_memory::AddressOf(p);std::uintptr_t vptr{},target{};
 if(!engine_memory::ReadField(address,0,&vptr,engine_memory::EngineMemoryReadable)||!engine_memory::ReadField(vptr,guards::kGridHurtVtableSlot,&target,engine_memory::EngineMemoryReadable))return luaL_error(state,"GridEntity.Hurt virtual method unavailable");
 const auto base=LuaRuntime::EngineModuleBase();unsigned index=kGuardCount;
 if(base&&target>=base){const auto offset=target-base;
  if(offset==guards::kGridEntityHurtEntry)index=static_cast<unsigned>(Api100EntitiesNative::GridEntityHurt);
  else if(offset==guards::kHurtFireEntry)index=kCount;
  else if(offset==guards::kHurtTntEntry)index=kCount+1;
  else if(offset==guards::kHurtPoopEntry)index=kCount+2;
 }
 if(index>=kGuardCount)return luaL_error(state,"GridEntity.Hurt virtual method guard target mismatch");
 Check(state,index);using Fn=bool(*)(void*,std::int32_t);Fn fn=nullptr;
#if !defined(__SWITCH__)
 const auto override=g_Tests.methods[static_cast<unsigned>(Api100EntitiesNative::GridEntityHurt)];if(override)fn=engine_call::AsFunction<Fn>(override);
#endif
 if(!fn)fn=engine_call::AsFunction<Fn>(target);
 lua_pushboolean(state,fn(p,damage));return 1;
}
}
