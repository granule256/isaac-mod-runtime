"""第一组20玩家方法的真实Lua→原生行为判据。"""
import unittest,tempfile,subprocess,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
ROOT=Path(__file__).resolve().parents[2]
BASELINE=r'''
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 const char*script="local m=RegisterMod('api100-entities',1);m:AddCallback(1,function()local p=Isaac.FindByType(3)[1]:ToFamiliar();for _,name in ipairs({'AddCoins','RemoveFromFollowers','Shoot'})do assert(type(p[name])=='function',name)end end)";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api100-entities.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();return LuaRuntime::TakeCallbackError()?2:0;
}
'''
class Entities24Baseline(unittest.TestCase):
 def test_required_methods_registered(self):
  with tempfile.TemporaryDirectory(prefix='api100-entities-red-')as d:
   source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+BASELINE
   source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
   extra=ROOT/'runtime/src/interfaces/lua/api100_entities.cpp'
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=source,extra_sources=()if not extra.exists()or extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

MAIN=r'''

#include "interfaces/lua/api100_entities.hpp"
#include "interfaces/lua/api100_entities.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static void*fam{},*pickup{},*rock{},*door{},*poop{};static unsigned calls[24]{},sounds{},shots{},frames{},dust{};static bool delayed{},follower=true,locked{};static int waitFrames{},anim{},big{},damage{};static float diagonal{};static int current{},target{};
static void Touch(unsigned i,const void*p,const void*want){assert(p==want);++calls[i];}
template<class T>T Read(const void*p,std::size_t o){T t{};std::memcpy(&t,static_cast<const unsigned char*>(p)+o,sizeof(t));return t;}
template<class T>void Write(void*p,std::size_t o,T t){std::memcpy(static_cast<unsigned char*>(p)+o,&t,sizeof(t));}
static void Coins(void*p,std::int32_t n){Touch(0,p,fam);assert(n==2);Write(p,0xd8c,Read<int>(p,0xd8c)+n);}
static void Hearts(void*p,std::int32_t n){Touch(1,p,fam);assert(n==3);Write(p,0xd90,Read<int>(p,0xd90)+n);}
static void Keys(void*p,std::int32_t n){Touch(2,p,fam);assert(n==-1);Write(p,0xd94,Read<int>(p,0xd94)+n);}
static void Followers(void*p){Touch(3,p,fam);follower=false;}
static void RemoveDelayed(void*p){Touch(4,p,fam);delayed=false;}
static void AddDelayed(void*p){Touch(5,p,fam);delayed=true;}
static void MoveDelayed(void*p,std::int32_t n){Touch(6,p,fam);assert(n==2);waitFrames=n;}
static void Diagonal(void*p,float n){Touch(7,p,fam);assert(n==.75F);diagonal=n;}
static void Charge(void*p,std::int32_t n){Touch(8,p,fam);assert(n==3);anim=n;}
static void FloatAnim(void*p,std::int32_t n){Touch(9,p,fam);assert(n==2);anim=n;}
static void ShootAnim(void*p,std::int32_t n){Touch(10,p,fam);assert(n==1);anim=n;}
static void Shoot(void*p){Touch(11,p,fam);++shots;}
static void PickupSound(void*p){Touch(12,p,pickup);++sounds;}
static void DropSound(void*p){Touch(13,p,pickup);++sounds;}
static void Appear(void*p){Touch(14,p,pickup);Write(p,0x5b8,1);}
static std::int32_t Coin(const void*p){Touch(15,p,pickup);return Read<int>(p,kEntitySubTypeOffset)==2?5:0;}
static bool Hurt(void*p,std::int32_t n){assert(p==poop||p==rock);++calls[16];assert(n==2);if(p==rock)return false;damage+=n;return true;}
static bool Blow(void*p){Touch(17,p,door);return !locked;}
static void Locked(void*p,bool b){Touch(18,p,door);locked=b;++frames;}
static void Types(void*p,std::int32_t a,std::int32_t b){Touch(19,p,door);assert(a==2&&b==3);current=a;target=b;}
static void Dust(void*p){Touch(20,p,door);++dust;}
static std::int32_t Big(const void*p){Touch(21,p,rock);return big;}
static void SetBig(void*p,std::int32_t n){Touch(22,p,rock);assert(n==-2);big=n;++frames;}
static void Update(void*p){Touch(23,p,rock);++frames;}
static void Grid(lua_State*L,void*p,const char*name,bool typedDoor=false){
 if(typedDoor){auto*h=static_cast<LuaRuntime::DoorHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::DoorHandle)));h->entity=p;h->slot=0;luaL_getmetatable(L,LuaRuntime::kGridEntityDoorMetatable);}
 else{auto*h=static_cast<LuaRuntime::GridEntityHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::GridEntityHandle)));h->entity=p;luaL_getmetatable(L,LuaRuntime::kGridEntityMetatable);}
 lua_setmetatable(L,-2);lua_setglobal(L,name);
}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();FillEntities();g_Entities[kFamiliar].resize(0x1000);PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);fam=g_Entities[kFamiliar].data();pickup=g_Entities[kPickup].data();
 std::vector<unsigned char>r(0x400),d(0x400),q(0x400);rock=r.data();door=d.data();poop=q.data();WriteWord(r,0,g_EngineBase+kGridEntity_RockVtableOffset);WriteWord(d,0,g_EngineBase+kGridEntity_DoorVtableOffset);WriteWord(q,0,g_EngineBase+kGridEntity_PoopVtableOffset);
 WriteWord(g_ModuleBytes,kGridEntity_RockVtableOffset+0x28,g_EngineBase+0x380c38);WriteWord(g_ModuleBytes,kGridEntity_PoopVtableOffset+0x28,g_EngineBase+0x38aaa4);
 Write(pickup,kEntitySubTypeOffset,2);
 namespace guards=api100_entities;auto guard=[&](auto o,const auto&b){std::memcpy(g_ModuleBytes.data()+o,b.data(),b.size());};
 guard(guards::kEntityFamiliarAddCoinsEntry,guards::kEntityFamiliarAddCoinsGuard);
guard(guards::kEntityFamiliarAddHeartsEntry,guards::kEntityFamiliarAddHeartsGuard);
guard(guards::kEntityFamiliarAddKeysEntry,guards::kEntityFamiliarAddKeysGuard);
guard(guards::kEntityFamiliarRemoveFromFollowersEntry,guards::kEntityFamiliarRemoveFromFollowersGuard);
guard(guards::kEntityFamiliarRemoveFromDelayedEntry,guards::kEntityFamiliarRemoveFromDelayedGuard);
guard(guards::kEntityFamiliarAddToDelayedEntry,guards::kEntityFamiliarAddToDelayedGuard);
guard(guards::kEntityFamiliarMoveDelayedEntry,guards::kEntityFamiliarMoveDelayedGuard);
guard(guards::kEntityFamiliarMoveDiagonallyEntry,guards::kEntityFamiliarMoveDiagonallyGuard);
guard(guards::kEntityFamiliarPlayChargeAnimEntry,guards::kEntityFamiliarPlayChargeAnimGuard);
guard(guards::kEntityFamiliarPlayFloatAnimEntry,guards::kEntityFamiliarPlayFloatAnimGuard);
guard(guards::kEntityFamiliarPlayShootAnimEntry,guards::kEntityFamiliarPlayShootAnimGuard);
guard(guards::kEntityFamiliarShootEntry,guards::kEntityFamiliarShootGuard);
guard(guards::kEntityPickupPlayPickupSoundEntry,guards::kEntityPickupPlayPickupSoundGuard);
guard(guards::kEntityPickupPlayDropSoundEntry,guards::kEntityPickupPlayDropSoundGuard);
guard(guards::kEntityPickupAppearFastEntry,guards::kEntityPickupAppearFastGuard);
guard(guards::kEntityPickupGetCoinValueEntry,guards::kEntityPickupGetCoinValueGuard);
guard(guards::kGridEntityHurtEntry,guards::kGridEntityHurtGuard);
guard(guards::kGridEntityDoorCanBlowOpenEntry,guards::kGridEntityDoorCanBlowOpenGuard);
guard(guards::kGridEntityDoorSetLockedEntry,guards::kGridEntityDoorSetLockedGuard);
guard(guards::kGridEntityDoorSetRoomTypesEntry,guards::kGridEntityDoorSetRoomTypesGuard);
guard(guards::kGridEntityDoorSpawnDustEntry,guards::kGridEntityDoorSpawnDustGuard);
guard(guards::kGridEntityRockGetBigRockFrameEntry,guards::kGridEntityRockGetBigRockFrameGuard);
guard(guards::kGridEntityRockSetBigRockFrameEntry,guards::kGridEntityRockSetBigRockFrameGuard);
guard(guards::kGridEntityRockUpdateAnimFrameEntry,guards::kGridEntityRockUpdateAnimFrameGuard);
guard(guards::kHurtFireEntry,guards::kHurtFireGuard);
guard(guards::kHurtTntEntry,guards::kHurtTntGuard);
guard(guards::kHurtPoopEntry,guards::kHurtPoopGuard);
 Api100EntitiesNativeTestBindings bindings{};
 bindings.methods[0]=engine_call::AddressOfFunction(&Coins);
bindings.methods[1]=engine_call::AddressOfFunction(&Hearts);
bindings.methods[2]=engine_call::AddressOfFunction(&Keys);
bindings.methods[3]=engine_call::AddressOfFunction(&Followers);
bindings.methods[4]=engine_call::AddressOfFunction(&RemoveDelayed);
bindings.methods[5]=engine_call::AddressOfFunction(&AddDelayed);
bindings.methods[6]=engine_call::AddressOfFunction(&MoveDelayed);
bindings.methods[7]=engine_call::AddressOfFunction(&Diagonal);
bindings.methods[8]=engine_call::AddressOfFunction(&Charge);
bindings.methods[9]=engine_call::AddressOfFunction(&FloatAnim);
bindings.methods[10]=engine_call::AddressOfFunction(&ShootAnim);
bindings.methods[11]=engine_call::AddressOfFunction(&Shoot);
bindings.methods[12]=engine_call::AddressOfFunction(&PickupSound);
bindings.methods[13]=engine_call::AddressOfFunction(&DropSound);
bindings.methods[14]=engine_call::AddressOfFunction(&Appear);
bindings.methods[15]=engine_call::AddressOfFunction(&Coin);
bindings.methods[16]=engine_call::AddressOfFunction(&Hurt);
bindings.methods[17]=engine_call::AddressOfFunction(&Blow);
bindings.methods[18]=engine_call::AddressOfFunction(&Locked);
bindings.methods[19]=engine_call::AddressOfFunction(&Types);
bindings.methods[20]=engine_call::AddressOfFunction(&Dust);
bindings.methods[21]=engine_call::AddressOfFunction(&Big);
bindings.methods[22]=engine_call::AddressOfFunction(&SetBig);
bindings.methods[23]=engine_call::AddressOfFunction(&Update);
 SetApi100EntitiesNativeTestBindings(bindings);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));
 // 复用生产GridEntity/门句柄布局与index；不改ToRock返回基类协议。
 luaL_newmetatable(L,LuaRuntime::kGridEntityMetatable);lua_pushcfunction(L,GridEntityIndex);lua_setfield(L,-2,"__index");lua_newtable(L);static_cast<void>(AttachGridEntityMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kGridEntityDoorMetatable);lua_pushcfunction(L,GridEntityDoorIndex);lua_setfield(L,-2,"__index");lua_newtable(L);static_cast<void>(AttachGridEntityDoorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 if(scene!="integration"){
 luaL_getmetatable(L,LuaRuntime::kEntityFamiliarMetatable);lua_getfield(L,-1,"__methods");
lua_pushcfunction(L,Api100EntityFamiliarAddCoins);lua_setfield(L,-2,"AddCoins");
lua_pushcfunction(L,Api100EntityFamiliarAddHearts);lua_setfield(L,-2,"AddHearts");
lua_pushcfunction(L,Api100EntityFamiliarAddKeys);lua_setfield(L,-2,"AddKeys");
lua_pushcfunction(L,Api100EntityFamiliarRemoveFromFollowers);lua_setfield(L,-2,"RemoveFromFollowers");
lua_pushcfunction(L,Api100EntityFamiliarRemoveFromDelayed);lua_setfield(L,-2,"RemoveFromDelayed");
lua_pushcfunction(L,Api100EntityFamiliarAddToDelayed);lua_setfield(L,-2,"AddToDelayed");
lua_pushcfunction(L,Api100EntityFamiliarMoveDelayed);lua_setfield(L,-2,"MoveDelayed");
lua_pushcfunction(L,Api100EntityFamiliarMoveDiagonally);lua_setfield(L,-2,"MoveDiagonally");
lua_pushcfunction(L,Api100EntityFamiliarPlayChargeAnim);lua_setfield(L,-2,"PlayChargeAnim");
lua_pushcfunction(L,Api100EntityFamiliarPlayFloatAnim);lua_setfield(L,-2,"PlayFloatAnim");
lua_pushcfunction(L,Api100EntityFamiliarPlayShootAnim);lua_setfield(L,-2,"PlayShootAnim");
lua_pushcfunction(L,Api100EntityFamiliarShoot);lua_setfield(L,-2,"Shoot");
lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kEntityPickupMetatable);lua_getfield(L,-1,"__methods");
lua_pushcfunction(L,Api100EntityPickupPlayPickupSound);lua_setfield(L,-2,"PlayPickupSound");
lua_pushcfunction(L,Api100EntityPickupPlayDropSound);lua_setfield(L,-2,"PlayDropSound");
lua_pushcfunction(L,Api100EntityPickupAppearFast);lua_setfield(L,-2,"AppearFast");
lua_pushcfunction(L,Api100EntityPickupGetCoinValue);lua_setfield(L,-2,"GetCoinValue");
lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kGridEntityMetatable);lua_getfield(L,-1,"__methods");
lua_pushcfunction(L,Api100GridEntityHurt);lua_setfield(L,-2,"Hurt");
lua_pushcfunction(L,Api100GridEntityDoorCanBlowOpen);lua_setfield(L,-2,"CanBlowOpen");
lua_pushcfunction(L,Api100GridEntityDoorSetLocked);lua_setfield(L,-2,"SetLocked");
lua_pushcfunction(L,Api100GridEntityDoorSetRoomTypes);lua_setfield(L,-2,"SetRoomTypes");
lua_pushcfunction(L,Api100GridEntityDoorSpawnDust);lua_setfield(L,-2,"SpawnDust");
lua_pushcfunction(L,Api100GridEntityRockGetBigRockFrame);lua_setfield(L,-2,"GetBigRockFrame");
lua_pushcfunction(L,Api100GridEntityRockSetBigRockFrame);lua_setfield(L,-2,"SetBigRockFrame");
lua_pushcfunction(L,Api100GridEntityRockUpdateAnimFrame);lua_setfield(L,-2,"UpdateAnimFrame");
lua_pop(L,2);
luaL_getmetatable(L,LuaRuntime::kGridEntityDoorMetatable);lua_getfield(L,-1,"__methods");
lua_pushcfunction(L,Api100GridEntityDoorCanBlowOpen);lua_setfield(L,-2,"CanBlowOpen");
lua_pushcfunction(L,Api100GridEntityDoorSetLocked);lua_setfield(L,-2,"SetLocked");
lua_pushcfunction(L,Api100GridEntityDoorSetRoomTypes);lua_setfield(L,-2,"SetRoomTypes");
lua_pushcfunction(L,Api100GridEntityDoorSpawnDust);lua_setfield(L,-2,"SpawnDust");
lua_pop(L,2);
 }
 Grid(L,rock,"r");Grid(L,poop,"g");Grid(L,door,"d");Grid(L,door,"td",true);
 if(scene=="community"){
  const char*community=R"lua(local grid=r;local grinformation={Frame=-2};local gridInformation={{}};local i=1
                        grid:ToRock():SetBigRockFrame(grinformation.Frame)
                grid:ToRock():UpdateAnimFrame()
                gridInformation[i].Frame = grid:ToRock():GetBigRockFrame()
assert(gridInformation[1].Frame==-2)
)lua";
  if(luaL_dostring(L,community)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 18;}
  if(calls[21]!=1||calls[22]!=1||calls[23]!=1||big!=-2)return 19;
  lua_close(L);return 0;
 }
 const char*script=R"lua(
 f=Isaac.FindByType(3)[1]:ToFamiliar();p=Isaac.FindByType(5)[1]:ToPickup();local player=Isaac.GetPlayer();assert(f and p)
 assert(select('#',f:AddCoins('4294967298',false))==0);f:AddHearts(3.0);f:AddKeys('4294967295')
 f:RemoveFromFollowers(false);f:AddToDelayed({});f:MoveDelayed(2);f:RemoveFromDelayed(true)
 f:MoveDiagonally('0.75');f:PlayChargeAnim(3);f:PlayFloatAnim(2);f:PlayShootAnim(1);assert(select('#',f:Shoot({}))==0)
 p:PlayPickupSound();p:PlayDropSound(nil);p:AppearFast(true);assert(p:GetCoinValue('ignored')==5)
 assert(g:Hurt('4294967298')==true and r:Hurt(2)==false)
 assert(d:CanBlowOpen());assert(select('#',d:SetLocked(0))==0);assert(not td:CanBlowOpen());td:SetLocked(nil);assert(d:CanBlowOpen());td:SetLocked();assert(d:CanBlowOpen())
 d:SetRoomTypes('4294967298',3.0,false);d:SpawnDust({})
 r:SetBigRockFrame(-2);assert(r:GetBigRockFrame()==-2);assert(select('#',r:UpdateAnimFrame({}))==0)
 for _,name in ipairs({'AddCoins','AddHearts','AddKeys','MoveDelayed','PlayChargeAnim','PlayFloatAnim','PlayShootAnim','MoveDiagonally'})do
  assert(not pcall(function()f[name](f)end));assert(not pcall(function()f[name](f,false)end));assert(not pcall(function()f[name](f,{})end))
 end
 assert(not pcall(function()f:MoveDelayed(1.5)end));assert(not pcall(function()d:SetRoomTypes(1)end));assert(not pcall(function()d:SetRoomTypes(false,1)end));assert(not pcall(function()g:Hurt()end));assert(not pcall(function()r:SetBigRockFrame(1.5)end))
 for _,name in ipairs({'AddCoins','AddHearts','AddKeys','RemoveFromFollowers','RemoveFromDelayed','AddToDelayed','MoveDelayed','MoveDiagonally','PlayChargeAnim','PlayFloatAnim','PlayShootAnim','Shoot'})do local fn=f[name];assert(not pcall(function()fn(player,1)end));assert(not pcall(function()fn({},1)end))end
 for _,name in ipairs({'PlayPickupSound','PlayDropSound','AppearFast','GetCoinValue'})do local fn=p[name];assert(not pcall(function()fn(f,1)end))end
 assert(not pcall(function()d.SetLocked(r,true)end));assert(not pcall(function()r.GetBigRockFrame(d)end));assert(not pcall(function()g.Hurt(player,2)end));assert(not pcall(function()g.Hurt(nil,2)end))
 )lua";
 if(scene=="badguard"){g_ModuleBytes[guards::kEntityFamiliarShootEntry]^=1;script="local f=Isaac.FindByType(3)[1]:ToFamiliar();assert(not pcall(function()f:Shoot()end))";}
 if(luaL_loadstring(L,script)||lua_pcall(L,0,0,0)){fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}
 if(scene=="badguard"){lua_close(L);return 0;}
 unsigned expected[24];for(auto&n:expected)n=1;expected[16]=2;expected[17]=4;expected[18]=3;
 for(unsigned i=0;i<24;++i)if(calls[i]!=expected[i]){fprintf(stderr,"native %u calls=%u expected=%u\n",i,calls[i],expected[i]);return 2;}
 if(sounds!=2||shots!=1||frames!=5||dust!=1||follower||delayed||diagonal!=.75F||anim!=1||waitFrames!=2||big!=-2||damage!=2||current!=2||target!=3)return 3;
 if(Read<int>(fam,0xd8c)!=2||Read<int>(fam,0xd90)!=3||Read<int>(fam,0xd94)!=-1||Read<int>(pickup,0x5b8)!=1)return 4;
 if(scene=="badvirtual"){
  WriteWord(g_ModuleBytes,kGridEntity_PoopVtableOffset+0x28,g_EngineBase+0x1234);
  if(luaL_dostring(L,"assert(not pcall(function()g:Hurt(2)end))"))return 5;
  if(calls[16]!=2)return 6;
 }
 if(scene=="dead"){
  RetireEntityLifetime(AddressOf(g_Entities[kFamiliar]));RetireEntityLifetime(AddressOf(g_Entities[kPickup]));WriteWord(r,0,0);WriteWord(d,0,0);WriteWord(q,0,0);
  if(luaL_dostring(L,"assert(not pcall(function()f:Shoot()end));assert(not pcall(function()p:GetCoinValue()end));assert(not pcall(function()r:GetBigRockFrame()end));assert(not pcall(function()d:SetLocked(true)end));assert(not pcall(function()g:Hurt(2)end))"))return 7;
  if(calls[11]!=1||calls[15]!=1||calls[16]!=2||calls[18]!=3||calls[21]!=1)return 8;
 }
 if(scene=="crossbase"){
  std::vector<unsigned char>changed=g_ModuleBytes;auto newBase=AddressOf(changed);changed[guards::kEntityFamiliarShootEntry]^=1;WriteWord(g_Entities[kFamiliar],0,newBase+kEntityFamiliarVtableOffset);LuaRuntime::SetEngineModuleBase(newBase);
  if(luaL_dostring(L,"assert(not pcall(function()f:Shoot()end))"))return 9;
  if(calls[11]!=1)return 10;
 }
 lua_close(L);return 0;
}

'''
class Entities24Behavior(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='api100-entities-behavior-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  extra=ROOT/'runtime/src/interfaces/lua/api100_entities.cpp'
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source,extra_sources=()if extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_native_consumers_parameters_virtuals_guards_and_lifetime(self):
  for scene in ('normal','badguard','badvirtual','dead','crossbase'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
class Entities24Integration(Entities24Behavior):
 def test_native_consumers_parameters_virtuals_guards_and_lifetime(self):
  r=subprocess.run([str(self.binary),'integration'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

class StageApiRockCommunityReplay(Entities24Behavior):
 def test_native_consumers_parameters_virtuals_guards_and_lifetime(self):
  r=subprocess.run([str(self.binary),"community"],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
