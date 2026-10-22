"""真实生产 require：编译诊断、false缓存与加载器模块名参数。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness
from . import test_support
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
HARNESS=r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include <cstring>
#include <cstdio>
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&,const char* path,u8* buffer,std::size_t capacity,std::size_t* length) {
 const char* text="local moduleName = ...; return moduleName";
 if(std::strstr(path,"bad.lua"))text="local broken = )";
 if(std::strstr(path,"false.lua"))text="FALSE_READS=(FALSE_READS or 0)+1; return false";
 *length=std::strlen(text);if(*length>capacity)return TextReadResult::LengthOutOfRange;
 std::memcpy(buffer,text,*length);return TextReadResult::Success;
}
}
int main(int argc,char** argv) {
 if(argc!=2)return 90;
 const char* script=nullptr;
 if(!std::strcmp(argv[1],"compile"))script="local ok,err=pcall(require,'bad'); assert(not ok); print('COMPILE='..err); assert(err:find('bad.lua:1:',1,true))";
 if(!std::strcmp(argv[1],"false"))script="assert(require('false')==false); assert(require('false')==false); assert(FALSE_READS==2)";
 if(!std::strcmp(argv[1],"name"))script="assert(require('name')=='name')";
 if(!script)return 91;
 char entry[2048];std::snprintf(entry,sizeof(entry),"%s local m=RegisterMod('Require',1); m:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)",script);
 GameFileReader::Bindings bindings{};
 return LuaRuntime::InitializeManifestMod(entry,std::strlen(entry),"@probe.lua","rom:/isaac_mods/mods/Probe",bindings)==LuaRuntime::LuaInitResult::Success ? 0:1;
}
'''
class RequireResultsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory(prefix='isaac-require-results-')
  flags=tuple(flag for flag in test_support.HARNESS_COMPILE_FLAGS if not flag.startswith('-DEXL_DIAGNOSTIC_STAGE='))
  with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
   cls.binary=build_lua_harness(source_root=ROOT/'runtime/source',workdir=Path(cls.temp.name),harness_source=HARNESS)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_compile_error_keeps_module_path_and_line(self):self.check('compile')
 def test_false_result_is_reloaded(self):self.check('false')
 def test_loader_receives_module_name(self):self.check('name')
 def check(self,name):
  result=subprocess.run([str(self.binary),name],text=True,capture_output=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
if __name__=='__main__':unittest.main()
