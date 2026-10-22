"""73原生槽：真实重定位、完整守卫与原入口先发布，拒绝错误版本/原地址。"""
import subprocess,tempfile,unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
NRO=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro'))
class ModUnloadPointerTests(unittest.TestCase):
 def test_real_nro_slot_and_full_function_guard(self):
  sys.path.insert(0,str(ROOT/'tools'));from nro_symbols import parse_dynamic_relocations
  raw=NRO.read_bytes();_,rows=parse_dynamic_relocations(raw)
  self.assertEqual([(r.offset,r.relocation_type,r.addend)for r in rows['_ZN15IsaacRepentance10ModManager10UnloadModsEv']],[(0xaa4e80,1026,0)])
  import re
  text=(ROOT/'runtime/source/mod_unload_guards.hpp').read_text()
  body=text.split('kFunctionBytes={',1)[1].split('};',1)[0]
  expected=bytes(int(x,16)for x in re.findall(r'0x([0-9A-F]{2})',body))
  self.assertEqual(expected,raw[0x41f5ac:0x41f690])
 def test_installer_rejects_each_guard_byte_and_wrong_pointer(self):
  shim='''#pragma once
#include <cstdint>
#include <cstddef>
namespace exl::util{struct RwPages{std::uintptr_t p;RwPages(std::uintptr_t a,std::size_t):p(a){}std::uintptr_t GetRw()const{return p;}void Flush(){}};}
'''
  driver=r'''
#include "mod_unload_hook.hpp"
#include "mod_unload_guards.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <cstring>
#include <vector>
namespace LuaRuntime{bool IsOnGameThread()noexcept{return false;}bool UnloadManifestMods()noexcept{return true;}void RecordLuaErrorText(const char*,std::size_t)noexcept{}}
namespace isaac::runtime{void UnloadShaderPrograms()noexcept{}void ClearRuntimeContentNames()noexcept{}Status FlushRuntimeOptions()noexcept{return Status{StatusCode::Unsupported};}}
using namespace isaac::runtime;
int main(){std::vector<unsigned char>image(0xab0000);auto base=reinterpret_cast<std::uintptr_t>(image.data());
 memcpy(image.data()+mod_unload::kOffset,mod_unload::kFunctionBytes.data(),mod_unload::kFunctionBytes.size());memcpy(image.data()+mod_unload::kPlt,mod_unload::kPltBytes.data(),16);
 auto original=base+mod_unload::kOffset;memcpy(image.data()+0xaa4e80,&original,8);
 HookTarget t{};t.base=base;t.codeSize=0x68d000;t.imageSize=image.size();t.buildId=kTargetBuildId;
 for(unsigned i=0;i<mod_unload::kFunctionBytes.size();++i){image[mod_unload::kOffset+i]^=1;assert(!InstallModUnloadPointerHook(t).ok());image[mod_unload::kOffset+i]^=1;}
 for(unsigned i=0;i<16;++i){image[mod_unload::kPlt+i]^=1;assert(!InstallModUnloadPointerHook(t).ok());image[mod_unload::kPlt+i]^=1;}
 auto write=[&](auto v){memcpy(image.data()+0xaa4e80,&v,8);};write(std::uintptr_t{1});assert(!InstallModUnloadPointerHook(t).ok());
 write(base+kPltResolverOffset);assert(InstallModUnloadPointerHook(t).ok());assert(!InstallModUnloadPointerHook(t).ok());}
'''
  with tempfile.TemporaryDirectory(prefix='isaac-unload-pointer-')as tmp:
   p=Path(tmp);(p/'lib/util/sys').mkdir(parents=True);(p/'lib/util/sys/rw_pages.hpp').write_text(shim);(p/'lua_runtime.hpp').write_text("#pragma once\n#include <cstddef>\nnamespace LuaRuntime{bool IsOnGameThread()noexcept;bool UnloadManifestMods()noexcept;void RecordLuaErrorText(const char*,std::size_t)noexcept;}\n");(p/'test.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/src/infrastructure/gotslot/mod_unload_pointer_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
