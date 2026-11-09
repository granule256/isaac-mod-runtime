"""A callback changing rooms must stop iteration before reading the old table again."""
from pathlib import Path
import subprocess,tempfile,unittest
from .test_lua_api_method_lookup_cost import function
ROOT=Path(__file__).resolve().parents[2]
class EntityCallbackIterationScopeTests(unittest.TestCase):
 def test_room_change_cancels_live_and_player_iteration_before_next_read(self):
  text=(ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
  def templ(name):
   p=text.index(name);return text[text.rfind('template <',0,p):p]+function(text,name)
  body=templ('void ForEachEntityInTable(')+templ('void ForEachPlayerEntity(')
  body+=function(text,'void VisitRoomEntities(')+function(text,'void VisitPlayerEntities(')
  pre=r'''
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <type_traits>
#include <cstdio>
using EntityVisitFn=void(*)(void*,std::uintptr_t);
constexpr unsigned kRoomEntityListOffset=0,kGamePlayerArrayBeginOffset=8,kGamePlayerArrayEndOffset=16,kEnginePlayerMaximumCount=16;
struct EntityTableSpec{};constexpr EntityTableSpec kLiveEntityTable{};
struct EntityTableView{std::uintptr_t begin;std::uint32_t count;};
std::uintptr_t entries[]={0x1111,0x2222,0x3333};
std::uint64_t roomGeneration=1,levelGeneration=1;bool changed=false;
unsigned calls=0,readsAfterChange=0;
std::uint64_t NativeRoomLoadStartGeneration(){return roomGeneration;}
std::uint64_t NativeLevelInitGeneration(){return levelGeneration;}
bool NativeLevelInitializing(){return false;}
std::uintptr_t ResolveRoom(){return 1;}
std::uintptr_t ResolveGameAddress(){return 0x1234;}
bool EntityListFingerprintMatches(std::uintptr_t){return true;}
bool IsEngineMemoryReadable(std::uintptr_t,std::size_t){return true;}
bool IsEntityPointer(std::uintptr_t){return true;}
bool ReadEntityTable(std::uintptr_t,const EntityTableSpec&,EntityTableView*v){v->begin=reinterpret_cast<std::uintptr_t>(entries);v->count=3;return true;}
template<class T>bool ReadEngineUnchecked(std::uintptr_t p,T*v){if(changed){++readsAfterChange;return false;}std::memcpy(v,reinterpret_cast<void*>(p),sizeof(T));return true;}
bool ReadEngine(std::uintptr_t p,std::uintptr_t*v){*v=reinterpret_cast<std::uintptr_t>(entries)+(p==0x1234+16?sizeof(entries):0);return true;}
void ChangeRoom(void*,std::uintptr_t){++calls;++roomGeneration;changed=true;}
'''
  main=r'''
int main(){
 VisitRoomEntities(ChangeRoom,nullptr);
 if(calls!=1||readsAfterChange){std::fprintf(stderr,"room visits=%u old-table reads=%u",calls,readsAfterChange);return 1;}
 calls=readsAfterChange=0;changed=false;
 VisitPlayerEntities(ChangeRoom,nullptr);
 if(calls!=1||readsAfterChange){std::fprintf(stderr,"player visits=%u old-table reads=%u",calls,readsAfterChange);return 2;}
 return 0;
}
'''
  with tempfile.TemporaryDirectory(prefix='entity-iteration-')as tmp:
   p=Path(tmp);(p/'scope.cpp').write_text(pre+body+main)
   r=subprocess.run(['c++','-std=c++17',str(p/'scope.cpp'),'-o',str(p/'scope')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(p/'scope')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
