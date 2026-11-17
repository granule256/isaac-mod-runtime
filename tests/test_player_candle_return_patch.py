"""The candle return bridge preserves the effect before restoring x20."""
import struct
import unittest
from tools import cold_static_callbacks as cold


class PlayerCandleReturnPatchTests(unittest.TestCase):
    def image(self):
        image = bytearray(0x68D000)
        image[0x40:0x60] = cold.BUILD_ID
        struct.pack_into("<I", image, 0x2F215C, 0xA94C4FF4)
        return image

    def test_effect_result_and_saved_registers_survive_epilogue(self):
        self.assertTrue(hasattr(cold, "player_candle_return_records"),
                        "ShootBlueCandle needs a defined native return value")
        image = self.image()
        for offset, payload in cold.player_candle_return_records(bytes(image)):
            image[offset:offset + len(payload)] = payload
        pc, result, x20, x19 = 0x2F215C, 0xDEAD, 0x12345678, 0x22
        for _ in range(4):
            word = struct.unpack_from("<I", image, pc)[0]
            if word & 0xFC000000 == 0x14000000:
                delta = word & 0x3FFFFFF
                if delta & (1 << 25):
                    delta -= 1 << 26
                pc += delta * 4
            elif word == 0xAA1403E0:
                result = x20
                pc += 4
            elif word == 0xA94C4FF4:
                x20, x19 = 0x33, 0x44
                pc += 4
            else:
                self.fail(f"unexpected bridge instruction {word:#x}")
        self.assertEqual((pc, result, x20, x19),
                         (0x2F2160, 0x12345678, 0x33, 0x44))

    def test_source_build_and_entire_island_are_guarded(self):
        self.assertTrue(hasattr(cold, "player_candle_return_records"))
        for offset in (0x40, 0x2F215C, 0x68CFA0, 0x68CFA4, 0x68CFA8):
            image = self.image()
            image[offset] ^= 1
            with self.assertRaises(ValueError):
                cold.player_candle_return_records(bytes(image))
