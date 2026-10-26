"""固定PC HomingLaser拥有值：四组非空深复制、真实setter边界与独立身份。

仅注入已验证非抛错同堆allocator pair；不替代getter、setter、guard或提交/回滚逻辑。
主线程负责冻结编译运行，本委派只写测试。
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from . import test_support
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'dist/api-remaining-recovery-20261025'
MAIN=r'''
#include "interfaces/lua/homing_laser_value.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
#include <algorithm>
#include <array>
#include <cassert>
#include <cerrno>
#include <cstdlib>
#include <map>
#include <set>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
constexpr unsigned kNative=0x88,kMember=0x458;
constexpr unsigned offsets[]={0x20,0x38,0x50,0x70},strides[]={8,8,8,24};static unsigned counts[]={2,3,1,2};
struct Triple{std::uintptr_t begin,end,capacity;};static_assert(sizeof(Triple)==24);
static std::array<Triple,4>sourceHeads,targetHeads;
static std::map<std::uintptr_t,std::size_t>gameHeap;
static std::vector<std::size_t>requests;
static std::vector<std::uintptr_t>released;
static unsigned attempts{},failAt{};static bool tracking{};
static std::uintptr_t Source(){return AddressOf(g_Entities[kSizeOnly])+kMember;}
static std::uintptr_t Target(){return AddressOf(g_Entities[kNoQuery])+kMember;}
template<class T>static T Load(std::uintptr_t address){T v{};std::memcpy(&v,reinterpret_cast<const void*>(address),sizeof(v));return v;}
template<class T>static void Store(std::uintptr_t address,const T&v){std::memcpy(reinterpret_cast<void*>(address),&v,sizeof(v));}
static void*GameMalloc(std::size_t size){
 assert(size>0);if(tracking){++attempts;requests.push_back(size);if(failAt&&attempts==failAt){errno=ENOMEM;return nullptr;}}
 void*p=std::malloc(size);assert(p);const auto address=reinterpret_cast<std::uintptr_t>(p);assert(gameHeap.emplace(address,size).second);return p;
}
static void GameFree(void*p){if(!p)return;const auto address=reinterpret_cast<std::uintptr_t>(p);auto it=gameHeap.find(address);assert(it!=gameHeap.end());if(tracking)released.push_back(address);gameHeap.erase(it);std::free(p);}
extern "C" std::uintptr_t HomingOwnedNativeRedirect(std::uintptr_t original)noexcept{
 if(original==g_EngineBase+0x67fdb0)return reinterpret_cast<std::uintptr_t>(&GameMalloc);
 if(original==g_EngineBase+0x67fd80)return reinterpret_cast<std::uintptr_t>(&GameFree);
 return original;
}
struct LuaAllocatorFault{lua_Alloc original;void*context;bool enabled;unsigned rejected;};
static void*LuaAllocateFault(void*raw,void*p,std::size_t oldSize,std::size_t newSize){auto*f=static_cast<LuaAllocatorFault*>(raw);if(f->enabled&&newSize&&newSize>oldSize){++f->rejected;return nullptr;}return f->original(f->context,p,oldSize,newSize);}
static unsigned snapshotEntered{};
static int ReadSnapshotProtected(lua_State*L){++snapshotEntered;lua_getglobal(L,"laser");lua_getfield(L,-1,"HomingLaser");return 1;}
static void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::exit(10);}}
static std::uintptr_t Hash(lua_State*L,int index){const int top=lua_gettop(L);index=lua_absindex(L,index);lua_getglobal(L,"GetPtrHash");lua_pushvalue(L,index);if(lua_pcall(L,1,1,0)!=LUA_OK)std::exit(11);assert(lua_isinteger(L,-1));const auto result=static_cast<std::uintptr_t>(lua_tointeger(L,-1));lua_settop(L,top);return result;}
struct Snapshot{std::uintptr_t native,storage;std::size_t bytes;std::vector<unsigned char> original;std::array<Triple,4> heads;};
static Snapshot Inspect(lua_State*L,const char*name,const std::vector<unsigned char>&native,const std::array<std::vector<unsigned char>,4>&data){
 lua_getglobal(L,name);assert(lua_type(L,-1)==LUA_TUSERDATA);const auto storage=reinterpret_cast<std::uintptr_t>(lua_touserdata(L,-1));const auto size=lua_rawlen(L,-1);const auto hash=Hash(L,-1);
 assert(size>=kNative&&hash>=storage&&hash-storage<=size-kNative);
 bool known=false;const int top=lua_gettop(L);assert(ResolveRegisteredObjectIdentity(L,-1,&known)==hash&&known&&lua_gettop(L)==top);
 assert(!std::memcmp(reinterpret_cast<const void*>(hash),native.data(),0x20));assert(!std::memcmp(reinterpret_cast<const void*>(hash+0x68),native.data()+0x68,8));
 Snapshot out{hash,storage,size,std::vector<unsigned char>(size),{}};std::memcpy(out.original.data(),reinterpret_cast<const void*>(storage),size);
 for(unsigned i=0;i<4;++i){const auto h=Load<Triple>(hash+offsets[i]);out.heads[i]=h;const auto used=counts[i]*strides[i];if(!used){assert(!h.begin&&!h.end&&!h.capacity);continue;}assert(h.begin>=storage&&h.end>=h.begin&&h.end-h.begin==used&&h.capacity==h.end&&h.end-storage<=size);assert(h.end<=hash||h.begin>=hash+kNative);assert(!std::memcmp(reinterpret_cast<const void*>(h.begin),data[i].data(),used));assert(h.begin!=sourceHeads[i].begin&&h.begin!=targetHeads[i].begin);for(unsigned j=0;j<i;++j)assert(h.end<=out.heads[j].begin||h.begin>=out.heads[j].end);}
 lua_pop(L,1);return out;
}
static void Stable(lua_State*L,const char*name,const Snapshot&s){lua_getglobal(L,name);assert(Hash(L,-1)==s.native&&lua_rawlen(L,-1)==s.bytes);assert(!std::memcmp(reinterpret_cast<const void*>(s.storage),s.original.data(),s.bytes));lua_pop(L,1);}
static void NoHeapCalls(){assert(!attempts&&requests.empty()&&released.empty());}
using HeapImage=std::map<std::uintptr_t,std::vector<unsigned char>>;
static HeapImage CaptureHeap(){HeapImage out;for(auto [p,size]:gameHeap)out.emplace(p,std::vector<unsigned char>(reinterpret_cast<const unsigned char*>(p),reinterpret_cast<const unsigned char*>(p)+size));return out;}
static void OriginalHeap(const HeapImage&before){assert(gameHeap.size()==before.size());for(const auto&[p,bytes]:before){auto it=gameHeap.find(p);assert(it!=gameHeap.end()&&it->second==bytes.size()&&!std::memcmp(reinterpret_cast<const void*>(p),bytes.data(),bytes.size()));}}
static void CheckAssigned(const std::vector<std::vector<unsigned char>>&before,const Snapshot&value,const HeapImage&heapBefore,bool reuse){
 auto expected=before;auto&target=expected[kNoQuery];std::memcpy(target.data()+kMember,reinterpret_cast<const void*>(value.native),0x20);std::memcpy(target.data()+kMember+0x68,reinterpret_cast<const void*>(value.native+0x68),8);
 std::vector<std::size_t>wantedRequests;std::set<std::uintptr_t>wantedReleased;
 for(unsigned i=0;i<4;++i){const auto used=counts[i]*strides[i];const auto h=Load<Triple>(Target()+offsets[i]);assert(h.end>=h.begin&&h.end-h.begin==used&&h.capacity>=h.end);auto it=gameHeap.find(h.begin);assert(it!=gameHeap.end()&&it->second==h.capacity-h.begin);assert(h.begin!=value.heads[i].begin&&(!used||!std::memcmp(reinterpret_cast<const void*>(h.begin),reinterpret_cast<const void*>(value.heads[i].begin),used)));
  if(reuse){assert(h.begin==targetHeads[i].begin&&h.capacity==targetHeads[i].capacity);const auto&old=heapBefore.at(h.begin);assert(!std::memcmp(reinterpret_cast<const void*>(h.end),old.data()+used,old.size()-used));}
  else{assert(!heapBefore.contains(h.begin)&&(h.capacity-h.begin)%strides[i]==0);wantedRequests.push_back(h.capacity-h.begin);if(targetHeads[i].begin)wantedReleased.insert(targetHeads[i].begin);}
  std::memcpy(target.data()+kMember+offsets[i],&h,sizeof(h));
 }
 auto actualRequests=requests;std::sort(actualRequests.begin(),actualRequests.end());std::sort(wantedRequests.begin(),wantedRequests.end());assert(actualRequests==wantedRequests&&attempts==wantedRequests.size());const std::set<std::uintptr_t>actualReleased(released.begin(),released.end());assert(actualReleased==wantedReleased&&released.size()==wantedReleased.size());for(auto p:wantedReleased)assert(!gameHeap.contains(p));assert(gameHeap.size()==heapBefore.size()+wantedRequests.size()-wantedReleased.size());assert(g_Entities==expected);
 for(unsigned i=0;i<4;++i){const auto&bytes=heapBefore.at(sourceHeads[i].begin);assert(!std::memcmp(reinterpret_cast<const void*>(sourceHeads[i].begin),bytes.data(),bytes.size()));}
}
int main(int argc,char**argv){
 if(argc!=2)return 90;const std::string scene=argv[1];if(scene=="empty")for(auto&n:counts)n=0;static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();FillEntity(kSizeOnly,7,1,0,1,2,3,4,5,g_EngineBase+kEntityLaserVtableOffset,0);FillEntity(kNoQuery,7,2,0,4,5,6,7,8,g_EngineBase+kEntityLaserVtableOffset,0);PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 FROZEN_GUARDS
 for(unsigned n=0x440;n<0x500;++n){g_Entities[kSizeOnly][n]=static_cast<unsigned char>(0x31+n%67);g_Entities[kNoQuery][n]=static_cast<unsigned char>(0x81+n%53);}Store(Source(),AddressOf(g_Entities[kSizeOnly]));Store(Target(),AddressOf(g_Entities[kNoQuery]));
 std::array<std::vector<unsigned char>,4>sourceData;
 for(unsigned i=0;i<4;++i){const auto used=counts[i]*strides[i],capacity=used+2*strides[i];const auto a=reinterpret_cast<std::uintptr_t>(GameMalloc(capacity));for(unsigned j=0;j<capacity;++j)reinterpret_cast<unsigned char*>(a)[j]=static_cast<unsigned char>(0x17+i*37+j);sourceData[i].assign(reinterpret_cast<const unsigned char*>(a),reinterpret_cast<const unsigned char*>(a)+used);sourceHeads[i]={a,a+used,a+capacity};Store(Source()+offsets[i],sourceHeads[i]);
  const auto targetCapacity=((scene=="reuse"||scene=="empty")?counts[i]+2:counts[i]-1)*strides[i];const auto b=targetCapacity?reinterpret_cast<std::uintptr_t>(GameMalloc(targetCapacity)):0;for(unsigned j=0;j<targetCapacity;++j)reinterpret_cast<unsigned char*>(b)[j]=static_cast<unsigned char>(0xc1+i*13+j);const auto targetUsed=targetCapacity?strides[i]:0;targetHeads[i]={b,b+targetUsed,b+targetCapacity};Store(Target()+offsets[i],targetHeads[i]);}
 SetHomingLaserAllocatorTestBindings(&GameMalloc,&GameFree);tracking=true;
 std::vector<unsigned char>sourceNative(kNative);std::memcpy(sourceNative.data(),reinterpret_cast<const void*>(Source()),kNative);const auto before=g_Entities;const auto gameBefore=g_GameBytes;const auto heapBefore=CaptureHeap();
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(RegisterIsaacApi(L));PushEntityCallbackArgument(L,AddressOf(g_Entities[kSizeOnly]));lua_setglobal(L,"laser");PushEntityCallbackArgument(L,AddressOf(g_Entities[kNoQuery]));lua_setglobal(L,"target");
 if(scene=="getter_guard_laser"||scene=="getter_guard_ctor"){
  g_ModuleBytes[scene=="getter_guard_laser"?0xf7640:0x399f80]^=1;Run(L,"assert(not pcall(function()return laser.HomingLaser end))");assert(g_Entities==before);OriginalHeap(heapBefore);NoHeapCalls();lua_close(L);tracking=false;while(!gameHeap.empty())GameFree(reinterpret_cast<void*>(gameHeap.begin()->first));return 0;
 }
 Run(L,"first=laser.HomingLaser;second=laser.HomingLaser;assert(type(first)=='userdata' and type(second)=='userdata' and first~=second,'HomingLaser must return independent owned values')");
 const auto first=Inspect(L,"first",sourceNative,sourceData),second=Inspect(L,"second",sourceNative,sourceData);assert(first.native!=second.native);for(unsigned i=0;i<4;++i)assert(first.heads[i].end<=second.heads[i].begin||first.heads[i].begin>=second.heads[i].end);assert(g_Entities==before);OriginalHeap(heapBefore);NoHeapCalls();
 if(scene=="lua_oom"){
  assert(lua_checkstack(L,40));void*context{};auto original=lua_getallocf(L,&context);LuaAllocatorFault fault{original,context,false,0};lua_setallocf(L,LuaAllocateFault,&fault);
  lua_pushcfunction(L,ReadSnapshotProtected);fault.enabled=true;const int status=lua_pcall(L,0,1,0);fault.enabled=false;lua_setallocf(L,original,context);assert(status==LUA_ERRMEM&&fault.rejected>0&&snapshotEntered==1);lua_pop(L,1);
  assert(g_Entities==before);OriginalHeap(heapBefore);NoHeapCalls();Stable(L,"first",first);Stable(L,"second",second);
 }else if(scene=="allocator_pair_unavailable"){
  SetHomingLaserAllocatorTestBindings(nullptr,nullptr);Run(L,"assert(not pcall(function()target.HomingLaser=first end))");assert(g_Entities==before);OriginalHeap(heapBefore);NoHeapCalls();Stable(L,"first",first);
 }else if(scene=="owned"){
  for(auto h:sourceHeads)for(auto*p=reinterpret_cast<unsigned char*>(h.begin);p!=reinterpret_cast<unsigned char*>(h.capacity);++p)*p^=0x5a;Store<unsigned>(Source()+0x18,0x91234567U);Stable(L,"first",first);Stable(L,"second",second);NoHeapCalls();
 }else if(scene=="assign"||scene=="reuse"||scene=="empty"){
  Run(L,"target.HomingLaser=first");CheckAssigned(before,first,heapBefore,scene=="reuse"||scene=="empty");Stable(L,"first",first);Stable(L,"second",second);
 }else if(scene.starts_with("oom")){
  failAt=static_cast<unsigned>(scene.back()-'0');assert(failAt>=1&&failAt<=4);Run(L,"assert(not pcall(function()target.HomingLaser=first end),'allocation failure must report Lua error')");assert(attempts==failAt&&requests.size()==failAt&&released.size()==failAt-1);for(auto p:released)assert(!heapBefore.contains(p));assert(g_Entities==before);OriginalHeap(heapBefore);Stable(L,"first",first);Stable(L,"second",second);
 }else if(scene=="source_retired"){
  RetireEntityLifetime(AddressOf(g_Entities[kSizeOnly]));Run(L,"local ok,v=pcall(function()return laser.HomingLaser end);assert(not ok or v==nil);pcall(function()laser.HomingLaser=first end)");assert(g_Entities==before);NoHeapCalls();Stable(L,"first",first);Run(L,"target.HomingLaser=first");CheckAssigned(before,first,heapBefore,false);Stable(L,"first",first);
 }else if(scene=="target_retired"){
  RetireEntityLifetime(AddressOf(g_Entities[kNoQuery]));Run(L,"pcall(function()target.HomingLaser=first end)");assert(g_Entities==before);OriginalHeap(heapBefore);NoHeapCalls();Stable(L,"first",first);
 }else if(scene=="wrong_type"||scene=="short"){
  Run(L,"assert(not pcall(function()target.HomingLaser=7 end));assert(not pcall(function()target.HomingLaser={}end));assert(not pcall(function()target.HomingLaser=laser end))");
  if(scene=="short"){lua_getglobal(L,"first");lua_getmetatable(L,-1);const int mt=lua_gettop(L);for(unsigned size:{0U,1U,7U,8U}){auto*raw=lua_newuserdata(L,size);if(size==8){const auto borrowed=Source();std::memcpy(raw,&borrowed,8);}lua_pushvalue(L,mt);lua_setmetatable(L,-2);bool known=false;const int top=lua_gettop(L);assert(ResolveRegisteredObjectIdentity(L,-1,&known)==0&&known&&lua_gettop(L)==top);assert(Hash(L,-1)==0);lua_pushvalue(L,-1);lua_setglobal(L,"fake");Run(L,"assert(not pcall(function()target.HomingLaser=fake end))");lua_pop(L,1);}lua_pop(L,2);}
  assert(g_Entities==before);OriginalHeap(heapBefore);NoHeapCalls();Stable(L,"first",first);
 }else if(scene=="setter_guard_vector"||scene=="setter_guard_bezier"||scene=="malloc_guard"||scene=="free_guard"){
  const auto offset=scene=="setter_guard_vector"?0xf5540:scene=="setter_guard_bezier"?0xf56ac:scene=="malloc_guard"?0x67fdb0:0x67fd80;g_ModuleBytes[offset]^=1;Run(L,"assert(not pcall(function()target.HomingLaser=first end))");assert(g_Entities==before);OriginalHeap(heapBefore);NoHeapCalls();Stable(L,"first",first);
 }else return 91;
 assert(g_GameBytes==gameBefore);const auto attemptsBeforeClose=attempts;const auto freeBeforeClose=released.size();lua_close(L);assert(attempts==attemptsBeforeClose&&released.size()==freeBeforeClose); // Lua拥有数组绝不能交给游戏free。
 tracking=false;while(!gameHeap.empty())GameFree(reinterpret_cast<void*>(gameHeap.begin()->first));SetHomingLaserAllocatorTestBindings(nullptr,nullptr);return 0;
}
'''
class HomingLaserOwnedValueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='homing-owned-');cls.addClassCleanup(cls.tmp.cleanup);work=Path(cls.tmp.name)
        cls.prefix=os.environ.get('ISAAC_HOMING_OWNED_PREFIX','homing-owned-main')
        cls.paths=tuple(sorted(set(test_support.layered_lua_runtime_sources(fixture.SOURCE))|set((ROOT/'runtime/src').rglob('*.hpp'))|set(fixture.SOURCE.rglob('*.hpp'))));cls.before=cls.snapshot();OUT.mkdir(parents=True,exist_ok=True)
        (OUT/(cls.prefix+'-input-before.json')).write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls.stable)
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        guards='\n'.join('const unsigned char b'+str(i)+'[]={'+','.join(map(str,nro[o:o+16]))+'};std::memcpy(g_ModuleBytes.data()+'+hex(o)+',b'+str(i)+',16);' for i,o in enumerate((0xf7640,0x399f80,0xf5540,0xf56ac,0x67fdb0,0x67fd80)))
        header=ROOT/'runtime/src/infrastructure/call/engine_call_access.hpp';code=header.read_text();old='return address == 0 ? nullptr : reinterpret_cast<Fn>(address);';assert code.count(old)==1
        code=code.replace('namespace isaac::runtime::engine_call {','extern "C" std::uintptr_t HomingOwnedNativeRedirect(std::uintptr_t) noexcept;\nnamespace isaac::runtime::engine_call {',1).replace(old,'return address == 0 ? nullptr : reinterpret_cast<Fn>(::HomingOwnedNativeRedirect(address));')
        shadow=work/'compatibility/infrastructure/call/engine_call_access.hpp';shadow.parent.mkdir(parents=True,exist_ok=True);shadow.write_text(code)
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')];prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
        source=prefix+MAIN.replace('FROZEN_GUARDS',guards);(OUT/(cls.prefix+'-harness.cpp')).write_text(source);(OUT/(cls.prefix+'-shadow-engine-call.hpp')).write_text(code)
        cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=work,harness_source=source)
    @classmethod
    def snapshot(cls):return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
    @classmethod
    def stable(cls):
        after=cls.snapshot();(OUT/(cls.prefix+'-input-after.json')).write_text(json.dumps(after,indent=2)+'\n')
        if cls.before!=after:raise AssertionError('生产输入在编译/执行期间改变')
    def test_owned_deep_copy_and_native_assignment(self):
        scenes=('owned','empty','lua_oom','allocator_pair_unavailable','assign','reuse','oom1','oom2','oom3','oom4','source_retired','target_retired','wrong_type','short','getter_guard_laser','getter_guard_ctor','setter_guard_vector','setter_guard_bezier','malloc_guard','free_guard')
        selected=os.environ.get('ISAAC_HOMING_SCENES');chosen=tuple(selected.split(','))if selected else scenes
        self.assertTrue(set(chosen)<=set(scenes))
        for scene in chosen:
            with self.subTest(scene=scene):
                r=subprocess.run([str(self.binary),scene],text=True,capture_output=True);print(f'{scene}: exit={r.returncode} {r.stdout}{r.stderr}',flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
