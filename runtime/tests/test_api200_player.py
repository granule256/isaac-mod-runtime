"""第一组20玩家方法的真实Lua→原生行为判据。"""
import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''

#include "interfaces/lua/api200_player.hpp"
#include "interfaces/lua/api200_player.guards.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/bitset128_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
#include <cmath>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;using Vec2=LuaRuntime::VectorHandle;
static void*wanted{},*enemy{};static unsigned calls[34]{};
static unsigned effects[34]{};static void*queued{};static unsigned queueFlags{},queueCharge{},queueData{};
static bool held{},shooting{},consumer{};
static bool curse{},dollars{},formCostume{},babySkin{},skinRemoved{};static unsigned pocketDropped{},zitShot{},candleShot{},familiars{},book{},poop{};static std::string animation;
static std::vector<unsigned char> manager,managerSlot,itemBytes,itemVector;
static void Touch(unsigned n,void*p){assert(p==wanted);++calls[n];++effects[n];}
static void FAddCurseMistEffect(void*p){Touch(0,p);curse=true;}
static void FAddDollarBillEffect(void*p){Touch(1,p);dollars=true;}
static void FAddPlayerFormCostume(void*p,std::int32_t a0){Touch(2,p);formCostume=true;assert(a0==-1);}
static void FAnimatePitfallIn(void*p,bool a0){Touch(3,p);animation="PitfallIn";if(consumer){assert(!a0);return;}if(calls[3]==1){assert(a0);}else{assert(!a0);}}
static void FAnimatePitfallOut(void*p){Touch(4,p);animation="PitfallOut";}
static void FAnimateTeleport(void*p,bool a0){Touch(5,p);animation=a0?"TeleportUp":"TeleportDown";if(calls[5]==1){assert(!a0);}else{assert(a0);}}
static void FDoZitEffect(void*p,const Vec2& a0){Touch(6,p);++zitShot;assert(a0.x==3&&a0.y==4);}
static void FDropPocketItem(void*p,std::uint32_t a0,const Vec2& a1){Touch(7,p);++pocketDropped;assert(a0==0xffffffffU);assert(a1.x==13&&a1.y==14);}
static void* FFireBrimstone(void*p,const Vec2& a0,void* a1,float a2){Touch(8,p);if(calls[8]==1){assert(a0.x==3&&a0.y==4);assert(a1==enemy);assert(a2==2.5F);}else{assert(a0.x==3&&a0.y==4&&a1==nullptr&&(a2==1.0F||a2==0.0F));}return calls[8]==1?g_Entities[kEffect].data():nullptr;}
static void* FFireDelayedBrimstone(void*p,float a0,void* a1){Touch(9,p);assert(a0==35.5F);assert(a1==enemy);return g_Entities[kEffect].data();}
static void* FFireKnife(void*p,void* a0,std::uint32_t a1,float a2,bool a3,std::uint32_t a4){Touch(10,p);if(calls[10]==1){assert(a0==enemy);assert(a1==8);assert(a2==12.5F);assert(a3);assert(a4==7);}else{assert(a0==nullptr&&a1==0&&a2==0.0F&&!a3&&a4==0);}return (calls[10]==1||calls[10]==4)?g_Entities[kEffectNoQuery].data():nullptr;}
static void* FFireTechXLaser(void*p,const Vec2& a0,const Vec2& a1,float a2,void* a3,float a4){Touch(11,p);if(consumer){assert(a0.x==-14||a0.x==16);assert(std::abs(a0.y-2)<0.0001F);assert(std::abs(std::abs(a1.x)-2)<0.0001F&&std::abs(a1.y+3.4641016F)<0.0001F);assert(a2==25&&a3==nullptr&&a4==1);return g_Entities[kEffect].data();}if(calls[11]==1){assert(a0.x==1&&a0.y==2);assert(a1.x==3&&a1.y==4);assert(a2==25);assert(a3==enemy);assert(a4==2.5F);}else{assert(a0.x==1&&a0.y==2&&a1.x==3&&a1.y==4&&a2==0&&a3==nullptr&&(a4==1||a4==0));}return calls[11]==1?g_Entities[kEffect].data():nullptr;}
static BitSet128Value FGetBombFlags(void*p,bool a0){Touch(12,p);if(consumer){assert(!a0);return {0x8000000000000001ULL,0x4000000000000002ULL};}if(calls[12]==1){assert(a0);}else{assert(!a0);}return {a0?0x8000000000000001ULL:0ULL,a0?0x4000000000000002ULL:0ULL};}
static Vec2 FGetFlyingOffset(void*p){Touch(13,p);return {3.25F,-4.5F};}
static Vec2 FGetLaserOffset(void*p,std::int32_t a0,const Vec2& a1){Touch(14,p);assert(a0==-1);assert(a1.x==3&&a1.y==4);return {a1.y+static_cast<float>(a0),-a1.x};}
static void* FGetNPCTarget(void*p){Touch(15,p);return g_Entities[kEnemyA].data();}
static bool FHasInvincibility(void*p,std::uint64_t a0){Touch(16,p);if(calls[16]==1){assert(a0==0x4000000000000001ULL);}else{assert(a0==0||a0==0x8000000000000000ULL);}return a0!=0;}
static void FInitBabySkin(void*p){Touch(17,p);babySkin=true;}
static bool FIsFullSpriteRendering(void*p){Touch(18,p);return true;}
static bool FIsPosInSpotLight(void*p,const Vec2& a0){Touch(19,p);if(calls[19]==1){assert(a0.x==3&&a0.y==4);}else{assert(a0.x==0&&a0.y==0);}return a0.x!=0;}
static void FPlayExtraAnimation(void*p,const char* a0){Touch(20,p);animation=a0;if(consumer){assert(!std::strcmp(a0,"HideItem")||!std::strcmp(a0,"Sad")||!std::strcmp(a0,"Happy")||!std::strcmp(a0,"Appear"));return;}assert(!std::strcmp(a0,"123"));}
static void FQueueItem(void*p,const void* a0,std::int32_t a1,std::uint8_t a2,std::int32_t a3){Touch(21,p);if(consumer){assert(a0==itemBytes.data()&&a1==5&&a2==0&&a3==0);queued=const_cast<void*>(a0);queueCharge=a1;queueFlags=a2;queueData=a3;return;}if(calls[21]==1){assert(a0==itemBytes.data());assert(a1==5);assert(a2==3);assert(a3==9);}else{assert(a0==nullptr&&a1==0&&a2==0&&a3==0);}queued=const_cast<void*>(a0);queueCharge=a1;queueFlags=a2;queueData=a3;}
static void FRemoveCurseMistEffect(void*p){Touch(22,p);curse=false;}
static void FRemoveSkinCostume(void*p){Touch(23,p);skinRemoved=true;}
static void FResetItemState(void*p){Touch(24,p);held=false;}
static void FRespawnFamiliars(void*p){Touch(25,p);++familiars;}
static void FShootRedCandle(void*p,const Vec2& a0){Touch(26,p);++candleShot;assert(a0.x==3&&a0.y==4);}
static void* FSpawnMawOfVoid(void*p,std::int32_t a0){Touch(27,p);if(consumer){assert(a0==15);return g_Entities[kEffect].data();}assert(a0==-1);return g_Entities[kEffect].data();}
static void* FThrowFriendlyDip(void*p,std::int32_t a0,const Vec2& a1,const Vec2& a2){Touch(28,p);assert(a0==-1);assert(a1.x==1&&a1.y==2);assert(a2.x==3&&a2.y==4);return g_Entities[kFamiliar].data();}
static void FTriggerBookOfVirtues(void*p,std::int32_t a0,std::int32_t a1){Touch(29,p);++book;if(calls[29]==1){assert(a0==-1);assert(a1==5);}else{assert(a0==0&&a1==0);}}
static bool FTryHoldEntity(void*p,void* a0){Touch(30,p);assert(a0==enemy);held=a0!=nullptr;return held;}
static bool FTryHoldTrinket(void*p,std::int32_t a0){Touch(31,p);if(calls[31]==1){assert(a0==-1);}else{assert(a0==0);}return a0!=0;}
static void FUpdateCanShoot(void*p){Touch(32,p);shooting=true;}
static void FUsePoopSpell(void*p,std::int32_t a0){Touch(33,p);++poop;assert(a0==-1);}

int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;const std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 wanted=g_Entities[kPlayer].data();enemy=g_Entities[kEnemyA].data();
 WriteWord(g_Entities[kEffect],0,g_EngineBase+kEntityLaserVtableOffset);WriteAt<std::uint32_t>(g_Entities[kEffect],kEntityTypeOffset,7);
 WriteWord(g_Entities[kEffectNoQuery],0,g_EngineBase+kEntityKnifeVtableOffset);WriteAt<std::uint32_t>(g_Entities[kEffectNoQuery],kEntityTypeOffset,8);
 manager.assign(kManagerItemConfigOffset+0x100,0);managerSlot.assign(8,0);itemBytes.assign(0xd8,0);itemVector.assign(16,0);
 WriteWord(managerSlot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(managerSlot));
 WriteWord(itemVector,8,AddressOf(itemBytes));WriteAt<std::uint32_t>(itemBytes,0,1);WriteAt<std::uint32_t>(itemBytes,4,1);
 WriteWord(manager,kManagerItemConfigOffset,AddressOf(itemVector));WriteWord(manager,kManagerItemConfigOffset+8,AddressOf(itemVector)+16);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 namespace guards=api200_player;auto guard=[&](auto o,const auto&b){std::memcpy(g_ModuleBytes.data()+o,b.data(),b.size());};
 guard(guards::kAddCurseMistEffectEntry,guards::kAddCurseMistEffectGuard);
 guard(guards::kAddDollarBillEffectEntry,guards::kAddDollarBillEffectGuard);
 guard(guards::kAddPlayerFormCostumeEntry,guards::kAddPlayerFormCostumeGuard);
 guard(guards::kAnimatePitfallInEntry,guards::kAnimatePitfallInGuard);
 guard(guards::kAnimatePitfallOutEntry,guards::kAnimatePitfallOutGuard);
 guard(guards::kAnimateTeleportEntry,guards::kAnimateTeleportGuard);
 guard(guards::kDoZitEffectEntry,guards::kDoZitEffectGuard);
 guard(guards::kDropPocketItemEntry,guards::kDropPocketItemGuard);
 guard(guards::kFireBrimstoneEntry,guards::kFireBrimstoneGuard);
 guard(guards::kFireDelayedBrimstoneEntry,guards::kFireDelayedBrimstoneGuard);
 guard(guards::kFireKnifeEntry,guards::kFireKnifeGuard);
 guard(guards::kFireTechXLaserEntry,guards::kFireTechXLaserGuard);
 guard(guards::kGetBombFlagsEntry,guards::kGetBombFlagsGuard);
 guard(guards::kGetFlyingOffsetEntry,guards::kGetFlyingOffsetGuard);
 guard(guards::kGetLaserOffsetEntry,guards::kGetLaserOffsetGuard);
 guard(guards::kGetNPCTargetEntry,guards::kGetNPCTargetGuard);
 guard(guards::kHasInvincibilityEntry,guards::kHasInvincibilityGuard);
 guard(guards::kInitBabySkinEntry,guards::kInitBabySkinGuard);
 guard(guards::kIsFullSpriteRenderingEntry,guards::kIsFullSpriteRenderingGuard);
 guard(guards::kIsPosInSpotLightEntry,guards::kIsPosInSpotLightGuard);
 guard(guards::kPlayExtraAnimationEntry,guards::kPlayExtraAnimationGuard);
 guard(guards::kQueueItemEntry,guards::kQueueItemGuard);
 guard(guards::kRemoveCurseMistEffectEntry,guards::kRemoveCurseMistEffectGuard);
 guard(guards::kRemoveSkinCostumeEntry,guards::kRemoveSkinCostumeGuard);
 guard(guards::kResetItemStateEntry,guards::kResetItemStateGuard);
 guard(guards::kRespawnFamiliarsEntry,guards::kRespawnFamiliarsGuard);
 guard(guards::kShootRedCandleEntry,guards::kShootRedCandleGuard);
 guard(guards::kSpawnMawOfVoidEntry,guards::kSpawnMawOfVoidGuard);
 guard(guards::kThrowFriendlyDipEntry,guards::kThrowFriendlyDipGuard);
 guard(guards::kTriggerBookOfVirtuesEntry,guards::kTriggerBookOfVirtuesGuard);
 guard(guards::kTryHoldEntityEntry,guards::kTryHoldEntityGuard);
 guard(guards::kTryHoldTrinketEntry,guards::kTryHoldTrinketGuard);
 guard(guards::kUpdateCanShootEntry,guards::kUpdateCanShootGuard);
 guard(guards::kUsePoopSpellEntry,guards::kUsePoopSpellGuard);
 Api200PlayerNativeTestBindings bindings{};
 bindings.methods[0]=engine_call::AddressOfFunction(&FAddCurseMistEffect);
 bindings.methods[1]=engine_call::AddressOfFunction(&FAddDollarBillEffect);
 bindings.methods[2]=engine_call::AddressOfFunction(&FAddPlayerFormCostume);
 bindings.methods[3]=engine_call::AddressOfFunction(&FAnimatePitfallIn);
 bindings.methods[4]=engine_call::AddressOfFunction(&FAnimatePitfallOut);
 bindings.methods[5]=engine_call::AddressOfFunction(&FAnimateTeleport);
 bindings.methods[6]=engine_call::AddressOfFunction(&FDoZitEffect);
 bindings.methods[7]=engine_call::AddressOfFunction(&FDropPocketItem);
 bindings.methods[8]=engine_call::AddressOfFunction(&FFireBrimstone);
 bindings.methods[9]=engine_call::AddressOfFunction(&FFireDelayedBrimstone);
 bindings.methods[10]=engine_call::AddressOfFunction(&FFireKnife);
 bindings.methods[11]=engine_call::AddressOfFunction(&FFireTechXLaser);
 bindings.methods[12]=engine_call::AddressOfFunction(&FGetBombFlags);
 bindings.methods[13]=engine_call::AddressOfFunction(&FGetFlyingOffset);
 bindings.methods[14]=engine_call::AddressOfFunction(&FGetLaserOffset);
 bindings.methods[15]=engine_call::AddressOfFunction(&FGetNPCTarget);
 bindings.methods[16]=engine_call::AddressOfFunction(&FHasInvincibility);
 bindings.methods[17]=engine_call::AddressOfFunction(&FInitBabySkin);
 bindings.methods[18]=engine_call::AddressOfFunction(&FIsFullSpriteRendering);
 bindings.methods[19]=engine_call::AddressOfFunction(&FIsPosInSpotLight);
 bindings.methods[20]=engine_call::AddressOfFunction(&FPlayExtraAnimation);
 bindings.methods[21]=engine_call::AddressOfFunction(&FQueueItem);
 bindings.methods[22]=engine_call::AddressOfFunction(&FRemoveCurseMistEffect);
 bindings.methods[23]=engine_call::AddressOfFunction(&FRemoveSkinCostume);
 bindings.methods[24]=engine_call::AddressOfFunction(&FResetItemState);
 bindings.methods[25]=engine_call::AddressOfFunction(&FRespawnFamiliars);
 bindings.methods[26]=engine_call::AddressOfFunction(&FShootRedCandle);
 bindings.methods[27]=engine_call::AddressOfFunction(&FSpawnMawOfVoid);
 bindings.methods[28]=engine_call::AddressOfFunction(&FThrowFriendlyDip);
 bindings.methods[29]=engine_call::AddressOfFunction(&FTriggerBookOfVirtues);
 bindings.methods[30]=engine_call::AddressOfFunction(&FTryHoldEntity);
 bindings.methods[31]=engine_call::AddressOfFunction(&FTryHoldTrinket);
 bindings.methods[32]=engine_call::AddressOfFunction(&FUpdateCanShoot);
 bindings.methods[33]=engine_call::AddressOfFunction(&FUsePoopSpell);
 SetApi200PlayerNativeTestBindings(bindings);

 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_MATHLIBNAME,luaopen_math,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));
 RegisterVectorReferenceMetatable(L);luaL_newmetatable(L,LuaRuntime::kVectorMetatable);lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,VectorNewIndex);lua_setfield(L,-2,"__newindex");lua_pushcfunction(L,VectorAdd);lua_setfield(L,-2,"__add");lua_newtable(L);static_cast<void>(AttachVectorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");RegisterBitSet128Api(L);
 if(scene!="integration"){
 luaL_getmetatable(L,LuaRuntime::kEntityPlayerMetatable);lua_getfield(L,-1,"__methods");
 lua_pushcfunction(L,Api200EntityPlayerAddCurseMistEffect);lua_setfield(L,-2,"AddCurseMistEffect");
 lua_pushcfunction(L,Api200EntityPlayerAddDollarBillEffect);lua_setfield(L,-2,"AddDollarBillEffect");
 lua_pushcfunction(L,Api200EntityPlayerAddPlayerFormCostume);lua_setfield(L,-2,"AddPlayerFormCostume");
 lua_pushcfunction(L,Api200EntityPlayerAnimatePitfallIn);lua_setfield(L,-2,"AnimatePitfallIn");
 lua_pushcfunction(L,Api200EntityPlayerAnimatePitfallOut);lua_setfield(L,-2,"AnimatePitfallOut");
 lua_pushcfunction(L,Api200EntityPlayerAnimateTeleport);lua_setfield(L,-2,"AnimateTeleport");
 lua_pushcfunction(L,Api200EntityPlayerDoZitEffect);lua_setfield(L,-2,"DoZitEffect");
 lua_pushcfunction(L,Api200EntityPlayerDropPocketItem);lua_setfield(L,-2,"DropPocketItem");
 lua_pushcfunction(L,Api200EntityPlayerFireBrimstone);lua_setfield(L,-2,"FireBrimstone");
 lua_pushcfunction(L,Api200EntityPlayerFireDelayedBrimstone);lua_setfield(L,-2,"FireDelayedBrimstone");
 lua_pushcfunction(L,Api200EntityPlayerFireKnife);lua_setfield(L,-2,"FireKnife");
 lua_pushcfunction(L,Api200EntityPlayerFireTechXLaser);lua_setfield(L,-2,"FireTechXLaser");
 lua_pushcfunction(L,Api200EntityPlayerGetBombFlags);lua_setfield(L,-2,"GetBombFlags");
 lua_pushcfunction(L,Api200EntityPlayerGetFlyingOffset);lua_setfield(L,-2,"GetFlyingOffset");
 lua_pushcfunction(L,Api200EntityPlayerGetLaserOffset);lua_setfield(L,-2,"GetLaserOffset");
 lua_pushcfunction(L,Api200EntityPlayerGetNPCTarget);lua_setfield(L,-2,"GetNPCTarget");
 lua_pushcfunction(L,Api200EntityPlayerHasInvincibility);lua_setfield(L,-2,"HasInvincibility");
 lua_pushcfunction(L,Api200EntityPlayerInitBabySkin);lua_setfield(L,-2,"InitBabySkin");
 lua_pushcfunction(L,Api200EntityPlayerIsFullSpriteRendering);lua_setfield(L,-2,"IsFullSpriteRendering");
 lua_pushcfunction(L,Api200EntityPlayerIsPosInSpotLight);lua_setfield(L,-2,"IsPosInSpotLight");
 lua_pushcfunction(L,Api200EntityPlayerPlayExtraAnimation);lua_setfield(L,-2,"PlayExtraAnimation");
 lua_pushcfunction(L,Api200EntityPlayerQueueItem);lua_setfield(L,-2,"QueueItem");
 lua_pushcfunction(L,Api200EntityPlayerRemoveCurseMistEffect);lua_setfield(L,-2,"RemoveCurseMistEffect");
 lua_pushcfunction(L,Api200EntityPlayerRemoveSkinCostume);lua_setfield(L,-2,"RemoveSkinCostume");
 lua_pushcfunction(L,Api200EntityPlayerResetItemState);lua_setfield(L,-2,"ResetItemState");
 lua_pushcfunction(L,Api200EntityPlayerRespawnFamiliars);lua_setfield(L,-2,"RespawnFamiliars");
 lua_pushcfunction(L,Api200EntityPlayerShootRedCandle);lua_setfield(L,-2,"ShootRedCandle");
 lua_pushcfunction(L,Api200EntityPlayerSpawnMawOfVoid);lua_setfield(L,-2,"SpawnMawOfVoid");
 lua_pushcfunction(L,Api200EntityPlayerThrowFriendlyDip);lua_setfield(L,-2,"ThrowFriendlyDip");
 lua_pushcfunction(L,Api200EntityPlayerTriggerBookOfVirtues);lua_setfield(L,-2,"TriggerBookOfVirtues");
 lua_pushcfunction(L,Api200EntityPlayerTryHoldEntity);lua_setfield(L,-2,"TryHoldEntity");
 lua_pushcfunction(L,Api200EntityPlayerTryHoldTrinket);lua_setfield(L,-2,"TryHoldTrinket");
 lua_pushcfunction(L,Api200EntityPlayerUpdateCanShoot);lua_setfield(L,-2,"UpdateCanShoot");
 lua_pushcfunction(L,Api200EntityPlayerUsePoopSpell);lua_setfield(L,-2,"UsePoopSpell");
 lua_pop(L,2);
 }
 const char*script=R"lua(p=Isaac.GetPlayer();npc=Isaac.FindByType(20)[1];item=Isaac.GetItemConfig():GetCollectible(1);assert(item and npc);
assert(select('#',p:AddCurseMistEffect('ignored',{}))==0,'AddCurseMistEffect');
assert(select('#',p:AddDollarBillEffect('ignored',{}))==0,'AddDollarBillEffect');
assert(select('#',p:AddPlayerFormCostume('4294967295'))==0,'AddPlayerFormCostume');
assert(select('#',p:AnimatePitfallIn(0))==0,'AnimatePitfallIn');
assert(select('#',p:AnimatePitfallOut('ignored',{}))==0,'AnimatePitfallOut');
assert(select('#',p:AnimateTeleport(false))==0,'AnimateTeleport');
assert(select('#',p:DoZitEffect(Vector(3,4)))==0,'DoZitEffect');
assert(select('#',p:DropPocketItem('4294967295',Vector(13,14)))==0,'DropPocketItem');
do local e=p:FireBrimstone(Vector(3,4),npc,2.5);assert(e and e:ToLaser()~=nil);savedFireBrimstone=e;end
do local e=p:FireDelayedBrimstone(35.5,npc);assert(e and e:ToLaser()~=nil);savedFireDelayedBrimstone=e;end
do local e=p:FireKnife(npc,12.5,true,7,8);assert(e and e:ToKnife()~=nil);savedFireKnife=e;end
do local e=p:FireTechXLaser(Vector(1,2),Vector(3,4),25,npc,2.5);assert(e and e:ToLaser()~=nil);savedFireTechXLaser=e;end
assert(p:GetBombFlags(0)==BitSet128(0x8000000000000001,0x4000000000000002));
do local v=p:GetFlyingOffset('ignored',{});assert(v.X==3.25 and v.Y==-4.5);end
do local v=p:GetLaserOffset('4294967295',Vector(3,4));assert(v.X==3 and v.Y==-3);end
do local e=p:GetNPCTarget('ignored',{});assert(e and e:ToNPC()~=nil);savedGetNPCTarget=e;end
assert(p:HasInvincibility(0x4000000000000001),'HasInvincibility');
assert(select('#',p:InitBabySkin('ignored',{}))==0,'InitBabySkin');
assert(p:IsFullSpriteRendering('ignored',{}),'IsFullSpriteRendering');
assert(p:IsPosInSpotLight(Vector(3,4)),'IsPosInSpotLight');
assert(select('#',p:PlayExtraAnimation(123))==0,'PlayExtraAnimation');
assert(select('#',p:QueueItem(item,5,0,true,9))==0,'QueueItem');
assert(select('#',p:RemoveCurseMistEffect('ignored',{}))==0,'RemoveCurseMistEffect');
assert(select('#',p:RemoveSkinCostume('ignored',{}))==0,'RemoveSkinCostume');
assert(select('#',p:ResetItemState('ignored',{}))==0,'ResetItemState');
assert(select('#',p:RespawnFamiliars('ignored',{}))==0,'RespawnFamiliars');
assert(select('#',p:ShootRedCandle(Vector(3,4)))==0,'ShootRedCandle');
do local e=p:SpawnMawOfVoid('4294967295');assert(e and e:ToLaser()~=nil);savedSpawnMawOfVoid=e;end
do local e=p:ThrowFriendlyDip('4294967295',Vector(1,2),Vector(3,4));assert(e and e:ToFamiliar()~=nil);savedThrowFriendlyDip=e;end
assert(select('#',p:TriggerBookOfVirtues('4294967295',5))==0,'TriggerBookOfVirtues');
assert(p:TryHoldEntity(npc),'TryHoldEntity');
assert(p:TryHoldTrinket('4294967295'),'TryHoldTrinket');
assert(select('#',p:UpdateCanShoot('ignored',{}))==0,'UpdateCanShoot');
assert(select('#',p:UsePoopSpell('4294967295'))==0,'UsePoopSpell');

assert(p:FireBrimstone(Vector(3,4))==nil);assert(p:FireBrimstone(Vector(3,4),nil,false)==nil);assert(p:FireBrimstone(Vector(3,4),nil,0)==nil)
assert(p:FireKnife(nil)==nil);assert(p:FireKnife(nil,false,nil,false,false)==nil);do local knife=p:FireKnife();assert(knife:ToKnife());savedZeroKnife=knife end
assert(p:FireTechXLaser(Vector(1,2),Vector(3,4),0)==nil);assert(p:FireTechXLaser(Vector(1,2),Vector(3,4),0,nil,false)==nil);assert(p:FireTechXLaser(Vector(1,2),Vector(3,4),0,nil,0)==nil)
assert(p:GetBombFlags()==BitSet128(0,0));assert(p:GetBombFlags(nil)==BitSet128(0,0));assert(p:GetBombFlags(false)==BitSet128(0,0))
assert(not p:HasInvincibility());assert(not p:HasInvincibility(false));assert(not p:HasInvincibility(0));assert(p:HasInvincibility(0x8000000000000000))
p:QueueItem(nil,false,nil,false,false);assert(select("#",p:QueueItem())==0);p:TriggerBookOfVirtues(false,nil);p:AnimatePitfallIn();p:AnimateTeleport(0)
assert(not p:IsPosInSpotLight(Vector(0,0)));assert(not p:TryHoldTrinket(0))
assert(not pcall(function()p:AddPlayerFormCostume() end),'AddPlayerFormCostume()');
assert(not pcall(function()p:AddPlayerFormCostume(nil) end),'AddPlayerFormCostume(nil)');
assert(not pcall(function()p:AddPlayerFormCostume(false) end),'AddPlayerFormCostume(false)');
assert(not pcall(function()p:AddPlayerFormCostume(1.5) end),'AddPlayerFormCostume(1.5)');
assert(not pcall(function()p:AddPlayerFormCostume({}) end),'AddPlayerFormCostume({})');
assert(not pcall(function()p:DropPocketItem(nil,Vector(1,2)) end),'DropPocketItem(nil,Vector(1,2))');
assert(not pcall(function()p:DropPocketItem(1,nil) end),'DropPocketItem(1,nil)');
assert(not pcall(function()p:DropPocketItem(1,{}) end),'DropPocketItem(1,{})');
assert(not pcall(function()p:DoZitEffect() end),'DoZitEffect()');
assert(not pcall(function()p:DoZitEffect(nil) end),'DoZitEffect(nil)');
assert(not pcall(function()p:DoZitEffect({}) end),'DoZitEffect({})');
assert(not pcall(function()p:DoZitEffect(npc) end),'DoZitEffect(npc)');
assert(not pcall(function()p:ShootRedCandle() end),'ShootRedCandle()');
assert(not pcall(function()p:ShootRedCandle(false) end),'ShootRedCandle(false)');
assert(not pcall(function()p:ShootRedCandle(npc) end),'ShootRedCandle(npc)');
assert(not pcall(function()p:FireBrimstone() end),'FireBrimstone()');
assert(not pcall(function()p:FireBrimstone(Vector(3,4),false) end),'FireBrimstone(Vector(3,4),false)');
assert(not pcall(function()p:FireBrimstone(Vector(3,4),{},1) end),'FireBrimstone(Vector(3,4),{},1)');
assert(not pcall(function()p:FireBrimstone(Vector(3,4),nil,{}) end),'FireBrimstone(Vector(3,4),nil,{})');
assert(not pcall(function()p:FireDelayedBrimstone() end),'FireDelayedBrimstone()');
assert(not pcall(function()p:FireDelayedBrimstone(1) end),'FireDelayedBrimstone(1)');
assert(not pcall(function()p:FireDelayedBrimstone(1,nil) end),'FireDelayedBrimstone(1,nil)');
assert(not pcall(function()p:FireDelayedBrimstone(false,npc) end),'FireDelayedBrimstone(false,npc)');
assert(not pcall(function()p:FireDelayedBrimstone(1,false) end),'FireDelayedBrimstone(1,false)');
assert(not pcall(function()p:FireKnife(false) end),'FireKnife(false)');
assert(not pcall(function()p:FireKnife(nil,{}) end),'FireKnife(nil,{})');
assert(not pcall(function()p:FireKnife(nil,0,false,1.5) end),'FireKnife(nil,0,false,1.5)');
assert(not pcall(function()p:FireKnife(nil,0,false,0,{}) end),'FireKnife(nil,0,false,0,{})');
assert(not pcall(function()p:FireTechXLaser() end),'FireTechXLaser()');
assert(not pcall(function()p:FireTechXLaser(Vector(1,2),nil,1) end),'FireTechXLaser(Vector(1,2),nil,1)');
assert(not pcall(function()p:FireTechXLaser(Vector(1,2),Vector(3,4),false) end),'FireTechXLaser(Vector(1,2),Vector(3,4),false)');
assert(not pcall(function()p:FireTechXLaser(Vector(1,2),Vector(3,4),0,false) end),'FireTechXLaser(Vector(1,2),Vector(3,4),0,false)');
assert(not pcall(function()p:FireTechXLaser(Vector(1,2),Vector(3,4),0,nil,{}) end),'FireTechXLaser(Vector(1,2),Vector(3,4),0,nil,{})');
assert(not pcall(function()p:GetLaserOffset() end),'GetLaserOffset()');
assert(not pcall(function()p:GetLaserOffset(false,Vector(1,2)) end),'GetLaserOffset(false,Vector(1,2))');
assert(not pcall(function()p:GetLaserOffset(1,nil) end),'GetLaserOffset(1,nil)');
assert(not pcall(function()p:HasInvincibility(1.5) end),'HasInvincibility(1.5)');
assert(not pcall(function()p:HasInvincibility({}) end),'HasInvincibility({})');
assert(not pcall(function()p:HasInvincibility("no") end),'HasInvincibility("no")');
assert(not pcall(function()p:IsPosInSpotLight() end),'IsPosInSpotLight()');
assert(not pcall(function()p:IsPosInSpotLight(false) end),'IsPosInSpotLight(false)');
assert(not pcall(function()p:IsPosInSpotLight({}) end),'IsPosInSpotLight({})');
assert(not pcall(function()p:PlayExtraAnimation() end),'PlayExtraAnimation()');
assert(not pcall(function()p:PlayExtraAnimation(nil) end),'PlayExtraAnimation(nil)');
assert(not pcall(function()p:PlayExtraAnimation(false) end),'PlayExtraAnimation(false)');
assert(not pcall(function()p:PlayExtraAnimation({}) end),'PlayExtraAnimation({})');
assert(not pcall(function()p:QueueItem(false) end),'QueueItem(false)');
assert(not pcall(function()p:QueueItem(npc) end),'QueueItem(npc)');
assert(not pcall(function()p:QueueItem({}) end),'QueueItem({})');
assert(not pcall(function()p:QueueItem(item,{},false,false,0) end),'QueueItem(item,{},false,false,0)');
assert(not pcall(function()p:QueueItem(item,0,false,false,1.5) end),'QueueItem(item,0,false,false,1.5)');
assert(not pcall(function()p:SpawnMawOfVoid() end),'SpawnMawOfVoid()');
assert(not pcall(function()p:SpawnMawOfVoid(nil) end),'SpawnMawOfVoid(nil)');
assert(not pcall(function()p:SpawnMawOfVoid(false) end),'SpawnMawOfVoid(false)');
assert(not pcall(function()p:SpawnMawOfVoid(1.5) end),'SpawnMawOfVoid(1.5)');
assert(not pcall(function()p:ThrowFriendlyDip() end),'ThrowFriendlyDip()');
assert(not pcall(function()p:ThrowFriendlyDip(1,Vector(1,2),nil) end),'ThrowFriendlyDip(1,Vector(1,2),nil)');
assert(not pcall(function()p:ThrowFriendlyDip(false,Vector(1,2),Vector(1,2)) end),'ThrowFriendlyDip(false,Vector(1,2),Vector(1,2))');
assert(not pcall(function()p:TriggerBookOfVirtues({}) end),'TriggerBookOfVirtues({})');
assert(not pcall(function()p:TriggerBookOfVirtues(0,1.5) end),'TriggerBookOfVirtues(0,1.5)');
assert(not pcall(function()p:TryHoldEntity() end),'TryHoldEntity()');
assert(not pcall(function()p:TryHoldEntity(nil) end),'TryHoldEntity(nil)');
assert(not pcall(function()p:TryHoldEntity(false) end),'TryHoldEntity(false)');
assert(not pcall(function()p:TryHoldEntity({}) end),'TryHoldEntity({})');
assert(not pcall(function()p:TryHoldTrinket() end),'TryHoldTrinket()');
assert(not pcall(function()p:TryHoldTrinket(nil) end),'TryHoldTrinket(nil)');
assert(not pcall(function()p:TryHoldTrinket(false) end),'TryHoldTrinket(false)');
assert(not pcall(function()p:TryHoldTrinket(1.5) end),'TryHoldTrinket(1.5)');
assert(not pcall(function()p:UsePoopSpell() end),'UsePoopSpell()');
assert(not pcall(function()p:UsePoopSpell(nil) end),'UsePoopSpell(nil)');
assert(not pcall(function()p:UsePoopSpell(false) end),'UsePoopSpell(false)');
assert(not pcall(function()p:UsePoopSpell(1.5) end),'UsePoopSpell(1.5)');
local methods={'AddCurseMistEffect','AddDollarBillEffect','AddPlayerFormCostume','AnimatePitfallIn','AnimatePitfallOut','AnimateTeleport','DoZitEffect','DropPocketItem','FireBrimstone','FireDelayedBrimstone','FireKnife','FireTechXLaser','GetBombFlags','GetFlyingOffset','GetLaserOffset','GetNPCTarget','HasInvincibility','InitBabySkin','IsFullSpriteRendering','IsPosInSpotLight','PlayExtraAnimation','QueueItem','RemoveCurseMistEffect','RemoveSkinCostume','ResetItemState','RespawnFamiliars','ShootRedCandle','SpawnMawOfVoid','ThrowFriendlyDip','TriggerBookOfVirtues','TryHoldEntity','TryHoldTrinket','UpdateCanShoot','UsePoopSpell'};for _,n in ipairs(methods)do local f=p[n];assert(not pcall(function()f(npc)end));assert(not pcall(function()f({})end));assert(not pcall(function()f(nil)end))end
)lua";
 if(scene=="consumer"){
 consumer=true;WriteAt<std::uint32_t>(itemBytes,kItemConfigItemMaxChargesOffset,5);
 script=R"lua(
 local player=Isaac.GetPlayer();player:AnimatePitfallIn();player:AnimatePitfallOut()
 player:PlayExtraAnimation("HideItem");local data={TriggerPlayer=player,player=player,Item=Isaac.GetItemConfig():GetCollectible(1)}
 data.TriggerPlayer:PlayExtraAnimation("Sad");data.TriggerPlayer:PlayExtraAnimation("Happy");data.player:PlayExtraAnimation("Appear")
 local p=player;p:QueueItem(data.Item,data.Item.MaxCharges,false)
 local touched=player;local laser=touched:SpawnMawOfVoid(15);assert(laser:ToLaser())
 local tear={Parent=player};local high=nil;local t_data={DramamineExplode=function(oncollision,flags)assert(oncollision==false);high=flags end}
 t_data.DramamineExplode(false,tear.Parent:ToPlayer():GetBombFlags());assert(high==BitSet128(0x8000000000000001,0x4000000000000002))
 local e1={Position=Vector(1,2)};local e2={Velocity=Vector(0,-4),Radius=25}
 for i=-1,1,2 do
 local angle=math.rad(e2.Velocity:GetAngleDegrees()+90*i)
 local t=player:FireTechXLaser(e1.Position+Vector(math.cos(angle)*15,math.sin(angle)*15),e2.Velocity:Rotated(30*i),e2.Radius)
 assert(t:ToLaser())
 end
 )lua";
 }
 if(scene=="badguard"){
 g_ModuleBytes[guards::kAddCurseMistEffectEntry]^=1;
 g_ModuleBytes[guards::kAddDollarBillEffectEntry]^=1;
 g_ModuleBytes[guards::kAddPlayerFormCostumeEntry]^=1;
 g_ModuleBytes[guards::kAnimatePitfallInEntry]^=1;
 g_ModuleBytes[guards::kAnimatePitfallOutEntry]^=1;
 g_ModuleBytes[guards::kAnimateTeleportEntry]^=1;
 g_ModuleBytes[guards::kDoZitEffectEntry]^=1;
 g_ModuleBytes[guards::kDropPocketItemEntry]^=1;
 g_ModuleBytes[guards::kFireBrimstoneEntry]^=1;
 g_ModuleBytes[guards::kFireDelayedBrimstoneEntry]^=1;
 g_ModuleBytes[guards::kFireKnifeEntry]^=1;
 g_ModuleBytes[guards::kFireTechXLaserEntry]^=1;
 g_ModuleBytes[guards::kGetBombFlagsEntry]^=1;
 g_ModuleBytes[guards::kGetFlyingOffsetEntry]^=1;
 g_ModuleBytes[guards::kGetLaserOffsetEntry]^=1;
 g_ModuleBytes[guards::kGetNPCTargetEntry]^=1;
 g_ModuleBytes[guards::kHasInvincibilityEntry]^=1;
 g_ModuleBytes[guards::kInitBabySkinEntry]^=1;
 g_ModuleBytes[guards::kIsFullSpriteRenderingEntry]^=1;
 g_ModuleBytes[guards::kIsPosInSpotLightEntry]^=1;
 g_ModuleBytes[guards::kPlayExtraAnimationEntry]^=1;
 g_ModuleBytes[guards::kQueueItemEntry]^=1;
 g_ModuleBytes[guards::kRemoveCurseMistEffectEntry]^=1;
 g_ModuleBytes[guards::kRemoveSkinCostumeEntry]^=1;
 g_ModuleBytes[guards::kResetItemStateEntry]^=1;
 g_ModuleBytes[guards::kRespawnFamiliarsEntry]^=1;
 g_ModuleBytes[guards::kShootRedCandleEntry]^=1;
 g_ModuleBytes[guards::kSpawnMawOfVoidEntry]^=1;
 g_ModuleBytes[guards::kThrowFriendlyDipEntry]^=1;
 g_ModuleBytes[guards::kTriggerBookOfVirtuesEntry]^=1;
 g_ModuleBytes[guards::kTryHoldEntityEntry]^=1;
 g_ModuleBytes[guards::kTryHoldTrinketEntry]^=1;
 g_ModuleBytes[guards::kUpdateCanShootEntry]^=1;
 g_ModuleBytes[guards::kUsePoopSpellEntry]^=1;
script=R"lua(local function guarded(f)local ok,err=pcall(f);assert(not ok and string.find(err,"guard"),tostring(err))end;p=Isaac.GetPlayer();npc=Isaac.FindByType(20)[1];item=Isaac.GetItemConfig():GetCollectible(1);guarded(function()p:AddCurseMistEffect('ignored',{})end);guarded(function()p:AddDollarBillEffect('ignored',{})end);guarded(function()p:AddPlayerFormCostume('4294967295')end);guarded(function()p:AnimatePitfallIn(0)end);guarded(function()p:AnimatePitfallOut('ignored',{})end);guarded(function()p:AnimateTeleport(false)end);guarded(function()p:DoZitEffect(Vector(3,4))end);guarded(function()p:DropPocketItem('4294967295',Vector(13,14))end);guarded(function()p:FireBrimstone(Vector(3,4),npc,2.5)end);guarded(function()p:FireDelayedBrimstone(35.5,npc)end);guarded(function()p:FireKnife(npc,12.5,true,7,8)end);guarded(function()p:FireTechXLaser(Vector(1,2),Vector(3,4),25,npc,2.5)end);guarded(function()p:GetBombFlags(0)end);guarded(function()p:GetFlyingOffset('ignored',{})end);guarded(function()p:GetLaserOffset('4294967295',Vector(3,4))end);guarded(function()p:GetNPCTarget('ignored',{})end);guarded(function()p:HasInvincibility(0x4000000000000001)end);guarded(function()p:InitBabySkin('ignored',{})end);guarded(function()p:IsFullSpriteRendering('ignored',{})end);guarded(function()p:IsPosInSpotLight(Vector(3,4))end);guarded(function()p:PlayExtraAnimation(123)end);guarded(function()p:QueueItem(item,5,0,true,9)end);guarded(function()p:RemoveCurseMistEffect('ignored',{})end);guarded(function()p:RemoveSkinCostume('ignored',{})end);guarded(function()p:ResetItemState('ignored',{})end);guarded(function()p:RespawnFamiliars('ignored',{})end);guarded(function()p:ShootRedCandle(Vector(3,4))end);guarded(function()p:SpawnMawOfVoid('4294967295')end);guarded(function()p:ThrowFriendlyDip('4294967295',Vector(1,2),Vector(3,4))end);guarded(function()p:TriggerBookOfVirtues('4294967295',5)end);guarded(function()p:TryHoldEntity(npc)end);guarded(function()p:TryHoldTrinket('4294967295')end);guarded(function()p:UpdateCanShoot('ignored',{})end);guarded(function()p:UsePoopSpell('4294967295')end);)lua";}
 if(luaL_dostring(L,script)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}
if(scene=="consumer"){if(calls[3]!=1||calls[4]!=1||calls[20]!=4||calls[21]!=1||calls[27]!=1||calls[12]!=1||calls[11]!=2||queued!=itemBytes.data()||queueCharge!=5||queueFlags||queueData||animation!="Appear")return 12;lua_close(L);return 0;}
if(scene=="badguard"){for(auto n:calls)if(n)return 10;lua_close(L);return 0;}
 const unsigned expected[]={1,1,1,2,1,2,1,1,4,1,4,4,4,1,1,1,5,1,1,2,1,3,1,1,1,1,1,1,1,2,1,2,1,1};for(unsigned i=0;i<34;++i){if(calls[i]!=expected[i]||effects[i]!=expected[i]){std::fprintf(stderr,"method %u count %u expected %u\n",i,calls[i],expected[i]);return 2;}}
 if(queued!=nullptr||queueFlags||queueCharge||queueData||!held||!shooting||curse||!dollars||!formCostume||!babySkin||!skinRemoved||pocketDropped!=1||zitShot!=1||candleShot!=1||familiars!=1||book!=2||poop!=1||animation!="TeleportUp")return 3;
 if(scene=="dead"){
 RetireEntityLifetime(AddressOf(g_Entities[kEnemyA]));
 if(luaL_dostring(L,"assert(not pcall(function()p:TryHoldEntity(npc)end));assert(not pcall(function()p:FireDelayedBrimstone(35.5,npc)end));assert(not pcall(function()p:FireKnife(npc)end));assert(not pcall(function()p:FireBrimstone(Vector(3,4),npc)end));assert(not pcall(function()p:FireTechXLaser(Vector(1,2),Vector(3,4),25,npc)end));assert(not savedGetNPCTarget:Exists())"))return 4;
 RetireEntityLifetime(AddressOf(g_Entities[kEffect]));RetireEntityLifetime(AddressOf(g_Entities[kEffectNoQuery]));RetireEntityLifetime(AddressOf(g_Entities[kFamiliar]));
 if(luaL_dostring(L,"assert(not savedFireBrimstone:Exists());assert(not savedFireDelayedBrimstone:Exists());assert(not savedFireTechXLaser:Exists());assert(not savedSpawnMawOfVoid:Exists());assert(not savedFireKnife:Exists());assert(not savedZeroKnife:Exists());assert(not savedThrowFriendlyDip:Exists())"))return 13;
 RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));
 if(luaL_dostring(L,R"lua(assert(not pcall(function()p:AddCurseMistEffect('ignored',{})end));assert(not pcall(function()p:AddDollarBillEffect('ignored',{})end));assert(not pcall(function()p:AddPlayerFormCostume('4294967295')end));assert(not pcall(function()p:AnimatePitfallIn(0)end));assert(not pcall(function()p:AnimatePitfallOut('ignored',{})end));assert(not pcall(function()p:AnimateTeleport(false)end));assert(not pcall(function()p:DoZitEffect(Vector(3,4))end));assert(not pcall(function()p:DropPocketItem('4294967295',Vector(13,14))end));assert(not pcall(function()p:FireBrimstone(Vector(3,4),npc,2.5)end));assert(not pcall(function()p:FireDelayedBrimstone(35.5,npc)end));assert(not pcall(function()p:FireKnife(npc,12.5,true,7,8)end));assert(not pcall(function()p:FireTechXLaser(Vector(1,2),Vector(3,4),25,npc,2.5)end));assert(not pcall(function()p:GetBombFlags(0)end));assert(not pcall(function()p:GetFlyingOffset('ignored',{})end));assert(not pcall(function()p:GetLaserOffset('4294967295',Vector(3,4))end));assert(not pcall(function()p:GetNPCTarget('ignored',{})end));assert(not pcall(function()p:HasInvincibility(0x4000000000000001)end));assert(not pcall(function()p:InitBabySkin('ignored',{})end));assert(not pcall(function()p:IsFullSpriteRendering('ignored',{})end));assert(not pcall(function()p:IsPosInSpotLight(Vector(3,4))end));assert(not pcall(function()p:PlayExtraAnimation(123)end));assert(not pcall(function()p:QueueItem(item,5,0,true,9)end));assert(not pcall(function()p:RemoveCurseMistEffect('ignored',{})end));assert(not pcall(function()p:RemoveSkinCostume('ignored',{})end));assert(not pcall(function()p:ResetItemState('ignored',{})end));assert(not pcall(function()p:RespawnFamiliars('ignored',{})end));assert(not pcall(function()p:ShootRedCandle(Vector(3,4))end));assert(not pcall(function()p:SpawnMawOfVoid('4294967295')end));assert(not pcall(function()p:ThrowFriendlyDip('4294967295',Vector(1,2),Vector(3,4))end));assert(not pcall(function()p:TriggerBookOfVirtues('4294967295',5)end));assert(not pcall(function()p:TryHoldEntity(npc)end));assert(not pcall(function()p:TryHoldTrinket('4294967295')end));assert(not pcall(function()p:UpdateCanShoot('ignored',{})end));assert(not pcall(function()p:UsePoopSpell('4294967295')end));)lua"))return 5;
}
 if(scene=="staleitem"){
 WriteWord(itemVector,8,0);if(luaL_dostring(L,"assert(not pcall(function()p:QueueItem(item)end))"))return 6;
 if(calls[21]!=3)return 7;
 }
 if(scene=="crossbase"){
 std::vector<unsigned char>changed=g_ModuleBytes;const auto base=AddressOf(changed);
 for(auto&entity:g_Entities){std::uintptr_t v{};std::memcpy(&v,entity.data(),8);if(v>=g_EngineBase+kEntityVtableRangeBeginOffset&&v<g_EngineBase+kEntityVtableRangeEndOffset)WriteWord(entity,0,base+(v-g_EngineBase));}LuaRuntime::SetEngineModuleBase(base);
 changed[guards::kAddCurseMistEffectEntry]^=1;
 changed[guards::kAddDollarBillEffectEntry]^=1;
 changed[guards::kAddPlayerFormCostumeEntry]^=1;
 changed[guards::kAnimatePitfallInEntry]^=1;
 changed[guards::kAnimatePitfallOutEntry]^=1;
 changed[guards::kAnimateTeleportEntry]^=1;
 changed[guards::kDoZitEffectEntry]^=1;
 changed[guards::kDropPocketItemEntry]^=1;
 changed[guards::kFireBrimstoneEntry]^=1;
 changed[guards::kFireDelayedBrimstoneEntry]^=1;
 changed[guards::kFireKnifeEntry]^=1;
 changed[guards::kFireTechXLaserEntry]^=1;
 changed[guards::kGetBombFlagsEntry]^=1;
 changed[guards::kGetFlyingOffsetEntry]^=1;
 changed[guards::kGetLaserOffsetEntry]^=1;
 changed[guards::kGetNPCTargetEntry]^=1;
 changed[guards::kHasInvincibilityEntry]^=1;
 changed[guards::kInitBabySkinEntry]^=1;
 changed[guards::kIsFullSpriteRenderingEntry]^=1;
 changed[guards::kIsPosInSpotLightEntry]^=1;
 changed[guards::kPlayExtraAnimationEntry]^=1;
 changed[guards::kQueueItemEntry]^=1;
 changed[guards::kRemoveCurseMistEffectEntry]^=1;
 changed[guards::kRemoveSkinCostumeEntry]^=1;
 changed[guards::kResetItemStateEntry]^=1;
 changed[guards::kRespawnFamiliarsEntry]^=1;
 changed[guards::kShootRedCandleEntry]^=1;
 changed[guards::kSpawnMawOfVoidEntry]^=1;
 changed[guards::kThrowFriendlyDipEntry]^=1;
 changed[guards::kTriggerBookOfVirtuesEntry]^=1;
 changed[guards::kTryHoldEntityEntry]^=1;
 changed[guards::kTryHoldTrinketEntry]^=1;
 changed[guards::kUpdateCanShootEntry]^=1;
 changed[guards::kUsePoopSpellEntry]^=1;
 if(luaL_dostring(L,R"lua(local function guarded(f)local ok,err=pcall(f);assert(not ok and string.find(err,"guard"),tostring(err))end;guarded(function()p:AddCurseMistEffect('ignored',{})end);guarded(function()p:AddDollarBillEffect('ignored',{})end);guarded(function()p:AddPlayerFormCostume('4294967295')end);guarded(function()p:AnimatePitfallIn(0)end);guarded(function()p:AnimatePitfallOut('ignored',{})end);guarded(function()p:AnimateTeleport(false)end);guarded(function()p:DoZitEffect(Vector(3,4))end);guarded(function()p:DropPocketItem('4294967295',Vector(13,14))end);guarded(function()p:FireBrimstone(Vector(3,4),npc,2.5)end);guarded(function()p:FireDelayedBrimstone(35.5,npc)end);guarded(function()p:FireKnife(npc,12.5,true,7,8)end);guarded(function()p:FireTechXLaser(Vector(1,2),Vector(3,4),25,npc,2.5)end);guarded(function()p:GetBombFlags(0)end);guarded(function()p:GetFlyingOffset('ignored',{})end);guarded(function()p:GetLaserOffset('4294967295',Vector(3,4))end);guarded(function()p:GetNPCTarget('ignored',{})end);guarded(function()p:HasInvincibility(0x4000000000000001)end);guarded(function()p:InitBabySkin('ignored',{})end);guarded(function()p:IsFullSpriteRendering('ignored',{})end);guarded(function()p:IsPosInSpotLight(Vector(3,4))end);guarded(function()p:PlayExtraAnimation(123)end);guarded(function()p:QueueItem(item,5,0,true,9)end);guarded(function()p:RemoveCurseMistEffect('ignored',{})end);guarded(function()p:RemoveSkinCostume('ignored',{})end);guarded(function()p:ResetItemState('ignored',{})end);guarded(function()p:RespawnFamiliars('ignored',{})end);guarded(function()p:ShootRedCandle(Vector(3,4))end);guarded(function()p:SpawnMawOfVoid('4294967295')end);guarded(function()p:ThrowFriendlyDip('4294967295',Vector(1,2),Vector(3,4))end);guarded(function()p:TriggerBookOfVirtues('4294967295',5)end);guarded(function()p:TryHoldEntity(npc)end);guarded(function()p:TryHoldTrinket('4294967295')end);guarded(function()p:UpdateCanShoot('ignored',{})end);guarded(function()p:UsePoopSpell('4294967295')end);)lua"))return 8;
}
 for(unsigned i=0;i<34;++i)if(calls[i]!=expected[i])return 9;lua_close(L);return 0;
}
'''
class Player34Behavior(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='api200-player-behavior-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  extra=ROOT/'runtime/src/interfaces/lua/api200_player.cpp'
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source,extra_sources=()if extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_34_native_parameters_results_guards_lifetime_and_side_effects(self):
  for scene in ('normal','badguard','crossbase','dead','staleitem','consumer'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)

class Player34Integration(Player34Behavior):
 def test_34_native_parameters_results_guards_lifetime_and_side_effects(self):
  result=subprocess.run([str(self.binary),"integration"],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
