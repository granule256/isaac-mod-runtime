import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

import subprocess,tempfile,re
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
MAIN=r'''
#include "interfaces/lua/rplus_health_api.hpp"
#include "interfaces/lua/rplus_health_guards.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
static unsigned calls[13]{};static bool maxFlag{},rottenFlag{},limitFlag{};static std::int32_t blackIndex{},boneIndex{},removedIndex{};
static std::int32_t Counter(void* p,std::uintptr_t off){std::int32_t v{};memcpy(&v,static_cast<unsigned char*>(p)+off,4);return v;}
static void Store(void* p,std::uintptr_t off,std::int32_t v){memcpy(static_cast<unsigned char*>(p)+off,&v,4);}
static void Black(void*p,std::int32_t n){++calls[0];Store(p,0x16c4,Counter(p,0x16c4)+n);}
static void Max(void*p,std::int32_t n,bool b){++calls[1];maxFlag=b;Store(p,0x16b8,Counter(p,0x16b8)+n);}
static void Rotten(void*p,std::int32_t n,bool b){++calls[2];rottenFlag=b;Store(p,0x2474,Counter(p,0x2474)+n);}
static void Soul(void*p,std::int32_t n){++calls[3];Store(p,0x16c4,Counter(p,0x16c4)+n);}
static bool PickBlack(void*){++calls[4];return true;}
static bool PickBone(void*){++calls[5];return false;}
static bool PickGolden(void*){++calls[6];return true;}
static bool PickRotten(void*){++calls[7];return false;}
static std::int32_t Limit(const void*,bool b){++calls[8];limitFlag=b;return b?24:20;}
static bool IsBlack(const void*,std::int32_t n){++calls[9];blackIndex=n;return n==1;}
static bool IsBone(const void*,std::int32_t n){++calls[10];boneIndex=n;return n==2;}
static void Remove(void*,std::int32_t n){++calls[11];removedIndex=n;}
static void Full(void*p){++calls[12];Store(p,0x16bc,Counter(p,0x16b8));}
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 namespace fields=isaac::runtime::rplus_health;
 auto guard=[&](auto off,const auto& bytes){memcpy(g_ModuleBytes.data()+off,bytes.data(),bytes.size());};
 guard(fields::kGoldenReaderEntry,fields::kGoldenReaderGuard);guard(fields::kRottenReaderEntry,fields::kRottenReaderGuard);guard(fields::kFullHealthReaderEntry,fields::kFullHealthReaderGuard);
 auto&p=g_Entities[kPlayer];Store(p.data(),0x16b8,8);Store(p.data(),0x16bc,1);Store(p.data(),0x16c4,2);Store(p.data(),0x1dc4,3);Store(p.data(),0x2474,2);
 if(scene=="overflow"){Store(p.data(),0x16b8,0);Store(p.data(),0x16bc,INT32_MAX);Store(p.data(),0x16c4,1);}
 if(scene=="badguard")g_ModuleBytes[fields::kFullHealthReaderEntry]^=1;
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 isaac::runtime::RPlusHealthNativeTestBindings native{};
 native.methods[0]=isaac::runtime::engine_call::AddressOfFunction(&Black);native.methods[1]=isaac::runtime::engine_call::AddressOfFunction(&Max);native.methods[2]=isaac::runtime::engine_call::AddressOfFunction(&Rotten);native.methods[3]=isaac::runtime::engine_call::AddressOfFunction(&Soul);
 native.methods[4]=isaac::runtime::engine_call::AddressOfFunction(&PickBlack);native.methods[5]=isaac::runtime::engine_call::AddressOfFunction(&PickBone);native.methods[6]=isaac::runtime::engine_call::AddressOfFunction(&PickGolden);native.methods[7]=isaac::runtime::engine_call::AddressOfFunction(&PickRotten);
 native.methods[8]=isaac::runtime::engine_call::AddressOfFunction(&Limit);native.methods[9]=isaac::runtime::engine_call::AddressOfFunction(&IsBlack);native.methods[10]=isaac::runtime::engine_call::AddressOfFunction(&IsBone);native.methods[11]=isaac::runtime::engine_call::AddressOfFunction(&Remove);native.methods[12]=isaac::runtime::engine_call::AddressOfFunction(&Full);
 isaac::runtime::SetRPlusHealthNativeTestBindings(native);
 std::string script=R"lua(local m=RegisterMod('chapi-health',1);_health={count=0,step=0};m:AddCallback(1,function()
 local player=Isaac.GetPlayer();local oldAssert=assert;local function assert(v)_health.step=_health.step+1;oldAssert(v)end
 assert(type(player.HasFullHeartsAndSoulHearts)=='function')
 )lua";
 if(scene=="overflow")script+="assert(player:HasFullHeartsAndSoulHearts()==false)";
 else if(scene=="badguard")script+="assert(not pcall(function()player:HasFullHeartsAndSoulHearts()end))";
 else script+=R"lua(
 assert(player:GetGoldenHearts()==3 and player:GetRottenHearts()==2)
 assert(player:HasFullHeartsAndSoulHearts()==false)
 player:AddMaxHearts('4294967298');player:AddRottenHearts(1,true)
 player:AddSoulHearts(3.0);assert(player:HasFullHeartsAndSoulHearts()==false)
 player:AddBlackHearts(5);assert(player:HasFullHeartsAndSoulHearts()==true)
 assert(player:GetRottenHearts()==3 and player:GetGoldenHearts()==3)
 assert(player:CanPickBlackHearts()==true and player:CanPickBoneHearts()==false)
 assert(player:CanPickGoldenHearts()==true and player:CanPickRottenHearts()==false)
 assert(player:GetHeartLimit()==20 and player:GetHeartLimit(false)==20)
 assert(player:GetHeartLimit('false')==24)
 assert(player:IsBlackHeart('4294967297')==true and player:IsBoneHeart(2.0)==true)
 player:RemoveBlackHeart('4294967295');player:SetFullHearts();assert(player:GetHearts()==10)
 assert(not pcall(function()player:AddSoulHearts()end))
 assert(not pcall(function()player:AddMaxHearts(false)end))
 assert(not pcall(function()player:AddRottenHearts(1.5)end))
 assert(not pcall(function()player:IsBlackHeart(false)end))
 )lua";
 script+="\n_health.count=_health.count+1 end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@chapi-health.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){double step=0;static_cast<void>(LuaRuntime::ReadLuaTableNumber("_health","step",&step));fprintf(stderr,"health assertion step=%g\\n",step);return 2;}
 double count=0;if(LuaRuntime::ReadLuaTableNumber("_health","count",&count)||count!=1)return 3;
 if(scene=="normal"){
  for(unsigned i=0;i<13;++i)if(calls[i]!=(i==8?3:1))return 4;
  if(maxFlag||!rottenFlag||!limitFlag||blackIndex!=1||boneIndex!=2||removedIndex!=-1)return 5;
 }
 return 0;
}
'''
class RPlusHealthBehaviorTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-rplus-health-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_original_chapi_health_contracts_and_native_consumers(self):
  for scene in ('normal','badguard','overflow'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
