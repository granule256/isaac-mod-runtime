"""REPENTOGON vector division preserves the vanilla scalar-only surface when off."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support
from .test_repentogon_in_game import PREFIX
SOURCE=Path(__file__).resolve().parents[1]/'source'
DRIVER=PREFIX+r'''
int main(int argc,char**){
 const bool enabled=argc>1;
 Files files(enabled);SetSessionSaveFilePort(&files);LuaRuntime::ObserveGameThread();
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 const char* script=enabled?R"lua(
local v=Vector(1280,720)/Vector(480,270)
assert(math.abs(v.X-8/3)<1e-6 and math.abs(v.Y-8/3)<1e-6)
local p=Vector(9,-8)/Vector(3,-2);assert(p.X==3 and p.Y==4)
local s=Vector(6,4)/2;assert(s.X==3 and s.Y==2)
for _,x in ipairs({0, Vector(0,1), Vector(1,0), '2', {}}) do
 assert(not pcall(function()return Vector(1,2)/x end))
end
assert(not pcall(function()return 2/Vector(1,2)end))
)lua":R"lua(
local s=Vector(6,4)/2;assert(s.X==3 and s.Y==2)
assert(not pcall(function()return Vector(6,4)/Vector(2,2)end))
)lua";
 const auto r=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@vector-division.lua");
 if(r!=LuaRuntime::LuaInitResult::Success){char e[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(e,sizeof(e)));std::fprintf(stderr,"%s\n",e);return 1;}
 assert(LuaRuntime::ShutdownForModReload());repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
}
'''
class RepentogonVectorDivisionTests(unittest.TestCase):
 def test_component_division_is_extension_scoped(self):
  with tempfile.TemporaryDirectory(prefix='rgon-vector-div-')as d:
   b=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(d),harness_source=DRIVER)
   for mode in ([],['enabled']):
    with self.subTest(mode=mode):
     p=subprocess.run([str(b),*mode],capture_output=True,text=True)
     self.assertEqual(p.returncode,0,p.stdout+p.stderr)
