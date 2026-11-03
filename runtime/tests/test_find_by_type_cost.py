"""Run the production type query/iterators; retain fresh results with fewer reads."""
from pathlib import Path
import subprocess,tempfile,unittest
from .test_support import lua_harness_objects
from .test_lua_api_method_lookup_cost import function
ROOT=Path(__file__).resolve().parents[2]

class FindByTypeCostTests(unittest.TestCase):
 def test_type_query_skips_spatial_reads_and_duplicate_pointer_validation(self):
  source=(ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
  def template(name):
   pos=source.index(name);return source[source.rfind('template <',0,pos):pos]+function(source,name)
  body=source[source.index('struct EntitySnapshot {'):source.index('\nbool CaptureEntity',source.index('struct EntitySnapshot {'))]
  if 'bool CaptureEntityTypeSnapshot('in source:body+=function(source,'bool CaptureEntityTypeSnapshot(')
  body+=function(source,'bool EntityHasNoQueryFlag(')
  body+=template('void ForEachEntityInTable(')+template('void ForEachPlayerEntity(')
  body+=function(source,'int IsaacFindByType(lua_State* state) {')
  prefix=r'''
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <set>
#include <vector>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
constexpr unsigned kEntitySnapshotSpan=0x348,kEntityFlagsOffset=0x1b8,kEntityTypeOffset=0x38,kEntityVariantOffset=0x3c,kEntitySubTypeOffset=0x40,kEntityIndexOffset=0x44,kEntityPositionOffset=0x100,kEntitySizeOffset=0x344,kEntityFlagNoQueryBit=46;
constexpr unsigned kRoomEntityListOffset=0,kGamePlayerArrayBeginOffset=0x20,kGamePlayerArrayEndOffset=0x28,kEnginePlayerMaximumCount=16;
std::array<unsigned char,0x348> a{},b{},c{},bad{};std::array<unsigned char,64>game{};
std::vector<std::uintptr_t>live,effects,players;std::set<std::uintptr_t>seen;
unsigned spatialReads=0,pointerChecks=0;
bool IsEngineMemoryReadable(std::uintptr_t p,std::size_t){return p!=0;}
bool IsEntityVtableInRange(std::uintptr_t p){return p==0x1234;}
template<class T>bool ReadEngineUnchecked(std::uintptr_t p,T*v){
 for(auto*e:{&a,&b,&c,&bad})for(auto offset:{kEntityPositionOffset,kEntityPositionOffset+4,kEntitySizeOffset})if(p==reinterpret_cast<std::uintptr_t>(e->data())+offset)++spatialReads;
 std::memcpy(v,reinterpret_cast<void*>(p),sizeof(T));return true;
}
template<class T>bool ReadEngine(std::uintptr_t p,T*v){return ReadEngineUnchecked(p,v);}
bool IsEntityPointer(std::uintptr_t p){++pointerChecks;std::uintptr_t v;std::memcpy(&v,reinterpret_cast<void*>(p),8);return IsEntityVtableInRange(v);}
struct EntityTableSpec{int id;};constexpr EntityTableSpec kLiveEntityTable{0},kEffectEntityTable{1};
struct EntityTableView{std::uintptr_t begin;std::uint32_t count;};
bool ReadEntityTable(std::uintptr_t,const EntityTableSpec&s,EntityTableView*v){auto&t=s.id?effects:live;v->begin=reinterpret_cast<std::uintptr_t>(t.data());v->count=t.size();return true;}
std::uintptr_t ResolveGameAddress(){return reinterpret_cast<std::uintptr_t>(game.data());}
std::uintptr_t ResolveRoom(){return 1;}bool EntityListFingerprintMatches(std::uintptr_t){return true;}
void RecordApiSequence(unsigned){}void ResetQueryDedup(){seen.clear();}
bool ReadIntegerArgument(lua_State*L,int i,lua_Integer*v){int valid=0;*v=lua_tointegerx(L,i,&valid);return valid;}
struct QuerySink{lua_State*state;int resultIndex;int emitted;};
void PushQueryResult(QuerySink*s,std::uintptr_t p){if(seen.insert(p).second){lua_pushlightuserdata(s->state,reinterpret_cast<void*>(p));lua_rawseti(s->state,s->resultIndex,++s->emitted);}}
template<class T>void write(std::array<unsigned char,0x348>&e,unsigned offset,T value){std::memcpy(e.data()+offset,&value,sizeof(value));}
int mutate(lua_State*){write(c,0x3c,std::uint32_t(470));return 0;}
'''
  main=r'''
int main(){
 for(auto*e:{&a,&b,&c,&bad}){write(*e,0,std::uintptr_t(0x1234));write(*e,0x38,std::uint32_t(160));write(*e,0x3c,std::uint32_t(470));}
 write(b,0x1b8,std::uint64_t(1ULL<<46));write(c,0x3c,std::uint32_t(9));write(bad,0,std::uintptr_t(9));
 auto addr=[](auto&e){return reinterpret_cast<std::uintptr_t>(e.data());};
 live={addr(a),0,addr(b),addr(bad)};effects={addr(c)};players={addr(a)};
 auto begin=reinterpret_cast<std::uintptr_t>(players.data()),end=begin+8;std::memcpy(game.data()+0x20,&begin,8);std::memcpy(game.data()+0x28,&end,8);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 lua_pushcfunction(L,IsaacFindByType);lua_setglobal(L,"query");lua_pushcfunction(L,mutate);lua_setglobal(L,"mutate");
 const char*s="local a=query(160,-1,-1,true,false);assert(#a==2);a[1]='changed';local b=query(160,470,0,false,false);assert(#b==1);mutate();assert(#query(160,470,0,true,false)==2);assert(#query(-1)==0)";
 if(luaL_loadstring(L,s)||lua_pcall(L,0,0,0)){std::fprintf(stderr,"%s",lua_tostring(L,-1));return 2;}
 if(spatialReads){std::fprintf(stderr,"type query read unused spatial fields %u times",spatialReads);return 3;}
 if(pointerChecks){std::fprintf(stderr,"type query repeated pointer validation %u times",pointerChecks);return 4;}
 lua_close(L);return 0;}
'''
  with tempfile.TemporaryDirectory(prefix='type-query-cost-')as tmp:
   folder=Path(tmp);cpp=folder/'query.cpp';cpp.write_text(prefix+body+main)
   objects=lua_harness_objects(ROOT/'runtime/source',folder)
   result=subprocess.run(['c++','-std=c++17','-I'+str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(cpp),*[str(p)for p in objects],'-o',str(folder/'query')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(folder/'query')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
