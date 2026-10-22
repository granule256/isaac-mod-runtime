"""73加载表与原生卸载：通知时登记存活，之后只清当前Mod，新登记不误清。"""
import subprocess,tempfile,unittest,re
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
int main(int argc,char**argv){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 if(argc!=2)return 99;const bool errorScene=std::strcmp(argv[1],"error")==0;CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 std::string script=R"lua(
 _unload={calls=0,old=0,new=0};
 first=RegisterMod('first',1);second=RegisterMod('second',1);
 first:AddCallback(1,function() _unload.old=_unload.old+1 end);
 second:AddCallback(1,function() _unload.old=_unload.old+10 end);
 second:AddCallback(73,function(_,mod)
  assert(mod==first or mod==second); assert(#Isaac.GetCallbacks(1)==2 or #Isaac.GetCallbacks(1)==1 or #Isaac.GetCallbacks(1)==3)
  _unload.calls=_unload.calls+1
  if mod==first then new=RegisterMod('replacement',1);new:AddCallback(1,function() _unload.new=_unload.new+1 end);if FAIL_ON_FIRST then error('unload-first') end end
 end)
 )lua";
 if(errorScene)script+=";FAIL_ON_FIRST=true";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@unload.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 LuaRuntime::ObserveGameThread();
 if(LuaRuntime::UnloadManifestMods()==errorScene)return 2;
 if(LuaRuntime::TakeCallbackError()!=errorScene)return 8;
 double calls{};if(LuaRuntime::ReadLuaTableNumber("_unload","calls",&calls)||calls!=2)return 3;
 LuaRuntime::DispatchPostUpdate();double old{},fresh{};
 if(LuaRuntime::ReadLuaTableNumber("_unload","old",&old)||old!=(errorScene?1:0))return 4;
 if(LuaRuntime::ReadLuaTableNumber("_unload","new",&fresh)||fresh!=1)return 5;
 if(!LuaRuntime::UnloadManifestMods())return 6;
 LuaRuntime::DispatchPostUpdate();if(LuaRuntime::ReadLuaTableNumber("_unload","new",&fresh)||fresh!=1)return 7;
 return 0;
}
'''
class ModUnloadTests(unittest.TestCase):
 def test_real_unload_entry_exists(self):
  self.assertIn('UnloadManifestMods', (ROOT/'runtime/source/lua_runtime.hpp').read_text())
 def test_registered_mods_use_pc_unload_and_new_generation_survives(self):
  if 'UnloadManifestMods' not in (ROOT/'runtime/source/lua_runtime.hpp').read_text():self.fail('实际卸载桥尚未实现')
  with tempfile.TemporaryDirectory(prefix='isaac-unload-') as tmp:
   source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+MAIN
   source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(tmp),harness_source=source)
   r=subprocess.run([str(binary),'normal'],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(binary),'error'],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
