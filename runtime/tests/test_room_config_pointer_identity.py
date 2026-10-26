"""固定PC七族真实身份：三种ArrayProxy拥有值与四种借用视图。"""
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
EVIDENCE=ROOT/'dist/api-remaining-recovery-20261025'
MAIN=r'''
#include "interfaces/lua/api500_world.hpp"
#include "interfaces/lua/game_api.hpp"
#include "interfaces/lua/api600_containers.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/object_identity_registry.hpp"
#include "lua_object_handles.hpp"
#include <cassert>
#include <cstdlib>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static std::vector<unsigned char> config(0x80),spawns(0x30),entries(0x24),grid(0x200);
void* RoomIdentityRoom(){return g_RoomBytes.data();}
static const void*Pick(std::uintptr_t spawn,float r){assert(spawn==AddressOf(spawns)&&r==0);return entries.data();}
static void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)){fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),s);std::exit(10);}}
static std::uintptr_t Hash(lua_State*L,int index){const int top=lua_gettop(L);index=lua_absindex(L,index);lua_getglobal(L,"GetPtrHash");lua_pushvalue(L,index);if(lua_pcall(L,1,1,0)!=LUA_OK)std::exit(11);assert(lua_isinteger(L,-1));auto value=static_cast<std::uintptr_t>(lua_tointeger(L,-1));lua_settop(L,top);return value;}
static void Identity(lua_State*L,const char*name,std::uintptr_t expected){lua_getglobal(L,name);bool known=false;const int top=lua_gettop(L);assert(ResolveRegisteredObjectIdentity(L,-1,&known)==expected&&known&&lua_gettop(L)==top);assert(Hash(L,-1)==expected);lua_pop(L,1);}
static std::uintptr_t Owned(lua_State*L,const char*name,unsigned count,std::uintptr_t begin){lua_getglobal(L,name);assert(lua_type(L,-1)==LUA_TUSERDATA&&lua_rawlen(L,-1)>=16);const auto*value=static_cast<const unsigned char*>(lua_touserdata(L,-1));unsigned actual{};std::uintptr_t pointer{};std::memcpy(&actual,value,4);std::memcpy(&pointer,value+8,8);assert(actual==count&&pointer==begin);const auto address=reinterpret_cast<std::uintptr_t>(value);lua_pop(L,1);Identity(L,name,address);return address;}
static void GameViews(lua_State*L){
 // RegisterGameApi为lua_runtime.cpp私有装配；这里仅装原生产访问器/方法，不模拟待测getter。
 luaL_newmetatable(L,LuaRuntime::kGameMetatable);lua_newtable(L);static_cast<void>(AttachGameMethods(L));lua_pushcclosure(L,GameIndex,1);lua_setfield(L,-2,"__index");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kLevelMetatable);static_cast<void>(AttachLevelMethods(L));lua_pushvalue(L,-1);lua_pushcclosure(L,LevelIndex,1);lua_setfield(L,-2,"__index");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kRoomMetatable);lua_newtable(L);static_cast<void>(AttachRoomMethods(L));lua_setfield(L,-2,"__index");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kGridEntityMetatable);lua_pushcfunction(L,GridEntityIndex);lua_setfield(L,-2,"__index");lua_newtable(L);static_cast<void>(AttachGridEntityMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kRoomDescriptorMetatable);lua_pushcfunction(L,RoomDescriptorIndex);lua_setfield(L,-2,"__index");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kRoomDescriptorListMetatable);lua_pushcfunction(L,RoomDescriptorListIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,RoomDescriptorListLen);lua_setfield(L,-2,"__len");lua_newtable(L);static_cast<void>(AttachRoomDescriptorListMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kRoomConfigSpawnMetatable);lua_pushcfunction(L,RoomConfigSpawnIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,Api600RoomConfigReadOnly);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachRoomConfigSpawnMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
 luaL_newmetatable(L,LuaRuntime::kRoomConfigEntryMetatable);lua_pushcfunction(L,RoomConfigEntryIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,Api600RoomConfigReadOnly);lua_setfield(L,-2,"__newindex");lua_pop(L,1);
 auto*h=static_cast<LuaRuntime::GameHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::GameHandle)));h->reserved=0;luaL_getmetatable(L,LuaRuntime::kGameMetatable);lua_setmetatable(L,-2);lua_setglobal(L,"game");
}
int main(int argc,char**argv){
 if(argc!=2)return 90;const std::string scene=argv[1];static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 WriteAt<unsigned>(g_GameBytes,0x21510,1);WriteAt<unsigned>(g_GameBytes,kLevelCurrentRoomIndexOffset,84);WriteAt<unsigned>(g_GameBytes,kLevelCurrentRoomDimensionOffset,0);WriteAt<unsigned>(g_GameBytes,0x18,84);WriteAt<unsigned>(g_GameBytes,0x1c,84);WriteAt<unsigned>(g_GameBytes,0x20,0);WriteWord(g_GameBytes,0x28,AddressOf(config));WriteWord(g_RoomBytes,8,AddressOf(g_GameBytes)+0x18);
 WriteAt<unsigned>(config,0xc,123);WriteWord(config,0x50,AddressOf(spawns));WriteAt<std::uint16_t>(config,0x58,2);WriteAt<std::int16_t>(spawns,0,-12);WriteWord(spawns,8,AddressOf(entries));WriteAt<std::uint8_t>(spawns,0x10,2);WriteWord(spawns,0x18+8,AddressOf(entries)+24);WriteAt<std::uint8_t>(spawns,0x18+0x10,1);WriteAt<int>(entries,0,5);WriteAt<int>(entries,12,9);WriteAt<int>(entries,24,1);
 WriteWord(grid,0,g_EngineBase+kGridEntity_RockVtableOffset);WriteAt<unsigned>(grid,8,2);WriteAt<unsigned>(grid,0xc,3);WriteAt<int>(grid,0x10,7);WriteAt<unsigned>(grid,0x28,1);WriteAt<unsigned>(g_RoomBytes,kRoomGridWidthOffset,13);WriteAt<unsigned>(g_RoomBytes,kRoomGridHeightOffset,7);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+8,AddressOf(grid));
 FROZEN_GUARDS
 SetRoomConfigSpawnPickEntryHostImplementation(&Pick);
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);assert(RegisterIsaacApi(L));GameViews(L);
 Run(L,"level=game:GetLevel();descriptor=level:GetCurrentRoomDesc();room1=descriptor.Data;room2=descriptor.Data;spawns1=room1.Spawns;spawns2=room1.Spawns;spawn1=spawns1:Get(0);spawn2=spawns2:Get(0);entries1=spawn1.Entries;entries2=spawn1.Entries;entry1=entries1:Get(0);entry2=entries2:Get(0);picked=spawn1:PickEntry(0);rooms1=level:GetRooms();rooms2=level:GetRooms();grid=game:GetRoom():GetGridEntity(1);desc1=grid.Desc;desc2=grid:GetSaveState();assert(room1.Variant==123 and spawn1.X==-12 and entry1.Type==5 and desc1.State==7)");
 if(scene=="borrowed"){
  Identity(L,"room1",AddressOf(config));Identity(L,"room2",AddressOf(config));Identity(L,"spawn1",AddressOf(spawns));Identity(L,"spawn2",AddressOf(spawns));Identity(L,"entry1",AddressOf(entries));Identity(L,"entry2",AddressOf(entries));Identity(L,"picked",AddressOf(entries));Identity(L,"desc1",AddressOf(grid)+8);Identity(L,"desc2",AddressOf(grid)+8);
  Run(L,"assert(GetPtrHash(grid)~=GetPtrHash(desc1));assert(GetPtrHash(room1)==GetPtrHash(room2));assert(GetPtrHash(entry1)==GetPtrHash(picked))");
 }else if(scene=="owned"){
  auto a=Owned(L,"spawns1",2,AddressOf(spawns));auto b=Owned(L,"spawns2",2,AddressOf(spawns));assert(a!=b&&a!=AddressOf(spawns));a=Owned(L,"entries1",2,AddressOf(entries));b=Owned(L,"entries2",2,AddressOf(entries));assert(a!=b&&a!=AddressOf(entries));a=Owned(L,"rooms1",1,AddressOf(g_GameBytes)+0x18);b=Owned(L,"rooms2",1,AddressOf(g_GameBytes)+0x18);assert(a!=b&&a!=AddressOf(g_GameBytes)+0x18);
 }else if(scene=="spawn_count"){
  WriteAt<std::uint16_t>(config,0x58,1);Run(L,"assert(spawns1.Size==2 and #spawns1==2);fresh=room1.Spawns;assert(fresh.Size==1 and fresh:Get(1)==nil);assert(not pcall(function()spawns1:Get(0)end));assert(not pcall(function()return spawn1.X end))");Owned(L,"spawns1",2,AddressOf(spawns));Owned(L,"fresh",1,AddressOf(spawns));Identity(L,"spawn1",0);
 }else if(scene=="entry_array"){
  WriteWord(spawns,8,AddressOf(entries)+12);WriteAt<std::uint8_t>(spawns,0x10,1);Run(L,"assert(entries1.Size==2 and #entries1==2);assert(not pcall(function()entries1:Get(0)end));assert(not pcall(function()return entry1.Type end));freshSpawn=spawns1:Get(0);fresh=freshSpawn.Entries;assert(fresh.Size==1 and fresh:Get(0).Type==9)");Owned(L,"entries1",2,AddressOf(entries));Owned(L,"fresh",1,AddressOf(entries)+12);Identity(L,"entry1",0);Identity(L,"picked",0);Identity(L,"spawn1",0);
 }else if(scene=="room_count"){
  WriteAt<unsigned>(g_GameBytes,0x21510,2);WriteAt<unsigned>(g_GameBytes,0x118,85);WriteAt<unsigned>(g_GameBytes,0x120,1);Run(L,"assert(rooms1.Size==1 and #rooms1==1,'GetRooms must capture count by value');assert(rooms1:Get(1)==nil);fresh=level:GetRooms();assert(fresh.Size==2 and fresh:Get(1).GridIndex==85)");Owned(L,"rooms1",1,AddressOf(g_GameBytes)+0x18);Owned(L,"fresh",2,AddressOf(g_GameBytes)+0x18);
 }else if(scene=="direct_index"){
  WriteAt<unsigned>(g_GameBytes,0x21510,2);WriteAt<unsigned>(g_GameBytes,0x20,1);WriteAt<unsigned>(g_GameBytes,0x118,85);WriteAt<unsigned>(g_GameBytes,0x120,0);
  Run(L,"fresh=level:GetRooms();assert(fresh:Get(0).GridIndex==84 and fresh:Get(1).GridIndex==85,'ArrayProxy.Get indexes storage without searching ListIndex');assert(fresh:Get(0).ListIndex==1 and fresh:Get(1).ListIndex==0)");
 }else if(scene=="grid_dead"){
  WriteWord(grid,0,0);Identity(L,"desc1",0);Identity(L,"desc2",0);Run(L,"assert(not pcall(function()return desc1.State end));assert(not pcall(function()desc1.State=8 end))");
 }else if(scene=="room_owner"){
  WriteWord(g_GameBytes,0x28,0);Identity(L,"room1",0);Identity(L,"room2",0);Run(L,"assert(not pcall(function()return room1.Variant end))");
 }else if(scene=="base"){
  LuaRuntime::SetEngineModuleBase(g_EngineBase+8);for(const auto*name:{"room1","spawn1","entry1","picked","desc1"})Identity(L,name,0);Owned(L,"spawns1",2,AddressOf(spawns));Owned(L,"entries1",2,AddressOf(entries));Owned(L,"rooms1",1,AddressOf(g_GameBytes)+0x18);Run(L,"assert(not pcall(function()spawns1:Get(0)end));assert(rooms1:Get(0)==nil)");LuaRuntime::SetEngineModuleBase(g_EngineBase);
 }else if(scene=="short"){
  for(const auto*mt:{"IsaacRuntime.RoomConfigRoom","IsaacRuntime.RoomConfigSpawns","IsaacRuntime.RoomConfigEntries",LuaRuntime::kRoomConfigSpawnMetatable,LuaRuntime::kRoomConfigEntryMetatable,"IsaacRuntime.GridEntityDesc",LuaRuntime::kRoomDescriptorListMetatable})for(unsigned size:{0U,1U,7U}){lua_newuserdata(L,size);luaL_getmetatable(L,mt);lua_setmetatable(L,-2);bool known=false;const int top=lua_gettop(L);assert(ResolveRegisteredObjectIdentity(L,-1,&known)==0&&known&&lua_gettop(L)==top);assert(Hash(L,-1)==0);lua_pop(L,1);}
 }else return 91;
 lua_close(L);return 0;
}
'''
class RoomConfigPointerIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='room-config-identity-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.prefix=os.environ.get('ISAAC_ROOM_IDENTITY_PREFIX','delegated-room-identity-red')
        cls.paths=tuple(sorted(set(test_support.layered_lua_runtime_sources(fixture.SOURCE))|set((ROOT/'runtime/src').rglob('*.hpp'))|set(fixture.SOURCE.rglob('*.hpp'))));cls.before=cls.snapshot();EVIDENCE.mkdir(parents=True,exist_ok=True)
        (EVIDENCE/(cls.prefix+'-input-before.json')).write_text(json.dumps(cls.before,indent=2)+'\n');cls.addClassCleanup(cls.stable)
        nro=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
        guards='\n'.join('const unsigned char b'+str(i)+'[]={'+','.join(map(str,nro[o:o+16]))+'};std::memcpy(g_ModuleBytes.data()+'+hex(o)+',b'+str(i)+',16);' for i,o in enumerate((0x48f490,0x495248,0x48f5ec,0x37e4c8)))
        prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')];prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
        prefix=prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}','void* RoomIdentityRoom();\nGameRoomObservation ReadCurrentGameRoom(uintptr_t,void** room){*room=RoomIdentityRoom();return GameRoomObservation::Success;}')
        source=prefix+MAIN.replace('FROZEN_GUARDS',guards);(EVIDENCE/(cls.prefix+'-harness.cpp')).write_text(source)
        cls.binary=test_support.build_lua_harness(source_root=fixture.SOURCE,workdir=Path(cls.tmp.name),harness_source=source)
    @classmethod
    def snapshot(cls):return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.paths}
    @classmethod
    def stable(cls):
        after=cls.snapshot();(EVIDENCE/(cls.prefix+'-input-after.json')).write_text(json.dumps(after,indent=2)+'\n')
        if cls.before!=after:raise AssertionError('生产输入在编译/执行期间变化')
    def test_seven_fixed_pc_object_families(self):
        for scene in ('borrowed','owned','spawn_count','entry_array','room_count','direct_index','grid_dead','room_owner','base','short'):
            with self.subTest(scene=scene):
                r=subprocess.run([str(self.binary),scene],text=True,capture_output=True);print(f'{scene}: exit={r.returncode} {r.stdout}{r.stderr}',flush=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
