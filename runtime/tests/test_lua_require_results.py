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
 char nested[128];int depth=0;
 if(const auto* chain=std::strstr(path,"chain")) {
  if(std::sscanf(chain,"chain%d.lua",&depth)!=1)return TextReadResult::OpenFailed;
  std::snprintf(nested,sizeof(nested),depth==15?"return 42":"local value=require('chain%d'); return value",depth+1);
  text=nested;
 }
 if(std::strstr(path,"cycle.lua"))text="return require('cycle')";
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
 if(!std::strcmp(argv[1],"deep"))script="assert(require('chain0')==42); assert(require('chain0')==42)";
 if(!std::strcmp(argv[1],"cycle"))script="local ok,e=pcall(require,'cycle'); assert(not ok and e:find('nesting exceeds maximum depth',1,true)); assert(require('chain0')==42)";
 if(!script)return 91;
 char entry[2048];std::snprintf(entry,sizeof(entry),"%s local m=RegisterMod('Require',1); m:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)",script);
 GameFileReader::Bindings bindings{};
 const auto result=LuaRuntime::InitializeManifestMod(entry,std::strlen(entry),"@probe.lua","rom:/isaac_mods/mods/Probe",bindings);
 char error[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
 if(result!=LuaRuntime::LuaInitResult::Success)std::fprintf(stderr,"%s\n",error);
 return result==LuaRuntime::LuaInitResult::Success ? 0:1;
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
 def test_sixteen_module_dependency_chain_loads(self):self.check('deep')
 def test_recursive_load_is_bounded_and_depth_recovers(self):self.check('cycle')
 def check(self,name):
  result=subprocess.run([str(self.binary),name],text=True,capture_output=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
if __name__=='__main__':unittest.main()
