"""8字节ADRP+BR近桩：独立解码signed21页、严格边界和页对齐。"""
import subprocess
import platform
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

class PageVeneerTests(unittest.TestCase):
 def test_real_aarch64_executes_forward_and_backward_page_jump(self):
  if platform.machine() not in {'arm64','aarch64'}:self.skipTest('需要AArch64宿主')
  driver=r'''
#include "relay/internal_hook.hpp"
#include <sys/mman.h>
#include <cassert>
using namespace isaac::runtime::relay;
int main(){
 auto*p=static_cast<unsigned char*>(mmap(nullptr,0x4000,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0));
 assert(p!=MAP_FAILED);auto base=reinterpret_cast<std::uintptr_t>(p);
 assert(BuildInternalPageVeneer(p,base,base+0x1000));
 assert(BuildInternalPageVeneer(p+0x3000,base+0x3000,base+0x1000));
 StoreLittleEndianWord(p+0x1000,0x52800540); // mov w0,#42
 StoreLittleEndianWord(p+0x1004,0xd65f03c0); // ret，近桩不得改LR
 __builtin___clear_cache(reinterpret_cast<char*>(p),reinterpret_cast<char*>(p+0x4000));
 assert(mprotect(p,0x4000,PROT_READ|PROT_EXEC)==0);
 using Fn=unsigned(*)();assert(reinterpret_cast<Fn>(p)()==42);
 assert(reinterpret_cast<Fn>(p+0x3000)()==42);
 assert(munmap(p,0x4000)==0);
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_real_installer_preserves_neighbor_and_rolls_back_one_word(self):
  from . import test_internal_hook_adapter as old
  import inspect,re
  text=inspect.getsource(old.InternalHookAdapterTests.test_real_installer_atomic_commit_retained_veneer_and_failure)
  shim=re.search('shim=r"""([\\s\\S]*?)"""',text).group(1)
  driver=r'''
#include "relay/internal_hook.hpp"
#include <cassert>
#include <cstring>
using namespace isaac::runtime::relay;
alignas(4096) unsigned char memory[4096]{};
unsigned mode=0,entryFlush=0;
auto entry(){return reinterpret_cast<std::uintptr_t>(memory+32);}
auto near(){return reinterpret_cast<std::uintptr_t>(memory+64);}
void FakeFlush(std::uintptr_t p,void* shadow,std::size_t n){
 if(p==near())assert(n==8);
 if(p==entry()) {assert(n==4);++entryFlush;if(mode==1&&entryFlush==1)return;}
 std::memcpy(reinterpret_cast<void*>(p),shadow,n);
}
extern "C" void isaac_internal_hook_context(){}
int main(){
 InternalHookBinding b{};b.callback=+[](InternalHookContext&,const void*)noexcept->unsigned{return 0;};
 b.resumeCount=1;b.resumes[0]=0x12340;b.scratch=InternalScratchPolicy::ProvedDeadX16;
 InternalHookSite site{entry(),0x940865d2,InternalVeneerKind::Page8};
 for(mode=0;mode<2;++mode){
  std::memset(memory,0,sizeof(memory));std::memset(memory+72,0xa5,8);std::memcpy(memory+32,&site.expected,4);entryFlush=0;
  auto f=TryInstallInternalHook(b,site,near());
  assert(f==(mode?InternalHookFailure::WriteVerifyFailed:InternalHookFailure::None));
  for(unsigned i=72;i<80;++i)assert(memory[i]==0xa5);
  unsigned wanted=site.expected;if(!mode)assert(BuildInternalBranch(&wanted,entry(),near()));
  assert(LoadLittleEndianWord(memory+32,0)==wanted);
  assert((LoadLittleEndianWord(memory+64,0)&0x9f00001f)==0x90000010);
  assert(LoadLittleEndianWord(memory+64,1)==0xd61f0200);
  assert(entryFlush==(mode?2:1));
 }
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'lib/util/sys').mkdir(parents=True);(p/'lib/util/sys/jit.hpp').write_text(shim)
   (p/'driver.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'driver.cpp'),str(ROOT/'runtime/source/relay/internal_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_encoder_boundaries_and_exact_eight_bytes(self):
  driver=r'''
#include "relay/internal_hook.hpp"
#include <cassert>
#include <cstring>
using namespace isaac::runtime::relay;
static unsigned long long decode(unsigned w,unsigned long long at){
 long long pages=((w>>5)&0x7ffff)*4+((w>>29)&3);
 if(pages&(1<<20))pages-=1<<21;
 return (at&~0xfffULL)+pages*4096;
}
int main(){
 unsigned char image[16];std::memset(image,0xa5,16);
 assert(BuildInternalPageVeneer(image,0x800000008ULL,0x800123000ULL));
 auto w=LoadLittleEndianWord(image,0);
 assert((w&0x9f00001f)==0x90000010&&decode(w,0x800000008ULL)==0x800123000ULL);
 assert(LoadLittleEndianWord(image,1)==0xd61f0200);
 for(unsigned i=8;i<16;++i)assert(image[i]==0xa5);
 assert(BuildInternalPageVeneer(image,0x800000008ULL,0x800000000ULL+0xfffff000ULL));
 assert(decode(LoadLittleEndianWord(image,0),0x800000008ULL)==0x8fffff000ULL);
 assert(!BuildInternalPageVeneer(image,0x800000008ULL,0x900000000ULL));
 assert(BuildInternalPageVeneer(image,0x800000008ULL,0x700000000ULL));
 assert(decode(LoadLittleEndianWord(image,0),0x800000008ULL)==0x700000000ULL);
 assert(!BuildInternalPageVeneer(image,0x800000008ULL,0x6fffff000ULL));
 assert(!BuildInternalPageVeneer(image,0x800000008ULL,0x800123004ULL));
 assert(!BuildInternalPageVeneer(image,0x800000009ULL,0x800123000ULL));
 assert(!BuildInternalPageVeneer(nullptr,0x800000008ULL,0x800123000ULL));
 assert(!BuildInternalPageVeneer(image,0,0x800123000ULL));
 assert(!BuildInternalPageVeneer(image,0x800000008ULL,0));
 assert(!BuildInternalPageVeneer(image,4,UINTPTR_MAX-0xfff));
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
