"""真实生产发布器只CAS写slot，代码/邻位保持；原件错字拒绝。"""
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SHIM=r'''
#pragma once
#include <array>
#include <span>
#include <cstdint>
namespace exl::util {
class RwPages{std::uintptr_t p;public:RwPages(std::uintptr_t a,std::size_t):p(a){}std::uintptr_t GetRw()const{return p;}void Flush(){}};
template<std::size_t N>class Jit{std::uintptr_t p{};public:constexpr Jit()=default;void Initialize(std::span<const std::uint8_t,N> a){p=reinterpret_cast<std::uintptr_t>(a.data());}std::uintptr_t GetRo()const{return p;}std::uintptr_t GetRw()const{return p;}void Flush(){}};
}
#define JIT_CREATE(name,size) namespace impl::name{alignas(4096)std::array<std::uint8_t,size>s_Area{};} constinit exl::util::Jit<size>name
'''
DRIVER=r'''
#include "relay/internal_hook.hpp"
#include <array>
#include <cassert>
#include <cstring>
using namespace isaac::runtime::relay;
extern "C" void isaac_internal_hook_context(){}
alignas(4096)std::array<unsigned char,4096> image{};
int main(){
 auto base=reinterpret_cast<std::uintptr_t>(image.data());auto source=base+64,gate=base+128;
 ColdInternalHookSite site{source,gate,0x7100a29f};
 unsigned branch{};assert(BuildInternalBranch(&branch,source,gate));std::memcpy(image.data()+64,&branch,4);
 unsigned code[]={0x100000d0,0xc8dffe10,0xb4000050,0xd61f0200,0x7100a29f,0};assert(BuildInternalBranch(&code[5],gate+20,source+4));std::memcpy(image.data()+128,code,24);
 InternalHookBinding b{};b.callback=+[](InternalHookContext&,const void*)noexcept->unsigned{return 0;};b.resumes[0]=gate+16;b.resumeCount=1;b.scratch=InternalScratchPolicy::ProvedDeadX16;
 auto before=image;
 for(unsigned off=128;off<152;++off){image[off]^=1;assert(TryInstallPreinstalledInternalHook(b,site)==InternalHookFailure::GuardMismatch);image[off]^=1;}
 for(unsigned off=64;off<68;++off){image[off]^=1;assert(TryInstallPreinstalledInternalHook(b,site)==InternalHookFailure::GuardMismatch);image[off]^=1;}
 assert(TryInstallPreinstalledInternalHook(b,site)==InternalHookFailure::None);
 std::uintptr_t callback{};std::memcpy(&callback,image.data()+152,8);assert(callback!=0);
 assert(!std::memcmp(before.data(),image.data(),152)&&!std::memcmp(before.data()+160,image.data()+160,image.size()-160));
 assert(TryInstallPreinstalledInternalHook(b,site)==InternalHookFailure::VeneerNotEmpty);
 auto bad=site;bad.original=0x54000000;assert(TryInstallPreinstalledInternalHook(b,bad)==InternalHookFailure::InvalidPlan);
}
'''
class ColdPublisherTests(unittest.TestCase):
 def test_real_production_publisher_guards_and_atomic_slot(self):
  header=(ROOT/'runtime/source/relay/internal_hook.hpp').read_text()
  self.assertIn('ColdInternalHookSite',header,'加载前中继的纯指针发布器尚未实现')
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'lib/util/sys').mkdir(parents=True);(p/'lib/util/sys/jit.hpp').write_text(SHIM);(p/'test.cpp').write_text(DRIVER)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/source/relay/internal_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
