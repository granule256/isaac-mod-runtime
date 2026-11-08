"""PC bootstrap defaults and native boolean coercion used by original Mods."""
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from . import test_lua_sprite as fixture
from .test_support import build_lua_harness
from . import test_support

MAIN = r'''
#include <cassert>
#include <vector>
std::vector<bool> loaded, played, overlays;
void LoadProbe(void* self,const void* path,bool flag) {FakeLoad(self,path,flag);loaded.push_back(flag);}
void PlayProbe(void* self,const char* name,bool flag) {FakePlay(self,name,flag);played.push_back(flag);}
void OverlayProbe(void* self,const char* name,bool flag) {FakePlayOverlay(self,name,flag);overlays.push_back(flag);}
int main() {
    static_cast<void>(&Report);
    static_cast<void>(g_fakeAnimations);static_cast<void>(kFakeLayerCount);
    static_cast<void>(kFakeDefaultAnimation);static_cast<void>(kScript);
    LuaRuntime::LuaSpriteBindings bindings{};
    @BINDINGS@
    bindings.load=LoadProbe;bindings.play=PlayProbe;bindings.playOverlay=OverlayProbe;
    LuaRuntime::SetSpriteBindings(bindings);
    const char* script=R"lua(
local s=Sprite()
s:Load('gfx/bool.anm2')
s:Load('gfx/bool.anm2',nil)
s:Load('gfx/bool.anm2',false)
s:Load('gfx/bool.anm2',true)
s:Load('gfx/bool.anm2',0)
s:Load('gfx/bool.anm2','')
s:Load('gfx/bool.anm2',{},'ignored')
s:Load(123,false,'ignored')
for _,method in ipairs({'Play','PlayOverlay'}) do
    s[method](s,'Idle')
    s[method](s,'Idle',nil)
    s[method](s,'Idle',false)
    s[method](s,'Idle',true)
    s[method](s,'Idle',0)
    s[method](s,'Idle','')
    s[method](s,'Idle',{},'ignored')
    s[method](s,123,false,'ignored')
    assert(not pcall(s[method],s,{}))
end
assert(not pcall(s.Load,s,{}))
local m=RegisterMod('sprite bool contract',1);m:AddCallback(1,function()end)
)lua";
    const auto result=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@sprite-bool.lua");
    if(result!=LuaRuntime::LuaInitResult::Success) {
        char error[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
        std::fprintf(stderr,"%s\n",error);return 1;
    }
    assert(loaded==std::vector<bool>({true,true,false,true,true,true,true,false}));
    const std::vector<bool> expected{false,false,false,true,true,true,true,false};
    assert(played==expected&&overlays==expected);
    assert(!std::strcmp(g_play.name,"123")&&!std::strcmp(g_playOverlay.name,"123"));
}
'''


class SpritePcBooleanTests(unittest.TestCase):
    def test_effective_pc_defaults_truthiness_and_ignored_tail(self):
        with tempfile.TemporaryDirectory(prefix='sprite-pc-bool-') as folder:
            prefix=fixture.HARNESS.split('int main(',1)[0]
            bindings=fixture.HARNESS.split('LuaRuntime::LuaSpriteBindings bindings{};',1)[1].split(
                'LuaRuntime::SetSpriteBindings(bindings);',1)[0]
            flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS
                        if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
            with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
                binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(folder),
                                         harness_source=prefix+MAIN.replace('@BINDINGS@',bindings))
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
