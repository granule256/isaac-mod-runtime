"""第六批玩家API：真实Lua公开入口、native参数/返回值、视图生命周期和base换代。"""
import unittest
from .test_api400_params import run_main
BASELINE_MAIN=r'''
#include "interfaces/lua/api600_player.hpp"
#include "interfaces/lua/api600_player.guards.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "interfaces/lua/bitset128_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cstring>
#include <cstdio>
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;using Vec=LuaRuntime::VectorHandle;
static unsigned tearCalls{},multiCalls{},posCalls{},bombCalls{};
template<class T>T At(const void*p,unsigned o){T v{};std::memcpy(&v,static_cast<const char*>(p)+o,sizeof(v));return v;}
template<class T>void Put(void*p,unsigned o,const T&v){std::memcpy(static_cast<char*>(p)+o,&v,sizeof(v));}
static Api600TearParams Tear(void*self,std::int32_t weapon,float scale,std::int32_t disp,void*source){
 assert(self==g_Entities[kPlayer].data()&&weapon==1);
 assert((scale==1&&disp==1&&!source)||(scale==2.5F&&disp==-3&&source==g_Entities[kEnemyA].data()));++tearCalls;
 Api600TearParams v{};Put(v.bytes,0,std::int32_t{7});Put(v.bytes,4,std::int32_t{9});auto color=DefaultEngineColorMod();color.tint[0]=.25F;Put(v.bytes,8,color);Put(v.bytes,0x38,BitSet128Value{0x8000000000000001ULL,0x123456789abcdef0ULL});Put(v.bytes,0x48,3.5F*scale);Put(v.bytes,0x4c,1.25F);Put(v.bytes,0x50,-12.0F);return v;}
static Api600MultiShotParams Multi(void*self,std::int32_t weapon){assert(self==g_Entities[kPlayer].data()&&weapon==1);++multiCalls;Api600MultiShotParams v{};for(unsigned i=0;i<sizeof(v.bytes);++i)v.bytes[i]=static_cast<unsigned char>(i+17);return v;}
static Api600PosVel Pos(std::int32_t loop,std::int32_t weapon,Vec direction,float speed,Api600MultiShotParams params){assert(loop==2&&weapon==1&&direction.x==3&&direction.y==4&&speed==2.5F);for(unsigned i=0;i<sizeof(params.bytes);++i)assert(params.bytes[i]==i+17);++posCalls;return{10,20,direction.x*speed,direction.y*speed};}
static std::int32_t Bomb(void*self,BitSet128Value flags,bool rocket){assert(self==g_Entities[kPlayer].data()&&flags.low==0x8000000000000001ULL&&flags.high==0x123456789abcdef0ULL&&rocket);++bombCalls;return 19;}
static void Guards(){namespace G=api600_player;
#define GUARD(n) std::memcpy(g_ModuleBytes.data()+G::k##n##GuardOffset,G::k##n##Guard.data(),16)
 GUARD(Constructor);GUARD(Init);GUARD(Active);GUARD(Shoot);GUARD(Evaluate);GUARD(Tear);GUARD(Multi);GUARD(PosVel);GUARD(Bomb);GUARD(Weapon);
#undef GUARD
}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);Guards();
std::vector<unsigned char>weapon(64);Put(weapon.data(),0x18,6.5F);WriteWord(g_Entities[kPlayer],0x1758,AddressOf(weapon));WriteAt<std::int32_t>(g_Entities[kPlayer],0x16b0,7);WriteAt<float>(g_Entities[kPlayer],0x2844,.5F);WriteAt<std::int32_t>(g_Entities[kPlayer],0x2840,123);WriteAt<Vec>(g_Entities[kPlayer],0x1a20,{3,4});WriteAt<EngineColorMod>(g_Entities[kPlayer],0x1894,DefaultEngineColorMod());WriteAt<std::uint8_t>(g_Entities[kPlayer],0x1a0c,1);WriteAt<std::uint8_t>(g_Entities[kPlayer],0x1781,1);for(unsigned i=0;i<4;++i)WriteAt<std::int32_t>(g_Entities[kPlayer],0x1970+i*0x1c,10+i);
SetApi600PlayerNativeTestBindings({{engine_call::AddressOfFunction(&Tear),engine_call::AddressOfFunction(&Multi),engine_call::AddressOfFunction(&Pos),engine_call::AddressOfFunction(&Bomb)}});
const char*script=R"lua(
local p=Isaac.GetPlayer();local npc=Isaac.FindByType(20)[1]
assert(type(p.GetTearHitParams)=='function');local t=p:GetTearHitParams(1)
assert(getmetatable(t).__class==getmetatable(TearParams).__class and getmetatable(t).__type=='TearParams')
assert(t.TearVariant==7 and t.BombVariant==9 and t.TearColor.R==.25 and t.TearDamage==3.5 and t.TearScale==1.25 and t.TearHeight==-12)
assert(t.TearFlags==BitSet128(0x8000000000000001,0x123456789abcdef0))
local t2=p:GetTearHitParams(1,2.5,-3,npc);assert(t2.TearDamage==8.75);local t3=p:GetTearHitParams(1,false,false,nil);assert(t3.TearDamage==3.5)
for _,n in ipairs({'TearVariant','BombVariant'})do t[n]=0x100000001;assert(t[n]==1);t[n]=-7;assert(t[n]==-7);assert(not pcall(function()t[n]=1.5 end))end
for _,n in ipairs({'TearDamage','TearScale','TearHeight'})do t[n]=2.5;assert(t[n]==2.5);assert(not pcall(function()t[n]={}end))end
t.TearColor=Color(.5,.25,.75,1,.1,.2,.3);assert(t.TearColor.R==.5);local c=t.TearColor;c.R=9;assert(t.TearColor.R==.5);assert(not pcall(function()t.TearColor={}end))
t.TearFlags=BitSet128(7,9);assert(t.TearFlags==BitSet128(7,9));t.TearFlags=9;assert(t.TearFlags==BitSet128(9,0));assert(not pcall(function()t.TearFlags={}end));assert(not pcall(function()t.Unknown=1 end))
assert(not pcall(function()p:GetTearHitParams(1,{},1,nil)end));assert(not pcall(function()p:GetTearHitParams(1,1,1,{})end));assert(not pcall(function()p.GetTearHitParams({})end))
assert(p.HeadFrameDelay==7 and p.IBSCharge==.5 and p.SamsonBerserkCharge==123)
p.HeadFrameDelay=0x100000001;assert(p.HeadFrameDelay==1);p.HeadFrameDelay=-3;assert(p.HeadFrameDelay==-3);assert(not pcall(function()p.HeadFrameDelay=1.5 end))
p.IBSCharge=.75;assert(p.IBSCharge==.75);assert(not pcall(function()p.IBSCharge={}end));p.SamsonBerserkCharge=0x100000001;assert(p.SamsonBerserkCharge==1);assert(not pcall(function()p.SamsonBerserkCharge=false end))
assert(p.LaserColor.R==1);p.LaserColor=Color(.25,.5,.75,1);assert(p.LaserColor.R==.25);local lc=p.LaserColor;lc.R=9;assert(p.LaserColor.R==.25);assert(not pcall(function()p.LaserColor={}end))
local offset=p.TearsOffset;assert(offset:Length()==5);assert(not pcall(function()offset.X=6 end));p.TearsOffset=Vector(5,12);assert(offset:Length()==13 and p.TearsOffset.X==5);assert(not pcall(function()p.TearsOffset={X=1,Y=2}end))
local desc=p.FriendBallEnemy;assert(type(desc)=='userdata' and desc.Type==nil);assert(not pcall(function()desc.Type=20 end));p.FriendBallEnemy=desc;assert(not pcall(function()p.FriendBallEnemy={}end))
assert(p.FireDelay==6.5);p.FireDelay=-2.25;assert(p.FireDelay==-2.25);assert(not pcall(function()p.FireDelay={}end))
assert(p:GetActiveSubCharge()==10 and p:GetActiveSubCharge(nil)==10 and p:GetActiveSubCharge(false)==10)
for i=0,3 do assert(p:GetActiveSubCharge(i)==10+i)end
assert(not pcall(function()p:GetActiveSubCharge(-1)end));assert(not pcall(function()p:GetActiveSubCharge(4)end));assert(not pcall(function()p:GetActiveSubCharge(1.5)end))
assert(p:AreOpposingShootDirectionsPressed()==true);assert(p:HasWeaponType(1) and not p:HasWeaponType(0));assert(not pcall(function()p:HasWeaponType(-1)end));assert(not pcall(function()p:HasWeaponType(16)end))
assert(p:GetBombVariant(BitSet128(0x8000000000000001,0x123456789abcdef0),true)==19);assert(not pcall(function()p:GetBombVariant({},false)end))
local m=p:GetMultiShotParams();assert(type(m)=='userdata' and m.NumTears==nil);assert(not pcall(function()m.NumTears=2 end));local mf=p:GetMultiShotParams(false);assert(type(mf)=='userdata')
local pv=p:GetMultiShotPositionVelocity(2,1,Vector(3,4),2.5,m)
assert(pv.Position.X==10 and pv.Position.Y==20 and pv.Velocity.X==7.5 and pv.Velocity.Y==10);local v=pv.Position;v.X=99;assert(pv.Position.X==10)
pv.Position=Vector(5,12);assert(pv.Position:Length()==13);pv.Velocity=Vector(8,15);assert(pv.Velocity:Length()==17);assert(not pcall(function()pv.Position={}end));assert(not pcall(function()pv.Unknown=1 end))
local ps=p.GetMultiShotPositionVelocity(2,1,Vector(3,4),2.5,m);assert(ps.Position.X==10 and ps.Velocity.Y==10)
assert(not pcall(function()p:GetMultiShotPositionVelocity(2,1,{},2.5,m)end));assert(not pcall(function()p:GetMultiShotPositionVelocity(2,1,Vector(3,4),2.5,{})end))
assert(npc.HeadFrameDelay==nil and npc.IBSCharge==nil and npc.LaserColor==nil and npc.FriendBallEnemy==nil)
)lua";
if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api600-player.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView errors[8]{};const auto count=LuaRuntime::CopyLuaErrorHistory(errors,8);for(std::size_t i=0;i<count;++i)std::fprintf(stderr,"%s\n",errors[i].text);return 1;}
assert(tearCalls==3&&multiCalls==2&&posCalls==2&&bombCalls==1);assert(At<float>(weapon.data(),0x18)==-2.25F);
// no-weapon case and second-weapon fallback use the same actual public getter/setter.
WriteWord(g_Entities[kPlayer],0x1758,0);WriteWord(g_Entities[kPlayer],0x1760,0);
auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));RegisterVectorReferenceMetatable(L);luaL_newmetatable(L,LuaRuntime::kVectorMetatable);lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,VectorNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachVectorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");PushEntityCallbackArgument(L,AddressOf(g_Entities[kPlayer]));lua_setglobal(L,"p");
if(luaL_dostring(L,"assert(p.FireDelay==0);p.FireDelay=12;offset=p.TearsOffset;desc=p.FriendBallEnemy;params=p:GetMultiShotParams()")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 2;}
WriteWord(g_Entities[kPlayer],0x1760,AddressOf(weapon));if(luaL_dostring(L,"assert(p.FireDelay==-2.25);p.FireDelay=9.5;assert(p.FireDelay==9.5)")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 3;}
// Cached guard must be rechecked when the module base changes; stale entities still get a valid new vtable.
std::vector<unsigned char>other=g_ModuleBytes;namespace G=api600_player;
for(auto o:{G::kConstructorGuardOffset,G::kTearGuardOffset,G::kMultiGuardOffset,G::kPosVelGuardOffset,G::kBombGuardOffset})other[o]^=1;
const auto otherBase=AddressOf(other);WriteWord(g_Entities[kPlayer],0,otherBase+kEntityPlayerVtableOffset);LuaRuntime::SetEngineModuleBase(otherBase);
if(luaL_dostring(L,R"lua(local function guarded(f)local ok,e=pcall(f);assert(not ok and e:find('guard'),tostring(e))end;guarded(function()return p.HeadFrameDelay end);guarded(function()p.HeadFrameDelay=1 end);guarded(function()p:GetTearHitParams(1)end);guarded(function()p:GetMultiShotParams()end);guarded(function()p:GetMultiShotPositionVelocity(2,1,Vector(3,4),2.5,params)end);guarded(function()p:GetBombVariant(BitSet128(1,0),false)end))lua")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 4;}
RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));if(luaL_dostring(L,R"lua(local function expired(f)local ok,e=pcall(f);assert(not ok and e:find('reference'),tostring(e))end;expired(function()return offset.X end);expired(function()return desc.Type end);expired(function()p:GetTearHitParams(1)end);expired(function()p:GetActiveSubCharge()end))lua")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 5;}
assert(tearCalls==3&&multiCalls==3&&posCalls==2&&bombCalls==1);lua_close(L);return 0;}
'''
class PlayerConsumer(unittest.TestCase):
 def test_public_player(self):
  r=run_main(BASELINE_MAIN);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
