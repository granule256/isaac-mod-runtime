import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]

MAIN=r'''
#include "interfaces/lua/api100_scalar.hpp"
#include "interfaces/lua/api100_scalar.guards.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
using namespace isaac::runtime;
static unsigned calls[42]{};static std::int32_t signedExpected=17;static std::uint32_t unsignedExpected=17;static bool boolExpected=true;static bool useDefaults=false;
static void Fake0(void*p,std::int32_t a0,std::int32_t a1){assert(p==poolBytes);++calls[0];assert(a0==signedExpected);assert(a1==signedExpected);return;}
static std::int32_t Fake1(void*p,std::int32_t a0){assert(p==poolBytes);++calls[1];assert(a0==signedExpected);return 23;}
static std::int32_t Fake2(void*p,std::uint32_t a0,bool a1,bool a2,bool a3){assert(p==poolBytes);++calls[2];assert(a0==unsignedExpected);assert(a1==boolExpected);assert(a2==boolExpected);assert(a3==boolExpected);return 23;}
static std::int32_t Fake3(void*p,std::uint32_t a0){assert(p==poolBytes);++calls[3];assert(a0==unsignedExpected);return 23;}
static std::int32_t Fake4(void*p,bool a0){assert(p==poolBytes);++calls[4];assert(a0==boolExpected);return 23;}
static bool Fake5(void*p,std::int32_t a0){assert(p==poolBytes);++calls[5];assert(a0==signedExpected);return boolExpected;}
static void Fake6(void*p){assert(p==poolBytes);++calls[6];return;}
static void Fake7(void*p){assert(p==poolBytes);++calls[7];return;}
static void Fake8(void*p){assert(p==g_GameBytes.data());++calls[8];return;}
static void Fake9(void*p,bool a0){assert(p==g_GameBytes.data());++calls[9];assert(a0==boolExpected);return;}
static void Fake10(void*p){assert(p==g_GameBytes.data());++calls[10];return;}
static bool Fake11(void*p,std::int32_t a0){assert(p==g_GameBytes.data());++calls[11];assert(a0==signedExpected);return boolExpected;}
static bool Fake12(void*p){assert(p==g_GameBytes.data());++calls[12];return boolExpected;}
static bool Fake13(void*p,std::int32_t a0){assert(p==g_GameBytes.data());++calls[13];assert(a0==signedExpected);return boolExpected;}
static void Fake14(void*p,std::int32_t a0,std::int32_t a1){assert(p==g_GameBytes.data());++calls[14];assert(a0==signedExpected);assert(a1==signedExpected);return;}
static void Fake15(void*p,bool a0,bool a1){assert(p==g_GameBytes.data());++calls[15];assert(a0==boolExpected);assert(a1==boolExpected);return;}
static bool Fake16(void*p,std::int32_t a0,std::int32_t a1){assert(p==g_GameBytes.data());++calls[16];assert(a0==signedExpected);assert(a1==signedExpected);return boolExpected;}
static void Fake17(void*p){assert(p==g_GameBytes.data());++calls[17];return;}
static void Fake18(void*p){assert(p==g_GameBytes.data());++calls[18];return;}
static void Fake19(void*p){assert(p==g_GameBytes.data());++calls[19];return;}
static void Fake20(void*p,bool a0){assert(p==g_GameBytes.data());++calls[20];assert(a0==boolExpected);return;}
static void Fake21(void*p,std::int32_t a0,std::int32_t a1){assert(p==g_GameBytes.data());++calls[21];assert(a0==signedExpected);assert(a1==signedExpected);return;}
static bool Fake22(void*p,std::int32_t a0,std::int32_t a1){assert(p==roomPointer);++calls[22];assert(a0==signedExpected);assert(a1==signedExpected);return boolExpected;}
static std::int32_t Fake23(void*p){assert(p==roomPointer);++calls[23];return 23;}
static float Fake24(void*p){assert(p==roomPointer);++calls[24];return 37.25F;}
static std::int32_t Fake25(void*p){assert(p==roomPointer);++calls[25];return 23;}
static float Fake26(void*p){assert(p==roomPointer);++calls[26];return 37.25F;}
static std::int32_t Fake27(void*p,std::int32_t a0){assert(p==roomPointer);++calls[27];assert(a0==signedExpected);return 23;}
static bool Fake28(void*p){assert(p==roomPointer);++calls[28];return boolExpected;}
static bool Fake29(void*p){assert(p==roomPointer);++calls[29];return boolExpected;}
static bool Fake30(void*p){assert(p==roomPointer);++calls[30];return boolExpected;}
static void Fake31(void*p){assert(p==roomPointer);++calls[31];return;}
static void Fake32(void*p,std::int32_t a0){assert(p==roomPointer);++calls[32];assert(a0==signedExpected);return;}
static void Fake33(void*p,bool a0,bool a1){assert(p==roomPointer);++calls[33];assert(a0==boolExpected);assert(a1==boolExpected);return;}
static void Fake34(void*p){assert(p==roomPointer);++calls[34];return;}
static void Fake35(void*p){assert(p==roomPointer);++calls[35];return;}
static void Fake36(void*p,bool a0){assert(p==roomPointer);++calls[36];assert(a0==boolExpected);return;}
static bool Fake37(void*p,bool a0,bool a1,bool a2){assert(p==roomPointer);++calls[37];assert(a0==(useDefaults?true:boolExpected));assert(a1==boolExpected);assert(a2==boolExpected);return boolExpected;}
static bool Fake38(void*p,bool a0,bool a1){assert(p==roomPointer);++calls[38];assert(a0==boolExpected);assert(a1==boolExpected);return boolExpected;}
static bool Fake39(void*p,bool a0){assert(p==roomPointer);++calls[39];assert(a0==boolExpected);return boolExpected;}
static bool Fake40(void*p,bool a0,bool a1){assert(p==roomPointer);++calls[40];assert(a0==boolExpected);assert(a1==boolExpected);return boolExpected;}
static bool Fake41(void*p,bool a0){assert(p==roomPointer);++calls[41];assert(a0==boolExpected);return boolExpected;}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);roomPointer=g_RoomBytes.data();LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 Api100ScalarNativeTestBindings bindings{}; namespace guards=api100_scalar;
std::memcpy(g_ModuleBytes.data()+guards::kItemPoolAddBibleUpgradeEntry,guards::kItemPoolAddBibleUpgradeGuard.data(),16);bindings.methods[0]=engine_call::AddressOfFunction(&Fake0);
std::memcpy(g_ModuleBytes.data()+guards::kItemPoolForceAddPillEffectEntry,guards::kItemPoolForceAddPillEffectGuard.data(),16);bindings.methods[1]=engine_call::AddressOfFunction(&Fake1);
std::memcpy(g_ModuleBytes.data()+guards::kItemPoolGetCardEntry,guards::kItemPoolGetCardGuard.data(),16);bindings.methods[2]=engine_call::AddressOfFunction(&Fake2);
std::memcpy(g_ModuleBytes.data()+guards::kItemPoolGetPillEntry,guards::kItemPoolGetPillGuard.data(),16);bindings.methods[3]=engine_call::AddressOfFunction(&Fake3);
std::memcpy(g_ModuleBytes.data()+guards::kItemPoolGetTrinketEntry,guards::kItemPoolGetTrinketGuard.data(),16);bindings.methods[4]=engine_call::AddressOfFunction(&Fake4);
std::memcpy(g_ModuleBytes.data()+guards::kItemPoolRemoveTrinketEntry,guards::kItemPoolRemoveTrinketGuard.data(),16);bindings.methods[5]=engine_call::AddressOfFunction(&Fake5);
std::memcpy(g_ModuleBytes.data()+guards::kItemPoolResetRoomBlacklistEntry,guards::kItemPoolResetRoomBlacklistGuard.data(),16);bindings.methods[6]=engine_call::AddressOfFunction(&Fake6);
std::memcpy(g_ModuleBytes.data()+guards::kItemPoolResetTrinketsEntry,guards::kItemPoolResetTrinketsGuard.data(),16);bindings.methods[7]=engine_call::AddressOfFunction(&Fake7);
std::memcpy(g_ModuleBytes.data()+guards::kLevelApplyBlueMapEffectEntry,guards::kLevelApplyBlueMapEffectGuard.data(),16);bindings.methods[8]=engine_call::AddressOfFunction(&Fake8);
std::memcpy(g_ModuleBytes.data()+guards::kLevelApplyCompassEffectEntry,guards::kLevelApplyCompassEffectGuard.data(),16);bindings.methods[9]=engine_call::AddressOfFunction(&Fake9);
std::memcpy(g_ModuleBytes.data()+guards::kLevelApplyMapEffectEntry,guards::kLevelApplyMapEffectGuard.data(),16);bindings.methods[10]=engine_call::AddressOfFunction(&Fake10);
std::memcpy(g_ModuleBytes.data()+guards::kLevelCanOpenChallengeRoomEntry,guards::kLevelCanOpenChallengeRoomGuard.data(),16);bindings.methods[11]=engine_call::AddressOfFunction(&Fake11);
std::memcpy(g_ModuleBytes.data()+guards::kLevelCanSpawnDevilRoomEntry,guards::kLevelCanSpawnDevilRoomGuard.data(),16);bindings.methods[12]=engine_call::AddressOfFunction(&Fake12);
std::memcpy(g_ModuleBytes.data()+guards::kLevelCanStageHaveCurseOfLabyrinthEntry,guards::kLevelCanStageHaveCurseOfLabyrinthGuard.data(),16);bindings.methods[13]=engine_call::AddressOfFunction(&Fake13);
std::memcpy(g_ModuleBytes.data()+guards::kLevelChangeRoomEntry,guards::kLevelChangeRoomGuard.data(),16);bindings.methods[14]=engine_call::AddressOfFunction(&Fake14);
std::memcpy(g_ModuleBytes.data()+guards::kLevelInitializeDevilAngelRoomEntry,guards::kLevelInitializeDevilAngelRoomGuard.data(),16);bindings.methods[15]=engine_call::AddressOfFunction(&Fake15);
std::memcpy(g_ModuleBytes.data()+guards::kLevelMakeRedRoomDoorEntry,guards::kLevelMakeRedRoomDoorGuard.data(),16);bindings.methods[16]=engine_call::AddressOfFunction(&Fake16);
std::memcpy(g_ModuleBytes.data()+guards::kLevelRemoveCompassEffectEntry,guards::kLevelRemoveCompassEffectGuard.data(),16);bindings.methods[17]=engine_call::AddressOfFunction(&Fake17);
std::memcpy(g_ModuleBytes.data()+guards::kLevelSetRedHeartDamageEntry,guards::kLevelSetRedHeartDamageGuard.data(),16);bindings.methods[18]=engine_call::AddressOfFunction(&Fake18);
std::memcpy(g_ModuleBytes.data()+guards::kLevelShowMapEntry,guards::kLevelShowMapGuard.data(),16);bindings.methods[19]=engine_call::AddressOfFunction(&Fake19);
std::memcpy(g_ModuleBytes.data()+guards::kLevelShowNameEntry,guards::kLevelShowNameGuard.data(),16);bindings.methods[20]=engine_call::AddressOfFunction(&Fake20);
std::memcpy(g_ModuleBytes.data()+guards::kLevelUncoverHiddenDoorEntry,guards::kLevelUncoverHiddenDoorGuard.data(),16);bindings.methods[21]=engine_call::AddressOfFunction(&Fake21);
std::memcpy(g_ModuleBytes.data()+guards::kRoomDamageGridEntry,guards::kRoomDamageGridGuard.data(),16);bindings.methods[22]=engine_call::AddressOfFunction(&Fake22);
std::memcpy(g_ModuleBytes.data()+guards::kRoomGetBrokenWatchStateEntry,guards::kRoomGetBrokenWatchStateGuard.data(),16);bindings.methods[23]=engine_call::AddressOfFunction(&Fake23);
std::memcpy(g_ModuleBytes.data()+guards::kRoomGetDevilRoomChanceEntry,guards::kRoomGetDevilRoomChanceGuard.data(),16);bindings.methods[24]=engine_call::AddressOfFunction(&Fake24);
std::memcpy(g_ModuleBytes.data()+guards::kRoomGetDungeonRockIdxEntry,guards::kRoomGetDungeonRockIdxGuard.data(),16);bindings.methods[25]=engine_call::AddressOfFunction(&Fake25);
std::memcpy(g_ModuleBytes.data()+guards::kRoomGetLightingAlphaEntry,guards::kRoomGetLightingAlphaGuard.data(),16);bindings.methods[26]=engine_call::AddressOfFunction(&Fake26);
std::memcpy(g_ModuleBytes.data()+guards::kRoomGetRandomTileIndexEntry,guards::kRoomGetRandomTileIndexGuard.data(),16);bindings.methods[27]=engine_call::AddressOfFunction(&Fake27);
std::memcpy(g_ModuleBytes.data()+guards::kRoomHasLavaEntry,guards::kRoomHasLavaGuard.data(),16);bindings.methods[28]=engine_call::AddressOfFunction(&Fake28);
std::memcpy(g_ModuleBytes.data()+guards::kRoomHasWaterEntry,guards::kRoomHasWaterGuard.data(),16);bindings.methods[29]=engine_call::AddressOfFunction(&Fake29);
std::memcpy(g_ModuleBytes.data()+guards::kRoomIsLShapedRoomEntry,guards::kRoomIsLShapedRoomGuard.data(),16);bindings.methods[30]=engine_call::AddressOfFunction(&Fake30);
std::memcpy(g_ModuleBytes.data()+guards::kRoomRespawnEnemiesEntry,guards::kRoomRespawnEnemiesGuard.data(),16);bindings.methods[31]=engine_call::AddressOfFunction(&Fake31);
std::memcpy(g_ModuleBytes.data()+guards::kRoomSetBrokenWatchStateEntry,guards::kRoomSetBrokenWatchStateGuard.data(),16);bindings.methods[32]=engine_call::AddressOfFunction(&Fake32);
std::memcpy(g_ModuleBytes.data()+guards::kRoomShopReshuffleEntry,guards::kRoomShopReshuffleGuard.data(),16);bindings.methods[33]=engine_call::AddressOfFunction(&Fake33);
std::memcpy(g_ModuleBytes.data()+guards::kRoomShopRestockFullEntry,guards::kRoomShopRestockFullGuard.data(),16);bindings.methods[34]=engine_call::AddressOfFunction(&Fake34);
std::memcpy(g_ModuleBytes.data()+guards::kRoomShopRestockPartialEntry,guards::kRoomShopRestockPartialGuard.data(),16);bindings.methods[35]=engine_call::AddressOfFunction(&Fake35);
std::memcpy(g_ModuleBytes.data()+guards::kRoomTriggerClearEntry,guards::kRoomTriggerClearGuard.data(),16);bindings.methods[36]=engine_call::AddressOfFunction(&Fake36);
std::memcpy(g_ModuleBytes.data()+guards::kRoomTrySpawnBlueWombDoorEntry,guards::kRoomTrySpawnBlueWombDoorGuard.data(),16);bindings.methods[37]=engine_call::AddressOfFunction(&Fake37);
std::memcpy(g_ModuleBytes.data()+guards::kRoomTrySpawnBossRushDoorEntry,guards::kRoomTrySpawnBossRushDoorGuard.data(),16);bindings.methods[38]=engine_call::AddressOfFunction(&Fake38);
std::memcpy(g_ModuleBytes.data()+guards::kRoomTrySpawnMegaSatanRoomDoorEntry,guards::kRoomTrySpawnMegaSatanRoomDoorGuard.data(),16);bindings.methods[39]=engine_call::AddressOfFunction(&Fake39);
std::memcpy(g_ModuleBytes.data()+guards::kRoomTrySpawnSecretExitEntry,guards::kRoomTrySpawnSecretExitGuard.data(),16);bindings.methods[40]=engine_call::AddressOfFunction(&Fake40);
std::memcpy(g_ModuleBytes.data()+guards::kRoomTrySpawnTheVoidDoorEntry,guards::kRoomTrySpawnTheVoidDoorGuard.data(),16);bindings.methods[41]=engine_call::AddressOfFunction(&Fake41);
SetApi100ScalarNativeTestBindings(bindings); const char*script=R"LUA(
local g=Game(); local room=g:GetRoom();local level=g:GetLevel();local pool=g:GetItemPool(); assert(room and level and pool)
REVEL={room=room}
function REVEL.GetDarkness()
    return REVEL.room:GetLightingAlpha()

    -- if REVEL.IsThereCurse(LevelCurse.CURSE_OF_DARKNESS) then
    --     return 1
    -- elseif TargetDarkness then
    --     if DarkLerpDir >= 0 then
    --         return REVEL.Lerp2Clamp(REVEL.BaseGameDarkness, TargetDarkness, DarkLerp, 0, DarkenFadeinDur)
    --     else
    --         return REVEL.Lerp2Clamp(REVEL.BaseGameDarkness, TargetDarkness, DarkLerp, 0, DarkenFadeoutDur)
    --     end
    -- else
    --     return REVEL.BaseGameDarkness
    -- end
end
assert(REVEL.GetDarkness()==37.25)

assert(pool:AddBibleUpgrade(17,17)==nil,'ItemPool:AddBibleUpgrade')
assert(pool:ForceAddPillEffect(17)==23,'ItemPool:ForceAddPillEffect')
assert(pool:GetCard(17,true,true,true)==23,'ItemPool:GetCard')
assert(pool:GetPill(17)==23,'ItemPool:GetPill')
assert(pool:GetTrinket(true)==23,'ItemPool:GetTrinket')
assert(pool:RemoveTrinket(17)==true,'ItemPool:RemoveTrinket')
assert(pool:ResetRoomBlacklist()==nil,'ItemPool:ResetRoomBlacklist')
assert(pool:ResetTrinkets()==nil,'ItemPool:ResetTrinkets')
assert(level:ApplyBlueMapEffect()==nil,'Level:ApplyBlueMapEffect')
assert(level:ApplyCompassEffect(true)==nil,'Level:ApplyCompassEffect')
assert(level:ApplyMapEffect()==nil,'Level:ApplyMapEffect')
assert(level:CanOpenChallengeRoom(17)==true,'Level:CanOpenChallengeRoom')
assert(level:CanSpawnDevilRoom()==true,'Level:CanSpawnDevilRoom')
assert(level:CanStageHaveCurseOfLabyrinth(17)==true,'Level:CanStageHaveCurseOfLabyrinth')
assert(level:ChangeRoom(17,17)==nil,'Level:ChangeRoom')
assert(level:InitializeDevilAngelRoom(true,true)==nil,'Level:InitializeDevilAngelRoom')
assert(level:MakeRedRoomDoor(17,17)==true,'Level:MakeRedRoomDoor')
assert(level:RemoveCompassEffect()==nil,'Level:RemoveCompassEffect')
assert(level:SetRedHeartDamage()==nil,'Level:SetRedHeartDamage')
assert(level:ShowMap()==nil,'Level:ShowMap')
assert(level:ShowName(true)==nil,'Level:ShowName')
assert(level:UncoverHiddenDoor(17,17)==nil,'Level:UncoverHiddenDoor')
assert(room:DamageGrid(17,17)==true,'Room:DamageGrid')
assert(room:GetBrokenWatchState()==23,'Room:GetBrokenWatchState')
assert(room:GetDevilRoomChance()==37.25,'Room:GetDevilRoomChance')
assert(room:GetDungeonRockIdx()==23,'Room:GetDungeonRockIdx')
assert(room:GetLightingAlpha()==37.25,'Room:GetLightingAlpha')
assert(room:GetRandomTileIndex(17)==23,'Room:GetRandomTileIndex')
assert(room:HasLava()==true,'Room:HasLava')
assert(room:HasWater()==true,'Room:HasWater')
assert(room:IsLShapedRoom()==true,'Room:IsLShapedRoom')
assert(room:RespawnEnemies()==nil,'Room:RespawnEnemies')
assert(room:SetBrokenWatchState(17)==nil,'Room:SetBrokenWatchState')
assert(room:ShopReshuffle(true,true)==nil,'Room:ShopReshuffle')
assert(room:ShopRestockFull()==nil,'Room:ShopRestockFull')
assert(room:ShopRestockPartial()==nil,'Room:ShopRestockPartial')
assert(room:TriggerClear(true)==nil,'Room:TriggerClear')
assert(room:TrySpawnBlueWombDoor(true,true,true)==true,'Room:TrySpawnBlueWombDoor')
assert(room:TrySpawnBossRushDoor(true,true)==true,'Room:TrySpawnBossRushDoor')
assert(room:TrySpawnMegaSatanRoomDoor(true)==true,'Room:TrySpawnMegaSatanRoomDoor')
assert(room:TrySpawnSecretExit(true,true)==true,'Room:TrySpawnSecretExit')
assert(room:TrySpawnTheVoidDoor(true)==true,'Room:TrySpawnTheVoidDoor')
assert(not pcall(function()pool:AddBibleUpgrade({},17)end))
assert(not pcall(function()pool:AddBibleUpgrade(17,{})end))
assert(not pcall(function()pool:ForceAddPillEffect({})end))
assert(not pcall(function()pool:GetCard({},true,true,true)end))
assert(not pcall(function()pool:GetPill({})end))
assert(not pcall(function()pool:RemoveTrinket({})end))
assert(not pcall(function()level:CanOpenChallengeRoom({})end))
assert(not pcall(function()level:CanStageHaveCurseOfLabyrinth({})end))
assert(not pcall(function()level:ChangeRoom({},17)end))
assert(not pcall(function()level:ChangeRoom(17,{})end))
assert(not pcall(function()level:MakeRedRoomDoor({},17)end))
assert(not pcall(function()level:MakeRedRoomDoor(17,{})end))
assert(not pcall(function()level:UncoverHiddenDoor({},17)end))
assert(not pcall(function()level:UncoverHiddenDoor(17,{})end))
assert(not pcall(function()room:DamageGrid({},17)end))
assert(not pcall(function()room:DamageGrid(17,{})end))
assert(not pcall(function()room:GetRandomTileIndex({})end))
assert(not pcall(function()room:SetBrokenWatchState({})end))
)LUA";if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@scalar42.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView errors[16]{};auto n=LuaRuntime::CopyLuaErrorHistory(errors,16);for(std::size_t i=0;i<n;i++)std::fprintf(stderr,"%s\n",errors[i].text);return 1;}for(unsigned i=0;i<42;i++)if(calls[i]!=(i==26?2U:1U))return 2;signedExpected=-1;unsignedExpected=0xffffffffU;const char*overflow=R"LUA(local g=Game();local room=g:GetRoom();local level=g:GetLevel();local pool=g:GetItemPool();assert(room and level and pool)

assert(pool:AddBibleUpgrade(4294967295,4294967295)==nil)
assert(pool:ForceAddPillEffect(4294967295)==23)
assert(pool:GetCard(4294967295,true,true,true)==23)
assert(pool:GetPill(4294967295)==23)
assert(pool:GetTrinket(true)==23)
assert(pool:RemoveTrinket(4294967295)==false)
assert(pool:RemoveTrinket(-1)==false)
assert(pool:RemoveTrinket(32)==false)
assert(pool:RemoveTrinket(4294967313)==false)
assert(pool:ResetRoomBlacklist()==nil)
assert(pool:ResetTrinkets()==nil)
assert(level:ApplyBlueMapEffect()==nil)
assert(level:ApplyCompassEffect(true)==nil)
assert(level:ApplyMapEffect()==nil)
assert(level:CanOpenChallengeRoom(4294967295)==true)
assert(level:CanSpawnDevilRoom()==true)
assert(level:CanStageHaveCurseOfLabyrinth(4294967295)==true)
assert(level:ChangeRoom(4294967295,4294967295)==nil)
assert(level:InitializeDevilAngelRoom(true,true)==nil)
assert(level:MakeRedRoomDoor(4294967295,4294967295)==true)
assert(level:RemoveCompassEffect()==nil)
assert(level:SetRedHeartDamage()==nil)
assert(level:ShowMap()==nil)
assert(level:ShowName(true)==nil)
assert(level:UncoverHiddenDoor(4294967295,4294967295)==nil)
assert(room:DamageGrid(4294967295,4294967295)==true)
assert(room:GetBrokenWatchState()==23)
assert(room:GetDevilRoomChance()==37.25)
assert(room:GetDungeonRockIdx()==23)
assert(room:GetLightingAlpha()==37.25)
assert(room:GetRandomTileIndex(4294967295)==23)
assert(room:HasLava()==true)
assert(room:HasWater()==true)
assert(room:IsLShapedRoom()==true)
assert(room:RespawnEnemies()==nil)
assert(room:SetBrokenWatchState(4294967295)==nil)
assert(room:ShopReshuffle(true,true)==nil)
assert(room:ShopRestockFull()==nil)
assert(room:ShopRestockPartial()==nil)
assert(room:TriggerClear(true)==nil)
assert(room:TrySpawnBlueWombDoor(true,true,true)==true)
assert(room:TrySpawnBossRushDoor(true,true)==true)
assert(room:TrySpawnMegaSatanRoomDoor(true)==true)
assert(room:TrySpawnSecretExit(true,true)==true)
assert(room:TrySpawnTheVoidDoor(true)==true))LUA";if(LuaRuntime::InitializeFromBuffer(overflow,std::strlen(overflow),"@scalar-overflow.lua")!=LuaRuntime::LuaInitResult::Success)return 3;
signedExpected=17;unsignedExpected=17;boolExpected=false;useDefaults=true;const char*missing=R"LUA(local g=Game();local room=g:GetRoom();local level=g:GetLevel();local pool=g:GetItemPool();assert(room and level and pool)

assert(pool:AddBibleUpgrade(17,17)==nil)
assert(not pcall(function()pool:AddBibleUpgrade(nil,nil)end))
assert(not pcall(function()pool.AddBibleUpgrade({},17,17)end))
assert(pool:ForceAddPillEffect(17)==23)
assert(not pcall(function()pool:ForceAddPillEffect(nil)end))
assert(not pcall(function()pool.ForceAddPillEffect({},17)end))
assert(pool:GetCard(17,nil,nil,nil)==23)
assert(not pcall(function()pool:GetCard(nil,true,true,true)end))
assert(not pcall(function()pool.GetCard({},17,true,true,true)end))
assert(pool:GetPill(17)==23)
assert(not pcall(function()pool:GetPill(nil)end))
assert(not pcall(function()pool.GetPill({},17)end))
assert(pool:GetTrinket(nil)==23)
assert(not pcall(function()pool.GetTrinket({},true)end))
assert(pool:RemoveTrinket(17)==false)
assert(not pcall(function()pool:RemoveTrinket(nil)end))
assert(not pcall(function()pool.RemoveTrinket({},17)end))
assert(pool:ResetRoomBlacklist()==nil)
assert(not pcall(function()pool.ResetRoomBlacklist({})end))
assert(pool:ResetTrinkets()==nil)
assert(not pcall(function()pool.ResetTrinkets({})end))
assert(level:ApplyBlueMapEffect()==nil)
assert(not pcall(function()level.ApplyBlueMapEffect({})end))
assert(level:ApplyCompassEffect(nil)==nil)
assert(not pcall(function()level.ApplyCompassEffect({},true)end))
assert(level:ApplyMapEffect()==nil)
assert(not pcall(function()level.ApplyMapEffect({})end))
assert(level:CanOpenChallengeRoom(17)==false)
assert(not pcall(function()level:CanOpenChallengeRoom(nil)end))
assert(not pcall(function()level.CanOpenChallengeRoom({},17)end))
assert(level:CanSpawnDevilRoom()==false)
assert(not pcall(function()level.CanSpawnDevilRoom({})end))
assert(level:CanStageHaveCurseOfLabyrinth(17)==false)
assert(not pcall(function()level:CanStageHaveCurseOfLabyrinth(nil)end))
assert(not pcall(function()level.CanStageHaveCurseOfLabyrinth({},17)end))
assert(level:ChangeRoom(17,17)==nil)
assert(not pcall(function()level:ChangeRoom(nil,nil)end))
assert(not pcall(function()level.ChangeRoom({},17,17)end))
assert(level:InitializeDevilAngelRoom(nil,nil)==nil)
assert(not pcall(function()level.InitializeDevilAngelRoom({},true,true)end))
assert(level:MakeRedRoomDoor(17,17)==false)
assert(not pcall(function()level:MakeRedRoomDoor(nil,nil)end))
assert(not pcall(function()level.MakeRedRoomDoor({},17,17)end))
assert(level:RemoveCompassEffect()==nil)
assert(not pcall(function()level.RemoveCompassEffect({})end))
assert(level:SetRedHeartDamage()==nil)
assert(not pcall(function()level.SetRedHeartDamage({})end))
assert(level:ShowMap()==nil)
assert(not pcall(function()level.ShowMap({})end))
assert(level:ShowName(nil)==nil)
assert(not pcall(function()level.ShowName({},true)end))
assert(level:UncoverHiddenDoor(17,17)==nil)
assert(not pcall(function()level:UncoverHiddenDoor(nil,nil)end))
assert(not pcall(function()level.UncoverHiddenDoor({},17,17)end))
assert(room:DamageGrid(17,17)==false)
assert(not pcall(function()room:DamageGrid(nil,nil)end))
assert(not pcall(function()room.DamageGrid({},17,17)end))
assert(room:GetBrokenWatchState()==23)
assert(not pcall(function()room.GetBrokenWatchState({})end))
assert(room:GetDevilRoomChance()==37.25)
assert(not pcall(function()room.GetDevilRoomChance({})end))
assert(room:GetDungeonRockIdx()==23)
assert(not pcall(function()room.GetDungeonRockIdx({})end))
assert(room:GetLightingAlpha()==37.25)
assert(not pcall(function()room.GetLightingAlpha({})end))
assert(room:GetRandomTileIndex(17)==23)
assert(not pcall(function()room:GetRandomTileIndex(nil)end))
assert(not pcall(function()room.GetRandomTileIndex({},17)end))
assert(room:HasLava()==false)
assert(not pcall(function()room.HasLava({})end))
assert(room:HasWater()==false)
assert(not pcall(function()room.HasWater({})end))
assert(room:IsLShapedRoom()==false)
assert(not pcall(function()room.IsLShapedRoom({})end))
assert(room:RespawnEnemies()==nil)
assert(not pcall(function()room.RespawnEnemies({})end))
assert(room:SetBrokenWatchState(17)==nil)
assert(not pcall(function()room:SetBrokenWatchState(nil)end))
assert(not pcall(function()room.SetBrokenWatchState({},17)end))
assert(room:ShopReshuffle(nil,nil)==nil)
assert(not pcall(function()room.ShopReshuffle({},true,true)end))
assert(room:ShopRestockFull()==nil)
assert(not pcall(function()room.ShopRestockFull({})end))
assert(room:ShopRestockPartial()==nil)
assert(not pcall(function()room.ShopRestockPartial({})end))
assert(room:TriggerClear(nil)==nil)
assert(not pcall(function()room.TriggerClear({},true)end))
assert(room:TrySpawnBlueWombDoor(nil,nil,nil)==false)
assert(not pcall(function()room.TrySpawnBlueWombDoor({},true,true,true)end))
assert(room:TrySpawnBossRushDoor(nil,nil)==false)
assert(not pcall(function()room.TrySpawnBossRushDoor({},true,true)end))
assert(room:TrySpawnMegaSatanRoomDoor(nil)==false)
assert(not pcall(function()room.TrySpawnMegaSatanRoomDoor({},true)end))
assert(room:TrySpawnSecretExit(nil,nil)==false)
assert(not pcall(function()room.TrySpawnSecretExit({},true,true)end))
assert(room:TrySpawnTheVoidDoor(nil)==false)
assert(not pcall(function()room.TrySpawnTheVoidDoor({},true)end)))LUA";if(LuaRuntime::InitializeFromBuffer(missing,std::strlen(missing),"@scalar-missing.lua")!=LuaRuntime::LuaInitResult::Success)return 4;
boolExpected=true;useDefaults=false;const char*truthy=R"LUA(local g=Game();local room=g:GetRoom();local level=g:GetLevel();local pool=g:GetItemPool();assert(room and level and pool)

assert(pool:AddBibleUpgrade(17,17)==nil)
assert(pool:ForceAddPillEffect(17)==23)
assert(pool:GetCard(17,0,0,0)==23)
assert(pool:GetPill(17)==23)
assert(pool:GetTrinket(0)==23)
assert(pool:RemoveTrinket(17)==true)
assert(pool:ResetRoomBlacklist()==nil)
assert(pool:ResetTrinkets()==nil)
assert(level:ApplyBlueMapEffect()==nil)
assert(level:ApplyCompassEffect(0)==nil)
assert(level:ApplyMapEffect()==nil)
assert(level:CanOpenChallengeRoom(17)==true)
assert(level:CanSpawnDevilRoom()==true)
assert(level:CanStageHaveCurseOfLabyrinth(17)==true)
assert(level:ChangeRoom(17,17)==nil)
assert(level:InitializeDevilAngelRoom(0,0)==nil)
assert(level:MakeRedRoomDoor(17,17)==true)
assert(level:RemoveCompassEffect()==nil)
assert(level:SetRedHeartDamage()==nil)
assert(level:ShowMap()==nil)
assert(level:ShowName(0)==nil)
assert(level:UncoverHiddenDoor(17,17)==nil)
assert(room:DamageGrid(17,17)==true)
assert(room:GetBrokenWatchState()==23)
assert(room:GetDevilRoomChance()==37.25)
assert(room:GetDungeonRockIdx()==23)
assert(room:GetLightingAlpha()==37.25)
assert(room:GetRandomTileIndex(17)==23)
assert(room:HasLava()==true)
assert(room:HasWater()==true)
assert(room:IsLShapedRoom()==true)
assert(room:RespawnEnemies()==nil)
assert(room:SetBrokenWatchState(17)==nil)
assert(room:ShopReshuffle(0,0)==nil)
assert(room:ShopRestockFull()==nil)
assert(room:ShopRestockPartial()==nil)
assert(room:TriggerClear(0)==nil)
assert(room:TrySpawnBlueWombDoor(0,0,0)==true)
assert(room:TrySpawnBossRushDoor(0,0)==true)
assert(room:TrySpawnMegaSatanRoomDoor(0)==true)
assert(room:TrySpawnSecretExit(0,0)==true)
assert(room:TrySpawnTheVoidDoor(0)==true))LUA";if(LuaRuntime::InitializeFromBuffer(truthy,std::strlen(truthy),"@scalar-truthy.lua")!=LuaRuntime::LuaInitResult::Success)return 5;
const char*numericstrings=R"LUA(local g=Game();local room=g:GetRoom();local level=g:GetLevel();local pool=g:GetItemPool()
assert(pool:AddBibleUpgrade('17','17')==nil)
assert(pool:ForceAddPillEffect('17')==23)
assert(pool:GetCard('17',true,true,true)==23)
assert(pool:GetPill('17')==23)
assert(pool:GetTrinket(true)==23)
assert(pool:RemoveTrinket('17')==true)
assert(pool:ResetRoomBlacklist()==nil)
assert(pool:ResetTrinkets()==nil)
assert(level:ApplyBlueMapEffect()==nil)
assert(level:ApplyCompassEffect(true)==nil)
assert(level:ApplyMapEffect()==nil)
assert(level:CanOpenChallengeRoom('17')==true)
assert(level:CanSpawnDevilRoom()==true)
assert(level:CanStageHaveCurseOfLabyrinth('17')==true)
assert(level:ChangeRoom('17','17')==nil)
assert(level:InitializeDevilAngelRoom(true,true)==nil)
assert(level:MakeRedRoomDoor('17','17')==true)
assert(level:RemoveCompassEffect()==nil)
assert(level:SetRedHeartDamage()==nil)
assert(level:ShowMap()==nil)
assert(level:ShowName(true)==nil)
assert(level:UncoverHiddenDoor('17','17')==nil)
assert(room:DamageGrid('17','17')==true)
assert(room:GetBrokenWatchState()==23)
assert(room:GetDevilRoomChance()==37.25)
assert(room:GetDungeonRockIdx()==23)
assert(room:GetLightingAlpha()==37.25)
assert(room:GetRandomTileIndex('17')==23)
assert(room:HasLava()==true)
assert(room:HasWater()==true)
assert(room:IsLShapedRoom()==true)
assert(room:RespawnEnemies()==nil)
assert(room:SetBrokenWatchState('17')==nil)
assert(room:ShopReshuffle(true,true)==nil)
assert(room:ShopRestockFull()==nil)
assert(room:ShopRestockPartial()==nil)
assert(room:TriggerClear(true)==nil)
assert(room:TrySpawnBlueWombDoor(true,true,true)==true)
assert(room:TrySpawnBossRushDoor(true,true)==true)
assert(room:TrySpawnMegaSatanRoomDoor(true)==true)
assert(room:TrySpawnSecretExit(true,true)==true)
assert(room:TrySpawnTheVoidDoor(true)==true))LUA";if(LuaRuntime::InitializeFromBuffer(numericstrings,std::strlen(numericstrings),"@scalar-numericstrings.lua")!=LuaRuntime::LuaInitResult::Success)return 9;std::vector<unsigned char> changed=g_ModuleBytes; for(auto& byte:changed)byte=0;WriteWord(changed,kGameOwnerGlobalSlotOffset,AddressOf(g_OwnerSlotBytes));LuaRuntime::SetEngineModuleBase(AddressOf(changed));const char*badguard=R"LUA(local g=Game();local room=g:GetRoom();local level=g:GetLevel();local pool=g:GetItemPool();assert(room and level and pool)

assert(not pcall(function()pool:AddBibleUpgrade(17,17)end))
assert(not pcall(function()pool:ForceAddPillEffect(17)end))
assert(not pcall(function()pool:GetCard(17,true,true,true)end))
assert(not pcall(function()pool:GetPill(17)end))
assert(not pcall(function()pool:GetTrinket(true)end))
assert(not pcall(function()pool:RemoveTrinket(17)end))
assert(not pcall(function()pool:ResetRoomBlacklist()end))
assert(not pcall(function()pool:ResetTrinkets()end))
assert(not pcall(function()level:ApplyBlueMapEffect()end))
assert(not pcall(function()level:ApplyCompassEffect(true)end))
assert(not pcall(function()level:ApplyMapEffect()end))
assert(not pcall(function()level:CanOpenChallengeRoom(17)end))
assert(not pcall(function()level:CanSpawnDevilRoom()end))
assert(not pcall(function()level:CanStageHaveCurseOfLabyrinth(17)end))
assert(not pcall(function()level:ChangeRoom(17,17)end))
assert(not pcall(function()level:InitializeDevilAngelRoom(true,true)end))
assert(not pcall(function()level:MakeRedRoomDoor(17,17)end))
assert(not pcall(function()level:RemoveCompassEffect()end))
assert(not pcall(function()level:SetRedHeartDamage()end))
assert(not pcall(function()level:ShowMap()end))
assert(not pcall(function()level:ShowName(true)end))
assert(not pcall(function()level:UncoverHiddenDoor(17,17)end))
assert(not pcall(function()room:DamageGrid(17,17)end))
assert(not pcall(function()room:GetBrokenWatchState()end))
assert(not pcall(function()room:GetDevilRoomChance()end))
assert(not pcall(function()room:GetDungeonRockIdx()end))
assert(not pcall(function()room:GetLightingAlpha()end))
assert(not pcall(function()room:GetRandomTileIndex(17)end))
assert(not pcall(function()room:HasLava()end))
assert(not pcall(function()room:HasWater()end))
assert(not pcall(function()room:IsLShapedRoom()end))
assert(not pcall(function()room:RespawnEnemies()end))
assert(not pcall(function()room:SetBrokenWatchState(17)end))
assert(not pcall(function()room:ShopReshuffle(true,true)end))
assert(not pcall(function()room:ShopRestockFull()end))
assert(not pcall(function()room:ShopRestockPartial()end))
assert(not pcall(function()room:TriggerClear(true)end))
assert(not pcall(function()room:TrySpawnBlueWombDoor(true,true,true)end))
assert(not pcall(function()room:TrySpawnBossRushDoor(true,true)end))
assert(not pcall(function()room:TrySpawnMegaSatanRoomDoor(true)end))
assert(not pcall(function()room:TrySpawnSecretExit(true,true)end))
assert(not pcall(function()room:TrySpawnTheVoidDoor(true)end)))LUA";if(LuaRuntime::InitializeFromBuffer(badguard,std::strlen(badguard),"@scalar-badguard.lua")!=LuaRuntime::LuaInitResult::Success)return 6;for(unsigned i=0;i<42;i++)if(calls[i]!=(i==26?6U:(i==5?4U:5U)))return 8;return 0;}
'''
class Scalar42Behavior(unittest.TestCase):
 def test_real_owner_registration_and_native_consumption(self):
  prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
  prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
  prefix=prefix.replace('GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**) {\n    return GameItemPoolObservation::GameUnreadable;\n}', 'alignas(8) static unsigned char poolBytes[0x1000];\nstatic std::uint64_t trinketPool[32]{};\nGameItemPoolObservation ReadCurrentGameItemPool(uintptr_t, void**out) {auto begin=reinterpret_cast<std::uintptr_t>(trinketPool);auto end=begin+sizeof(trinketPool);std::memcpy(poolBytes+0xA10,&begin,8);std::memcpy(poolBytes+0xA18,&end,8);*out=poolBytes; return GameItemPoolObservation::Success;}')
  prefix=prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}', 'static void* roomPointer;\nGameRoomObservation ReadCurrentGameRoom(uintptr_t, void**out) {*out=roomPointer;return GameRoomObservation::Success;}')
  with tempfile.TemporaryDirectory(prefix='api100-scalar-behavior-')as d:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+MAIN)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
