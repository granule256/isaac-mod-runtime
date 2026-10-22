"""共享content守卫必须逐个消费地址核对，std::uintptr_t不得漏掉。"""
import unittest
from tools.verify_runtime_constants_against_nro import check
class ContentGuardTests(unittest.TestCase):
 TEXT='''
inline constexpr std::uintptr_t kPlainOffset = 0x30;
inline constexpr std::array<u8, 4> kPlainExpectedBytes = {0x11,0x22,0x33,0x44};
inline constexpr std::array<u8, 4> kSharedExpectedBytes = {0x55,0x66,0x77,0x88};
inline constexpr std::array<ModContentFeedSpec, 2> kModContentFeedSpecs = {{
 {0x10, kSharedExpectedBytes.data(), kSharedExpectedBytes.size(), 0},
 {0x20, kSharedExpectedBytes.data(),
  kSharedExpectedBytes.size(), 0},
}};
'''
 def image(self):
  b=bytearray(0x40);b[0x10:0x14]=b[0x20:0x24]=bytes.fromhex('55667788');b[0x30:0x34]=bytes.fromhex('11223344');return b
 def test_all_shared_consumers_and_qualified_offset_are_checked(self):
  r=check(self.TEXT,bytes(self.image()),patched=set());self.assertEqual(r['checked'],3);self.assertEqual(r['unpaired_arrays'],[]);self.assertEqual(r['failures'],[])
 def test_corrupt_second_shared_consumer_is_rejected(self):
  b=self.image();b[0x20]^=1;r=check(self.TEXT,bytes(b),patched=set());self.assertTrue(r['failures'])
