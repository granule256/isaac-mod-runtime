from pathlib import Path
import subprocess
import tempfile
import unittest


RUNTIME = Path(__file__).resolve().parents[1]


class DeathAudioLifecycleTests(unittest.TestCase):
    def test_dead_players_do_not_receive_synthesized_effect_updates(self):
        source = (RUNTIME / 'source/lua_runtime.cpp').read_text()
        effects = source.split('void DispatchPlayerEntityEvents(', 1)[1].split('kCallbackPostPlayerUpdate', 1)[0]
        self.assertIn('kEntityIsDeadOffset', effects)
        self.assertIn('!dead', effects)

    def test_only_death_screen_sounds_are_drained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test.cpp').write_text(r'''
#include "interfaces/lua/game_over_sfx.hpp"
#include <cassert>
#include <vector>
using isaac::runtime::GameOverSfx;
int main() {
    GameOverSfx<4096> sounds;
    std::vector<int> stopped;
    const auto stop = [&](int id) { stopped.push_back(id); };
    sounds.Played(1);
    assert(!sounds.End(stop));
    sounds.Begin();
    sounds.Played(834);
    sounds.Played(834);
    sounds.Played(4095);
    sounds.Played(4096);
    sounds.Played(-1);
    sounds.Stopped(4095);
    assert(sounds.End(stop));
    assert(stopped == std::vector<int>{834});
    assert(!sounds.End(stop));
    sounds.Played(9);
    sounds.Begin();
    assert(sounds.End(stop));
    assert(stopped == std::vector<int>{834});
}
''')
            subprocess.run(['c++', '-std=c++20', '-I', str(RUNTIME / 'src'), str(root / 'test.cpp'),
                            '-o', str(root / 'test')], check=True)
            subprocess.run([str(root / 'test')], check=True)
