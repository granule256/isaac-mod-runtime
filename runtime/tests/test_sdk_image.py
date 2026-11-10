"""Self-built dynamic image, never game code, checks SDK discovery boundaries."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include "infrastructure/persistence/sdk_image.hpp"
#include <cassert>
#include <cstring>
using namespace isaac::runtime;
alignas(8) unsigned char bytes[4096]{};
void U32(unsigned n,std::uint32_t value){std::memcpy(bytes+n,&value,4);}
void U64(unsigned n,std::uint64_t value){std::memcpy(bytes+n,&value,8);}
int main(){
 const auto base=reinterpret_cast<std::uintptr_t>(bytes);
 SdkImage image{};image.base=base;
 image.ranges[0]={base,512,true};image.ranges[1]={base+512,3584,false};image.count=2;
 U32(4,8);U32(8,0x30444f4d);U32(12,504);
 unsigned pos=512;auto dyn=[&](unsigned tag,unsigned value){U64(pos,tag);U64(pos+8,value);pos+=16;};
 dyn(4,768);dyn(5,1024);dyn(6,1536);dyn(10,64);dyn(11,24);dyn(0,0);
 U32(768,1);U32(772,2);U32(776,1);U32(780,0);U32(784,0);
 std::strcpy(reinterpret_cast<char*>(bytes+1025),"open");
 U32(1560,1);bytes[1564]=0x12;bytes[1566]=1;U64(1568,128);
 assert(image.Parse() && image.FindFunction("open")==base+128);
 assert(image.FindFunction("absent")==0);
 U64(1568,3000);assert(image.FindFunction("open")==0);U64(1568,128);
 U32(1560,63);bytes[1087]='x';assert(image.FindFunction("open")==0);U32(1560,1);
 U64(528+8,4090);assert(!image.Parse());U64(528+8,1024);
 U32(772,0xffffffff);assert(!image.Parse());U32(772,2);
 image.ranges[1]={base+768,3328,false};assert(!image.Parse());
 image.ranges[1]={base+512,3584,false};
 // The same image using GNU hash with one bucket and one terminated chain.
 U64(512,0x6ffffef5);U32(768,1);U32(772,1);U32(776,1);U32(780,5);
 U64(784,~std::uint64_t{});U32(792,1);U32(796,1);
 assert(image.Parse() && image.FindFunction("open")==base+128);
 U32(796,0);assert(!image.Parse());
 // Decode the verified ADRP/LDR/ADD/BR import form at arbitrary ASLR bases.
 const std::uint32_t thunk[]{0xb0002130,0xf947ce11,0x913e6210,0xd61f0220};
 assert(SdkImage::ImportSlot(0x100680060,thunk)==0x100aa5f98);
 const std::uint32_t bad[]{0xb0002130,0xf947ce11,0x913e6210,0};
 assert(SdkImage::ImportSlot(0x100680060,bad)==0);
 // Unused PLT imports may still point at the verified game resolver. Calls
 // must use the independently resolved SDK export, never that resolver.
 assert(SdkImage::ImportTargetAllowed(0x1234,0x1234,0x5678));
 assert(SdkImage::ImportTargetAllowed(0x5678,0x1234,0x5678));
 assert(!SdkImage::ImportTargetAllowed(0x9876,0x1234,0x5678));
 assert(!SdkImage::ImportTargetAllowed(0x5678,0,0x5678));
}
'''


class SdkImageTests(unittest.TestCase):
    def test_bounds_hashes_function_permissions_and_import_decode(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "driver.cpp"
            source.write_text(DRIVER)
            binary = Path(tmp) / "driver"
            result = subprocess.run([
                "c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "runtime/src"), str(source), "-o", str(binary),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
