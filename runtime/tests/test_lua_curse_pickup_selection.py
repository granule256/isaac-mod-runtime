"""12/37实际Lua：首非nil、整数规则、局部覆盖时机与错误的部分写入。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;std::string scene=argv[1];CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 bool curse=scene.rfind("curse",0)==0;unsigned flags=5,variant=10,subtype=7;
 std::string returned;
 if(scene=="curse_zero")returned="return 0";
 else if(scene=="curse_low32")returned="return '4294967298'";
 else if(scene=="curse_false")returned="return false";
 else if(scene=="curse_error"||scene=="pickup_error")returned="error('native-event')";
 else if(scene=="curse_nil")returned="return nil";
 else if(scene=="pickup_pair")returned="return {40,5}";
 else if(scene=="pickup_one")returned="return {40}";
 else if(scene=="pickup_two")returned="return {[2]='4294967299'}";
 else if(scene=="pickup_partial_error")returned="return {40,{}}";
 else if(scene=="pickup_meta")returned="return setmetatable({},{__index=function(_,k) if k==1 then return '40' else return 6 end end})";
 else if(scene=="pickup_meta_error")returned="return setmetatable({},{__index=function(_,k) if k==1 then return 40 else error('second') end end})";
 else if(scene=="pickup_false")returned="return false";
 else if(scene=="pickup_empty")returned="return {}";
 else if(scene=="pickup_nil")returned="return nil";
 else if(scene=="pickup_builtin")returned="return {40,5}";
 else return 98;
 std::string script="_event={head=0,tail=0};local m=RegisterMod('12-37',1);m:AddCallback("+std::string(curse?"12":"37")+",function(_,"+std::string(curse?"flags":"p,v,s")+") _event.head=_event.head+1;";
 script+=curse?"assert(flags==5);":"assert(p.Type==5 and p.Variant==100 and v==10 and s==7);p:GetData().seen=true;";
 script+=returned+" end);m:AddCallback("+std::string(curse?"12":"37")+",function() _event.tail=_event.tail+1;return "+std::string(curse?"3":"{41,8}")+" end)";
 if(scene=="pickup_builtin")script+=";Isaac.SetBuiltInCallbackState(37,false)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@12-37.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(curse)flags=LuaRuntime::DispatchPostCurseEval(flags);
 else LuaRuntime::DispatchPostPickupSelection(AddressOf(g_Entities[kPickup]),&variant,&subtype);
 double head{},tail{};if(LuaRuntime::ReadLuaTableNumber("_event","head",&head)||LuaRuntime::ReadLuaTableNumber("_event","tail",&tail))return 2;
 bool nil=scene=="curse_nil"||scene=="pickup_nil";
 if(head!=(scene=="pickup_builtin"?0:1)||tail!=(nil?1:0))return 3;
 bool error=scene=="curse_false"||scene=="curse_error"||scene=="pickup_error"||scene=="pickup_partial_error"||scene=="pickup_meta_error";
 if(LuaRuntime::TakeCallbackError()!=error)return 4;
 if(curse){unsigned want=scene=="curse_zero"?0:scene=="curse_low32"?2:scene=="curse_nil"?3:5;if(flags!=want)return 5;}
 else{
  unsigned wantV=scene=="pickup_nil"?41:scene=="pickup_pair"||scene=="pickup_one"||scene=="pickup_partial_error"||scene=="pickup_meta"||scene=="pickup_meta_error"?40:10;
  unsigned wantS=scene=="pickup_nil"?8:scene=="pickup_pair"?5:scene=="pickup_two"?3:scene=="pickup_meta"?6:7;
  if(variant!=wantV||subtype!=wantS)return 6;
  unsigned actual{};std::memcpy(&actual,g_Entities[kPickup].data()+kEntityVariantOffset,4);if(actual!=100)return 7;
 }
 return 0;
}
'''
class CursePickupLuaTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.binary=None
  header=(ROOT/'runtime/source/lua_runtime.hpp').read_text()
  if 'DispatchPostCurseEval' not in header or 'DispatchPostPickupSelection' not in header:return
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-curse-pickup-')
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', source,count=1)
  cls.binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
 @classmethod
 def tearDownClass(cls):
  if cls.binary:cls.tmp.cleanup()
 def test_native_dispatchers_exist(self):self.assertIsNotNone(self.binary,'正确12/37派发桥尚未实现')
 def test_curse_and_pickup_exact_values_and_partial_errors(self):
  if not self.binary:self.skipTest('派发桥尚未实现')
  for scene in ('curse_zero','curse_low32','curse_false','curse_error','curse_nil','pickup_pair','pickup_one','pickup_two','pickup_partial_error','pickup_meta','pickup_meta_error','pickup_false','pickup_empty','pickup_nil','pickup_error','pickup_builtin'):
   with self.subTest(scene=scene):
    r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
