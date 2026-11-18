import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LevelStageMappingCostTests(unittest.TestCase):
    def test_stage_rereads_values_but_reuses_strict_mapping_proofs_within_dispatch(self):
        harness = r'''
#include "game_observer.hpp"
#include "infrastructure/memory/engine_memory_guard.hpp"
#include "lib/nx/nx.h"
#include <cassert>
#include <limits>

using namespace isaac::runtime;
alignas(8) std::uint32_t gameA = 2, gameB = 4;
std::uintptr_t game = 0, owner = 0;
unsigned queries = 0;
u32 permissions = Perm_Rw;
bool failQuery = false;

extern "C" Result svcQueryMemory(MemoryInfo* info, u32* page, u64 addr) {
    ++queries;
    if (failQuery) return 1;
    for (const auto region : {std::pair{reinterpret_cast<u64>(&owner), sizeof(owner)},
                              std::pair{reinterpret_cast<u64>(&game), sizeof(game)},
                              std::pair{reinterpret_cast<u64>(&gameA), sizeof(gameA)},
                              std::pair{reinterpret_cast<u64>(&gameB), sizeof(gameB)}}) {
        if (addr >= region.first && addr - region.first < region.second) {
            *info = {};
            info->addr = region.first; info->size = region.second; info->perm = permissions;
            *page = 0;
            return 0;
        }
    }
    return 1;
}

int main() {
    auto slot = reinterpret_cast<std::uintptr_t>(&owner);
    owner = reinterpret_cast<std::uintptr_t>(&game);
    game = reinterpret_cast<std::uintptr_t>(&gameA);
    auto read = [&](std::uint32_t expected) {
        std::uint32_t stage = 0;
        assert(ReadCurrentGameLevelStage(slot, &stage) == GameLevelStageObservation::Success);
        assert(stage == expected);
    };
    read(2); read(2); assert(queries == 6); // Load-time calls do not use a dispatch proof.

    EngineGuardEnterDispatch();
    for (unsigned i = 0; i < 1000; ++i) { gameA = i; read(i); }
    assert(queries == 9); // The original 3000 queries collapse to three mapping proofs.
    game = reinterpret_cast<std::uintptr_t>(&gameB);
    read(4); assert(queries == 10);
    game = 0;
    std::uint32_t sentinel = 99;
    assert(ReadCurrentGameLevelStage(slot, &sentinel) == GameLevelStageObservation::GameNull);
    assert(sentinel == 99);
    game = reinterpret_cast<std::uintptr_t>(&gameB);
    EngineGuardLeaveDispatch();

    permissions = Perm_Rx;
    EngineGuardEnterDispatch();
    // A general readable proof cannot satisfy the strict no-execute guard.
    EngineGuardRememberReadable(slot, slot + sizeof(owner));
    assert(ReadCurrentGameLevelStage(slot, &sentinel) == GameLevelStageObservation::OwnerUnreadable);
    permissions = Perm_Rw;
    failQuery = true;
    assert(ReadCurrentGameLevelStage(slot, &sentinel) == GameLevelStageObservation::OwnerUnreadable);
    failQuery = false;
    read(4);
    EngineGuardSetCacheEnabled(false);
    permissions = Perm_Rx;
    assert(ReadCurrentGameLevelStage(slot, &sentinel) == GameLevelStageObservation::OwnerUnreadable);
    EngineGuardSetCacheEnabled(true);
    assert(ReadCurrentGameLevelStage(slot, &sentinel) == GameLevelStageObservation::OwnerUnreadable);
    EngineGuardLeaveDispatch();
    assert(ReadCurrentGameLevelStage(slot + 1, &sentinel) == GameLevelStageObservation::OwnerUnreadable);
    assert(ReadCurrentGameLevelStage(std::numeric_limits<std::uintptr_t>::max() - 7, &sentinel) ==
           GameLevelStageObservation::OwnerUnreadable);
    assert(sentinel == 99);
}
'''
        source = ROOT / "runtime/source"
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "main.cpp"
            fixture.write_text("#include <utility>\n" + harness)
            exe = str(Path(temp) / "level-stage")
            subprocess.run([
                "c++", "-std=c++17", "-O2", "-I" + str(source),
                "-I" + str(ROOT / "runtime/src"), str(fixture),
                str(source / "game_observer.cpp"), "-o", exe,
            ], check=True)
            run = subprocess.run([exe], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
