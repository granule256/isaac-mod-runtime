"""第四批实体35项真实Lua消费与寿命/guard行为。"""
import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
ROOT=Path(__file__).resolve().parents[2]
BASELINE_MAIN='\nextern "C" {\n#include <lauxlib.h>\n#include <lualib.h>\n}\nusing namespace isaac::runtime;\nint main(){\n static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);\n CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);\n WriteWord(g_Entities[kTearNear],0,g_EngineBase+kEntityTearVtableOffset);\n WriteWord(g_Entities[kBullet],0,g_EngineBase+kEntityProjectileVtableOffset);\n FillEntity(kNoQuery,7,0,0,0,0,0,0,0,g_EngineBase+kEntityLaserVtableOffset,0);\n FillEntity(kSizeOnly,8,0,0,0,0,0,0,0,g_EngineBase+kEntityKnifeVtableOffset,0);\n LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);\n auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));\n const EntitySlot slots[]={kPlayer,kEnemyA,kPickup,kEffect,kSizeOnly,kNoQuery,kBullet,kTearNear};\n const char*names[]={"p","npc","pickup","effect","knife","laser","projectile","tear"};\n for(unsigned i=0;i<8;++i){PushEntityCallbackArgument(L,AddressOf(g_Entities[slots[i]]));lua_setglobal(L,names[i]);}\n if(luaL_dostring(L,R"lua(assert(type(p.RenderGlow)==\'function\',"missing EntityPlayer:RenderGlow");assert(type(npc.KillUnique)==\'function\',"missing EntityNPC:KillUnique");assert(type(npc.MakeChampion)==\'function\',"missing EntityNPC:MakeChampion");assert(type(npc.MakeSplat)==\'function\',"missing EntityNPC:MakeSplat");assert(type(pickup.TryOpenChest)==\'function\',"missing EntityPickup:TryOpenChest");assert(type(npc.GetBossID)==\'function\',"missing Entity:GetBossID");assert(type(npc.SetSpriteOverlayFrame)==\'function\',"missing Entity:SetSpriteOverlayFrame");assert(type(effect.FollowParent)==\'function\',"missing EntityEffect:FollowParent");assert(type(effect.SetDamageSource)==\'function\',"missing EntityEffect:SetDamageSource");assert(type(effect.SetRadii)==\'function\',"missing EntityEffect:SetRadii");assert(type(effect.SetTimeout)==\'function\',"missing EntityEffect:SetTimeout");assert(type(knife.GetKnifeDistance)==\'function\',"missing EntityKnife:GetKnifeDistance");assert(type(knife.GetKnifeVelocity)==\'function\',"missing EntityKnife:GetKnifeVelocity");assert(type(knife.SetPathFollowSpeed)==\'function\',"missing EntityKnife:SetPathFollowSpeed");assert(type(laser.GetEndPoint)==\'function\',"missing EntityLaser:GetEndPoint");assert(type(laser.IsCircleLaser)==\'function\',"missing EntityLaser:IsCircleLaser");assert(type(laser.IsSampleLaser)==\'function\',"missing EntityLaser:IsSampleLaser");assert(type(laser.SetBlackHpDropChance)==\'function\',"missing EntityLaser:SetBlackHpDropChance");assert(type(laser.SetHomingType)==\'function\',"missing EntityLaser:SetHomingType");assert(type(laser.SetMultidimensionalTouched)==\'function\',"missing EntityLaser:SetMultidimensionalTouched");assert(type(laser.SetOneHit)==\'function\',"missing EntityLaser:SetOneHit");assert(type(laser.SetTimeout)==\'function\',"missing EntityLaser:SetTimeout");assert(type(npc.ResetPathFinderTarget)==\'function\',"missing EntityNPC:ResetPathFinderTarget");assert(type(p.RenderTop)==\'function\',"missing EntityPlayer:RenderTop");assert(type(npc.RenderShadowLayer)==\'function\',"missing Entity:RenderShadowLayer");assert(type(projectile.AddChangeFlags)==\'function\',"missing EntityProjectile:AddChangeFlags");assert(type(projectile.AddFallingAccel)==\'function\',"missing EntityProjectile:AddFallingAccel");assert(type(projectile.AddFallingSpeed)==\'function\',"missing EntityProjectile:AddFallingSpeed");assert(type(projectile.AddHeight)==\'function\',"missing EntityProjectile:AddHeight");assert(type(projectile.AddProjectileFlags)==\'function\',"missing EntityProjectile:AddProjectileFlags");assert(type(projectile.AddScale)==\'function\',"missing EntityProjectile:AddScale");assert(type(projectile.ClearProjectileFlags)==\'function\',"missing EntityProjectile:ClearProjectileFlags");assert(type(tear.SetKnockbackMultiplier)==\'function\',"missing EntityTear:SetKnockbackMultiplier");assert(type(tear.SetParentOffset)==\'function\',"missing EntityTear:SetParentOffset");assert(type(tear.SetWaitFrames)==\'function\',"missing EntityTear:SetWaitFrames"))lua")){std::fprintf(stderr,"%s\\n",lua_tostring(L,-1));return 1;}lua_close(L);return 0;\n}\n'
MAIN=r'''

#include "interfaces/lua/api400_entities.hpp"
#include "interfaces/lua/api400_entities.guards.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/rplus_extended_fields_guards.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;using Vec=LuaRuntime::VectorHandle;using NI=Api400EntitiesNative;
static unsigned calls[14]{};static bool nullSplat{};
static void Glow(void*p,const Vec&v){assert(p==g_Entities[kPlayer].data()&&v.x==3&&v.y==4);++calls[0];}
static void Kill(void*p){assert(p==g_Entities[kEnemyA].data());++calls[1];WriteAt<std::int32_t>(g_Entities[kEnemyA],0xb70,17);WriteAt<std::int32_t>(g_Entities[kEnemyA],0x400,0);}
static void Champion(void*p,std::uint32_t seed,std::int32_t color,bool init){assert(p==g_Entities[kEnemyA].data());++calls[2];assert(seed==0xffffffffU||seed==7);if(seed==0xffffffffU){assert(color==-1&&!init);}else assert(color==4&&init);WriteAt<std::int32_t>(g_Entities[kEnemyA],0xcc0,color);}
static void*Splat(void*p,float size){assert(p==g_Entities[kEnemyA].data()&&size==2.5);++calls[3];return nullSplat?nullptr:g_Entities[kEffect].data();}
static bool Chest(void*p,void*player){assert(p==g_Entities[kPickup].data());assert(!player||player==g_Entities[kPlayer].data());++calls[4];return !player;}
static void Overlay(void*p,const char*name,std::int32_t frame){assert(p==g_Entities[kEnemyA].data()+0x50);assert(std::strcmp(name,"Overlay")==0&&frame==-7);++calls[5];}
static void Parent(void*p,void*parent){assert(p==g_Entities[kEffect].data()&&parent==g_Entities[kEnemyA].data());++calls[6];WriteWord(g_Entities[kEffect],0x390,AddressOf(g_Entities[kEnemyA]));}
static void Reset(void*p){assert(p==g_Entities[kEnemyA].data()+0x408);++calls[7];WriteAt<Vec>(g_Entities[kEnemyA],0x410,Vec{0,0});WriteAt<Vec>(g_Entities[kEnemyA],0x418,Vec{0,0});}
static void Top(void*p,const Vec&v){assert(p==g_Entities[kPlayer].data()&&v.x==3&&v.y==4);++calls[8];}
static bool Shadow(void*p,const Vec&v){assert(p&&v.x==3&&v.y==4);++calls[9];return p==g_Entities[kEnemyA].data();}
template<class T>T Field(EntitySlot s,std::size_t o){T v{};std::memcpy(&v,g_Entities[s].data()+o,sizeof(v));return v;}
static int Run(lua_State*L,const char*script){if(luaL_dostring(L,script)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}return 0;}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;const std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 WriteWord(g_Entities[kEffect],0,g_EngineBase+kEntityEffectVtableOffset);WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);
 WriteWord(g_Entities[kTearNear],0,g_EngineBase+kEntityTearVtableOffset);WriteWord(g_Entities[kBullet],0,g_EngineBase+kEntityProjectileVtableOffset);
 FillEntity(kNoQuery,7,0,2,0,0,0,0,0,g_EngineBase+kEntityLaserVtableOffset,0);FillEntity(kSizeOnly,8,0,0,0,0,0,0,0,g_EngineBase+kEntityKnifeVtableOffset,0);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 namespace G=api400_entities;
 std::memcpy(g_ModuleBytes.data()+extended_fields::kTear0Entry,extended_fields::kTear0Guard.data(),extended_fields::kTear0Guard.size());
 std::memcpy(g_ModuleBytes.data()+extended_fields::kTear1Entry,extended_fields::kTear1Guard.data(),extended_fields::kTear1Guard.size());
 std::memcpy(g_ModuleBytes.data()+extended_fields::kTear2Entry,extended_fields::kTear2Guard.data(),extended_fields::kTear2Guard.size());
 std::memcpy(g_ModuleBytes.data()+G::kRenderGlowEntry,G::kRenderGlowGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kKillUniqueEntry,G::kKillUniqueGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kMakeChampionEntry,G::kMakeChampionGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kMakeSplatEntry,G::kMakeSplatGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kTryOpenChestEntry,G::kTryOpenChestGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kOverlayEntry,G::kOverlayGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kSetParentEntry,G::kSetParentGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kResetMovementTargetEntry,G::kResetMovementTargetGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kRenderTopEntry,G::kRenderTopGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kShadowEntityEntry,G::kShadowEntityGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kShadowEntity_NPCEntry,G::kShadowEntity_NPCGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kShadowEntity_LaserEntry,G::kShadowEntity_LaserGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kShadowEntity_PlayerEntry,G::kShadowEntity_PlayerGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kShadowEntity_FamiliarEntry,G::kShadowEntity_FamiliarGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kEntityLayoutEntry,G::kEntityLayoutGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kConfigLayoutEntry,G::kConfigLayoutGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kEffectLayoutEntry,G::kEffectLayoutGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kEffectUpdateEntry,G::kEffectUpdateGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kKnifeLayoutEntry,G::kKnifeLayoutGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kKnifeUpdateEntry,G::kKnifeUpdateGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kLaserLayoutEntry,G::kLaserLayoutGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kLaserDamageEntry,G::kLaserDamageGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kLaserUpdateEntry,G::kLaserUpdateGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kLaserInitEntry,G::kLaserInitGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kTearLayoutEntry,G::kTearLayoutGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kTearUpdateEntry,G::kTearUpdateGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kProjectileLayoutEntry,G::kProjectileLayoutGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kProjectileUpdateEntry,G::kProjectileUpdateGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kNpcLayoutEntry,G::kNpcLayoutGuard.data(),16);
std::memcpy(g_ModuleBytes.data()+G::kTearHitLayoutEntry,G::kTearHitLayoutGuard.data(),16);
 Api400EntitiesNativeTestBindings bindings{};
 bindings.methods[static_cast<unsigned>(NI::RenderGlow)]=engine_call::AddressOfFunction(&Glow);
bindings.methods[static_cast<unsigned>(NI::KillUnique)]=engine_call::AddressOfFunction(&Kill);
bindings.methods[static_cast<unsigned>(NI::MakeChampion)]=engine_call::AddressOfFunction(&Champion);
bindings.methods[static_cast<unsigned>(NI::MakeSplat)]=engine_call::AddressOfFunction(&Splat);
bindings.methods[static_cast<unsigned>(NI::TryOpenChest)]=engine_call::AddressOfFunction(&Chest);
bindings.methods[static_cast<unsigned>(NI::Overlay)]=engine_call::AddressOfFunction(&Overlay);
bindings.methods[static_cast<unsigned>(NI::SetParent)]=engine_call::AddressOfFunction(&Parent);
bindings.methods[static_cast<unsigned>(NI::ResetMovementTarget)]=engine_call::AddressOfFunction(&Reset);
bindings.methods[static_cast<unsigned>(NI::RenderTop)]=engine_call::AddressOfFunction(&Top);
bindings.methods[static_cast<unsigned>(NI::ShadowEntity)]=engine_call::AddressOfFunction(&Shadow);
bindings.methods[static_cast<unsigned>(NI::ShadowEntity_NPC)]=engine_call::AddressOfFunction(&Shadow);
bindings.methods[static_cast<unsigned>(NI::ShadowEntity_Laser)]=engine_call::AddressOfFunction(&Shadow);
bindings.methods[static_cast<unsigned>(NI::ShadowEntity_Player)]=engine_call::AddressOfFunction(&Shadow);
bindings.methods[static_cast<unsigned>(NI::ShadowEntity_Familiar)]=engine_call::AddressOfFunction(&Shadow);
 SetApi400EntitiesNativeTestBindings(bindings);
 // 原生vtable槽7必须真正读到本类入口；测试替身仅在真实guard之后可选。
 const EntitySlot shadows[]={kEnemyA,kPlayer,kEffect,kSizeOnly,kNoQuery,kTearNear,kBullet,kFamiliar};
 const std::uintptr_t targets[]={G::kShadowEntity_NPCEntry,G::kShadowEntity_PlayerEntry,G::kShadowEntityEntry,G::kShadowEntityEntry,G::kShadowEntity_LaserEntry,G::kShadowEntityEntry,G::kShadowEntityEntry,G::kShadowEntity_FamiliarEntry};
 for(unsigned i=0;i<8;++i){auto vptr=Field<std::uintptr_t>(shadows[i],0);std::uintptr_t target=g_EngineBase+targets[i];std::memcpy(engine_memory::AsObject(vptr+56),&target,8);}
 std::vector<unsigned char>config(0x180,0);WriteWord(g_Entities[kEnemyA],0x300,AddressOf(config));WriteAt<std::int32_t>(config,0x34,-37);WriteAt<std::int32_t>(config,0x30,91);
 WriteAt<Vec>(g_Entities[kEffect],0x310,Vec{10,20});WriteAt<Vec>(g_Entities[kEnemyA],0x310,Vec{3,5});
 WriteAt<float>(g_Entities[kSizeOnly],0x434,7.5);WriteAt<float>(g_Entities[kSizeOnly],0x438,-8.25);WriteAt<Vec>(g_Entities[kNoQuery],0x500,Vec{13,14});WriteAt<std::uint8_t>(g_Entities[kNoQuery],0x44d,255);
 WriteAt<std::uint64_t>(g_Entities[kBullet],0x428,1);WriteAt<std::uint64_t>(g_Entities[kBullet],0x438,1);
 WriteAt<float>(g_Entities[kBullet],0x400,-10);WriteAt<float>(g_Entities[kBullet],0x404,3);WriteAt<float>(g_Entities[kBullet],0x408,0.25);WriteAt<float>(g_Entities[kBullet],0x410,2);
 WriteAt<float>(g_Entities[kTearNear],0x454,91.75);WriteAt<float>(g_Entities[kTearNear],0x45c,92.75);WriteAt<float>(g_Entities[kTearNear],0x464,93.75);
 WriteAt<Vec>(g_Entities[kEnemyA],0x410,Vec{11,12});WriteAt<Vec>(g_Entities[kEnemyA],0x418,Vec{13,14});
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));
 RegisterVectorReferenceMetatable(L);luaL_newmetatable(L,LuaRuntime::kVectorMetatable);lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,VectorNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachVectorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");
 luaL_getmetatable(L,LuaRuntime::kEntityPlayerMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityPlayerRenderGlow);lua_setfield(L,-2,"RenderGlow");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityNPCMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityNPCKillUnique);lua_setfield(L,-2,"KillUnique");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityNPCMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityNPCMakeChampion);lua_setfield(L,-2,"MakeChampion");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityNPCMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityNPCMakeSplat);lua_setfield(L,-2,"MakeSplat");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityPickupMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityPickupTryOpenChest);lua_setfield(L,-2,"TryOpenChest");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityGetBossID);lua_setfield(L,-2,"GetBossID");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntitySetSpriteOverlayFrame);lua_setfield(L,-2,"SetSpriteOverlayFrame");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityEffectFollowParent);lua_setfield(L,-2,"FollowParent");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityEffectSetDamageSource);lua_setfield(L,-2,"SetDamageSource");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityEffectSetRadii);lua_setfield(L,-2,"SetRadii");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityEffectSetTimeout);lua_setfield(L,-2,"SetTimeout");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityKnifeMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityKnifeGetKnifeDistance);lua_setfield(L,-2,"GetKnifeDistance");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityKnifeMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityKnifeGetKnifeVelocity);lua_setfield(L,-2,"GetKnifeVelocity");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityKnifeMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityKnifeSetPathFollowSpeed);lua_setfield(L,-2,"SetPathFollowSpeed");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityLaserMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityLaserGetEndPoint);lua_setfield(L,-2,"GetEndPoint");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityLaserMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityLaserIsCircleLaser);lua_setfield(L,-2,"IsCircleLaser");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityLaserMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityLaserIsSampleLaser);lua_setfield(L,-2,"IsSampleLaser");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityLaserMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityLaserSetBlackHpDropChance);lua_setfield(L,-2,"SetBlackHpDropChance");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityLaserMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityLaserSetHomingType);lua_setfield(L,-2,"SetHomingType");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityLaserMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityLaserSetMultidimensionalTouched);lua_setfield(L,-2,"SetMultidimensionalTouched");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityLaserMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityLaserSetOneHit);lua_setfield(L,-2,"SetOneHit");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityLaserMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityLaserSetTimeout);lua_setfield(L,-2,"SetTimeout");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityNPCMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityNPCResetPathFinderTarget);lua_setfield(L,-2,"ResetPathFinderTarget");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityPlayerMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityPlayerRenderTop);lua_setfield(L,-2,"RenderTop");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityRenderShadowLayer);lua_setfield(L,-2,"RenderShadowLayer");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityProjectileMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityProjectileAddChangeFlags);lua_setfield(L,-2,"AddChangeFlags");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityProjectileMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityProjectileAddFallingAccel);lua_setfield(L,-2,"AddFallingAccel");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityProjectileMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityProjectileAddFallingSpeed);lua_setfield(L,-2,"AddFallingSpeed");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityProjectileMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityProjectileAddHeight);lua_setfield(L,-2,"AddHeight");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityProjectileMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityProjectileAddProjectileFlags);lua_setfield(L,-2,"AddProjectileFlags");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityProjectileMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityProjectileAddScale);lua_setfield(L,-2,"AddScale");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityProjectileMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityProjectileClearProjectileFlags);lua_setfield(L,-2,"ClearProjectileFlags");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityTearMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityTearSetKnockbackMultiplier);lua_setfield(L,-2,"SetKnockbackMultiplier");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityTearMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityTearSetParentOffset);lua_setfield(L,-2,"SetParentOffset");lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityTearMetatable);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,Api400EntityTearSetWaitFrames);lua_setfield(L,-2,"SetWaitFrames");lua_pop(L,2);
 const EntitySlot slots[]={kPlayer,kEnemyA,kPickup,kEffect,kSizeOnly,kNoQuery,kBullet,kTearNear};const char*names[]={"p","npc","pickup","effect","knife","laser","projectile","tear"};
 auto publish=[&](){for(unsigned i=0;i<8;++i){PushEntityCallbackArgument(L,AddressOf(g_Entities[slots[i]]));lua_setglobal(L,names[i]);}};publish();
 if(scene=="badguard"){
 g_ModuleBytes[G::kRenderGlowEntry]^=1;
g_ModuleBytes[G::kKillUniqueEntry]^=1;
g_ModuleBytes[G::kMakeChampionEntry]^=1;
g_ModuleBytes[G::kMakeSplatEntry]^=1;
g_ModuleBytes[G::kTryOpenChestEntry]^=1;
g_ModuleBytes[G::kOverlayEntry]^=1;
g_ModuleBytes[G::kSetParentEntry]^=1;
g_ModuleBytes[G::kResetMovementTargetEntry]^=1;
g_ModuleBytes[G::kRenderTopEntry]^=1;
g_ModuleBytes[G::kShadowEntityEntry]^=1;
g_ModuleBytes[G::kShadowEntity_NPCEntry]^=1;
g_ModuleBytes[G::kShadowEntity_LaserEntry]^=1;
g_ModuleBytes[G::kShadowEntity_PlayerEntry]^=1;
g_ModuleBytes[G::kShadowEntity_FamiliarEntry]^=1;
g_ModuleBytes[G::kEntityLayoutEntry]^=1;
g_ModuleBytes[G::kConfigLayoutEntry]^=1;
g_ModuleBytes[G::kEffectLayoutEntry]^=1;
g_ModuleBytes[G::kEffectUpdateEntry]^=1;
g_ModuleBytes[G::kKnifeLayoutEntry]^=1;
g_ModuleBytes[G::kKnifeUpdateEntry]^=1;
g_ModuleBytes[G::kLaserLayoutEntry]^=1;
g_ModuleBytes[G::kLaserDamageEntry]^=1;
g_ModuleBytes[G::kLaserUpdateEntry]^=1;
g_ModuleBytes[G::kLaserInitEntry]^=1;
g_ModuleBytes[G::kTearLayoutEntry]^=1;
g_ModuleBytes[G::kTearUpdateEntry]^=1;
g_ModuleBytes[G::kProjectileLayoutEntry]^=1;
g_ModuleBytes[G::kProjectileUpdateEntry]^=1;
g_ModuleBytes[G::kNpcLayoutEntry]^=1;
g_ModuleBytes[G::kTearHitLayoutEntry]^=1;
 if(Run(L,R"lua(local function guarded(f)local ok,err=pcall(f);assert(not ok and string.find(err,'guard'),tostring(err))end;guarded(function()p:RenderGlow(Vector(3,4))end);guarded(function()npc:KillUnique()end);guarded(function()npc:MakeChampion(0xffffffff)end);guarded(function()npc:MakeSplat(2.5)end);guarded(function()pickup:TryOpenChest(nil)end);guarded(function()npc:GetBossID()end);guarded(function()npc:SetSpriteOverlayFrame('Overlay',-7)end);guarded(function()effect:FollowParent(npc)end);guarded(function()effect:SetDamageSource(-9)end);guarded(function()effect:SetRadii(12.5,-2.5)end);guarded(function()effect:SetTimeout(-19)end);guarded(function()knife:GetKnifeDistance()end);guarded(function()knife:GetKnifeVelocity()end);guarded(function()knife:SetPathFollowSpeed(3.25)end);guarded(function()laser:GetEndPoint()end);guarded(function()laser:IsCircleLaser()end);guarded(function()laser:IsSampleLaser()end);guarded(function()laser:SetBlackHpDropChance(0.375)end);guarded(function()laser:SetHomingType(-17)end);guarded(function()laser:SetMultidimensionalTouched(true)end);guarded(function()laser:SetOneHit(true)end);guarded(function()laser:SetTimeout(-23)end);guarded(function()npc:ResetPathFinderTarget()end);guarded(function()p:RenderTop(Vector(3,4))end);guarded(function()npc:RenderShadowLayer(Vector(3,4))end);guarded(function()projectile:AddChangeFlags(0x8000000000000002)end);guarded(function()projectile:AddFallingAccel(0.5)end);guarded(function()projectile:AddFallingSpeed(-2.5)end);guarded(function()projectile:AddHeight(3.25)end);guarded(function()projectile:AddProjectileFlags(0x8000000000000002)end);guarded(function()projectile:AddScale(1.5)end);guarded(function()projectile:ClearProjectileFlags(1)end);guarded(function()tear:SetKnockbackMultiplier(1.25)end);guarded(function()tear:SetParentOffset(Vector(5,6))end);guarded(function()tear:SetWaitFrames(-29)end))lua"))return 2;for(auto n:calls)assert(n==0);lua_close(L);return 0;}
 if(Run(L,R"lua(assert(select('#',p:RenderGlow(Vector(3,4)))==0)
assert(select('#',npc:KillUnique())==0)
assert(select('#',npc:MakeChampion(0xffffffff))==0)
splat=npc:MakeSplat(2.5);assert(splat:ToEffect() and GetPtrHash(splat)==GetPtrHash(effect))
assert(pickup:TryOpenChest())
assert(npc:GetBossID()==-37)
assert(select('#',npc:SetSpriteOverlayFrame('Overlay',-7))==0)
assert(select('#',effect:FollowParent(npc))==0)
assert(select('#',effect:SetDamageSource(-9))==0)
assert(select('#',effect:SetRadii(12.5,-2.5))==0)
assert(select('#',effect:SetTimeout(-19))==0)
assert(knife:GetKnifeDistance()==7.5)
assert(knife:GetKnifeVelocity()==-8.25)
assert(select('#',knife:SetPathFollowSpeed(3.25))==0)
endpoint=laser:GetEndPoint();assert(endpoint.X==13 and endpoint.Y==14)
assert(laser:IsCircleLaser())
assert(laser:IsSampleLaser())
assert(select('#',laser:SetBlackHpDropChance(0.375))==0)
assert(select('#',laser:SetHomingType(-17))==0)
assert(select('#',laser:SetMultidimensionalTouched(true))==0)
assert(select('#',laser:SetOneHit(true))==0)
assert(select('#',laser:SetTimeout(-23))==0)
assert(select('#',npc:ResetPathFinderTarget())==0)
assert(select('#',p:RenderTop(Vector(3,4)))==0)
assert(npc:RenderShadowLayer(Vector(3,4)))
assert(select('#',projectile:AddChangeFlags(0x8000000000000002))==0)
assert(select('#',projectile:AddFallingAccel(0.5))==0)
assert(select('#',projectile:AddFallingSpeed(-2.5))==0)
assert(select('#',projectile:AddHeight(3.25))==0)
assert(select('#',projectile:AddProjectileFlags(0x8000000000000002))==0)
assert(select('#',projectile:AddScale(1.5))==0)
assert(select('#',projectile:ClearProjectileFlags(1))==0)
assert(select('#',tear:SetKnockbackMultiplier(1.25))==0)
assert(select('#',tear:SetParentOffset(Vector(5,6)))==0)
assert(select('#',tear:SetWaitFrames(-29))==0))lua"))return 3;
 assert(Field<std::int32_t>(kEnemyA,0xb70)==17&&Field<std::int32_t>(kEnemyA,0x400)==0&&Field<std::int32_t>(kEnemyA,0xcc0)==-1);
 assert(Field<std::uintptr_t>(kEffect,0x390)==AddressOf(g_Entities[kEnemyA]));assert(Field<std::uint8_t>(kEffect,0x45c)==1);assert(Field<Vec>(kEffect,0x460).x==7&&Field<Vec>(kEffect,0x460).y==15);
 assert(Field<std::int32_t>(kEffect,0x468)==-9&&Field<float>(kEffect,0x44c)==12.5&&Field<float>(kEffect,0x450)==-2.5&&Field<std::int32_t>(kEffect,0x454)==-19&&Field<std::int32_t>(kEffect,0x458)==-19);
 assert(Field<float>(kSizeOnly,0x4ec)==3.25&&Field<float>(kNoQuery,0x524)==0.375&&Field<std::int32_t>(kNoQuery,0x4fc)==-17&&Field<std::uint8_t>(kNoQuery,0x538)==1&&Field<std::uint8_t>(kNoQuery,0x561)==1&&Field<std::int32_t>(kNoQuery,0x448)==-23);
 assert(Field<Vec>(kEnemyA,0x410).x==0&&Field<Vec>(kEnemyA,0x418).y==0);
 assert(Field<std::uint64_t>(kBullet,0x438)==0x8000000000000003ULL&&Field<std::uint64_t>(kBullet,0x428)==0x8000000000000002ULL);
 assert(Field<float>(kBullet,0x400)==-6.75&&Field<float>(kBullet,0x404)==0.5&&Field<float>(kBullet,0x408)==0.75&&Field<float>(kBullet,0x410)==3.5);
 assert(Field<float>(kTearNear,0x460)==1.25&&Field<Vec>(kTearNear,0x8ec).x==5&&Field<Vec>(kTearNear,0x8ec).y==6&&Field<std::int32_t>(kTearNear,0x428)==-29);
 assert(Field<float>(kTearNear,0x454)==91.75&&Field<float>(kTearNear,0x45c)==92.75&&Field<float>(kTearNear,0x464)==93.75);
 if(Run(L,"assert(tear.KnockbackMultiplier==1.25)"))return 14;
 for(unsigned i=0;i<9;++i)assert(calls[i]==1);assert(calls[9]==1);
 if(Run(L,R"lua(assert(not pcall(function()p.RenderGlow({},Vector(3,4))end));assert(not pcall(function()npc.KillUnique({})end));assert(not pcall(function()npc.MakeChampion({},0xffffffff)end));assert(not pcall(function()npc.MakeSplat({},2.5)end));assert(not pcall(function()pickup.TryOpenChest({},nil)end));assert(not pcall(function()npc.GetBossID({})end));assert(not pcall(function()npc.SetSpriteOverlayFrame({},'Overlay',-7)end));assert(not pcall(function()effect.FollowParent({},npc)end));assert(not pcall(function()effect.SetDamageSource({},-9)end));assert(not pcall(function()effect.SetRadii({},12.5,-2.5)end));assert(not pcall(function()effect.SetTimeout({},-19)end));assert(not pcall(function()knife.GetKnifeDistance({})end));assert(not pcall(function()knife.GetKnifeVelocity({})end));assert(not pcall(function()knife.SetPathFollowSpeed({},3.25)end));assert(not pcall(function()laser.GetEndPoint({})end));assert(not pcall(function()laser.IsCircleLaser({})end));assert(not pcall(function()laser.IsSampleLaser({})end));assert(not pcall(function()laser.SetBlackHpDropChance({},0.375)end));assert(not pcall(function()laser.SetHomingType({},-17)end));assert(not pcall(function()laser.SetMultidimensionalTouched({},true)end));assert(not pcall(function()laser.SetOneHit({},true)end));assert(not pcall(function()laser.SetTimeout({},-23)end));assert(not pcall(function()npc.ResetPathFinderTarget({})end));assert(not pcall(function()p.RenderTop({},Vector(3,4))end));assert(not pcall(function()npc.RenderShadowLayer({},Vector(3,4))end));assert(not pcall(function()projectile.AddChangeFlags({},0x8000000000000002)end));assert(not pcall(function()projectile.AddFallingAccel({},0.5)end));assert(not pcall(function()projectile.AddFallingSpeed({},-2.5)end));assert(not pcall(function()projectile.AddHeight({},3.25)end));assert(not pcall(function()projectile.AddProjectileFlags({},0x8000000000000002)end));assert(not pcall(function()projectile.AddScale({},1.5)end));assert(not pcall(function()projectile.ClearProjectileFlags({},1)end));assert(not pcall(function()tear.SetKnockbackMultiplier({},1.25)end));assert(not pcall(function()tear.SetParentOffset({},Vector(5,6))end));assert(not pcall(function()tear.SetWaitFrames({},-29)end));assert(not pcall(function()p.RenderGlow(npc,Vector(3,4))end));assert(not pcall(function()npc.KillUnique(p)end));assert(not pcall(function()npc.MakeChampion(p,0xffffffff)end));assert(not pcall(function()npc.MakeSplat(p,2.5)end));assert(not pcall(function()pickup.TryOpenChest(p,nil)end));assert(not pcall(function()effect.FollowParent(p,npc)end));assert(not pcall(function()effect.SetDamageSource(p,-9)end));assert(not pcall(function()effect.SetRadii(p,12.5,-2.5)end));assert(not pcall(function()effect.SetTimeout(p,-19)end));assert(not pcall(function()knife.GetKnifeDistance(p)end));assert(not pcall(function()knife.GetKnifeVelocity(p)end));assert(not pcall(function()knife.SetPathFollowSpeed(p,3.25)end));assert(not pcall(function()laser.GetEndPoint(p)end));assert(not pcall(function()laser.IsCircleLaser(p)end));assert(not pcall(function()laser.IsSampleLaser(p)end));assert(not pcall(function()laser.SetBlackHpDropChance(p,0.375)end));assert(not pcall(function()laser.SetHomingType(p,-17)end));assert(not pcall(function()laser.SetMultidimensionalTouched(p,true)end));assert(not pcall(function()laser.SetOneHit(p,true)end));assert(not pcall(function()laser.SetTimeout(p,-23)end));assert(not pcall(function()npc.ResetPathFinderTarget(p)end));assert(not pcall(function()p.RenderTop(npc,Vector(3,4))end));assert(not pcall(function()projectile.AddChangeFlags(p,0x8000000000000002)end));assert(not pcall(function()projectile.AddFallingAccel(p,0.5)end));assert(not pcall(function()projectile.AddFallingSpeed(p,-2.5)end));assert(not pcall(function()projectile.AddHeight(p,3.25)end));assert(not pcall(function()projectile.AddProjectileFlags(p,0x8000000000000002)end));assert(not pcall(function()projectile.AddScale(p,1.5)end));assert(not pcall(function()projectile.ClearProjectileFlags(p,1)end));assert(not pcall(function()tear.SetKnockbackMultiplier(p,1.25)end));assert(not pcall(function()tear.SetParentOffset(p,Vector(5,6))end));assert(not pcall(function()tear.SetWaitFrames(p,-29)end)))lua"))return 4;
 if(Run(L,R"lua(
 assert(not pcall(function()npc:MakeChampion({})end));assert(not pcall(function()npc:MakeChampion(7,{})end));assert(not pcall(function()pickup:TryOpenChest(npc)end));assert(not pcall(function()npc:SetSpriteOverlayFrame({},2)end));assert(not pcall(function()effect:FollowParent(nil)end));assert(not pcall(function()effect:SetRadii(2,{})end));assert(not pcall(function()tear:SetParentOffset({})end));assert(not pcall(function()projectile:AddChangeFlags({})end));assert(not pcall(function()projectile:ClearProjectileFlags({})end))
 npc:MakeChampion(7,4,true);npc:MakeChampion(0xffffffff,false,false);assert(not pickup:TryOpenChest(p));assert(pickup:TryOpenChest(nil));
 )lua"))return 5;
 if(Run(L,"laser:SetOneHit(0);laser:SetMultidimensionalTouched({});laser:SetTimeout(0xffffffff);projectile:ClearProjectileFlags(0x8000000000000000)"))return 15;
 assert(Field<std::uint8_t>(kNoQuery,0x561)==1&&Field<std::uint8_t>(kNoQuery,0x538)==1&&Field<std::int32_t>(kNoQuery,0x448)==-1&&Field<std::uint64_t>(kBullet,0x428)==2);
 nullSplat=true;if(Run(L,"assert(npc:MakeSplat(2.5)==nil)"))return 6;
 WriteAt<std::uint32_t>(g_Entities[kNoQuery],0x40,0);WriteAt<std::uint8_t>(g_Entities[kNoQuery],0x44d,0);WriteAt<Vec>(g_Entities[kNoQuery],0x500,Vec{23,24});WriteAt<float>(g_Entities[kSizeOnly],0x434,-17);WriteAt<float>(g_Entities[kSizeOnly],0x438,18);
 if(Run(L,"assert(not laser:IsCircleLaser() and not laser:IsSampleLaser());assert(endpoint.X==23 and endpoint.Y==24);assert(not pcall(function()endpoint.X=33 end));assert(laser:GetEndPoint().X==23);assert(knife:GetKnifeDistance()==-17 and knife:GetKnifeVelocity()==18);laser:SetOneHit();laser:SetMultidimensionalTouched(false);assert(not p:RenderShadowLayer(Vector(3,4)))"))return 7;
 assert(Field<std::uint8_t>(kNoQuery,0x561)==0&&Field<std::uint8_t>(kNoQuery,0x538)==0);
 if(scene=="dead"){
 for(auto s:slots)RetireEntityLifetime(AddressOf(g_Entities[s]));
 if(Run(L,R"lua(assert(not pcall(function()p:RenderGlow(Vector(3,4))end));assert(not pcall(function()npc:KillUnique()end));assert(not pcall(function()npc:MakeChampion(0xffffffff)end));assert(not pcall(function()npc:MakeSplat(2.5)end));assert(not pcall(function()pickup:TryOpenChest(nil)end));assert(not pcall(function()npc:GetBossID()end));assert(not pcall(function()npc:SetSpriteOverlayFrame('Overlay',-7)end));assert(not pcall(function()effect:FollowParent(npc)end));assert(not pcall(function()effect:SetDamageSource(-9)end));assert(not pcall(function()effect:SetRadii(12.5,-2.5)end));assert(not pcall(function()effect:SetTimeout(-19)end));assert(not pcall(function()knife:GetKnifeDistance()end));assert(not pcall(function()knife:GetKnifeVelocity()end));assert(not pcall(function()knife:SetPathFollowSpeed(3.25)end));assert(not pcall(function()laser:GetEndPoint()end));assert(not pcall(function()laser:IsCircleLaser()end));assert(not pcall(function()laser:IsSampleLaser()end));assert(not pcall(function()laser:SetBlackHpDropChance(0.375)end));assert(not pcall(function()laser:SetHomingType(-17)end));assert(not pcall(function()laser:SetMultidimensionalTouched(true)end));assert(not pcall(function()laser:SetOneHit(true)end));assert(not pcall(function()laser:SetTimeout(-23)end));assert(not pcall(function()npc:ResetPathFinderTarget()end));assert(not pcall(function()p:RenderTop(Vector(3,4))end));assert(not pcall(function()npc:RenderShadowLayer(Vector(3,4))end));assert(not pcall(function()projectile:AddChangeFlags(0x8000000000000002)end));assert(not pcall(function()projectile:AddFallingAccel(0.5)end));assert(not pcall(function()projectile:AddFallingSpeed(-2.5)end));assert(not pcall(function()projectile:AddHeight(3.25)end));assert(not pcall(function()projectile:AddProjectileFlags(0x8000000000000002)end));assert(not pcall(function()projectile:AddScale(1.5)end));assert(not pcall(function()projectile:ClearProjectileFlags(1)end));assert(not pcall(function()tear:SetKnockbackMultiplier(1.25)end));assert(not pcall(function()tear:SetParentOffset(Vector(5,6))end));assert(not pcall(function()tear:SetWaitFrames(-29)end));assert(not splat:Exists());assert(not pcall(function()return endpoint.X end)))lua"))return 8;
 }
 if(scene=="crossbase"){
 std::vector<unsigned char>changed=g_ModuleBytes;const auto base=AddressOf(changed);
 for(auto s:slots){const auto old=Field<std::uintptr_t>(s,0);WriteWord(g_Entities[s],0,base+(old-g_EngineBase));}
 for(unsigned i=0;i<8;++i){auto vptr=Field<std::uintptr_t>(shadows[i],0);const auto target=base+targets[i];std::memcpy(engine_memory::AsObject(vptr+56),&target,8);}
 LuaRuntime::SetEngineModuleBase(base);publish();
 changed[G::kRenderGlowEntry]^=1;
changed[G::kKillUniqueEntry]^=1;
changed[G::kMakeChampionEntry]^=1;
changed[G::kMakeSplatEntry]^=1;
changed[G::kTryOpenChestEntry]^=1;
changed[G::kOverlayEntry]^=1;
changed[G::kSetParentEntry]^=1;
changed[G::kResetMovementTargetEntry]^=1;
changed[G::kRenderTopEntry]^=1;
changed[G::kShadowEntityEntry]^=1;
changed[G::kShadowEntity_NPCEntry]^=1;
changed[G::kShadowEntity_LaserEntry]^=1;
changed[G::kShadowEntity_PlayerEntry]^=1;
changed[G::kShadowEntity_FamiliarEntry]^=1;
changed[G::kEntityLayoutEntry]^=1;
changed[G::kConfigLayoutEntry]^=1;
changed[G::kEffectLayoutEntry]^=1;
changed[G::kEffectUpdateEntry]^=1;
changed[G::kKnifeLayoutEntry]^=1;
changed[G::kKnifeUpdateEntry]^=1;
changed[G::kLaserLayoutEntry]^=1;
changed[G::kLaserDamageEntry]^=1;
changed[G::kLaserUpdateEntry]^=1;
changed[G::kLaserInitEntry]^=1;
changed[G::kTearLayoutEntry]^=1;
changed[G::kTearUpdateEntry]^=1;
changed[G::kProjectileLayoutEntry]^=1;
changed[G::kProjectileUpdateEntry]^=1;
changed[G::kNpcLayoutEntry]^=1;
changed[G::kTearHitLayoutEntry]^=1;
 if(Run(L,R"lua(local function guarded(f)local ok,err=pcall(f);assert(not ok and string.find(err,'guard'),tostring(err))end;guarded(function()p:RenderGlow(Vector(3,4))end);guarded(function()npc:KillUnique()end);guarded(function()npc:MakeChampion(0xffffffff)end);guarded(function()npc:MakeSplat(2.5)end);guarded(function()pickup:TryOpenChest(nil)end);guarded(function()npc:GetBossID()end);guarded(function()npc:SetSpriteOverlayFrame('Overlay',-7)end);guarded(function()effect:FollowParent(npc)end);guarded(function()effect:SetDamageSource(-9)end);guarded(function()effect:SetRadii(12.5,-2.5)end);guarded(function()effect:SetTimeout(-19)end);guarded(function()knife:GetKnifeDistance()end);guarded(function()knife:GetKnifeVelocity()end);guarded(function()knife:SetPathFollowSpeed(3.25)end);guarded(function()laser:GetEndPoint()end);guarded(function()laser:IsCircleLaser()end);guarded(function()laser:IsSampleLaser()end);guarded(function()laser:SetBlackHpDropChance(0.375)end);guarded(function()laser:SetHomingType(-17)end);guarded(function()laser:SetMultidimensionalTouched(true)end);guarded(function()laser:SetOneHit(true)end);guarded(function()laser:SetTimeout(-23)end);guarded(function()npc:ResetPathFinderTarget()end);guarded(function()p:RenderTop(Vector(3,4))end);guarded(function()npc:RenderShadowLayer(Vector(3,4))end);guarded(function()projectile:AddChangeFlags(0x8000000000000002)end);guarded(function()projectile:AddFallingAccel(0.5)end);guarded(function()projectile:AddFallingSpeed(-2.5)end);guarded(function()projectile:AddHeight(3.25)end);guarded(function()projectile:AddProjectileFlags(0x8000000000000002)end);guarded(function()projectile:AddScale(1.5)end);guarded(function()projectile:ClearProjectileFlags(1)end);guarded(function()tear:SetKnockbackMultiplier(1.25)end);guarded(function()tear:SetParentOffset(Vector(5,6))end);guarded(function()tear:SetWaitFrames(-29)end))lua"))return 9;
 }
 lua_close(L);return 0;
}

'''
class Entities35Behavior(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='api400-entities-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=source.replace('kEntityBlockSize = 0xD00','kEntityBlockSize = 0x3000')
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  extra=ROOT/'runtime/src/interfaces/lua/api400_entities.cpp'
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source,extra_sources=() if not extra.exists() or extra in layered_lua_runtime_sources(fixture.SOURCE) else (extra,))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_35_methods(self):
  for scene in ('normal','badguard','dead','crossbase'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
