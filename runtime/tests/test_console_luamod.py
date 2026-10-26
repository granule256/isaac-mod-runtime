"""单模组重载：真实命令→73→仅该目录回调卸载→main和require重新读取。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
from . import test_support
from unittest.mock import patch
MAIN=r'''
#include "console_callback_hook.hpp"
#include "infrastructure/console/console_bridge.hpp"
#include <cassert>
unsigned version=1,readsA{},readsB{};std::string output;
const char* entryA=R"lua(A=RegisterMod('ReloadA',1);Aloads=(Aloads or 0)+1;local n=require('a_module');Avalue=n;if WRAPPED then assert(include('a_include')==77)end;A:AddCallback(1,function()assert(require('a_late')==99);Acalls=(Acalls or 0)+n end);A:AddCallback(73,function(_,m)if m==A then unloadCount=(unloadCount or 0)+1;if FAIL_UNLOAD_ONCE then FAIL_UNLOAD_ONCE=false;error('unload-retry')end;assert(#Isaac.GetCallbacks(1)==2)end end))lua";
const char* entryB=R"lua(B=RegisterMod('ReloadB',1);Bmodule=require('b_module');B:AddCallback(1,function()Bcalls=(Bcalls or 0)+1 end))lua";
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&,const char* path,u8* out,std::size_t capacity,std::size_t* n){
 const char* source=nullptr;
 if(!std::strcmp(path,"rom:/isaac_mods/mods/A/main.lua")){static const std::string bomEntry=std::string("\xef\xbb\xbf")+entryA;source=bomEntry.c_str();++readsA;}
 if(!std::strcmp(path,"rom:/isaac_mods/mods/A/a_module.lua")){source=version==1?"return 1":"return 2";++readsA;}
 if(!std::strcmp(path,"rom:/isaac_mods/mods/B/b_module.lua")){source="return {}";++readsB;}
 if(!std::strcmp(path,"rom:/isaac_mods/mods/A/a_include.lua"))source="return 77";
 if(!std::strcmp(path,"rom:/isaac_mods/mods/A/a_late.lua"))source="return 99";
 if(!source)return TextReadResult::OpenFailed;*n=std::strlen(source);if(*n>=capacity)return TextReadResult::LengthOutOfRange;std::memcpy(out,source,*n);return TextReadResult::Success;
}}
void Print(void*,const void* h,std::uint32_t,std::uint32_t){output.append(isaac::runtime::console::EngineStringData(static_cast<const unsigned char*>(h)),isaac::runtime::console::EngineStringSize(static_cast<const unsigned char*>(h)));}
void Command(std::initializer_list<const char*> words){std::vector<std::array<unsigned char,24>> tokens(words.size());std::size_t i{};for(auto*w:words)assert(isaac::runtime::console::BuildBorrowedCommandString(w,strlen(w),tokens[i++].data()));isaac::runtime::ConsoleCommandView v{tokens.data(),tokens.size(),nullptr,Print};LuaRuntime::DispatchExecuteCommand(v);}
double Number(const char* key){double out{};assert(LuaRuntime::ReadLuaGlobalNumber(key,&out));return out;}
int main(int argc,char**){const bool retry=argc>1;static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);LuaRuntime::ObserveGameThread();
 GameFileReader::Bindings bindings{};
 if(argc>2){const char* wrapper="WRAPPED=true;local original=require;require=function(n) local ok,v=pcall(original,n);if not ok then error(v,2)end;return v end;local oi=include;include=function(n) local ok,v=pcall(oi,n);if not ok then error(v,2)end;return v end";
 assert(LuaRuntime::InitializeManifestMod(wrapper,strlen(wrapper),"@rom:/isaac_mods/mods/Wrapper/adapter.lua","rom:/isaac_mods/mods/Wrapper",bindings)==LuaRuntime::LuaInitResult::Success);}

 assert(LuaRuntime::InitializeManifestMod(entryA,strlen(entryA),"@rom:/isaac_mods/mods/A/main.lua","rom:/isaac_mods/mods/A",bindings)==LuaRuntime::LuaInitResult::Success);
 assert(LuaRuntime::InitializeManifestMod(entryB,strlen(entryB),"@rom:/isaac_mods/mods/B/main.lua","rom:/isaac_mods/mods/B",bindings)==LuaRuntime::LuaInitResult::Success);
 LuaRuntime::DispatchPostUpdate();assert(Number("Acalls")==1&&Number("Bcalls")==1);
 version=2;
 if(retry){const char*fail="FAIL_UNLOAD_ONCE=true";assert(LuaRuntime::InitializeFromBuffer(fail,strlen(fail),"@prepare.lua")==LuaRuntime::LuaInitResult::Success);Command({"luamod","A"});assert(Number("Aloads")==1&&LuaRuntime::TakeCallbackError());}
 Command({"luamod","A"});if(Number("Aloads")!=2){std::printf("Aloads=%g output=%s\n",Number("Aloads"),output.c_str());return 2;}
 assert(Number("Avalue")==2&&Number("unloadCount")==static_cast<double>(retry?2:1)&&readsA==(retry?4U:3U)&&readsB==1);
 LuaRuntime::DispatchPostUpdate();assert(Number("Acalls")==3&&Number("Bcalls")==2);
 const char* check="assert(package.loaded.b_module==Bmodule and #Isaac.GetCallbacks(1)==2)";
 assert(LuaRuntime::InitializeFromBuffer(check,strlen(check),"@reload-check.lua")==LuaRuntime::LuaInitResult::Success);
 assert(!LuaRuntime::TakeCallbackError());
}
'''
class ConsoleLuaModTests(unittest.TestCase):
 def test_single_owner_unload_reload_and_cache(self):
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)+MAIN
  with tempfile.TemporaryDirectory(prefix='console-luamod-')as tmp:
   flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
   with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
    binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(tmp),harness_source=source)
   for mode in ([],['retry'],['retry','wrapped']):
    with self.subTest(mode=mode):
     r=subprocess.run([str(binary),*mode],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
