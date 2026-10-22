#include "interfaces/lua/api400_entities.hpp"
#include "interfaces/lua/api400_entities.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_runtime.hpp"
#include "lua_object_handles.hpp"
#include <cstring>
extern "C" {
#include <lauxlib.h>
}
namespace isaac::runtime {
namespace {
namespace guard=api400_entities;
using Vec=LuaRuntime::VectorHandle;
using NativeId=Api400EntitiesNative;
constexpr api100_native::Entry kEntries[]={
{guard::kRenderGlowEntry,guard::kRenderGlowGuard.data()},
{guard::kKillUniqueEntry,guard::kKillUniqueGuard.data()},
{guard::kMakeChampionEntry,guard::kMakeChampionGuard.data()},
{guard::kMakeSplatEntry,guard::kMakeSplatGuard.data()},
{guard::kTryOpenChestEntry,guard::kTryOpenChestGuard.data()},
{guard::kOverlayEntry,guard::kOverlayGuard.data()},
{guard::kSetParentEntry,guard::kSetParentGuard.data()},
{guard::kResetMovementTargetEntry,guard::kResetMovementTargetGuard.data()},
{guard::kRenderTopEntry,guard::kRenderTopGuard.data()},
{guard::kShadowEntityEntry,guard::kShadowEntityGuard.data()},
{guard::kShadowEntity_NPCEntry,guard::kShadowEntity_NPCGuard.data()},
{guard::kShadowEntity_LaserEntry,guard::kShadowEntity_LaserGuard.data()},
{guard::kShadowEntity_PlayerEntry,guard::kShadowEntity_PlayerGuard.data()},
{guard::kShadowEntity_FamiliarEntry,guard::kShadowEntity_FamiliarGuard.data()},
{guard::kEntityLayoutEntry,guard::kEntityLayoutGuard.data()},
{guard::kConfigLayoutEntry,guard::kConfigLayoutGuard.data()},
{guard::kEffectLayoutEntry,guard::kEffectLayoutGuard.data()},
{guard::kEffectUpdateEntry,guard::kEffectUpdateGuard.data()},
{guard::kKnifeLayoutEntry,guard::kKnifeLayoutGuard.data()},
{guard::kKnifeUpdateEntry,guard::kKnifeUpdateGuard.data()},
{guard::kLaserLayoutEntry,guard::kLaserLayoutGuard.data()},
{guard::kLaserDamageEntry,guard::kLaserDamageGuard.data()},
{guard::kLaserUpdateEntry,guard::kLaserUpdateGuard.data()},
{guard::kLaserInitEntry,guard::kLaserInitGuard.data()},
{guard::kTearLayoutEntry,guard::kTearLayoutGuard.data()},
{guard::kTearUpdateEntry,guard::kTearUpdateGuard.data()},
{guard::kProjectileLayoutEntry,guard::kProjectileLayoutGuard.data()},
{guard::kProjectileUpdateEntry,guard::kProjectileUpdateGuard.data()},
{guard::kNpcLayoutEntry,guard::kNpcLayoutGuard.data()},
{guard::kTearHitLayoutEntry,guard::kTearHitLayoutGuard.data()},
};
api100_native::Cache g_Cache[static_cast<unsigned>(NativeId::Count)]{};
#if !defined(__SWITCH__)
Api400EntitiesNativeTestBindings g_Tests{};
#endif
template<class Fn>Fn Native(lua_State*L,NativeId id){const auto i=static_cast<unsigned>(id);std::uintptr_t host{};
#if !defined(__SWITCH__)
 host=g_Tests.methods[i];
#endif
 return engine_call::AsFunction<Fn>(api100_native::Resolve(L,kEntries[i],g_Cache[i],host));}
void Guard(lua_State*L,NativeId id){static_cast<void>(Native<void(*)()>(L,id));}
template<class T>__attribute__((noinline)) T Read(lua_State*L,std::uintptr_t p,std::uintptr_t offset){T value{};if(!engine_memory::ReadField(p,offset,&value,engine_memory::EngineMemoryReadable))luaL_error(L,"entity field is not readable");return value;}
template<class T>__attribute__((noinline)) void Write(lua_State*L,std::uintptr_t p,std::uintptr_t offset,const T&value){if(!engine_memory::WriteField(p,offset,value,engine_memory::EngineMemoryWritable))luaL_error(L,"entity field is not writable");}
__attribute__((noinline)) std::uintptr_t Self(lua_State*L,CallbackEntityClass family){const auto p=EntityPointerArgument(L,1);if(!p||(family!=CallbackEntityClass::None&&ClassifyCallbackEntity(p)!=family))luaL_error(L,"entity receiver expired or has the wrong family");return p;}
std::int32_t Int(lua_State*L,int i){const auto bits=static_cast<std::uint32_t>(luaL_checkinteger(L,i));std::int32_t value{};std::memcpy(&value,&bits,4);return value;}
float Number(lua_State*L,int i){return static_cast<float>(luaL_checknumber(L,i));}
void*Object(std::uintptr_t p){return engine_memory::AsObject(p);}
__attribute__((noinline)) std::uintptr_t FieldSelf(lua_State*L,CallbackEntityClass family,NativeId layout,NativeId consumer){const auto p=Self(L,family);Guard(L,layout);Guard(L,consumer);return p;}
int SetFloat(lua_State*L,CallbackEntityClass family,NativeId layout,NativeId consumer,std::uintptr_t offset){const auto p=FieldSelf(L,family,layout,consumer);const auto value=Number(L,2);Write(L,p,offset,value);return 0;}
int SetInt(lua_State*L,CallbackEntityClass family,NativeId layout,NativeId consumer,std::uintptr_t offset){const auto p=FieldSelf(L,family,layout,consumer);const auto value=Int(L,2);Write(L,p,offset,value);return 0;}
int SetBool(lua_State*L,CallbackEntityClass family,NativeId layout,NativeId consumer,std::uintptr_t offset){const auto p=FieldSelf(L,family,layout,consumer);const auto value=static_cast<std::uint8_t>(lua_toboolean(L,2));Write(L,p,offset,value);return 0;}
int AddFloat(lua_State*L,std::uintptr_t offset){const auto p=FieldSelf(L,CallbackEntityClass::Projectile,NativeId::ProjectileLayout,NativeId::ProjectileUpdate);const auto added=Number(L,2);Write(L,p,offset,Read<float>(L,p,offset)+added);return 0;}
int ProjectileFlags(lua_State*L,std::uintptr_t offset,bool clear){const auto p=FieldSelf(L,CallbackEntityClass::Projectile,NativeId::ProjectileLayout,NativeId::ProjectileUpdate);const auto mask=static_cast<std::uint64_t>(luaL_checkinteger(L,2));const auto before=Read<std::uint64_t>(L,p,offset);Write(L,p,offset,clear?(before&~mask):(before|mask));return 0;}
int EntityResult(lua_State*L,void*p){if(p)PushEntityCallbackArgument(L,engine_memory::AddressOf(p));else lua_pushnil(L);return 1;}
}
#if !defined(__SWITCH__)
void SetApi400EntitiesNativeTestBindings(Api400EntitiesNativeTestBindings value) noexcept{g_Tests=value;}
#endif
int Api400EntityPlayerRenderGlow(lua_State*L){const auto p=Self(L,CallbackEntityClass::Player);const auto v=*RequireVectorArgument(L,2);Native<void(*)(void*,const Vec&)>(L,NativeId::RenderGlow)(Object(p),v);return 0;}
int Api400EntityPlayerRenderTop(lua_State*L){const auto p=Self(L,CallbackEntityClass::Player);const auto v=*RequireVectorArgument(L,2);Native<void(*)(void*,const Vec&)>(L,NativeId::RenderTop)(Object(p),v);return 0;}
int Api400EntityNPCKillUnique(lua_State*L){const auto p=Self(L,CallbackEntityClass::Npc);Native<void(*)(void*)>(L,NativeId::KillUnique)(Object(p));return 0;}
int Api400EntityNPCMakeChampion(lua_State*L){const auto p=Self(L,CallbackEntityClass::Npc);const auto seed=static_cast<std::uint32_t>(luaL_checkinteger(L,2));const auto color=lua_toboolean(L,3)?Int(L,3):-1;const auto init=lua_toboolean(L,4)!=0;Native<void(*)(void*,std::uint32_t,std::int32_t,bool)>(L,NativeId::MakeChampion)(Object(p),seed,color,init);return 0;}
int Api400EntityNPCMakeSplat(lua_State*L){const auto p=Self(L,CallbackEntityClass::Npc);const auto size=Number(L,2);return EntityResult(L,Native<void*(*)(void*,float)>(L,NativeId::MakeSplat)(Object(p),size));}
int Api400EntityPickupTryOpenChest(lua_State*L){const auto p=Self(L,CallbackEntityClass::Pickup);std::uintptr_t player{};if(!lua_isnoneornil(L,2)){player=EntityPointerArgument(L,2);if(!player||ClassifyCallbackEntity(player)!=CallbackEntityClass::Player)return luaL_argerror(L,2,"live EntityPlayer or nil expected");}lua_pushboolean(L,Native<bool(*)(void*,void*)>(L,NativeId::TryOpenChest)(Object(p),Object(player)));return 1;}
int Api400EntityGetBossID(lua_State*L){const auto p=FieldSelf(L,CallbackEntityClass::None,NativeId::EntityLayout,NativeId::ConfigLayout);const auto config=Read<std::uintptr_t>(L,p,0x300);lua_pushinteger(L,Read<std::int32_t>(L,config,0x34));return 1;}
int Api400EntitySetSpriteOverlayFrame(lua_State*L){const auto p=Self(L,CallbackEntityClass::None);const auto*name=luaL_checkstring(L,2);const auto frame=Int(L,3);Native<void(*)(void*,const char*,std::int32_t)>(L,NativeId::Overlay)(Object(p+0x50),name,frame);return 0;}
int Api400EntityEffectFollowParent(lua_State*L){const auto p=FieldSelf(L,CallbackEntityClass::Effect,NativeId::EffectLayout,NativeId::EffectUpdate);const auto parent=EntityPointerArgument(L,2);if(!parent)return luaL_argerror(L,2,"live Entity expected");const auto position=Read<Vec>(L,p,0x310),origin=Read<Vec>(L,parent,0x310);auto set=Native<void(*)(void*,void*)>(L,NativeId::SetParent);set(Object(p),Object(parent));Write(L,p,0x45c,std::uint8_t{1});Write(L,p,0x460,Vec{position.x-origin.x,position.y-origin.y});return 0;}
int Api400EntityEffectSetDamageSource(lua_State*L){return SetInt(L,CallbackEntityClass::Effect,NativeId::EffectLayout,NativeId::EffectUpdate,0x468);}
int Api400EntityEffectSetRadii(lua_State*L){const auto p=FieldSelf(L,CallbackEntityClass::Effect,NativeId::EffectLayout,NativeId::EffectUpdate);const auto minimum=Number(L,2),maximum=Number(L,3);Write(L,p,0x44c,Vec{minimum,maximum});return 0;}
int Api400EntityEffectSetTimeout(lua_State*L){const auto p=FieldSelf(L,CallbackEntityClass::Effect,NativeId::EffectLayout,NativeId::EffectUpdate);const auto timeout=Int(L,2);Write(L,p,0x454,timeout);Write(L,p,0x458,timeout);return 0;}
int Api400EntityKnifeGetKnifeDistance(lua_State*L){const auto p=FieldSelf(L,CallbackEntityClass::Knife,NativeId::KnifeLayout,NativeId::KnifeUpdate);lua_pushnumber(L,Read<float>(L,p,0x434));return 1;}
int Api400EntityKnifeGetKnifeVelocity(lua_State*L){const auto p=FieldSelf(L,CallbackEntityClass::Knife,NativeId::KnifeLayout,NativeId::KnifeUpdate);lua_pushnumber(L,Read<float>(L,p,0x438));return 1;}
int Api400EntityKnifeSetPathFollowSpeed(lua_State*L){return SetFloat(L,CallbackEntityClass::Knife,NativeId::KnifeLayout,NativeId::KnifeUpdate,0x4ec);}
int Api400EntityLaserGetEndPoint(lua_State*L){const auto p=FieldSelf(L,CallbackEntityClass::Laser,NativeId::LaserLayout,NativeId::LaserInit);PushEntityVectorReference(L,p,0x500);return 1;}
int Api400EntityLaserIsCircleLaser(lua_State*L){const auto p=FieldSelf(L,CallbackEntityClass::Laser,NativeId::LaserLayout,NativeId::LaserInit);const auto subtype=Read<std::uint32_t>(L,p,0x40);lua_pushboolean(L,subtype>=1&&subtype<=3);return 1;}
int Api400EntityLaserIsSampleLaser(lua_State*L){const auto p=FieldSelf(L,CallbackEntityClass::Laser,NativeId::LaserLayout,NativeId::LaserInit);lua_pushboolean(L,Read<std::uint8_t>(L,p,0x44d)!=0);return 1;}
int Api400EntityLaserSetBlackHpDropChance(lua_State*L){return SetFloat(L,CallbackEntityClass::Laser,NativeId::LaserLayout,NativeId::LaserDamage,0x524);}
int Api400EntityLaserSetHomingType(lua_State*L){return SetInt(L,CallbackEntityClass::Laser,NativeId::LaserLayout,NativeId::LaserUpdate,0x4fc);}
int Api400EntityLaserSetMultidimensionalTouched(lua_State*L){return SetBool(L,CallbackEntityClass::Laser,NativeId::LaserLayout,NativeId::LaserUpdate,0x538);}
int Api400EntityLaserSetOneHit(lua_State*L){return SetBool(L,CallbackEntityClass::Laser,NativeId::LaserLayout,NativeId::LaserUpdate,0x561);}
int Api400EntityLaserSetTimeout(lua_State*L){return SetInt(L,CallbackEntityClass::Laser,NativeId::LaserLayout,NativeId::LaserUpdate,0x448);}
int Api400EntityNPCResetPathFinderTarget(lua_State*L){const auto p=Self(L,CallbackEntityClass::Npc);Guard(L,NativeId::NpcLayout);Native<void(*)(void*)>(L,NativeId::ResetMovementTarget)(Object(p+0x408));return 0;}
int Api400EntityRenderShadowLayer(lua_State*L){const auto p=Self(L,CallbackEntityClass::None);const auto v=*RequireVectorArgument(L,2);const auto vptr=Read<std::uintptr_t>(L,p,0);const auto target=Read<std::uintptr_t>(L,vptr,7*8);const auto base=LuaRuntime::EngineModuleBase();NativeId id=NativeId::Count;for(unsigned i=static_cast<unsigned>(NativeId::ShadowEntity);i<=static_cast<unsigned>(NativeId::ShadowEntity_Familiar);++i){if(base<=UINTPTR_MAX-kEntries[i].offset&&target==base+kEntries[i].offset){id=static_cast<NativeId>(i);break;}}if(id==NativeId::Count)return luaL_error(L,"RenderShadowLayer virtual target unavailable");lua_pushboolean(L,Native<bool(*)(void*,const Vec&)>(L,id)(Object(p),v));return 1;}
int Api400EntityProjectileAddChangeFlags(lua_State*L){return ProjectileFlags(L,0x438,false);}
int Api400EntityProjectileAddFallingAccel(lua_State*L){return AddFloat(L,0x408);}
int Api400EntityProjectileAddFallingSpeed(lua_State*L){return AddFloat(L,0x404);}
int Api400EntityProjectileAddHeight(lua_State*L){return AddFloat(L,0x400);}
int Api400EntityProjectileAddProjectileFlags(lua_State*L){return ProjectileFlags(L,0x428,false);}
int Api400EntityProjectileAddScale(lua_State*L){return AddFloat(L,0x410);}
int Api400EntityProjectileClearProjectileFlags(lua_State*L){return ProjectileFlags(L,0x428,true);}
int Api400EntityTearSetKnockbackMultiplier(lua_State*L){return SetFloat(L,CallbackEntityClass::Tear,NativeId::TearLayout,NativeId::TearHitLayout,0x460);}
int Api400EntityTearSetParentOffset(lua_State*L){const auto p=FieldSelf(L,CallbackEntityClass::Tear,NativeId::TearLayout,NativeId::TearUpdate);const auto v=*RequireVectorArgument(L,2);Write(L,p,0x8ec,v);return 0;}
int Api400EntityTearSetWaitFrames(lua_State*L){return SetInt(L,CallbackEntityClass::Tear,NativeId::TearLayout,NativeId::TearUpdate,0x428);}
}
