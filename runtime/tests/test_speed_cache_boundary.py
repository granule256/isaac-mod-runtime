"""Speed cache dispatch belongs before the native speed clamp, not after EvaluateItems."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import cold_static_callbacks as cold
from .test_player_damage_internal_hook import original_nro
from .test_support import HARNESS_COMPILE_FLAGS, prepare_harness_directory

DRIVER = r'''
#include "cold_callbacks_internal_hook.hpp"
#include "speed_cache_boundary_layout.hpp"
#include "infrastructure/internal/speed_cache_hook_installer.hpp"
#include <cassert>
#include <cstring>
#include <fstream>
#include <iterator>
#include <new>
#include <cstdlib>
#include <vector>
using namespace isaac::runtime;
static bool enabled=true,denyAllocation=false;
static unsigned calls{},installs{};
static bool failInstall{};
static std::uintptr_t playerWant{},base{};
void* operator new(std::size_t n){assert(!denyAllocation);if(auto*p=std::malloc(n))return p;throw std::bad_alloc();}
void operator delete(void*p) noexcept {std::free(p);}
namespace isaac::runtime {bool BuiltinCallbackEnabled(std::uint32_t id) noexcept {assert(id==8);return enabled;}}
namespace LuaRuntime {
std::uint32_t DispatchPostCurseEval(std::uint32_t v){return v;}
void DispatchPostPickupSelection(std::uintptr_t,std::uint32_t*,std::uint32_t*){}
void DispatchEvaluateCache(std::uintptr_t player,std::int32_t flag){
 assert(player==playerWant&&flag==16);++calls;
 float speed=3.4F;std::memcpy(reinterpret_cast<void*>(player+0x194c),&speed,4);
}
}
namespace isaac::runtime::relay {
InternalHookFailure TryInstallPreinstalledInternalHook(const InternalHookBinding& binding,const ColdInternalHookSite& site){
 ++installs;assert(binding.callback==SpeedCacheInternalCallback&&binding.resumeCount==1);
 assert(binding.resumes[0]==base+speed_cache_boundary::kGate+16);
 assert(binding.scratch==InternalScratchPolicy::ProvedDeadX16);
 assert(site.source==base+speed_cache_boundary::kSource&&site.gate==base+speed_cache_boundary::kGate);
 return failInstall ? InternalHookFailure::WriteVerifyFailed : InternalHookFailure::None;
}
}
int main(int argc,char**argv){
 assert(argc==2);std::ifstream in(argv[1],std::ios::binary);
 std::vector<unsigned char> image{std::istreambuf_iterator<char>(in),{}};
 base=reinterpret_cast<std::uintptr_t>(image.data());
 assert(speed_cache_boundary::ImageMatches(image.data(),image.size()));
 const std::uint32_t chargeBranch=speed_cache_boundary::Branch(0x280d0c,0x277744);
 std::uint32_t originalChargeWord{};
 std::memcpy(&originalChargeWord,image.data()+0x280d0c,4);
 std::memcpy(image.data()+0x280d0c,&chargeBranch,4);
 assert(speed_cache_boundary::ImageMatches(image.data(),image.size()));
 image[0x280d0c]^=1;
 assert(!speed_cache_boundary::ImageMatches(image.data(),image.size()));
 std::memcpy(image.data()+0x280d0c,&originalChargeWord,4);
 for(auto at:{std::uintptr_t{0x40},speed_cache_boundary::kFunction,speed_cache_boundary::kSource,
             speed_cache_boundary::kFunction+speed_cache_boundary::kLength-1,speed_cache_boundary::kGate+23}){
  image[at]^=1;assert(!speed_cache_boundary::ImageMatches(image.data(),image.size()));image[at]^=1;
 }
 HookTarget target{};target.base=base;target.codeSize=image.size();target.buildId=speed_cache_boundary::kBuildId;
 auto bad=target;bad.buildId[0]^=1;assert(!TryInstallSpeedCacheBoundary(bad)&&installs==0);
 assert(!speed_cache_boundary::ImageMatches(nullptr,image.size()));
 assert(!speed_cache_boundary::ImageMatches(image.data(),speed_cache_boundary::kGate+31));
 failInstall=true;
 assert(!TryInstallSpeedCacheBoundary(target)&&installs==1);
 assert(g_SpeedCacheBoundaryInstallState.failure==static_cast<unsigned>(relay::InternalHookFailure::WriteVerifyFailed));
 assert(!TryInstallSpeedCacheBoundary(target)&&installs==1);
 g_SpeedCacheBoundaryInstallState={};failInstall=false;installs=0;
 assert(TryInstallSpeedCacheBoundary(target)&&installs==1);
 assert(TryInstallSpeedCacheBoundary(target)&&installs==1);
 alignas(16) unsigned char player[0x2000]{};playerWant=reinterpret_cast<std::uintptr_t>(player);
 std::uint32_t mask=0;relay::InternalHookContext ctx{};ctx.x[19]=playerWant;ctx.x[21]=reinterpret_cast<std::uintptr_t>(&mask);
 const auto before=ctx;
 denyAllocation=true;
 assert(SpeedCacheInternalCallback(ctx,nullptr)==0&&calls==0);
 mask=16;enabled=false;assert(SpeedCacheInternalCallback(ctx,nullptr)==0&&calls==0);
 enabled=true;assert(SpeedCacheInternalCallback(ctx,nullptr)==0&&calls==1);
 assert(std::memcmp(&ctx,&before,sizeof(ctx))==0);
 float speed{};std::memcpy(&speed,player+0x194c,4);assert(speed==3.4F);
 denyAllocation=false;
}
'''

class SpeedCacheBoundaryTests(unittest.TestCase):
    def test_cold_gate_and_real_installer_callback(self):
        nro = original_nro()
        if nro is None:
            self.skipTest("requires the local original NRO")
        self.assertIn((0x2857A8, 0x68CF40, 0x394002A8), cold.SITES,
                      'speed cache must have a preinstalled internal gate')
        image = bytearray(nro.read_bytes())
        bad=bytearray(image);bad[0x2857a8]^=1
        with self.assertRaises(ValueError):cold.build_static_callback_patch(bytes(bad))
        bad=bytearray(image);bad[0x68cf40]=1
        with self.assertRaises(ValueError):cold.build_static_callback_patch(bytes(bad))
        patch = cold.build_static_callback_patch(bytes(image))
        # Patch parser uses the same IPS format as production.
        pos=5
        while patch[pos:pos+3] != b'EOF':
            at=int.from_bytes(patch[pos:pos+3],'big');size=int.from_bytes(patch[pos+3:pos+5],'big');pos+=5
            self.assertGreater(size,0)
            image[at:at+size]=patch[pos:pos+size];pos+=size
        self.assertEqual(struct.unpack_from('<I',image,0x2857a8)[0],cold.branch(0x2857a8,0x68cf40))
        self.assertEqual(image[0x68cf40:0x68cf60],cold.gate_image(0x2857a8,0x68cf40,0x394002a8))
        with tempfile.TemporaryDirectory() as folder:
            path=prepare_harness_directory(Path(folder));(path/'driver.cpp').write_text(DRIVER);(path/'patched.nro').write_bytes(image)
            command=['clang++',*HARNESS_COMPILE_FLAGS,'-I',str(path/'compatibility'),'-I',str(ROOT/'runtime/source'),
                     '-I',str(ROOT/'runtime/src'),'-I',str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),
                     str(path/'driver.cpp'),str(ROOT/'runtime/source/cold_callbacks_internal_hook.cpp'),
                     str(ROOT/'runtime/src/infrastructure/internal/speed_cache_hook_installer.cpp'),'-o',str(path/'test')]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(path/'test'),str(path/'patched.nro')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_stage109_cannot_publish_a_conflicting_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            (path/'test.cpp').write_text('''#include "infrastructure/internal/speed_cache_hook_installer.hpp"
#include <cassert>
int main(){isaac::runtime::HookTarget target{};
assert(!isaac::runtime::TryInstallSpeedCacheBoundary(target));}
''')
            result=subprocess.run(['clang++','-std=c++20','-Wall','-Wextra','-Werror',
                '-DEXL_DIAGNOSTIC_STAGE=109','-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),
                str(path/'test.cpp'),str(ROOT/'runtime/src/infrastructure/internal/speed_cache_hook_installer.cpp'),
                '-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
