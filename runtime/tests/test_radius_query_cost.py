"""Exercise production radius queries with a repeated fire-collision workload."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_lua_api_method_lookup_cost import function
from .test_support import lua_harness_objects

ROOT = Path(__file__).resolve().parents[2]

PREFIX = r'''
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
constexpr unsigned kEntitySnapshotSpan=0x348, kEntityFlagsOffset=0x1b8,
 kEntityTypeOffset=0x38, kEntityVariantOffset=0x3c, kEntitySubTypeOffset=0x40,
 kEntityIndexOffset=0x30, kEntityPositionOffset=0x100, kEntitySizeOffset=0x344,
 kEntityFlagNoQueryBit=46, kEntityTypeEffect=1000, kEntityTypePlayer=1,
 kEntityEnemyTypeBase=10, kEntityEnemyTypeSpan=990, kRoomEntityListOffset=0,
 kGamePlayerArrayBeginOffset=0x20, kGamePlayerArrayEndOffset=0x28,
 kEnginePlayerMaximumCount=16;
using Entity = std::array<unsigned char, kEntitySnapshotSpan>;
std::array<Entity, 260> entities{};
std::array<unsigned char, 64> game{};
std::vector<std::uintptr_t> live, effects, players, seen;
unsigned pointerChecks=0, indexReads=0, spatialReads=0, excludedSpatialReads=0;
bool measure=false, roomValid=true;
std::array<bool, 260> excluded{};
std::uintptr_t address(unsigned i) {return reinterpret_cast<std::uintptr_t>(entities[i].data());}
bool IsEngineMemoryReadable(std::uintptr_t p, std::size_t) {return p && p!=address(259);}
bool IsEntityVtableInRange(std::uintptr_t p) {return p==0x1234;}
template<class T> bool ReadEngineUnchecked(std::uintptr_t p, T* value) {
 if(measure) for(unsigned i=0;i<entities.size();++i) {
  if(p==address(i)+kEntityIndexOffset) ++indexReads;
  if(p==address(i)+kEntityPositionOffset || p==address(i)+kEntityPositionOffset+4 ||
     p==address(i)+kEntitySizeOffset) {++spatialReads;if(excluded[i])++excludedSpatialReads;}
 }
 std::memcpy(value,reinterpret_cast<void*>(p),sizeof(T));return true;
}
template<class T> bool ReadEngine(std::uintptr_t p, T* value) {
 return IsEngineMemoryReadable(p,sizeof(T)) && ReadEngineUnchecked(p,value);
}
bool IsEntityPointer(std::uintptr_t p) {
 if(measure)++pointerChecks;
 std::uintptr_t v=0;return ReadEngine(p,&v)&&IsEntityVtableInRange(v);
}
struct EntityTableSpec {int id;};
constexpr EntityTableSpec kLiveEntityTable{0}, kEffectEntityTable{1};
struct EntityTableView {std::uintptr_t begin;std::uint32_t count;};
bool ReadEntityTable(std::uintptr_t,const EntityTableSpec& spec,EntityTableView* view) {
 auto& table=spec.id?effects:live;
 *view={reinterpret_cast<std::uintptr_t>(table.data()),static_cast<std::uint32_t>(table.size())};
 return true;
}
std::uintptr_t ResolveGameAddress() {return reinterpret_cast<std::uintptr_t>(game.data());}
std::uintptr_t ResolveRoom() {return roomValid?1:0;}
bool EntityListFingerprintMatches(std::uintptr_t) {return true;}
void RecordApiSequence(unsigned) {}
void ResetQueryDedup() {seen.clear();}
bool ReadIntegerArgument(lua_State* L,int i,lua_Integer* v) {
 int valid=0;*v=lua_tointegerx(L,i,&valid);return valid;
}
struct QuerySink {lua_State* state;int resultIndex;int emitted;};
void PushQueryResult(QuerySink* sink,std::uintptr_t p) {
 for(auto old:seen)if(old==p)return;
 seen.push_back(p);lua_pushinteger(sink->state,(p-address(0))/sizeof(Entity));
 lua_rawseti(sink->state,sink->resultIndex,++sink->emitted);
}
struct Vector {float x,y;};
Vector* TryVectorArgument(lua_State* L,int i) {return static_cast<Vector*>(lua_touserdata(L,i));}
std::atomic<unsigned> g_FindInRadiusCalls{},g_FindInRadiusLastMask{},g_FindInRadiusLastRadius{},
 g_FindInRadiusResults{},g_FindInRadiusRoomOk{},g_FindInRadiusFingerprint{},
 g_FindInRadiusLive{},g_FindInRadiusPlayers{},g_FindInRadiusEffects{};
template<class T>void write(unsigned i,unsigned offset,T value) {
 std::memcpy(entities[i].data()+offset,&value,sizeof(T));
}
int mutate(lua_State*) {
 write(0,kEntityPositionOffset,100.0F);write(1,kEntityFlagsOffset,std::uint64_t(1ULL<<46));
 return 0;
}
'''

MAIN = r'''
int main() {
 for(unsigned i=0;i<entities.size();++i) {
  write(i,0,std::uintptr_t(0x1234));write(i,kEntityTypeOffset,std::uint32_t(9));
  write(i,kEntityPositionOffset,0.0F);write(i,kEntityPositionOffset+4,0.0F);
  write(i,kEntitySizeOffset,4.0F);excluded[i]=true;
 }
 // Two enemies, a player duplicated across tables, an exact boundary and a large enemy.
 for(unsigned i:{0U,1U,3U,4U}) {write(i,kEntityTypeOffset,std::uint32_t(160));excluded[i]=false;}
 write(2,kEntityTypeOffset,std::uint32_t(1));excluded[2]=false;
 write(3,kEntityPositionOffset,24.0F);
 write(4,kEntityPositionOffset,30.0F);write(4,kEntitySizeOffset,11.0F);
 write(5,kEntityTypeOffset,std::uint32_t(160));write(5,kEntityFlagsOffset,std::uint64_t(1ULL<<46));
 write(258,0,std::uintptr_t(9));
 for(unsigned i=0;i<256;++i)live.push_back(address(i));
 live.push_back(0);live.push_back(address(258));live.push_back(address(259));
 // Fire effects are deliberately absent from the live table, as in the engine.
 write(256,kEntityTypeOffset,std::uint32_t(1000));effects.push_back(address(256));
 players.push_back(address(2));
 auto begin=reinterpret_cast<std::uintptr_t>(players.data()),end=begin+sizeof(std::uintptr_t);
 std::memcpy(game.data()+0x20,&begin,sizeof(begin));std::memcpy(game.data()+0x28,&end,sizeof(end));
 auto* L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 Vector center{0,0};lua_pushlightuserdata(L,&center);lua_setglobal(L,"center");
 lua_pushcfunction(L,IsaacFindInRadius);lua_setglobal(L,"query");
 lua_pushcfunction(L,mutate);lua_setglobal(L,"mutate");
 const char* script=R"lua(
  for fire=1,96 do
   local found=query(center,20,8|32)
   assert(#found==4 and found[1]==0 and found[2]==1 and found[3]==2 and found[4]==4)
   found[1]='modified'
  end
 )lua";
 measure=true;
 if(luaL_dostring(L,script)) {std::fprintf(stderr,"%s",lua_tostring(L,-1));return 1;}
 measure=false;
 // Position and query flags may change between queries in the same callback.
 if(luaL_dostring(L,R"lua(
  mutate();local found=query(center,20,8|32)
  assert(#found==2 and found[1]==2 and found[2]==4)
  assert(#query(center,20,64)==1)
  assert(#query(center,20,0)==0)
  assert(#query(center,-1,8)==0)
 )lua")) {std::fprintf(stderr,"%s",lua_tostring(L,-1));return 2;}
 roomValid=false;
 if(luaL_dostring(L,"assert(#query(center,20,8|32)==0)"))return 3;
 std::printf("{\"pointer_checks\":%u,\"index_reads\":%u,\"spatial_reads\":%u,"
             "\"excluded_spatial_reads\":%u}\n",pointerChecks,indexReads,spatialReads,excludedSpatialReads);
 lua_close(L);return 0;
}
'''


class RadiusQueryCostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / 'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
        start = source.index('struct EntitySnapshot {')
        body = source[start:source.index('\nbool CaptureEntity', start)]
        body += source[source.index('constexpr std::uint32_t kPartitionFamiliar ='):
                       source.index('// 分类判据：')]
        for name in ('bool CaptureEntityTypeSnapshot(',
                     'bool EntityHasNoQueryFlag(', 'std::uint32_t ClassifyEntity(',
                     'bool EntityMatchesRadius(', 'bool EntityMatchesRadiusQuery('):
            body += function(source, name) + '\n'
        for name in ('void ForEachEntityInTable(', 'void ForEachPlayerEntity('):
            pos = source.index(name)
            body += source[source.rfind('template <', 0, pos):pos] + function(source, name) + '\n'
        body += function(source, 'int IsaacFindInRadius(lua_State* state) {')
        cls.work = tempfile.TemporaryDirectory(prefix='radius-query-cost-')
        folder = Path(cls.work.name)
        cpp = folder / 'query.cpp'
        cpp.write_text(PREFIX + body + MAIN)
        objects = lua_harness_objects(ROOT / 'runtime/source', folder)
        binary = folder / 'query'
        compiled = subprocess.run(['c++', '-std=c++17', '-O2',
                        '-I' + str(ROOT / 'runtime/source/third_party/lua-5.3.3/src'),
                        str(cpp), *map(str, objects), '-o', str(binary)],
                       capture_output=True, text=True)
        if compiled.returncode:
            raise AssertionError(compiled.stdout + compiled.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.cost = json.loads(result.stdout)
        print('96 fire collision queries:', cls.cost)

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def test_each_candidate_is_validated_once(self):
        self.assertEqual(self.cost['pointer_checks'], 0)

    def test_excluded_entities_need_no_spatial_reads(self):
        self.assertEqual(self.cost['excluded_spatial_reads'], 0)

    def test_radius_query_does_not_read_unused_entity_index(self):
        self.assertEqual(self.cost['index_reads'], 0)


if __name__ == '__main__':
    unittest.main()
