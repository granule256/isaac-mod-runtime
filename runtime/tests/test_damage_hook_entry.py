"""伤害API必须接受自己已验证安装的入口中继，且拒绝篡改的中继。"""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DRIVER = r'''
#include "interfaces/lua/hooked_engine_entry.hpp"
#include "relay/entry_relay.hpp"
#include <array>
#include <cstring>
using namespace isaac::runtime;
bool readable(std::uintptr_t a, std::size_t n) { return a != 0 && n <= 64; }
int main() {
    std::array<std::uint8_t,16> original{};
    original[0]=0xff; original[1]=0xc3; original[2]=7; original[3]=0xd1;
    alignas(8) std::array<std::uint8_t,16> target=original;
    alignas(8) std::array<std::uint8_t,64> slot{};
    auto a=reinterpret_cast<std::uintptr_t>(target.data());
    auto s=reinterpret_cast<std::uintptr_t>(slot.data());
    auto valid=[&](bool installed) {return VerifiedHookedEngineEntry(a, original, installed,
                                 s+relay::kSlotFallbackOffset, readable);};
    if (!valid(false)) return 1;
    relay::BuildSlotImage(slot.data(),a,original.data(),0x1234);
    relay::BuildEntryPatch(target.data(),s);
    if (!valid(true)) return 2;
    if (valid(false)) return 3;
    target[8]^=1; if (valid(true)) return 4; target[8]^=1;
    slot[relay::kSlotFallbackOffset+8]^=1; if (valid(true)) return 5;
    slot[relay::kSlotFallbackOffset+8]^=1;
    slot[relay::kSlotFallbackTargetOffset]^=1; if (valid(true)) return 6;
    return 0;
}
'''

class DamageHookEntryTests(unittest.TestCase):
    def test_original_and_owned_relay_and_corruptions(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d);(p/'test.cpp').write_text(DRIVER)
            b=subprocess.run(['c++','-std=c++20','-I',str(ROOT/'runtime/source'),
                              '-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),'-o',str(p/'test')],
                             capture_output=True,text=True)
            self.assertEqual(b.returncode,0,b.stderr)
            r=subprocess.run([str(p/'test')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,'失败场景编号 '+str(r.returncode))
