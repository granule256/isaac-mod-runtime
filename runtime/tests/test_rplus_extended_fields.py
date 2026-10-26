"""原模组字段表达式必须消费原生值与必要setter效果。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include "interfaces/lua/rplus_extended_fields.hpp"
#include "interfaces/lua/rplus_extended_fields_guards.hpp"
#include "interfaces/lua/engine_color_mod.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include <cassert>
#include <cmath>
using namespace isaac::runtime;
template<class T>T ReadAt(const std::vector<unsigned char>&v,std::size_t o){T t{};std::memcpy(&t,v.data()+o,sizeof(t));return t;}
static unsigned targets{},children{},heights{},parents{};
[[maybe_unused]] static void Parent(void*p,void*t){++parents;std::memcpy(static_cast<unsigned char*>(p)+0x390,&t,8);}
template<class T>void BindParent(T&b){if constexpr(requires{b.setParent;})b.setParent=Parent;}
static void Target(void*p,void*t){++targets;std::memcpy(static_cast<unsigned char*>(p)+0x3a0,&t,8);}
static void Child(void*p,void*t){++children;std::memcpy(static_cast<unsigned char*>(p)+0x398,&t,8);}
static void Height(void*p,float f){++heights;std::memcpy(static_cast<unsigned char*>(p)+0x400,&f,4);float render=f/2;std::memcpy(static_cast<unsigned char*>(p)+0x324,&render,4);}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();FillEntities();
 g_Entities[kFamiliar].resize(0x1000);WriteWord(g_Entities[kEffect],0,g_EngineBase+kEntityEffectVtableOffset);WriteWord(g_Entities[kTearNear],0,g_EngineBase+kEntityTearVtableOffset);WriteWord(g_Entities[kBullet],0,g_EngineBase+kEntityProjectileVtableOffset);
 auto&bomb=g_Entities[kSizeOnly];bomb.assign(0xc00,0);WriteWord(bomb,0,g_EngineBase+kEntityBombVtableOffset);WriteAt<std::uint32_t>(bomb,kEntityTypeOffset,4);bomb[kEntityExistsOffset]=1;
 PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 std::vector<unsigned char> manager(kManagerItemConfigOffset+0x100),slot(8),item(0x200),items(16);
 WriteWord(slot,0,AddressOf(manager));WriteWord(g_ModuleBytes,kGameManagerGlobalSlotOffset,AddressOf(slot));
 WriteAt<std::uint32_t>(item,kItemConfigItemTypeOffset,kItemTypePassive);WriteAt<std::uint32_t>(item,kItemConfigItemIdOffset,1);WriteWord(items,8,AddressOf(item));WriteWord(manager,kManagerItemConfigOffset+kItemConfigCollectibleBeginOffset,AddressOf(items));WriteWord(manager,kManagerItemConfigOffset+kItemConfigCollectibleEndOffset,AddressOf(items)+16);
 WriteWord(g_Entities[kPlayer],kEntityPlayerQueuedItemOffset,AddressOf(item));
 WriteAt<std::uint32_t>(g_GameBytes,0x21510,2);
 for(unsigned x=0;x<2;++x){const auto d=0x18+x*0x100;WriteAt<std::uint32_t>(g_GameBytes,d,97+x);WriteAt<std::uint32_t>(g_GameBytes,d+4,97+x);WriteAt<std::uint32_t>(g_GameBytes,d+8,x);WriteAt<std::int16_t>(g_GameBytes,d+0xf2,x==0?3:-1);}
 WriteWord(g_RoomBytes,kRoomDescriptorPointerOffset,AddressOf(g_GameBytes)+0x18);
 namespace guards=isaac::runtime::extended_fields;auto guard=[&](auto o,const auto&b){std::memcpy(g_ModuleBytes.data()+o,b.data(),b.size());};
 /*GUARDS*/
 if(scene=="badguard")g_ModuleBytes[guards::kFamiliar1Entry]^=1;
 if(scene=="badparentguard")g_ModuleBytes[guards::kSetParent0Entry]^=1;
 ExtendedFieldsNativeTestBindings bindings{Target,Child,Height};BindParent(bindings);SetExtendedFieldsNativeTestBindings(bindings);
 WriteAt<std::int32_t>(g_Entities[kFamiliar],0xd60,18);WriteAt<std::int32_t>(g_Entities[kFamiliar],0xd9c,3);WriteAt<std::int32_t>(g_Entities[kFamiliar],0xd90,15);WriteAt<std::int32_t>(g_Entities[kFamiliar],0xd94,13);
 WriteAt<float>(g_Entities[kTearNear],0x400,-5);WriteAt<float>(g_Entities[kPlayer],0x124,1);WriteAt<float>(g_Entities[kPlayer],0x128,2);
 for(unsigned i=0;i<7;++i)WriteAt<std::int32_t>(item,0x58+i*4,static_cast<std::int32_t>(i+1));item[0xb4]=1;
 WriteAt<std::int32_t>(g_Entities[kPlayer],0x1d6c,4);
 const std::string setup="local m=RegisterMod('extended-fields',1);m:AddCallback(1,function() local p=Isaac.GetPlayer();local f=Isaac.FindByType(3)[1]:ToFamiliar();local t=Isaac.FindByType(2)[1]:ToTear();local q=Isaac.FindByType(5)[1]:ToPickup();local b=Isaac.FindByType(4)[1]:ToBomb();local e=Isaac.FindByType(1000)[1]:ToEffect();local j=Isaac.FindByType(9)[1]:ToProjectile();";
 const char*body=R"lua(
 assert(f.FireCooldown==18 and f.RoomClearCount>=3 and f.Hearts>=15 and f.Keys==13)
 f.FireCooldown=f.FireCooldown-1;f.RoomClearCount=0;f.Hearts=16;f.Keys=14;f.State=-1000;f.IsFollower=true
 assert(f.IsFollower and f.State==-1000)
 f.SpriteOffset=f.SpriteOffset+Vector(0,-.4);f.SpriteScale=Vector(.6,.7)
 p.Target=f;assert(p.Target.Index==f.Index);p.Target=nil;assert(p.Target==nil)
 p.Child=t;assert(p.Child.Index==t.Index);p.Child=nil
 p.Parent=f;assert(p.Parent.Index==f.Index);p.Parent=t;assert(p.Parent.Index==t.Index);p.Parent=nil;assert(p.Parent==nil)
 p.DepthOffset=-100;p.EntityCollisionClass=0;p.GridCollisionClass=5
 local c=Color(.2,.3,.4,.5,1,2,3);c:SetColorize(.6,.7,.8,.9);f.SplatColor=c
 assert(math.abs(f.SplatColor.R-.2)<1e-5 and f.SplatColor.RO==1)
 q.State=2;q.Timeout=600;q.Wait=20;q.Charge=12;assert(q.State==2 and q.Timeout==600 and q.Wait==20 and q.Charge==12)
 e.FallingSpeed=-14;e.FallingAcceleration=1.3;e.m_Height=e.FallingSpeed;e.State=1;e.Timeout=27;e.Rotation=90
 assert(e.m_Height==-14 and e.State==1 and e.Timeout==27 and e.Rotation==90)
 t.Height=-11;t.KnockbackMultiplier=.8;t.Rotation=30;j.Height=-22;b.ExplosionDamage=35;p.ItemHoldCooldown=0
 local sp=t:GetSprite();sp.Rotation=t.Velocity:GetAngleDegrees()+90
 local r1=Game():GetLevel():GetRoomByIdx(97);local r2=Game():GetLevel():GetRoomByIdx(98);assert(r1.ShopItemDiscountIdx==3 and r2.ShopItemDiscountIdx==-1);r1.ShopItemDiscountIdx=65537;r2.ShopItemDiscountIdx=32768;assert(r1.ShopItemDiscountIdx==1 and r2.ShopItemDiscountIdx==-32768)
 local i=p.QueuedItem.Item;assert(i.Special and i.AddMaxHearts==1 and i.AddHearts==2 and i.AddSoulHearts==3 and i.AddBlackHearts==4 and i.AddBombs==5 and i.AddKeys==6 and i.AddCoins==7);i.AddCoins="23";i.Special=false;assert(i.AddCoins==23 and not i.Special)
 _extended={done=1}
 )lua";
 if(scene=="badguard")body="assert(not pcall(function()return f.Hearts end));_extended={done=1}";
 if(scene=="badparentguard")body="assert(not pcall(function()p.Parent=f end));assert(p.Parent==nil);_extended={done=1}";
 if(scene=="types")body=R"lua(
  assert(not pcall(function()f.FireCooldown=1.5 end))
  f.State=4294967297;assert(f.State==1);f.FireCooldown="19";assert(f.FireCooldown==19)
  f.IsFollower=0;assert(f.IsFollower);f.IsFollower=nil;assert(not f.IsFollower)
  assert(not pcall(function()p.Parent=false end));assert(not pcall(function()p.Parent={} end));assert(p.Parent==nil)
  assert(not pcall(function()p.Target=false end));assert(not pcall(function()p.SpriteScale={} end))
  assert(not pcall(function()f.SplatColor={} end));p.DepthOffset="2.5";assert(p.DepthOffset==2.5)
  _extended={done=1}
 )lua";
 const auto script=setup+body+"end)";
 if(LuaRuntime::InitializeFromBuffer(script.c_str(),script.size(),"@extended-fields.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 // 未知名字必须在配置/实体校验前退出，不能给HasCollectible/Position新增分类。
 auto*L=LuaRuntime::StateForTesting(); /*STATE*/
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView errs[8]{};const auto n=LuaRuntime::CopyLuaErrorHistory(errs,8);for(unsigned x=0;x<n;++x)fprintf(stderr,"%s\n",errs[x].text);return 2;}
 double done{};if(LuaRuntime::ReadLuaTableNumber("_extended","done",&done)||done!=1)return 3;
 if(scene=="badguard"||scene=="types"||scene=="badparentguard")return 0;
 if(targets!=2||children!=2||heights!=1||parents!=3||ReadAt<std::uintptr_t>(g_Entities[kPlayer],0x390)!=0)return 4;
 if(ReadAt<std::int32_t>(g_Entities[kFamiliar],0xd60)!=17||ReadAt<float>(g_Entities[kTearNear],0x324)!=-5.5F||ReadAt<std::int32_t>(g_Entities[kPickup],0x574)!=20)return 5;
 if(ReadAt<float>(g_Entities[kTearNear],0x460)!=.8F||ReadAt<float>(bomb,0x408)!=35||ReadAt<float>(g_Entities[kEffect],0x46c)!=90)return 6;
 const auto cm=ReadAt<EngineColorMod>(g_Entities[kFamiliar],0x24c);
 if(std::fabs(cm.colorize[3]-.9F)>1e-5||cm.shift[2]!=3||ReadAt<std::int32_t>(item,0x70)!=23||item[0xb4]!=0)return 7;
 if(ReadAt<std::int16_t>(g_GameBytes,0x18+0xf2)!=1||ReadAt<std::int16_t>(g_GameBytes,0x118+0xf2)!=-32768)return 8;
 return 0;
}
'''
class ExtendedFieldConsumers(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-extended-fields-')
  header=(ROOT/'runtime/src/interfaces/lua/rplus_extended_fields_guards.hpp').read_text()
  guards='\n'.join(f'guard(guards::k{name}Entry,guards::k{name}Guard);' for name in re.findall(r'k(\w+)Entry=',header))
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN.replace('/*GUARDS*/',guards)
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  source=source.replace('auto*L=LuaRuntime::StateForTesting(); /*STATE*/','assert(TryPushExtendedEntityField(nullptr,0,"HasCollectible")==0);assert(!TryWriteExtendedEntityField(nullptr,0,"Position"));assert(TryPushExtendedItemConfigField(nullptr,0,"ID")==0);')
  extra=ROOT/'runtime/src/interfaces/lua/rplus_extended_fields.cpp'
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source,extra_sources=()if extra in layered_lua_runtime_sources(fixture.SOURCE)else(extra,))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_consumers_and_guard_rejection(self):
  for scene in ('normal','badguard','types','badparentguard'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],text=True,capture_output=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
