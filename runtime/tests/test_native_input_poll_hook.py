"""The native Poll GOT hook publishes input only after original Poll returns."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "runtime/src/infrastructure/gotslot/input_poll_pointer_hook.cpp"
DRIVER = r'''
#include "input_poll_pointer_hook.cpp"
#include <cassert>
#include <vector>
using namespace isaac::runtime;
namespace poll=input_poll;
int phase{};
void* expectedManager{};
void Original(void* manager) {assert(manager==expectedManager && phase==0);phase=1;}
namespace isaac::runtime {
void NativeFrameClock::CompleteInputPoll() noexcept {assert(phase==1);phase=2;}
}
int main() {
    static_assert(IsRequired(HookId::NativeInputPoll));
    static_assert(BackendOf(HookId::NativeInputPoll)==HookBackend::GotSlot);
    std::vector<unsigned char> image(0xab0000);
    auto base=reinterpret_cast<std::uintptr_t>(image.data());
    std::memcpy(image.data()+poll::kPollOffset,poll::kPollBytes.data(),poll::kPollBytes.size());
    std::memcpy(image.data()+poll::kPltOffset,poll::kPltBytes.data(),poll::kPltBytes.size());
    auto put=[&](std::uintptr_t address){std::memcpy(image.data()+poll::kGotOffset,&address,8);};
    auto got=[&](){std::uintptr_t address{};std::memcpy(&address,image.data()+poll::kGotOffset,8);return address;};
    HookTarget target{};target.base=base;target.codeSize=0x68d000;
    target.imageSize=image.size();target.buildId=kTargetBuildId;
    put(base+kPltResolverOffset);
    for(auto offset:{poll::kPollOffset,poll::kPltOffset})for(unsigned byte=0;byte<16;++byte) {
        image[offset+byte]^=1;
        assert(!InstallNativeInputPollHook(target).ok());
        assert(got()==base+kPltResolverOffset);
        image[offset+byte]^=1;
    }
    auto bad=target;bad.buildId[0]^=1;assert(!InstallNativeInputPollHook(bad).ok());
    bad=target;bad.imageSize=poll::kGotOffset+7;assert(!InstallNativeInputPollHook(bad).ok());
    put(123);assert(!InstallNativeInputPollHook(target).ok());
    put(base+poll::kPollOffset);assert(InstallNativeInputPollHook(target).ok());
    assert(got()==engine_call::AddressOfFunction(&IsaacModRuntime_NativeInputPollIntercept));
    assert(s_InputPollOriginal.load(std::memory_order_acquire)==base+poll::kPollOffset);
    assert(!InstallNativeInputPollHook(target).ok());
    expectedManager=image.data();
    s_InputPollOriginal.store(engine_call::AddressOfFunction(&Original),std::memory_order_release);
    engine_call::AsFunction<NativeInputPollFn>(got())(expectedManager);
    assert(phase==2);
    s_InputPollOriginal.store(base+poll::kPollOffset,std::memory_order_release);
    put(base+kPltResolverOffset);assert(InstallNativeInputPollHook(target).ok());
    assert(got()==engine_call::AddressOfFunction(&IsaacModRuntime_NativeInputPollIntercept));
}
'''


class NativeInputPollHookTests(unittest.TestCase):
    def test_required_route(self):
        catalog = (ROOT / "runtime/src/domain/runtime/hook_catalog.hpp").read_text()
        self.assertRegex(catalog, r'HookId::NativeInputPoll,\s*"NativeInputPoll",\s*HookBackend::GotSlot,\s*true')
        adapter = (ROOT / "runtime/src/infrastructure/gotslot/got_slot_hook_adapter.cpp").read_text()
        self.assertIn("HookId::NativeInputPoll", adapter)
        self.assertIn("InstallNativeInputPollHook(target)", adapter)

    def test_real_callback_order_and_guarded_got_install(self):
        self.assertTrue(HOOK.is_file(), "native Poll return hook must exist")
        with tempfile.TemporaryDirectory(prefix="isaac-native-poll-") as directory:
            path = Path(directory)
            shim = path / "lib/util/sys/rw_pages.hpp"
            shim.parent.mkdir(parents=True)
            shim.write_text("""#pragma once
#include <cstdint>
#include <cstddef>
namespace exl::util {struct RwPages {std::uintptr_t address;
RwPages(std::uintptr_t p,std::size_t):address(p){}
std::uintptr_t GetRw()const{return address;}void Flush(){}};}
""")
            (path / "test.cpp").write_text(DRIVER)
            binary = path / "test"
            result = subprocess.run([
                "c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                "-I" + str(path), "-I" + str(HOOK.parent),
                "-I" + str(ROOT / "runtime/source"), "-I" + str(ROOT / "runtime/src"),
                str(path / "test.cpp"), "-o", str(binary),
            ], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
