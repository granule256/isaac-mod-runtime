"""Library calls can require data belonging to the currently loading mod."""
import subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from . import test_support
ROOT=Path(__file__).resolve().parents[2]
HARNESS=r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include <cstring>
#include <cstdio>
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&,const char* path,u8* out,std::size_t cap,std::size_t* length){
 const char* text=nullptr;
 if(!std::strcmp(path,"rom:/isaac_mods/mods/Consumer/resources-dlc3/luarooms/custom.lua"))
  text="ROOM_READS=(ROOM_READS or 0)+1;local child=include('room_child');return {marker=child}";
 if(!std::strcmp(path,"rom:/isaac_mods/mods/Consumer/room_child.lua"))text="return 73";
 if(!std::strcmp(path,"rom:/isaac_mods/mods/Library/room_child.lua"))text="return 12";
 if(!std::strcmp(path,"rom:/isaac_mods/mods/Library/broken.lua"))text="local invalid = )";
 if(!std::strcmp(path,"rom:/isaac_mods/mods/Consumer/broken.lua"))text="return 999";
 if(!text)return TextReadResult::OpenFailed;
 *length=std::strlen(text);if(*length>cap)return TextReadResult::LengthOutOfRange;
 std::memcpy(out,text,*length);return TextReadResult::Success;
}
}
int main(){
 const char* lib=R"lua(
  Lib={Read=function(name)local value=require(name);return value end}
  local m=RegisterMod('Library',1);m:AddCallback(1,function()end)
 )lua";
 auto result=LuaRuntime::InitializeManifestMod(lib,std::strlen(lib),
  "@rom:/isaac_mods/mods/Library/main.lua","rom:/isaac_mods/mods/Library",{});
 if(result!=LuaRuntime::LuaInitResult::Success)return 1;
 const char* script=R"lua(
  local a=Lib.Read('resources-dlc3/luarooms/custom')
  assert(a.marker==73)
  assert(Lib.Read('resources-dlc3/luarooms/custom')==a and ROOM_READS==1)
  local ok,e=pcall(Lib.Read,'broken')
  assert(not ok and e:find('Library/broken.lua:1:',1,true),'must preserve syntax errors in found modules')
  assert(not pcall(Lib.Read,'missing'))
  assert(Lib.Read('resources-dlc3/luarooms/custom')==a)
  local m=RegisterMod('Consumer',1);m:AddCallback(1,function()end)
 )lua";
 result=LuaRuntime::InitializeManifestMod(script,std::strlen(script),
  "@rom:/isaac_mods/mods/Consumer/main.lua","rom:/isaac_mods/mods/Consumer",{});
 char e[1024]{};(void)LuaRuntime::CopyLastLuaErrorText(e,sizeof(e));
 if(result!=LuaRuntime::LuaInitResult::Success)std::fprintf(stderr,"%s\n",e);
 return result==LuaRuntime::LuaInitResult::Success?0:2;
}
'''
class RequireActiveContextTests(unittest.TestCase):
 def test_library_requires_current_mod_room_data_and_preserves_found_module_errors(self):
  with tempfile.TemporaryDirectory(prefix='isaac-require-context-')as temp:
   flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
   with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
    binary=test_support.build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(temp),harness_source=HARNESS)
   r=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
