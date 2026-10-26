"""真实SDK new/delete→malloc/free关系：拒绝不同堆、损坏跳转与不可读数据。"""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
MAIN=r'''
#include "infrastructure/call/cpp_allocator_pair.hpp"
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
using isaac::runtime::engine_call::CppAllocatorPairMatches;
alignas(4096) std::array<unsigned char,8192> memory{};
std::uintptr_t Base(){return reinterpret_cast<std::uintptr_t>(memory.data());}
bool Readable(std::uintptr_t p,std::size_t n){return p>=Base()&&p-Base()<=memory.size()&&n<=memory.size()-(p-Base());}
void Put(unsigned offset,std::uint32_t word){std::memcpy(memory.data()+offset,&word,4);}
void Pointer(unsigned offset,std::uintptr_t word){std::memcpy(memory.data()+offset,&word,8);}
void Branch(unsigned at,unsigned to,bool link){Put(at,(link?0x94000000U:0x14000000U)|(static_cast<std::uint32_t>((static_cast<int>(to)-static_cast<int>(at))/4)&0x3ffffffU));}
void Plt(unsigned at,unsigned got){Put(at,0x90000010U);Put(at+4,0xf9400211U|((got/8)<<10));Put(at+8,0x91000210U|(got<<10));Put(at+12,0xd61f0220U);}
bool Matches(){return CppAllocatorPairMatches(Base()+0x100,Base()+0x200,0x12345678,0x87654320,Readable);}
int main(){
 const std::array<std::uint32_t,6> prefix={0xa9be7bfd,0xf9000bf3,0x910003fd,0xf100001f,0x9a9f1413,0xaa1303e0};
 for(unsigned i=0;i<6;++i)Put(0x100+i*4,prefix[i]);Branch(0x118,0x300,true);Branch(0x200,0x340,false);Plt(0x300,0x800);Plt(0x340,0x808);Pointer(0x800,0x12345678);Pointer(0x808,0x87654320);
 assert(Matches());const auto before=memory;
 Pointer(0x800,0x11111110);assert(!Matches());memory=before;
 Pointer(0x808,0x11111110);assert(!Matches());memory=before;
 Put(0x118,0x14000000);assert(!Matches());memory=before;
 Put(0x200,0x94000000);assert(!Matches());memory=before;
 Put(0x308,0x91000210U|(0x810U<<10));assert(!Matches());memory=before;
 Put(0x30c,0xd65f03c0);assert(!Matches());memory=before;
 Put(0x100,0xd503201f);assert(!Matches());memory=before;
 assert(!CppAllocatorPairMatches(0,Base()+0x200,1,2,Readable));
 assert(!CppAllocatorPairMatches(Base()+8100,Base()+0x200,1,2,Readable));
 assert(!CppAllocatorPairMatches(UINTPTR_MAX-16,Base()+0x200,1,2,Readable));
 // SDK的malloc stub可能位于new之前，负BL必须按signed imm26解码。
 Branch(0x118,0x40,true);Plt(0x40,0x800);assert(Matches());
 // ADRP跨页正/负解析，GOT载入目标一致才可认可。
 memory=before;Branch(0x118,0x1300,true);Plt(0x1300,0x800);Put(0x1300,0xf0fffff0U);assert(Matches());
 memory=before;Branch(0x118,0x300,true);Plt(0x300,0x800);Put(0x300,0xb0000010U);Pointer(0x1800,0x12345678);assert(Matches());
 assert(memory!=before);std::puts("allocator provenance: matching SDK heap and 12 rejection/branch cases passed");
}
'''
class CppAllocatorPairTests(unittest.TestCase):
 def test_actual_sdk_shape_same_heap_and_rejections(self):
  with tempfile.TemporaryDirectory(prefix='cpp-allocator-pair-')as d:
   p=Path(d);source=p/'test.cpp';source.write_text(MAIN);binary=p/'test'
   r=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),str(source),'-o',str(binary)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(binary)],capture_output=True,text=True);print(r.stdout+r.stderr,flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
