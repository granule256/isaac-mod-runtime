"""Pool interception refuses mismatched images and changes only its GOT slot."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
DRIVER=r'''
#include "mod_itempool_hook.hpp"
#include "mod_itempool_guards.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
namespace isaac::runtime::modmenu {void LoadEngineModItemPools(void*)noexcept{}}
using namespace isaac::runtime;
int main(){
 std::vector<unsigned char> image(0xab0000);
 auto base=reinterpret_cast<std::uintptr_t>(image.data());
 auto copy=[&](auto offset,const auto& bytes){memcpy(image.data()+offset,bytes.data(),bytes.size());};
 copy(mod_itempools::kLoadOffset,mod_itempools::kLoadBytes);
 copy(mod_itempools::kUpdateOffset,mod_itempools::kUpdateBytes);
 copy(mod_itempools::kPltOffset,mod_itempools::kPltBytes);
 auto write=[&](auto value){memcpy(image.data()+mod_itempools::kGotOffset,&value,8);};
 HookTarget t{};t.base=base;t.codeSize=0x68d000;t.imageSize=image.size();t.buildId=kTargetBuildId;
 write(base+mod_itempools::kLoadOffset);
 auto reject=[&](auto offset,const auto& bytes){
  for(unsigned i=0;i<bytes.size();++i){image[offset+i]^=1;assert(!InstallModItemPoolPointerHook(t).ok());image[offset+i]^=1;}
 };
 reject(mod_itempools::kLoadOffset,mod_itempools::kLoadBytes);
 reject(mod_itempools::kUpdateOffset,mod_itempools::kUpdateBytes);
 reject(mod_itempools::kPltOffset,mod_itempools::kPltBytes);
 write(std::uintptr_t{123});assert(!InstallModItemPoolPointerHook(t).ok());
 write(base+kPltResolverOffset);
 auto wrong=t;wrong.buildId[0]^=1;assert(!InstallModItemPoolPointerHook(wrong).ok());
 wrong=t;wrong.imageSize=mod_itempools::kGotOffset;assert(!InstallModItemPoolPointerHook(wrong).ok());
 const auto before=image;
 assert(InstallModItemPoolPointerHook(t).ok());
 for(std::size_t i=0;i<image.size();++i)
  if(i<mod_itempools::kGotOffset||i>=mod_itempools::kGotOffset+8)assert(image[i]==before[i]);
 assert(!InstallModItemPoolPointerHook(t).ok());
}
'''

class ModItemPoolInstallerTests(unittest.TestCase):
    def test_exact_guards_image_identity_slot_ownership_and_single_install(self):
        with tempfile.TemporaryDirectory(prefix="isaac-pool-hook-")as temp:
            p=Path(temp);(p/"lib/util/sys").mkdir(parents=True)
            (p/"lib/util/sys/rw_pages.hpp").write_text(
                "#pragma once\n#include <cstdint>\n#include <cstddef>\n"
                "namespace exl::util{struct RwPages{std::uintptr_t p;"
                "RwPages(std::uintptr_t a,std::size_t):p(a){}"
                "std::uintptr_t GetRw()const{return p;}void Flush(){}};}\n")
            (p/"mod_menu_native.hpp").write_text(
                "#pragma once\nnamespace isaac::runtime::modmenu{void LoadEngineModItemPools(void*)noexcept;}\n")
            (p/"test.cpp").write_text(DRIVER)
            result=subprocess.run(["clang++","-std=c++23","-Wall","-Wextra","-Werror",
                "-I",str(p),"-I",str(ROOT/"runtime/source"),"-I",str(ROOT/"runtime/src"),
                str(p/"test.cpp"),str(ROOT/"runtime/src/infrastructure/gotslot/mod_itempool_pointer_hook.cpp"),
                "-o",str(p/"test")],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(p/"test")],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
