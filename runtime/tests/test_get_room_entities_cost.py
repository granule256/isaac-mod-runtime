"""Execute the production room query; scan the live table once with fresh results."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_lua_api_method_lookup_cost import function
from .test_support import lua_harness_objects

ROOT = Path(__file__).resolve().parents[2]


class GetRoomEntitiesCostTests(unittest.TestCase):
    def test_live_table_is_the_only_source_and_mutations_are_immediate(self):
        source = (ROOT / "runtime/src/interfaces/lua/isaac_api.cpp").read_text()

        def template(name):
            pos = source.index(name)
            return source[source.rfind("template <", 0, pos):pos] + function(source, name)

        body = "\n".join(function(source, name) for name in (
            "[[nodiscard]] inline std::size_t QueryDedupSlot(",
            "void ResetQueryDedup(",
            "bool QueryRecordUnique(",
            "void PushQueryResult(",
        ))
        body += template("void ForEachEntityInTable(")
        body += template("void ForEachPlayerEntity(")
        body += function(source, "int IsaacGetRoomEntities(lua_State* state) {")
        prefix = r'''
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
constexpr std::size_t kMaximumQueryResults=4096,kQueryDedupSlots=8192;
std::array<std::uintptr_t,kQueryDedupSlots>g_QuerySeen{};
std::array<unsigned,kQueryDedupSlots>g_QuerySeenEpoch{};
unsigned g_QueryEpoch=0;std::size_t g_QuerySeenCount=0;
int g_RoomEntityQueryCapacity=0;
constexpr const char*kEntityMetatable="Entity";
constexpr unsigned kRoomEntityListOffset=0,kGamePlayerArrayBeginOffset=0x20,kGamePlayerArrayEndOffset=0x28,kEnginePlayerMaximumCount=16;
struct Entity{std::uintptr_t vptr=0x1234;unsigned type=0;std::uint64_t flags=0;};
std::array<Entity,4100>entities{};Entity spawned{},stale{};
std::vector<std::uintptr_t>live,effects,players;
std::array<unsigned char,64>game{};
unsigned pointerChecks=0,liveTableReads=0,effectTableReads=0,playerVectorReads=0;
bool roomAvailable=true,fingerprintMatches=true;
std::uintptr_t address(Entity&e){return reinterpret_cast<std::uintptr_t>(&e);}
bool IsEngineMemoryReadable(std::uintptr_t p,std::size_t){return p!=0;}
template<class T>bool ReadEngineUnchecked(std::uintptr_t p,T*v){std::memcpy(v,reinterpret_cast<void*>(p),sizeof(T));return true;}
template<class T>bool ReadEngine(std::uintptr_t p,T*v){++playerVectorReads;return ReadEngineUnchecked(p,v);}
bool IsEntityPointer(std::uintptr_t p){++pointerChecks;return reinterpret_cast<Entity*>(p)->vptr==0x1234;}
struct EntityTableSpec{int id;};constexpr EntityTableSpec kLiveEntityTable{0},kEffectEntityTable{1};
struct EntityTableView{std::uintptr_t begin;std::uint32_t count;};
bool ReadEntityTable(std::uintptr_t,const EntityTableSpec&s,EntityTableView*v){
 if(s.id)++effectTableReads;else ++liveTableReads;
 auto&t=s.id?effects:live;v->begin=reinterpret_cast<std::uintptr_t>(t.data());v->count=t.size();return true;
}
std::uintptr_t ResolveGameAddress(){return reinterpret_cast<std::uintptr_t>(game.data());}
std::uintptr_t ResolveRoom(){return roomAvailable?1:0;}
bool EntityListFingerprintMatches(std::uintptr_t){return fingerprintMatches;}
struct QuerySink{lua_State*state;int resultIndex;int emitted;};
void PushEntityHandle(lua_State*L,std::uintptr_t p,const char*){lua_pushlightuserdata(L,reinterpret_cast<void*>(p));}
int spawn(lua_State*){live.push_back(address(spawned));return 0;}
int removeSpawn(lua_State*){live.erase(std::remove(live.begin(),live.end(),address(spawned)),live.end());return 0;}
int removeEffect(lua_State*){live.erase(std::remove(live.begin(),live.end(),address(entities[1])),live.end());return 0;}
int exclude(lua_State*){entities[0].flags=1ULL<<46;return 0;}
'''
        main = r'''
int main(){
 entities[0].type=1;
 for(unsigned i=0;i<100;++i){live.push_back(address(entities[i]));if(i>0&&i<=80){entities[i].type=1000;effects.push_back(address(entities[i]));}}
 players={address(entities[0])};
 auto begin=reinterpret_cast<std::uintptr_t>(players.data()),end=begin+sizeof(std::uintptr_t);
 std::memcpy(game.data()+0x20,&begin,sizeof(begin));std::memcpy(game.data()+0x28,&end,sizeof(end));
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 lua_pushcfunction(L,IsaacGetRoomEntities);
 if(lua_pcall(L,0,1,0))return 1;
 if(lua_rawlen(L,-1)!=100)return 2;
 for(unsigned i=0;i<100;++i){lua_rawgeti(L,-1,i+1);if(reinterpret_cast<std::uintptr_t>(lua_touserdata(L,-1))!=live[i])return 3;lua_pop(L,1);}
 lua_pop(L,1);
 if(pointerChecks!=100||liveTableReads!=1||effectTableReads||playerVectorReads){
  std::fprintf(stderr,"100 live entities required %u pointer validations, %u live reads, %u effect reads and %u player reads",pointerChecks,liveTableReads,effectTableReads,playerVectorReads);return 4;
 }
 // The effect collision snapshot may retain a removed pointer absent from live.
 effects.push_back(address(stale));
 lua_pushcfunction(L,IsaacGetRoomEntities);lua_setglobal(L,"query");
 for(auto entry:{std::pair<const char*,lua_CFunction>{"spawn",spawn},{"removeSpawn",removeSpawn},{"removeEffect",removeEffect},{"exclude",exclude}}){lua_pushcfunction(L,entry.second);lua_setglobal(L,entry.first);}
 const char*script=R"lua(
 local first=query();local second=query()
 assert(#first==100 and #second==100,'stale collision snapshot must not add entities')
 assert(first~=second and first[1]==second[1] and first[100]==second[100])
 first[1]='changed';assert(query()[1]==second[1],'each query owns a fresh array')
 spawn();assert(#query()==101,'same-callback spawn must be visible')
 removeSpawn();assert(#query()==100,'same-callback remove must be visible')
 removeEffect();assert(#query()==99,'removed effect must not return from snapshot')
 exclude();assert(#query()==99 and query()[1]==second[1],'GetRoomEntities includes NO_QUERY entities')
 local ok=pcall(query,1);assert(not ok,'arguments must still be rejected')
 )lua";
 if(luaL_dostring(L,script)){std::fprintf(stderr,"%s",lua_tostring(L,-1));return 5;}
 // Exercise the production sink's deduplication and 4096-result bound.
 live.clear();effects.clear();players.clear();
 for(auto&e:entities){live.push_back(address(e));live.push_back(address(e));}
 lua_pushcfunction(L,IsaacGetRoomEntities);
 if(lua_pcall(L,0,1,0)||lua_rawlen(L,-1)!=4096)return 6;
 for(unsigned i=0;i<4096;++i){lua_rawgeti(L,-1,i+1);if(reinterpret_cast<std::uintptr_t>(lua_touserdata(L,-1))!=address(entities[i]))return 7;lua_pop(L,1);}
 lua_pop(L,1);
 for(unsigned mode=0;mode<2;++mode){roomAvailable=mode!=0;fingerprintMatches=false;lua_pushcfunction(L,IsaacGetRoomEntities);if(lua_pcall(L,0,1,0)||lua_rawlen(L,-1)!=0)return 8;lua_pop(L,1);}
 lua_close(L);return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="room-query-cost-") as tmp:
            folder = Path(tmp)
            cpp = folder / "query.cpp"
            cpp.write_text(prefix + body + main)
            objects = lua_harness_objects(ROOT / "runtime/source", folder)
            result = subprocess.run([
                "c++", "-std=c++17",
                "-I" + str(ROOT / "runtime/source/third_party/lua-5.3.3/src"),
                str(cpp), *(str(path) for path in objects), "-o", str(folder / "query"),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(folder / "query")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
