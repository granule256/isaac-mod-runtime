"""Native Tear/Effect Init and Fire do not depend on the frame's room/player gate."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import test_lua_entity_query as fixture
from . import test_support


MAIN = r'''
int main(int argc, char** argv) {
    if (argc != 2) return 90;
    static_cast<void>(kScriptTemplate);
    static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);
    static_cast<void>(&PublishLists);
    static_cast<void>(&PublishGame);
    static_cast<void>(&PublishEntityList);
    // Valid callback arguments need the module's identity layout. No room,
    // game owner or player vector is published to satisfy a global world gate.
    CreateBlocks(); FillEntities();
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
    if (isaac::runtime::ShouldDispatchManagedCallbacks()) return 91;
    const char* script = R"lua(
local m = RegisterMod('native events before world ready', 1)
tearInit, effectInit, tearFire = 0, 0, 0
m:AddCallback(ModCallbacks.MC_POST_TEAR_INIT, function(_, tear)
    assert(tear.Type == 2 and tear.Variant == 0)
    tear:GetData().initialized = true
    tearInit = tearInit + 1
end, 0)
m:AddCallback(ModCallbacks.MC_POST_EFFECT_INIT, function(_, effect)
    assert(effect.Type == 1000 and effect.Variant == 7)
    effect:GetData().initialized = true
    effectInit = effectInit + 1
end, 7)
m:AddCallback(ModCallbacks.MC_POST_FIRE_TEAR, function(_, tear)
    assert(tear.Type == 2)
    tearFire = tearFire + 1
end)
)lua";
    if (LuaRuntime::InitializeFromBuffer(script, std::strlen(script), "@native-world-gate.lua") !=
        LuaRuntime::LuaInitResult::Success) return 1;
    const std::string mode = argv[1];
    const auto tear = AddressOf(g_Entities[kTearNear]);
    const auto effect = AddressOf(g_Entities[kEffect]);
    if (mode == "tear") {
        LuaRuntime::DispatchNativeTearInit(0);
        LuaRuntime::DispatchNativeTearInit(effect); // Type checks remain necessary.
        LuaRuntime::DispatchNativeTearInit(tear);
    } else if (mode == "effect") {
        LuaRuntime::DispatchNativeEffectInit(0);
        LuaRuntime::DispatchNativeEffectInit(tear);
        LuaRuntime::DispatchNativeEffectInit(effect);
    } else if (mode == "fire") {
        LuaRuntime::DispatchPostFireTear(0);
        LuaRuntime::DispatchPostFireTear(effect);
        LuaRuntime::DispatchPostFireTear(tear);
    } else return 92;
    if (!ExpectNumber("tearInit", mode == "tear" ? 1 : 0) ||
        !ExpectNumber("effectInit", mode == "effect" ? 1 : 0) ||
        !ExpectNumber("tearFire", mode == "fire" ? 1 : 0)) return 2;
    if (isaac::runtime::ShouldDispatchManagedCallbacks()) return 93;
    if (LuaRuntime::TakeCallbackError()) return 3;
    return 0;
}
'''


class NativeInitWorldGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='native-world-gate-')
        work = Path(cls.temp.name)
        api = fixture.SOURCE.parent / 'src/interfaces/lua/isaac_api.cpp'
        text = api.read_text()
        signature = 'bool ShouldDispatchManagedCallbacks() noexcept {'
        start = text.index(signature)
        end = start + len(signature)
        depth = 1
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        altered = work / 'isaac_api_world_unavailable.cpp'
        altered.write_text(text[:start] + signature + '\n    return false;\n}' + text[end:])
        sources = test_support.layered_lua_runtime_sources(fixture.SOURCE)
        sources = [altered if source == api else source for source in sources]
        flags = tuple(flag for flag in test_support.HARNESS_COMPILE_FLAGS
                      if not flag.startswith('-DEXL_DIAGNOSTIC_STAGE='))
        with patch.object(test_support, 'HARNESS_COMPILE_FLAGS', flags), \
             patch.object(test_support, 'layered_lua_runtime_sources', return_value=sources):
            cls.binary = test_support.build_lua_harness(source_root=fixture.SOURCE,
                workdir=work, harness_source=fixture.HARNESS.split('int main(', 1)[0] + MAIN)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_mode(self, mode):
        result = subprocess.run([str(self.binary), mode], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_tear_init_when_frame_world_gate_is_false(self):
        self.run_mode('tear')

    def test_effect_init_when_frame_world_gate_is_false(self):
        self.run_mode('effect')

    def test_fire_tear_when_frame_world_gate_is_false(self):
        self.run_mode('fire')
