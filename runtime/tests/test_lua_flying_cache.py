"""Flying cache callbacks must update terrain movement, not only flight visuals."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_support import build_lua_harness
from .test_lua_batch285_receivers import HARNESS, SOURCE


class FlyingCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="isaac-flying-cache-")
        harness = HARNESS.replace("#include <vector>", "#include <vector>\n#include <string>")
        start = harness.index("    const char* script = nullptr;")
        end = harness.index("    return 0;\n}", start)
        harness = harness[:start] + r'''
    const bool revoke = std::strcmp(scenario, "pickup") == 0;
    const bool unchanged = std::strcmp(scenario, "player") == 0;
    const bool unrelated = std::strcmp(scenario, "unrelated") == 0;
    const std::uint8_t before = revoke || unchanged ? 1 : 0;
    const std::int32_t initialLayer = unchanged ? 1 : (revoke ? 3 : 5);
    WriteAt(g_PlayerBytes, kEntityPlayerCanFlyOffset, before);
    WriteAt(g_PlayerBytes, kEntityFlyingLayerOffset, initialLayer);
    std::string script = std::string("local grant = ") + (revoke ? "false" : "true") + R"lua(
local mod = RegisterMod('flight-cache-test', 1)
mod:AddCallback(ModCallbacks.MC_EVALUATE_CACHE, function(_, player, flag)
    player.CanFly = not grant
end)
mod:AddCallback(ModCallbacks.MC_EVALUATE_CACHE, function(_, player, flag)
    player.CanFly = grant
    print('FLIGHT_CACHE_CALLBACK_OK')
end)
)lua";
    static_cast<void>(LuaRuntime::InitializeFromBuffer(script.c_str(), script.size(), "@flight.lua"));
    LuaRuntime::DispatchEvaluateCache(AddressOf(g_PlayerBytes), unrelated ? 1 : 128);
    std::int32_t layer = -1;
    std::memcpy(&layer, g_PlayerBytes.data() + kEntityFlyingLayerOffset, sizeof(layer));
    const auto canFly = g_PlayerBytes[kEntityPlayerCanFlyOffset];
    const std::int32_t expected = unchanged || unrelated ? initialLayer : (revoke ? 5 : 3);
    if (layer != expected || canFly != (revoke ? 0 : 1)) {
        std::printf("flight layer=%d expected=%d CanFly=%u\n", layer, expected, canFly);
        return 92;
    }
''' + harness[end:]
        harness = harness.replace('} else {\n        return 91;',
                                  '} else if (std::strcmp(scenario, "unrelated") != 0) {\n        return 91;', 1)
        cls.binary = build_lua_harness(source_root=SOURCE, workdir=Path(cls.tmp.name),
                                      harness_source=harness)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_callback_final_flight_controls_terrain_layer(self):
        for scenario in ("npc", "pickup", "player", "unrelated"):
            with self.subTest(scenario=scenario):
                result = subprocess.run([str(self.binary), scenario], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("FLIGHT_CACHE_CALLBACK_OK", result.stdout)
