"""PC require accepts relative slash paths and caches by the original module name."""
import subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from .test_support import build_lua_harness
from . import test_support
SOURCE=Path(__file__).resolve().parents[1]/"source"
HARNESS=r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include <cstdio>
#include <cstring>
static unsigned reads=0;
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&,const char* path,u8* out,std::size_t capacity,std::size_t* length){
 ++reads;
 if(std::strcmp(path,"rom:/isaac_mods/mods/Paths/compat/a.lua"))return TextReadResult::OpenFailed;
 const char* text="loads=(loads or 0)+1;return {number=loads}";*length=std::strlen(text);
 if(*length>capacity)return TextReadResult::LengthOutOfRange;
 std::memcpy(out,text,*length);return TextReadResult::Success;
}
}
int main(){const char* script=R"lua(
 local a=require('compat/a');assert(a.number==1 and require('compat/a')==a)
 local b=require('compat.a');assert(b.number==2 and b~=a)
 local c=require('compat\\a');assert(c.number==3 and require('compat\\a')==c)
 for _,name in ipairs({'../escape','/absolute','\\absolute','compat/','compat\\','compat/../escape','compat..a'})do
  assert(not pcall(require,name),name)
 end
 local m=RegisterMod('Paths',1);m:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)
 )lua";
 const auto status=LuaRuntime::InitializeManifestMod(script,std::strlen(script),"@rom:/isaac_mods/mods/Paths/main.lua","rom:/isaac_mods/mods/Paths",{});
 char error[1024]{};(void)LuaRuntime::CopyLastLuaErrorText(error,sizeof(error));
 std::printf("status=%u reads=%u error=%s\n",unsigned(status),reads,error);
 return status==LuaRuntime::LuaInitResult::Success&&reads==3?0:1;
}
'''
class RequirePathTests(unittest.TestCase):
 def test_relative_paths_cache_and_reject_traversal_before_file_access(self):
  with tempfile.TemporaryDirectory(prefix='isaac-require-paths-')as d:
   flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
   with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
    binary=build_lua_harness(source_root=SOURCE,workdir=Path(d),harness_source=HARNESS)
   r=subprocess.run([str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
