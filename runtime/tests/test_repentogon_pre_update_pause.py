"""Callback pause suppresses ordinary post-update work before any frame scan."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from . import test_support
from .test_repentogon_callbacks import RUNTIME_DRIVER, SOURCE

DRIVER=RUNTIME_DRIVER.replace('static NativePort port{Ready,Install};',r'''
static bool forcedUpdatePause{};static unsigned pauseQueries{},snapshotCalls{},nativeFrame=10;
static bool NativeUpdatePaused() noexcept {++pauseQueries;return forcedUpdatePause;}
static NativePort port{Ready,Install,nullptr,NativeUpdatePaused};
static bool Snapshot(ManagedUpdateSnapshot* out) noexcept {++snapshotCalls;out->game=0x1000;out->frame=nativeFrame;return true;}
''').replace('#include "runtime_constants.hpp"','#include "runtime_constants.hpp"\n#include "game_observer.hpp"\nGameIsPausedObservation ObserveGameIsPaused(uintptr_t,uintptr_t){return GameIsPausedObservation::ThunkUnavailable;}\n#include "interfaces/lua/isaac_api.hpp"\n#include "application/callback/callback_dispatcher.hpp"')
DRIVER=DRIVER.replace('    if(mode=="off"||mode=="none"){',
 '    if(mode=="post_gate"){script+="m:AddCallback(1,function()calls=calls+1 end)";}else if(mode=="off"||mode=="none"){',1)
DRIVER=DRIVER.replace('        if(mode=="catalog"){',r'''
        if(mode=="post_gate"){
            SetManagedUpdateSnapshotReaderForTest(Snapshot);assert(g_ExtendedCallbackEnabledCount==0);
            const auto epoch=EngineGuardDispatchEpoch().load();const auto frames=ManagedFrameClock::Count();
            forcedUpdatePause=true;LuaRuntime::DispatchPostUpdate();LuaRuntime::DispatchPostUpdate();
            assert(snapshotCalls==0&&Number("calls")==0&&ManagedFrameClock::Count()==frames&&EngineGuardDispatchEpoch().load()==epoch);
            forcedUpdatePause=false;LuaRuntime::DispatchPostUpdate();Check();
            assert(snapshotCalls==1&&Number("calls")==1&&ManagedFrameClock::Count()==frames+1);
            g_ExtendedCallbackDelivery=false;forcedUpdatePause=true;++nativeFrame;const auto queries=pauseQueries;
            LuaRuntime::DispatchPostUpdate();Check();
            assert(snapshotCalls==2&&Number("calls")==2&&pauseQueries==queries&&ManagedFrameClock::Count()==frames+2);
            g_ExtendedCallbackDelivery=true;SetManagedUpdateSnapshotReaderForTest(nullptr);
        }else if(mode=="catalog"){
''',1)

class PreUpdatePauseTests(unittest.TestCase):
    def test_callback_pause_skips_post_update_scan_and_clock_even_without_listeners(self):
        with tempfile.TemporaryDirectory(prefix='repentogon-post-pause-') as tmp:
            tmp=Path(tmp)
            if os.environ.get('REPENTOGON_PHASE_BASELINE'):
                copy=tmp/'baseline_runtime.cpp'
                text=(SOURCE/'lua_runtime.cpp').read_text()
                copy.write_text(text.replace('    if(isaac::runtime::g_ExtendedCallbackDelivery&&isaac::runtime::repentogon::UpdatePaused())return;\n','',1))
                sources=tuple(copy if p==SOURCE/'lua_runtime.cpp' else p for p in test_support.layered_lua_runtime_sources(SOURCE))
                with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
                    binary=test_support.build_lua_harness(source_root=SOURCE,workdir=tmp,harness_source=DRIVER)
            else:
                binary=test_support.build_lua_harness(source_root=SOURCE,workdir=tmp,harness_source=DRIVER)
            result=subprocess.run([str(binary),'post_gate'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
