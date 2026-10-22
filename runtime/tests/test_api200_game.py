"""第一组20玩家方法的真实Lua→原生行为判据。"""
import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
ROOT=Path(__file__).resolve().parents[2]

MAIN=r'''

#include "interfaces/lua/api200_game.hpp"
#include "interfaces/lua/api200_game.guards.hpp"
#include "interfaces/lua/game_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;using Vec2=LuaRuntime::VectorHandle;
static void*wanted{},*enemy{},*player{};static unsigned calls[18]{};
static bool consumer{};static std::int32_t encountered{};static std::uint32_t variant{};static bool known{};
static int angel{},greed{},ending{},lap{},collectibles{},pickups{},finished{},shock{},farts{},rerolls{},transition{};
static float fadeSpeed{},alpha{};static int fadeTarget{};static void*transitionPlayer{};
static void Touch(unsigned n,void*p){assert(p==wanted);++calls[n];}
static int ConstructGame(lua_State*L){assert(lua_gettop(L)==0);auto*g=static_cast<LuaRuntime::GameHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::GameHandle)));g->reserved=0;luaL_getmetatable(L,LuaRuntime::kGameMetatable);lua_setmetatable(L,-2);return 1;}
static void FAddEncounteredBoss(void*p,std::int32_t a0,std::uint32_t a1){Touch(0,p);assert(a0==-1);assert(a1==0xffffffffU);encountered=a0;variant=a1;known=true;}
static void FButterBeanFart(void*p,const Vec2& a0,float a1,void* a2,bool a3,bool a4){Touch(1,p);if(consumer){assert(a0.x==3&&a0.y==4&&a1==100&&a2==player&&a3&&!a4);++farts;return;}if(calls[1]==1){assert(a0.x==3&&a0.y==4);assert(a1==2.5F);assert(a2==enemy);assert(a3);assert(!a4);}else{assert(a0.x==0&&a0.y==0&&a1==0&&a2==nullptr&&!a3&&a4);}farts+=a3?1:0;}
static void FDonateAngel(void*p,std::int32_t a0){Touch(2,p);assert(a0==-1);angel+=a0;}
static void FDonateGreed(void*p,std::int32_t a0){Touch(3,p);assert(a0==5);greed+=a0;}
static void FEnd(void*p,std::int32_t a0){Touch(4,p);assert(a0==-1);ending=a0;}
static void FFadein(void*p,float a0){Touch(5,p);assert(a0==2.5F);fadeSpeed=a0;alpha=1;}
static void FFadeout(void*p,float a0,std::int32_t a1){Touch(6,p);assert(a0==2.5F);assert(a1==-1);fadeSpeed=a0;alpha+=a0;fadeTarget=a1;}
static void FFinishChallenge(void*p){Touch(7,p);if(consumer){++finished;return;}++finished;}
static std::uint32_t FGetGreedWavesNum(void*p){Touch(8,p);return 0xf0000000U;}
static void* FGetNearestPlayer(void*p,const Vec2& a0){Touch(9,p);if(calls[9]==1){assert(a0.x==3&&a0.y==4);}else{assert(a0.x==0&&a0.y==0);}return a0.x==3?player:nullptr;}
static void* FGetRandomPlayer(void*p,const Vec2& a0,float a1){Touch(10,p);if(calls[10]==1){assert(a0.x==3&&a0.y==4);assert(a1==75);}else{assert(a0.x==3&&a0.y==4&&a1==0);}return a1>0?player:nullptr;}
static bool FHasEncounteredBoss(void*p,std::int32_t a0,std::uint32_t a1){Touch(11,p);if(calls[11]==1){assert(a0==-1);assert(a1==0xffffffffU);}else{assert(a0==-1&&a1==0);}return known&&encountered==a0&&variant==a1;}
static void FMakeShockwave(void*p,const Vec2& a0,float a1,float a2,std::int32_t a3){Touch(12,p);assert(a0.x==3&&a0.y==4);assert(a1==1.5F);assert(a2==2.5F);assert(a3==-1);++shock;}
static void FNextVictoryLap(void*p){Touch(13,p);++lap;}
static bool FRerollEnemy(void*p,void* a0,bool a1){Touch(14,p);if(consumer){assert(a0==enemy&&!a1);++rerolls;return true;}if(calls[14]==1){assert(a0==enemy);assert(a1);}else{assert((a0==enemy&&!a1)||(a0==nullptr&&!a1));}return (a0?(++rerolls,true):false);}
static void FRerollLevelCollectibles(void*p){Touch(15,p);++collectibles;}
static void FRerollLevelPickups(void*p,std::uint32_t a0){Touch(16,p);assert(a0==0xffffffffU);pickups=static_cast<int>(a0);}
static void FStartStageTransition(void*p,bool a0,std::int32_t a1,void* a2){Touch(17,p);if(consumer){assert(!a0&&a1==0&&a2==player);++transition;transitionPlayer=a2;return;}if(calls[17]==1){assert(a0);assert(a1==-1);assert(a2==player);}else{assert(!a0&&a1==0&&a2==nullptr);}++transition;transitionPlayer=a2?a2:player;}

int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;const std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 wanted=g_GameBytes.data();enemy=g_Entities[kEnemyA].data();player=g_Entities[kPlayer].data();
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 namespace guards=api200_game;auto guard=[&](auto o,const auto&b){std::memcpy(g_ModuleBytes.data()+o,b.data(),b.size());};
 guard(guards::kAddEncounteredBossEntry,guards::kAddEncounteredBossGuard);
 guard(guards::kButterBeanFartEntry,guards::kButterBeanFartGuard);
 guard(guards::kDonateAngelEntry,guards::kDonateAngelGuard);
 guard(guards::kDonateGreedEntry,guards::kDonateGreedGuard);
 guard(guards::kEndEntry,guards::kEndGuard);
 guard(guards::kFadeinEntry,guards::kFadeinGuard);
 guard(guards::kFadeoutEntry,guards::kFadeoutGuard);
 guard(guards::kFinishChallengeEntry,guards::kFinishChallengeGuard);
 guard(guards::kGetGreedWavesNumEntry,guards::kGetGreedWavesNumGuard);
 guard(guards::kGetNearestPlayerEntry,guards::kGetNearestPlayerGuard);
 guard(guards::kGetRandomPlayerEntry,guards::kGetRandomPlayerGuard);
 guard(guards::kHasEncounteredBossEntry,guards::kHasEncounteredBossGuard);
 guard(guards::kMakeShockwaveEntry,guards::kMakeShockwaveGuard);
 guard(guards::kNextVictoryLapEntry,guards::kNextVictoryLapGuard);
 guard(guards::kRerollEnemyEntry,guards::kRerollEnemyGuard);
 guard(guards::kRerollLevelCollectiblesEntry,guards::kRerollLevelCollectiblesGuard);
 guard(guards::kRerollLevelPickupsEntry,guards::kRerollLevelPickupsGuard);
 guard(guards::kStartStageTransitionEntry,guards::kStartStageTransitionGuard);
 Api200GameNativeTestBindings bindings{};
 bindings.methods[0]=engine_call::AddressOfFunction(&FAddEncounteredBoss);
 bindings.methods[1]=engine_call::AddressOfFunction(&FButterBeanFart);
 bindings.methods[2]=engine_call::AddressOfFunction(&FDonateAngel);
 bindings.methods[3]=engine_call::AddressOfFunction(&FDonateGreed);
 bindings.methods[4]=engine_call::AddressOfFunction(&FEnd);
 bindings.methods[5]=engine_call::AddressOfFunction(&FFadein);
 bindings.methods[6]=engine_call::AddressOfFunction(&FFadeout);
 bindings.methods[7]=engine_call::AddressOfFunction(&FFinishChallenge);
 bindings.methods[8]=engine_call::AddressOfFunction(&FGetGreedWavesNum);
 bindings.methods[9]=engine_call::AddressOfFunction(&FGetNearestPlayer);
 bindings.methods[10]=engine_call::AddressOfFunction(&FGetRandomPlayer);
 bindings.methods[11]=engine_call::AddressOfFunction(&FHasEncounteredBoss);
 bindings.methods[12]=engine_call::AddressOfFunction(&FMakeShockwave);
 bindings.methods[13]=engine_call::AddressOfFunction(&FNextVictoryLap);
 bindings.methods[14]=engine_call::AddressOfFunction(&FRerollEnemy);
 bindings.methods[15]=engine_call::AddressOfFunction(&FRerollLevelCollectibles);
 bindings.methods[16]=engine_call::AddressOfFunction(&FRerollLevelPickups);
 bindings.methods[17]=engine_call::AddressOfFunction(&FStartStageTransition);

 SetApi200GameNativeTestBindings(bindings);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));
 luaL_newmetatable(L,LuaRuntime::kGameMetatable);lua_newtable(L);static_cast<void>(AttachGameMethods(L));
 if(scene!="integration"){
 lua_pushcfunction(L,Api200GameAddEncounteredBoss);lua_setfield(L,-2,"AddEncounteredBoss");
 lua_pushcfunction(L,Api200GameButterBeanFart);lua_setfield(L,-2,"ButterBeanFart");
 lua_pushcfunction(L,Api200GameDonateAngel);lua_setfield(L,-2,"DonateAngel");
 lua_pushcfunction(L,Api200GameDonateGreed);lua_setfield(L,-2,"DonateGreed");
 lua_pushcfunction(L,Api200GameEnd);lua_setfield(L,-2,"End");
 lua_pushcfunction(L,Api200GameFadein);lua_setfield(L,-2,"Fadein");
 lua_pushcfunction(L,Api200GameFadeout);lua_setfield(L,-2,"Fadeout");
 lua_pushcfunction(L,Api200GameFinishChallenge);lua_setfield(L,-2,"FinishChallenge");
 lua_pushcfunction(L,Api200GameGetGreedWavesNum);lua_setfield(L,-2,"GetGreedWavesNum");
 lua_pushcfunction(L,Api200GameGetNearestPlayer);lua_setfield(L,-2,"GetNearestPlayer");
 lua_pushcfunction(L,Api200GameGetRandomPlayer);lua_setfield(L,-2,"GetRandomPlayer");
 lua_pushcfunction(L,Api200GameHasEncounteredBoss);lua_setfield(L,-2,"HasEncounteredBoss");
 lua_pushcfunction(L,Api200GameMakeShockwave);lua_setfield(L,-2,"MakeShockwave");
 lua_pushcfunction(L,Api200GameNextVictoryLap);lua_setfield(L,-2,"NextVictoryLap");
 lua_pushcfunction(L,Api200GameRerollEnemy);lua_setfield(L,-2,"RerollEnemy");
 lua_pushcfunction(L,Api200GameRerollLevelCollectibles);lua_setfield(L,-2,"RerollLevelCollectibles");
 lua_pushcfunction(L,Api200GameRerollLevelPickups);lua_setfield(L,-2,"RerollLevelPickups");
 lua_pushcfunction(L,Api200GameStartStageTransition);lua_setfield(L,-2,"StartStageTransition");

 }
 lua_pushcclosure(L,GameIndex,1);lua_setfield(L,-2,"__index");lua_pop(L,1);lua_pushcfunction(L,ConstructGame);lua_setglobal(L,"Game");
 RegisterVectorReferenceMetatable(L);luaL_newmetatable(L,LuaRuntime::kVectorMetatable);lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pop(L,1);lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");
 const char*script=R"lua(g=Game();p=Isaac.GetPlayer();npc=Isaac.FindByType(20)[1];assert(p and npc);
assert(select("#",g:AddEncounteredBoss('4294967295','4294967295'))==0,'AddEncounteredBoss');
assert(select("#",g:ButterBeanFart(Vector(3,4),2.5,npc,0,false))==0,'ButterBeanFart');
assert(select("#",g:DonateAngel('4294967295'))==0,'DonateAngel');
assert(select("#",g:DonateGreed(5))==0,'DonateGreed');
assert(select("#",g:End('4294967295'))==0,'End');
assert(select("#",g:Fadein(2.5,false,{}))==0,'Fadein');
assert(select("#",g:Fadeout(2.5,'4294967295',{}))==0,'Fadeout');
assert(select("#",g:FinishChallenge('ignored',{}))==0,'FinishChallenge');
assert(g:GetGreedWavesNum('ignored',{})==4026531840);
savedGetNearestPlayer=g:GetNearestPlayer(Vector(3,4));assert(savedGetNearestPlayer:ToPlayer() and savedGetNearestPlayer.Index==p.Index);
savedGetRandomPlayer=g:GetRandomPlayer(Vector(3,4),75);assert(savedGetRandomPlayer:ToPlayer() and savedGetRandomPlayer.Index==p.Index);
assert(g:HasEncounteredBoss('4294967295','4294967295'),'HasEncounteredBoss');
assert(select("#",g:MakeShockwave(Vector(3,4),1.5,2.5,'4294967295'))==0,'MakeShockwave');
assert(select("#",g:NextVictoryLap('ignored',{}))==0,'NextVictoryLap');
assert(g:RerollEnemy(npc,0),'RerollEnemy');
assert(select("#",g:RerollLevelCollectibles('ignored',{}))==0,'RerollLevelCollectibles');
assert(select("#",g:RerollLevelPickups('4294967295'))==0,'RerollLevelPickups');
assert(select("#",g:StartStageTransition(0,'4294967295',p))==0,'StartStageTransition');

assert(not g:HasEncounteredBoss(-1,0));assert(g:GetNearestPlayer(Vector(0,0))==nil);assert(g:GetRandomPlayer(Vector(3,4),0)==nil)
assert(g:RerollEnemy(npc));assert(not g:RerollEnemy(nil));assert(not g:RerollEnemy(nil,false));
g:ButterBeanFart(Vector(0,0),0,nil,nil,0);g:StartStageTransition(false,0);g:StartStageTransition(false,0,nil)
assert(not pcall(function()g:AddEncounteredBoss() end),'AddEncounteredBoss()');
assert(not pcall(function()g:AddEncounteredBoss(1) end),'AddEncounteredBoss(1)');
assert(not pcall(function()g:AddEncounteredBoss(nil,1) end),'AddEncounteredBoss(nil,1)');
assert(not pcall(function()g:AddEncounteredBoss(1,false) end),'AddEncounteredBoss(1,false)');
assert(not pcall(function()g:AddEncounteredBoss(1,1.5) end),'AddEncounteredBoss(1,1.5)');
assert(not pcall(function()g:ButterBeanFart() end),'ButterBeanFart()');
assert(not pcall(function()g:ButterBeanFart(Vector(3,4),1) end),'ButterBeanFart(Vector(3,4),1)');
assert(not pcall(function()g:ButterBeanFart(Vector(3,4),false,nil) end),'ButterBeanFart(Vector(3,4),false,nil)');
assert(not pcall(function()g:ButterBeanFart(nil,1,nil) end),'ButterBeanFart(nil,1,nil)');
assert(not pcall(function()g:ButterBeanFart(Vector(3,4),1,false) end),'ButterBeanFart(Vector(3,4),1,false)');
assert(not pcall(function()g:ButterBeanFart(Vector(3,4),1,{}) end),'ButterBeanFart(Vector(3,4),1,{})');
assert(not pcall(function()g:DonateAngel() end),'DonateAngel()');
assert(not pcall(function()g:DonateAngel(nil) end),'DonateAngel(nil)');
assert(not pcall(function()g:DonateAngel(false) end),'DonateAngel(false)');
assert(not pcall(function()g:DonateAngel(1.5) end),'DonateAngel(1.5)');
assert(not pcall(function()g:DonateGreed() end),'DonateGreed()');
assert(not pcall(function()g:DonateGreed(false) end),'DonateGreed(false)');
assert(not pcall(function()g:DonateGreed({}) end),'DonateGreed({})');
assert(not pcall(function()g:End() end),'End()');
assert(not pcall(function()g:End(nil) end),'End(nil)');
assert(not pcall(function()g:End(1.5) end),'End(1.5)');
assert(not pcall(function()g:Fadein() end),'Fadein()');
assert(not pcall(function()g:Fadein(nil) end),'Fadein(nil)');
assert(not pcall(function()g:Fadein(false) end),'Fadein(false)');
assert(not pcall(function()g:Fadein({}) end),'Fadein({})');
assert(not pcall(function()g:Fadeout() end),'Fadeout()');
assert(not pcall(function()g:Fadeout(1) end),'Fadeout(1)');
assert(not pcall(function()g:Fadeout(1,false) end),'Fadeout(1,false)');
assert(not pcall(function()g:Fadeout(false,1) end),'Fadeout(false,1)');
assert(not pcall(function()g:Fadeout(1,1.5) end),'Fadeout(1,1.5)');
assert(not pcall(function()g:GetNearestPlayer() end),'GetNearestPlayer()');
assert(not pcall(function()g:GetNearestPlayer(nil) end),'GetNearestPlayer(nil)');
assert(not pcall(function()g:GetNearestPlayer(npc) end),'GetNearestPlayer(npc)');
assert(not pcall(function()g:GetNearestPlayer({}) end),'GetNearestPlayer({})');
assert(not pcall(function()g:GetRandomPlayer() end),'GetRandomPlayer()');
assert(not pcall(function()g:GetRandomPlayer(Vector(3,4)) end),'GetRandomPlayer(Vector(3,4))');
assert(not pcall(function()g:GetRandomPlayer(Vector(3,4),false) end),'GetRandomPlayer(Vector(3,4),false)');
assert(not pcall(function()g:GetRandomPlayer(nil,1) end),'GetRandomPlayer(nil,1)');
assert(not pcall(function()g:HasEncounteredBoss() end),'HasEncounteredBoss()');
assert(not pcall(function()g:HasEncounteredBoss(1) end),'HasEncounteredBoss(1)');
assert(not pcall(function()g:HasEncounteredBoss(false,1) end),'HasEncounteredBoss(false,1)');
assert(not pcall(function()g:HasEncounteredBoss(1,nil) end),'HasEncounteredBoss(1,nil)');
assert(not pcall(function()g:HasEncounteredBoss(1,1.5) end),'HasEncounteredBoss(1,1.5)');
assert(not pcall(function()g:MakeShockwave() end),'MakeShockwave()');
assert(not pcall(function()g:MakeShockwave(Vector(3,4),1,1) end),'MakeShockwave(Vector(3,4),1,1)');
assert(not pcall(function()g:MakeShockwave(Vector(3,4),false,1,1) end),'MakeShockwave(Vector(3,4),false,1,1)');
assert(not pcall(function()g:MakeShockwave(Vector(3,4),1,nil,1) end),'MakeShockwave(Vector(3,4),1,nil,1)');
assert(not pcall(function()g:MakeShockwave(Vector(3,4),1,1,false) end),'MakeShockwave(Vector(3,4),1,1,false)');
assert(not pcall(function()g:RerollEnemy() end),'RerollEnemy()');
assert(not pcall(function()g:RerollEnemy(false) end),'RerollEnemy(false)');
assert(not pcall(function()g:RerollEnemy({}) end),'RerollEnemy({})');
assert(not pcall(function()g:RerollLevelPickups() end),'RerollLevelPickups()');
assert(not pcall(function()g:RerollLevelPickups(nil) end),'RerollLevelPickups(nil)');
assert(not pcall(function()g:RerollLevelPickups(false) end),'RerollLevelPickups(false)');
assert(not pcall(function()g:RerollLevelPickups(1.5) end),'RerollLevelPickups(1.5)');
assert(not pcall(function()g:StartStageTransition() end),'StartStageTransition()');
assert(not pcall(function()g:StartStageTransition(false) end),'StartStageTransition(false)');
assert(not pcall(function()g:StartStageTransition(false,nil) end),'StartStageTransition(false,nil)');
assert(not pcall(function()g:StartStageTransition(true,1.5) end),'StartStageTransition(true,1.5)');
assert(not pcall(function()g:StartStageTransition(false,0,false) end),'StartStageTransition(false,0,false)');
assert(not pcall(function()g:StartStageTransition(false,0,npc) end),'StartStageTransition(false,0,npc)');
assert(not pcall(function()g:StartStageTransition(false,0,{}) end),'StartStageTransition(false,0,{})');
for _,n in ipairs({'AddEncounteredBoss','ButterBeanFart','DonateAngel','DonateGreed','End','Fadein','Fadeout','FinishChallenge','GetGreedWavesNum','GetNearestPlayer','GetRandomPlayer','HasEncounteredBoss','MakeShockwave','NextVictoryLap','RerollEnemy','RerollLevelCollectibles','RerollLevelPickups','StartStageTransition'})do local f=g[n];assert(not pcall(function()f(p)end));assert(not pcall(function()f({})end));assert(not pcall(function()f(nil)end))end
)lua";
 if(scene=="badguard"){
 g_ModuleBytes[guards::kAddEncounteredBossEntry]^=1;
 g_ModuleBytes[guards::kButterBeanFartEntry]^=1;
 g_ModuleBytes[guards::kDonateAngelEntry]^=1;
 g_ModuleBytes[guards::kDonateGreedEntry]^=1;
 g_ModuleBytes[guards::kEndEntry]^=1;
 g_ModuleBytes[guards::kFadeinEntry]^=1;
 g_ModuleBytes[guards::kFadeoutEntry]^=1;
 g_ModuleBytes[guards::kFinishChallengeEntry]^=1;
 g_ModuleBytes[guards::kGetGreedWavesNumEntry]^=1;
 g_ModuleBytes[guards::kGetNearestPlayerEntry]^=1;
 g_ModuleBytes[guards::kGetRandomPlayerEntry]^=1;
 g_ModuleBytes[guards::kHasEncounteredBossEntry]^=1;
 g_ModuleBytes[guards::kMakeShockwaveEntry]^=1;
 g_ModuleBytes[guards::kNextVictoryLapEntry]^=1;
 g_ModuleBytes[guards::kRerollEnemyEntry]^=1;
 g_ModuleBytes[guards::kRerollLevelCollectiblesEntry]^=1;
 g_ModuleBytes[guards::kRerollLevelPickupsEntry]^=1;
 g_ModuleBytes[guards::kStartStageTransitionEntry]^=1;
script=R"lua(g=Game();p=Isaac.GetPlayer();npc=Isaac.FindByType(20)[1];local function guarded(f)local ok,err=pcall(f);assert(not ok and string.find(err,"guard"),tostring(err))end;guarded(function()g:AddEncounteredBoss('4294967295','4294967295')end);guarded(function()g:ButterBeanFart(Vector(3,4),2.5,npc,0,false)end);guarded(function()g:DonateAngel('4294967295')end);guarded(function()g:DonateGreed(5)end);guarded(function()g:End('4294967295')end);guarded(function()g:Fadein(2.5,false,{})end);guarded(function()g:Fadeout(2.5,'4294967295',{})end);guarded(function()g:FinishChallenge('ignored',{})end);guarded(function()g:GetGreedWavesNum('ignored',{})end);guarded(function()g:GetNearestPlayer(Vector(3,4))end);guarded(function()g:GetRandomPlayer(Vector(3,4),75)end);guarded(function()g:HasEncounteredBoss('4294967295','4294967295')end);guarded(function()g:MakeShockwave(Vector(3,4),1.5,2.5,'4294967295')end);guarded(function()g:NextVictoryLap('ignored',{})end);guarded(function()g:RerollEnemy(npc,0)end);guarded(function()g:RerollLevelCollectibles('ignored',{})end);guarded(function()g:RerollLevelPickups('4294967295')end);guarded(function()g:StartStageTransition(0,'4294967295',p)end);)lua";}
 if(scene=="consumer"){
 consumer=true;script=R"lua(
 local player=Isaac.GetPlayer();local pickup={Position=Vector(3,4)}
 Game():ButterBeanFart(pickup.Position,100.0,player,true,false)
 local REVEL={game=Game()};REVEL.game:FinishChallenge()
 local entities={Isaac.FindByType(20)[1]};local i=1;assert(Game():RerollEnemy(entities[i]))
 Game():StartStageTransition(false,0,Isaac.GetPlayer())
 )lua";
 }
 if(luaL_dostring(L,script)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}
 if(scene=="badguard"){for(auto n:calls)if(n)return 10;lua_close(L);return 0;}
 if(scene=="consumer"){if(farts!=1||finished!=1||rerolls!=1||transition!=1||transitionPlayer!=player)return 11;lua_close(L);return 0;}
 const unsigned expected[]={1,2,1,1,1,1,1,1,1,2,2,2,1,1,4,1,1,3};for(unsigned i=0;i<18;++i){if(calls[i]!=expected[i]){std::fprintf(stderr,"method %u count %u expected %u\n",i,calls[i],expected[i]);return 2;}}
 if(!known||encountered!=-1||variant!=0xffffffffU||angel!=-1||greed!=5||ending!=-1||fadeSpeed!=2.5F||alpha!=3.5F||fadeTarget!=-1||finished!=1||shock!=1||lap!=1||collectibles!=1||pickups!=-1||farts!=1||rerolls!=2||transition!=3||transitionPlayer!=player)return 3;
 if(scene=="deadentity"){
 RetireEntityLifetime(AddressOf(g_Entities[kEnemyA]));RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));
 if(luaL_dostring(L,"assert(not pcall(function()g:RerollEnemy(npc)end));assert(not pcall(function()g:ButterBeanFart(Vector(3,4),1,npc)end));assert(not pcall(function()g:StartStageTransition(false,0,p)end));assert(not savedGetNearestPlayer:Exists());assert(not savedGetRandomPlayer:Exists())"))return 4;
 }
 if(scene=="deadgame"){
 WriteWord(g_OwnerSlotBytes,0,0);
 if(luaL_dostring(L,R"lua(assert(not pcall(function()g:AddEncounteredBoss('4294967295','4294967295')end));assert(not pcall(function()g:ButterBeanFart(Vector(3,4),2.5,npc,0,false)end));assert(not pcall(function()g:DonateAngel('4294967295')end));assert(not pcall(function()g:DonateGreed(5)end));assert(not pcall(function()g:End('4294967295')end));assert(not pcall(function()g:Fadein(2.5,false,{})end));assert(not pcall(function()g:Fadeout(2.5,'4294967295',{})end));assert(not pcall(function()g:FinishChallenge('ignored',{})end));assert(not pcall(function()g:GetGreedWavesNum('ignored',{})end));assert(not pcall(function()g:GetNearestPlayer(Vector(3,4))end));assert(not pcall(function()g:GetRandomPlayer(Vector(3,4),75)end));assert(not pcall(function()g:HasEncounteredBoss('4294967295','4294967295')end));assert(not pcall(function()g:MakeShockwave(Vector(3,4),1.5,2.5,'4294967295')end));assert(not pcall(function()g:NextVictoryLap('ignored',{})end));assert(not pcall(function()g:RerollEnemy(npc,0)end));assert(not pcall(function()g:RerollLevelCollectibles('ignored',{})end));assert(not pcall(function()g:RerollLevelPickups('4294967295')end));assert(not pcall(function()g:StartStageTransition(0,'4294967295',p)end));)lua"))return 5;
}
 if(scene=="crossbase"){
 std::vector<unsigned char>changed=g_ModuleBytes;const auto base=AddressOf(changed);
 for(auto&entity:g_Entities){std::uintptr_t v{};std::memcpy(&v,entity.data(),8);if(v>=g_EngineBase+kEntityVtableRangeBeginOffset&&v<g_EngineBase+kEntityVtableRangeEndOffset)WriteWord(entity,0,base+(v-g_EngineBase));}LuaRuntime::SetEngineModuleBase(base);
 changed[guards::kAddEncounteredBossEntry]^=1;
 changed[guards::kButterBeanFartEntry]^=1;
 changed[guards::kDonateAngelEntry]^=1;
 changed[guards::kDonateGreedEntry]^=1;
 changed[guards::kEndEntry]^=1;
 changed[guards::kFadeinEntry]^=1;
 changed[guards::kFadeoutEntry]^=1;
 changed[guards::kFinishChallengeEntry]^=1;
 changed[guards::kGetGreedWavesNumEntry]^=1;
 changed[guards::kGetNearestPlayerEntry]^=1;
 changed[guards::kGetRandomPlayerEntry]^=1;
 changed[guards::kHasEncounteredBossEntry]^=1;
 changed[guards::kMakeShockwaveEntry]^=1;
 changed[guards::kNextVictoryLapEntry]^=1;
 changed[guards::kRerollEnemyEntry]^=1;
 changed[guards::kRerollLevelCollectiblesEntry]^=1;
 changed[guards::kRerollLevelPickupsEntry]^=1;
 changed[guards::kStartStageTransitionEntry]^=1;
 if(luaL_dostring(L,R"lua(g=Game();p=Isaac.GetPlayer();npc=Isaac.FindByType(20)[1];local function guarded(f)local ok,err=pcall(f);assert(not ok and string.find(err,"guard"),tostring(err))end;guarded(function()g:AddEncounteredBoss('4294967295','4294967295')end);guarded(function()g:ButterBeanFart(Vector(3,4),2.5,npc,0,false)end);guarded(function()g:DonateAngel('4294967295')end);guarded(function()g:DonateGreed(5)end);guarded(function()g:End('4294967295')end);guarded(function()g:Fadein(2.5,false,{})end);guarded(function()g:Fadeout(2.5,'4294967295',{})end);guarded(function()g:FinishChallenge('ignored',{})end);guarded(function()g:GetGreedWavesNum('ignored',{})end);guarded(function()g:GetNearestPlayer(Vector(3,4))end);guarded(function()g:GetRandomPlayer(Vector(3,4),75)end);guarded(function()g:HasEncounteredBoss('4294967295','4294967295')end);guarded(function()g:MakeShockwave(Vector(3,4),1.5,2.5,'4294967295')end);guarded(function()g:NextVictoryLap('ignored',{})end);guarded(function()g:RerollEnemy(npc,0)end);guarded(function()g:RerollLevelCollectibles('ignored',{})end);guarded(function()g:RerollLevelPickups('4294967295')end);guarded(function()g:StartStageTransition(0,'4294967295',p)end);)lua"))return 6;
}
 for(unsigned i=0;i<18;++i)if(calls[i]!=expected[i])return 9;lua_close(L);return 0;
}
'''
class Game18Behavior(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='api200-game-behavior-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  extra=ROOT/'runtime/src/interfaces/lua/api200_game.cpp'
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source,extra_sources=()if extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_18_native_parameters_results_guards_lifetime_and_effects(self):
  for scene in ('normal','badguard','crossbase','deadentity','deadgame','consumer'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)

class Game18Integration(Game18Behavior):
 def test_18_native_parameters_results_guards_lifetime_and_side_effects(self):
  result=subprocess.run([str(self.binary),"integration"],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
