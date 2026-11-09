"""Run production cached query bridging against a mutable native arena model."""
from pathlib import Path
import subprocess,tempfile,unittest
from .test_lua_api_method_lookup_cost import function
from .test_support import lua_harness_objects
ROOT=Path(__file__).resolve().parents[2]

class NativeTypeQueryCacheTests(unittest.TestCase):
 def test_native_cache_snapshot_fallback_and_invalidation(self):
  source=(ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
  self.assertTrue('bool TryPushNativeCachedTypeQuery(' in source,'native cached query is not implemented')
  start=source.index('struct NativeEntityTypeQueryResult {')
  abi=source[start:source.index('\n};',start)+3]
  def templ(name):
   pos=source.index(name);return source[source.rfind('template <',0,pos):pos]+function(source,name)
  body=abi+'\n'+function(source,'bool TryPushNativeCachedTypeQuery(')+'\n'
  body+=templ('void ForEachEntityInTable(')+'\n'+function(source,'int IsaacFindByType(lua_State* state) {')+'\n'
  body+=function(source,'void InvalidateNativeEntityTypeQueries(std::uintptr_t entity) noexcept {')+'\n'+templ('bool MutateEntityFlags(')
  pre=r'''
#include <array>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <tuple>
#include <vector>
#include <limits>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
constexpr unsigned kEntitySnapshotSpan=0x348,kEntityFlagsOffset=0x1b8,kEntityTypeOffset=0x38,kEntityVariantOffset=0x3c,kEntitySubTypeOffset=0x40,kEntityFlagNoQueryBit=46,kRoomEntityListOffset=0;
constexpr unsigned kMaximumQueryResults=4096,kEntityListQueryTypeOffset=1,kEntityListInvalidateQueryOffset=2;
constexpr std::array<unsigned char,16>kEntityListQueryTypeExpectedBytes{},kEntityListInvalidateQueryExpectedBytes{};
constexpr const char*kEntityMetatable="Entity";
struct NativeEntityTypeQueryResult;
NativeEntityTypeQueryResult Query(std::uintptr_t,int,int,int,bool,bool);
void Invalidate(std::uintptr_t,int,int,int);
void InvalidateNativeEntityTypeQueries(std::uintptr_t)noexcept;
int IsaacFindByType(lua_State*);
namespace engine_call {template<class F>F AsFunction(std::uintptr_t p){return reinterpret_cast<F>(p);}}
namespace engine_memory {inline void*AsObject(std::uintptr_t p){return reinterpret_cast<void*>(p);}}
struct EntityTableSpec{};constexpr EntityTableSpec kLiveEntityTable{};
struct EntityTableView{std::uintptr_t begin;std::uint32_t count;};
std::vector<std::array<unsigned char,0x348>> entities(4);
std::vector<std::uintptr_t>live,arena;
using Key=std::tuple<int,int,int>;std::map<Key,std::vector<std::uintptr_t>>cached;
int nativeCalls=0,scans=0,invalidations=0,scratchAllocations=0;bool available=true;int badResult=0;
std::uintptr_t room=1;bool nested=false,scratchRoomChange=false;
std::uintptr_t ResolveRoom(){return room;}
bool EntityListFingerprintMatches(std::uintptr_t r){return r!=0;}
std::uintptr_t EntityMethodByExpectedBytes(std::uintptr_t o,const std::array<unsigned char,16>&){return !available?0:o==1?reinterpret_cast<std::uintptr_t>(Query):reinterpret_cast<std::uintptr_t>(Invalidate);}
bool ReadEntityTable(std::uintptr_t,const EntityTableSpec&,EntityTableView*v){v->begin=reinterpret_cast<std::uintptr_t>(live.data());v->count=live.size();return true;}
bool IsEngineMemoryReadable(std::uintptr_t p,std::size_t n){return n==0||p>4096;}
bool IsEntityVtableInRange(std::uintptr_t p){return p==0x1234;}
template<class T>bool ReadEngineUnchecked(std::uintptr_t p,T*v){std::memcpy(v,reinterpret_cast<void*>(p),sizeof(T));return true;}
template<class T>bool ReadEngine(std::uintptr_t p,T*v){return ReadEngineUnchecked(p,v);}
template<class T>bool WriteEngine(std::uintptr_t p,T v){std::memcpy(reinterpret_cast<void*>(p),&v,sizeof(T));return true;}
bool IsEntityPointer(std::uintptr_t p){return std::find(live.begin(),live.end(),p)!=live.end();}
void RecordApiSequence(unsigned){}void ResetQueryDedup(){}
bool ReadIntegerArgument(lua_State*L,int i,lua_Integer*v){int ok=0;*v=lua_tointegerx(L,i,&ok);return ok;}
struct QuerySink{lua_State*state;int resultIndex;int emitted;};
void PushEntityHandle(lua_State*L,std::uintptr_t p,const char*){
 if(nested){nested=false;lua_pushcfunction(L,IsaacFindByType);lua_pushinteger(L,1);lua_pushinteger(L,-1);lua_pushinteger(L,-1);lua_pushboolean(L,1);if(lua_pcall(L,4,1,0))std::abort();lua_pop(L,1);}
 lua_pushlightuserdata(L,reinterpret_cast<void*>(p));
}
void PushQueryResult(QuerySink*s,std::uintptr_t p){PushEntityHandle(s->state,p,kEntityMetatable);lua_rawseti(s->state,s->resultIndex,++s->emitted);}
void*Scratch(lua_State*L,std::size_t n){++scratchAllocations;void*p=lua_newuserdata(L,n);if(scratchRoomChange){scratchRoomChange=false;++room;}return p;}
#define lua_newuserdata Scratch
'''
  post=r'''
#undef lua_newuserdata
NativeEntityTypeQueryResult Query(std::uintptr_t,int t,int v,int s,bool cache,bool ignore){
 ++nativeCalls;if(!cache||ignore)std::abort();Key key{t,v,s};auto it=cached.find(key);
 if(it==cached.end()){
  ++scans;std::vector<std::uintptr_t>a;
  for(auto p:live){unsigned type,var,sub;std::uint64_t flags;ReadEngine(p+0x38,&type);ReadEngine(p+0x3c,&var);ReadEngine(p+0x40,&sub);ReadEngine(p+0x1b8,&flags);if(type==unsigned(t)&&(v<0||var==unsigned(v))&&(s<0||sub==unsigned(s))&&!(flags&(1ULL<<46)))a.push_back(p);}
  it=cached.emplace(key,a).first;
 }
 arena=it->second;NativeEntityTypeQueryResult r{};r.borrowed=1;r.data=reinterpret_cast<std::uintptr_t>(arena.data());r.capacity=arena.size();r.count=arena.size();
 if(badResult==1)r.borrowed=0;if(badResult==2)r.capacity=0;if(badResult==3)r.data=8;if(badResult==4){r.count=live.size()+1;r.capacity=r.count;}
 return r;
}
void Invalidate(std::uintptr_t,int t,int v,int s){++invalidations;cached.erase(Key{t,v,s});cached.erase(Key{t,v,-1});cached.erase(Key{t,-1,-1});}
void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));std::abort();}}
int main(){
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 for(unsigned i=0;i<4;++i){auto p=reinterpret_cast<std::uintptr_t>(entities[i].data());WriteEngine(p,std::uintptr_t(0x1234));WriteEngine(p+0x38,unsigned(i?1000:1));WriteEngine(p+0x3c,unsigned(135));live.push_back(p);}
 lua_pushcfunction(L,IsaacFindByType);lua_setglobal(L,"query");
 Run(L,"first=query(1000,135,0,true);second=query(1000,135,0,true);assert(#first==3 and #second==3 and first~=second);first[1]='changed';assert(query(1000,135,0,true)[1]==second[1])");
 if(nativeCalls!=3||scans!=1)return 2;
 if(scratchAllocations){std::fprintf(stderr,"small queries allocated scratch userdata");return 11;}
 Run(L,"assert(#query(99999,-1,-1,true)==0 and #query(99999,-1,-1,true)==0)");if(scans!=2)return 3;
 nested=true;Run(L,"assert(#query(1000,135,0,true)==3)");if(arena.size()!=1)return 4;
 int n=nativeCalls;
 Run(L,"assert(#query(1000,-1,0,true)==3);assert(#query(3,206,-1,true)==0);assert(#query(1000,135,0,false)==3);assert(#query(1000,135,0,true,true)==3);assert(#query(4294967296,-1,-1,true)==0)");
 if(nativeCalls!=n)return 5;
 available=false;Run(L,"assert(#query(1000,135,0,true)==3)");if(nativeCalls!=n)return 6;available=true;
 for(badResult=1;badResult<=4;++badResult)Run(L,"assert(#query(1000,135,0,true)==3)");badResult=0;
 auto originalLive=live;while(live.size()<300)live.push_back(live[0]);
 scratchRoomChange=true;n=nativeCalls;Run(L,"assert(#query(1000,135,0,true)==3)");if(nativeCalls!=n)return 7;live=originalLive;
 // Direct classification writes invalidate both old and new memberships.
 auto e=live[1];InvalidateNativeEntityTypeQueries(e);WriteEngine(e+0x3c,unsigned(136));InvalidateNativeEntityTypeQueries(e);
 Run(L,"assert(#query(1000,135,0,true)==2);assert(#query(1000,136,0,true)==1)");
 if(!MutateEntityFlags(e,[](std::uint64_t f){return f|(1ULL<<46);}))return 8;
 Run(L,"assert(#query(1000,136,0,true)==0)");
 if(!MutateEntityFlags(e,[](std::uint64_t f){return f&~(1ULL<<46);}))return 9;
 Run(L,"assert(#query(1000,136,0,true)==1)");
 n=invalidations;MutateEntityFlags(e,[](std::uint64_t f){return f|4;});if(invalidations!=n)return 10;
 // Same rules as native Add/Remove, including cached empty memberships.
 auto added=reinterpret_cast<std::uintptr_t>(entities[0].data());Invalidate(room,1,135,0);live.erase(live.begin());
 Run(L,"assert(#query(1,-1,-1,true)==0)");live.push_back(added);Invalidate(room,1,135,0);Run(L,"assert(#query(1,-1,-1,true)==1)");
 // Room/native state reset gives fresh query content.
 cached.clear();++room;Run(L,"assert(#query(1000,136,0,true)==1)");
 lua_close(L);return 0;
}
'''
  with tempfile.TemporaryDirectory(prefix='native-query-')as tmp:
   folder=Path(tmp);cpp=folder/'query.cpp';cpp.write_text(pre+body+post)
   r=subprocess.run(['c++','-std=c++17','-I'+str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(cpp),*map(str,lua_harness_objects(ROOT/'runtime/source',folder)),'-o',str(folder/'query')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   r=subprocess.run([str(folder/'query')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_pickup_reinitialization_invalidates_before_author_callback(self):
  source=(ROOT/'runtime/source/lua_runtime.cpp').read_text()
  body=function(source,'void DispatchNativePickupInit(')
  pre=r'''
#include <cstdint>
bool invalidated=false,delivered=false;
bool IsReady(){return true;}
void*g_LuaState=reinterpret_cast<void*>(1);int g_CallbackRegistry=0;
bool g_NativePickupInitObserved=false;
struct ManagedEngineDispatchScope{};
struct LuaCallbackInvoker{static LuaCallbackInvoker ForEntity(std::uintptr_t){return {};}};
namespace isaac::runtime {
enum class CallbackEntityClass {Pickup};
enum class ThreadAffinity {Any};
constexpr unsigned kCallbackPostPickupInit=34;
CallbackEntityClass ClassifyCallbackEntity(std::uintptr_t,std::int64_t*v){*v=100;return CallbackEntityClass::Pickup;}
void InvalidateNativeEntityTypeQueries(std::uintptr_t){invalidated=true;}
bool BuiltinCallbackEnabled(unsigned){return true;}
struct CallbackDispatcher {
 CallbackDispatcher(int&,LuaCallbackInvoker&){}
 int DispatchFiltered(unsigned,ThreadAffinity,std::int64_t){delivered=invalidated;return 0;}
};
}
'''
  with tempfile.TemporaryDirectory(prefix='pickup-cache-')as tmp:
   folder=Path(tmp);cpp=folder/'pickup.cpp';cpp.write_text(pre+body+'\nint main(){DispatchNativePickupInit(1);return delivered?0:1;}')
   subprocess.run(['c++','-std=c++17',str(cpp),'-o',str(folder/'pickup')],check=True,capture_output=True,text=True)
   r=subprocess.run([str(folder/'pickup')],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,'Pickup Init callback observed stale target cache')

if __name__=='__main__':unittest.main()
