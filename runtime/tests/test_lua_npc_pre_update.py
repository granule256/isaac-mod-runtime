"""真实Lua验证AI回调的Type过滤、首非nil短路和嵌套派发后的恢复。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_event_callbacks import HARNESS,SOURCE
MAIN=r'''
int main(int argc,char** argv) {
 if(argc!=2)return 99;
 const char* result=argv[1];
 std::string script=R"lua(
local m=RegisterMod('npc',1)
m:AddCallback(1,function() end)
_probe={first=0,last=0}
m:AddCallback(69,function(_,npc) error('wrong Type filter') end,123)
m:AddCallback(69,function(_,npc) assert(type(npc)=='userdata');_probe.first=_probe.first+1;return )lua";
 script+=result;
 script+=R"lua( end,1)
m:AddCallback(69,function(_,npc) _probe.last=_probe.last+1;return true end,1)
)lua";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@npc.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 bool expected=std::strcmp(result,"false")!=0;
 if(LuaRuntime::DispatchPreNpcUpdate(Player(),1)!=expected)return 2;
 double count=0;
 if(!Counter("first",&count)||count!=1)return 3;
 if(!Counter("last",&count)||count!=(std::strcmp(result,"nil")==0?1:0))return 4;
 if(LuaRuntime::DispatchPreNpcUpdate(Player(),2))return 5;
 bool unused=false;static_cast<void>(Flag("unused",&unused));static_cast<void>(Collider());
 return LuaRuntime::TakeCallbackError()?6:0;
}
'''
class NpcPreUpdateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-npc-pre-')
  cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name),harness_source="#include <string>\n"+HARNESS[:HARNESS.index('int main(')]+MAIN)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_true_false_and_nil(self):
  for value in ('true','false','nil'):
   with self.subTest(value=value):
    r=subprocess.run([str(self.binary),value],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
