"""真实内部中继后端：64KiB紧密容量、Page8混排与失败提交边界。"""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHIM = r'''
#pragma once
#include <array>
#include <span>
#include <cstdint>
#include <cstring>
inline std::uintptr_t fakeArena{};
inline std::size_t fakeArenaBytes{};
inline bool failJitFlush{};
extern void FakeFlush(std::uintptr_t,void*,std::size_t);
extern void FakeMap(std::uintptr_t);
namespace exl::util {
class RwPages {
 std::uintptr_t address_;std::size_t size_;alignas(16) unsigned char shadow_[16]{};
public:
 RwPages(std::uintptr_t p,std::size_t n):address_(p),size_(n){std::memcpy(shadow_,reinterpret_cast<void*>(p),n);FakeMap(p);}
 std::uintptr_t GetRw()const{return reinterpret_cast<std::uintptr_t>(shadow_);}
 void Flush(){FakeFlush(address_,shadow_,size_);}
};
template<std::size_t N>class Jit {
 std::uintptr_t address_{};
public:
 constexpr Jit()=default;
 void Initialize(std::span<const std::uint8_t,N> a){address_=reinterpret_cast<std::uintptr_t>(a.data());fakeArena=address_;fakeArenaBytes=N;}
 std::uintptr_t GetRo()const{return address_;}
 std::uintptr_t GetRw()const{return address_;}
 void Flush(){if(failJitFlush){reinterpret_cast<unsigned char*>(address_)[0]^=1;failJitFlush=false;}}
};
}
#define JIT_CREATE(name,size) namespace impl::name {alignas(4096) std::array<std::uint8_t,size>s_Area{};} constinit exl::util::Jit<size>name
'''
DRIVER = r'''
#include "relay/internal_hook.hpp"
#include "lib/util/sys/jit.hpp"
#include <cassert>
#include <cstring>
#include <string>
using namespace isaac::runtime::relay;
alignas(4096) static unsigned char memory[0x10000]{};
static std::uintptr_t refusedEntry{};
static bool refuseOnce{},sabotageNearMap{};
static std::uintptr_t Addr(std::size_t offset){return reinterpret_cast<std::uintptr_t>(memory+offset);}
static std::uintptr_t Pointer(std::uintptr_t p){std::uintptr_t v{};std::memcpy(&v,reinterpret_cast<void*>(p),8);return v;}
void FakeMap(std::uintptr_t p){if(sabotageNearMap&&p==Addr(32)){*reinterpret_cast<unsigned char*>(p)=1;sabotageNearMap=false;}}
void FakeFlush(std::uintptr_t p,void* shadow,std::size_t n){
 if(refuseOnce&&p==refusedEntry){refuseOnce=false;return;}
 std::memcpy(reinterpret_cast<void*>(p),shadow,n);
}
extern "C" void isaac_internal_hook_context(){}
static InternalHookBinding Binding(){InternalHookBinding b{};b.callback=+[](InternalHookContext&,const void*)noexcept->unsigned{return 0;};b.resumeCount=1;b.resumes[0]=Addr(0xff00);b.scratch=InternalScratchPolicy::ProvedDeadX16;return b;}
static InternalHookFailure Install(unsigned n,unsigned kind,std::uintptr_t* gateway){
 const auto source=Addr(n*128),veneer=source+32,slot=source+64;
 auto binding=Binding();
 if(kind==3){
  binding.resumes[0]=veneer+16;constexpr unsigned original=0xF9400309;
  unsigned branch{},resume{};assert(BuildInternalBranch(&branch,source,veneer));assert(BuildInternalBranch(&resume,veneer+20,source+4));
  std::memcpy(reinterpret_cast<void*>(source),&branch,4);
  const unsigned code[6]={0x100000D0,0xC8DFFE10,0xB4000050,0xD61F0200,original,resume};
  std::memcpy(reinterpret_cast<void*>(veneer),code,sizeof(code));
  const auto result=TryInstallPreinstalledInternalHook(binding,{source,veneer,original});
  *gateway=Pointer(veneer+24);return result;
 }
 constexpr unsigned original=0x94000001;
 std::memcpy(reinterpret_cast<void*>(source),&original,4);
 const auto result=TryInstallInternalHook(binding,{source,original,static_cast<InternalVeneerKind>(kind),kind==2?slot:0},veneer);
 if(kind==0)*gateway=Pointer(veneer+8);
 else if(kind==2)*gateway=Pointer(slot);
 else {
  const auto word=LoadLittleEndianWord(reinterpret_cast<const std::uint8_t*>(veneer),0);
  const unsigned imm=((word>>29)&3)|((word>>5&0x7ffff)<<2);
  const std::int64_t signedImm=(imm&0x100000)?static_cast<std::int64_t>(imm)-0x200000:imm;
  *gateway=static_cast<std::uintptr_t>((veneer&~std::uintptr_t{0xfff})+signedImm*4096);
 }
 return result;
}
static void Gateway(std::uintptr_t address){
 assert(address>=fakeArena&&address+32<=fakeArena+fakeArenaBytes&&fakeArenaBytes==0x10000);
 assert(LoadLittleEndianWord(reinterpret_cast<const std::uint8_t*>(address),0)==0xA9BF7BF1);
 const auto* binding=reinterpret_cast<const InternalHookBinding*>(Pointer(address+16));
 assert(ValidInternalBinding(*binding));
 assert(Pointer(address+24)==reinterpret_cast<std::uintptr_t>(&isaac_internal_hook_context));
}
int main(int argc,char**argv){
 assert(argc==2);const std::string scene=argv[1];std::uintptr_t gateway{};
 if(scene=="capacity"){
  std::uintptr_t gateways[32]{};
  for(unsigned i=0;i<32;++i){
   // Cold/Absolute/Literal三种实际发布路径共享同一个32条计数和紧密cursor。
   const unsigned kind=i%3==0?3:i%3==1?0:2;
   assert(Install(i,kind,&gateway)==InternalHookFailure::None);
   Gateway(gateway);gateways[i]=gateway;
  }
  for(unsigned i=0;i<32;++i)assert(gateways[i]==fakeArena+i*32);
  assert(Install(32,3,&gateway)==InternalHookFailure::ArenaExhausted);
  assert(Install(33,0,&gateway)==InternalHookFailure::ArenaExhausted);
 }else if(scene=="mixed_page"){
  const unsigned kinds[]={0,1,3,2,1,0};
  const unsigned offsets[]={0,0x1000,0x1020,0x1040,0x2000,0x2020};
  for(unsigned i=0;i<6;++i){assert(Install(i,kinds[i],&gateway)==InternalHookFailure::None);Gateway(gateway);assert(gateway==fakeArena+offsets[i]);}
 }else if(scene=="page_exhaustion"){
  for(unsigned i=0;i<16;++i){assert(Install(i,1,&gateway)==InternalHookFailure::None);Gateway(gateway);assert(gateway==fakeArena+i*0x1000);}
  assert(Install(16,1,&gateway)==InternalHookFailure::ArenaExhausted);
  assert(Install(17,3,&gateway)==InternalHookFailure::None);assert(gateway==fakeArena+0xf020);
 }else if(scene=="before_publish"){
  // gateway校验失败时任何指针/近桩尚未发布；允许重写同一安全位置。
  failJitFlush=true;assert(Install(0,0,&gateway)==InternalHookFailure::WriteVerifyFailed);
  assert(Pointer(Addr(32))==0);
  assert(Install(1,3,&gateway)==InternalHookFailure::None);assert(gateway==fakeArena);
 }else if(scene=="near_race"){
  sabotageNearMap=true;assert(Install(0,0,&gateway)==InternalHookFailure::VeneerNotEmpty);
  assert(Install(1,3,&gateway)==InternalHookFailure::None);assert(gateway==fakeArena);
 }else if(scene=="before_publish_cold"){
  failJitFlush=true;assert(Install(0,3,&gateway)==InternalHookFailure::WriteVerifyFailed);
  assert(Pointer(Addr(32+24))==0);
  assert(Install(1,0,&gateway)==InternalHookFailure::None);assert(gateway==fakeArena);
 }else if(scene=="after_publish_cold"){
  refusedEntry=Addr(32+24);refuseOnce=true;
  assert(Install(0,3,&gateway)==InternalHookFailure::WriteVerifyFailed);
  const auto retained=fakeArena;Gateway(retained);
  unsigned char previous[32];std::memcpy(previous,reinterpret_cast<void*>(retained),32);
  assert(Install(1,2,&gateway)==InternalHookFailure::None);assert(gateway==retained+32);
  assert(std::memcmp(previous,reinterpret_cast<void*>(retained),32)==0);
 }else if(scene=="after_publish"){
  refusedEntry=Addr(0);refuseOnce=true;
  assert(Install(0,0,&gateway)==InternalHookFailure::WriteVerifyFailed);
  const auto retained=gateway;Gateway(retained);
  unsigned char previous[32];std::memcpy(previous,reinterpret_cast<void*>(retained),32);
  assert(Install(1,3,&gateway)==InternalHookFailure::None);assert(gateway==retained+32);
  assert(std::memcmp(previous,reinterpret_cast<void*>(retained),32)==0);
 }else return 90;
}
'''


class InternalGatewayBackendTests(unittest.TestCase):
    def test_real_backend_allocation_and_publication(self):
        with tempfile.TemporaryDirectory(prefix='internal-gateway-backend-') as tmp:
            path = pathlib.Path(tmp)
            (path / 'lib/util/sys').mkdir(parents=True)
            (path / 'lib/util/sys/jit.hpp').write_text(SHIM)
            (path / 'driver.cpp').write_text(DRIVER)
            compiled = subprocess.run(['clang++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                                       '-I', str(path), '-I', str(ROOT / 'runtime/source'),
                                       '-I', str(ROOT / 'runtime/src'), str(path / 'driver.cpp'),
                                       str(ROOT / 'runtime/source/relay/internal_hook.cpp'),
                                       '-o', str(path / 'driver')], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            for scene in ('capacity', 'mixed_page', 'page_exhaustion', 'before_publish', 'after_publish', 'before_publish_cold', 'after_publish_cold', 'near_race'):
                with self.subTest(scene=scene):
                    result = subprocess.run([str(path / 'driver'), scene], capture_output=True, text=True)
                    print(scene, result.returncode, result.stdout + result.stderr, flush=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
