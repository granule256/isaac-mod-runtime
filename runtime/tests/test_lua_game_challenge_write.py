"""CuerLib temporarily changes Challenge while recomputing shooting eligibility."""
import unittest
from .test_api500_world import run_world
from .test_lua_game_time_counter import MAIN as TIME_MAIN

SCRIPT = r'''
local game = Game()
assert(game.Challenge == 17)
local player = Isaac.GetPlayer(0)
local oldChallenge = game.Challenge
game.Challenge = 6
player:UpdateCanShoot()
game.Challenge = oldChallenge
assert(game.Challenge == 17, "original challenge must be restored")
assert(Isaac.GetChallenge() == 17, "native getter sees restoration")
game.Challenge = nil
game.Challenge = {}
game.Challenge = "invalid"
assert(game.Challenge == 17, "invalid writes preserve native challenge")
game:GetLevel().Challenge = 6
assert(game.Challenge == 17, "Level cannot write the Game field")
'''

MAIN = TIME_MAIN.replace('#include <atomic>', '''#include <atomic>
#include "interfaces/lua/api200_player.hpp"
#include "interfaces/lua/api200_player.guards.hpp"
#include "infrastructure/call/engine_call_access.hpp"
''').replace('int main(){', r'''
static unsigned challengeUpdates{};
static void NativeUpdateCanShoot(void* player) {
    assert(player == g_Entities[kPlayer].data());
    std::int32_t challenge{};
    std::memcpy(&challenge, g_GameBytes.data() + kGameChallengeOffset, sizeof(challenge));
    assert(challenge == 6 && "native shooting update must observe temporary challenge");
    ++challengeUpdates;
}
int main(){
''').replace('g_GameBytes.resize(kGameTimeCounterOffset + 16, 0);',
            'g_GameBytes.resize(kGameChallengeOffset + 16, 0);')
start = MAIN.index('    const char* script = R"lua(')
end = MAIN.index(')lua";', start) + len(')lua";')
MAIN = MAIN[:start] + '''
WriteAt<std::int32_t>(g_GameBytes, kGameChallengeOffset, 17);
std::memcpy(g_ModuleBytes.data() + api200_player::kUpdateCanShootEntry,
            api200_player::kUpdateCanShootGuard.data(),
            api200_player::kUpdateCanShootGuard.size());
Api200PlayerNativeTestBindings bindings{};
bindings.methods[32] = engine_call::AddressOfFunction(&NativeUpdateCanShoot);
SetApi200PlayerNativeTestBindings(bindings);
const char* script = R"lua(''' + SCRIPT + ')lua";' + MAIN[end:]
start = MAIN.index('    std::int32_t native = 0;')
MAIN = MAIN[:start] + r'''
    std::int32_t native{};
    std::memcpy(&native, g_GameBytes.data() + kGameChallengeOffset, sizeof(native));
    assert(native == 17 && challengeUpdates == 1);
    assert(g_IsaacGameTimeCounterWriteCount.load() == 0);
    assert(g_IsaacIgnoredFieldWriteCount.load() == 4);
    return 0;
}
'''


class GameChallengeWrite(unittest.TestCase):
    def test_temporary_challenge_reaches_native_update_then_restores(self):
        result = run_world(main=MAIN)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
