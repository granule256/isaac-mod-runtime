"""生产require与公开package.loaded共用真实缓存，保留Lua标准的自登记及重载语义。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import test_support

ROOT = Path(__file__).resolve().parents[2]
HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_file_reader.hpp"
#include <cstring>
#include <cstdio>
namespace GameFileReader {
TextReadResult ReadTextFile(const Bindings&,const char* path,u8* buffer,std::size_t capacity,std::size_t* length) {
 const char* text="return true";
 if(std::strstr(path,"/state.lua"))text="STATE_READS=(STATE_READS or 0)+1; return {generation=STATE_READS}";
 if(std::strstr(path,"/self.lua"))text="package.loaded.self={registered=true}";
 if(std::strstr(path,"/self_false.lua"))text="SELF_FALSE_READS=(SELF_FALSE_READS or 0)+1; package.loaded.self_false=false";
 if(std::strstr(path,"/none.lua"))text="NONE_READS=(NONE_READS or 0)+1";
 *length=std::strlen(text);if(*length>capacity)return TextReadResult::LengthOutOfRange;
 std::memcpy(buffer,text,*length);return TextReadResult::Success;
}
}
int main(int argc,char**argv){
 if(argc!=2)return 90;
 const char* script=nullptr;
 if(!std::strcmp(argv[1],"identity"))script=R"lua(
assert(type(package)=='table','package missing')
assert(type(package.loaded)=='table','package.loaded missing')
assert(package.loaded.string==string and package.loaded.table==table and package.loaded._G==_G)
assert(require('string')==string)
local j=require('json'); assert(package.loaded.json==j and require('json')==j)
local a=require('state'); assert(package.loaded.state==a and require('state')==a and STATE_READS==1)
local replacement={manual=true};package.loaded.state=replacement;assert(require('state')==replacement)
package.loaded.state=false;local b=require('state');assert(b.generation==2 and package.loaded.state==b)
package.loaded.state=nil;local c=require('state');assert(c.generation==3 and package.loaded.state==c)
local real=package.loaded;package.loaded={state={wrong=true}};assert(require('state')==real.state)
package.loaded=real
)lua";
 if(!std::strcmp(argv[1],"nil_result"))script=R"lua(
assert(type(package)=='table','package missing')
local s=require('self');assert(type(s)=='table' and s.registered and package.loaded.self==s)
assert(require('self_false')==false and package.loaded.self_false==false)
assert(require('self_false')==false and SELF_FALSE_READS==2)
assert(require('none')==true and package.loaded.none==true)
assert(require('none')==true and NONE_READS==1)
)lua";
 if(!std::strcmp(argv[1],"shared"))script="assert(type(package)=='table','package missing'); SHARED_MODULE={value=123};package.loaded.shared=SHARED_MODULE";
 if(!script)return 91;
 char entry[4096];std::snprintf(entry,sizeof(entry),"%s local m=RegisterMod('Package test',1);m:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)",script);
 GameFileReader::Bindings bindings{};
 auto result=LuaRuntime::InitializeManifestMod(entry,std::strlen(entry),"@package-test.lua","rom:/isaac_mods/mods/PackageA",bindings);
 char error[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
 std::printf("FIRST=%u ERROR=%s\n",unsigned(result),error);
 if(result!=LuaRuntime::LuaInitResult::Success)return 1;
 if(!std::strcmp(argv[1],"shared")){
  const char* second="assert(require('shared')==SHARED_MODULE);package.loaded.shared=false;assert(require('shared')==true);local m=RegisterMod('Package second',1)";
  result=LuaRuntime::InitializeManifestMod(second,std::strlen(second),"@package-second.lua","rom:/isaac_mods/mods/PackageB",bindings);
  static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::printf("SECOND=%u ERROR=%s\n",unsigned(result),error);
 }
 return result==LuaRuntime::LuaInitResult::Success?0:2;
}
'''

class PackageLoadedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='isaac-package-loaded-')
        flags = tuple(flag for flag in test_support.HARNESS_COMPILE_FLAGS if not flag.startswith('-DEXL_DIAGNOSTIC_STAGE='))
        with patch.object(test_support, 'HARNESS_COMPILE_FLAGS', flags):
            cls.binary = test_support.build_lua_harness(source_root=ROOT/'runtime/source', workdir=Path(cls.temp.name), harness_source=HARNESS)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self, scenario):
        result = subprocess.run([str(self.binary), scenario], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_registry_identity_and_explicit_cache_mutations(self):
        self.check('identity')

    def test_nil_return_preserves_module_self_registration(self):
        self.check('nil_result')

    def test_loaded_modules_are_shared_between_mod_entries(self):
        self.check('shared')
