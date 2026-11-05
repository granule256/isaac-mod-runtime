"""The composition root installs optional extensions before user scripts; PC core is independent."""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
MAIN=r'''
namespace LuaRuntime {template<class F>void SetRuntimeExtensionInstaller(F)noexcept{}}
static unsigned installs{};
static void BrokenExtension(lua_State*L)noexcept{luaL_error(L,"bad optional extension");}
static void Extension(lua_State*L)noexcept{++installs;lua_pushboolean(L,1);lua_setglobal(L,"extensionPrepared");}
int main(){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::ObserveGameThread();
 using Installer=void(*)(lua_State*)noexcept;
 const char*pure=R"lua(assert(extensionPrepared==nil);local m=RegisterMod('pure core',1);m:AddCallback(1,function()end))lua";
 LuaRuntime::SetRuntimeExtensionInstaller(static_cast<Installer>(nullptr));
 if(LuaRuntime::InitializeFromBuffer(pure,std::strlen(pure),"@pure.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(!LuaRuntime::ShutdownForModReload())return 2;
 LuaRuntime::SetRuntimeExtensionInstaller(static_cast<Installer>(&Extension));
 const char*script=R"lua(assert(extensionPrepared==true,'extension ran after user script');local m=RegisterMod('extension test',1);m:AddCallback(1,function()end))lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@extension.lua")!=LuaRuntime::LuaInitResult::Success)return 3;
 if(installs!=1||!LuaRuntime::ShutdownForModReload())return 4;
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@extension2.lua")!=LuaRuntime::LuaInitResult::Success)return 5;
 if(installs!=2||!LuaRuntime::ShutdownForModReload())return 6;
 LuaRuntime::SetRuntimeExtensionInstaller(static_cast<Installer>(nullptr));
 if(LuaRuntime::InitializeFromBuffer(pure,std::strlen(pure),"@pure2.lua")!=LuaRuntime::LuaInitResult::Success)return 7;
 if(installs!=2||!LuaRuntime::ShutdownForModReload())return 8;
 LuaRuntime::SetRuntimeExtensionInstaller(static_cast<Installer>(&BrokenExtension));
 if(LuaRuntime::InitializeFromBuffer(pure,std::strlen(pure),"@isolated.lua")!=LuaRuntime::LuaInitResult::Success)return 9;
 const auto d=LuaRuntime::GetRuntimeExtensionDiagnostics();
 return d.failures==1&&d.lastStatus!=LUA_OK&&d.error[0]?0:10;
}
'''
class RuntimeExtensionTests(unittest.TestCase):
 def test_composition_installs_once_per_vm_before_user_script_and_can_be_absent(self):
  with tempfile.TemporaryDirectory(prefix='runtime-extension-')as d:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=fixture.HARNESS.split('int main(',1)[0]+MAIN)
   result=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
