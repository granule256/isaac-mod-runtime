import struct
import unittest
from runtime.tools.patch_npdm import grant_sd_access


class SdPermissionTests(unittest.TestCase):
    def test_only_both_sd_permission_bits_change(self):
        data = bytearray(0x600)
        data[:4] = b'META'
        struct.pack_into('<4I', data, 0x70, 0x480, 0x180, 0x80, 0x400)
        data[0x480:0x484] = b'ACI0'
        data[0x280:0x284] = b'ACID'
        struct.pack_into('<II', data, 0x4a0, 0x40, 0x20)
        struct.pack_into('<II', data, 0x2a0, 0x240, 0x20)
        struct.pack_into('<Q', data, 0x4c4, 1 << 62)
        struct.pack_into('<Q', data, 0x2c4, 1 << 62)
        patched, changed = grant_sd_access(bytes(data))
        self.assertEqual({i for i, (a, b) in enumerate(zip(data, patched)) if a != b}, {0x4c6, 0x2c6})
        self.assertEqual(changed, frozenset({0x4c6, 0x2c6}))
        self.assertEqual(len(data), len(patched))
        self.assertEqual(grant_sd_access(patched)[0], patched)

    def test_malformed_blocks_fail_closed(self):
        for data in (b'', b'META' + bytes(0x80)):
            with self.assertRaises(ValueError):
                grant_sd_access(data)
