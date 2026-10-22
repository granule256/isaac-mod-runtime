"""真实Lua碰撞回调保留nil/false/true并按过滤器与首个非nil短路。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_event_callbacks import HARNESS, SOURCE

MAIN = r'''
int main(int argc, char** argv) {
    if(argc != 3)return 90;
    unsigned id = static_cast<unsigned>(std::strtoul(argv[1],nullptr,10));
    const char* value=argv[2];
        char script[1800];
        std::snprintf(script,sizeof(script),R"lua(
local m=RegisterMod('collision',1)
m:AddCallback(1,function() end)
_probe={hit=0,later=0,miss=0}
m:AddCallback(%u,function(self,e,other,low)
 assert(self==m and type(e)=='userdata' and type(other)=='userdata' and low==false)
 _probe.hit=_probe.hit+1
 return %s
end,100)
m:AddCallback(%u,function() _probe.later=_probe.later+1 end)
m:AddCallback(%u,function() _probe.miss=_probe.miss+1 end,200)
)lua",id,value,id,id);
        if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@collision.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
        auto outcome=LuaRuntime::DispatchPreEntityCollision(id,Player(),Collider(),false,100);
        auto expected=std::strcmp(value,"nil")==0?LuaRuntime::CollisionOverride::Continue:
                     std::strcmp(value,"true")==0?LuaRuntime::CollisionOverride::Ignore:LuaRuntime::CollisionOverride::Collide;
        if(outcome!=expected)return 2;
        bool unusedFlag = false; static_cast<void>(Flag("unused", &unusedFlag));
        double count=0;
        if(!Counter("hit",&count)||count!=1){
          std::printf("id=%u value=%s hit=%f error=%d\n",id,value,count,LuaRuntime::TakeCallbackError());
          LuaRuntime::LuaErrorHistoryEntryView errors[8];
          auto n=LuaRuntime::CopyLuaErrorHistory(errors,8);
          for(std::size_t i=0;i<n;++i)std::printf("%s\n",errors[i].text);
          return 3;
        }
        if(!Counter("later",&count)||count!=(expected==LuaRuntime::CollisionOverride::Continue?1:0))return 4;
        if(!Counter("miss",&count)||count!=0)return 5;
        if(LuaRuntime::TakeCallbackError())return 6;
    return 0;
}
'''
class LuaCollisionTristateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-collision-')
  text=HARNESS[:HARNESS.index('int main(')].replace('#include <cstring>','#include <cstring>\n#include <cstdio>\n#include <cstdlib>')+MAIN
  cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name),harness_source=text)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_eight_families_and_all_return_values(self):
  for id in (26,30,33,38,42,46,53,60):
   for value in ('nil','false','true'):
    with self.subTest(id=id,value=value):
     r=subprocess.run([str(self.binary),str(id),value],capture_output=True,text=True)
     self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
