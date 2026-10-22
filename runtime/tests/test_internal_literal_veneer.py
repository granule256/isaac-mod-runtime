"""8B近桩通过独立文字池跨越任意ASLR距离，不覆盖近桩之后的中继。"""
import unittest
from .test_clear_award_internal_adapter import helper
DRIVER=r'''
#include "relay/internal_hook.hpp"
#include <cassert>
#include <cstring>
using namespace isaac::runtime::relay;
int main(){unsigned char bytes[16];std::memset(bytes,0xA5,sizeof(bytes));
 const std::uintptr_t near=0x6ac8ac8db8ULL,slot=0x6ac8ac8d68ULL,far=0x37bed91000ULL;
 assert(BuildInternalLiteralVeneer(bytes,near,slot));
 unsigned word{},branch{},sentinel{};std::memcpy(&word,bytes,4);std::memcpy(&branch,bytes+4,4);std::memcpy(&sentinel,bytes+8,4);
 assert((word&0xff00001fU)==0x58000010U&&branch==0xd61f0200U&&sentinel==0xa5a5a5a5U);
 int imm=static_cast<int>((word>>5)&0x7ffffU);if(imm&0x40000)imm-=0x80000;
 assert(near+static_cast<std::int64_t>(imm)*4==slot);
 assert(!BuildInternalLiteralVeneer(bytes,near,near+0x100000));
 assert(!BuildInternalLiteralVeneer(bytes,near,slot+1));
 assert(!BuildInternalLiteralVeneer(bytes,near,near));
 assert(!BuildInternalLiteralVeneer(bytes,near,near+4));
 assert(BuildInternalLiteralVeneer(bytes,near,near-0x100000));
 assert(!BuildInternalPageVeneer(bytes,near,far));
}
'''
class InternalLiteralVeneerTests(unittest.TestCase):
 def test_far_target_via_near_pointer_slot(self):helper.InternalHookAdapterTests().compile_run(DRIVER,[])

 def test_real_publisher_touches_only_source_code_and_pointer(self):
  import subprocess,tempfile
  from pathlib import Path
  from .test_cold_internal_publisher import SHIM,ROOT
  source=r'''
#include "relay/internal_hook.hpp"
#include <array>
#include <cassert>
#include <cstring>
using namespace isaac::runtime::relay;
extern "C" void isaac_internal_hook_context(){}
alignas(4096)std::array<unsigned char,4096> image{};
int main(){auto base=reinterpret_cast<std::uintptr_t>(image.data());
 auto source=base+64,near=base+128,slot=base+256;
 unsigned original=0x940864d2;std::memcpy(image.data()+64,&original,4);
 InternalHookSite site{source,original,InternalVeneerKind::Literal8,slot};
 InternalHookBinding b{};b.callback=+[](InternalHookContext&,const void*)noexcept->unsigned{return 0;};b.resumes[0]=source+4;b.resumeCount=1;b.scratch=InternalScratchPolicy::ProvedDeadX16;
 auto before=image;auto bad=site;bad.literalSlot=source;assert(TryInstallInternalHook(b,bad,near)==InternalHookFailure::InvalidPlan);
 image[128]=1;assert(TryInstallInternalHook(b,site,near)==InternalHookFailure::VeneerNotEmpty);image=before;
 image[256]=1;assert(TryInstallInternalHook(b,site,near)==InternalHookFailure::VeneerNotEmpty);image=before;
 image[64]^=1;assert(TryInstallInternalHook(b,site,near)==InternalHookFailure::GuardMismatch);image=before;
 assert(TryInstallInternalHook(b,site,near)==InternalHookFailure::None);
 unsigned branch{};assert(BuildInternalBranch(&branch,source,near));assert(!std::memcmp(&branch,image.data()+64,4));
 unsigned char code[8];assert(BuildInternalLiteralVeneer(code,near,slot));assert(!std::memcmp(code,image.data()+128,8));
 std::uintptr_t gateway{};std::memcpy(&gateway,image.data()+256,8);assert(gateway!=0);
 for(unsigned i=0;i<4096;++i)if(!(64<=i&&i<68)&&!(128<=i&&i<136)&&!(256<=i&&i<264))assert(image[i]==before[i]);
 assert(TryInstallInternalHook(b,site,near)==InternalHookFailure::GuardMismatch);
}
'''
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp);(p/'lib/util/sys').mkdir(parents=True);(p/'lib/util/sys/jit.hpp').write_text(SHIM);(p/'test.cpp').write_text(source)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/source/relay/internal_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
