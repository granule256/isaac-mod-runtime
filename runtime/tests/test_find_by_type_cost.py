"""Run the production type query/iterators; retain fresh results with fewer reads."""
import json
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
#include <algorithm>
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
std::array<unsigned char,0x348> a{},b{},c{},bad{},player{},spawned{};std::array<unsigned char,64>game{};
std::vector<std::uintptr_t>live,effects,players;std::set<std::uintptr_t>seen;
unsigned spatialReads=0,pointerChecks=0;
unsigned effectTableReads=0,playerVectorReads=0;
std::array<std::array<unsigned char,0x348>,256> crowd{};
bool measuring=false;unsigned fieldReads=0,unneededReads=0;
int requestedType=0,requestedVariant=-1,requestedSubType=-1;
bool IsEngineMemoryReadable(std::uintptr_t p,std::size_t){return p!=0;}
bool IsEntityVtableInRange(std::uintptr_t p){return p==0x1234;}
template<class T>bool ReadEngineUnchecked(std::uintptr_t p,T*v){
 if(measuring){
  auto begin=reinterpret_cast<std::uintptr_t>(crowd.data()),end=begin+sizeof(crowd);
  if(p>=begin&&p<end){
   ++fieldReads;auto offset=(p-begin)%0x348;
   const auto& e=crowd[(p-begin)/0x348];std::uint32_t type,variant,sub;
   std::memcpy(&type,e.data()+0x38,4);std::memcpy(&variant,e.data()+0x3c,4);std::memcpy(&sub,e.data()+0x40,4);
   if((offset==0x3c&&(type!=requestedType||requestedVariant<0))||
      (offset==0x40&&(type!=requestedType||(requestedVariant>=0&&variant!=requestedVariant)||requestedSubType<0))||
      (offset==0x1b8&&(type!=requestedType||(requestedVariant>=0&&variant!=requestedVariant)||(requestedSubType>=0&&sub!=requestedSubType))))++unneededReads;
  }
 }
 for(auto*e:{&a,&b,&c,&bad})for(auto offset:{kEntityPositionOffset,kEntityPositionOffset+4,kEntitySizeOffset})if(p==reinterpret_cast<std::uintptr_t>(e->data())+offset)++spatialReads;
 std::memcpy(v,reinterpret_cast<void*>(p),sizeof(T));return true;
}
template<class T>bool ReadEngine(std::uintptr_t p,T*v){if(p==reinterpret_cast<std::uintptr_t>(game.data())+0x20||p==reinterpret_cast<std::uintptr_t>(game.data())+0x28)++playerVectorReads;return ReadEngineUnchecked(p,v);}
bool IsEntityPointer(std::uintptr_t p){++pointerChecks;std::uintptr_t v;std::memcpy(&v,reinterpret_cast<void*>(p),8);return IsEntityVtableInRange(v);}
struct EntityTableSpec{int id;};constexpr EntityTableSpec kLiveEntityTable{0},kEffectEntityTable{1};
struct EntityTableView{std::uintptr_t begin;std::uint32_t count;};
bool ReadEntityTable(std::uintptr_t,const EntityTableSpec&s,EntityTableView*v){if(s.id)++effectTableReads;auto&t=s.id?effects:live;v->begin=reinterpret_cast<std::uintptr_t>(t.data());v->count=t.size();return true;}
std::uintptr_t ResolveGameAddress(){return reinterpret_cast<std::uintptr_t>(game.data());}
std::uintptr_t ResolveRoom(){return 1;}bool EntityListFingerprintMatches(std::uintptr_t){return true;}
void RecordApiSequence(unsigned){}void ResetQueryDedup(){seen.clear();}
bool ReadIntegerArgument(lua_State*L,int i,lua_Integer*v){int valid=0;*v=lua_tointegerx(L,i,&valid);return valid;}
struct QuerySink{lua_State*state;int resultIndex;int emitted;};
void PushQueryResult(QuerySink*s,std::uintptr_t p){if(seen.insert(p).second){lua_pushlightuserdata(s->state,reinterpret_cast<void*>(p));lua_rawseti(s->state,s->resultIndex,++s->emitted);}}
template<class T>void write(std::array<unsigned char,0x348>&e,unsigned offset,T value){std::memcpy(e.data()+offset,&value,sizeof(value));}
int mutate(lua_State*){write(c,0x3c,std::uint32_t(470));return 0;}
int spawn(lua_State*){write(spawned,0,std::uintptr_t(0x1234));write(spawned,0x38,std::uint32_t(160));write(spawned,0x3c,std::uint32_t(470));write(spawned,0x40,std::uint32_t(4));live.push_back(reinterpret_cast<std::uintptr_t>(spawned.data()));return 0;}
int removeSpawn(lua_State*){const auto p=reinterpret_cast<std::uintptr_t>(spawned.data());live.erase(std::remove(live.begin(),live.end(),p),live.end());return 0;}
int morph(lua_State*){write(c,0x38,std::uint32_t(1000));write(c,0x3c,std::uint32_t(135));effects={reinterpret_cast<std::uintptr_t>(c.data())};return 0;}
int removeEffect(lua_State*){const auto p=reinterpret_cast<std::uintptr_t>(c.data());live.erase(std::remove(live.begin(),live.end(),p),live.end());return 0;}
int exclude(lua_State*){write(a,0x1b8,std::uint64_t(1ULL<<46));return 0;}
'''
  main=r'''
int main(){
 for(auto*e:{&a,&b,&c,&bad}){write(*e,0,std::uintptr_t(0x1234));write(*e,0x38,std::uint32_t(160));write(*e,0x3c,std::uint32_t(470));}
 write(b,0x1b8,std::uint64_t(1ULL<<46));write(c,0x3c,std::uint32_t(9));write(bad,0,std::uintptr_t(9));
 auto addr=[](auto&e){return reinterpret_cast<std::uintptr_t>(e.data());};
 // PC QueryType415ED0 and NS79718 use live, even for Type1000. The
 // collision-effect table is only a snapshot subset and can retain removals.
 write(player,0,std::uintptr_t(0x1234));write(player,0x38,std::uint32_t(1));
 live={addr(a),0,addr(b),addr(c),addr(bad),addr(player),addr(a)};effects={};players={addr(player)};
 auto begin=reinterpret_cast<std::uintptr_t>(players.data()),end=begin+8;std::memcpy(game.data()+0x20,&begin,8);std::memcpy(game.data()+0x28,&end,8);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 lua_pushcfunction(L,IsaacFindByType);lua_setglobal(L,"query");lua_pushcfunction(L,mutate);lua_setglobal(L,"mutate");
 lua_pushcfunction(L,spawn);lua_setglobal(L,"spawn");lua_pushcfunction(L,removeSpawn);lua_setglobal(L,"removeSpawn");
 lua_pushcfunction(L,morph);lua_setglobal(L,"morph");lua_pushcfunction(L,removeEffect);lua_setglobal(L,"removeEffect");lua_pushcfunction(L,exclude);lua_setglobal(L,"exclude");
 const char*s=R"lua(
 local first=query(160,-1,-1,true,false);assert(#first==2)
 local second=query(160,-1,-1,true,false);assert(first~=second and first[1]==second[1] and first[2]==second[2])
 first[1]='changed';assert(query(160,-1,-1)[1]==second[1])
 assert(#query(1)==1,'player is already in live')
 assert(#query(160,470,0,false,false)==1);mutate();assert(#query(160,470,0,true,false)==2)
 spawn();assert(#query(160,470,-1)==3 and #query(160,470,4)==1)
 removeSpawn();assert(#query(160,470,-1,true)==2)
 morph();assert(#query(160,-1,-1)==1 and #query(1000,135,0)==1,'NPC morph to Type1000 remains in live')
 removeEffect();assert(#query(1000,-1,-1)==0,'removed effect must not return from stale collision table')
 exclude();assert(#query(160)==0,'NO_QUERY changes are immediate')
 assert(#query(-1)==0)
 )lua";
 if(luaL_loadstring(L,s)||lua_pcall(L,0,0,0)){std::fprintf(stderr,"%s",lua_tostring(L,-1));return 2;}
 if(spatialReads){std::fprintf(stderr,"type query read unused spatial fields %u times",spatialReads);return 3;}
 if(pointerChecks){std::fprintf(stderr,"type query repeated pointer validation %u times",pointerChecks);return 4;}
 if(effectTableReads||playerVectorReads){std::fprintf(stderr,"QueryType traversed extra sources: effects=%u players=%u",effectTableReads,playerVectorReads);return 8;}
 struct Scenario{const char*name;unsigned count,queries;int type,variant,sub,layout;};
 const Scenario scenarios[]={
  {"empty",0,16,160,470,-1,0},{"small_room",32,16,160,470,-1,0},
  {"firewhirl_players",256,64,1,-1,-1,0},
  {"glass_eye_projectiles",256,16,9,-1,-1,1},
  {"shaggoth_marker",256,16,1000,1809,4,2},
  {"cordend_explosions",256,64,1000,1,-1,2},
  {"organization_variants",256,64,160,470,-1,0},
  {"same_type_different_subtype",256,16,1000,1809,4,3}
 };
 for(const auto&s:scenarios){
  live.clear();effects.clear();players.clear();
  std::memcpy(game.data()+0x28,&begin,8);
  std::vector<std::uintptr_t> expected;
  for(unsigned i=0;i<s.count;++i){
   auto&e=crowd[i];e.fill(0);write(e,0,std::uintptr_t(0x1234));
   unsigned type=i==0?1:s.layout==1?9:s.layout>=2?1000:i%4==0?160:i%4==1?9:1000;
   unsigned variant=type==160?470+i%3:type==1000?(i%3==0?1:i%3==1?1809:7005):0;
   unsigned sub=i%7==0?4:0;std::uint64_t flags=i%13==12?1ULL<<46:0;
   write(e,0x38,type);write(e,0x3c,variant);write(e,0x40,sub);write(e,0x1b8,flags);
   if(s.layout==3){type=1000;variant=1809;write(e,0x38,type);write(e,0x3c,variant);}
   if(i==s.count-1)write(e,0,std::uintptr_t(9));
   auto ptr=addr(e);live.push_back(ptr);if(type==1000&&i%3==0)effects.push_back(ptr);
  }
  // Independent reference follows the native live-array order.
  for(auto ptr:live){
   const auto*e=reinterpret_cast<const unsigned char*>(ptr);std::uintptr_t vptr;unsigned type,variant,sub;std::uint64_t flags;
   std::memcpy(&vptr,e,8);std::memcpy(&type,e+0x38,4);std::memcpy(&variant,e+0x3c,4);std::memcpy(&sub,e+0x40,4);std::memcpy(&flags,e+0x1b8,8);
   if(vptr==0x1234&&type==s.type&&(s.variant<0||variant==s.variant)&&(s.sub<0||sub==s.sub)&&!(flags&(1ULL<<46)))expected.push_back(ptr);
  }
  fieldReads=unneededReads=effectTableReads=playerVectorReads=0;requestedType=s.type;requestedVariant=s.variant;requestedSubType=s.sub;measuring=true;
  for(unsigned q=0;q<s.queries;++q){
   lua_pushcfunction(L,IsaacFindByType);lua_pushinteger(L,s.type);lua_pushinteger(L,s.variant);lua_pushinteger(L,s.sub);lua_pushboolean(L,q%2);lua_pushboolean(L,0);
   if(lua_pcall(L,5,1,0)){std::fprintf(stderr,"%s",lua_tostring(L,-1));return 5;}
   if(lua_rawlen(L,-1)!=expected.size())return 6;
   for(unsigned i=0;i<expected.size();++i){lua_rawgeti(L,-1,i+1);if(reinterpret_cast<std::uintptr_t>(lua_touserdata(L,-1))!=expected[i])return 7;lua_pop(L,1);}
   lua_pushnil(L);lua_rawseti(L,-2,1);lua_pop(L,1);
  }
  measuring=false;
  if(effectTableReads||playerVectorReads)return 8;
  std::printf("{\"scenario\":\"%s\",\"candidates\":%u,\"queries\":%u,\"field_reads\":%u,\"unneeded_reads\":%u,\"extra_source_reads\":%u}\n",s.name,s.count,s.queries,fieldReads,unneededReads,effectTableReads+playerVectorReads);
 }
 lua_close(L);return 0;}
'''
  with tempfile.TemporaryDirectory(prefix='type-query-cost-')as tmp:
   folder=Path(tmp);cpp=folder/'query.cpp';cpp.write_text(prefix+body+main)
   objects=lua_harness_objects(ROOT/'runtime/source',folder)
   result=subprocess.run(['c++','-std=c++17','-I'+str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(cpp),*[str(p)for p in objects],'-o',str(folder/'query')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   result=subprocess.run([str(folder/'query')],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   for line in result.stdout.splitlines():
    cost=json.loads(line)
    print(cost)
    with self.subTest(scenario=cost['scenario']):
     self.assertEqual(cost['unneeded_reads'],0)
     self.assertEqual(cost['extra_source_reads'],0)
