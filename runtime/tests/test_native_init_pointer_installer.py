"""Pinned Init data slots reject bad guards and preserve every instruction."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include "entity_init_hook.hpp"
#include "ports/hook_port.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
using namespace isaac::runtime;
namespace isaac::runtime {
void RunNativeEntityInit(const EntityInitNativeBindings*,NativeEntityInitKind,void*,
 std::uint32_t,std::uint32_t,std::uint32_t,std::uint32_t) noexcept {}
}
int main(){
 std::vector<unsigned char> image(0xab0000);const auto base=reinterpret_cast<std::uintptr_t>(image.data());
 HookTarget t{};t.base=base;t.codeSize=0x68d000;t.imageSize=image.size();t.buildId=kTargetBuildId;
 auto copy=[&](auto off,const auto& bytes){memcpy(image.data()+off,bytes.data(),bytes.size());};
 copy(kNativeEntityInitOffset,kNativeEntityInitExpectedBytes);
 copy(kNativeEntityInitPltOffset,kNativeEntityInitPltExpectedBytes);
 copy(kNativeTearInitOffset,kNativeTearInitExpectedBytes);
 copy(kNativeEffectInitOffset,kNativeEffectInitExpectedBytes);
 copy(kNativePickupInitOffset,kNativePickupInitExpectedBytes);
 auto write=[&](auto off,auto pointer){memcpy(image.data()+off,&pointer,8);};
 write(kNativeEntityInitVtableSlotOffset,base+kNativeEntityInitOffset);
 write(kNativeEntityInitGotOffset,base+kPltResolverOffset);
 write(kNativeTearInitVtableSlotOffset,base+kNativeTearInitOffset);
 write(kNativeEffectInitVtableSlotOffset,base+kNativeEffectInitOffset);
 write(kNativePickupInitVtableSlotOffset,base+kNativePickupInitOffset);
 auto reject=[&](HookId id,auto off,const auto& bytes){
  for(unsigned i=0;i<bytes.size();++i){image[off+i]^=1;const auto before=image;
   assert(!InstallEntityInitPointerHooks(id,t).ok());assert(image==before);image[off+i]^=1;}
 };
 reject(HookId::EntityInit,kNativeEntityInitOffset,kNativeEntityInitExpectedBytes);
 reject(HookId::EntityInit,kNativeEntityInitPltOffset,kNativeEntityInitPltExpectedBytes);
 reject(HookId::EntityTearInit,kNativeTearInitOffset,kNativeTearInitExpectedBytes);
 reject(HookId::EntityEffectInit,kNativeEffectInitOffset,kNativeEffectInitExpectedBytes);
 reject(HookId::EntityPickupInit,kNativePickupInitOffset,kNativePickupInitExpectedBytes);
 const HookId ids[]={HookId::EntityInit,HookId::EntityTearInit,HookId::EntityEffectInit,HookId::EntityPickupInit};
 const uintptr_t slots[]={kNativeEntityInitVtableSlotOffset,kNativeTearInitVtableSlotOffset,kNativeEffectInitVtableSlotOffset,kNativePickupInitVtableSlotOffset};
 const uintptr_t offsets[]={kNativeEntityInitOffset,kNativeTearInitOffset,kNativeEffectInitOffset,kNativePickupInitOffset};
 for(unsigned i=0;i<4;++i){
  auto wrong=t;wrong.buildId[0]^=1;assert(!InstallEntityInitPointerHooks(ids[i],wrong).ok());
  auto shortImage=t;shortImage.imageSize=slots[i];assert(!InstallEntityInitPointerHooks(ids[i],shortImage).ok());
  write(slots[i],uintptr_t{123});const auto foreign=image;
  assert(!InstallEntityInitPointerHooks(ids[i],t).ok()&&foreign==image);
  write(slots[i],base+offsets[i]);
 }
 // Guard the entire text, not merely the observed entry's first 16 bytes.
 const auto original=image;
 for(auto id:ids){assert(InstallEntityInitPointerHooks(id,t).ok());assert(!InstallEntityInitPointerHooks(id,t).ok());}
 assert(!memcmp(image.data(),original.data(),t.codeSize));
 uintptr_t baseVirtual{},baseDirect{};
 memcpy(&baseVirtual,image.data()+kNativeEntityInitVtableSlotOffset,8);
 memcpy(&baseDirect,image.data()+kNativeEntityInitGotOffset,8);
 assert(baseVirtual==baseDirect&&baseVirtual!=base+kNativeEntityInitOffset);
 for(unsigned i=1;i<3;++i){uintptr_t p{};memcpy(&p,image.data()+slots[i],8);assert(p!=base+offsets[i]&&p!=0);}
}
'''


class NativeInitPointerInstallerTests(unittest.TestCase):
    def test_guards_data_slots_and_unchanged_native_layout(self):
        with tempfile.TemporaryDirectory(prefix='native-init-installer-') as directory:
            work = Path(directory)
            shim = work / 'lib/util/sys/rw_pages.hpp'
            shim.parent.mkdir(parents=True)
            shim.write_text('#pragma once\n#include <cstdint>\n#include <cstddef>\n'
                'namespace exl::util {struct RwPages {std::uintptr_t p;'
                'RwPages(std::uintptr_t a,std::size_t):p(a){}'
                'std::uintptr_t GetRw() const{return p;}void Flush(){}};}\n')
            (work / 'main.cpp').write_text(DRIVER)
            result = subprocess.run(['clang++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                '-I', str(work), '-I', str(ROOT / 'runtime/source'), '-I', str(ROOT / 'runtime/src'),
                str(work / 'main.cpp'), str(ROOT / 'runtime/src/infrastructure/gotslot/entity_init_pointer_hooks.cpp'),
                '-o', str(work / 'test')], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(work / 'test')], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
