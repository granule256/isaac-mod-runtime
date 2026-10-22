"""固定PC的PRE零哨兵与62/63低32位返回，不把文档口径当机器规则。"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_event_callbacks as f
from .test_support import build_lua_harness
MAIN=r'''
int main(int argc,char**argv){(void)&Player;(void)&Collider;(void)&Counter;(void)&Flag;if(argc!=2)return 90;std::string value=argv[1];
 std::string script="local m=RegisterMod('values',1);m:AddCallback(1,function() end);m:AddCallback(62,function() return "+value+" end);m:AddCallback(63,function() return "+value+" end)";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@values.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 const auto before=LuaRuntime::DispatchPreGetCollectible(nullptr,1,2,1,0);bool preError=LuaRuntime::TakeCallbackError();
 const auto after=LuaRuntime::DispatchPostGetCollectible(nullptr,777,1,1,2);bool postError=LuaRuntime::TakeCallbackError();
 std::printf("%llu %u %llu %u\n",static_cast<unsigned long long>(before),preError,static_cast<unsigned long long>(after),postError);return 0;}
'''
class CollectibleBootstrapValueTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-collectible-bootstrap-')
  cls.binary=build_lua_harness(source_root=f.SOURCE,workdir=Path(cls.tmp.name),harness_source='#include <string>\n'+f.HARNESS[:f.HARNESS.index('int main(')]+MAIN)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_pre_zero_sentinel_and_low_word_post_override(self):
  for value,low,error in [('0',0,0),('4294967296',0,0),('-1',0xffffffff,0),('4294967297',1,0),("'42'",42,0),('false',0,1),('1.5',0,1)]:
   with self.subTest(value=value):
    r=subprocess.run([str(self.binary),value],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    before=(0x300000000|low) if low and not error else 0
    after=(0x100000000|low) if not error else 0
    self.assertEqual(r.stdout.strip(),f'{before} {error} {after} {error}')
if __name__=='__main__':unittest.main()
