"""CHAPI原件类包装协议：共享身份、原方法保存与替换后的实际玩家调用。"""
import unittest, subprocess, tempfile, re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MOD=Path('/Users/kelinls/code/github/isaac mod/analysis/mod-sources/RepentancePlus/repentanceplus')
MAIN=r'''int main() {
 static_cast<void>(&BuildPrelude);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&ExpectNumber);static_cast<void>(kScriptTemplate);
 CreateBlocks(); FillEntities(); WriteWord(g_Entities[kTearNear],0,g_EngineBase+kEntityTearVtableOffset); WriteWord(g_Entities[kBullet],0,g_EngineBase+kEntityProjectileVtableOffset); PublishLists(); PublishGame(); PublishEntityList(g_RoomBytes,true); LuaRuntime::SetEngineModuleBase(g_EngineBase); LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 std::string script=R"lua(
 local mod=RegisterMod('rplus-class-contract',1)
 CustomHealthAPI={Mod=mod, Helper={},PersistentData={},CallbacksToAdd={},CallbacksToRemove={}}
 assert(type(Entity)=='table' and type(EntityPlayer)=='table', 'PC entity classes unavailable')
 assert(type(getmetatable(Entity).__class.TakeDamage)=='function')
 assert(type(getmetatable(EntityPlayer).__class.AddHearts)=='function')
 local originalEntityIndex=getmetatable(Entity).__class.__index
 local originalPlayerIndex=getmetatable(EntityPlayer).__class.__index
 @CHAPI@
 for key, original in pairs(CustomHealthAPI.PersistentData.OverriddenFunctions) do
   assert(type(original)=='function',key..' missing original')
 end
 assert(CustomHealthAPI.PersistentData.OverriddenFunctions.AddHearts,'AddHearts original missing')
 assert(CustomHealthAPI.PersistentData.OverriddenFunctions.TakeDamagePlayer,'inherited TakeDamage original missing')
 local count=0
 CustomHealthAPI.Helper.HookFunctions.AddHearts=function(self,hp)count=count+hp;return 321 end
 mod:AddCallback(1,function()
  local player=Isaac.GetPlayer()
  assert(getmetatable(player)==getmetatable(EntityPlayer).__class,'class identity mismatch')
  assert(player:GetPlayerType()==0, 'unmodified method lost')
  local ok,data=pcall(function() return player:GetData() end)
  if not ok then print("CHAPI_GETDATA_FAIL "..tostring(data)); error(data) end
  assert(type(data)=='table','CHAPI inherited GetData unavailable')
  data.class_protocol_marker=71
  assert(player:GetData()==data and player:GetData().class_protocol_marker==71,'GetData identity lost')
  assert(player.__missing_class_protocol_key==nil,'unknown player key must return nil')
  assert(originalEntityIndex(player,'GetData')(player)==data,'original base index rejected player')
  for _,spec in ipairs({{5,'ToPickup'},{2,'ToTear'},{3,'ToFamiliar'},{9,'ToProjectile'},{20,'ToNPC'}}) do
   local entity=Isaac.FindByType(spec[1])[1]
   assert(entity,'subclass fixture missing: '..spec[2])
   local child=entity[spec[2]](entity)
   assert(child,'subclass cast missing: '..spec[2])
   assert(type(originalEntityIndex(child,'GetData'))=='function','original base index rejected '..spec[2])
   assert(originalEntityIndex(child,'__missing_class_protocol_key')==nil)
   assert(not pcall(originalPlayerIndex,child,'GetData'),'player index accepted another subclass')
  end
  for _,invalid in ipairs({Vector(1,2),{}}) do
   assert(not pcall(originalEntityIndex,invalid,'GetData'),'base index accepted non-entity')
   assert(not pcall(originalPlayerIndex,invalid,'GetData'),'player index accepted non-entity')
  end
  player:AddHearts(3); assert(count==3,'CHAPI replacement not called')
  local idx=getmetatable(EntityPlayer).__class.__index
  local captured=player.AddHearts
  rawset(getmetatable(EntityPlayer).__class,'__index',function(self,k)if k=='AddHearts' then return function(_,n)count=count+2*n end end return idx(self,k) end)
  player:AddHearts(4);assert(count==11,'shared replacement ignored')
  captured(player,5);assert(count==16,'saved wrapper lost')
  _class_ok=1
 end)
 )lua";
 auto pos=script.find("@CHAPI@");script.replace(pos,7,R"CHAPI(@SOURCE@)CHAPI");
 auto result=LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@rplus-class.lua");
 if(result!=LuaRuntime::LuaInitResult::Success){std::printf("CLASS_INIT_FAIL %d\n",static_cast<int>(result));return 1;}
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::TakeCallbackError()){LuaRuntime::LuaErrorHistoryEntryView errors[8]{}; auto n=LuaRuntime::CopyLuaErrorHistory(errors,8); for(std::size_t i=0;i<n;++i)std::printf("CLASS_CALLBACK_FAIL %s\n",errors[i].text);return 2;}
 return ExpectNumber("_class_ok",1)?0:3;
}'''
class RPlusClassProtocolTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='rplus-class-')
  source=(MOD/'scripts/customhealthapi/reimpl/apioverrides.lua').read_text()
  source=source[:source.index('-- HUD Overrides --')];source=source[:source.rfind('-------------------')]
  expected=sorted(set(re.findall(r'OverriddenFunctions\.(\w+) = META0\.',source)))
  checks='\n'.join("assert(type(CustomHealthAPI.PersistentData.OverriddenFunctions.%s)=='function', '%s original missing')"%(n,n) for n in expected)
  cpp=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN.replace('@SOURCE@',source+'\n'+checks)
  cpp=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '', cpp,count=1)
  cls.bin=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=cpp)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_original_chapi_override_and_shared_class_identity(self):
  r=subprocess.run([str(self.bin)],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
