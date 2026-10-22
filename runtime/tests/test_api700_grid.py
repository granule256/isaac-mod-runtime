"""第七批网格：额外Sprite真偏移、完整复制赋值、借用GC与Room/槽位生命周期。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness,layered_lua_runtime_sources
MAIN=r'''
#include "interfaces/lua/api700_grid.hpp"
#include "interfaces/lua/api500_world.hpp"
#include "interfaces/lua/api700_grid.guards.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "interfaces/lua/sprite_api.hpp"
#include "interfaces/lua/vector_api.hpp"
#include "lua_object_handles.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
#include <cstdio>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
static std::vector<unsigned char>doorGrid(0x400),plateGrid(0x400),poopGrid(0x400);static unsigned copies{},assignments{},temporaryDestructors{},ownedDestructors{};
static void Copy(void*d,const void*s){++copies;assert(s==doorGrid.data()+0x1b0||s==plateGrid.data()+0x1a0||s==plateGrid.data()+0x48);std::memcpy(d,s,kSpriteObjectSize);}
static void* Assign(void*d,void*s){++assignments;assert(d==doorGrid.data()+0x1b0||d==plateGrid.data()+0x1a0);alignas(16)unsigned char temp[kSpriteObjectSize];std::memcpy(temp,d,kSpriteObjectSize);std::memcpy(d,s,kSpriteObjectSize);std::memcpy(s,temp,kSpriteObjectSize);return d;}
static void TemporaryDestroy(void*){++temporaryDestructors;}
static void OwnedDestroy(void*){++ownedDestructors;}
static int GridRead(lua_State*L){if(!std::strcmp(lua_tostring(L,2),"ReduceSpawnRate")){lua_pushcfunction(L,Api700GridPoopReduceSpawnRate);return 1;}if(int n=TryPushApi700GridField(L,lua_tostring(L,2)))return n;return GridEntityIndex(L);}
static int DoorRead(lua_State*L){if(int n=TryPushApi700GridField(L,lua_tostring(L,2)))return n;return GridEntityDoorIndex(L);}
static int GridWrite(lua_State*L){if(TryWriteApi700GridField(L,lua_tostring(L,2)))return 0;return luaL_error(L,"unknown GridEntity field");}
static int RemoveGrid(lua_State*){WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+21*8,0);return 0;}
static int ChangeDoorSlot(lua_State*){WriteWord(g_RoomBytes,kRoomDoorObjectTableOffset,0);return 0;}
static int ChangeRoom(lua_State*){WriteWord(g_RoomBytes,8,0xdeadbeef);return 0;}
void*GridTestRoom(){return g_RoomBytes.data();}
int main(){static_cast<void>(&GridRead);static_cast<void>(&DoorRead);static_cast<void>(&GridWrite);static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
for(const auto&e:api700_grid::kEntries)std::memcpy(g_ModuleBytes.data()+e.offset,e.guard,16);
WriteAt<std::uint32_t>(g_RoomBytes,kRoomGridWidthOffset,13);WriteAt<std::uint32_t>(g_RoomBytes,kRoomGridHeightOffset,7);WriteWord(doorGrid,0,g_EngineBase+kGridEntity_DoorVtableOffset);WriteWord(plateGrid,0,g_EngineBase+kGridEntity_PressurePlateVtableOffset);WriteWord(poopGrid,0,g_EngineBase+kGridEntity_PoopVtableOffset);WriteAt<std::uint32_t>(doorGrid,kGridEntityDoorSlotOffset,0);WriteAt<std::uint32_t>(doorGrid,kGridEntityGridIndexOffset,20);WriteAt<std::uint32_t>(plateGrid,kGridEntityGridIndexOffset,21);WriteAt<std::uint32_t>(poopGrid,kGridEntityGridIndexOffset,22);WriteWord(g_RoomBytes,kRoomDoorObjectTableOffset,AddressOf(doorGrid));WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+20*8,AddressOf(doorGrid));WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+21*8,AddressOf(plateGrid));WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+22*8,AddressOf(poopGrid));
WriteAt<std::uint8_t>(doorGrid,0x1b0+kSpriteLoadedFlagOffset,1);WriteAt<std::uint8_t>(doorGrid,0x48+kSpriteLoadedFlagOffset,0);WriteAt<std::uint8_t>(plateGrid,0x1a0+kSpriteLoadedFlagOffset,0);WriteAt<std::uint8_t>(plateGrid,0x48+kSpriteLoadedFlagOffset,1);WriteAt<float>(doorGrid,0x1b0+kSpritePlaybackSpeedOffset,3.5F);WriteAt<float>(plateGrid,0x1a0+kSpritePlaybackSpeedOffset,2.5F);WriteAt<float>(plateGrid,0x48+kSpritePlaybackSpeedOffset,4.5F);
LuaRuntime::LuaSpriteBindings sb{};sb.destructor_=OwnedDestroy;LuaRuntime::SetSpriteBindings(sb);const std::uintptr_t natives[]={engine_call::AddressOfFunction(&Copy),engine_call::AddressOfFunction(&Assign),engine_call::AddressOfFunction(&TemporaryDestroy)};SetApi700GridSpriteNatives(natives);
auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_STRLIBNAME,luaopen_string,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));
luaL_newmetatable(L,LuaRuntime::kSpriteMetatable);lua_pushcfunction(L,SpriteIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,SpriteNewIndex);lua_setfield(L,-2,"__newindex");lua_pushcfunction(L,DestroySpriteHandle);lua_setfield(L,-2,"__gc");lua_newtable(L);static_cast<void>(AttachSpriteMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
luaL_newmetatable(L,LuaRuntime::kGridEntityMetatable);lua_pushcfunction(L,GridEntityIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,Api500GridNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachGridEntityMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);luaL_newmetatable(L,LuaRuntime::kGridEntityDoorMetatable);lua_pushcfunction(L,GridEntityDoorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,Api500GridNewIndex);lua_setfield(L,-2,"__newindex");lua_newtable(L);static_cast<void>(AttachGridEntityDoorMethods(L));lua_setfield(L,-2,"__methods");lua_pop(L,1);
#ifdef API700_GRID_LOCAL
luaL_newmetatable(L,LuaRuntime::kGridEntityMetatable);lua_pushcfunction(L,GridRead);lua_setfield(L,-2,"__index");lua_pushcfunction(L,GridWrite);lua_setfield(L,-2,"__newindex");lua_pop(L,1);luaL_newmetatable(L,LuaRuntime::kGridEntityDoorMetatable);lua_pushcfunction(L,DoorRead);lua_setfield(L,-2,"__index");lua_pushcfunction(L,GridWrite);lua_setfield(L,-2,"__newindex");lua_pop(L,1);
#endif
for(unsigned i=0;i<3;++i){if(!i){auto*h=static_cast<LuaRuntime::DoorHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::DoorHandle)));*h={doorGrid.data(),0,0};luaL_getmetatable(L,LuaRuntime::kGridEntityDoorMetatable);}else{auto*h=static_cast<LuaRuntime::GridEntityHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::GridEntityHandle)));h->entity=i==1?plateGrid.data():poopGrid.data();luaL_getmetatable(L,LuaRuntime::kGridEntityMetatable);}lua_setmetatable(L,-2);lua_setglobal(L,i==0?"door":i==1?"plate":"poop");}
PushEngineGridEntitySpriteHandle(L,plateGrid.data());lua_setglobal(L,"normalSprite");for(const auto&r:{std::pair<const char*,lua_CFunction>{"removeGrid",RemoveGrid},{"changeDoorSlot",ChangeDoorSlot},{"changeRoom",ChangeRoom}}){lua_pushcfunction(L,r.second);lua_setglobal(L,r.first);}
const char*script=R"lua(
local extra=door.ExtraSprite;local timer=plate.TimerPlate;assert(extra:IsLoaded() and not timer:IsLoaded() and normalSprite:IsLoaded());assert(extra.PlaybackSpeed==3.5 and timer.PlaybackSpeed==2.5)
timer.PlaybackSpeed=1.75;assert(plate.TimerPlate.PlaybackSpeed==1.75 and normalSprite.PlaybackSpeed==4.5)
door.ExtraSprite=timer;assert(not extra:IsLoaded() and extra.PlaybackSpeed==1.75);plate.TimerPlate=normalSprite;assert(timer:IsLoaded() and timer.PlaybackSpeed==4.5);door.ExtraSprite=extra;assert(extra.PlaybackSpeed==1.75)
assert(not pcall(function()door.ExtraSprite={}end));assert(not pcall(function()plate.TimerPlate={}end));assert(select('#',poop:ReduceSpawnRate())==0);assert(poop.VarData==1);assert(poop.ReducedSpawnRate==nil)
getmetatable(extra).__gc(extra);getmetatable(timer).__gc(timer);assert(extra.PlaybackSpeed==1.75 and timer:IsLoaded())
removeGrid();assert(not pcall(function()timer:IsLoaded()end));assert(not pcall(function()plate.TimerPlate=extra end));changeDoorSlot();assert(not pcall(function()extra:IsLoaded()end))
)lua";
if(luaL_dostring(L,script)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}assert(copies==3&&assignments==3&&temporaryDestructors==3&&ownedDestructors==0);
// 恢复槽位后新视图可用；旧视图必须在Room描述符/base变化时失效。
WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+21*8,AddressOf(plateGrid));WriteWord(g_RoomBytes,kRoomDoorObjectTableOffset,AddressOf(doorGrid));
if(luaL_dostring(L,"held=door.ExtraSprite;changeRoom();assert(not pcall(function()held:IsLoaded()end))")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 2;}WriteWord(g_RoomBytes,8,0);if(luaL_dostring(L,"held=door.ExtraSprite"))return 3;LuaRuntime::SetEngineModuleBase(g_EngineBase+0x1000);if(luaL_dostring(L,"assert(not pcall(function()held:IsLoaded()end))"))return 4;LuaRuntime::SetEngineModuleBase(g_EngineBase);lua_close(L);assert(ownedDestructors==0);return 0;}
'''
def run(local=False):
 prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
 prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
 prefix=prefix.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}', 'void*GridTestRoom();\nGameRoomObservation ReadCurrentGameRoom(uintptr_t, void** room) {*room=GridTestRoom();return GameRoomObservation::Success;}')
 source=fixture.SOURCE.parent/'src/interfaces/lua/api700_grid.cpp';extra=()if source in layered_lua_runtime_sources(fixture.SOURCE)else(source,)
 with tempfile.TemporaryDirectory(prefix='api700-grid-')as d:
  binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+('\n#define API700_GRID_LOCAL\n'if local else'')+MAIN,extra_sources=extra)
  return subprocess.run([str(binary)],capture_output=True,text=True)
class GridConsumer(unittest.TestCase):
 def test_extra_sprite_owner_copy_gc_and_var_data(self):
  r=run();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
