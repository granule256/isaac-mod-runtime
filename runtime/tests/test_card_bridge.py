import subprocess,tempfile,unittest,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include "card_hook.hpp"
#include <cassert>
static unsigned nativeCalls=0,constructCalls=0,destroyCalls=0;
static std::uint32_t Native(const void*,std::uint32_t seed,bool p,bool r,bool o){++nativeCalls;assert(seed==123&&p&&!r&&o);return 42;}
static void Construct(void* p,std::uint32_t seed,std::uint32_t shift){++constructCalls;assert(seed==123&&shift==35);std::uint32_t words[4]={seed,5,9,7};memcpy(p,words,16);}
static void Advance(void* p){std::uint32_t seed;memcpy(&seed,p,4);seed^=seed>>5;seed^=seed<<9;seed^=seed>>7;memcpy(p,&seed,4);}
static void Destroy(void*){++destroyCalls;}
int main(int argc,char** argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);LuaRuntime::ObserveGameThread();LuaRuntime::SetRngBindings(0,reinterpret_cast<std::uintptr_t>(&Advance));
 std::string script=R"lua(local m=RegisterMod('card20',1);_card={a=0,b=0};
 m:AddCallback(20,function(_,rng,card,p,r,o)assert(card==42 and p==true and r==false and o==true);assert(rng:GetSeed()==123);SAVED=rng;_card.a=_card.a+1;)lua";
 if(scene=="normal"||scene=="param")script+="assert(rng:Next()==61848)";
 if(scene=="integer")script+="return '4294967297'";
 if(scene=="zero")script+="return 0";
 if(scene=="negative")script+="return -1";
 if(scene=="float")script+="return 9.0";
 if(scene=="fraction")script+="return 9.5";
 if(scene=="false")script+="return false";
 if(scene=="error")script+="error('card20 error')";
 script+=R"lua(
 end)
 m:AddCallback(20,function(_,rng)assert(rng==SAVED and rng:GetSeed()==61848);_card.b=_card.b+1;return nil end)
 m:AddCallback(1,function()assert(not pcall(function()return SAVED:GetSeed()end))end)
 )lua";
 if(scene=="param")script+=";setmetatable(Isaac.GetCallbacks(20),{__matchParams=function(a,b) assert(a==-1);return true end})";
 if(scene=="builtin")script+="Isaac.SetBuiltInCallbackState(20,false)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@card20.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 isaac::runtime::CardNativeBindings native{Native,Construct,Destroy};
 auto result=isaac::runtime::RunCardIntercept(&native,nullptr,123,true,false,true);
 if(nativeCalls!=1||constructCalls!=(scene=="builtin"?0:1)||destroyCalls!=constructCalls)return 2;
 if(result!=(scene=="integer"?1:scene=="zero"?0:scene=="negative"?UINT32_MAX:scene=="float"?9:42))return 3;
 if(LuaRuntime::TakeCallbackError()!=(scene=="false"||scene=="fraction"||scene=="error"))return 4;
 double a=0,b=0;if(LuaRuntime::ReadLuaTableNumber("_card","a",&a)||LuaRuntime::ReadLuaTableNumber("_card","b",&b))return 5;
 if(a!=(scene=="builtin"?0:1)||b!=((scene=="normal"||scene=="param")?1:0))return 6;
 if(scene!="builtin"){LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError())return 7;}
 return 0;
}
'''
class CardBridgeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-card20-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source,extra_sources=(ROOT/'runtime/source/card_hook.cpp',))
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_original_cleanup_low32_error_and_shared_userdata(self):
  for scene in ('normal','param','integer','zero','negative','float','fraction','false','error','builtin'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
