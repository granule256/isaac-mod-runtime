"""Cold death-check boundary with an ASLR-relative, zero-pointer native fallback."""
import struct

SOURCE = 0x2E55C8
GATE = 0x259874
CALLBACK_GATE = 0x24DDA4
SLOT = 0x249548
ORIGINAL = bytes.fromhex("34010036f4031f2acd00001474190037")


def records(nro):
    from build_patches import encode_branch
    if nro[SOURCE:SOURCE + 16] != ORIGINAL:
        raise ValueError("MGO death phase guard mismatch")
    for address, size in ((GATE, 12), (CALLBACK_GATE, 12), (SLOT, 8)):
        if nro[address:address + size] != bytes(size):
            raise ValueError("MGO death cold cave is occupied")
        previous = struct.unpack_from("<I", nro, address - 4)[0]
        if previous != 0xD65F03C0 and previous & 0xFC000000 != 0x14000000:
            raise ValueError("MGO death cave lacks a RET/B predecessor")
    gate = (struct.pack("<I", 0x36000054) +
            encode_branch(GATE + 4, SOURCE + 4) +
            encode_branch(GATE + 8, CALLBACK_GATE))
    ldr = 0x58000010 | ((((SLOT - CALLBACK_GATE) // 4) & 0x7FFFF) << 5)
    cbz = 0xB4000010 | (((((SOURCE + 0x24) - (CALLBACK_GATE + 4)) // 4)
                         & 0x7FFFF) << 5)
    callback_gate = struct.pack("<III", ldr, cbz, 0xD61F0200)
    return [(SOURCE, encode_branch(SOURCE, GATE)), (GATE, gate),
            (CALLBACK_GATE, callback_gate)]
