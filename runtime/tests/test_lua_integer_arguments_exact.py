"""真实Lua数值转换：保持64位整数精度并兼容整值浮点和字符串。"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from .test_support import lua_harness_objects

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'
HARNESS=r'''
#include "interfaces/lua/lua_integer_argument.hpp"
extern "C" {
#include "lauxlib.h"
}
#include <cstdio>
#include <cstring>
#include <limits>
bool check(lua_State* L,lua_Integer expected){
 lua_Integer actual{};
 if(!isaac::runtime::IsIntegerArgument(L,-1)||!isaac::runtime::IntegerArgumentAt(L,-1,&actual)||actual!=expected){
  std::fprintf(stderr,"integer value changed: expected %lld got %lld\n",static_cast<long long>(expected),static_cast<long long>(actual));return false;
 }
 return true;
}
int main(int argc,char** argv){
 if(argc!=2)return 99;
 auto*L=luaL_newstate();bool ok=true;
 if(!std::strcmp(argv[1],"wide")){
  const lua_Integer values[]={9007199254740993LL,-9007199254740993LL,std::numeric_limits<lua_Integer>::max(),std::numeric_limits<lua_Integer>::min()};
  for(auto value:values){lua_settop(L,0);lua_pushinteger(L,value);if(!check(L,value)){ok=false;break;}}
 }else if(!std::strcmp(argv[1],"coercion")){
  const char*expressions[]={"return 0","return -42","return 42.0","return '42'","return '42.0'","return ' 42 '","return '0x2a'","return '4.2e1'","return '9007199254740993'","return '9223372036854775807'"};
  const lua_Integer expected[]={0,-42,42,42,42,42,42,42,9007199254740993LL,std::numeric_limits<lua_Integer>::max()};
  for(unsigned i=0;i<sizeof(expected)/sizeof(expected[0]);++i){lua_settop(L,0);if(luaL_loadstring(L,expressions[i])||lua_pcall(L,0,1,0)||!check(L,expected[i])){ok=false;break;}}
 }else if(!std::strcmp(argv[1],"reject")){
  const char*expressions[]={"return 1.5","return '1.5'","return true","return nil","return {}","return 'x'","return 1/0","return 0/0","return 18446744073709551616.0"};
  for(auto expression:expressions){lua_settop(L,0);if(luaL_loadstring(L,expression)||lua_pcall(L,0,1,0)){ok=false;break;}lua_Integer actual=123;
   if(isaac::runtime::IsIntegerArgument(L,-1)||isaac::runtime::IntegerArgumentAt(L,-1,&actual)||actual!=123){ok=false;break;}}
  lua_pushinteger(L,42);if(isaac::runtime::IntegerArgumentAt(L,-1,nullptr)||isaac::runtime::IsIntegerArgument(nullptr,1)||isaac::runtime::IntegerArgumentAt(nullptr,1,nullptr))ok=false;
 }else ok=false;
 lua_close(L);return ok?0:1;
}
'''

class ExactIntegerArgumentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='exact-integer-');work=Path(cls.tmp.name)
  objects=lua_harness_objects(SOURCE,work);(work/'host.cpp').write_text(HARNESS)
  cls.host=work/'host'
  r=subprocess.run(['c++','-std=c++17','-I'+str(ROOT/'runtime/src'),'-I'+str(SOURCE/'third_party/lua-5.3.3/src'),str(work/'host.cpp'),*[str(p)for p in objects],'-o',str(cls.host)],capture_output=True,text=True)
  if r.returncode:raise AssertionError(r.stdout+r.stderr)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_case(self,name):
  r=subprocess.run([str(self.host),name],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_integer_subtype_keeps_all_64_bits(self):self.run_case('wide')
 def test_integral_float_and_numeric_strings_keep_pc_conversion(self):self.run_case('coercion')
 def test_fractional_invalid_and_out_of_range_values_are_rejected(self):self.run_case('reject')
