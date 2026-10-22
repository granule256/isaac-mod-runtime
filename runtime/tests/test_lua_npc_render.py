"""NPC渲染传递原生偏移并按实体Type过滤，不能伪造零坐标。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_event_callbacks import HARNESS, SOURCE

MAIN = r''' 
int main() {
    static_cast<void>(Collider());
    const char* script = R"lua(
local m=RegisterMod('render',1)
m:AddCallback(1,function() end)
_probe={hit=0,miss=0,all=0}
m:AddCallback(28,function(self,npc,offset)
 assert(self==m and type(npc)=="userdata")
 assert(offset.X==12.5 and offset.Y==-7.25)
 _probe.hit=_probe.hit+1
end,10)
m:AddCallback(28,function() _probe.miss=_probe.miss+1 end,20)
m:AddCallback(28,function() _probe.all=_probe.all+1 end)
)lua";
    std::uint32_t type=10,variant=20;
    std::memcpy(g_FakePlayer+kEntityTypeOffset,&type,4);
    std::memcpy(g_FakePlayer+kEntityVariantOffset,&variant,4);
    if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@render.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
    float offset[2]={12.5f,-7.25f};
    LuaRuntime::DispatchPostNpcRender(Player(),offset);
    double count=0;
    if(!Counter("hit",&count)||count!=1)return 2;
    if(!Counter("miss",&count)||count!=0)return 3;
    if(!Counter("all",&count)||count!=1)return 4;
    LuaRuntime::DispatchPostNpcRender(Player(),nullptr);
    if(!Counter("all",&count)||count!=1)return 5;
    bool unused=false;static_cast<void>(Flag("unused",&unused));
    return LuaRuntime::TakeCallbackError()?6:0;
}
'''
class NpcRenderTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='isaac-npc-render-')
  text=HARNESS[:HARNESS.index('int main(')].replace('#include <cstdint>', '#include <cstdint>\n#include \"runtime_constants.hpp\"')+MAIN
  cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.tmp.name),harness_source=text)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_native_render_offset_and_type_filter(self):
  r=subprocess.run([str(self.binary)],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
