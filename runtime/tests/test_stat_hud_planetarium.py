"""Host checks for the StatHUD planetarium value and text gate."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"


DRIVER = r'''
#include "interfaces/lua/stat_hud_planetarium.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include <cassert>
#include <cstring>
#include <vector>

using namespace isaac::runtime;

static int chanceCalls{};
static int unlockedCalls{};
static float Chance(void*) { ++chanceCalls; return 1.25F; }
static bool Unlocked(void*, std::uint32_t id) { ++unlockedCalls; return id == 406; }

static std::uintptr_t PointerSlot(std::vector<unsigned char>& bytes,
                                  std::uintptr_t slot) {
    return engine_memory::AddressOf(bytes.data()) + slot * stat_hud::kPlayerSlotStride +
           stat_hud::kPlayerPointerOffset;
}

static std::uintptr_t StatSlot(std::vector<unsigned char>& bytes,
                               std::uintptr_t slot) {
    return engine_memory::AddressOf(bytes.data()) + stat_hud::kStatArrayOffset +
           slot * stat_hud::kPlayerSlotStride + stat_hud::kPlanetariumStatValueOffset;
}

int main() {
    static_assert(stat_hud::IconResumeIndex(false, false) == 0);
    static_assert(stat_hud::IconResumeIndex(true, true) == 0);
    static_assert(stat_hud::IconResumeIndex(true, false) == 1);
    static_assert(stat_hud::TextResumeIndex(0, 8, true) == 2);
    static_assert(stat_hud::TextResumeIndex(0, 8, false) == 1);
    static_assert(stat_hud::TextResumeIndex(1, 9, true) == 1);
    static_assert(stat_hud::TextResumeIndex(2, 3, false) == 0);

    std::vector<unsigned char> hud(0x500);
    const auto base = engine_memory::AddressOf(hud.data());
    const std::uintptr_t player0 = 0x1000;
    const std::uintptr_t player1 = 0x2000;
    std::memcpy(engine_memory::AsObject(PointerSlot(hud, 0)),
                &player0, sizeof(player0));
    std::memcpy(engine_memory::AsObject(PointerSlot(hud, 1)),
                &player1, sizeof(player1));

    stat_hud::NativeCalls calls{};
    calls.game = reinterpret_cast<void*>(0x3000);
    calls.persistentGameData = reinterpret_cast<void*>(0x4000);
    calls.planetariumChance = &Chance;
    calls.unlocked = &Unlocked;
    calls.gameFrame = 100;
    calls.gameFrameValid = true;
    assert(stat_hud::PrepareFrame(hud.data(), true, calls));
    assert(stat_hud::Enabled());
    assert(chanceCalls == 1 && unlockedCalls == 1);
    assert(stat_hud::PrepareFrame(hud.data(), true, calls));
    assert(chanceCalls == 1 && unlockedCalls == 1);
    for (std::uintptr_t slot = 0; slot < 2; ++slot) {
        float value = 0;
        float delta = -1;
        std::uint32_t timer = 1;
        const auto stat = StatSlot(hud, slot);
        std::memcpy(&value, engine_memory::AsObject(stat), sizeof(value));
        std::memcpy(&delta, engine_memory::AsObject(stat + sizeof(float)),
                    sizeof(delta));
        std::memcpy(&timer, engine_memory::AsObject(stat + stat_hud::kStatTimerOffset),
                    sizeof(timer));
        assert(value == 100.0F && delta == 0.0F && timer == 0);
    }

    const stat_hud::FrameState saved = stat_hud::g_frame;
    assert(stat_hud::PrepareFrame(hud.data(), false, calls));
    assert(!stat_hud::Enabled());
    assert(chanceCalls == 1 && unlockedCalls == 1);
    assert(stat_hud::PrepareFrame(hud.data(), true, calls));
    assert(chanceCalls == 2 && unlockedCalls == 2);
    calls.gameFrame = 101;
    assert(stat_hud::PrepareFrame(hud.data(), true, calls));
    assert(chanceCalls == 3 && unlockedCalls == 3);
    float unchanged = 0;
    std::memcpy(&unchanged, engine_memory::AsObject(StatSlot(hud, 0)),
                sizeof(unchanged));
    assert(unchanged == 100.0F);
    stat_hud::RestoreFrame(hud.data(), saved);
    assert(!stat_hud::Enabled());
    (void)base;
    return 0;
}
'''


class StatHudPlanetariumTests(unittest.TestCase):
    def test_value_text_gate_and_restore(self):
        with tempfile.TemporaryDirectory(prefix="isaac-stathud-planetarium-") as folder:
            work = Path(folder)
            source = work / "driver.cpp"
            source.write_text(DRIVER, encoding="utf-8")
            binary = work / "driver"
            command = [
                "c++", "-std=c++23", "-Wall", "-Wextra", "-Werror",
                f"-I{SOURCE}", f"-I{ROOT / 'src'}",
                str(source), "-o", str(binary),
            ]
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
