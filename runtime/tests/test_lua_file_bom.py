"""文件入口接受 UTF-8 BOM，字符串编译保持原语义。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from .test_support import build_lua_harness
from . import test_support
ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include <cstring>
#include <cstdio>
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&,const char* path,u8* buffer,std::size_t capacity,std::size_t* length) {
 const char* text="\xef\xbb\xbfreturn 37";
 if(std::strstr(path,"line.lua"))text="\xef\xbb\xbf\nlocal broken = )";
 if(std::strstr(path,"short1.lua"))text="\xef";
 if(std::strstr(path,"short2.lua"))text="\xef\xbb";
 if(std::strstr(path,"middle.lua"))text="local x=1;\xef\xbb\xbfreturn x";
 *length=std::strlen(text);if(*length>capacity)return TextReadResult::LengthOutOfRange;
 std::memcpy(buffer,text,*length);return TextReadResult::Success;
}
}
int main(int argc,char**argv) {
 if(argc!=2)return 90;
 GameFileReader::Bindings bindings{};
 const char* plain="local m=RegisterMod('BOM',1); m:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)";
 char entry[4096]; std::snprintf(entry,sizeof(entry),"%s",plain);
 const char* name=argv[1];
 if(!std::strcmp(name,"first"))std::snprintf(entry,sizeof(entry),"\xef\xbb\xbf%s",plain);
 if(!std::strcmp(name,"string"))return LuaRuntime::InitializeFromBuffer("\xef\xbb\xbfreturn 1",11,"@string.lua")==LuaRuntime::LuaInitResult::ScriptLoadFailed?0:1;
 auto result=LuaRuntime::InitializeManifestMod(entry,std::strlen(entry),"@main.lua","rom:/isaac_mods/mods/BOM",bindings);
 if(result!=LuaRuntime::LuaInitResult::Success)return 2;
 const char* script=nullptr;
 if(!std::strcmp(name,"first"))return 0;
 if(!std::strcmp(name,"empty"))script="\xef\xbb\xbf";
 if(!std::strcmp(name,"append"))script="\xef\xbb\xbf" "assert(true)";
 if(!std::strcmp(name,"require"))script="assert(require('bom')==37)";
 if(!std::strcmp(name,"include"))script="assert(include('bom')==37)";
 if(!std::strcmp(name,"lines"))script="for _,f in ipairs({require,include}) do local ok,e=pcall(f,'line'); assert(not ok); assert(e:find('line.lua:2:',1,true),e) end";
 if(!std::strcmp(name,"boundaries"))script="for _,f in ipairs({require,include}) do for _,n in ipairs({'short1','short2','middle'}) do assert(not pcall(f,n)) end end local b=string.char(239,187,191)..'return 1'; assert(load(b)==nil); assert(loadstring(b)==nil)";
 if(!script)return 91;
 return LuaRuntime::InitializeManifestMod(script,std::strlen(script),"@append.lua","rom:/isaac_mods/mods/BOM",bindings)==LuaRuntime::LuaInitResult::Success?0:3;
}
'''
class LuaFileBomTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='isaac-file-bom-')
  flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
  with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
   cls.binary=build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(cls.temp.name),harness_source=HARNESS)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_file_entries(self):
  for name in ('first','append','empty','require','include','lines','boundaries','string'):
   with self.subTest(name=name):
    result=subprocess.run([str(self.binary),name],text=True,capture_output=True)
    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
if __name__=='__main__':unittest.main()
