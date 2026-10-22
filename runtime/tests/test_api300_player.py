"""第一组20玩家方法的真实Lua→原生行为判据。"""
import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''

#include "interfaces/lua/api300_player.hpp"
#include "interfaces/lua/api300_player.guards.hpp"
#include "interfaces/lua/api100_native.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;using Vec2=LuaRuntime::VectorHandle;
static void*wanted{};static unsigned headCalls{},bodyCalls{},weaponCalls{},turnCalls{};static float drawnX{},drawnY{};
template<class T>T Field(std::size_t o){T v{};std::memcpy(&v,static_cast<unsigned char*>(wanted)+o,sizeof(v));return v;}
static bool Turn(void*p){assert(p==wanted);++turnCalls;return (Field<std::uint32_t>(0x16b4)>>31)!=0;}
static void* Weapon(void*p){assert(p==wanted);++weaponCalls;const auto a=Field<std::uintptr_t>(0x1758);if(a)return engine_memory::AsObject(a);return engine_memory::AsObject(Field<std::uintptr_t>(0x1760));}
static void Head(void*p,const Vec2&v){assert(p==wanted);assert(v.x==3||v.x==33);assert(v.y==4||v.y==44);++headCalls;drawnX=v.x;drawnY=v.y;}
static void Body(void*p,const Vec2&v){assert(p==wanted);assert(v.x==3||v.x==33);assert(v.y==4||v.y==44);++bodyCalls;drawnX=v.x;drawnY=v.y;}
static void SetupFields(){
 auto&b=g_Entities[kPlayer];
 // 数值来自原件证据中的NS字面偏移；相邻格放诱饵，不能按PC偏移平移或拿邻格凑结果。
 WriteAt<std::uint8_t>(b,0x1c9d,1);WriteAt<std::uint8_t>(b,0x1c9c,0);
 WriteAt<std::uint32_t>(b,0x16b4,0x80000001U);
 for(unsigned i=0;i<4;++i){WriteAt<std::int32_t>(b,0x1968+28*i,77+i);WriteAt<std::int32_t>(b,0x196c+28*i,-9-static_cast<int>(i));WriteAt<std::int32_t>(b,0x1970+28*i,101+i);}
 WriteAt<std::int32_t>(b,0x1d10,-13);WriteAt<std::int32_t>(b,0x1d0c,23);
 WriteAt<std::int32_t>(b,0x19d4,-31);WriteAt<std::int32_t>(b,0x19d8,888);
 WriteAt<std::int32_t>(b,0x16d0,-12);WriteAt<std::int32_t>(b,0x16f0,-17);
 WriteAt<std::uint64_t>(b,0x1aa0,0x8000000000000001ULL);WriteAt<std::uint32_t>(b,0x1aa8,92);WriteAt<std::uint32_t>(b,0x1aac,0xf0000033U);
 WriteAt<float>(b,0x1a04,91);WriteAt<float>(b,0x1a08,92);
 WriteAt<float>(b,0x1a10,3);WriteAt<float>(b,0x1a14,4);
 WriteAt<float>(b,0x1a18,13);WriteAt<float>(b,0x1a1c,14);
 WriteAt<float>(b,0x1a20,93);WriteAt<float>(b,0x1a24,94);
 WriteAt<float>(b,0x1a28,23);WriteAt<float>(b,0x1a2c,24);
 WriteAt<float>(b,0x1a34,33);WriteAt<float>(b,0x1a38,44);
 WriteAt<std::int32_t>(b,0x16e4,11);WriteAt<std::int32_t>(b,0x16e8,12);WriteAt<std::int32_t>(b,0x24a4,13);
 WriteAt<float>(b,0x20e0,37.125F);WriteAt<float>(b,0x1960,4.625F);WriteAt<std::int32_t>(b,0x1914,-41);
 WriteWord(b,0x17c8,AddressOf(g_Entities[kEffect]));WriteWord(b,0x17d0,AddressOf(g_Entities[kPickup]));
 WriteAt<std::uint8_t>(b,0x27e0,1);WriteAt<std::uint8_t>(b,0x27e1,0);
 WriteWord(b,0x1c38,AddressOf(g_Entities[kPickup]));
 WriteAt<std::int32_t>(b,0x1734,7);WriteAt<std::uint32_t>(b,kEntityVariantOffset,1);
 WriteAt<std::int32_t>(b,0x2478,55);WriteAt<std::int32_t>(b,0x247c,56);WriteAt<std::int32_t>(b,0x2480,57);
 WriteAt<std::uint8_t>(b,0x400,1);WriteAt<std::int32_t>(b,0x404,4);
 WriteWord(b,0x1758,AddressOf(g_Entities[kEffect]));WriteWord(b,0x1760,AddressOf(g_Entities[kFamiliar]));
}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;const std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);wanted=g_Entities[kPlayer].data();SetupFields();
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 namespace guards=api300_player;auto guard=[&](auto o,const auto&b){std::memcpy(g_ModuleBytes.data()+o,b.data(),b.size());};
 guard(guards::kLayoutConstructorEntry,guards::kLayoutConstructorGuard);
 guard(guards::kLayoutInitEntry,guards::kLayoutInitGuard);
 guard(guards::kActiveLayoutEntry,guards::kActiveLayoutGuard);
 guard(guards::kCanTurnHeadEntry,guards::kCanTurnHeadGuard);
 guard(guards::kGetActiveWeaponEntityEntry,guards::kGetActiveWeaponEntityGuard);
 guard(guards::kRenderHeadEntry,guards::kRenderHeadGuard);
 guard(guards::kRenderBodyEntry,guards::kRenderBodyGuard);

 Api300PlayerNativeTestBindings bindings{};
 bindings.methods[static_cast<unsigned>(Api300PlayerNative::CanTurnHead)]=engine_call::AddressOfFunction(&Turn);
 bindings.methods[static_cast<unsigned>(Api300PlayerNative::GetActiveWeaponEntity)]=engine_call::AddressOfFunction(&Weapon);
 bindings.methods[static_cast<unsigned>(Api300PlayerNative::RenderHead)]=engine_call::AddressOfFunction(&Head);
 bindings.methods[static_cast<unsigned>(Api300PlayerNative::RenderBody)]=engine_call::AddressOfFunction(&Body);
 SetApi300PlayerNativeTestBindings(bindings);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);luaL_requiref(L,LUA_MATHLIBNAME,luaopen_math,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));
 RegisterVectorReferenceMetatable(L);luaL_newmetatable(L,LuaRuntime::kVectorMetatable);lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,VectorNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachVectorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");
 luaL_getmetatable(L,LuaRuntime::kEntityPlayerMetatable);lua_getfield(L,-1,"__methods");
 lua_pushcfunction(L,Api300EntityPlayerCanShoot);lua_setfield(L,-2,"CanShoot");
 lua_pushcfunction(L,Api300EntityPlayerCanTurnHead);lua_setfield(L,-2,"CanTurnHead");
 lua_pushcfunction(L,Api300EntityPlayerRenderBody);lua_setfield(L,-2,"RenderBody");
 lua_pushcfunction(L,Api300EntityPlayerGetActiveWeaponEntity);lua_setfield(L,-2,"GetActiveWeaponEntity");
 lua_pushcfunction(L,Api300EntityPlayerGetBatteryCharge);lua_setfield(L,-2,"GetBatteryCharge");
 lua_pushcfunction(L,Api300EntityPlayerGetBodyColor);lua_setfield(L,-2,"GetBodyColor");
 lua_pushcfunction(L,Api300EntityPlayerGetHeadColor);lua_setfield(L,-2,"GetHeadColor");
 lua_pushcfunction(L,Api300EntityPlayerGetItemState);lua_setfield(L,-2,"GetItemState");
 lua_pushcfunction(L,Api300EntityPlayerGetJarFlies);lua_setfield(L,-2,"GetJarFlies");
 lua_pushcfunction(L,Api300EntityPlayerGetLastActionTriggers);lua_setfield(L,-2,"GetLastActionTriggers");
 lua_pushcfunction(L,Api300EntityPlayerGetLastDamageFlags);lua_setfield(L,-2,"GetLastDamageFlags");
 lua_pushcfunction(L,Api300EntityPlayerGetLastDirection);lua_setfield(L,-2,"GetLastDirection");
 lua_pushcfunction(L,Api300EntityPlayerGetMovementVector);lua_setfield(L,-2,"GetMovementVector");
 lua_pushcfunction(L,Api300EntityPlayerGetNumBlueFlies);lua_setfield(L,-2,"GetNumBlueFlies");
 lua_pushcfunction(L,Api300EntityPlayerGetNumBlueSpiders);lua_setfield(L,-2,"GetNumBlueSpiders");
 lua_pushcfunction(L,Api300EntityPlayerGetNumGigaBombs);lua_setfield(L,-2,"GetNumGigaBombs");
 lua_pushcfunction(L,Api300EntityPlayerGetRecentMovementVector);lua_setfield(L,-2,"GetRecentMovementVector");
 lua_pushcfunction(L,Api300EntityPlayerGetSmoothBodyRotation);lua_setfield(L,-2,"GetSmoothBodyRotation");
 lua_pushcfunction(L,Api300EntityPlayerGetTearPoisonDamage);lua_setfield(L,-2,"GetTearPoisonDamage");
 lua_pushcfunction(L,Api300EntityPlayerGetTearRangeModifier);lua_setfield(L,-2,"GetTearRangeModifier");
 lua_pushcfunction(L,Api300EntityPlayerGetTotalDamageTaken);lua_setfield(L,-2,"GetTotalDamageTaken");
 lua_pushcfunction(L,Api300EntityPlayerGetTractorBeam);lua_setfield(L,-2,"GetTractorBeam");
 lua_pushcfunction(L,Api300EntityPlayerGetVelocityBeforeUpdate);lua_setfield(L,-2,"GetVelocityBeforeUpdate");
 lua_pushcfunction(L,Api300EntityPlayerHasCurseMistEffect);lua_setfield(L,-2,"HasCurseMistEffect");
 lua_pushcfunction(L,Api300EntityPlayerIsItemQueueEmpty);lua_setfield(L,-2,"IsItemQueueEmpty");
 lua_pushcfunction(L,Api300EntityPlayerIsP2Appearing);lua_setfield(L,-2,"IsP2Appearing");
 lua_pushcfunction(L,Api300EntityPlayerSetBloodCharge);lua_setfield(L,-2,"SetBloodCharge");
 lua_pushcfunction(L,Api300EntityPlayerSetSoulCharge);lua_setfield(L,-2,"SetSoulCharge");
 lua_pushcfunction(L,Api300EntityPlayerRenderHead);lua_setfield(L,-2,"RenderHead");
 lua_pushcfunction(L,Api300EntityPlayerAddControlsCooldown);lua_setfield(L,-2,"AddControlsCooldown");
 lua_pushcfunction(L,Api300EntityPlayerAreControlsEnabled);lua_setfield(L,-2,"AreControlsEnabled");
 lua_pop(L,2);
 const char*script=R"lua(
p=Isaac.GetPlayer();npc=Isaac.FindByType(20)[1];assert(p and npc)
assert(p:CanShoot("ignored",{}) and p:CanTurnHead(false))
assert(p:GetBatteryCharge()==-9 and p:GetBatteryCharge(nil)==-9 and p:GetBatteryCharge(false)==-9)
assert(p:GetBatteryCharge(0)==-9 and p:GetBatteryCharge("4294967296")==-9 and p:GetBatteryCharge(3)==-12)
assert(p:GetBodyColor()==-13 and math.type(p:GetBodyColor())=="integer");assert(p:GetHeadColor()==23)
assert(p:GetItemState()==-31 and p:GetJarFlies()==-12 and p:GetLastActionTriggers()==-17)
assert(p:GetLastDamageFlags()==0x8000000000000001)
last=p:GetLastDirection();movement=p:GetMovementVector();recent=p:GetRecentMovementVector();before=p:GetVelocityBeforeUpdate()
assert(last.X==3 and last.Y==4 and last:Length()==5)
assert(movement.X==13 and movement.Y==14 and recent.X==23 and recent.Y==24 and before.X==33 and before.Y==44)
for _,v in ipairs({last,movement,recent,before})do assert(type(v)=="userdata");assert(not pcall(function()v.X=8 end));assert(not pcall(function()v.Y=8 end))end
assert(p:GetNumBlueFlies()==11 and p:GetNumBlueSpiders()==12 and p:GetNumGigaBombs()==13)
assert(p:GetSmoothBodyRotation()==37.125 and math.type(p:GetSmoothBodyRotation())=="float")
assert(p:GetTearPoisonDamage()==4.625 and math.type(p:GetTearPoisonDamage())=="float")
assert(p:GetTearRangeModifier()==-41 and p:GetTotalDamageTaken()==4026531891)
tractor=p:GetTractorBeam();assert(tractor and tractor.Type==1000)
assert(p:HasCurseMistEffect() and not p:IsItemQueueEmpty() and p:IsP2Appearing() and not p:AreControlsEnabled())
assert(select("#",p:SetBloodCharge("4294967295",false))==0);assert(select("#",p:SetSoulCharge("-2147483648",{}))==0)
assert(select("#",p:AddControlsCooldown(-6))==0);assert(p:AreControlsEnabled())
assert(select("#",p:RenderHead(last))==0);assert(select("#",p:RenderBody(Vector(3,4)))==0)
weapon=p:GetActiveWeaponEntity();assert(weapon.Type==1000)
for _,n in ipairs({"SetBloodCharge","SetSoulCharge","AddControlsCooldown"})do
 for _,v in ipairs({false,true,{},1.5,"no"})do assert(not pcall(function()p[n](p,v)end),n)end
 assert(not pcall(function()p[n](p,nil)end));assert(not pcall(function()p[n](p)end))
end
for _,v in ipairs({true,{},1.5,"no",-1,4})do assert(not pcall(function()p:GetBatteryCharge(v)end))end
for _,n in ipairs({"RenderHead","RenderBody"})do
 assert(not pcall(function()p[n](p)end));assert(not pcall(function()p[n](p,nil)end));assert(not pcall(function()p[n](p,false)end));assert(not pcall(function()p[n](p,{X=3,Y=4})end))
end
for _,n in ipairs({'CanShoot','CanTurnHead','RenderBody','GetActiveWeaponEntity','GetBatteryCharge','GetBodyColor','GetHeadColor','GetItemState','GetJarFlies','GetLastActionTriggers','GetLastDamageFlags','GetLastDirection','GetMovementVector','GetNumBlueFlies','GetNumBlueSpiders','GetNumGigaBombs','GetRecentMovementVector','GetSmoothBodyRotation','GetTearPoisonDamage','GetTearRangeModifier','GetTotalDamageTaken','GetTractorBeam','GetVelocityBeforeUpdate','HasCurseMistEffect','IsItemQueueEmpty','IsP2Appearing','SetBloodCharge','SetSoulCharge','RenderHead','AddControlsCooldown','AreControlsEnabled'})do local f=p[n];assert(not pcall(function()f(npc)end));assert(not pcall(function()f({})end));assert(not pcall(function()f(nil)end))end
)lua";
 if(scene=="consumer"){
 script=R"lua(
 local player=Isaac.GetPlayer();local pos=Vector(3,4)
 player:RenderBody(pos)
 player:RenderHead(pos)
 local ActiveSlot={SLOT_PRIMARY=0,SLOT_SECONDARY=1}
 local charge=player:GetActiveCharge(ActiveSlot.SLOT_SECONDARY)+player:GetBatteryCharge(ActiveSlot.SLOT_SECONDARY)
 assert(charge==68)
 local mov=player:GetMovementVector()
 local len=mov:Length()
 assert(len>0.1)
 local normalized=mov/len
 assert(math.abs(normalized:Length()-1)<0.000001)
 assert(not(player:GetMovementVector():Length()<=0))
 local degrees=player:GetMovementVector():GetAngleDegrees()-180
 assert(type(degrees)=="number" and degrees<0)
 )lua";
 }
 if(scene=="badguard"){
 g_ModuleBytes[guards::kLayoutConstructorEntry]^=1;
 g_ModuleBytes[guards::kLayoutInitEntry]^=1;
 g_ModuleBytes[guards::kActiveLayoutEntry]^=1;
 g_ModuleBytes[guards::kCanTurnHeadEntry]^=1;
 g_ModuleBytes[guards::kGetActiveWeaponEntityEntry]^=1;
 g_ModuleBytes[guards::kRenderHeadEntry]^=1;
 g_ModuleBytes[guards::kRenderBodyEntry]^=1;
script=R"lua(p=Isaac.GetPlayer();local function guarded(f)local ok,err=pcall(f);assert(not ok and string.find(err,"guard"),tostring(err))end;guarded(function()p:CanShoot('ignored',{})end);guarded(function()p:CanTurnHead('ignored',{})end);guarded(function()p:RenderBody(Vector(3,4))end);guarded(function()p:GetActiveWeaponEntity('ignored',{})end);guarded(function()p:GetBatteryCharge(0)end);guarded(function()p:GetBodyColor('ignored',{})end);guarded(function()p:GetHeadColor('ignored',{})end);guarded(function()p:GetItemState('ignored',{})end);guarded(function()p:GetJarFlies('ignored',{})end);guarded(function()p:GetLastActionTriggers('ignored',{})end);guarded(function()p:GetLastDamageFlags('ignored',{})end);guarded(function()p:GetLastDirection('ignored',{})end);guarded(function()p:GetMovementVector('ignored',{})end);guarded(function()p:GetNumBlueFlies('ignored',{})end);guarded(function()p:GetNumBlueSpiders('ignored',{})end);guarded(function()p:GetNumGigaBombs('ignored',{})end);guarded(function()p:GetRecentMovementVector('ignored',{})end);guarded(function()p:GetSmoothBodyRotation('ignored',{})end);guarded(function()p:GetTearPoisonDamage('ignored',{})end);guarded(function()p:GetTearRangeModifier('ignored',{})end);guarded(function()p:GetTotalDamageTaken('ignored',{})end);guarded(function()p:GetTractorBeam('ignored',{})end);guarded(function()p:GetVelocityBeforeUpdate('ignored',{})end);guarded(function()p:HasCurseMistEffect('ignored',{})end);guarded(function()p:IsItemQueueEmpty('ignored',{})end);guarded(function()p:IsP2Appearing('ignored',{})end);guarded(function()p:SetBloodCharge(8)end);guarded(function()p:SetSoulCharge(7)end);guarded(function()p:RenderHead(Vector(3,4))end);guarded(function()p:AddControlsCooldown(1)end);guarded(function()p:AreControlsEnabled('ignored',{})end);)lua";}

 if(luaL_dostring(L,script)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}
 if(scene=="consumer"){if(headCalls!=1||bodyCalls!=1||turnCalls||weaponCalls||drawnX!=3||drawnY!=4)return 15;lua_close(L);return 0;}
 if(scene=="badguard"){if(turnCalls||weaponCalls||headCalls||bodyCalls||Field<std::int32_t>(0x2478)!=55||Field<std::int32_t>(0x247c)!=56||Field<std::int32_t>(0x404)!=4)return 10;lua_close(L);return 0;}
 if(Field<std::int32_t>(0x2478)!=INT32_MIN||Field<std::int32_t>(0x247c)!=-1||Field<std::int32_t>(0x2480)!=57||Field<std::int32_t>(0x404)!=-2)return 2;
 if(turnCalls!=1||weaponCalls!=1||headCalls!=1||bodyCalls!=1||drawnX!=3||drawnY!=4)return 3;
 // 同一引用必须观察后续引擎写者改变，而不是旧值副本；同时独立改变所有标量和条件。
 auto&b=g_Entities[kPlayer];
 WriteAt<std::uint8_t>(b,0x1c9d,0);WriteAt<std::uint32_t>(b,0x16b4,17);
 WriteAt<std::int32_t>(b,0x1d10,14);WriteAt<std::int32_t>(b,0x1d0c,-24);WriteAt<std::int32_t>(b,0x19d4,32);WriteAt<std::int32_t>(b,0x16d0,15);WriteAt<std::int32_t>(b,0x16f0,0x1234567);
 WriteAt<std::uint64_t>(b,0x1aa0,0x4000000000000002ULL);WriteAt<std::uint32_t>(b,0x1aac,19);
 WriteAt<float>(b,0x1a10,33);WriteAt<float>(b,0x1a14,44);WriteAt<float>(b,0x1a18,43);WriteAt<float>(b,0x1a1c,44);WriteAt<float>(b,0x1a28,53);WriteAt<float>(b,0x1a2c,54);WriteAt<float>(b,0x1a34,63);WriteAt<float>(b,0x1a38,64);
 WriteAt<std::int32_t>(b,0x16e4,-11);WriteAt<std::int32_t>(b,0x16e8,-12);WriteAt<std::int32_t>(b,0x24a4,-13);
 WriteAt<float>(b,0x20e0,-18.75F);WriteAt<float>(b,0x1960,-2.5F);WriteAt<std::int32_t>(b,0x1914,41);
 WriteAt<std::uint8_t>(b,0x27e0,0);WriteWord(b,0x1c38,0);WriteAt<std::int32_t>(b,0x1734,0);WriteAt<std::uint8_t>(b,0x400,0);
 WriteWord(b,0x1758,0);WriteWord(b,0x17c8,0);
 if(luaL_dostring(L,R"lua(
 assert(not p:CanShoot() and not p:CanTurnHead())
 assert(p:GetBodyColor()==14 and p:GetHeadColor()==-24 and p:GetItemState()==32 and p:GetJarFlies()==15 and p:GetLastActionTriggers()==0x1234567)
 assert(p:GetLastDamageFlags()==0x4000000000000002 and p:GetTotalDamageTaken()==19)
 assert(last.X==33 and last.Y==44 and last:Length()==55);assert(movement.X==43 and movement.Y==44);assert(recent.X==53 and recent.Y==54);assert(before.X==63 and before.Y==64)
 assert(p:GetLastDirection().X==33 and p:GetMovementVector().X==43 and p:GetRecentMovementVector().X==53 and p:GetVelocityBeforeUpdate().X==63)
 assert(p:GetNumBlueFlies()==-11 and p:GetNumBlueSpiders()==-12 and p:GetNumGigaBombs()==-13)
 assert(p:GetSmoothBodyRotation()==-18.75 and p:GetTearPoisonDamage()==-2.5 and p:GetTearRangeModifier()==41)
 assert(not p:HasCurseMistEffect() and p:IsItemQueueEmpty() and not p:IsP2Appearing() and not p:AreControlsEnabled())
 assert(p:GetTractorBeam()==nil);fallback=p:GetActiveWeaponEntity();assert(fallback:ToFamiliar())
 p:RenderHead(last);p:RenderBody(last)
 )lua")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 4;}
 WriteWord(b,0x1760,0);
 if(luaL_dostring(L,"assert(p:GetActiveWeaponEntity()==nil)"))return 5;
 // x86 add的32位回绕，不夹0，字段getter同可变引擎值一致。
 WriteAt<std::uint8_t>(b,0x400,1);WriteAt<std::int32_t>(b,0x404,INT32_MAX);
 if(luaL_dostring(L,"p:AddControlsCooldown(1);assert(p:AreControlsEnabled());p:SetBloodCharge(7);p:SetSoulCharge(8)"))return 6;
 if(Field<std::int32_t>(0x404)!=INT32_MIN||Field<std::int32_t>(0x247c)!=7||Field<std::int32_t>(0x2478)!=8)return 7;
 if(turnCalls!=2||weaponCalls!=3||headCalls!=2||bodyCalls!=2||drawnX!=33||drawnY!=44)return 8;
 if(scene=="dead"){
 RetireEntityLifetime(AddressOf(g_Entities[kEffect]));RetireEntityLifetime(AddressOf(g_Entities[kFamiliar]));
 if(luaL_dostring(L,"assert(not weapon:Exists());assert(not tractor:Exists());assert(not fallback:Exists())"))return 11;
 RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));
 if(luaL_dostring(L,R"lua(assert(not pcall(function()p:CanShoot('ignored',{})end));assert(not pcall(function()p:CanTurnHead('ignored',{})end));assert(not pcall(function()p:RenderBody(Vector(3,4))end));assert(not pcall(function()p:GetActiveWeaponEntity('ignored',{})end));assert(not pcall(function()p:GetBatteryCharge(0)end));assert(not pcall(function()p:GetBodyColor('ignored',{})end));assert(not pcall(function()p:GetHeadColor('ignored',{})end));assert(not pcall(function()p:GetItemState('ignored',{})end));assert(not pcall(function()p:GetJarFlies('ignored',{})end));assert(not pcall(function()p:GetLastActionTriggers('ignored',{})end));assert(not pcall(function()p:GetLastDamageFlags('ignored',{})end));assert(not pcall(function()p:GetLastDirection('ignored',{})end));assert(not pcall(function()p:GetMovementVector('ignored',{})end));assert(not pcall(function()p:GetNumBlueFlies('ignored',{})end));assert(not pcall(function()p:GetNumBlueSpiders('ignored',{})end));assert(not pcall(function()p:GetNumGigaBombs('ignored',{})end));assert(not pcall(function()p:GetRecentMovementVector('ignored',{})end));assert(not pcall(function()p:GetSmoothBodyRotation('ignored',{})end));assert(not pcall(function()p:GetTearPoisonDamage('ignored',{})end));assert(not pcall(function()p:GetTearRangeModifier('ignored',{})end));assert(not pcall(function()p:GetTotalDamageTaken('ignored',{})end));assert(not pcall(function()p:GetTractorBeam('ignored',{})end));assert(not pcall(function()p:GetVelocityBeforeUpdate('ignored',{})end));assert(not pcall(function()p:HasCurseMistEffect('ignored',{})end));assert(not pcall(function()p:IsItemQueueEmpty('ignored',{})end));assert(not pcall(function()p:IsP2Appearing('ignored',{})end));assert(not pcall(function()p:SetBloodCharge(8)end));assert(not pcall(function()p:SetSoulCharge(7)end));assert(not pcall(function()p:RenderHead(Vector(3,4))end));assert(not pcall(function()p:AddControlsCooldown(1)end));assert(not pcall(function()p:AreControlsEnabled('ignored',{})end));assert(not pcall(function()return last.X end));assert(not pcall(function()return movement:Length()end));assert(not pcall(function()return recent.X end));assert(not pcall(function()return before.X end));)lua"))return 12;
}
 if(scene=="crossbase"){
 std::vector<unsigned char>changed=g_ModuleBytes;const auto base=AddressOf(changed);
 for(auto&entity:g_Entities){std::uintptr_t v{};std::memcpy(&v,entity.data(),8);if(v>=g_EngineBase+kEntityVtableRangeBeginOffset&&v<g_EngineBase+kEntityVtableRangeEndOffset)WriteWord(entity,0,base+(v-g_EngineBase));}
 LuaRuntime::SetEngineModuleBase(base);
 changed[guards::kLayoutConstructorEntry]^=1;
 changed[guards::kLayoutInitEntry]^=1;
 changed[guards::kActiveLayoutEntry]^=1;
 changed[guards::kCanTurnHeadEntry]^=1;
 changed[guards::kGetActiveWeaponEntityEntry]^=1;
 changed[guards::kRenderHeadEntry]^=1;
 changed[guards::kRenderBodyEntry]^=1;
 if(luaL_dostring(L,R"lua(p=Isaac.GetPlayer();local function guarded(f)local ok,err=pcall(f);assert(not ok and string.find(err,"guard"),tostring(err))end;guarded(function()p:CanShoot('ignored',{})end);guarded(function()p:CanTurnHead('ignored',{})end);guarded(function()p:RenderBody(Vector(3,4))end);guarded(function()p:GetActiveWeaponEntity('ignored',{})end);guarded(function()p:GetBatteryCharge(0)end);guarded(function()p:GetBodyColor('ignored',{})end);guarded(function()p:GetHeadColor('ignored',{})end);guarded(function()p:GetItemState('ignored',{})end);guarded(function()p:GetJarFlies('ignored',{})end);guarded(function()p:GetLastActionTriggers('ignored',{})end);guarded(function()p:GetLastDamageFlags('ignored',{})end);guarded(function()p:GetLastDirection('ignored',{})end);guarded(function()p:GetMovementVector('ignored',{})end);guarded(function()p:GetNumBlueFlies('ignored',{})end);guarded(function()p:GetNumBlueSpiders('ignored',{})end);guarded(function()p:GetNumGigaBombs('ignored',{})end);guarded(function()p:GetRecentMovementVector('ignored',{})end);guarded(function()p:GetSmoothBodyRotation('ignored',{})end);guarded(function()p:GetTearPoisonDamage('ignored',{})end);guarded(function()p:GetTearRangeModifier('ignored',{})end);guarded(function()p:GetTotalDamageTaken('ignored',{})end);guarded(function()p:GetTractorBeam('ignored',{})end);guarded(function()p:GetVelocityBeforeUpdate('ignored',{})end);guarded(function()p:HasCurseMistEffect('ignored',{})end);guarded(function()p:IsItemQueueEmpty('ignored',{})end);guarded(function()p:IsP2Appearing('ignored',{})end);guarded(function()p:SetBloodCharge(8)end);guarded(function()p:SetSoulCharge(7)end);guarded(function()p:RenderHead(Vector(3,4))end);guarded(function()p:AddControlsCooldown(1)end);guarded(function()p:AreControlsEnabled('ignored',{})end);)lua"))return 13;
}
 if(turnCalls!=2||weaponCalls!=3||headCalls!=2||bodyCalls!=2)return 14;lua_close(L);return 0;
}
'''
class Player31Behavior(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='api300-player-behavior-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  extra=ROOT/'runtime/src/interfaces/lua/api300_player.cpp'
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source,extra_sources=()if extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_31_methods_live_fields_native_parameters_guards_and_lifetime(self):
  for scene in ('normal','badguard','crossbase','dead','consumer'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)

class Player31Integration(Player31Behavior):
 @classmethod
 def setUpClass(cls):
  global MAIN
  saved=MAIN
  try:
   MAIN=re.sub(r' lua_pushcfunction\(L,Api300EntityPlayer\w+\);lua_setfield\(L,-2,"[^"]+"\);\n','',MAIN)
   super().setUpClass()
  finally:MAIN=saved
