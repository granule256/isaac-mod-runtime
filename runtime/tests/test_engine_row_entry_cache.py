"""Alternating native API rows retain successful guards and still reject mismatches."""
from pathlib import Path
import re,subprocess,tempfile,unittest
from .test_lua_api_method_lookup_cost import function
ROOT=Path(__file__).resolve().parents[2]
class EngineRowCacheTests(unittest.TestCase):
 def test_alternating_rows_reload_collision_and_failed_guards(self):
  s=(ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
  if 'EngineRowEntrySlotFor(' in s:
   declaration=re.search(r'isaac::runtime::EngineEntrySlot g_EngineRowEntrySlots\[\d+\]\{\};',s)[0]
   slot=function(s,'isaac::runtime::EngineEntrySlot& EngineRowEntrySlotFor(')
  else:
   declaration=re.search(r'isaac::runtime::EngineEntrySlot g_EngineRowEntrySlot\{\};',s)[0]
   slot='isaac::runtime::EngineEntrySlot& EngineRowEntrySlotFor(std::uintptr_t,std::uint32_t){return g_EngineRowEntrySlot;}'
  code=r'''
#include "interfaces/lua/engine_method_lookup.hpp"
#include <array>
#include <cassert>
static std::uintptr_t module{};static unsigned reads{};
namespace LuaRuntime{std::uintptr_t EngineModuleBase() noexcept{return module;}}
bool Readable(std::uintptr_t p,std::size_t n){++reads;return p&&n==4;}
''' + declaration+slot +r'''
std::uintptr_t Get(unsigned off,unsigned word){return isaac::runtime::EngineEntryAddressCached<Readable>(EngineRowEntrySlotFor(off,word),off,word);}
int main(){
 alignas(16) std::array<unsigned char,8192>a{},b{};
 const unsigned guard=0x39408408;module=reinterpret_cast<std::uintptr_t>(a.data());
 for(auto off:{64u,128u})std::memcpy(a.data()+off,&guard,4);
 for(unsigned i=0;i<1000;++i){assert(Get(64,guard)==module+64);assert(Get(128,guard)==module+128);}
 assert(reads==2&&"alternating native rows evict each other's successful guards");
 module=reinterpret_cast<std::uintptr_t>(b.data());
 assert(!Get(64,guard)&&!Get(64,guard)&&reads==4); // failure never cached
 std::memcpy(b.data()+64,&guard,4);assert(Get(64,guard)==module+64&&reads==5);
 assert(Get(64,guard)==module+64&&reads==5);
 assert(!Get(64,guard^1)&&reads==6); // expected word is part of the key
 unsigned collision=0;
 for(unsigned o=132;o<4096;o+=4)if(&EngineRowEntrySlotFor(o,guard)==&EngineRowEntrySlotFor(64,guard)){collision=o;break;}
 assert(collision);std::memcpy(b.data()+collision,&guard,4);
 assert(Get(collision,guard)==module+collision);assert(Get(64,guard)==module+64);
 module=0;assert(Get(64,guard)==0);
}
'''
  with tempfile.TemporaryDirectory()as td:
   p=Path(td);(p/'p.cpp').write_text(code)
   c=subprocess.run(['c++','-std=c++20','-I',str(ROOT/'runtime/src'),'-I',str(ROOT/'runtime/source'),'-I',str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(p/'p.cpp'),'-o',str(p/'p')],capture_output=True,text=True);self.assertEqual(c.returncode,0,c.stderr)
   r=subprocess.run([str(p/'p')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
