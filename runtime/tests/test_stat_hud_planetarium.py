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
    calls.foundHud = true;
    calls.foundHudValid = true;
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
    calls.gameFrame = 102;
    calls.foundHud = false;
    assert(stat_hud::PrepareFrame(hud.data(), true, calls));
    assert(!stat_hud::Enabled());
    assert(chanceCalls == 3 && unlockedCalls == 3);
    stat_hud::RestoreFrame(hud.data(), saved);
    assert(!stat_hud::Enabled());
    (void)base;
    return 0;
}
'''


NO_DUALITY_DRIVER = r'''
#include "interfaces/lua/stat_hud_planetarium.hpp"
#include "infrastructure/memory/engine_field_access.hpp"
#include <cassert>
#include <cstring>
#include <vector>

using namespace isaac::runtime;

struct Calls {
    int setFrames[4]{};
    int setFrameCount{};
    int renderCount{};
    stat_hud::Vector2 position{};
};

static Calls g_calls{};

static void SetFrame(void*, int frame) {
    ++g_calls.setFrameCount;
    g_calls.setFrames[g_calls.setFrameCount - 1] = frame;
}

static void Render(void*, const void* position, const void*, const void*) {
    ++g_calls.renderCount;
    std::memcpy(&g_calls.position, position, sizeof(g_calls.position));
}

int main() {
    std::vector<unsigned char> hud(0x400);
    const stat_hud::Vector2 renderPosition{40.0F, 15.0F};
    const stat_hud::NativeSpriteCalls calls{&SetFrame, &Render};
    const std::uintptr_t player = 0x1000;
    std::memcpy(engine_memory::AsObject(engine_memory::AddressOf(hud.data()) +
                                        stat_hud::kPlayerPointerOffset),
                &player, sizeof(player));

    stat_hud::g_frame = {true, 1.0F};
    assert(stat_hud::RenderNoDualityPlanetariumIcon(hud.data(), &renderPosition, calls));
    assert(g_calls.setFrameCount == 2);
    assert(g_calls.setFrames[0] == 8 && g_calls.setFrames[1] == 7);
    assert(g_calls.renderCount == 1);
    assert(g_calls.position.x == 40.0F && g_calls.position.y == 111.0F);

    *static_cast<unsigned char*>(engine_memory::AsObject(
        engine_memory::AddressOf(hud.data()) + stat_hud::kDualityFlagOffset)) = 1;
    assert(!stat_hud::RenderNoDualityPlanetariumIcon(hud.data(), &renderPosition, calls));
    assert(g_calls.renderCount == 1);

    *static_cast<unsigned char*>(engine_memory::AsObject(
        engine_memory::AddressOf(hud.data()) + stat_hud::kDualityFlagOffset)) = 0;
    *static_cast<unsigned char*>(engine_memory::AsObject(
        engine_memory::AddressOf(hud.data()) + stat_hud::kRowSpacingSelectorOffset)) = 1;
    assert(stat_hud::RenderNoDualityPlanetariumIcon(hud.data(), &renderPosition, calls));
    assert(g_calls.position.x == 40.0F && g_calls.position.y == 127.0F);

    stat_hud::g_frame = {};
    const int renders = g_calls.renderCount;
    assert(!stat_hud::RenderNoDualityPlanetariumIcon(hud.data(), &renderPosition, calls));
    assert(g_calls.renderCount == renders);
    return 0;
}
'''


class StatHudPlanetariumTests(unittest.TestCase):
    def run_driver(self, driver: str):
        with tempfile.TemporaryDirectory(prefix="isaac-stathud-planetarium-") as folder:
            work = Path(folder)
            source = work / "driver.cpp"
            source.write_text(driver, encoding="utf-8")
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

    def test_value_text_gate_and_restore(self):
        self.run_driver(DRIVER)

    def test_plain_icon_path_renders_native_frame8_at_expected_row(self):
        self.run_driver(NO_DUALITY_DRIVER)


if __name__ == "__main__":
    unittest.main()
