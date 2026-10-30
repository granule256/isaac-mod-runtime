"""Procedural item pixels must become CPU coherent before native generation/present."""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
HARNESS=r'''
#include "application/graphics/procedural_texel_readback.hpp"
#include <array>
#include <cstdint>
#include <cstring>
#include <cassert>
using namespace isaac::runtime;
std::array<unsigned char,0x40> manager{};
std::array<unsigned char,0x610> first{},second{};
unsigned calls{};bool readable=true;
template<class T>void put(void*p,unsigned off,T x){std::memcpy(static_cast<char*>(p)+off,&x,sizeof(x));}
bool Read(std::uintptr_t a,void*out,std::size_t n){
 if(!readable)return false;
 for(auto b:{std::pair<std::uintptr_t,std::size_t>{reinterpret_cast<std::uintptr_t>(manager.data()),manager.size()},
            {reinterpret_cast<std::uintptr_t>(first.data()),first.size()},
            {reinterpret_cast<std::uintptr_t>(second.data()),second.size()}})
  if(a>=b.first&&n<=b.second&&a-b.first<=b.second-n){std::memcpy(out,reinterpret_cast<void*>(a),n);return true;}
 return false;
}
void Enable(std::uintptr_t p,bool value){
 assert(value);++calls;std::uint64_t f{};assert(Read(p+0x10,&f,8));
 put(reinterpret_cast<void*>(p),0x10,f|0x10000ULL);
 put(reinterpret_cast<void*>(p),0x608,std::uintptr_t{0x1234});
}
int main(){
 const auto a=reinterpret_cast<std::uintptr_t>(first.data()),b=reinterpret_cast<std::uintptr_t>(second.data());
 put(manager.data(),0x18,a);put(manager.data(),0x28,b);
 put(first.data(),0x10,std::uint64_t{2});put(second.data(),0x10,std::uint64_t{2});
 put(first.data(),0x51c,std::uint32_t{1024});put(first.data(),0x520,std::uint32_t{1024});
 put(second.data(),0x51c,std::uint32_t{512});put(second.data(),0x520,std::uint32_t{512});
 const ProceduralTexelBackend backend{Read,Enable};
 auto r=PrepareProceduralItemReadback(reinterpret_cast<std::uintptr_t>(manager.data()),backend);
 assert(r.enabled==2&&r.failed==0&&calls==2); // native generation/present follows these calls
 r=PrepareProceduralItemReadback(reinterpret_cast<std::uintptr_t>(manager.data()),backend);
 assert(r.enabled==0&&r.failed==0&&calls==2); // no repeated allocation/copy per texel
 // Same address can be recreated: flags must be reread, not cached by pointer.
 put(first.data(),0x10,std::uint64_t{2});put(first.data(),0x608,std::uintptr_t{0});
 r=PrepareProceduralItemReadback(reinterpret_cast<std::uintptr_t>(manager.data()),backend);
 assert(r.enabled==1&&calls==3);
 put(first.data(),0x51c,std::uint32_t{8192});
 r=PrepareProceduralItemReadback(reinterpret_cast<std::uintptr_t>(manager.data()),backend);
 assert(r.enabled==0&&r.failed==1&&calls==3); // do not turn arbitrary large targets coherent
 put(manager.data(),0x18,std::uintptr_t{0});put(manager.data(),0x28,std::uintptr_t{0});
 r=PrepareProceduralItemReadback(reinterpret_cast<std::uintptr_t>(manager.data()),backend);
 assert(r.enabled==0&&r.failed==0&&calls==3);
 readable=false;r=PrepareProceduralItemReadback(reinterpret_cast<std::uintptr_t>(manager.data()),backend);
 assert(r.failed==2&&calls==3);
}
'''
class ProceduralTexelReadbackTests(unittest.TestCase):
 def test_lifecycle_bounded_targets_and_one_time_enable(self):
  with tempfile.TemporaryDirectory(prefix='procedural-texel-')as d:
   p=Path(d);(p/'test.cpp').write_text(HARNESS)
   r=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I'+str(ROOT/'runtime/src'),str(p/'test.cpp'),str(ROOT/'runtime/src/application/graphics/procedural_texel_readback.cpp'),'-o',str(p/'test')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'test')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
