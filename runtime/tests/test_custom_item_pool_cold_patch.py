"""Cold patch images preserve original GetCollectible pool lookup until runtime install."""

import struct
import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import custom_item_pool_cold  # noqa: E402


def word(image: bytes, offset: int) -> int:
    return struct.unpack_from("<I", image, offset)[0]


def branch_target(offset: int, instruction: int) -> int:
    displacement = instruction & 0x03FFFFFF
    if displacement & (1 << 25):
        displacement -= 1 << 26
    return offset + displacement * 4


class CustomItemPoolColdPatchTests(unittest.TestCase):
    def test_pointer_slots_support_atomic_publication(self):
        for site in custom_item_pool_cold.SITES:
            self.assertEqual(site.slot % 8, 0, site.name)
            with self.assertRaises(ValueError):
                custom_item_pool_cold.gate_image(replace(site, slot=site.slot + 4))

    def make_nro(self) -> bytearray:
        nro = bytearray(0x68D000)
        nro[0x40:0x60] = custom_item_pool_cold.BUILD_ID
        for site in custom_item_pool_cold.SITES:
            struct.pack_into("<I", nro, site.source, site.original)
            for address in (site.gate, site.fallback, site.slot):
                struct.pack_into("<I", nro, address - 4, 0xD65F03C0)
        return nro

    def test_each_pool_lookup_site_has_a_null_safe_replay_path(self):
        nro = self.make_nro()
        records = dict(custom_item_pool_cold.cold_records(nro))
        for site in custom_item_pool_cold.SITES:
            source = records[site.source]
            self.assertEqual(branch_target(site.source, word(source, 0)), site.gate)

            gate = records[site.gate]
            self.assertEqual(word(gate, 0) & 0xFF000000, 0x58000000)  # ldr x16
            self.assertEqual(word(gate, 4) & 0xFF000000, 0xB4000000)  # cbz replay
            self.assertEqual(word(gate, 8), 0xD61F0200)        # br x16

            fallback = records[site.fallback]
            self.assertEqual(word(fallback, 0), site.original)
            self.assertEqual(
                branch_target(site.fallback + 4, word(fallback, 4)),
                site.source + 4,
            )
            self.assertEqual(records[site.slot], bytes(8))

    def test_wrong_source_word_is_rejected(self):
        nro = self.make_nro()
        struct.pack_into("<I", nro, custom_item_pool_cold.SITES[0].source, 0)
        with self.assertRaises(ValueError):
            custom_item_pool_cold.cold_records(nro)


if __name__ == "__main__":
    unittest.main()
