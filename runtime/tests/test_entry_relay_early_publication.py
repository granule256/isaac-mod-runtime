"""实际底层安装器：槽先核、外部fallback先发布、随后入口可达；拒绝时不改入口。"""
import pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]

class EntryRelayPublicationTests(unittest.TestCase):
 def test_actual_installer_publishes_before_callback_and_retains_on_rollback(self):
  self.assertIn('TryInstallEntryRelayWithPublisher',(ROOT/'runtime/source/relay/entry_relay.hpp').read_text(),
    '现四参out只写局部变量，缺真正外部fallback发布接口')
  shim=r'''
#pragma once
#include <array>
#include <span>
#include <cstdint>
#include <cstring>
extern void FakeFlush(std::uintptr_t,void*,std::size_t);
extern void FakeArenaFlush(void*);
namespace exl::util{
class RwPages{
 std::uintptr_t address_;std::size_t size_;alignas(16)unsigned char shadow_[16]{};
public:
 RwPages(std::uintptr_t p,std::size_t n):address_(p),size_(n){std::memcpy(shadow_,reinterpret_cast<void*>(p),n);}
 std::uintptr_t GetRw()const{return reinterpret_cast<std::uintptr_t>(shadow_);}
 void Flush(){FakeFlush(address_,shadow_,size_);}
};
template<std::size_t N>class Jit{
 std::uintptr_t address_{};
public:
 constexpr Jit()=default;
 void Initialize(std::span<const std::uint8_t,N>a){address_=reinterpret_cast<std::uintptr_t>(a.data());}
 std::uintptr_t GetRo()const{return address_;}std::uintptr_t GetRw()const{return address_;}
 void Flush(){FakeArenaFlush(reinterpret_cast<void*>(address_));}
};
}
#define JIT_CREATE(name,size) namespace impl::name{alignas(4096)std::array<std::uint8_t,size>s_Area{};}constinit exl::util::Jit<size>name
'''
  driver=r'''
#include "relay/entry_relay.hpp"
#include <atomic>
#include <cassert>
#include <cstring>
#include <initializer_list>
using namespace isaac::runtime::relay;
alignas(4096)static unsigned char memory[4096]{};
static std::atomic<std::uintptr_t>published{0};
static unsigned publications=0,callbacks=0,entryWrites=0;
static int mode=0;static bool corrupted=false;
static std::uintptr_t target(){return reinterpret_cast<std::uintptr_t>(memory+32);}
static const unsigned char original[16]={0xfd,0x7b,0xbf,0xa9,0xfd,0x03,0x00,0x91,0x08,0x98,0x8d,0x52,0x68,0x00,0xa0,0x72};
void FakeArenaFlush(void* a){if(mode==2&&!corrupted){unsigned char* bytes=static_cast<unsigned char*>(a);unsigned last=0;
 for(unsigned i=0;i<64;++i)if(bytes[i*64]==0xd1)last=i;
 bytes[last*64]^=1;corrupted=true;}}
static bool Publish(std::uintptr_t p,void* user)noexcept{
 assert(user==&published&&p!=0&&entryWrites==0);
 assert(std::memcmp(reinterpret_cast<void*>(p),original,16)==0);
 ++publications;
 if(mode==1)return false;
 published.store(p,std::memory_order_release);return true;
}
void FakeFlush(std::uintptr_t p,void* shadow,std::size_t n){
 assert(p==target());++entryWrites;
 std::memcpy(reinterpret_cast<void*>(p),shadow,n);
 if(entryWrites==1){
  ++callbacks;auto fallback=published.load(std::memory_order_acquire);
  assert(fallback!=0&&publications==1&&std::memcmp(reinterpret_cast<void*>(fallback),original,16)==0);
  if(mode==3)memory[32]^=1;
 }
}
int main(){
 for(int testMode:{0,1,2,3}){
  mode=testMode;corrupted=false;published.store(0);publications=callbacks=entryWrites=0;
  std::memcpy(memory+32,original,16);std::uintptr_t diagnostic=0;
  bool ok=TryInstallEntryRelayWithPublisher(target(),original,0x1000,Publish,&published,&diagnostic);
  assert(ok==(mode==0));
  if(mode==0){assert(callbacks==1&&diagnostic==published.load()&&InstalledCount()==1);}
  if(mode==1){assert(publications==1&&callbacks==0&&entryWrites==0&&published.load()==0&&std::memcmp(memory+32,original,16)==0);}
  if(mode==2){assert(publications==0&&callbacks==0&&entryWrites==0&&std::memcmp(memory+32,original,16)==0);}
  if(mode==3){assert(callbacks==1&&entryWrites==2&&published.load()!=0&&std::memcmp(memory+32,original,16)==0);}
 }
}
'''
  with tempfile.TemporaryDirectory()as tmp:
   p=pathlib.Path(tmp);(p/'lib/util/sys').mkdir(parents=True)
   (p/'lib/util/sys/jit.hpp').write_text(shim);(p/'driver.cpp').write_text(driver)
   result=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(p),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/src'),str(p/'driver.cpp'),str(ROOT/'runtime/source/relay/entry_relay.cpp'),'-o',str(p/'driver')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(p/'driver')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
