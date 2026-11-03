"""Fiend 音效苍蝇的关门属性及 Golem 道具魂火返回视图。"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from . import test_lua_batch303_vtable_calls as fixture
from . import test_support

ROOT = Path(__file__).resolve().parents[2]
PREFIX = r'''
#include <cstdint>
extern "C" std::uintptr_t FiendHostWisp(std::uintptr_t, int, const void*, bool);
extern "C" void FiendHostRemoveOrbit(std::uintptr_t);
template<class Fn> Fn FiendWispFunction(std::uintptr_t) {
    return reinterpret_cast<Fn>(&FiendHostWisp);
}
template<class Fn> Fn FiendOrbitFunction(std::uintptr_t) {
    return reinterpret_cast<Fn>(&FiendHostRemoveOrbit);
}
'''
MAIN = r'''
#include "interfaces/lua/entity_lifetime.hpp"
#include <cassert>
std::vector<unsigned char> g_WispBytes;
unsigned wispCalls{}, orbitCalls{};
std::string g_Scene;
extern "C" std::uintptr_t FiendHostWisp(std::uintptr_t player, int item, const void* pos, bool adjust) {
    assert(player == AddressOf(g_PlayerBytes) && item == 139 && !adjust);
    float values[2]; std::memcpy(values, pos, sizeof(values));
    assert(values[0] == -1000 && values[1] == -1000);
    if(g_Scene=="retired")isaac::runtime::RetireEntityLifetime(AddressOf(g_NpcBytes));
    if(g_Scene=="wrong_type"){
        WriteAt<std::uintptr_t>(g_NpcBytes,0,g_EngineBase+kEntityPlayerVtableOffset);
        WriteAt<unsigned>(g_NpcBytes,kEntityTypeOffset,1);
    }
    ++wispCalls; return AddressOf(g_WispBytes);
}
extern "C" void FiendHostRemoveOrbit(std::uintptr_t familiar) {
    assert(familiar == AddressOf(g_WispBytes)); ++orbitCalls;
    WriteAt<int>(g_WispBytes, 0xd84, -1);
}
int main(int argc, char** argv) {
    assert(argc == 2); std::string scene = argv[1];g_Scene=scene;
    PublishFakeWorld(0x1234, 0x5678);
    LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes), 0x3030);
    // NPC::CanShutDoors at 0x124b00 reads +cc8; NPC::Init copies config+5c there.
    const unsigned char doorGuard[] = {0x08,0x20,0x73,0x39,0xa8,0x00,0x00,0x34,0x08,0xec,0x46,0x39,0x1f,0x01,0x1b,0x72};
    std::memcpy(g_ModuleBytes.data()+0x124b00,doorGuard,sizeof(doorGuard));
    std::memcpy(g_ModuleBytes.data()+kEntityPlayerAddItemWispOffset,
                kEntityPlayerAddItemWispExpectedBytes.data(),16);
    std::memcpy(g_ModuleBytes.data()+kEntityFamiliarRemoveFromOrbitOffset,
                kEntityFamiliarRemoveFromOrbitExpectedBytes.data(),16);
    MakeFakeEntity(g_WispBytes,kEntityFamiliarVtableOffset);
    WriteAt<unsigned>(g_WispBytes,kEntityTypeOffset,3);
    WriteAt<int>(g_WispBytes,0xd84,7);
    g_NpcBytes[0xcc8]=1;g_NpcBytes[0xcc9]=0x5a;g_NpcBytes[0x1bb]=0x20;
    std::string body;
    if(scene=="npc") body=R"lua(
        assert(type(n.CanShutDoors)=='boolean' and n.CanShutDoors)
        n.CanShutDoors=false;assert(n.CanShutDoors==false)
        n.CanShutDoors=true;assert(n.CanShutDoors==true)
        n.CanShutDoors=nil;assert(n.CanShutDoors==false)
        n.CanShutDoors=0;assert(n.CanShutDoors==true)
        n.CanShutDoors=false
        assert(type(p.CanShutDoors)=='function')
        assert(not pcall(function() p.CanShutDoors=false end))
    )lua";
    else if(scene=="wisp") body=R"lua(
        local w=p:AddItemWisp(139,Vector(-1000,-1000),false)
        assert(w and type(w.RemoveFromOrbit)=='function','item wisp must expose familiar methods')
        assert(getmetatable(w)==getmetatable(w:ToFamiliar()))
        w:RemoveFromOrbit();assert(w.OrbitLayer==-1)
    )lua";
    else if(scene=="badguard") {
        g_ModuleBytes[0x124b00+15]^=1;
        body="assert(not pcall(function() return n.CanShutDoors end));assert(not pcall(function() n.CanShutDoors=false end))";
    } else if(scene=="retired" || scene=="wrong_type") body=R"lua(
        assert(n.CanShutDoors==nil)
        local ok=pcall(function() n.CanShutDoors=false end)
        -- Existing expired-write behavior is a no-op; live sibling types must reject.
        if SCENE=='wrong_type' then assert(not ok) else assert(ok) end
    )lua";
    else return 90;
    std::string script="local SCENE='"+scene+"';local p=Isaac.GetPlayer(0);local n=p.Parent:ToNPC();assert(n);";
    if(scene=="retired"||scene=="wrong_type")script+="p:AddItemWisp(139,Vector(-1000,-1000),false);";
    script+=body;
    if(LuaRuntime::InitializeFromBuffer(script.c_str(),script.size(),"@fiend-regression.lua")!=LuaRuntime::LuaInitResult::Success){
        LuaRuntime::LuaErrorHistoryEntryView errors[8]{};
        auto count=LuaRuntime::CopyLuaErrorHistory(errors,8);
        for(unsigned i=0;i<count;++i)std::fprintf(stderr,"%s\n",errors[i].text);
        return 1;
    }
    if(scene=="wisp")return wispCalls==1 && orbitCalls==1 ? 0 : 3;
    assert(g_NpcBytes[0xcc9]==0x5a && g_NpcBytes[0x1bb]==0x20);
    assert(g_NpcBytes[0xcc8]==(scene=="npc"?0:1));
    return 0;
}
'''


class FiendNpcAndWispTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="fiend-npc-wisp-")
        work = Path(cls.tmp.name)
        source = fixture.HARNESS[:fixture.HARNESS.index("int main(")] + MAIN
        path = ROOT / "runtime/src/interfaces/lua/isaac_api.cpp"
        code = path.read_text().replace("engine_call::AsFunction<AddItemWispFn>", "FiendWispFunction<AddItemWispFn>")
        code = code.replace("engine_call::AsFunction<EntityFamiliarRemoveFromOrbitFn>", "FiendOrbitFunction<EntityFamiliarRemoveFromOrbitFn>")
        instrumented = work / "isaac_api.cpp"
        instrumented.write_text(PREFIX + code)
        sources = [instrumented if p == path else p for p in test_support.layered_lua_runtime_sources(fixture.SOURCE)]
        with mock.patch.object(test_support, "layered_lua_runtime_sources", return_value=sources):
            cls.binary = test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=work,harness_source=source)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_npc_writable_boolean_and_sibling_protection(self):
        self.run_scene("npc")

    def test_item_wisp_returns_familiar_and_runs_orbit_method(self):
        self.run_scene("wisp")

    def test_door_field_guard_lifetime_and_type(self):
        for scene in ("badguard", "retired", "wrong_type"):
            with self.subTest(scene=scene):
                self.run_scene(scene)

    def run_scene(self, scene):
        result = subprocess.run([str(self.binary), scene],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
