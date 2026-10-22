"""第二批主线程48项真实Lua参数、返回、登记与副作用模型。"""
import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include "interfaces/lua/api200_main.hpp"
#include "interfaces/lua/api200_bindings.hpp"
#include "interfaces/lua/api200_main.guards.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/game_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;using Vec=LuaRuntime::VectorHandle;
static unsigned calls[48]{},effects[48]{};static bool expectedBoolean=true;static bool defaultsMode=false;static bool consumerMode=false;static unsigned rewards{},collisions{};static Vec observedSize{};
static std::vector<unsigned char> knifeBytes,pitBytes,poopBytes,plateBytes,doorBytes,rockBytes,managerBytes,managerSlotBytes,nullItemBytes,nullItemSlots;
static void* roomPointer{};static void* want[48]{};
static void Touch(unsigned i,void*p){assert(p==want[i]);++calls[i];++effects[i];}
static bool F0(void*self,void* a0){Touch(0,self);assert(a0==g_Entities[kPlayer].data());return expectedBoolean;}
static void F1(void*self,float a0,Vec a1,std::int32_t a2){Touch(1,self);assert(a0==2.5F);assert(a1.x==3&&a1.y==4);assert(a2==17);observedSize=a1;std::memcpy(static_cast<unsigned char*>(self)+kEntitySizeOffset,&a0,4);return;}
static Vec F2(std::int32_t a0){++calls[2];++effects[2];assert(a0==(consumerMode?0:17));return {11,29};}
static void F3(void*self,float a0,std::int32_t a1,std::uint32_t a2,const Vec* a3,float a4){Touch(3,self);if(defaultsMode){assert(a0==2.5F&&a1==13&&a2==0&&a3&&a3->x==0&&a3->y==0&&a4==15);return;}assert(a0==2.5F);assert(a1==17);assert(a2==17);assert(a3&&a3->x==3&&a3->y==4);assert(a4==15);return;}
static void F4(void*self){Touch(4,self);return;}
static void F5(void*self,float a0,float a1){Touch(5,self);assert(a0==2.5F);assert(a1==2.5F);return;}
static void F6(void*self,float a0){Touch(6,self);assert(a0==2.5F);return;}
static bool F7(void*self,bool a0,void* a1){Touch(7,self);assert(a0==expectedBoolean);assert(a1==g_Entities[kPlayer].data());return expectedBoolean;}
static bool F8(void*self,void* a0,bool a1){Touch(8,self);assert(a0==g_Entities[kPlayer].data());assert(a1==expectedBoolean);return expectedBoolean;}
static void F9(void*self,void* a0){Touch(9,self);assert(a0==(consumerMode?pitBytes.data():rockBytes.data()));const int state=1;std::memcpy(static_cast<unsigned char*>(self)+0x10,&state,4);return;}
static void F10(void*self,bool a0){Touch(10,self);assert(a0==expectedBoolean);static_cast<unsigned char*>(self)[0x1a0]=a0?1:0;return;}
static void F11(void*self){Touch(11,self);++collisions;return;}
static void F12(void*self){Touch(12,self);return;}
static void F13(void*self){Touch(13,self);++rewards;return;}
static void F14(void*self){Touch(14,self);return;}
static void F15(void*self,void* a0,std::int32_t a1){Touch(15,self);assert(a0==g_Entities[kPlayer].data());assert(a1==17);return;}
static void F16(void*self,void* a0,std::int32_t a1){Touch(16,self);assert(a0==g_Entities[kPlayer].data());assert(a1==17);return;}
static void F17(void*self,void* a0){Touch(17,self);assert(a0==g_Entities[kPlayer].data());return;}
static void F18(void*self){Touch(18,self);return;}
static void F19(void*self){Touch(19,self);return;}
static void* F20(void*self,std::int32_t a0){Touch(20,self);assert(a0==1||a0==-1);return a0==1?nullItemBytes.data():nullptr;}
static bool F21(void*self,std::uint32_t a0){Touch(21,self);assert(a0==17);return expectedBoolean;}
static Vec F22(void*self){Touch(22,self);return {11,29};}
static std::int32_t F23(void*self){Touch(23,self);return -17;}
static void F24(void*self,const Vec* a0,bool a1){Touch(24,self);assert(a0&&a0->x==3&&a0->y==4);assert(a1==expectedBoolean);return;}
static std::int32_t F25(void*self){Touch(25,self);return -17;}
static bool F26(void*self,bool a0){Touch(26,self);assert(a0==expectedBoolean);return expectedBoolean;}
static void F27(void*self,float a0,bool a1){Touch(27,self);assert(a0==2.5F);assert(a1==expectedBoolean);return;}
static void F28(void*self,bool a0){Touch(28,self);assert(a0==expectedBoolean);return;}
static void F29(void*self){Touch(29,self);return;}
static void F30(void*self){Touch(30,self);return;}
static void F31(void*self){Touch(31,self);return;}
static bool F32(void*self,const Vec* a0,const Vec* a1,std::int32_t a2,std::int32_t a3,bool a4,bool a5,Vec*out){Touch(32,self);assert(a0&&a0->x==3&&a0->y==4);assert(a1&&a1->x==3&&a1->y==4);assert(a2==(consumerMode?3:17));assert(a3==(consumerMode?0:17));assert(a4==expectedBoolean);assert(a5==expectedBoolean);assert(out);*out={11,29};return expectedBoolean;}
static std::int32_t F33(void*self,const Vec* a0){Touch(33,self);assert(a0&&a0->x==3&&a0->y==4);return -17;}
static Vec F34(void*self,const Vec* a0,const Vec* a1){Touch(34,self);assert(a0&&a0->x==3&&a0->y==4);assert(a1&&a1->x==3&&a1->y==4);return {11,29};}
static std::int32_t F35(void*self,std::uint32_t a0,bool a1){Touch(35,self);assert(a0==17);assert(a1==expectedBoolean);return -17;}
static void F36(void*self,const Vec* a0){Touch(36,self);assert(a0&&a0->x==3&&a0->y==4);return;}
static bool F37(void*self,void* a0,void* a1){Touch(37,self);assert(a0==(consumerMode?pitBytes.data():rockBytes.data()));assert(a1==(consumerMode?pitBytes.data():rockBytes.data()));return expectedBoolean;}
static bool F38(void*self,bool a0,bool a1){Touch(38,self);assert(a0==expectedBoolean);assert(a1==expectedBoolean);return expectedBoolean;}
static bool F39(void*self,bool a0){Touch(39,self);assert(a0==expectedBoolean);return expectedBoolean;}
static bool F40(void*self){Touch(40,self);return expectedBoolean;}
static bool F41(void*self,std::int32_t a0){Touch(41,self);assert(a0==17);return expectedBoolean;}
static std::int32_t F42(){++calls[42];++effects[42];return -17;}
static void F43(){++calls[43];++effects[43];return;}
static void F44(void*self,std::int32_t a0){Touch(44,self);assert(a0==17);return;}
static void F45(void*self){Touch(45,self);return;}
static void F46(void*self,std::int32_t a0){Touch(46,self);assert(a0==17);return;}
static bool F47(void*self,const char* a0,bool a1){Touch(47,self);assert(!std::strcmp(a0,"overlay-name"));assert(a1==expectedBoolean);return false;}
static void Meta(lua_State*L,const char*name,lua_CFunction index,const char*owner){luaL_newmetatable(L,name);lua_newtable(L);if(!std::strcmp(owner,"Game"))static_cast<void>(AttachGameMethods(L));else if(!std::strcmp(owner,"HUD"))static_cast<void>(AttachHudMethods(L));else if(!std::strcmp(owner,"Seeds"))static_cast<void>(AttachSeedsMethods(L));else if(!std::strcmp(owner,"Sprite"))static_cast<void>(AttachSpriteMethods(L));else static_cast<void>(AttachApi200Methods(L,owner));lua_setfield(L,-2,"__methods");lua_pushcfunction(L,index);lua_setfield(L,-2,"__index");lua_pop(L,1);}
static int GameCtor(lua_State*L){auto*p=static_cast<LuaRuntime::GameHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::GameHandle)));p->reserved=0;luaL_getmetatable(L,LuaRuntime::kGameMetatable);lua_setmetatable(L,-2);return 1;}
static void Grid(lua_State*L,void*p,const char*name){auto*h=static_cast<LuaRuntime::GridEntityHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::GridEntityHandle)));h->entity=p;luaL_getmetatable(L,LuaRuntime::kGridEntityMetatable);lua_setmetatable(L,-2);lua_setglobal(L,name);}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 90;const std::string scene=argv[1];
 CreateBlocks();g_GameBytes.resize(0x270000);g_Entities[kFamiliar].resize(0x1000);FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);roomPointer=g_RoomBytes.data();
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 knifeBytes.assign(0xd00,0);WriteWord(knifeBytes,0,g_EngineBase+kEntityKnifeVtableOffset);WriteAt<std::uint32_t>(knifeBytes,kEntityTypeOffset,8);
 WriteWord(g_Entities[kTearNear],0,g_EngineBase+kEntityTearVtableOffset);
 auto initGrid=[&](auto&bytes,auto offset){bytes.assign(0x300,0);WriteWord(bytes,0,g_EngineBase+offset);};
 initGrid(pitBytes,kGridEntity_PitVtableOffset);initGrid(poopBytes,kGridEntity_PoopVtableOffset);initGrid(plateBytes,kGridEntity_PressurePlateVtableOffset);initGrid(doorBytes,kGridEntity_DoorVtableOffset);initGrid(rockBytes,kGridEntity_RockVtableOffset);
 managerBytes.assign(kManagerItemConfigOffset+0x100,0);managerSlotBytes.assign(8,0);nullItemBytes.assign(0xd8,0);nullItemSlots.assign(16,0);
 WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(managerSlotBytes));WriteWord(managerSlotBytes,0,AddressOf(managerBytes));WriteWord(nullItemSlots,8,AddressOf(nullItemBytes));WriteAt<int>(nullItemBytes,4,77);
 WriteWord(managerBytes,kManagerItemConfigOffset+kItemConfigNullItemBeginOffset,AddressOf(nullItemSlots));WriteWord(managerBytes,kManagerItemConfigOffset+kItemConfigNullItemEndOffset,AddressOf(nullItemSlots)+16);
 namespace guards=api200_main;Api200MainNativeTestBindings bindings{};
std::memcpy(g_ModuleBytes.data()+guards::kEntityHasCommonParentWithEntityEntry,guards::kEntityHasCommonParentWithEntityGuard.data(),16);bindings.methods[0]=engine_call::AddressOfFunction(&F0);
want[0]=g_Entities[kPlayer].data();
std::memcpy(g_ModuleBytes.data()+guards::kEntitySetSizeEntry,guards::kEntitySetSizeGuard.data(),16);bindings.methods[1]=engine_call::AddressOfFunction(&F1);
want[1]=g_Entities[kPlayer].data();
std::memcpy(g_ModuleBytes.data()+guards::kEntityFamiliarGetOrbitDistanceEntry,guards::kEntityFamiliarGetOrbitDistanceGuard.data(),16);bindings.methods[2]=engine_call::AddressOfFunction(&F2);
std::memcpy(g_ModuleBytes.data()+guards::kEntityFamiliarPickEnemyTargetEntry,guards::kEntityFamiliarPickEnemyTargetGuard.data(),16);bindings.methods[3]=engine_call::AddressOfFunction(&F3);
want[3]=g_Entities[kFamiliar].data();
std::memcpy(g_ModuleBytes.data()+guards::kEntityKnifeResetEntry,guards::kEntityKnifeResetGuard.data(),16);bindings.methods[4]=engine_call::AddressOfFunction(&F4);
want[4]=knifeBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kEntityKnifeShootEntry,guards::kEntityKnifeShootGuard.data(),16);bindings.methods[5]=engine_call::AddressOfFunction(&F5);
want[5]=knifeBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kEntityTearSetDeadEyeIntensityEntry,guards::kEntityTearSetDeadEyeIntensityGuard.data(),16);bindings.methods[6]=engine_call::AddressOfFunction(&F6);
want[6]=g_Entities[kTearNear].data();
std::memcpy(g_ModuleBytes.data()+guards::kGridEntityDoorTryBlowOpenEntry,guards::kGridEntityDoorTryBlowOpenGuard.data(),16);bindings.methods[7]=engine_call::AddressOfFunction(&F7);
want[7]=doorBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kGridEntityDoorTryUnlockEntry,guards::kGridEntityDoorTryUnlockGuard.data(),16);bindings.methods[8]=engine_call::AddressOfFunction(&F8);
want[8]=doorBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kGridEntityPitMakeBridgeEntry,guards::kGridEntityPitMakeBridgeGuard.data(),16);bindings.methods[9]=engine_call::AddressOfFunction(&F9);
want[9]=pitBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kGridEntityPitSetLadderEntry,guards::kGridEntityPitSetLadderGuard.data(),16);bindings.methods[10]=engine_call::AddressOfFunction(&F10);
want[10]=pitBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kGridEntityPitUpdateCollisionEntry,guards::kGridEntityPitUpdateCollisionGuard.data(),16);bindings.methods[11]=engine_call::AddressOfFunction(&F11);
want[11]=pitBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kGridEntityPoopRespawnRedPoopEntry,guards::kGridEntityPoopRespawnRedPoopGuard.data(),16);bindings.methods[12]=engine_call::AddressOfFunction(&F12);
want[12]=poopBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kGridEntityPressurePlateRewardEntry,guards::kGridEntityPressurePlateRewardGuard.data(),16);bindings.methods[13]=engine_call::AddressOfFunction(&F13);
want[13]=plateBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kHUDAssignPlayerHUDsEntry,guards::kHUDAssignPlayerHUDsGuard.data(),16);bindings.methods[14]=engine_call::AddressOfFunction(&F14);
want[14]=g_GameBytes.data()+kGameHudObjectOffset;
std::memcpy(g_ModuleBytes.data()+guards::kHUDFlashChargeBarEntry,guards::kHUDFlashChargeBarGuard.data(),16);bindings.methods[15]=engine_call::AddressOfFunction(&F15);
want[15]=g_GameBytes.data()+kGameHudObjectOffset;
std::memcpy(g_ModuleBytes.data()+guards::kHUDInvalidateActiveItemEntry,guards::kHUDInvalidateActiveItemGuard.data(),16);bindings.methods[16]=engine_call::AddressOfFunction(&F16);
want[16]=g_GameBytes.data()+kGameHudObjectOffset;
std::memcpy(g_ModuleBytes.data()+guards::kHUDInvalidateCraftingItemEntry,guards::kHUDInvalidateCraftingItemGuard.data(),16);bindings.methods[17]=engine_call::AddressOfFunction(&F17);
want[17]=g_GameBytes.data()+kGameHudObjectOffset;
std::memcpy(g_ModuleBytes.data()+guards::kHUDPostUpdateEntry,guards::kHUDPostUpdateGuard.data(),16);bindings.methods[18]=engine_call::AddressOfFunction(&F18);
want[18]=g_GameBytes.data()+kGameHudObjectOffset;
std::memcpy(g_ModuleBytes.data()+guards::kHUDUpdateEntry,guards::kHUDUpdateGuard.data(),16);bindings.methods[19]=engine_call::AddressOfFunction(&F19);
want[19]=g_GameBytes.data()+kGameHudObjectOffset;
std::memcpy(g_ModuleBytes.data()+guards::kItemConfigGetNullItemEntry,guards::kItemConfigGetNullItemGuard.data(),16);bindings.methods[20]=engine_call::AddressOfFunction(&F20);
want[20]=managerBytes.data()+kManagerItemConfigOffset;
std::memcpy(g_ModuleBytes.data()+guards::kLevelForceHorsemanBossEntry,guards::kLevelForceHorsemanBossGuard.data(),16);bindings.methods[21]=engine_call::AddressOfFunction(&F21);
want[21]=g_GameBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kLevelGetEnterPositionEntry,guards::kLevelGetEnterPositionGuard.data(),16);bindings.methods[22]=engine_call::AddressOfFunction(&F22);
want[22]=g_GameBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kLevelGetNonCompleteRoomIndexEntry,guards::kLevelGetNonCompleteRoomIndexGuard.data(),16);bindings.methods[23]=engine_call::AddressOfFunction(&F23);
want[23]=g_GameBytes.data();
std::memcpy(g_ModuleBytes.data()+guards::kPathFinderEvadeTargetEntry,guards::kPathFinderEvadeTargetGuard.data(),16);bindings.methods[24]=engine_call::AddressOfFunction(&F24);
want[24]=g_Entities[kEnemyA].data()+kEntityNpcPathfinderOffset;
std::memcpy(g_ModuleBytes.data()+guards::kPathFinderGetGridIndexEntry,guards::kPathFinderGetGridIndexGuard.data(),16);bindings.methods[25]=engine_call::AddressOfFunction(&F25);
want[25]=g_Entities[kEnemyA].data()+kEntityNpcPathfinderOffset;
std::memcpy(g_ModuleBytes.data()+guards::kPathFinderMoveRandomlyEntry,guards::kPathFinderMoveRandomlyGuard.data(),16);bindings.methods[26]=engine_call::AddressOfFunction(&F26);
want[26]=g_Entities[kEnemyA].data()+kEntityNpcPathfinderOffset;
std::memcpy(g_ModuleBytes.data()+guards::kPathFinderMoveRandomlyAxisAlignedEntry,guards::kPathFinderMoveRandomlyAxisAlignedGuard.data(),16);bindings.methods[27]=engine_call::AddressOfFunction(&F27);
want[27]=g_Entities[kEnemyA].data()+kEntityNpcPathfinderOffset;
std::memcpy(g_ModuleBytes.data()+guards::kPathFinderMoveRandomlyBossEntry,guards::kPathFinderMoveRandomlyBossGuard.data(),16);bindings.methods[28]=engine_call::AddressOfFunction(&F28);
want[28]=g_Entities[kEnemyA].data()+kEntityNpcPathfinderOffset;
std::memcpy(g_ModuleBytes.data()+guards::kPathFinderResetEntry,guards::kPathFinderResetGuard.data(),16);bindings.methods[29]=engine_call::AddressOfFunction(&F29);
want[29]=g_Entities[kEnemyA].data()+kEntityNpcPathfinderOffset;
std::memcpy(g_ModuleBytes.data()+guards::kPathFinderResetMovementTargetEntry,guards::kPathFinderResetMovementTargetGuard.data(),16);bindings.methods[30]=engine_call::AddressOfFunction(&F30);
want[30]=g_Entities[kEnemyA].data()+kEntityNpcPathfinderOffset;
std::memcpy(g_ModuleBytes.data()+guards::kPathFinderUpdateGridIndexEntry,guards::kPathFinderUpdateGridIndexGuard.data(),16);bindings.methods[31]=engine_call::AddressOfFunction(&F31);
want[31]=g_Entities[kEnemyA].data()+kEntityNpcPathfinderOffset;
std::memcpy(g_ModuleBytes.data()+guards::kRoomCheckLineEntry,guards::kRoomCheckLineGuard.data(),16);bindings.methods[32]=engine_call::AddressOfFunction(&F32);
want[32]=roomPointer;
std::memcpy(g_ModuleBytes.data()+guards::kRoomGetClampedGridIndexEntry,guards::kRoomGetClampedGridIndexGuard.data(),16);bindings.methods[33]=engine_call::AddressOfFunction(&F33);
want[33]=roomPointer;
std::memcpy(g_ModuleBytes.data()+guards::kRoomGetLaserTargetEntry,guards::kRoomGetLaserTargetGuard.data(),16);bindings.methods[34]=engine_call::AddressOfFunction(&F34);
want[34]=roomPointer;
std::memcpy(g_ModuleBytes.data()+guards::kRoomGetSeededCollectibleEntry,guards::kRoomGetSeededCollectibleGuard.data(),16);bindings.methods[35]=engine_call::AddressOfFunction(&F35);
want[35]=roomPointer;
std::memcpy(g_ModuleBytes.data()+guards::kRoomMamaMegaExplosionEntry,guards::kRoomMamaMegaExplosionGuard.data(),16);bindings.methods[36]=engine_call::AddressOfFunction(&F36);
want[36]=roomPointer;
std::memcpy(g_ModuleBytes.data()+guards::kRoomTryMakeBridgeEntry,guards::kRoomTryMakeBridgeGuard.data(),16);bindings.methods[37]=engine_call::AddressOfFunction(&F37);
want[37]=roomPointer;
std::memcpy(g_ModuleBytes.data()+guards::kRoomTrySpawnDevilRoomDoorEntry,guards::kRoomTrySpawnDevilRoomDoorGuard.data(),16);bindings.methods[38]=engine_call::AddressOfFunction(&F38);
want[38]=roomPointer;
std::memcpy(g_ModuleBytes.data()+guards::kRoomTrySpawnSecretShopEntry,guards::kRoomTrySpawnSecretShopGuard.data(),16);bindings.methods[39]=engine_call::AddressOfFunction(&F39);
want[39]=roomPointer;
std::memcpy(g_ModuleBytes.data()+guards::kRoomTrySpawnSpecialQuestDoorEntry,guards::kRoomTrySpawnSpecialQuestDoorGuard.data(),16);bindings.methods[40]=engine_call::AddressOfFunction(&F40);
want[40]=roomPointer;
std::memcpy(g_ModuleBytes.data()+guards::kSeedsCanAddSeedEffectEntry,guards::kSeedsCanAddSeedEffectGuard.data(),16);bindings.methods[41]=engine_call::AddressOfFunction(&F41);
want[41]=g_GameBytes.data()+kGameSeedsObjectOffset;
std::memcpy(g_ModuleBytes.data()+guards::kSeedsCountUnlockedSeedEffectsEntry,guards::kSeedsCountUnlockedSeedEffectsGuard.data(),16);bindings.methods[42]=engine_call::AddressOfFunction(&F42);
std::memcpy(g_ModuleBytes.data()+guards::kSeedsInitSeedInfoEntry,guards::kSeedsInitSeedInfoGuard.data(),16);bindings.methods[43]=engine_call::AddressOfFunction(&F43);
std::memcpy(g_ModuleBytes.data()+guards::kSeedsRemoveBlockingSeedEffectsEntry,guards::kSeedsRemoveBlockingSeedEffectsGuard.data(),16);bindings.methods[44]=engine_call::AddressOfFunction(&F44);
want[44]=g_GameBytes.data()+kGameSeedsObjectOffset;
std::memcpy(g_ModuleBytes.data()+guards::kSeedsResetEntry,guards::kSeedsResetGuard.data(),16);bindings.methods[45]=engine_call::AddressOfFunction(&F45);
want[45]=g_GameBytes.data()+kGameSeedsObjectOffset;
std::memcpy(g_ModuleBytes.data()+guards::kSeedsRestartEntry,guards::kSeedsRestartGuard.data(),16);bindings.methods[46]=engine_call::AddressOfFunction(&F46);
want[46]=g_GameBytes.data()+kGameSeedsObjectOffset;
std::memcpy(g_ModuleBytes.data()+guards::kSpriteSetOverlayAnimationEntry,guards::kSpriteSetOverlayAnimationGuard.data(),16);bindings.methods[47]=engine_call::AddressOfFunction(&F47);
want[47]=g_Entities[kPlayer].data()+kEntitySpriteOffset;
SetApi200MainNativeTestBindings(bindings);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));
 Meta(L,LuaRuntime::kGameMetatable,GameIndex,"Game");luaL_getmetatable(L,LuaRuntime::kGameMetatable);static_cast<void>(AttachGameMethods(L));lua_pushvalue(L,-1);lua_pushcclosure(L,GameIndex,1);lua_setfield(L,-2,"__index");lua_pop(L,1);lua_pushcfunction(L,GameCtor);lua_setglobal(L,"Game");
 luaL_newmetatable(L,LuaRuntime::kRoomMetatable);lua_newtable(L);static_cast<void>(AttachRoomMethods(L));lua_setfield(L,-2,"__index");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kLevelMetatable);static_cast<void>(AttachLevelMethods(L));lua_pushvalue(L,-1);lua_pushcclosure(L,LevelIndex,1);lua_setfield(L,-2,"__index");lua_pop(L,1);
 Meta(L,LuaRuntime::kHudMetatable,NativeClassMethodIndex,"HUD");Meta(L,LuaRuntime::kSeedsMetatable,NativeClassMethodIndex,"Seeds");PublishNativeClass(L,"Seeds",LuaRuntime::kSeedsMetatable);PublishApi200Statics(L,"Seeds");
 luaL_newmetatable(L,LuaRuntime::kGridEntityMetatable);lua_pushcfunction(L,GridEntityIndex);lua_setfield(L,-2,"__index");lua_newtable(L);static_cast<void>(AttachGridEntityMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 Meta(L,LuaRuntime::kGridEntityDoorMetatable,GridEntityDoorIndex,"GridEntityDoor");Meta(L,LuaRuntime::kSpriteMetatable,SpriteIndex,"Sprite");
 RegisterVectorReferenceMetatable(L);luaL_newmetatable(L,LuaRuntime::kVectorMetatable);lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pop(L,1);lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");
 PushEntityCallbackArgument(L,AddressOf(knifeBytes));lua_setglobal(L,"knife");Grid(L,pitBytes.data(),"pit");Grid(L,poopBytes.data(),"poop");Grid(L,plateBytes.data(),"plate");Grid(L,doorBytes.data(),"door");Grid(L,rockBytes.data(),"rock");
if(scene=="badguard"){
std::memset(g_ModuleBytes.data()+guards::kEntityHasCommonParentWithEntityEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kEntitySetSizeEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kEntityFamiliarGetOrbitDistanceEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kEntityFamiliarPickEnemyTargetEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kEntityKnifeResetEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kEntityKnifeShootEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kEntityTearSetDeadEyeIntensityEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kGridEntityDoorTryBlowOpenEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kGridEntityDoorTryUnlockEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kGridEntityPitMakeBridgeEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kGridEntityPitSetLadderEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kGridEntityPitUpdateCollisionEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kGridEntityPoopRespawnRedPoopEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kGridEntityPressurePlateRewardEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kHUDAssignPlayerHUDsEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kHUDFlashChargeBarEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kHUDInvalidateActiveItemEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kHUDInvalidateCraftingItemEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kHUDPostUpdateEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kHUDUpdateEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kItemConfigGetNullItemEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kLevelForceHorsemanBossEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kLevelGetEnterPositionEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kLevelGetNonCompleteRoomIndexEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kPathFinderEvadeTargetEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kPathFinderGetGridIndexEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kPathFinderMoveRandomlyEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kPathFinderMoveRandomlyAxisAlignedEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kPathFinderMoveRandomlyBossEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kPathFinderResetEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kPathFinderResetMovementTargetEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kPathFinderUpdateGridIndexEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kRoomCheckLineEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kRoomGetClampedGridIndexEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kRoomGetLaserTargetEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kRoomGetSeededCollectibleEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kRoomMamaMegaExplosionEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kRoomTryMakeBridgeEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kRoomTrySpawnDevilRoomDoorEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kRoomTrySpawnSecretShopEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kRoomTrySpawnSpecialQuestDoorEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kSeedsCanAddSeedEffectEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kSeedsCountUnlockedSeedEffectsEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kSeedsInitSeedInfoEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kSeedsRemoveBlockingSeedEffectsEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kSeedsResetEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kSeedsRestartEntry,0,16);
std::memset(g_ModuleBytes.data()+guards::kSpriteSetOverlayAnimationEntry,0,16);
const char*bad=R"LUA(p=Isaac.GetPlayer();f=Isaac.FindByType(3)[1]:ToFamiliar();tear=Isaac.FindByType(2)[1]:ToTear();npc=Isaac.FindByType(20)[1]:ToNPC();path=npc.Pathfinder;game=Game();level=game:GetLevel();room=game:GetRoom();hud=game:GetHUD();seed=game:GetSeeds();config=Isaac.GetItemConfig();sprite=p:GetSprite();assert(p and f and tear and path and config)
local ok,msg=pcall(function()p:HasCommonParentWithEntity(p)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Entity:HasCommonParentWithEntity must check its native guard")
local ok,msg=pcall(function()p:SetSize(2.5,Vector(3,4),17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Entity:SetSize must check its native guard")
local ok,msg=pcall(function()EntityFamiliar.GetOrbitDistance(17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"EntityFamiliar:GetOrbitDistance must check its native guard")
local ok,msg=pcall(function()f:PickEnemyTarget(2.5,17,17,Vector(3,4),15)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"EntityFamiliar:PickEnemyTarget must check its native guard")
local ok,msg=pcall(function()knife:Reset()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"EntityKnife:Reset must check its native guard")
local ok,msg=pcall(function()knife:Shoot(2.5,2.5)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"EntityKnife:Shoot must check its native guard")
local ok,msg=pcall(function()tear:SetDeadEyeIntensity(2.5)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"EntityTear:SetDeadEyeIntensity must check its native guard")
local ok,msg=pcall(function()door:TryBlowOpen(true,p)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityDoor:TryBlowOpen must check its native guard")
local ok,msg=pcall(function()door:TryUnlock(p,true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityDoor:TryUnlock must check its native guard")
local ok,msg=pcall(function()pit:MakeBridge(rock)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityPit:MakeBridge must check its native guard")
local ok,msg=pcall(function()pit:SetLadder(true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityPit:SetLadder must check its native guard")
local ok,msg=pcall(function()pit:UpdateCollision()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityPit:UpdateCollision must check its native guard")
local ok,msg=pcall(function()poop:RespawnRedPoop()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityPoop:RespawnRedPoop must check its native guard")
local ok,msg=pcall(function()plate:Reward()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityPressurePlate:Reward must check its native guard")
local ok,msg=pcall(function()hud:AssignPlayerHUDs()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:AssignPlayerHUDs must check its native guard")
local ok,msg=pcall(function()hud:FlashChargeBar(p,17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:FlashChargeBar must check its native guard")
local ok,msg=pcall(function()hud:InvalidateActiveItem(p,17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:InvalidateActiveItem must check its native guard")
local ok,msg=pcall(function()hud:InvalidateCraftingItem(p)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:InvalidateCraftingItem must check its native guard")
local ok,msg=pcall(function()hud:PostUpdate()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:PostUpdate must check its native guard")
local ok,msg=pcall(function()hud:Update()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:Update must check its native guard")
local ok,msg=pcall(function()config:GetNullItem(1)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"ItemConfig:GetNullItem must check its native guard")
local ok,msg=pcall(function()level:ForceHorsemanBoss(17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Level:ForceHorsemanBoss must check its native guard")
local ok,msg=pcall(function()level:GetEnterPosition()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Level:GetEnterPosition must check its native guard")
local ok,msg=pcall(function()level:GetNonCompleteRoomIndex()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Level:GetNonCompleteRoomIndex must check its native guard")
local ok,msg=pcall(function()path:EvadeTarget(Vector(3,4),true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:EvadeTarget must check its native guard")
local ok,msg=pcall(function()path:GetGridIndex()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:GetGridIndex must check its native guard")
local ok,msg=pcall(function()path:MoveRandomly(true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:MoveRandomly must check its native guard")
local ok,msg=pcall(function()path:MoveRandomlyAxisAligned(2.5,true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:MoveRandomlyAxisAligned must check its native guard")
local ok,msg=pcall(function()path:MoveRandomlyBoss(true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:MoveRandomlyBoss must check its native guard")
local ok,msg=pcall(function()path:Reset()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:Reset must check its native guard")
local ok,msg=pcall(function()path:ResetMovementTarget()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:ResetMovementTarget must check its native guard")
local ok,msg=pcall(function()path:UpdateGridIndex()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:UpdateGridIndex must check its native guard")
local ok,msg=pcall(function()room:CheckLine(Vector(3,4),Vector(3,4),17,17,true,true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:CheckLine must check its native guard")
local ok,msg=pcall(function()room:GetClampedGridIndex(Vector(3,4))end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:GetClampedGridIndex must check its native guard")
local ok,msg=pcall(function()room:GetLaserTarget(Vector(3,4),Vector(3,4))end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:GetLaserTarget must check its native guard")
local ok,msg=pcall(function()room:GetSeededCollectible(17,true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:GetSeededCollectible must check its native guard")
local ok,msg=pcall(function()room:MamaMegaExplosion(Vector(3,4))end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:MamaMegaExplosion must check its native guard")
local ok,msg=pcall(function()room:TryMakeBridge(rock,rock)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:TryMakeBridge must check its native guard")
local ok,msg=pcall(function()room:TrySpawnDevilRoomDoor(true,true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:TrySpawnDevilRoomDoor must check its native guard")
local ok,msg=pcall(function()room:TrySpawnSecretShop(true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:TrySpawnSecretShop must check its native guard")
local ok,msg=pcall(function()room:TrySpawnSpecialQuestDoor()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:TrySpawnSpecialQuestDoor must check its native guard")
local ok,msg=pcall(function()seed:CanAddSeedEffect(17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:CanAddSeedEffect must check its native guard")
local ok,msg=pcall(function()Seeds.CountUnlockedSeedEffects()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:CountUnlockedSeedEffects must check its native guard")
local ok,msg=pcall(function()Seeds.InitSeedInfo()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:InitSeedInfo must check its native guard")
local ok,msg=pcall(function()seed:RemoveBlockingSeedEffects(17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:RemoveBlockingSeedEffects must check its native guard")
local ok,msg=pcall(function()seed:Reset()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:Reset must check its native guard")
local ok,msg=pcall(function()seed:Restart(17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:Restart must check its native guard")
local ok,msg=pcall(function()sprite:SetOverlayAnimation("overlay-name",true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Sprite:SetOverlayAnimation must check its native guard")
)LUA";if(luaL_dostring(L,bad)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 4;}for(auto n:calls)if(n)return 5;lua_close(L);return 0;
}
const char*script=R"LUA(p=Isaac.GetPlayer();f=Isaac.FindByType(3)[1]:ToFamiliar();tear=Isaac.FindByType(2)[1]:ToTear();npc=Isaac.FindByType(20)[1]:ToNPC();path=npc.Pathfinder;game=Game();level=game:GetLevel();room=game:GetRoom();hud=game:GetHUD();seed=game:GetSeeds();config=Isaac.GetItemConfig();sprite=p:GetSprite();assert(p and f and tear and path and config)
assert(p:HasCommonParentWithEntity(p)==true)
assert(p:SetSize(2.5,Vector(3,4),17)==nil)
local v=EntityFamiliar.GetOrbitDistance(17);assert(v.X==11 and v.Y==29)
assert(f:PickEnemyTarget(2.5,17,17,Vector(3,4),15)==nil)
assert(knife:Reset()==nil)
assert(knife:Shoot(2.5,2.5)==nil)
assert(tear:SetDeadEyeIntensity(2.5)==nil)
assert(door:TryBlowOpen(true,p)==true)
assert(door:TryUnlock(p,true)==true)
assert(pit:MakeBridge(rock)==nil)
assert(pit:SetLadder(true)==nil)
assert(pit:UpdateCollision()==nil)
assert(poop:RespawnRedPoop()==nil)
assert(plate:Reward()==nil)
assert(hud:AssignPlayerHUDs()==nil)
assert(hud:FlashChargeBar(p,17)==nil)
assert(hud:InvalidateActiveItem(p,17)==nil)
assert(hud:InvalidateCraftingItem(p)==nil)
assert(hud:PostUpdate()==nil)
assert(hud:Update()==nil)
local item=config:GetNullItem(1);assert(item.ID==77)
assert(level:ForceHorsemanBoss(17)==true)
local v=level:GetEnterPosition();assert(v.X==11 and v.Y==29)
assert(level:GetNonCompleteRoomIndex()==-17)
assert(path:EvadeTarget(Vector(3,4),true)==nil)
assert(path:GetGridIndex()==-17)
assert(path:MoveRandomly(true)==true)
assert(path:MoveRandomlyAxisAligned(2.5,true)==nil)
assert(path:MoveRandomlyBoss(true)==nil)
assert(path:Reset()==nil)
assert(path:ResetMovementTarget()==nil)
assert(path:UpdateGridIndex()==nil)
local ok,v=room:CheckLine(Vector(3,4),Vector(3,4),17,17,true,true);assert(ok and v.X==11 and v.Y==29)
assert(room:GetClampedGridIndex(Vector(3,4))==-17)
local v=room:GetLaserTarget(Vector(3,4),Vector(3,4));assert(v.X==11 and v.Y==29)
assert(room:GetSeededCollectible(17,true)==-17)
assert(room:MamaMegaExplosion(Vector(3,4))==nil)
assert(room:TryMakeBridge(rock,rock)==true)
assert(room:TrySpawnDevilRoomDoor(true,true)==true)
assert(room:TrySpawnSecretShop(true)==true)
assert(room:TrySpawnSpecialQuestDoor()==true)
assert(seed:CanAddSeedEffect(17)==true)
assert(Seeds.CountUnlockedSeedEffects()==-17)
assert(Seeds.InitSeedInfo()==nil)
assert(seed:RemoveBlockingSeedEffects(17)==nil)
assert(seed:Reset()==nil)
assert(seed:Restart(17)==nil)
assert(sprite:SetOverlayAnimation("overlay-name",true)==nil)
assert(not pcall(function()p:SetSize({},Vector(3,4),17)end))
assert(not pcall(function()p:SetSize(2.5,{},17)end))
assert(not pcall(function()p:SetSize(2.5,Vector(3,4),{})end))
assert(not pcall(function()EntityFamiliar.GetOrbitDistance({})end))
assert(not pcall(function()f:PickEnemyTarget({},17,17,Vector(3,4),15)end))
assert(not pcall(function()knife:Shoot({},2.5)end))
assert(not pcall(function()knife:Shoot(2.5,{})end))
assert(not pcall(function()tear:SetDeadEyeIntensity({})end))
assert(not pcall(function()hud:FlashChargeBar(p,{})end))
assert(not pcall(function()hud:InvalidateActiveItem(p,{})end))
assert(not pcall(function()config:GetNullItem({})end))
assert(not pcall(function()level:ForceHorsemanBoss({})end))
assert(not pcall(function()path:EvadeTarget({},true)end))
assert(not pcall(function()path:MoveRandomlyAxisAligned({},true)end))
assert(not pcall(function()room:CheckLine({},Vector(3,4),17,17,true,true)end))
assert(not pcall(function()room:CheckLine(Vector(3,4),{},17,17,true,true)end))
assert(not pcall(function()room:CheckLine(Vector(3,4),Vector(3,4),{},17,true,true)end))
assert(not pcall(function()room:GetClampedGridIndex({})end))
assert(not pcall(function()room:GetLaserTarget({},Vector(3,4))end))
assert(not pcall(function()room:GetLaserTarget(Vector(3,4),{})end))
assert(not pcall(function()room:GetSeededCollectible({},true)end))
assert(not pcall(function()room:MamaMegaExplosion({})end))
assert(not pcall(function()seed:CanAddSeedEffect({})end))
assert(not pcall(function()seed:RemoveBlockingSeedEffects({})end))
assert(not pcall(function()seed:Restart({})end))
assert(not pcall(function()sprite:SetOverlayAnimation({},true)end))
)LUA";if(luaL_dostring(L,script)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}for(unsigned i=0;i<48;i++)if(calls[i]!=1||effects[i]!=1)return 2;
 float size{};std::memcpy(&size,g_Entities[kPlayer].data()+kEntitySizeOffset,4);if(size!=2.5F||observedSize.x!=3||observedSize.y!=4||pitBytes[0x1a0]!=1||rewards!=1||collisions!=1)return 10;

 if(scene=="crossbase"){
  std::vector<unsigned char>changed=g_ModuleBytes;const auto newBase=AddressOf(changed);
std::memset(changed.data()+guards::kEntityHasCommonParentWithEntityEntry,0,16);
std::memset(changed.data()+guards::kEntitySetSizeEntry,0,16);
std::memset(changed.data()+guards::kEntityFamiliarGetOrbitDistanceEntry,0,16);
std::memset(changed.data()+guards::kEntityFamiliarPickEnemyTargetEntry,0,16);
std::memset(changed.data()+guards::kEntityKnifeResetEntry,0,16);
std::memset(changed.data()+guards::kEntityKnifeShootEntry,0,16);
std::memset(changed.data()+guards::kEntityTearSetDeadEyeIntensityEntry,0,16);
std::memset(changed.data()+guards::kGridEntityDoorTryBlowOpenEntry,0,16);
std::memset(changed.data()+guards::kGridEntityDoorTryUnlockEntry,0,16);
std::memset(changed.data()+guards::kGridEntityPitMakeBridgeEntry,0,16);
std::memset(changed.data()+guards::kGridEntityPitSetLadderEntry,0,16);
std::memset(changed.data()+guards::kGridEntityPitUpdateCollisionEntry,0,16);
std::memset(changed.data()+guards::kGridEntityPoopRespawnRedPoopEntry,0,16);
std::memset(changed.data()+guards::kGridEntityPressurePlateRewardEntry,0,16);
std::memset(changed.data()+guards::kHUDAssignPlayerHUDsEntry,0,16);
std::memset(changed.data()+guards::kHUDFlashChargeBarEntry,0,16);
std::memset(changed.data()+guards::kHUDInvalidateActiveItemEntry,0,16);
std::memset(changed.data()+guards::kHUDInvalidateCraftingItemEntry,0,16);
std::memset(changed.data()+guards::kHUDPostUpdateEntry,0,16);
std::memset(changed.data()+guards::kHUDUpdateEntry,0,16);
std::memset(changed.data()+guards::kItemConfigGetNullItemEntry,0,16);
std::memset(changed.data()+guards::kLevelForceHorsemanBossEntry,0,16);
std::memset(changed.data()+guards::kLevelGetEnterPositionEntry,0,16);
std::memset(changed.data()+guards::kLevelGetNonCompleteRoomIndexEntry,0,16);
std::memset(changed.data()+guards::kPathFinderEvadeTargetEntry,0,16);
std::memset(changed.data()+guards::kPathFinderGetGridIndexEntry,0,16);
std::memset(changed.data()+guards::kPathFinderMoveRandomlyEntry,0,16);
std::memset(changed.data()+guards::kPathFinderMoveRandomlyAxisAlignedEntry,0,16);
std::memset(changed.data()+guards::kPathFinderMoveRandomlyBossEntry,0,16);
std::memset(changed.data()+guards::kPathFinderResetEntry,0,16);
std::memset(changed.data()+guards::kPathFinderResetMovementTargetEntry,0,16);
std::memset(changed.data()+guards::kPathFinderUpdateGridIndexEntry,0,16);
std::memset(changed.data()+guards::kRoomCheckLineEntry,0,16);
std::memset(changed.data()+guards::kRoomGetClampedGridIndexEntry,0,16);
std::memset(changed.data()+guards::kRoomGetLaserTargetEntry,0,16);
std::memset(changed.data()+guards::kRoomGetSeededCollectibleEntry,0,16);
std::memset(changed.data()+guards::kRoomMamaMegaExplosionEntry,0,16);
std::memset(changed.data()+guards::kRoomTryMakeBridgeEntry,0,16);
std::memset(changed.data()+guards::kRoomTrySpawnDevilRoomDoorEntry,0,16);
std::memset(changed.data()+guards::kRoomTrySpawnSecretShopEntry,0,16);
std::memset(changed.data()+guards::kRoomTrySpawnSpecialQuestDoorEntry,0,16);
std::memset(changed.data()+guards::kSeedsCanAddSeedEffectEntry,0,16);
std::memset(changed.data()+guards::kSeedsCountUnlockedSeedEffectsEntry,0,16);
std::memset(changed.data()+guards::kSeedsInitSeedInfoEntry,0,16);
std::memset(changed.data()+guards::kSeedsRemoveBlockingSeedEffectsEntry,0,16);
std::memset(changed.data()+guards::kSeedsResetEntry,0,16);
std::memset(changed.data()+guards::kSeedsRestartEntry,0,16);
std::memset(changed.data()+guards::kSpriteSetOverlayAnimationEntry,0,16);
const auto delta=newBase-g_EngineBase;
  for(auto&b:g_Entities){std::uintptr_t v{};std::memcpy(&v,b.data(),8);WriteWord(b,0,v+delta);}
  for(auto*b:{&knifeBytes,&pitBytes,&poopBytes,&plateBytes,&doorBytes,&rockBytes}){std::uintptr_t v{};std::memcpy(&v,b->data(),8);WriteWord(*b,0,v+delta);}
  LuaRuntime::SetEngineModuleBase(newBase);
  const char*bad=R"LUA(local ok,msg=pcall(function()p:HasCommonParentWithEntity(p)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Entity:HasCommonParentWithEntity must check its native guard")
local ok,msg=pcall(function()p:SetSize(2.5,Vector(3,4),17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Entity:SetSize must check its native guard")
local ok,msg=pcall(function()EntityFamiliar.GetOrbitDistance(17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"EntityFamiliar:GetOrbitDistance must check its native guard")
local ok,msg=pcall(function()f:PickEnemyTarget(2.5,17,17,Vector(3,4),15)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"EntityFamiliar:PickEnemyTarget must check its native guard")
local ok,msg=pcall(function()knife:Reset()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"EntityKnife:Reset must check its native guard")
local ok,msg=pcall(function()knife:Shoot(2.5,2.5)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"EntityKnife:Shoot must check its native guard")
local ok,msg=pcall(function()tear:SetDeadEyeIntensity(2.5)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"EntityTear:SetDeadEyeIntensity must check its native guard")
local ok,msg=pcall(function()door:TryBlowOpen(true,p)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityDoor:TryBlowOpen must check its native guard")
local ok,msg=pcall(function()door:TryUnlock(p,true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityDoor:TryUnlock must check its native guard")
local ok,msg=pcall(function()pit:MakeBridge(rock)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityPit:MakeBridge must check its native guard")
local ok,msg=pcall(function()pit:SetLadder(true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityPit:SetLadder must check its native guard")
local ok,msg=pcall(function()pit:UpdateCollision()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityPit:UpdateCollision must check its native guard")
local ok,msg=pcall(function()poop:RespawnRedPoop()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityPoop:RespawnRedPoop must check its native guard")
local ok,msg=pcall(function()plate:Reward()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"GridEntityPressurePlate:Reward must check its native guard")
local ok,msg=pcall(function()hud:AssignPlayerHUDs()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:AssignPlayerHUDs must check its native guard")
local ok,msg=pcall(function()hud:FlashChargeBar(p,17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:FlashChargeBar must check its native guard")
local ok,msg=pcall(function()hud:InvalidateActiveItem(p,17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:InvalidateActiveItem must check its native guard")
local ok,msg=pcall(function()hud:InvalidateCraftingItem(p)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:InvalidateCraftingItem must check its native guard")
local ok,msg=pcall(function()hud:PostUpdate()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:PostUpdate must check its native guard")
local ok,msg=pcall(function()hud:Update()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"HUD:Update must check its native guard")
local ok,msg=pcall(function()config:GetNullItem(1)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"ItemConfig:GetNullItem must check its native guard")
local ok,msg=pcall(function()level:ForceHorsemanBoss(17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Level:ForceHorsemanBoss must check its native guard")
local ok,msg=pcall(function()level:GetEnterPosition()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Level:GetEnterPosition must check its native guard")
local ok,msg=pcall(function()level:GetNonCompleteRoomIndex()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Level:GetNonCompleteRoomIndex must check its native guard")
local ok,msg=pcall(function()path:EvadeTarget(Vector(3,4),true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:EvadeTarget must check its native guard")
local ok,msg=pcall(function()path:GetGridIndex()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:GetGridIndex must check its native guard")
local ok,msg=pcall(function()path:MoveRandomly(true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:MoveRandomly must check its native guard")
local ok,msg=pcall(function()path:MoveRandomlyAxisAligned(2.5,true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:MoveRandomlyAxisAligned must check its native guard")
local ok,msg=pcall(function()path:MoveRandomlyBoss(true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:MoveRandomlyBoss must check its native guard")
local ok,msg=pcall(function()path:Reset()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:Reset must check its native guard")
local ok,msg=pcall(function()path:ResetMovementTarget()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:ResetMovementTarget must check its native guard")
local ok,msg=pcall(function()path:UpdateGridIndex()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"PathFinder:UpdateGridIndex must check its native guard")
local ok,msg=pcall(function()room:CheckLine(Vector(3,4),Vector(3,4),17,17,true,true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:CheckLine must check its native guard")
local ok,msg=pcall(function()room:GetClampedGridIndex(Vector(3,4))end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:GetClampedGridIndex must check its native guard")
local ok,msg=pcall(function()room:GetLaserTarget(Vector(3,4),Vector(3,4))end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:GetLaserTarget must check its native guard")
local ok,msg=pcall(function()room:GetSeededCollectible(17,true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:GetSeededCollectible must check its native guard")
local ok,msg=pcall(function()room:MamaMegaExplosion(Vector(3,4))end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:MamaMegaExplosion must check its native guard")
local ok,msg=pcall(function()room:TryMakeBridge(rock,rock)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:TryMakeBridge must check its native guard")
local ok,msg=pcall(function()room:TrySpawnDevilRoomDoor(true,true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:TrySpawnDevilRoomDoor must check its native guard")
local ok,msg=pcall(function()room:TrySpawnSecretShop(true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:TrySpawnSecretShop must check its native guard")
local ok,msg=pcall(function()room:TrySpawnSpecialQuestDoor()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Room:TrySpawnSpecialQuestDoor must check its native guard")
local ok,msg=pcall(function()seed:CanAddSeedEffect(17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:CanAddSeedEffect must check its native guard")
local ok,msg=pcall(function()Seeds.CountUnlockedSeedEffects()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:CountUnlockedSeedEffects must check its native guard")
local ok,msg=pcall(function()Seeds.InitSeedInfo()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:InitSeedInfo must check its native guard")
local ok,msg=pcall(function()seed:RemoveBlockingSeedEffects(17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:RemoveBlockingSeedEffects must check its native guard")
local ok,msg=pcall(function()seed:Reset()end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:Reset must check its native guard")
local ok,msg=pcall(function()seed:Restart(17)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Seeds:Restart must check its native guard")
local ok,msg=pcall(function()sprite:SetOverlayAnimation("overlay-name",true)end);assert(not ok and tostring(msg):find("guard mismatch",1,true),"Sprite:SetOverlayAnimation must check its native guard")
)LUA";if(luaL_dostring(L,bad)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 6;}for(auto n:calls)if(n!=1)return 7;
 }
 if(scene=="deadentity"){
  RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));
  if(luaL_dostring(L,"assert(not pcall(function()p:SetSize(2.5,Vector(3,4),17)end));assert(not pcall(function()hud:FlashChargeBar(p,17)end));assert(not pcall(function()sprite:SetOverlayAnimation('overlay-name')end))"))return 8;
 }


 if(scene=="boundaries"){
  expectedBoolean=false;const char*falseValues=R"LUA(p=Isaac.GetPlayer();f=Isaac.FindByType(3)[1]:ToFamiliar();tear=Isaac.FindByType(2)[1]:ToTear();npc=Isaac.FindByType(20)[1]:ToNPC();path=npc.Pathfinder;game=Game();level=game:GetLevel();room=game:GetRoom();hud=game:GetHUD();seed=game:GetSeeds();config=Isaac.GetItemConfig();sprite=p:GetSprite();assert(p and f and tear and path and config)
assert(p:HasCommonParentWithEntity(p)==false)
assert(p:SetSize(2.5,Vector(3,4),17)==nil)
local v=EntityFamiliar.GetOrbitDistance(17);assert(v.X==11 and v.Y==29)
assert(f:PickEnemyTarget(2.5,17,17,Vector(3,4),15)==nil)
assert(knife:Reset()==nil)
assert(knife:Shoot(2.5,2.5)==nil)
assert(tear:SetDeadEyeIntensity(2.5)==nil)
assert(door:TryBlowOpen(false,p)==false)
assert(door:TryUnlock(p,false)==false)
assert(pit:MakeBridge(rock)==nil)
assert(pit:SetLadder(false)==nil)
assert(pit:UpdateCollision()==nil)
assert(poop:RespawnRedPoop()==nil)
assert(plate:Reward()==nil)
assert(hud:AssignPlayerHUDs()==nil)
assert(hud:FlashChargeBar(p,17)==nil)
assert(hud:InvalidateActiveItem(p,17)==nil)
assert(hud:InvalidateCraftingItem(p)==nil)
assert(hud:PostUpdate()==nil)
assert(hud:Update()==nil)
local item=config:GetNullItem(1);assert(item.ID==77)
assert(level:ForceHorsemanBoss(17)==false)
local v=level:GetEnterPosition();assert(v.X==11 and v.Y==29)
assert(level:GetNonCompleteRoomIndex()==-17)
assert(path:EvadeTarget(Vector(3,4),false)==nil)
assert(path:GetGridIndex()==-17)
assert(path:MoveRandomly(false)==false)
assert(path:MoveRandomlyAxisAligned(2.5,false)==nil)
assert(path:MoveRandomlyBoss(false)==nil)
assert(path:Reset()==nil)
assert(path:ResetMovementTarget()==nil)
assert(path:UpdateGridIndex()==nil)
local ok,v=room:CheckLine(Vector(3,4),Vector(3,4),17,17,false,false);assert(not ok and v.X==11 and v.Y==29)
assert(room:GetClampedGridIndex(Vector(3,4))==-17)
local v=room:GetLaserTarget(Vector(3,4),Vector(3,4));assert(v.X==11 and v.Y==29)
assert(room:GetSeededCollectible(17,false)==-17)
assert(room:MamaMegaExplosion(Vector(3,4))==nil)
assert(room:TryMakeBridge(rock,rock)==false)
assert(room:TrySpawnDevilRoomDoor(false,false)==false)
assert(room:TrySpawnSecretShop(false)==false)
assert(room:TrySpawnSpecialQuestDoor()==false)
assert(seed:CanAddSeedEffect(17)==false)
assert(Seeds.CountUnlockedSeedEffects()==-17)
assert(Seeds.InitSeedInfo()==nil)
assert(seed:RemoveBlockingSeedEffects(17)==nil)
assert(seed:Reset()==nil)
assert(seed:Restart(17)==nil)
assert(sprite:SetOverlayAnimation("overlay-name",false)==nil)
assert(not pcall(function()p:SetSize({},Vector(3,4),17)end))
assert(not pcall(function()p:SetSize(2.5,{},17)end))
assert(not pcall(function()p:SetSize(2.5,Vector(3,4),{})end))
assert(not pcall(function()EntityFamiliar.GetOrbitDistance({})end))
assert(not pcall(function()f:PickEnemyTarget({},17,17,Vector(3,4),15)end))
assert(not pcall(function()knife:Shoot({},2.5)end))
assert(not pcall(function()knife:Shoot(2.5,{})end))
assert(not pcall(function()tear:SetDeadEyeIntensity({})end))
assert(not pcall(function()hud:FlashChargeBar(p,{})end))
assert(not pcall(function()hud:InvalidateActiveItem(p,{})end))
assert(not pcall(function()config:GetNullItem({})end))
assert(not pcall(function()level:ForceHorsemanBoss({})end))
assert(not pcall(function()path:EvadeTarget({},false)end))
assert(not pcall(function()path:MoveRandomlyAxisAligned({},false)end))
assert(not pcall(function()room:CheckLine({},Vector(3,4),17,17,false,false)end))
assert(not pcall(function()room:CheckLine(Vector(3,4),{},17,17,false,false)end))
assert(not pcall(function()room:CheckLine(Vector(3,4),Vector(3,4),{},17,false,false)end))
assert(not pcall(function()room:GetClampedGridIndex({})end))
assert(not pcall(function()room:GetLaserTarget({},Vector(3,4))end))
assert(not pcall(function()room:GetLaserTarget(Vector(3,4),{})end))
assert(not pcall(function()room:GetSeededCollectible({},false)end))
assert(not pcall(function()room:MamaMegaExplosion({})end))
assert(not pcall(function()seed:CanAddSeedEffect({})end))
assert(not pcall(function()seed:RemoveBlockingSeedEffects({})end))
assert(not pcall(function()seed:Restart({})end))
assert(not pcall(function()sprite:SetOverlayAnimation({},false)end))
)LUA";if(luaL_dostring(L,falseValues)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 11;}
  expectedBoolean=true;const char*numbers=R"LUA(p=Isaac.GetPlayer();f=Isaac.FindByType(3)[1]:ToFamiliar();tear=Isaac.FindByType(2)[1]:ToTear();npc=Isaac.FindByType(20)[1]:ToNPC();path=npc.Pathfinder;game=Game();level=game:GetLevel();room=game:GetRoom();hud=game:GetHUD();seed=game:GetSeeds();config=Isaac.GetItemConfig();sprite=p:GetSprite();assert(p and f and tear and path and config)
assert(p:HasCommonParentWithEntity(p)==true)
assert(p:SetSize('2.5',Vector(3,4),'4294967313')==nil)
local v=EntityFamiliar.GetOrbitDistance('4294967313');assert(v.X==11 and v.Y==29)
assert(f:PickEnemyTarget('2.5','4294967313','4294967313',Vector(3,4),15)==nil)
assert(knife:Reset()==nil)
assert(knife:Shoot('2.5','2.5')==nil)
assert(tear:SetDeadEyeIntensity('2.5')==nil)
assert(door:TryBlowOpen(true,p)==true)
assert(door:TryUnlock(p,true)==true)
assert(pit:MakeBridge(rock)==nil)
assert(pit:SetLadder(true)==nil)
assert(pit:UpdateCollision()==nil)
assert(poop:RespawnRedPoop()==nil)
assert(plate:Reward()==nil)
assert(hud:AssignPlayerHUDs()==nil)
assert(hud:FlashChargeBar(p,'4294967313')==nil)
assert(hud:InvalidateActiveItem(p,'4294967313')==nil)
assert(hud:InvalidateCraftingItem(p)==nil)
assert(hud:PostUpdate()==nil)
assert(hud:Update()==nil)
local item=config:GetNullItem(1);assert(item.ID==77)
assert(level:ForceHorsemanBoss('4294967313')==true)
local v=level:GetEnterPosition();assert(v.X==11 and v.Y==29)
assert(level:GetNonCompleteRoomIndex()==-17)
assert(path:EvadeTarget(Vector(3,4),true)==nil)
assert(path:GetGridIndex()==-17)
assert(path:MoveRandomly(true)==true)
assert(path:MoveRandomlyAxisAligned('2.5',true)==nil)
assert(path:MoveRandomlyBoss(true)==nil)
assert(path:Reset()==nil)
assert(path:ResetMovementTarget()==nil)
assert(path:UpdateGridIndex()==nil)
local ok,v=room:CheckLine(Vector(3,4),Vector(3,4),'4294967313','4294967313',true,true);assert(ok and v.X==11 and v.Y==29)
assert(room:GetClampedGridIndex(Vector(3,4))==-17)
local v=room:GetLaserTarget(Vector(3,4),Vector(3,4));assert(v.X==11 and v.Y==29)
assert(room:GetSeededCollectible('4294967313',true)==-17)
assert(room:MamaMegaExplosion(Vector(3,4))==nil)
assert(room:TryMakeBridge(rock,rock)==true)
assert(room:TrySpawnDevilRoomDoor(true,true)==true)
assert(room:TrySpawnSecretShop(true)==true)
assert(room:TrySpawnSpecialQuestDoor()==true)
assert(seed:CanAddSeedEffect('4294967313')==true)
assert(Seeds.CountUnlockedSeedEffects()==-17)
assert(Seeds.InitSeedInfo()==nil)
assert(seed:RemoveBlockingSeedEffects('4294967313')==nil)
assert(seed:Reset()==nil)
assert(seed:Restart('4294967313')==nil)
assert(sprite:SetOverlayAnimation("overlay-name",true)==nil)
assert(not pcall(function()p:SetSize({},Vector(3,4),'4294967313')end))
assert(not pcall(function()p:SetSize('2.5',{},'4294967313')end))
assert(not pcall(function()p:SetSize('2.5',Vector(3,4),{})end))
assert(not pcall(function()EntityFamiliar.GetOrbitDistance({})end))
assert(not pcall(function()f:PickEnemyTarget({},'4294967313','4294967313',Vector(3,4),15)end))
assert(not pcall(function()knife:Shoot({},'2.5')end))
assert(not pcall(function()knife:Shoot('2.5',{})end))
assert(not pcall(function()tear:SetDeadEyeIntensity({})end))
assert(not pcall(function()hud:FlashChargeBar(p,{})end))
assert(not pcall(function()hud:InvalidateActiveItem(p,{})end))
assert(not pcall(function()config:GetNullItem({})end))
assert(not pcall(function()level:ForceHorsemanBoss({})end))
assert(not pcall(function()path:EvadeTarget({},true)end))
assert(not pcall(function()path:MoveRandomlyAxisAligned({},true)end))
assert(not pcall(function()room:CheckLine({},Vector(3,4),'4294967313','4294967313',true,true)end))
assert(not pcall(function()room:CheckLine(Vector(3,4),{},'4294967313','4294967313',true,true)end))
assert(not pcall(function()room:CheckLine(Vector(3,4),Vector(3,4),{},'4294967313',true,true)end))
assert(not pcall(function()room:GetClampedGridIndex({})end))
assert(not pcall(function()room:GetLaserTarget({},Vector(3,4))end))
assert(not pcall(function()room:GetLaserTarget(Vector(3,4),{})end))
assert(not pcall(function()room:GetSeededCollectible({},true)end))
assert(not pcall(function()room:MamaMegaExplosion({})end))
assert(not pcall(function()seed:CanAddSeedEffect({})end))
assert(not pcall(function()seed:RemoveBlockingSeedEffects({})end))
assert(not pcall(function()seed:Restart({})end))
assert(not pcall(function()sprite:SetOverlayAnimation({},true)end))
)LUA";if(luaL_dostring(L,numbers)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 12;}
  defaultsMode=true;if(luaL_dostring(L,"f:PickEnemyTarget(2.5);assert(not pcall(function()f:PickEnemyTarget(2.5,1.5)end))"))return 13;
 }
 if(scene=="consumer"){
  consumerMode=true;expectedBoolean=true;
  const char*consumerA=R"LUA(
local REVEL={game=game,room=room,player=p,config=config,Dynamo={},ITEM={DYNAMO={costume=1}}}
local familiar=f
familiar.OrbitDistance = EntityFamiliar.GetOrbitDistance(0)
assert(familiar.OrbitDistance.X==11 and familiar.OrbitDistance.Y==29)
knife:Reset()
door:TryBlowOpen(true, REVEL.player)
door:TryUnlock(Isaac.GetPlayer(0), true)
local grid=pit
-- 原文ToPit的结果必须是pit而不是其它网格。
grid:ToPit():MakeBridge(grid)
REVEL.game:GetHUD():AssignPlayerHUDs()
Game():GetHUD():PostUpdate()
REVEL.Dynamo.baseCostumeCfg = REVEL.config:GetNullItem(REVEL.ITEM.DYNAMO.costume)
assert(REVEL.Dynamo.baseCostumeCfg.ID==77)
local gridEnt=pit
REVEL.room:TryMakeBridge(gridEnt, gridEnt)
local shootAnim="overlay-name"
sprite:SetOverlayAnimation(shootAnim)
)LUA";if(luaL_dostring(L,consumerA)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 14;}
  expectedBoolean=false;
  const char*consumerB=R"LUA(
local REVEL={room=room};local pathfinder=path;local target={Position=Vector(3,4)}
pathfinder:MoveRandomly(false)
pathfinder:EvadeTarget(target.Position)
npc.Pathfinder:Reset()
local npc={Position=Vector(3,4)};local data={StartPosition=Vector(3,4)}
if REVEL.room:CheckLine(npc.Position,data.StartPosition,3,0,false,false) then
 error("independent native fixture returned false")
end
)LUA";if(luaL_dostring(L,consumerB)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 15;}
  const unsigned used[]={2,4,7,8,9,14,18,20,24,26,29,32,37,47};
  for(unsigned i:used)if(calls[i]!=2||effects[i]!=2)return 16;
 }
 if(scene=="nullitem"){
  if(luaL_dostring(L,"assert(config:GetNullItem(-1)==nil);saved=config:GetNullItem(1)"))return 17;
  lua_getglobal(L,"saved");assert(ItemConfigPointerArgument(L,-1)==AddressOf(nullItemBytes));lua_pop(L,1);
  WriteWord(managerBytes,kManagerItemConfigOffset+kItemConfigNullItemBeginOffset,0);
  WriteWord(managerBytes,kManagerItemConfigOffset+kItemConfigNullItemEndOffset,0);
  lua_getglobal(L,"saved");assert(ItemConfigPointerArgument(L,-1)==0);lua_pop(L,1);
  if(luaL_dostring(L,"assert(not pcall(function()config:GetNullItem(1)end));local ok,value=pcall(function()return saved.ID end);assert(not ok or value==nil)"))return 18;
 }
 if(scene=="deadpath"){
  RetireEntityLifetime(AddressOf(g_Entities[kEnemyA]));
  if(luaL_dostring(L,"assert(not pcall(function()path:Reset()end), 'pathfinder must reject a destroyed NPC owner')")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 3;}
 }
 lua_close(L);return 0;}
'''
class Main48Behavior(unittest.TestCase):
 def test_48_registered_native_consumers(self):
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  source=source.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}', 'extern void* api200Room;\nGameRoomObservation ReadCurrentGameRoom(uintptr_t,void**out){*out=api200Room;return GameRoomObservation::Success;}')
  source=source.replace('static void* roomPointer{};', 'void*api200Room{};\nstatic void* roomPointer{};').replace('roomPointer=g_RoomBytes.data();','roomPointer=g_RoomBytes.data();api200Room=roomPointer;')
  with tempfile.TemporaryDirectory(prefix='api200-main-')as d:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=source)
   for scene in ('normal','badguard','crossbase','deadentity','deadpath','boundaries','consumer','nullitem'):
    result=subprocess.run([str(binary),scene],capture_output=True,text=True);self.assertEqual(result.returncode,0,scene+result.stdout+result.stderr)
