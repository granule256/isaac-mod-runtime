"""PC argument semantics exercised by Reverie's Centipede and Devilcrow."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import test_support
from .test_lua_sprite import HARNESS as SPRITE_HARNESS, SCRIPT, SOURCE
from . import test_lua_batch303_vtable_calls as entity


class ReverieBossBindingTests(unittest.TestCase):
    def build_run(self, harness):
        with tempfile.TemporaryDirectory(prefix='boss-binding-') as folder:
            flags=tuple(f for f in test_support.HARNESS_COMPILE_FLAGS
                        if not f.startswith('-DEXL_DIAGNOSTIC_STAGE='))
            with patch.object(test_support,'HARNESS_COMPILE_FLAGS',flags):
                binary=test_support.build_lua_harness(source_root=SOURCE,
                    workdir=Path(folder),harness_source=harness)
            result=subprocess.run([str(binary)],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_sprite_flipx_uses_pc_truthiness(self):
        script=SCRIPT.replace('local sprite = Sprite()', '''local sprite = Sprite()
  sprite.FlipX=nil;assert(sprite.FlipX==false)
  sprite.FlipX=false;assert(sprite.FlipX==false)
  sprite.FlipX=true;assert(sprite.FlipX==true)
  sprite.FlipX=0;assert(sprite.FlipX==true)
  sprite.FlipX='';assert(sprite.FlipX==true)
  sprite.FlipX={};assert(sprite.FlipX==true)
  sprite.FlipX=false
''')
        self.build_run(SPRITE_HARNESS.replace('@SCRIPT@',script))

    def test_entity_kill_ignores_trailing_values_and_keeps_virtual_dispatch(self):
        harness=entity.HARNESS.split('int main(',1)[0]
        harness+=r'''
int main(){
 PublishFakeWorld(0x1A2B3C4D,0x5E6F7081);
 SetVtableSlot(kEntityPlayerVtableOffset,kEntityVtableKillSlot,0x1A2B3C4D);
 SetVtableSlot(kEntityNpcVtableOffset,kEntityVtableKillSlot,0x5E6F7081);
 LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x3030);
 const char*script=R"lua(
 local p=Isaac.GetPlayer(0)
 assert(select('#',p:Kill(nil,{},'ignored'))==0)
 local n=p.Parent:ToNPC();assert(n)
 assert(select('#',n:Kill(EntityRef(n)))==0)
 assert(not pcall(function()p.Kill({})end))
 )lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@kill-extra.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[512]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 if(g_HostEngineCallTrampolineCalls!=2 || g_HostEngineCallTrampolineLastTarget!=0x5E6F7081 ||
    g_HostEngineCallTrampolineLastIntegers[0]!=AddressOf(g_NpcBytes))return 2;
 return 0;
}
'''
        self.build_run(harness)
