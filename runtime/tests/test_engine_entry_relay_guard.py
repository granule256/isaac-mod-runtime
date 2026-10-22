"""主动Lua方法识别自己安装的中继，仍拒绝陌生跳板与错误回放序言。"""
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DRIVER=r'''
#include "interfaces/lua/engine_method_lookup.hpp"
#include <array>
#include <cassert>
static bool readable(std::uintptr_t a,std::size_t n){return a!=0&&n<=128;}
int main(){
 alignas(16) std::array<unsigned char,16> entry{};
 alignas(16) std::array<unsigned char,64> slot{};
 const std::array<unsigned char,16> expected={0xfd,0x7b,0xbd,0xa9,1,2,3,4,5,6,7,8,9,10,11,12};
 auto address=reinterpret_cast<std::uintptr_t>(entry.data());
 auto fallback=reinterpret_cast<std::uintptr_t>(slot.data()+32);
 std::memcpy(entry.data(),expected.data(),16);
 assert(isaac::runtime::EngineEntryOrRelayMatches<readable>(address,expected.data(),16,0));
 std::uint32_t words[2]={0x58000050,0xd61f0200};
 std::memcpy(entry.data(),words,8);auto pointer=fallback-32;std::memcpy(entry.data()+8,&pointer,8);
 std::memcpy(slot.data()+32,expected.data(),16);
 assert(!isaac::runtime::EngineEntryOrRelayMatches<readable>(address,expected.data(),16,0));
 assert(isaac::runtime::EngineEntryOrRelayMatches<readable>(address,expected.data(),16,fallback));
 slot[34]^=1;assert(!isaac::runtime::EngineEntryOrRelayMatches<readable>(address,expected.data(),16,fallback));slot[34]^=1;
 pointer+=16;std::memcpy(entry.data()+8,&pointer,8);
 assert(!isaac::runtime::EngineEntryOrRelayMatches<readable>(address,expected.data(),16,fallback));
 assert(!isaac::runtime::EngineEntryOrRelayMatches<readable>(0,expected.data(),16,fallback));
}
'''
class EngineEntryGuardTests(unittest.TestCase):
 def test_relay_identity_and_original_fingerprint(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'probe.cpp';p.write_text(DRIVER);b=Path(td)/'probe'
   r=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(p),'-o',str(b)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   r=subprocess.run([str(b)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':unittest.main()
