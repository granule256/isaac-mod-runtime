"""The mandatory cold IPS guards native challenge achievement lookups."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import cold_static_callbacks as cold
from tools.nro_ips import decode_ips


class ChallengeAchievementPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ.get('ISAAC_SOURCE_ROOT', ROOT))
        cls.nro = next(root.glob('The Binding*Afterbirth*/*/1/.nro/Repentance.nro')).read_bytes()

    def test_challenge_guard_is_in_mandatory_cold_ips(self):
        records = decode_ips(cold.build_static_callback_patch(self.nro))
        self.assertEqual([at for at, _ in records if 0x439500 <= at < 0x439654],
                         [0x439598])

    def test_unexpected_lookup_or_continuation_rejects_build(self):
        for site in (0x439594, 0x4395B0, 0x4395C8, 0x43954C):
            with self.subTest(site=hex(site)):
                image = bytearray(self.nro)
                image[site] ^= 1
                with self.assertRaisesRegex(ValueError, 'challenge achievement scan'):
                    cold.build_static_callback_patch(bytes(image))
