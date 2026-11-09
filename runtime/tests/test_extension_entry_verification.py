"""Registered extension hooks preserve strict engine-entry validation."""
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DRIVER = r'''
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
using namespace isaac::runtime;
static std::array<std::uint8_t,16> original{}, hooked{};
static std::uintptr_t site{};
static unsigned checks{};
static bool Readable(std::uintptr_t p,std::size_t n) {return p==site&&n==16;}
static bool Verify(std::uintptr_t p,const std::uint8_t* expected,std::size_t n,engine_call::ReadableCheck read) noexcept {
 ++checks;
 return p==site&&n==16&&read(p,n)&&std::memcmp(expected,original.data(),16)==0&&std::memcmp(engine_memory::AsObject(p),hooked.data(),16)==0;
}
int main() {
 original.fill(1);hooked.fill(2);
 auto image=hooked;site=engine_memory::AddressOf(image.data());
 assert(!engine_call::VerifyEntryBytes(site,original.data(),16,Readable));
 engine_call::SetInstalledEntryVerifier(Verify);
 assert(engine_call::VerifyEntryBytes(site,original.data(),16,Readable));
 std::uintptr_t resolved{};
 assert(engine_call::ResolveEntryAddress(site,16,0,original,&resolved,Readable)&&resolved==site);
 auto other=original;other[3]^=1;
 assert(!engine_call::VerifyEntryBytes(site,other.data(),16,Readable));
 assert(!engine_call::VerifyEntryBytes(site,original.data(),16,+[](std::uintptr_t,std::size_t){return false;}));
 image[5]^=1;assert(!engine_call::VerifyEntryBytes(site,original.data(),16,Readable));
 image=original;const auto before=checks;
 assert(engine_call::VerifyEntryBytes(site,original.data(),16,Readable));assert(checks==before);
 engine_call::SetInstalledEntryVerifier(nullptr);image=hooked;
 assert(!engine_call::VerifyEntryBytes(site,original.data(),16,Readable));
}
'''
class ExtensionEntryTests(unittest.TestCase):
    def test_original_or_explicitly_registered_complete_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);source=folder/'test.cpp';source.write_text(DRIVER)
            binary=folder/'test'
            subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'src'),str(source),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
