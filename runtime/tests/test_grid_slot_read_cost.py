"""Grid scans validate the fixed native table once, while reading live slots."""
from pathlib import Path
import subprocess,tempfile,unittest
from .test_lua_api_method_lookup_cost import function
ROOT=Path(__file__).resolve().parents[2]
class GridSlotReadCost(unittest.TestCase):
 def test_live_mutation_room_epoch_invalidation_and_unscoped_checks(self):
  body=function((ROOT/'runtime/src/interfaces/lua/remaining_api.cpp').read_text(),'int PushGridEntityAtSlot(')
  prefix=r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <array>
struct lua_State{};
static std::uintptr_t pushed{};static int checks{};static bool readable=true;
static std::atomic<std::uint32_t> epoch{1},active{1};
auto& EngineGuardDispatchEpoch(){return epoch;}
auto& EngineGuardDispatchActive(){return active;}
static std::atomic<std::uint32_t> cacheEnabled{1};
auto& EngineGuardCacheEnabledFlag(){return cacheEnabled;}
constexpr std::uintptr_t kRoomGridEntityTableOffset=0x30;
bool IsEngineMemoryReadable(std::uintptr_t,std::size_t){++checks;return readable;}
void lua_pushnil(lua_State*){pushed=0;}
void PushGridEntityHandle(lua_State*,std::uintptr_t p){pushed=p;}
namespace isaac::runtime::engine_memory {
inline void* AsObject(std::uintptr_t p){return reinterpret_cast<void*>(p);}
template<class T>bool ReadAt(std::uintptr_t p,T*out,bool(*r)(std::uintptr_t,std::size_t)){
 if(!r(p,sizeof(T)))return false;std::memcpy(out,AsObject(p),sizeof(T));return true;
}
template<class T>bool LoadVerifiedAt(std::uintptr_t p,std::size_t i,T*out){std::memcpy(out,AsObject(p+i*sizeof(T)),sizeof(T));return true;}
}
'''
  main=r'''
int main(){
 std::array<std::uintptr_t,454>a{},b{};lua_State L;
 auto room=reinterpret_cast<std::uintptr_t>(a.data());
 a[6+3]=0x1000;
 for(int i=0;i<1000;++i){PushGridEntityAtSlot(&L,room,3);assert(pushed==0x1000);}
 assert(checks==1&&"grid scan repeats permission validation for each cell");
 a[6+3]=0x2000;PushGridEntityAtSlot(&L,room,3);assert(pushed==0x2000&&checks==1);
 a[6+3]=0;PushGridEntityAtSlot(&L,room,3);assert(pushed==0&&checks==1);
 auto other=reinterpret_cast<std::uintptr_t>(b.data());b[6+3]=0x3000;
 PushGridEntityAtSlot(&L,other,3);assert(pushed==0x3000&&checks==2);
 ++epoch;readable=false;PushGridEntityAtSlot(&L,other,3);assert(pushed==0&&checks==3);
 readable=true;PushGridEntityAtSlot(&L,other,3);assert(pushed==0x3000&&checks==4);
 active=0;for(int i=0;i<2;++i)PushGridEntityAtSlot(&L,other,3);assert(checks==6);
 PushGridEntityAtSlot(&L,other,-1);PushGridEntityAtSlot(&L,other,448);assert(pushed==0&&checks==6);
}
'''
  with tempfile.TemporaryDirectory()as td:
   p=Path(td);(p/'p.cpp').write_text(prefix+body+main)
   c=subprocess.run(['c++','-std=c++20',str(p/'p.cpp'),'-o',str(p/'p')],capture_output=True,text=True)
   self.assertEqual(c.returncode,0,c.stderr)
   r=subprocess.run([str(p/'p')],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
