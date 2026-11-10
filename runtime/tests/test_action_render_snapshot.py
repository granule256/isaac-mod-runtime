"""A Poll edge survives skipped input ticks until one native Render consumes it."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from .test_input_button_edge_source import HARNESS, SOURCE
from .test_support import build_lua_harness

SCENARIO = r'''
    isaac::runtime::RenderFrameCoordinator coordinator;
    const auto action = [&](bool expected) {
        Check(luaL_dostring(state, "renderEdge=Input.IsActionTriggered(14,1)") == LUA_OK,
              "render action query runs");
        lua_getglobal(state,"renderEdge");
        Check((lua_toboolean(state,-1)!=0)==expected,"action edge matches phase snapshot");
        lua_pop(state,1);
    };
    const auto render = [&](bool expected,bool query=true) {
        const auto scans=isaac::runtime::g_InputSampleCalls.load();
        const auto buttonQueries=g_buttonCalls;
        isaac::runtime::RenderFrameScope frame(coordinator,nullptr);
        isaac::runtime::RenderInputFrameScope inputFrame;
        if(query){action(expected);action(expected);}
        Check(isaac::runtime::g_InputSampleCalls.load()==scans&&g_buttonCalls==buttonQueries,
              "render boundary performs no engine input queries");
    };
    g_heldButtons=0;advance_frame();
    render(false,false); // consume previous unrelated input without querying
    g_heldButtons=1u<<13;advance_frame();
    action(true); // update phase retains native Poll semantics
    isaac::runtime::NativeFrameClock::MarkNativeFrame(false);
    action(false); // skipped update must not replay that Poll edge
    render(true); // first render sees it even though the native clock advanced
    render(false); // next render expires it even without another Poll
    g_heldButtons=0;advance_frame();
    g_heldButtons=1u<<13;advance_frame();
    render(true);
    render(false);
    g_heldButtons=0;advance_frame();
    g_heldButtons=1u<<13;advance_frame();
    render(true,false); // consume the edge at the boundary without any reader
    render(false);
    // A Poll during a render must not change the shared visible render view.
    g_heldButtons=0;advance_frame();
    {
        isaac::runtime::RenderFrameScope frame(coordinator,nullptr);
        isaac::runtime::RenderInputFrameScope inputFrame;
        action(false);
        g_heldButtons=1u<<13;advance_frame();
        action(false);
        {
            isaac::runtime::RenderFrameScope nested(coordinator,nullptr);
            isaac::runtime::RenderInputFrameScope nestedInput;
            action(false);
        }
        action(false);
    }
    action(true); // update still sees the new Poll immediately
    render(true); // that Poll belongs to the following native render
    render(false);
'''

PHASE_DRIVERS = r'''
static int PhasePoll(lua_State* state) {
    g_heldButtons=lua_toboolean(state,1)?1u<<13:0;
    isaac::runtime::NativeFrameClock::MarkNativeFrame();return 0;
}
static int PhaseSkip(lua_State*) {
    isaac::runtime::NativeFrameClock::MarkNativeFrame(false);return 0;
}
static int PhaseRender(lua_State* state) {
    isaac::runtime::RenderInputFrameScope inputFrame;
    lua_getglobal(state,"_phaseRender");lua_call(state,0,0);return 0;
}
static void InstallPhaseDrivers(lua_State* state) noexcept {
    lua_pushcfunction(state,PhasePoll);lua_setglobal(state,"PhasePoll");
    lua_pushcfunction(state,PhaseSkip);lua_setglobal(state,"PhaseSkip");
    lua_pushcfunction(state,PhaseRender);lua_setglobal(state,"PhaseRender");
}
'''
PHASE_SCENARIO = r'''
    LuaRuntime::SetRuntimeExtensionInstaller(InstallPhaseDrivers);
    const char* phaseScript=R"lua(
local mod=RegisterMod("action-render-phase",1)
local expected=false
local reads=0
local function nativeRead()
    assert(not Input.IsActionTriggered(14,1),"nested update/input callback keeps native snapshot")
end
mod:AddCallback(1,nativeRead) -- MC_POST_UPDATE, not NPC_UPDATE=0
mod:AddCallback(13,nativeRead)
local function renderRead()
    assert(Input.IsActionTriggered(14,1)==expected,"render sees pending edge")
    Isaac.RunCallback(1)
    Isaac.RunCallback(13,nil,0,14)
    assert(Input.IsActionTriggered(14,1)==expected,"render restored after nested callbacks")
    reads=reads+1
end
mod:AddCallback(2,renderRead) -- MC_POST_RENDER
mod:AddCallback(32,renderRead) -- MC_POST_PLAYER_RENDER
function _phaseRender() Isaac.RunCallback(2);Isaac.RunCallback(32) end
PhasePoll(false);PhasePoll(true);PhaseSkip()
expected=true;PhaseRender()
expected=false;PhaseRender()
assert(reads==4)
)lua";
    Check(LuaRuntime::InitializeFromBuffer(phaseScript,std::strlen(phaseScript),"@action-render-phase.lua")
          ==LuaRuntime::LuaInitResult::Success,"actual nested render/update callback phases");
'''

class ActionRenderSnapshotTests(unittest.TestCase):
    def test_real_poll_skipped_update_render_and_lua_queries(self):
        marker='    // The global PC clock counts native cycles'
        harness=HARNESS.replace('#include "interfaces/lua/input_api.hpp"',
            '#include "interfaces/lua/input_api.hpp"\n#include "domain/runtime/render_frame_coordinator.hpp"')
        self.assertIn(marker,harness)
        harness=harness.replace(marker,SCENARIO+'\n'+marker,1)
        harness=harness.replace('int main() {',PHASE_DRIVERS+'\nint main() {',1)
        harness=harness.replace('    lua_close(state);',PHASE_SCENARIO+'\n    lua_close(state);',1)
        with tempfile.TemporaryDirectory(prefix='isaac-action-render-') as folder:
            binary=build_lua_harness(source_root=SOURCE,workdir=Path(folder),harness_source=harness)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
