"""真实加载完成边界的源码接线和五参ABI，避免两秒轮询漏过NRO。"""
from pathlib import Path
import unittest
from . import test_internal_hook_adapter as helper
ROOT=helper.ROOT
class MainModuleLoadHookTests(unittest.TestCase):
 def test_loader_observer_is_installed_before_worker_creation(self):
  source=(ROOT/'runtime/source/runtime_entry.cpp').read_text()
  entry=source[source.index('extern "C" void exl_main('):]
  self.assertIn('InstallMainModuleLoadObserver',entry)
  self.assertLess(entry.index('InstallMainModuleLoadObserver'),entry.index('svcCreateThread'))
  worker=source[source.index('void ModuleWorker(void*)'):source.index('bool PrepareEarlyResourcesAfterLoad() noexcept {')]
  self.assertNotIn('RunEarlyModMountPrelude();',worker)
  self.assertIn('MainModuleLoadPreparationReady()',worker)
 def test_real_callback_preserves_loader_abi_and_prepares_before_return(self):
  driver=r'''
#include "main_module_load_hook.hpp"
#include "runtime_constants.hpp"
#include <cassert>
#include <array>
#include <cstring>
using namespace isaac::runtime;
namespace isaac::runtime::relay {InternalHookFailure TryInstallInternalHook(const InternalHookBinding&,const InternalHookSite&,std::uintptr_t){return InternalHookFailure::InvalidPlan;}}
std::array<unsigned char,128> image{};unsigned calls{},prepares{},sequence{};std::uint32_t status{};bool prepareOk{};
std::uint32_t Original(void* out,const void* source,void* buffer,std::size_t bytes,int flag){
 assert(out==reinterpret_cast<void*>(0x1110)&&source==image.data()&&buffer==reinterpret_cast<void*>(0x2220)&&bytes==0x123000&&flag==2);
 assert(sequence==0);sequence=1;++calls;
 // SDK加载后原源缓冲不再可靠：标识必须在调用前取得。
 std::memset(image.data(),0,image.size());return status;
}
bool Prepare()noexcept{assert(sequence==1);sequence=2;++prepares;return prepareOk;}
void Fill(bool target){image.fill(0);std::uint32_t magic=0x304f524e;std::memcpy(image.data()+0x10,&magic,4);if(target)std::memcpy(image.data()+0x40,kTargetBuildId.data(),32);}
int main(){
 MainModuleLoadBindings bindings{Original,Prepare,0xabc694};
 for(unsigned mode=0;mode<5;++mode){
  sequence=0;Fill(mode!=1);status=mode==0?0xf1234567U:0;prepareOk=mode>=3;
  relay::InternalHookContext ctx{};ctx.x[0]=0x1110;ctx.x[1]=reinterpret_cast<std::uintptr_t>(image.data());ctx.x[2]=0x2220;ctx.x[3]=0x123000;ctx.x[4]=2;ctx.x[6]=0x9876;
  assert(MainModuleLoadInternalCallback(ctx,&bindings)==0);
  assert(ctx.x[0]==status&&ctx.x[30]==0xabc694&&ctx.x[6]==0x9876);
  assert(sequence==((mode==2||mode==3)?2U:1U));
  assert(MainModuleLoadPreparationReady()==(mode>=3));
 }
 assert(calls==5&&prepares==2);
 auto&s=g_MainModuleLoadObserverState;assert(s.calls==5&&s.targetCalls==3&&s.loadFailures==1&&s.prepared==1);
}
'''
  helper.InternalHookAdapterTests().compile_run(driver,[ROOT/'runtime/source/main_module_load_hook.cpp'])
 def test_all_original_guard_bytes_and_exact_internal_plan(self):
  driver=r'''
#include "main_module_load_hook.hpp"
#include "main_module_load_guards.hpp"
#include <cassert>
#include <vector>
#include <cstring>
using namespace isaac::runtime;
std::uintptr_t base{};unsigned installs{};
bool Prepare()noexcept{return true;}
namespace isaac::runtime::relay {
InternalHookFailure TryInstallInternalHook(const InternalHookBinding&b,const InternalHookSite&s,std::uintptr_t v){
 assert(ValidInternalBinding(b)&&b.callback==MainModuleLoadInternalCallback&&b.resumeCount==1&&b.resumes[0]==base+0x694);
 assert(s.target==base+0x690&&s.expected==0x9402176c&&s.veneerKind==InternalVeneerKind::Absolute16&&v==base+0x86ff0);
 auto*n=static_cast<const MainModuleLoadBindings*>(b.user);assert(n->prepare==Prepare&&reinterpret_cast<std::uintptr_t>(n->originalPlt)==base+0x86440&&n->resume==base+0x694);
 ++installs;return InternalHookFailure::None;
}}
int main(){std::vector<unsigned char> memory(0x87000);base=reinterpret_cast<std::uintptr_t>(memory.data());
 std::memcpy(memory.data()+0x680,main_module_load::kCallGuard.data(),32);std::memcpy(memory.data()+0x86440,main_module_load::kPltGuard.data(),16);
 assert(!InstallMainModuleLoadObserver(base,0x86fff,Prepare)&&installs==0);
 for(auto pair:{std::pair{0x680U,32U},std::pair{0x86440U,16U}}){for(unsigned i=0;i<pair.second;++i){memory[pair.first+i]^=1;assert(!InstallMainModuleLoadObserver(base,memory.size(),Prepare)&&installs==0);memory[pair.first+i]^=1;}}
 assert(!InstallMainModuleLoadObserver(base,memory.size(),nullptr)&&installs==0);
 assert(InstallMainModuleLoadObserver(base,memory.size(),Prepare)&&installs==1);
 assert(InstallMainModuleLoadObserver(base,memory.size(),Prepare)&&installs==1);
 assert(!InstallMainModuleLoadObserver(base+0x1000,memory.size(),Prepare)&&installs==1);
}
'''
  helper.InternalHookAdapterTests().compile_run(driver,[ROOT/'runtime/source/main_module_load_hook.cpp'])
 def test_actual_main_relocation_and_rx_padding_are_independent_inputs(self):
  import subprocess
  r=subprocess.run(['python3',str(ROOT/'tools/verify_main_module_load_hook.py')],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  import json
  v=json.loads(r.stdout);self.assertTrue(v['ok']);self.assertEqual(v['untouched_got'],'0x10ccc0')
 def test_real_publisher_changes_only_main_call_and_padding(self):
  import tempfile,subprocess
  jit=r'''
#pragma once
#include <array>
#include <span>
#include <cstdint>
#include <cstring>
namespace exl::util {
class RwPages {std::uintptr_t p;std::size_t n;std::uint8_t shadow[16]{};public:RwPages(std::uintptr_t a,std::size_t s):p(a),n(s){std::memcpy(shadow,reinterpret_cast<void*>(a),s);}std::uintptr_t GetRw()const{return reinterpret_cast<std::uintptr_t>(shadow);}void Flush(){std::memcpy(reinterpret_cast<void*>(p),shadow,n);}};
template<std::size_t N>class Jit{std::uintptr_t p{};public:constexpr Jit()=default;void Initialize(std::span<const std::uint8_t,N>a){p=reinterpret_cast<std::uintptr_t>(a.data());}std::uintptr_t GetRo()const{return p;}std::uintptr_t GetRw()const{return p;}void Flush(){}};
}
#define JIT_CREATE(name,size) namespace impl::name{alignas(4096)std::array<std::uint8_t,size>s_Area{};} constinit exl::util::Jit<size>name
'''
  driver=r'''
#include "main_module_load_hook.hpp"
#include "main_module_load_guards.hpp"
#include <cassert>
#include <array>
#include <cstring>
using namespace isaac::runtime;
extern "C" void isaac_internal_hook_context(){}
alignas(4096)static std::array<unsigned char,0x112000> mainImage{};
bool Prepare()noexcept{return true;}
int main(){using namespace main_module_load;
 auto base=reinterpret_cast<std::uintptr_t>(mainImage.data());
 std::memcpy(mainImage.data()+kCallOffset-16,kCallGuard.data(),32);std::memcpy(mainImage.data()+kPltOffset,kPltGuard.data(),16);
 const std::uintptr_t salty=0x19d1408e60ULL;std::memcpy(mainImage.data()+0x10ccc0,&salty,8);
 mainImage[kVeneerOffset]=1;assert(!InstallMainModuleLoadObserver(base,0x87000,Prepare));mainImage[kVeneerOffset]=0;
 auto before=mainImage;assert(InstallMainModuleLoadObserver(base,0x87000,Prepare));
 unsigned branch{};assert(relay::BuildInternalBranch(&branch,base+kCallOffset,base+kVeneerOffset));
 assert(relay::LoadLittleEndianWord(mainImage.data()+kCallOffset,0)==branch);
 assert(relay::LoadLittleEndianWord(mainImage.data()+kVeneerOffset,0)==0x58000050);
 assert(relay::LoadLittleEndianWord(mainImage.data()+kVeneerOffset,1)==0xd61f0200);
 for(std::size_t i=0;i<mainImage.size();++i)if(mainImage[i]!=before[i])assert((i>=kCallOffset&&i<kCallOffset+4)||(i>=kVeneerOffset&&i<kVeneerOffset+16));
 std::uintptr_t got{};std::memcpy(&got,mainImage.data()+0x10ccc0,8);assert(got==salty);
}
'''
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);mock=p/'lib/util/sys/jit.hpp';mock.parent.mkdir(parents=True);mock.write_text(jit);(p/'test.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/source/main_module_load_hook.cpp'),str(ROOT/'runtime/source/relay/internal_hook.cpp'),'-o',str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
