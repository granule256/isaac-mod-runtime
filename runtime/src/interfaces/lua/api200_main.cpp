#include "interfaces/lua/api200_main.hpp"
#include "interfaces/lua/api200_main.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
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
using Vec=LuaRuntime::VectorHandle;
static_assert(sizeof(Vec)==8);
namespace guard=api200_main;
constexpr api100_native::Entry kEntries[]={
{guard::kEntityHasCommonParentWithEntityEntry,guard::kEntityHasCommonParentWithEntityGuard.data()},
{guard::kEntitySetSizeEntry,guard::kEntitySetSizeGuard.data()},
{guard::kEntityFamiliarGetOrbitDistanceEntry,guard::kEntityFamiliarGetOrbitDistanceGuard.data()},
{guard::kEntityFamiliarPickEnemyTargetEntry,guard::kEntityFamiliarPickEnemyTargetGuard.data()},
{guard::kEntityKnifeResetEntry,guard::kEntityKnifeResetGuard.data()},
{guard::kEntityKnifeShootEntry,guard::kEntityKnifeShootGuard.data()},
{guard::kEntityTearSetDeadEyeIntensityEntry,guard::kEntityTearSetDeadEyeIntensityGuard.data()},
{guard::kGridEntityDoorTryBlowOpenEntry,guard::kGridEntityDoorTryBlowOpenGuard.data()},
{guard::kGridEntityDoorTryUnlockEntry,guard::kGridEntityDoorTryUnlockGuard.data()},
{guard::kGridEntityPitMakeBridgeEntry,guard::kGridEntityPitMakeBridgeGuard.data()},
{guard::kGridEntityPitSetLadderEntry,guard::kGridEntityPitSetLadderGuard.data()},
{guard::kGridEntityPitUpdateCollisionEntry,guard::kGridEntityPitUpdateCollisionGuard.data()},
{guard::kGridEntityPoopRespawnRedPoopEntry,guard::kGridEntityPoopRespawnRedPoopGuard.data()},
{guard::kGridEntityPressurePlateRewardEntry,guard::kGridEntityPressurePlateRewardGuard.data()},
{guard::kHUDAssignPlayerHUDsEntry,guard::kHUDAssignPlayerHUDsGuard.data()},
{guard::kHUDFlashChargeBarEntry,guard::kHUDFlashChargeBarGuard.data()},
{guard::kHUDInvalidateActiveItemEntry,guard::kHUDInvalidateActiveItemGuard.data()},
{guard::kHUDInvalidateCraftingItemEntry,guard::kHUDInvalidateCraftingItemGuard.data()},
{guard::kHUDPostUpdateEntry,guard::kHUDPostUpdateGuard.data()},
{guard::kHUDUpdateEntry,guard::kHUDUpdateGuard.data()},
{guard::kItemConfigGetNullItemEntry,guard::kItemConfigGetNullItemGuard.data()},
{guard::kLevelForceHorsemanBossEntry,guard::kLevelForceHorsemanBossGuard.data()},
{guard::kLevelGetEnterPositionEntry,guard::kLevelGetEnterPositionGuard.data()},
{guard::kLevelGetNonCompleteRoomIndexEntry,guard::kLevelGetNonCompleteRoomIndexGuard.data()},
{guard::kPathFinderEvadeTargetEntry,guard::kPathFinderEvadeTargetGuard.data()},
{guard::kPathFinderGetGridIndexEntry,guard::kPathFinderGetGridIndexGuard.data()},
{guard::kPathFinderMoveRandomlyEntry,guard::kPathFinderMoveRandomlyGuard.data()},
{guard::kPathFinderMoveRandomlyAxisAlignedEntry,guard::kPathFinderMoveRandomlyAxisAlignedGuard.data()},
{guard::kPathFinderMoveRandomlyBossEntry,guard::kPathFinderMoveRandomlyBossGuard.data()},
{guard::kPathFinderResetEntry,guard::kPathFinderResetGuard.data()},
{guard::kPathFinderResetMovementTargetEntry,guard::kPathFinderResetMovementTargetGuard.data()},
{guard::kPathFinderUpdateGridIndexEntry,guard::kPathFinderUpdateGridIndexGuard.data()},
{guard::kRoomCheckLineEntry,guard::kRoomCheckLineGuard.data()},
{guard::kRoomGetClampedGridIndexEntry,guard::kRoomGetClampedGridIndexGuard.data()},
{guard::kRoomGetLaserTargetEntry,guard::kRoomGetLaserTargetGuard.data()},
{guard::kRoomGetSeededCollectibleEntry,guard::kRoomGetSeededCollectibleGuard.data()},
{guard::kRoomMamaMegaExplosionEntry,guard::kRoomMamaMegaExplosionGuard.data()},
{guard::kRoomTryMakeBridgeEntry,guard::kRoomTryMakeBridgeGuard.data()},
{guard::kRoomTrySpawnDevilRoomDoorEntry,guard::kRoomTrySpawnDevilRoomDoorGuard.data()},
{guard::kRoomTrySpawnSecretShopEntry,guard::kRoomTrySpawnSecretShopGuard.data()},
{guard::kRoomTrySpawnSpecialQuestDoorEntry,guard::kRoomTrySpawnSpecialQuestDoorGuard.data()},
{guard::kSeedsCanAddSeedEffectEntry,guard::kSeedsCanAddSeedEffectGuard.data()},
{guard::kSeedsCountUnlockedSeedEffectsEntry,guard::kSeedsCountUnlockedSeedEffectsGuard.data()},
{guard::kSeedsInitSeedInfoEntry,guard::kSeedsInitSeedInfoGuard.data()},
{guard::kSeedsRemoveBlockingSeedEffectsEntry,guard::kSeedsRemoveBlockingSeedEffectsGuard.data()},
{guard::kSeedsResetEntry,guard::kSeedsResetGuard.data()},
{guard::kSeedsRestartEntry,guard::kSeedsRestartGuard.data()},
{guard::kSpriteSetOverlayAnimationEntry,guard::kSpriteSetOverlayAnimationGuard.data()},
};
api100_native::Cache g_Cache[48]{};
#if !defined(__SWITCH__)
Api200MainNativeTestBindings g_Tests{};
#endif
template<class Fn>Fn Native(lua_State*L,Api200MainNative method){
 const auto i=static_cast<unsigned>(method);if(i>=48){luaL_error(L,"invalid api200 method");return nullptr;}
 std::uintptr_t test{};
#if !defined(__SWITCH__)
 test=g_Tests.methods[i];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(L,kEntries[i],g_Cache[i],test));
}
std::int32_t Integer(lua_State*L,int index){const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(L,index));std::int32_t result{};std::memcpy(&result,&bits,4);return result;}
std::int32_t IntegerOr(lua_State*L,int index,std::int32_t fallback){return lua_toboolean(L,index)?Integer(L,index):fallback;}
float Number(lua_State*L,int i){return static_cast<float>(luaL_checknumber(L,i));}
float NumberOr(lua_State*L,int i,float fallback){return lua_toboolean(L,i)?Number(L,i):fallback;}
Vec Vector(lua_State*L,int i){return *RequireVectorArgument(L,i);}
Vec VectorOrZero(lua_State*L,int i){return lua_toboolean(L,i)?Vector(L,i):Vec{0,0};}
void* EntityArg(lua_State*L,int i,bool player=false){
 if(lua_type(L,i)==LUA_TNIL)return nullptr;
 const auto pointer=EntityPointerArgument(L,i);
 if(!pointer||(player&&ClassifyCallbackEntity(pointer)!=CallbackEntityClass::Player)){luaL_argerror(L,i,player?"expected a live EntityPlayer or nil":"expected a live Entity or nil");return nullptr;}
 return engine_memory::AsObject(pointer);
}
void* GridArg(lua_State*L,int i){if(lua_type(L,i)==LUA_TNIL)return nullptr;auto*p=GridEntityHandleArgument(L,i);if(!p)luaL_argerror(L,i,"expected a live GridEntity or nil");return p;}
void* Receiver(lua_State*L,const char*metatable,FieldReceipt receipt){luaL_checkudata(L,1,metatable);const auto p=ResolveEngineReceiver(L,receipt,1);if(!p)luaL_error(L,"api200 receiver is no longer available");return engine_memory::AsObject(p);}
void* EntitySelf(lua_State*L,const char*metatable,CallbackEntityClass family){
 if(metatable)luaL_checkudata(L,1,metatable);
 const auto p=ResolveEngineReceiver(L,FieldReceipt::Entity,1);
 if(!p||(family!=CallbackEntityClass::None&&ClassifyCallbackEntity(p)!=family))luaL_error(L,"api200 entity receiver has expired or has the wrong type");
 return engine_memory::AsObject(p);
}
void* GridSelf(lua_State*L,std::uintptr_t vtable){const auto p=ResolveEngineReceiver(L,FieldReceipt::GridEntity,1);std::uintptr_t v{};
 if(!p||!engine_memory::ReadField(p,0,&v,engine_memory::EngineMemoryReadable)||v!=LuaRuntime::EngineModuleBase()+vtable)luaL_error(L,"api200 grid receiver has expired or has the wrong type");
 return engine_memory::AsObject(p);
}
void* Hud(lua_State*L){luaL_checkudata(L,1,LuaRuntime::kHudMetatable);auto p=ResolveEngineReceiver(L,FieldReceipt::Level,1);if(!p||p>UINTPTR_MAX-kGameHudObjectOffset)luaL_error(L,"HUD receiver unavailable");return engine_memory::AsObject(p+kGameHudObjectOffset);}
template<class R,class...A>int Invoke(lua_State*L,Api200MainNative method,A...a){
 auto fn=Native<R(*)(A...)>(L,method);
 if constexpr(std::is_void_v<R>){fn(a...);return 0;}
 else{auto value=fn(a...);if constexpr(std::is_same_v<R,bool>)lua_pushboolean(L,value);else if constexpr(std::is_same_v<R,Vec>)PushLuaVector(L,value.x,value.y);else lua_pushinteger(L,value);return 1;}
}
}
#if !defined(__SWITCH__)
void SetApi200MainNativeTestBindings(Api200MainNativeTestBindings value)noexcept{g_Tests=value;}
#endif
int Api200EntityHasCommonParentWithEntity(lua_State*L){
 auto*self=EntitySelf(L,nullptr,CallbackEntityClass::None);
 const auto arg0=EntityArg(L,2);
 return Invoke<bool>(L,Api200MainNative::EntityHasCommonParentWithEntity,self,arg0);
}
int Api200EntitySetSize(lua_State*L){
 auto*self=EntitySelf(L,nullptr,CallbackEntityClass::None);
 const auto arg0=Number(L,2);
 const auto arg1=Vector(L,3);
 const auto arg2=Integer(L,4);
 return Invoke<void>(L,Api200MainNative::EntitySetSize,self,arg0,arg1,arg2);
}
int Api200EntityFamiliarGetOrbitDistance(lua_State*L){
 const auto arg0=Integer(L,1);
 return Invoke<Vec>(L,Api200MainNative::EntityFamiliarGetOrbitDistance,arg0);
}
int Api200EntityFamiliarPickEnemyTarget(lua_State*L){
 auto*self=EntitySelf(L,LuaRuntime::kEntityFamiliarMetatable,CallbackEntityClass::Familiar);
 const auto arg0=Number(L,2);
 const auto arg1=IntegerOr(L,3,13);
 const auto arg2=static_cast<std::uint32_t>(IntegerOr(L,4,0));
 const auto arg3=VectorOrZero(L,5);
 const auto arg4=NumberOr(L,6,15.0F);
 return Invoke<void>(L,Api200MainNative::EntityFamiliarPickEnemyTarget,self,arg0,arg1,arg2,&arg3,arg4);
}
int Api200EntityKnifeReset(lua_State*L){
 auto*self=EntitySelf(L,LuaRuntime::kEntityKnifeMetatable,CallbackEntityClass::Knife);
 return Invoke<void>(L,Api200MainNative::EntityKnifeReset,self);
}
int Api200EntityKnifeShoot(lua_State*L){
 auto*self=EntitySelf(L,LuaRuntime::kEntityKnifeMetatable,CallbackEntityClass::Knife);
 const auto arg0=Number(L,2);
 const auto arg1=Number(L,3);
 return Invoke<void>(L,Api200MainNative::EntityKnifeShoot,self,arg0,arg1);
}
int Api200EntityTearSetDeadEyeIntensity(lua_State*L){
 auto*self=EntitySelf(L,LuaRuntime::kEntityTearMetatable,CallbackEntityClass::Tear);
 const auto arg0=Number(L,2);
 return Invoke<void>(L,Api200MainNative::EntityTearSetDeadEyeIntensity,self,arg0);
}
int Api200GridEntityDoorTryBlowOpen(lua_State*L){
 auto*self=GridSelf(L,kGridEntity_DoorVtableOffset);
 const auto arg0=lua_toboolean(L,2)!=0;
 const auto arg1=EntityArg(L,3);
 return Invoke<bool>(L,Api200MainNative::GridEntityDoorTryBlowOpen,self,arg0,arg1);
}
int Api200GridEntityDoorTryUnlock(lua_State*L){
 auto*self=GridSelf(L,kGridEntity_DoorVtableOffset);
 const auto arg0=EntityArg(L,2,true);
 const auto arg1=lua_toboolean(L,3)!=0;
 return Invoke<bool>(L,Api200MainNative::GridEntityDoorTryUnlock,self,arg0,arg1);
}
int Api200GridEntityPitMakeBridge(lua_State*L){
 auto*self=GridSelf(L,kGridEntity_PitVtableOffset);
 const auto arg0=GridArg(L,2);
 return Invoke<void>(L,Api200MainNative::GridEntityPitMakeBridge,self,arg0);
}
int Api200GridEntityPitSetLadder(lua_State*L){
 auto*self=GridSelf(L,kGridEntity_PitVtableOffset);
 const auto arg0=lua_toboolean(L,2)!=0;
 return Invoke<void>(L,Api200MainNative::GridEntityPitSetLadder,self,arg0);
}
int Api200GridEntityPitUpdateCollision(lua_State*L){
 auto*self=GridSelf(L,kGridEntity_PitVtableOffset);
 return Invoke<void>(L,Api200MainNative::GridEntityPitUpdateCollision,self);
}
int Api200GridEntityPoopRespawnRedPoop(lua_State*L){
 auto*self=GridSelf(L,kGridEntity_PoopVtableOffset);
 return Invoke<void>(L,Api200MainNative::GridEntityPoopRespawnRedPoop,self);
}
int Api200GridEntityPressurePlateReward(lua_State*L){
 auto*self=GridSelf(L,kGridEntity_PressurePlateVtableOffset);
 return Invoke<void>(L,Api200MainNative::GridEntityPressurePlateReward,self);
}
int Api200HUDAssignPlayerHUDs(lua_State*L){
 auto*self=Hud(L);
 return Invoke<void>(L,Api200MainNative::HUDAssignPlayerHUDs,self);
}
int Api200HUDFlashChargeBar(lua_State*L){
 auto*self=Hud(L);
 const auto arg0=EntityArg(L,2,true);
 const auto arg1=Integer(L,3);
 return Invoke<void>(L,Api200MainNative::HUDFlashChargeBar,self,arg0,arg1);
}
int Api200HUDInvalidateActiveItem(lua_State*L){
 auto*self=Hud(L);
 const auto arg0=EntityArg(L,2,true);
 const auto arg1=Integer(L,3);
 return Invoke<void>(L,Api200MainNative::HUDInvalidateActiveItem,self,arg0,arg1);
}
int Api200HUDInvalidateCraftingItem(lua_State*L){
 auto*self=Hud(L);
 const auto arg0=EntityArg(L,2,true);
 return Invoke<void>(L,Api200MainNative::HUDInvalidateCraftingItem,self,arg0);
}
int Api200HUDPostUpdate(lua_State*L){
 auto*self=Hud(L);
 return Invoke<void>(L,Api200MainNative::HUDPostUpdate,self);
}
int Api200HUDUpdate(lua_State*L){
 auto*self=Hud(L);
 return Invoke<void>(L,Api200MainNative::HUDUpdate,self);
}
int Api200ItemConfigGetNullItem(lua_State*L){
 auto*self=engine_memory::AsObject(Api200ItemConfigReceiver(L,1));
 const auto arg0=Integer(L,2);
 auto*result=Native<void*(*)(void*,std::int32_t)>(L,Api200MainNative::ItemConfigGetNullItem)(self,arg0);return Api200PushNullItemView(L,engine_memory::AddressOf(result),arg0);
}
int Api200LevelForceHorsemanBoss(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 const auto arg0=static_cast<std::uint32_t>(luaL_checkinteger(L,2));
 return Invoke<bool>(L,Api200MainNative::LevelForceHorsemanBoss,self,arg0);
}
int Api200LevelGetEnterPosition(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 return Invoke<Vec>(L,Api200MainNative::LevelGetEnterPosition,self);
}
int Api200LevelGetNonCompleteRoomIndex(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kLevelMetatable,FieldReceipt::Level);
 return Invoke<std::int32_t>(L,Api200MainNative::LevelGetNonCompleteRoomIndex,self);
}
int Api200PathFinderEvadeTarget(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kPathFinderMetatable,FieldReceipt::PathFinder);
 const auto arg0=Vector(L,2);
 const auto arg1=lua_toboolean(L,3)!=0;
 return Invoke<void>(L,Api200MainNative::PathFinderEvadeTarget,self,&arg0,arg1);
}
int Api200PathFinderGetGridIndex(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kPathFinderMetatable,FieldReceipt::PathFinder);
 return Invoke<std::int32_t>(L,Api200MainNative::PathFinderGetGridIndex,self);
}
int Api200PathFinderMoveRandomly(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kPathFinderMetatable,FieldReceipt::PathFinder);
 const auto arg0=lua_toboolean(L,2)!=0;
 return Invoke<bool>(L,Api200MainNative::PathFinderMoveRandomly,self,arg0);
}
int Api200PathFinderMoveRandomlyAxisAligned(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kPathFinderMetatable,FieldReceipt::PathFinder);
 const auto arg0=Number(L,2);
 const auto arg1=lua_toboolean(L,3)!=0;
 return Invoke<void>(L,Api200MainNative::PathFinderMoveRandomlyAxisAligned,self,arg0,arg1);
}
int Api200PathFinderMoveRandomlyBoss(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kPathFinderMetatable,FieldReceipt::PathFinder);
 const auto arg0=lua_toboolean(L,2)!=0;
 return Invoke<void>(L,Api200MainNative::PathFinderMoveRandomlyBoss,self,arg0);
}
int Api200PathFinderReset(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kPathFinderMetatable,FieldReceipt::PathFinder);
 return Invoke<void>(L,Api200MainNative::PathFinderReset,self);
}
int Api200PathFinderResetMovementTarget(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kPathFinderMetatable,FieldReceipt::PathFinder);
 return Invoke<void>(L,Api200MainNative::PathFinderResetMovementTarget,self);
}
int Api200PathFinderUpdateGridIndex(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kPathFinderMetatable,FieldReceipt::PathFinder);
 return Invoke<void>(L,Api200MainNative::PathFinderUpdateGridIndex,self);
}
int Api200RoomCheckLine(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=Vector(L,2);
 const auto arg1=Vector(L,3);
 const auto arg2=Integer(L,4);
 const auto arg3=IntegerOr(L,5,0);
 const auto arg4=lua_toboolean(L,6)!=0;
 const auto arg5=lua_toboolean(L,7)!=0;
 Vec out{};const auto ok=Native<bool(*)(void*,const Vec*,const Vec*,std::int32_t,std::int32_t,bool,bool,Vec*)>(L,Api200MainNative::RoomCheckLine)(self,&arg0,&arg1,arg2,arg3,arg4,arg5,&out);lua_pushboolean(L,ok);PushLuaVector(L,out.x,out.y);return 2;
}
int Api200RoomGetClampedGridIndex(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=Vector(L,2);
 return Invoke<std::int32_t>(L,Api200MainNative::RoomGetClampedGridIndex,self,&arg0);
}
int Api200RoomGetLaserTarget(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=Vector(L,2);
 const auto arg1=Vector(L,3);
 return Invoke<Vec>(L,Api200MainNative::RoomGetLaserTarget,self,&arg0,&arg1);
}
int Api200RoomGetSeededCollectible(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=static_cast<std::uint32_t>(luaL_checkinteger(L,2));
 const auto arg1=lua_toboolean(L,3)!=0;
 return Invoke<std::int32_t>(L,Api200MainNative::RoomGetSeededCollectible,self,arg0,arg1);
}
int Api200RoomMamaMegaExplosion(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=Vector(L,2);
 return Invoke<void>(L,Api200MainNative::RoomMamaMegaExplosion,self,&arg0);
}
int Api200RoomTryMakeBridge(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=GridArg(L,2);
 const auto arg1=GridArg(L,3);
 return Invoke<bool>(L,Api200MainNative::RoomTryMakeBridge,self,arg0,arg1);
}
int Api200RoomTrySpawnDevilRoomDoor(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=lua_toboolean(L,2)!=0;
 const auto arg1=lua_toboolean(L,3)!=0;
 return Invoke<bool>(L,Api200MainNative::RoomTrySpawnDevilRoomDoor,self,arg0,arg1);
}
int Api200RoomTrySpawnSecretShop(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 const auto arg0=lua_toboolean(L,2)!=0;
 return Invoke<bool>(L,Api200MainNative::RoomTrySpawnSecretShop,self,arg0);
}
int Api200RoomTrySpawnSpecialQuestDoor(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kRoomMetatable,FieldReceipt::Room);
 return Invoke<bool>(L,Api200MainNative::RoomTrySpawnSpecialQuestDoor,self);
}
int Api200SeedsCanAddSeedEffect(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kSeedsMetatable,FieldReceipt::Seeds);
 const auto arg0=Integer(L,2);
 return Invoke<bool>(L,Api200MainNative::SeedsCanAddSeedEffect,self,arg0);
}
int Api200SeedsCountUnlockedSeedEffects(lua_State*L){
 return Invoke<std::int32_t>(L,Api200MainNative::SeedsCountUnlockedSeedEffects);
}
int Api200SeedsInitSeedInfo(lua_State*L){
 return Invoke<void>(L,Api200MainNative::SeedsInitSeedInfo);
}
int Api200SeedsRemoveBlockingSeedEffects(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kSeedsMetatable,FieldReceipt::Seeds);
 const auto arg0=Integer(L,2);
 return Invoke<void>(L,Api200MainNative::SeedsRemoveBlockingSeedEffects,self,arg0);
}
int Api200SeedsReset(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kSeedsMetatable,FieldReceipt::Seeds);
 return Invoke<void>(L,Api200MainNative::SeedsReset,self);
}
int Api200SeedsRestart(lua_State*L){
 auto*self=Receiver(L,LuaRuntime::kSeedsMetatable,FieldReceipt::Seeds);
 const auto arg0=Integer(L,2);
 return Invoke<void>(L,Api200MainNative::SeedsRestart,self,arg0);
}
int Api200SpriteSetOverlayAnimation(lua_State*L){
 auto*self=ResolveSpriteArgument(L,1);
 const auto arg0=luaL_checkstring(L,2);
 const auto arg1=!(lua_isboolean(L,3)&&!lua_toboolean(L,3));
 static_cast<void>(Native<bool(*)(void*,const char*,bool)>(L,Api200MainNative::SpriteSetOverlayAnimation)(self,arg0,arg1));return 0;
}
}
