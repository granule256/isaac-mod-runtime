"""药丸回调保留原实参且首个非nil整数短路，退化回调真实实体实参与取消结果。"""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_event_callbacks import HARNESS,SOURCE
MAIN=r'''
int main(int argc,char** argv) {
 const bool nilPrefix=argc==2 && std::strcmp(argv[1],"nil_prefix")==0;
 std::string script=R"lua(
local m=RegisterMod('pool',1)
m:AddCallback(1,function() end)
_probe={pill=0,effect=0,devolve=0}
m:AddCallback(64,function(_,seed) assert(seed==123);_probe.pill=_probe.pill+1;return 4 end)
m:AddCallback(64,function(_,seed) assert(seed==123);_probe.pill=_probe.pill+1;return nil end)
m:AddCallback(64,function(_,seed) assert(seed==123);_probe.pill=_probe.pill+1;return 8 end)
m:AddCallback(65,function(_,effect,color) assert(effect==10 and color==6);_probe.effect=_probe.effect+1;return 3 end)
m:AddCallback(65,function(_,effect,color) assert(effect==10 and color==6);_probe.effect=_probe.effect+1;return 20 end)
m:AddCallback(72,function(_,e) assert(type(e)=='userdata');_probe.devolve=_probe.devolve+1;return true end)
)lua";
 if(nilPrefix) {
  auto at=script.find("return 4 end");script.replace(at,std::strlen("return 4 end"),"return nil end");
  at=script.find("return 3 end");script.replace(at,std::strlen("return 3 end"),"return nil end");
 }
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@pills.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(LuaRuntime::DispatchGetPillColor(123,6)!=(nilPrefix?8:4))return 2;
 if(LuaRuntime::DispatchGetPillEffect(6,10)!=(nilPrefix?20:3))return 3;
 if(!LuaRuntime::DispatchPreEntityDevolve(Player()))return 4;
 double count=0;
 if(!Counter("pill",&count)||count!=(nilPrefix?3:1))return 5;
 if(!Counter("effect",&count)||count!=(nilPrefix?2:1))return 6;
 if(!Counter("devolve",&count)||count!=1)return 7;
 bool unused=false;static_cast<void>(Flag("unused",&unused));static_cast<void>(Collider());
 return LuaRuntime::TakeCallbackError()?8:0;
}
'''
class PillDevolveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-pill-devolve-')
  cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name),harness_source='#include <string>\n'+HARNESS[:HARNESS.index('int main(')]+MAIN)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_arguments_and_native_override(self):
  for scenario in ('first_non_nil','nil_prefix'):
   with self.subTest(scenario=scenario):
    r=subprocess.run([str(self.binary),scenario],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
