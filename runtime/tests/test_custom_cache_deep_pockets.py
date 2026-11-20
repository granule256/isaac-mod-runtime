"""The vanilla Deep Pockets item invalidates the custom coin maximum."""
import subprocess
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src'

DRIVER = r'''
#include "application/custom_cache/custom_cache_runtime.hpp"
#include <cassert>
using namespace isaac::runtime::custom_cache;

struct State { bool ownsItem = false; unsigned coinEvaluations = 0; };

int main() {
    State state;
    RuntimeBridge bridge{};
    bridge.port.user = &state;
    bridge.port.defaultValue = [](void* user, std::uintptr_t, std::string_view tag) noexcept {
        return tag == "maxcoins" && static_cast<State*>(user)->ownsItem ? 999.0 : 99.0;
    };
    bridge.port.evaluate = [](void* user, std::uintptr_t, std::string_view tag,
                              double, double*) noexcept {
        if (tag == "maxcoins") ++static_cast<State*>(user)->coinEvaluations;
        return false;
    };
    assert(ConfigureRuntimeBridge(&bridge));
    constexpr std::uintptr_t player = 1;
    auto check = [&] {
        state.ownsItem = false;
        EvaluateCustomCacheItemsForPlayer(player, kCacheAll);
        assert(GetConsumableMaximumForPlayer(player, "maxcoins") == 99);
        const auto evaluations = state.coinEvaluations;
        state.ownsItem = true;
        TriggerItemCustomCacheForPlayer(player, ItemKind::Collectible, 416, true);
        assert(GetConsumableMaximumForPlayer(player, "maxcoins") == 999);
        assert(state.coinEvaluations == evaluations + 1);
        state.ownsItem = false;
        TriggerItemCustomCacheForPlayer(player, ItemKind::Collectible, 416, true);
        assert(GetConsumableMaximumForPlayer(player, "maxcoins") == 99);
        assert(state.coinEvaluations == evaluations + 2);
    };
    check();
    ClearCustomCacheXmlTags();
    check();
}
'''


class CustomCacheDeepPocketsTests(unittest.TestCase):
    def test_item_changes_refresh_previously_evaluated_maxcoins(self):
        with tempfile.TemporaryDirectory() as temp:
            driver = Path(temp) / 'test.cpp'
            driver.write_text(DRIVER)
            binary = driver.with_suffix('')
            cache = SRC / 'application/custom_cache'
            subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                            '-I', str(SRC), str(driver), str(cache / 'custom_cache.cpp'),
                            str(cache / 'custom_cache_runtime.cpp'), '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
