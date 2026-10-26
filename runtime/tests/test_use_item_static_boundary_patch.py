"""五条主动道具路径的加载前中继和完整函数版本校验。"""
from pathlib import Path
import struct,sys,tempfile,subprocess,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import cold_static_callbacks as patches
SITES=((0x30a19c,0x68ce60,0xb9595b69),(0x30c728,0x68ce80,0xb9595b69),(0x317318,0x68cea0,0xb9595b69),(0x31a80c,0x68cec0,0xb94056e8),(0x31a92c,0x68cee0,0xb94056e8))
def records(blob):
 out={};i=5
 while blob[i:i+3]!=b'EOF':
  o=int.from_bytes(blob[i:i+3],'big');n=int.from_bytes(blob[i+3:i+5],'big');assert n;i+=5;out[o]=blob[i:i+n];i+=n
 return out
class UseItemStaticPatchTests(unittest.TestCase):
 def test_all_five_native_paths_have_null_safe_gates(self):
  nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding*Afterbirth*/*/1/.nro/Repentance.nro')).read_bytes();r=records(patches.build_static_callback_patch(nro))
  for source,gate,original in SITES:
   with self.subTest(site=hex(source)):
    self.assertEqual(r.get(source),struct.pack('<I',patches.branch(source,gate)))
    self.assertEqual(r.get(gate),patches.gate_image(source,gate,original))
    words=struct.unpack('<6IQ',r[gate]);self.assertEqual(words[-1],0);self.assertEqual(words[2],0xb4000050);self.assertEqual(words[4],original)

 def test_actual_installer_full_function_guard_and_publication_failure(self):
  nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding*Afterbirth*/*/1/.nro/Repentance.nro')).read_bytes();image=bytearray(nro)
  for offset,data in records(patches.build_static_callback_patch(nro)).items():image[offset:offset+len(data)]=data
  source=r'''
#include "infrastructure/internal/use_item_hook_installer.hpp"
#include "use_item_boundary_layout.hpp"
#include "use_item_internal_hook.hpp"
#include <fstream>
#include <iterator>
#include <vector>
#include <cassert>
using namespace isaac::runtime;
unsigned publishes{},failAt{};
namespace isaac::runtime {
std::uint32_t UseItemNativeBoundaryCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
std::uint32_t UseItemAnimationEventCallback(relay::InternalHookContext&,const void*)noexcept{return 0;}
namespace relay {
InternalHookFailure TryInstallPreinstalledInternalHook(const InternalHookBinding& b,const ColdInternalHookSite& s){
 const auto& expected=use_item_boundary::kSites[publishes++];
 assert(s.source==g_UseItemBoundaryInstallState.base+expected.source&&s.gate==g_UseItemBoundaryInstallState.base+expected.gate&&s.original==expected.original);
 assert(b.callback==UseItemNativeBoundaryCallback&&b.resumeCount==1&&b.resumes[0]==s.gate+16&&b.scratch==InternalScratchPolicy::ProvedDeadX16);
 assert(static_cast<const UseItemNativeBoundaryBinding*>(b.user)->defaultDischarge==expected.defaultDischarge);
 assert(static_cast<const UseItemNativeBoundaryBinding*>(b.user)->reloadCacheFlags==(expected.source==0x317318));
 return publishes==failAt?InternalHookFailure::WriteVerifyFailed:InternalHookFailure::None;
 }
InternalHookFailure TryInstallInternalHook(const InternalHookBinding& b,const InternalHookSite& s,std::uintptr_t veneer){
 const auto i=publishes++-5;assert(i<2);const auto& expected=use_item_boundary::kAnimationSites[i];const auto base=g_UseItemBoundaryInstallState.base;
 assert(s.target==base+expected.source&&s.expected==expected.original&&s.veneerKind==InternalVeneerKind::Absolute16&&veneer==base+expected.veneer);
 assert(b.callback==UseItemAnimationEventCallback&&b.resumeCount==1&&b.resumes[0]==s.target+4&&b.scratch==InternalScratchPolicy::ProvedDeadX16);
 const auto& view=*static_cast<const UseItemAnimationEventBinding*>(b.user);
 assert(view.original==base+expected.plt&&view.resume==s.target+4&&view.event==(i==0?UseItemAnimationEvent::TammyLaser:UseItemAnimationEvent::FlipReplace));
 return publishes==failAt?InternalHookFailure::WriteVerifyFailed:InternalHookFailure::None;
}
}
}
int main(int argc,char**argv){assert(argc==3);std::ifstream f(argv[1],std::ios::binary);std::vector<std::uint8_t> image((std::istreambuf_iterator<char>(f)),{});using namespace use_item_boundary;
 assert(ImageMatches(image.data(),image.size()));assert(!ImageMatches(image.data(),0x68ceff));assert(!ImageMatches(nullptr,image.size()));
 std::vector<std::uintptr_t> mutations={0x40,kFunction,kFunction+0x8400,kFunction+kLength-1};
 for(const auto& site:kSites)for(auto off:{site.source,site.source+4,site.gate,site.gate+4,site.gate+8,site.gate+12,site.gate+16,site.gate+20})mutations.push_back(off);
 for(const auto& site:kAnimationSites)for(unsigned i=0;i<16;++i){mutations.push_back(site.veneer+i);mutations.push_back(site.plt+i);}
 HookTarget target{reinterpret_cast<std::uintptr_t>(image.data()),image.size(),image.size(),kBuildId};
 for(auto at:mutations){image[at]^=1;assert(!ImageMatches(image.data(),image.size()));assert(!TryInstallUseItemNativeBoundaries(target));assert(publishes==0&&g_UseItemBoundaryInstallState.installed==0);image[at]^=1;}
 auto bad=target;bad.buildId[0]^=1;assert(!TryInstallUseItemNativeBoundaries(bad)&&publishes==0);
 bad=target;bad.codeSize=0x68ceff;assert(!TryInstallUseItemNativeBoundaries(bad)&&publishes==0);
 failAt=static_cast<unsigned>(std::stoul(argv[2]));g_UseItemBoundaryInstallState={};
 assert(TryInstallUseItemNativeBoundaries(target)==(failAt==0));
 assert(publishes==(failAt?failAt:7));assert(g_UseItemBoundaryInstallState.installed==(failAt?failAt-1:7));
 auto before=publishes;assert(TryInstallUseItemNativeBoundaries(target)==(failAt==0));assert(publishes==before);
 if(!failAt){++target.base;assert(!TryInstallUseItemNativeBoundaries(target));}
}
'''
  with tempfile.TemporaryDirectory(prefix='use-boundary-install-')as tmp:
   p=Path(tmp);(p/'image').write_bytes(image);(p/'test.cpp').write_text(source)
   r=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/src/infrastructure/internal/use_item_hook_installer.cpp'),'-o',str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   for failure in range(8):
    with self.subTest(failure=failure):
     r=subprocess.run([str(p/'test'),str(p/'image'),str(failure)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
