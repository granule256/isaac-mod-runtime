"""StatHUD cold branches retain vanilla conditions until runtime publication."""
import struct
import unittest
from tools import cold_static_callbacks as cold

SITES=((0x3af298,0x68cf60,0x60c704,0x54ffff40),
       (0x3af558,0x68cf78,0x60c724,0x54ffff43))

def run(image,source,z,c):
    pc=source;x16=0
    stops={source-24,source+4,0x900000}
    for _ in range(16):
        if pc in stops and pc!=source:return pc
        word=struct.unpack_from('<I',image,pc)[0]
        if word&0xfc000000==0x14000000:
            delta=word&0x3ffffff
            if delta&(1<<25):delta-=1<<26
            pc+=delta*4
        elif word&0xff000000==0x58000000:
            delta=(word>>5)&0x7ffff
            if delta&(1<<18):delta-=1<<19
            x16=struct.unpack_from('<Q',image,pc+delta*4)[0];pc+=4
        elif word&0xff000000==0xb4000000:
            delta=(word>>5)&0x7ffff
            if delta&(1<<18):delta-=1<<19
            pc=pc+delta*4 if x16==0 else pc+4
        elif word&0xff000010==0x54000000:
            cond=word&15;take={0:z,1:not z,2:c,3:not c}[cond]
            delta=(word>>5)&0x7ffff
            if delta&(1<<18):delta-=1<<19
            pc=pc+delta*4 if take else pc+4
        elif word==0xd61f0200:pc=x16
        else:raise AssertionError(hex(word))
    raise AssertionError('cold gate did not resume')

class StatHudColdPatchTests(unittest.TestCase):
    def image(self):
        image=bytearray(0x68d000);image[0x40:0x60]=cold.BUILD_ID
        for source,_,_,original in SITES:struct.pack_into('<I',image,source,original)
        return image

    def test_null_slot_replays_both_original_predicates(self):
        image=self.image()
        self.assertTrue(hasattr(cold,'stat_hud_conditional_records'))
        records=cold.stat_hud_conditional_records(bytes(image))
        for offset,payload in records:image[offset:offset+len(payload)]=payload
        for source,gate,_,original in SITES:
            for z in (False,True):
                for c in (False,True):
                    taken=z if original&15==0 else not c
                    self.assertEqual(run(image,source,z,c),source-24 if taken else source+4)
            struct.pack_into('<Q',image,gate+16,0x900000)
            for z in (False,True):
                for c in (False,True):self.assertEqual(run(image,source,z,c),0x900000)

    def test_fixed_build_and_all_caves_guarded(self):
        self.assertTrue(hasattr(cold,'stat_hud_conditional_records'))
        image=self.image()
        for source,gate,fallback,_ in SITES:
            for offset in (source,gate,gate+16,fallback):
                image[offset]^=1
                with self.assertRaises(ValueError):cold.stat_hud_conditional_records(bytes(image))
                image[offset]^=1
        image[0x40]^=1
        with self.assertRaises(ValueError):cold.stat_hud_conditional_records(bytes(image))
