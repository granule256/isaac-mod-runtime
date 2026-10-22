"""锁定原模组需要的方法，不把候选继承项当新实现。"""
import unittest,subprocess,tempfile,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
BASELINE_MAIN=r'''
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 const char*script="local m=RegisterMod('rplus-methods',1);m:AddCallback(1,function()local p=Isaac.GetPlayer();assert(type(p.FullCharge)=='function' and type(p.GetAimDirection)=='function' and type(p.AddBurn)=='function')end)";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@methods-baseline.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();return LuaRuntime::TakeCallbackError()?2:0;
}
'''
class RPlusMethodsContractTests(unittest.TestCase):
 def test_locked_mod_method_consumers_exist(self):
  with tempfile.TemporaryDirectory(prefix='isaac-rplus-methods-')as d:
   source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+BASELINE_MAIN
   source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=source)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,'原模组所需Player/继承Entity方法未接：'+r.stdout+r.stderr)
METHODS_MAIN=r'''
#include "interfaces/lua/rplus_methods_api.hpp"
#include "interfaces/lua/rplus_methods_guards.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
#include <cmath>
using Vec=LuaRuntime::VectorHandle;
static unsigned calls[25]{};static void* wantPlayer{};static void* wantNpc{};static void* wantBomb{};static void* wantFamiliar{};static void* wantItem{};static void* wantDoor{};
static void Ref(const void* p){std::uintptr_t entity{};std::memcpy(&entity,static_cast<const unsigned char*>(p)+0x28,8);assert(entity==reinterpret_cast<std::uintptr_t>(wantPlayer));}
static void Burn(void*p,const void*r,std::int32_t n,float f){++calls[0];assert(p==wantNpc&&n==30&&f==1.5F);Ref(r);}
static void Confusion(void*p,const void*r,std::int32_t n,bool b){++calls[1];assert(p==wantNpc&&n==4&&b);Ref(r);}
static void Midas(void*p,const void*r,std::int32_t n){++calls[2];assert(p==wantNpc&&n==5);Ref(r);}
static void Shrink(void*p,const void*r,std::int32_t n){++calls[3];assert(p==wantNpc&&n==6);Ref(r);}
static void Slowing(void*p,const void*r,std::int32_t n,float f,isaac::runtime::EngineColorMod c){++calls[4];assert(p==wantNpc&&n==7&&f==.8F&&c.tint[1]==.5F&&c.shift[0]==1&&std::fabs(c.colorize[3]-.5F)<1e-6);Ref(r);}
static bool Mortal(void*p){++calls[5];assert(p==wantNpc);return true;}
static void Costume(void*p,const void*i,bool b){++calls[6];assert(p==wantPlayer&&i==wantItem&&b);}
static void* Wisp(void*p,std::int32_t n,const Vec&v,bool a,bool b){++calls[7];assert(p==wantPlayer&&n==8&&v.x==10&&v.y==20&&!a&&b);return wantFamiliar;}
static void Card(void*p,std::int32_t n,const char*a){++calls[8];assert(p==wantPlayer&&n==9&&!std::strcmp(a,"Pickup"));}
static void Pickup(void*p,const void*sp,bool b,const char*a){++calls[9];assert(p==wantPlayer&&sp==static_cast<unsigned char*>(wantPlayer)+kEntitySpriteOffset&&!b&&!std::strcmp(a,"Pickup"));}
static bool CanPickup(void*p){++calls[10];assert(p==wantPlayer);return true;}
static void* Bomb(void*p,const Vec&a,const Vec&b,void* source){++calls[11];assert(p==wantPlayer&&a.x==10&&b.y==2&&source==nullptr);return wantBomb;}
static bool Flush(void*p){++calls[12];assert(p==wantPlayer);return false;}
static std::int32_t Charge(void*p,std::int32_t slot,bool force){++calls[13];assert(p==wantPlayer&&slot==0&&!force);return 2;}
static std::int32_t Trinkets(const void*p){++calls[14];assert(p==wantPlayer);return 4;}
static Vec Inheritance(const void*p,const Vec&d,bool b){++calls[15];assert(p==wantPlayer&&d.x==.25F&&d.y==-.5F&&!b);return {3,4};}
static void RemoveCostume(void*p,const void*i){++calls[16];assert(p==wantPlayer&&i==wantItem);}
static void Pill(void*p,std::int32_t slot,std::int32_t id){++calls[17];assert(p==wantPlayer&&slot==1&&id==-1);}
static void Pocket(void*p,std::int32_t id,std::uint32_t slot,bool b){++calls[18];assert(p==wantPlayer&&id==10&&slot==2&&!b);}
static void* Spider(void*p,const Vec&a,const Vec&b){++calls[19];assert(p==wantPlayer&&a.x==10&&b.x==30);return wantFamiliar;}
static bool Revive(void*p){++calls[20];assert(p==wantPlayer);return true;}
static void Fart(void*,const Vec&a,float r,void*src,float scale,std::uint32_t type,const isaac::runtime::EngineColorMod&c){++calls[21];assert(a.x==10&&r==85&&src==nullptr&&scale==1&&type==0&&c.tint[0]==1&&c.colorize[3]==0);}
static void Shake(void*,std::int32_t n){++calls[22];assert(n==11);}
static void Bar(void*p){++calls[23];assert(p==wantDoor);}
static void Find(void*p,const Vec&v,float speed,std::int32_t mark,bool b){++calls[24];assert(p==static_cast<unsigned char*>(wantNpc)+kEntityNpcPathfinderOffset&&v.x==10&&speed==1.25F&&mark==1&&!b);}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();g_GameBytes.resize(0x26fa70);FillEntities();
 WriteWord(g_Entities[kTearNear],0,g_EngineBase+kEntityTearVtableOffset);
 FillEntity(kNoQuery,7,0,0,80,280,4,5,900,g_EngineBase+kEntityLaserVtableOffset,0);
 FillEntity(kCharmed,8,0,0,80,280,4,7,900,g_EngineBase+kEntityKnifeVtableOffset,0);
 WriteWord(g_Entities[kBullet],0,g_EngineBase+kEntityProjectileVtableOffset);
 std::uint32_t projectileFlags=0x80000000;std::memcpy(g_Entities[kBullet].data()+kEntityProjectileFlagsOffset,&projectileFlags,4);
 wantPlayer=g_Entities[kPlayer].data();wantNpc=g_Entities[kEnemyA].data();wantFamiliar=g_Entities[kFamiliar].data();
 auto& bomb=g_Entities[kSizeOnly];bomb.assign(0xc00,0);WriteWord(bomb,0,g_EngineBase+kEntityBombVtableOffset);std::uint32_t type=4;std::memcpy(bomb.data()+kEntityTypeOffset,&type,4);bomb[kEntityExistsOffset]=1;wantBomb=bomb.data();
 PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 std::vector<unsigned char> manager(kManagerItemConfigOffset+0x100),managerSlot(8),item(0x200),items(16),door(0x400),grids(16*8),descriptor(0x100);
 wantItem=item.data();wantDoor=door.data();
 WriteWord(managerSlot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(managerSlot));
 WriteWord(items,8,AddressOf(item));WriteWord(manager,kManagerItemConfigOffset+kItemConfigCollectibleBeginOffset,AddressOf(items));WriteWord(manager,kManagerItemConfigOffset+kItemConfigCollectibleEndOffset,AddressOf(items)+items.size());
 WriteWord(door,0,g_EngineBase+kGridEntity_DoorVtableOffset);WriteWord(grids,3*8,AddressOf(door));WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+3*8,AddressOf(door));WriteWord(g_RoomBytes,kRoomDoorObjectTableOffset,AddressOf(door));
 std::uint32_t gridIndex=3;std::memcpy(g_RoomBytes.data()+kRoomDoorGridIndexTableOffset,&gridIndex,4);
 WriteWord(g_RoomBytes,kRoomDescriptorPointerOffset,AddressOf(descriptor));std::uint32_t award=0x89abcdef;std::memcpy(descriptor.data()+0x6c,&award,4);
 namespace guards=isaac::runtime::rplus_methods;
 auto guard=[&](auto off,const auto&bytes){std::memcpy(g_ModuleBytes.data()+off,bytes.data(),bytes.size());};
 guard(guards::kAimWriterEntry,guards::kAimWriterGuard);guard(guards::kBombCountdownWriterEntry,guards::kBombCountdownWriterGuard);guard(guards::kHeartStagesWriterEntry,guards::kHeartStagesWriterGuard);guard(guards::kGridDescWriterEntry,guards::kGridDescWriterGuard);guard(guards::kAwardSeedReaderEntry,guards::kAwardSeedReaderGuard);
 Vec aim{.25F,-.5F};std::memcpy(g_Entities[kPlayer].data()+0x1a04,&aim,sizeof(aim));
 std::uint32_t stageCount=3;std::memcpy(g_GameBytes.data()+0x26fa68,&stageCount,4);
 if(scene=="badguard")g_ModuleBytes[guards::kAimWriterEntry]^=1;
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 isaac::runtime::RPlusMethodsNativeTestBindings native{};std::uintptr_t pointers[]={
  isaac::runtime::engine_call::AddressOfFunction(&Burn),isaac::runtime::engine_call::AddressOfFunction(&Confusion),isaac::runtime::engine_call::AddressOfFunction(&Midas),isaac::runtime::engine_call::AddressOfFunction(&Shrink),isaac::runtime::engine_call::AddressOfFunction(&Slowing),isaac::runtime::engine_call::AddressOfFunction(&Mortal),isaac::runtime::engine_call::AddressOfFunction(&Costume),isaac::runtime::engine_call::AddressOfFunction(&Wisp),isaac::runtime::engine_call::AddressOfFunction(&Card),isaac::runtime::engine_call::AddressOfFunction(&Pickup),isaac::runtime::engine_call::AddressOfFunction(&CanPickup),isaac::runtime::engine_call::AddressOfFunction(&Bomb),isaac::runtime::engine_call::AddressOfFunction(&Flush),isaac::runtime::engine_call::AddressOfFunction(&Charge),isaac::runtime::engine_call::AddressOfFunction(&Trinkets),isaac::runtime::engine_call::AddressOfFunction(&Inheritance),isaac::runtime::engine_call::AddressOfFunction(&RemoveCostume),isaac::runtime::engine_call::AddressOfFunction(&Pill),isaac::runtime::engine_call::AddressOfFunction(&Pocket),isaac::runtime::engine_call::AddressOfFunction(&Spider),isaac::runtime::engine_call::AddressOfFunction(&Revive),isaac::runtime::engine_call::AddressOfFunction(&Fart),isaac::runtime::engine_call::AddressOfFunction(&Shake),isaac::runtime::engine_call::AddressOfFunction(&Bar),isaac::runtime::engine_call::AddressOfFunction(&Find)};
 for(unsigned i=0;i<25;++i)native.methods[i]=pointers[i];isaac::runtime::SetRPlusMethodsNativeTestBindings(native);
 std::string script=R"lua(local m=RegisterMod('rplus-methods-native',1);_methods={count=0,step=0};m:AddCallback(1,function()
 local oldAssert=assert;local function assert(v)_methods.step=_methods.step+1;oldAssert(v)end
 local player=Isaac.GetPlayer();assert(type(player.GetAimDirection)=='function')
 if _methods.count>0 then
  if _methods.count==1 then assert(SAVED_AIM.X==.75 and SAVED_AIM.Y==-.5);assert(not pcall(function()SAVED_AIM.X=99 end));assert(not pcall(function()SAVED_AIM:Normalize()end))
  else assert(not pcall(function()return SAVED_AIM.X end)) end
  _methods.count=_methods.count+1;return
 end
 )lua";
 if(scene=="badguard")script+="assert(not pcall(function()player:GetAimDirection()end))";
 else script+=R"lua(
 local enemy=Isaac.FindByType(20)[1];local source=EntityRef(player)
 enemy:AddBurn(source,30,1.5);enemy:AddConfusion(source,'4294967300',0);enemy:AddMidasFreeze(source,5);enemy:AddShrink(source,6)
 local c=Color(1,.5,.2,.8,1,2,3);c:SetColorize(.2,.3,.4,.5);enemy:AddSlowing(source,7,.8,c);assert(enemy:HasMortalDamage())
 assert(not pcall(function()enemy:AddBurn(nil,1,1)end));assert(not pcall(function()enemy:AddShrink(source,1.5)end))
 local pos=Vector(10,20);local item=Isaac.GetItemConfig():GetCollectible(1);player:AddCostume(item,true);player:RemoveCostume(item)
 player:AnimatePickup(player:GetSprite(),false,false);enemy.Pathfinder:FindGridPath(pos,1.25,'4294967297',false)
 local wisp=player:AddWisp(8,pos,nil,true);assert(wisp~=nil and wisp.Type==3)
 player:AnimateCard(9,false);assert(player:CanPickupItem() and not player:FlushQueueItem())
 local bomb=player:FireBomb(pos,Vector(1,2));assert(bomb~=nil and bomb.Type==4);bomb:SetExplosionCountdown('4294967297')
 local function checkAddFlags(method,key)
  assert(type(method)=='function');local t={[key]=BitSet128(1,0x100)};method(t,2);method(t,BitSet128(0,0x200))
  assert(t[key].l==3 and t[key].h==0x300);assert(not pcall(function()method(t,'4')end))
 end
 checkAddFlags(bomb.AddTearFlags,'Flags');checkAddFlags(Isaac.FindByType(2)[1].AddTearFlags,'TearFlags')
 checkAddFlags(Isaac.FindByType(7)[1]:ToLaser().AddTearFlags,'TearFlags');checkAddFlags(Isaac.FindByType(8)[1].AddTearFlags,'TearFlags')
 local projectile=Isaac.FindByType(9)[1]:ToProjectile();assert(projectile:HasProjectileFlags(1<<31) and not projectile:HasProjectileFlags(1))

 assert(player:FullCharge(false)==true and player:GetMaxTrinkets()==4)
 local aim=player:GetAimDirection();SAVED_AIM=aim;assert(aim.X==.25 and aim.Y==-.5)
 local inheritance=player:GetTearMovementInheritance(aim);assert(inheritance.X==3 and inheritance.Y==4)
 player:SetPill(1,'4294967295');player:SetPocketActiveItem(10,false)
 assert(player:ThrowBlueSpider(pos,Vector(30,40))~=nil and player:WillPlayerRevive())
 local room=Game():GetRoom();local door=room:GetDoor(0);assert(door~=nil);door:Bar();local grid=room:GetGridEntity(3);grid:SetVariant('4294967313');assert(grid:GetVariant()==17);assert(room:GetAwardSeed()==2309737967)
 Game():Fart(pos,false,nil,false,false,false);Game():ShakeScreen('4294967307');Game():ClearStagesWithoutHeartsPicked()
 )lua";
 script+="\n_methods.count=_methods.count+1 end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@rplus-native-methods.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){double step=0;static_cast<void>(LuaRuntime::ReadLuaTableNumber("_methods","step",&step));fprintf(stderr,"methods assertion step=%g\n",step);LuaRuntime::LuaErrorHistoryEntryView errors[8]{};auto errorCount=LuaRuntime::CopyLuaErrorHistory(errors,8);for(unsigned i=0;i<errorCount;++i)fprintf(stderr,"%s\n",errors[i].text);return 2;}
 double count=0;if(LuaRuntime::ReadLuaTableNumber("_methods","count",&count)||count!=1)return 3;
 if(scene=="normal"){
  for(unsigned i=0;i<25;++i)if(calls[i]!=1)return 4;
  std::int32_t pair[2]{};std::memcpy(pair,bomb.data()+0x400,8);if(pair[0]!=1||pair[1]!=1)return 5;
  std::memcpy(&stageCount,g_GameBytes.data()+0x26fa68,4);if(stageCount!=0)return 6;
  aim.x=.75F;std::memcpy(g_Entities[kPlayer].data()+0x1a04,&aim,sizeof(aim));
  LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 7;
  isaac::runtime::RetireEntityLifetime(reinterpret_cast<std::uintptr_t>(wantPlayer));
  LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 8;
  if(LuaRuntime::ReadLuaTableNumber("_methods","count",&count)||count!=3)return 9;
 }
 return 0;
}
'''
class RPlusMethodsNativeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-rplus-methods-native-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+METHODS_MAIN
  source=source.replace("GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}",r"""GameRoomObservation ReadCurrentGameRoom(uintptr_t owner,void** room){
   std::uintptr_t game{};if(!owner||!room)return GameRoomObservation::GameNull;
   std::memcpy(&game,reinterpret_cast<void*>(owner),8);if(!game)return GameRoomObservation::GameNull;
   std::memcpy(room,reinterpret_cast<void*>(game+kGameRoomPointerOffset),8);
   return *room?GameRoomObservation::Success:GameRoomObservation::RoomNull;
  }""")
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_status_player_vectors_defaults_returns_and_native_cleanup(self):
  for scene in ('normal','badguard'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
