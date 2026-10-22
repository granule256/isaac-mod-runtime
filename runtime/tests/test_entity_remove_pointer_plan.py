"""64bit函数指针事务：陌生目标不覆盖，部分失败只回滚自己的值。"""
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class PointerPlanTests(unittest.TestCase):
 def test_atomic_compare_exchange_rollback_and_foreign_writer(self):
  driver=r'''
#include "entity_remove_slots.hpp"
#include <cassert>
#include <array>
using namespace isaac::runtime;
struct Memory {std::array<std::uintptr_t,11> words{};unsigned swaps{},failAt{99};bool foreign{};};
static std::uintptr_t Read(const void*p,std::uintptr_t a){return static_cast<const Memory*>(p)->words[a];}
static bool Swap(void*p,std::uintptr_t a,std::uintptr_t expected,std::uintptr_t value){
 auto&m=*static_cast<Memory*>(p);++m.swaps;
 if(value==0x8888&&a==m.failAt){if(m.foreign)m.words[0]=0x9999;return false;}
 if(m.words[a]!=expected)return false;m.words[a]=value;return true;
}
int main(){
 std::array<std::uintptr_t,11> sites{},original{};
 for(unsigned i=0;i<11;++i){sites[i]=i;original[i]=0x1000+i;}
 for(unsigned fail:{99U,0U,5U}){
  Memory m;m.words=original;m.failAt=fail;EntityPointerIo io{&m,Read,Swap};
  auto result=InstallEntityPointerPlan(io,sites,original,0x8888);
  assert(result==(fail==99?EntityPointerFailure::None:EntityPointerFailure::WriteFailed));
  for(unsigned i=0;i<11;++i)assert(m.words[i]==(fail==99?0x8888:original[i]));
 }
 Memory m;m.words=original;m.words[6]=0x7777;EntityPointerIo io{&m,Read,Swap};
 assert(InstallEntityPointerPlan(io,sites,original,0x8888)==EntityPointerFailure::GuardMismatch&&m.swaps==0);
 m={};m.words=original;m.failAt=5;m.foreign=true;
 assert(InstallEntityPointerPlan(io,sites,original,0x8888)==EntityPointerFailure::RollbackFailed);
 assert(m.words[0]==0x9999);
 for(unsigned i=1;i<11;++i)assert(m.words[i]==original[i]);
}
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.cpp').write_text(driver)
   r=subprocess.run(['clang++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/source'),str(p/'test.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
