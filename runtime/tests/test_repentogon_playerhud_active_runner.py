"""Focused host checks for REPENTOGON callback 1079's PlayerHUD runner."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "runtime" / "source"
UNITS = ROOT / "runtime" / "src"
PRIVATE = SOURCE if (SOURCE / "repentogon_playerhud_active_runner.cpp").is_file() else (
    ROOT.parent / "private" / "runtime" / "source"
)
RUNNER = PRIVATE / "repentogon_playerhud_active_runner.cpp"
PROJECT = next((path for path in ROOT.parents if (path / "data/games").is_dir()),
               ROOT.parents[1])
NRO = (
    PROJECT
    / "data/games/The Binding of Isaac_ Afterbirth+ 1.7.9b "
      "[010021C000B6A800][v524288][UPD]/Program #0/1/.nro/Repentance.nro"
)

DRIVER = r'''
#include "repentogon_playerhud_active_runner.hpp"

#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>

using namespace isaac::runtime::repentogon::playerhud_active_runner;

namespace {

template <class T>
void Put(void* object, std::uintptr_t offset, T value) {
    std::memcpy(static_cast<std::uint8_t*>(object) + offset, &value,
                sizeof(value));
}

bool listen;
unsigned originalCalls;
unsigned dispatchCalls;
Event lastEvent{};
void* expectedPlayer;

bool Listening(std::uint32_t id) noexcept {
    assert(id == kCallbackId);
    return listen;
}

void Dispatch(const Event& event) noexcept {
    assert(originalCalls == 1);
    ++dispatchCalls;
    lastEvent = event;
}

void Original(void* hud, std::uint32_t slot, const Vector& pos, float size,
              float alpha, bool unused) noexcept {
    ++originalCalls;
    assert(hud != nullptr);
    (void)slot;
    assert(pos.x == 100.0F && pos.y == 50.0F);
    assert(size > 0.0F);
    assert(alpha >= 0.0F);
    (void)unused;
}

void Reset() {
    originalCalls = 0;
    dispatchCalls = 0;
    lastEvent = {};
}

bool Near(float actual, float expected) noexcept {
    return std::fabs(actual - expected) < 0.0001F;
}

struct Harness {
    alignas(16) std::uint8_t hud[0x400]{};
    alignas(16) std::uint8_t player[0x3000]{};
    alignas(8) std::uint64_t bookImage{};
    Vector pos{100.0F, 50.0F};

    Harness(std::int16_t hudIndex, std::uint32_t slot, std::int32_t item,
            bool book, bool ghost = false) {
        Put<std::uintptr_t>(hud, kPlayerHudPlayerOffset,
                            reinterpret_cast<std::uintptr_t>(player));
        Put<std::int16_t>(hud, kPlayerHudIndexOffset, hudIndex);
        Put<std::uint8_t>(player, kPlayerCoopGhostOffset, ghost ? 1 : 0);
        Put<std::int32_t>(
            player,
            kPlayerActiveItemOffset +
                static_cast<std::uintptr_t>(slot) * kPlayerActiveItemStride,
            item);
        Put<std::uintptr_t>(
            hud, kPlayerHudActiveItemOffset +
                     static_cast<std::uintptr_t>(slot) *
                         kPlayerHudActiveItemStride +
                     kPlayerHudBookImageOffset,
            book ? reinterpret_cast<std::uintptr_t>(&bookImage) : 0);
    }
};

}  // namespace

int main() {
    static_assert(kCallbackId == 1079);
    static_assert(kPlayerHudIndexOffset == 0x10);
    static_assert(kPlayerHudActiveItemOffset == 0x258);
    static_assert(kPlayerHudActiveItemStride == 0x30);
    static_assert(kPlayerHudBookImageOffset == 0x18);
    static_assert(kPlayerActiveItemOffset == 0x1964);
    static_assert(kPlayerActiveItemStride == 0x1c);
    static_assert(kPlayerCoopGhostOffset == 0x284c);
    static_assert(abi::kRenderActiveItemOffset == 0x3a3ed4);
    const RunnerPort port{Listening, Dispatch};

    // Zero listeners must call the original before touching the invalid HUD.
    listen = false;
    Reset();
    RunRenderActiveItem(
        reinterpret_cast<void*>(0x1), 0, Vector{100.0F, 50.0F}, 1.0F, 0.5F,
        false, &Original, port);
    assert(originalCalls == 1 && dispatchCalls == 0);

    listen = true;
    {
        Harness h(0, 0, 321, false);
        Reset();
        expectedPlayer = h.player;
        RunRenderActiveItem(h.hud, 0, h.pos, 2.0F, 0.75F, false, &Original,
                            port);
        assert(originalCalls == 1 && dispatchCalls == 1);
        assert(lastEvent.id == kCallbackId);
        assert(lastEvent.player == expectedPlayer);
        assert(lastEvent.slot == 0 && lastEvent.activeItemId == 321);
        assert(Near(lastEvent.itemPos.x, 100.0F) &&
               Near(lastEvent.itemPos.y, 50.0F));
        assert(Near(lastEvent.chargeBarPos.x, 168.0F) &&
               Near(lastEvent.chargeBarPos.y, 84.0F));
        assert(Near(lastEvent.alpha, 0.75F) && Near(lastEvent.scale, 2.0F));
    }
    {
        Harness h(0, 1, 322, false);
        Reset();
        RunRenderActiveItem(h.hud, 1, h.pos, 2.0F, 0.0F, false, &Original,
                            port);
        assert(dispatchCalls == 1);
        assert(Near(lastEvent.scale, 1.0F));
        assert(Near(lastEvent.chargeBarPos.x, 98.0F) &&
               Near(lastEvent.chargeBarPos.y, 67.0F));
    }
    {
        Harness h(4, 1, 323, false);
        Reset();
        RunRenderActiveItem(h.hud, 1, h.pos, 2.0F, 0.0F, false, &Original,
                            port);
        assert(dispatchCalls == 1);
        assert(Near(lastEvent.chargeBarPos.x, 138.0F) &&
               Near(lastEvent.chargeBarPos.y, 67.0F));
    }
    {
        Harness h(4, 0, 324, false);
        Reset();
        RunRenderActiveItem(h.hud, 0, h.pos, 2.0F, 0.0F, false, &Original,
                            port);
        assert(dispatchCalls == 1);
        assert(Near(lastEvent.chargeBarPos.x, 100.0F) &&
               Near(lastEvent.chargeBarPos.y, 84.0F));
    }
    {
        Harness h(0, 0, 325, true);
        Reset();
        RunRenderActiveItem(h.hud, 0, h.pos, 2.0F, 0.0F, false, &Original,
                            port);
        assert(dispatchCalls == 1);
        assert(Near(lastEvent.itemPos.y, 46.0F));
        assert(Near(lastEvent.chargeBarPos.y, 87.0F));
    }
    {
        Harness h(0, 1, 326, false);
        Reset();
        RunRenderActiveItem(h.hud, 1, h.pos, 2.0F, 0.0F, true, &Original,
                            port);
        assert(dispatchCalls == 1);
        assert(Near(lastEvent.scale, 2.0F));
        assert(Near(lastEvent.chargeBarPos.x, 96.0F) &&
               Near(lastEvent.chargeBarPos.y, 84.0F));
    }
    {
        Harness h(0, 0, 327, false, true);
        Reset();
        RunRenderActiveItem(h.hud, 0, h.pos, 1.0F, 0.0F, false, &Original,
                            port);
        assert(originalCalls == 1 && dispatchCalls == 0);
    }
    {
        Harness h(0, 0, 328, false);
        Reset();
        RunRenderActiveItem(h.hud, 4, h.pos, 1.0F, 0.0F, false, &Original,
                            port);
        assert(originalCalls == 1 && dispatchCalls == 0);
    }
    Reset();
    RunRenderActiveItem(reinterpret_cast<void*>(0x1), 0,
                        Vector{100.0F, 50.0F}, 1.0F, 0.0F, false, nullptr,
                        port);
    assert(originalCalls == 0 && dispatchCalls == 0);
    return 0;
}
'''


class PlayerHudActiveRunnerTests(unittest.TestCase):
    def setUp(self):
        if not (PRIVATE / "repentogon_playerhud_active_runner.hpp").is_file():
            self.skipTest("assembled private PlayerHUD runner is required")

    def test_runner_transaction_and_derived_offsets(self):
        with tempfile.TemporaryDirectory(prefix="playerhud-active-") as tmp:
            folder = Path(tmp)
            driver = folder / "driver.cpp"
            driver.write_text(DRIVER)
            result = subprocess.run(
                [shutil.which("c++"), "-std=c++20", "-Wall", "-Wextra", "-Werror",
                 f"-I{SOURCE}", f"-I{UNITS}", f"-I{PRIVATE}", str(driver),
                 str(RUNNER), "-o", str(folder / "driver")],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            result = subprocess.run([str(folder / "driver")],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)

    @unittest.skipUnless(NRO.is_file(), "user-provided Switch NRO is not present")
    def test_binding_guard_matches_pinned_nro(self):
        text = (PRIVATE / "repentogon_playerhud_active_runner.hpp").read_text()
        self.assertIn("kRenderActiveItemOffset = 0x3a3ed4", text)
        expected = bytes.fromhex(
            "ef 3b b6 6d ed 33 01 6d eb 2b 02 6d e9 23 03 6d"
        )
        data = NRO.read_bytes()
        self.assertEqual(data[0x3a3ed4:0x3a3ed4 + len(expected)], expected)


if __name__ == "__main__":
    unittest.main()
