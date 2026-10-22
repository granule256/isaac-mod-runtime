"""第七批真实容器：公开Lua、native x8返回、活Vector与owner变化。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
MAIN=r'''
#include "interfaces/lua/api700_containers.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/api700_containers.guards.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "interfaces/lua/class_metadata.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "lua_object_handles.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
#include <cstdio>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;using Vec=LuaRuntime::VectorHandle;
static std::vector<std::uintptr_t>arena(0x8000);static Vec samples[3]={{3,4},{6,8},{9,12}},otherSamples[3]={{1,2},{3,4},{5,6}};static unsigned calls[3]{};
template<class T>void Put(void*p,unsigned offset,const T&v){std::memcpy(static_cast<char*>(p)+offset,&v,sizeof(v));}
static Api700EntityArray MakeQueryResult(){Api700EntityArray a{};a.bytes[0]=1;Put(a.bytes,8,reinterpret_cast<std::uintptr_t>(arena.data()));Put(a.bytes,16,std::uint32_t{2});Put(a.bytes,20,std::uint32_t{2});return a;}
static Api700EntityArray QueryType(const void*p,std::int32_t t,std::int32_t v){assert(p==g_Entities[kEnemyA].data()&&t==20&&v==-1);++calls[0];return MakeQueryResult();}
static Api700EntityArray QuerySpawner(const void*p,std::int32_t s,std::int32_t t,bool enemies){assert(p==g_Entities[kEnemyA].data()&&s==1&&t==20&&enemies);++calls[1];return MakeQueryResult();}
static Api700EntityArray QueryGroup(void*p,std::int32_t group){assert(p==g_Entities[kEnemyA].data()&&group==7);++calls[2];return MakeQueryResult();}
static int LocalRoomIndex(lua_State*L){lua_getmetatable(L,1);lua_getfield(L,-1,"__methods");lua_pushvalue(L,2);lua_rawget(L,-2);return 1;}
static int Mutate(lua_State*){samples[0]={5,12};return 0;}
static int Reallocate(lua_State*){WriteWord(g_Entities[kEffect],0x478,reinterpret_cast<std::uintptr_t>(otherSamples));WriteWord(g_Entities[kEffect],0x480,reinterpret_cast<std::uintptr_t>(otherSamples+3));WriteWord(g_Entities[kEffect],0x488,reinterpret_cast<std::uintptr_t>(otherSamples+3));return 0;}
static int ResetArena(lua_State*){WriteWord(g_RoomBytes,0x1a28,reinterpret_cast<std::uintptr_t>(arena.data()+4));return 0;}
static int ChangeOwner(lua_State*){WriteWord(g_RoomBytes,8,0xdeadbeef);return 0;}
static int RetireLaser(lua_State*){RetireEntityLifetime(AddressOf(g_Entities[kEffect]));return 0;}
void*ContainerTestRoom(){return g_RoomBytes.data();}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();WriteWord(g_Entities[kEffect],0,g_EngineBase+kEntityLaserVtableOffset);WriteAt<std::uint32_t>(g_Entities[kEffect],kEntityTypeOffset,7);PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
for(const auto&e:api700_containers::kEntries)std::memcpy(g_ModuleBytes.data()+e.offset,e.guard,16);
arena[0]=AddressOf(g_Entities[kEnemyA]);arena[1]=AddressOf(g_Entities[kPlayer]);WriteWord(g_RoomBytes,0x1a28,reinterpret_cast<std::uintptr_t>(arena.data()));WriteAt<std::uint32_t>(g_RoomBytes,0x1a30,0x8000);
for(unsigned offset:{0x478U,0x490U}){WriteWord(g_Entities[kEffect],offset,reinterpret_cast<std::uintptr_t>(samples));WriteWord(g_Entities[kEffect],offset+8,reinterpret_cast<std::uintptr_t>(samples+3));WriteWord(g_Entities[kEffect],offset+16,reinterpret_cast<std::uintptr_t>(samples+3));}
const std::uintptr_t bindings[]={engine_call::AddressOfFunction(&QueryType),engine_call::AddressOfFunction(&QuerySpawner),engine_call::AddressOfFunction(&QueryGroup)};SetApi700ContainerNatives(bindings);
auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));RegisterApi700Containers(L);
RegisterVectorReferenceMetatable(L);luaL_newmetatable(L,LuaRuntime::kVectorMetatable);for(const auto&r:{std::pair<const char*,lua_CFunction>{"__index",VectorIndex},{"__newindex",VectorNewIndex},{"__add",VectorAdd},{"__mul",VectorMul},{"__eq",VectorEqual}}){lua_pushcfunction(L,r.second);lua_setfield(L,-2,r.first);}lua_newtable(L);static_cast<void>(AttachVectorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);lua_pushcfunction(L,CreateVectorHandle);lua_setglobal(L,"Vector");
luaL_newmetatable(L,LuaRuntime::kRoomMetatable);lua_getfield(L,-1,"__methods");if(lua_isnil(L,-1)){lua_pop(L,1);lua_newtable(L);static_cast<void>(AttachRoomMethods(L));lua_setfield(L,-2,"__methods");lua_pushcfunction(L,LocalRoomIndex);lua_setfield(L,-2,"__index");}else{lua_pop(L,1);}lua_pop(L,1);
#ifdef API700_CONTAINER_LOCAL
#define B(mt,name,fn) luaL_getmetatable(L,mt);lua_getfield(L,-1,"__methods");lua_pushcfunction(L,fn);lua_setfield(L,-2,name);lua_pop(L,2)
B("IsaacRuntime.EntityList","__len",Api700EntityListLen);B("IsaacRuntime.VectorList","__len",Api700VectorListLen);B("IsaacRuntime.EntityList","Get",Api700EntityListGet);B("IsaacRuntime.VectorList","Get",Api700VectorListGet);B(LuaRuntime::kEntityLaserMetatable,"GetSamples",Api700LaserGetSamples);B(LuaRuntime::kEntityLaserMetatable,"GetNonOptimizedSamples",Api700LaserGetNonOptimizedSamples);B(LuaRuntime::kEntityNPCMetatable,"QueryNPCsType",Api700NPCQueryType);B(LuaRuntime::kEntityNPCMetatable,"QueryNPCsSpawnerType",Api700NPCQuerySpawnerType);B(LuaRuntime::kEntityNPCMetatable,"QueryNPCsGroup",Api700NPCQueryGroup);B(LuaRuntime::kRoomMetatable,"GetEntities",Api700RoomGetEntities);
#undef B
#endif
PushEntityCallbackArgument(L,AddressOf(g_Entities[kEnemyA]));lua_setglobal(L,"npc");PushEntityCallbackArgument(L,AddressOf(g_Entities[kEffect]));lua_setglobal(L,"laser");auto*room=static_cast<LuaRuntime::RoomHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::RoomHandle)));room->reserved=0;luaL_getmetatable(L,LuaRuntime::kRoomMetatable);lua_setmetatable(L,-2);lua_setglobal(L,"room");
for(const auto&r:{std::pair<const char*,lua_CFunction>{"mutate",Mutate},{"reallocate",Reallocate},{"resetArena",ResetArena},{"changeOwner",ChangeOwner},{"retireLaser",RetireLaser}}){lua_pushcfunction(L,r.second);lua_setglobal(L,r.first);}
const char*script=R"lua(
local s=laser:GetSamples();assert(getmetatable(s).__class==getmetatable(CppContainer.Vector.VectorList).__class);local raw=laser:GetNonOptimizedSamples();assert(s.Size==3 and s:__len()==3 and #s==3 and #raw==3)
local v=s:Get(0);assert(v.X==3 and v.Y==4 and v:Length()==5);assert((v+Vector(1,2)).Y==6 and (v*2).X==6);assert(not pcall(function()v.X=9 end));assert(not pcall(function()v:Normalize()end));assert(not pcall(function()v:Resize(2)end));assert(not pcall(function()v:Clamp(2)end));assert(v:Normalized():Length()>0.99);mutate();assert(v.X==5 and v:Length()==13)
assert(not pcall(function()s:Get(-1)end));assert(not pcall(function()s:Get(3)end));assert(not pcall(function()s:Get(1.5)end))
local list=npc:QueryNPCsType(20,-1);local b=npc:QueryNPCsSpawnerType(1,20,0);local c=npc:QueryNPCsGroup(7);assert(#list==2 and list.Size==2 and list:__len()==2 and #b==2 and #c==2 and list:Get(0).Type==20 and list:Get(1).Type==1)
local entities=room:GetEntities();assert(#entities>0 and entities.Size==#entities and entities:Get(0));assert(not pcall(function()entities:Get(-1)end));assert(not pcall(function()npc:QueryNPCsType(20,1.5)end));assert(not pcall(function()list.Size=1 end))
reallocate();assert(s.Size==3 and s:Get(0).X==1);assert(not pcall(function()return v.X end));assert(not pcall(function()return v:Length()end));assert(not pcall(function()return v+Vector(1,2)end))
resetArena();assert(not pcall(function()return #list end));changeOwner();assert(not pcall(function()return entities.Size end));retireLaser();assert(not pcall(function()return raw.Size end));assert(not pcall(function()return s:Get(0)end))
)lua";
if(luaL_dostring(L,script)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}assert(calls[0]==1&&calls[1]==1&&calls[2]==1);lua_close(L);return 0;}
'''
def run(local=False):
 prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
 prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
 prefix=prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}', 'void*ContainerTestRoom();\nGameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {*room=ContainerTestRoom();return GameRoomObservation::Success;}')
 source=fixture.SOURCE.parent/'src/interfaces/lua/api700_containers.cpp'
 extra=()if source in layered_lua_runtime_sources(fixture.SOURCE)else(source,)
 with tempfile.TemporaryDirectory(prefix='api700-containers-')as d:
  binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+('\n#define API700_CONTAINER_LOCAL\n'if local else'')+MAIN,extra_sources=extra)
  return subprocess.run([str(binary)],capture_output=True,text=True)
class ContainerConsumer(unittest.TestCase):
 def test_live_containers(self):
  r=run();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
