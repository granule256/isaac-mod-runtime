"""原版Manager::Render会重设屏幕：核对真实重定位与完整入口守卫，拒绝错地址。"""
import unittest,tempfile,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
NRO=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro'))
class ShaderScreenHookTests(unittest.TestCase):
 def test_real_relocation_is_the_screen_target_function(self):
  sys.path.insert(0,str(ROOT/'tools'));from nro_symbols import parse_dynamic_relocations
  _,rows=parse_dynamic_relocations(NRO.read_bytes())
  self.assertEqual([(r.offset,r.relocation_type,r.addend)for r in rows['_ZN4KAGE8Graphics11ManagerBase21SetRenderTargetScreenEv'] if r.relocation_type==1026],[(0xa9e8e8,1026,0)])
 def test_guards_original_pointer_and_idempotent_install(self):
  driver=r'''
#include "application/shader/shader_screen_hook.hpp"
#include "runtime_constants.hpp"
#include <array>
#include <cassert>
#include <vector>
#include <cstring>
namespace LuaRuntime{bool IsOnGameThread()noexcept{return false;}}
namespace isaac::runtime{bool CaptureShaderScreenTarget()noexcept{return false;}}
int main(){using namespace isaac::runtime;std::vector<unsigned char> image(0xab0000);const auto base=reinterpret_cast<std::uintptr_t>(image.data());
 const std::array<unsigned char,16> entry{0x28,0x00,0x80,0x52,0x08,0xA0,0x00,0x39,0x1F,0x10,0x00,0xF9,0xC0,0x03,0x5F,0xD6};
 const std::array<unsigned char,16> plt{0x70,0x21,0x00,0xB0,0x11,0x76,0x44,0xF9,0x10,0xA2,0x23,0x91,0x20,0x02,0x1F,0xD6};
 memcpy(image.data()+0x4ef70c,entry.data(),16);memcpy(image.data()+0x671300,plt.data(),16);
 auto write=[&](std::uintptr_t v){memcpy(image.data()+0xa9e8e8,&v,8);};write(base+0x4ef70c);
 for(auto offset:{0x4ef70c,0x671300})for(int i=0;i<16;++i){image[offset+i]^=1;assert(!InstallShaderScreenHook(base));image[offset+i]^=1;}
 write(1);assert(!InstallShaderScreenHook(base));write(base+kPltResolverOffset);assert(InstallShaderScreenHook(base));assert(InstallShaderScreenHook(base));return 0;}
'''
  with tempfile.TemporaryDirectory(prefix='isaac-shader-screen-')as tmp:
   p=Path(tmp);(p/'lib/util/sys').mkdir(parents=True)
   (p/'lib/util/sys/rw_pages.hpp').write_text('#pragma once\n#include <cstdint>\n#include <cstddef>\nnamespace exl::util{struct RwPages{std::uintptr_t p;RwPages(std::uintptr_t a,std::size_t):p(a){}std::uintptr_t GetRw()const{return p;}void Flush(){}};}\n')
   (p/'lua_runtime.hpp').write_text('#pragma once\nnamespace LuaRuntime{bool IsOnGameThread()noexcept;}\n');(p/'test.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/src/application/shader/shader_screen_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
