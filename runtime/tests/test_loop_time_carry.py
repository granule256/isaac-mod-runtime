"""Replay the original loop decisions using the instruction in the generated IPS."""
import importlib
import math
import os
from pathlib import Path
import unittest

from tools.nro_ips import apply_records, decode_ips
from tools import build_patches

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = Path(os.environ.get('ISAAC_SOURCE_ROOT', ROOT))
SITE = 0x4C08F4
FMOV = 0x4EAA1D49
FMAX = 0x1E6A4929  # Independently assembled by clang and decoded by llvm-objdump.


def replay(word, duration=60, workload=None, pause=None, scene=2, stall=None):
    """4C0948..4C0A64: sample, add 1/60, update, skip decision, render, anchor."""
    assert word in (FMOV, FMAX)
    now = anchor = 0.0
    steps = renders = skipped = max_skipped = world = 0
    while now < duration:
        if stall and steps == stall[0]:
            now += stall[1]
        sample = now
        anchor += 1 / 60
        update, render = workload(steps) if workload else (.001, 1 / 60 - .001)
        if steps % 2 == 0 and not (pause and pause[0] <= sample < pause[1]):
            world += 1
        now += update
        steps += 1
        if skipped > 3 or sample - anchor < .002 or scene == 3:
            now += render
            renders += 1
            max_skipped = max(max_skipped, skipped)
            skipped = 0
            anchor = sample if word == FMOV else max(anchor, sample)
        else:
            skipped += 1
    return dict(speed=steps / 60 / now, steps=steps, seconds=now,
                world_seconds=world / 30, renders=renders, max_skipped=max_skipped)


class LoopTimeCarryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = next(SOURCE_ROOT.glob('The Binding*Afterbirth*/*/1/.nro/Repentance.nro')).read_bytes()

    def patch_module(self):
        self.assertIsNotNone(importlib.util.find_spec('runtime.game_patches'),
                             'original-game patches need their own source package')
        return importlib.import_module('runtime.game_patches.loop_time_carry')

    def patched_word(self):
        module = self.patch_module()
        patch = module.build_loop_time_carry_patch(self.source)
        image = apply_records(self.source, decode_ips(patch))
        return int.from_bytes(image[SITE:SITE + 4], 'little')

    def test_normal_sixty_step_cadence_is_preserved(self):
        before = replay(FMOV)
        after = replay(self.patched_word())
        self.assertEqual(before, after)
        self.assertAlmostEqual(after['speed'], 1, places=9)

    def test_sustained_overload_does_not_compound_early_updates(self):
        workload = lambda _: (.003, .017)
        before = replay(FMOV, workload=workload)
        after = replay(self.patched_word(), workload=workload)
        self.assertGreater(before['speed'], 1.3, 'original acceleration no longer reproduced')
        self.assertLess(after['speed'], 1.001)
        self.assertGreater(after['speed'], .98)

    def test_intermittent_load_and_render_tolerance(self):
        def workload(step):
            return (.003, .017) if step % 200 < 80 else (.001, 1 / 60 - .001)
        before = replay(FMOV, duration=180, workload=workload)
        after = replay(self.patched_word(), duration=180, workload=workload)
        self.assertGreater(before['speed'], 1.05)
        self.assertLess(after['speed'], 1.001)
        self.assertGreater(after['speed'], .98)

    def test_long_suspend_keeps_original_bounded_recovery(self):
        result = replay(self.patched_word(), duration=65, stall=(200, 30))
        self.assertLessEqual(result['max_skipped'], 4)
        # The original policy discards remaining late time at a render; no 1800-step catch-up.
        self.assertLess(result['steps'], 36 * 60)

    def test_pause_stops_world_and_cutscene_keeps_rendering(self):
        result = replay(self.patched_word(), duration=10, pause=(3, 7))
        self.assertAlmostEqual(result['world_seconds'], 6, delta=1 / 30)
        workload = lambda _: (.003, .017)
        before = replay(FMOV, scene=3, workload=workload)
        after = replay(self.patched_word(), scene=3, workload=workload)
        self.assertEqual(before, after)
        self.assertEqual(after['steps'], after['renders'])

    def test_exact_single_instruction_and_all_other_bytes_preserved(self):
        module = self.patch_module()
        blob = module.build_loop_time_carry_patch(self.source)
        self.assertEqual(len(blob), 17)
        records = decode_ips(blob)
        self.assertEqual(records, [(SITE, FMAX.to_bytes(4, 'little'))])
        patched = apply_records(self.source, records)
        self.assertEqual(patched[:SITE], self.source[:SITE])
        self.assertEqual(patched[SITE + 4:], self.source[SITE + 4:])

    def test_wrong_build_and_modified_source_are_rejected(self):
        module = self.patch_module()
        for offset in (0x40, 0x4C08B8, SITE, 0x4C09E4, 0x4C0A64, 0x500):
            with self.subTest(offset=hex(offset)):
                image = bytearray(self.source)
                image[offset] ^= 1
                with self.assertRaises(ValueError):
                    module.build_loop_time_carry_patch(bytes(image))

    def test_lifecycle_output_contains_only_compatibility_relays(self):
        records = decode_ips(build_patches.build_game_start_lifecycle_relay_patch(self.source))
        original = build_patches.GAME_START_LIFECYCLE_RELAY_RECORDS
        self.assertEqual(records, original,
                         'an independent game optimization leaked into a compatibility relay')


if __name__ == '__main__':
    unittest.main()
