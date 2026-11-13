"""Cold indirect BLR gate: image generation, holes and AArch64 semantics."""

import hashlib
import struct
import unittest
from dataclasses import replace
from unittest import mock
from pathlib import Path

from tools import extra_source_cold as cold


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[1]
NRO = (
    PROJECT
    / "data/games/The Binding of Isaac_ Afterbirth+ 1.7.9b "
      "[010021C000B6A800][v524288][UPD]/Program #0/1/.nro/Repentance.nro"
)
EXPECTED_SHA256 = "cc363208c220f65547edda6d8268b3b6c0f7373b14c91ae6ffb378018de4b66a"


def sign_extend(value, bits):
    if value & (1 << (bits - 1)):
        value -= 1 << bits
    return value


def encode_b(source, target):
    delta = target - source
    return 0x14000000 | ((delta >> 2) & 0x3FFFFFF)


def run_until_exit(image, start, x8, initial_lr, stop_after_return):
    pc = start
    x16 = 0
    x30 = initial_lr
    steps = []
    for _ in range(32):
        steps.append((pc, x16, x30))
        word = struct.unpack_from("<I", image, pc)[0]
        if word == 0xD65F03C0:  # ret
            pc = x30
            if stop_after_return(pc):
                return pc, x16, x30, steps
            continue
        if word & 0xFC000000 == 0x14000000:  # b
            pc += sign_extend(word & 0x3FFFFFF, 26) * 4
            continue
        if word & 0xFF000000 == 0x58000000:  # ldr x16, literal
            if (word & 0x1F) != 16:
                raise AssertionError(hex(word))
            delta = sign_extend((word >> 5) & 0x7FFFF, 19) * 4
            x16 = struct.unpack_from("<Q", image, pc + delta)[0]
            pc += 4
            continue
        if word & 0xFF000000 == 0xB4000000:  # cbz x16, label
            if (word & 0x1F) != 16:
                raise AssertionError(hex(word))
            delta = sign_extend((word >> 5) & 0x7FFFF, 19) * 4
            pc = pc + delta if x16 == 0 else pc + 4
            continue
        if word & 0xFFFFFC1F == 0xD61F0000:  # br
            rn = (word >> 5) & 0x1F
            if rn == 8:
                pc = x8
            elif rn == 16:
                pc = x16
            else:
                raise AssertionError(f"br x{rn} at {pc:x}")
            continue
        if word & 0x9F000000 == 0x10000000:  # adr
            rd = word & 0x1F
            imm = (((word >> 5) & 0x7FFFF) << 2) | ((word >> 29) & 3)
            value = pc + sign_extend(imm, 21)
            if rd != 30:
                raise AssertionError(hex(word))
            x30 = value
            pc += 4
            continue
        raise AssertionError(f"unsupported instruction {word:08x} at {pc:x}")
    raise AssertionError("gate did not terminate")


class ExtraSourceColdToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NRO.is_file():
            raise unittest.SkipTest("pinned Repentance NRO is not available")
        cls.image = NRO.read_bytes()

    def test_pinned_laser_metadata_and_holes(self):
        self.assertEqual(hashlib.sha256(self.image).hexdigest(), EXPECTED_SHA256)
        site = cold.LASER_SITE
        self.assertEqual(site.source, 0xFF978)
        self.assertEqual(site.original, 0xD63F0100)
        self.assertEqual(site.target_register, 8)
        self.assertEqual(site.gate, 0xEA894)
        self.assertEqual(site.slot, 0x13E5D8)
        self.assertEqual(site.fallback, 0x12F544)
        self.assertEqual(
            cold.discover_holes(self.image, site.source),
            (site.gate, site.slot, site.fallback),
        )
        for address, length in (
            (site.gate, cold.GATE_BYTES),
            (site.slot, cold.SLOT_BYTES),
            (site.fallback, cold.FALLBACK_BYTES),
        ):
            self.assertEqual(self.image[address : address + length], bytes(length))
            self.assertIn(cold.predecessor_kind(self.image, address), ("ret", "b"))

    def test_cold_records_are_guarded_and_patch_all_three_holes(self):
        self.assertEqual(len(cold.SITES), 7)
        records = cold.cold_records(self.image)
        by_offset = dict(records)
        expected_offsets = set()
        for site in cold.SITES:
            expected_offsets.update((site.source, site.gate, site.fallback))
        self.assertEqual(len(records), 21)
        self.assertEqual(set(by_offset), expected_offsets)
        patched = bytearray(self.image)
        for offset, payload in records:
            patched[offset : offset + len(payload)] = payload
        for site in cold.SITES:
            self.assertEqual(
                struct.unpack_from("<I", patched, site.source)[0],
                encode_b(site.source, site.gate),
            )
            self.assertEqual(
                patched[site.gate : site.gate + cold.GATE_BYTES],
                cold.gate_image(site),
            )
            self.assertEqual(
                patched[site.fallback : site.fallback + cold.FALLBACK_BYTES],
                cold.fallback_image(site),
            )
            self.assertEqual(
                patched[site.slot : site.slot + cold.SLOT_BYTES], bytes(8)
            )

    def test_guard_failure_modes_cover_source_build_and_holes(self):
        for site in cold.SITES:
            for name, offset in (
                ("source", site.source),
                ("gate", site.gate),
                ("slot", site.slot),
                ("fallback", site.fallback),
            ):
                image = bytearray(self.image)
                image[offset] ^= 1
                with self.assertRaises(ValueError, msg=f"{site.name}/{name}"):
                    cold.cold_records(bytes(image))
        image = bytearray(self.image)
        image[0x40] ^= 1
        with self.assertRaises(ValueError):
            cold.cold_records(bytes(image))

    def test_cross_site_slot_collisions_are_rejected(self):
        base = 0x100000
        first = cold.ColdSite(
            name="first",
            source=base,
            original=0xD63F0100,
            target_register=8,
            gate=base + 0x40,
            slot=base + 0x100,
            fallback=base + 0x80,
        )
        for collision in (first.gate, first.fallback, first.slot):
            second = replace(
                first,
                name="second",
                source=base + 4,
                gate=base + 0x140,
                slot=collision,
                fallback=base + 0x180,
            )
            with mock.patch.object(cold, "verify_site", lambda *_: None):
                with self.assertRaises(ValueError):
                    cold.cold_records(b"", (first, second))

    def test_hole_xref_scan_covers_all_21_ranges_and_detects_a_hit(self):
        self.assertEqual(len(cold.SITES) * 3, 21)
        self.assertEqual(cold.scan_hole_xrefs(self.image), [])
        image = bytearray(self.image)
        target = cold.LASER_SITE.gate
        struct.pack_into("<I", image, 0x1000, target)
        hits = cold.scan_hole_xrefs(bytes(image))
        self.assertIn((0x1000, 4, target), hits)

    def test_aarch64_gate_null_slot_preserves_lr_and_uses_x8(self):
        site = cold.LASER_SITE
        image = bytearray(self.image)
        for offset, payload in cold.cold_records(image):
            image[offset : offset + len(payload)] = payload
        struct.pack_into("<Q", image, site.slot, 0)
        callee = 0x500000
        struct.pack_into("<I", image, callee, 0xD65F03C0)
        initial_lr = 0x12345678
        observed = {}

        def stop_after_return(pc):
            if pc == site.source + 4:
                observed["returned"] = True
                return True
            return False

        pc, x16, x30, _ = run_until_exit(
            image, site.source, callee, initial_lr, stop_after_return
        )
        self.assertEqual(pc, site.source + 4)
        self.assertEqual(x30, site.source + 4)
        self.assertEqual(x16, 0)
        self.assertTrue(observed.get("returned"))

    def test_aarch64_gate_nonnull_slot_keeps_original_lr(self):
        site = cold.LASER_SITE
        image = bytearray(self.image)
        for offset, payload in cold.cold_records(image):
            image[offset : offset + len(payload)] = payload
        gateway = 0x600000
        struct.pack_into("<Q", image, site.slot, gateway)
        struct.pack_into("<I", image, gateway, 0xD65F03C0)
        initial_lr = 0x12345678

        pc, x16, x30, _ = run_until_exit(
            image,
            site.source,
            0x500000,
            initial_lr,
            lambda value: value == initial_lr,
        )
        self.assertEqual(pc, initial_lr)
        self.assertEqual(x30, initial_lr)
        self.assertEqual(x16, gateway)

    def test_aarch64_all_seven_gates_keep_blr_contract(self):
        image = bytearray(self.image)
        for offset, payload in cold.cold_records(image):
            image[offset : offset + len(payload)] = payload
        for index, site in enumerate(cold.SITES):
            callee = 0x600000 + index * 0x100
            gateway = 0x610000 + index * 0x100
            struct.pack_into("<I", image, callee, 0xD65F03C0)
            struct.pack_into("<I", image, gateway, 0xD65F03C0)
            struct.pack_into("<Q", image, site.slot, 0)
            pc, x16, x30, _ = run_until_exit(
                image,
                site.source,
                callee,
                0x12345678,
                lambda value, source=site.source: value == source + 4,
            )
            self.assertEqual(pc, site.source + 4)
            self.assertEqual(x30, site.source + 4)
            self.assertEqual(x16, 0)
            struct.pack_into("<Q", image, site.slot, gateway)
            pc, x16, x30, _ = run_until_exit(
                image,
                site.source,
                callee,
                0x12345678,
                lambda value: value == 0x12345678,
            )
            self.assertEqual(pc, 0x12345678)
            self.assertEqual(x30, 0x12345678)
            self.assertEqual(x16, gateway)


if __name__ == "__main__":
    unittest.main()
