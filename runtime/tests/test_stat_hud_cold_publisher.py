"""Production StatHUD publication only changes its guarded 64-bit pointer."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_cold_internal_publisher import SHIM
ROOT=Path(__file__).resolve().parents[2]
DRIVER=r'''
#include "relay/internal_hook.hpp"
#include <array>
#include <cassert>
#include <cstring>
#include <cstdlib>
using namespace isaac::runtime::relay;
extern "C" void isaac_internal_hook_context(){}
alignas(4096)static std::array<unsigned char,4096> image{};
int main(int argc,char**argv){
 assert(argc==2);auto original=static_cast<std::uint32_t>(std::strtoul(argv[1],nullptr,0));
 const auto base=reinterpret_cast<std::uintptr_t>(image.data());
 ColdInternalHookSite site{base+64,base+128,original};
 std::array<std::uint8_t,24> gate{};std::array<std::uint8_t,12> replay{};
 assert(BuildStatHudColdImages(site,base+192,gate.data(),replay.data()));
 std::memcpy(image.data()+128,gate.data(),gate.size());
 std::memcpy(image.data()+192,replay.data(),replay.size());
 std::uint32_t jump{};assert(BuildInternalBranch(&jump,site.source,site.gate));
 std::memcpy(image.data()+64,&jump,4);
 InternalHookBinding binding{};
 binding.callback=+[](InternalHookContext&,const void*)noexcept->std::uint32_t{return 0;};
 binding.scratch=InternalScratchPolicy::ProvedDeadX16;
 binding.resumes[0]=site.source+4;binding.resumes[1]=site.source-24;
 binding.resumeCount=original==0x54ffff40?2:3;
 if(binding.resumeCount==3)binding.resumes[2]=site.source+32;
 const auto before=image;
 for(unsigned offset:{64u,128u,132u,136u,140u,192u,196u,200u}){
  image[offset]^=1;
  assert(TryInstallStatHudColdHook(binding,site,base+192)==InternalHookFailure::GuardMismatch);
  image[offset]^=1;
 }
 assert(TryInstallStatHudColdHook(binding,site,base+192)==InternalHookFailure::None);
 std::uintptr_t value{};std::memcpy(&value,image.data()+144,8);assert(value);
 assert(!std::memcmp(before.data(),image.data(),144));
 assert(!std::memcmp(before.data()+152,image.data()+152,image.size()-152));
 assert(TryInstallStatHudColdHook(binding,site,base+192)==InternalHookFailure::VeneerNotEmpty);
}
'''
class StatHudColdPublisherTests(unittest.TestCase):
 def test_guarded_slot_only_publication(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'lib/util/sys').mkdir(parents=True)
   (p/'lib/util/sys/jit.hpp').write_text(SHIM);(p/'test.cpp').write_text(DRIVER)
   result=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror',
    '-I',tmp,'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),
    str(p/'test.cpp'),str(ROOT/'runtime/source/relay/internal_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   for original in ('0x54ffff40','0x54ffff43'):
    result=subprocess.run([str(p/'test'),original],capture_output=True,text=True)
    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
