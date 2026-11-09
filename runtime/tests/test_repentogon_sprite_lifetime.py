"""RGON pause sprites retain native lifetime and reuse views without per-frame allocations."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from . import test_support
from .test_repentogon_callbacks import RUNTIME_DRIVER, SOURCE

DRIVER=RUNTIME_DRIVER.replace('static NativePort port{Ready,Install};',r'''
static std::uintptr_t activeMain{},activeStats{};
static bool ValidSprite(std::uintptr_t address) noexcept {return address&&(address==activeMain||address==activeStats);}
static NativePort port{Ready,Install,ValidSprite};
''')
DRIVER=DRIVER.replace('if(mode=="off"||mode=="none"){',r'''
if(mode=="persistent") {
 script+=R"lua(
m:AddCallback(1218,function(_,main,stats)
 assert(_spriteAlive(main) and _spriteAlive(stats))
 if savedMain then assert(rawequal(savedMain,main) and rawequal(savedStats,stats)) end
 savedMain=main;savedStats=stats;calls=calls+1
end)
m:AddCallback(1020,function()assert(_spriteAlive(savedMain) and _spriteAlive(savedStats));calls=calls+1 end)
m:AddCallback(1021,function()assert(not _spriteAlive(savedMain) and not _spriteAlive(savedStats)) end)
)lua";
}else if(mode=="off"||mode=="none"){
''',1)
DRIVER=DRIVER.replace('if(mode=="catalog"){\n            assert',r'''
if(mode=="persistent") {
 activeMain=Address(entity);activeStats=Address(collider);
 send(1218);Check();send(1020);Check();assert(Number("calls")==2);
 send(1218);Check();assert(Number("calls")==3);
 auto* state=savedState;
 void* allocatorContext{};const auto allocator=lua_getallocf(state,&allocatorContext);
 CleanupAllocator meter{allocator,allocatorContext};
 lua_setallocf(state,RejectCleanupAllocation,&meter);
 for(unsigned i=0;i<1000;++i) {
  const auto ref=BeginCallbackSpriteScope(state);
  PushCallbackSpriteHandle(state,activeMain,ref);lua_pop(state,1);
  PushCallbackSpriteHandle(state,activeStats,ref);lua_pop(state,1);
  EndCallbackSpriteScope(state,ref);
 }
 lua_setallocf(state,allocator,allocatorContext);assert(meter.attempts==0);
 activeMain=activeStats=0;send(1021);Check();
 }else if(mode=="catalog"){
            assert''',1)
DRIVER=DRIVER.replace('static void Extensions(lua_State* state) noexcept {','static lua_State* savedState{};\nstatic void Extensions(lua_State* state) noexcept {savedState=state;')

class PauseSpriteLifetimeTests(unittest.TestCase):
 def test_persistent_validated_borrowing_and_warm_cache_no_allocations(self):
  with tempfile.TemporaryDirectory() as task_dir:
   binary=test_support.build_lua_harness(source_root=SOURCE,workdir=Path(task_dir),harness_source=DRIVER)
   result=subprocess.run([str(binary),'persistent'],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
