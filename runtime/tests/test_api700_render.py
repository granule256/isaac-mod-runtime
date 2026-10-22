"""Render按动态对象虚表调用，不能只调用Entity基类。"""
import unittest
from .test_api500_world import run_world
MAIN=r'''
#include "lua_object_handles.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include <cstdio>
#include <cstring>
#include <cassert>
using namespace isaac::runtime;using Vec=LuaRuntime::VectorHandle;
extern "C" {extern std::uint32_t g_HostEngineCallTrampolineCalls;extern std::uintptr_t g_HostEngineCallTrampolineLastTarget;extern std::uint64_t g_HostEngineCallTrampolineLastIntegers[8];}
std::vector<unsigned char> grid(0x500);
void* Api500WorldRoom(){return g_RoomBytes.data();}void* Api500WorldPool(){return nullptr;}
static void Npc(void*p,const Vec&v){assert(p==g_Entities[kEnemyA].data()&&v.x==3&&v.y==4);}
static void Player(void*p,const Vec&v){assert(p==g_Entities[kPlayer].data()&&v.x==5&&v.y==6);}
static void Post(void*p){assert(p==g_Entities[kEnemyA].data());}
static void Grid(void*p,const Vec&v){assert(p==grid.data()&&v.x==7&&v.y==8);}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);WriteWord(g_Entities[kPlayer],0,g_EngineBase+kEntityPlayerVtableOffset);
WriteWord(g_ModuleBytes,kEntityNpcVtableOffset+0x30,engine_call::AddressOfFunction(&Npc));WriteWord(g_ModuleBytes,kEntityPlayerVtableOffset+0x30,engine_call::AddressOfFunction(&Player));WriteWord(g_ModuleBytes,kEntityNpcVtableOffset+0x40,engine_call::AddressOfFunction(&Post));
WriteAt<std::uint32_t>(g_RoomBytes,kRoomGridWidthOffset,13);WriteAt<std::uint32_t>(g_RoomBytes,kRoomGridHeightOffset,7);WriteWord(grid,0,g_EngineBase+kGridEntity_RockVtableOffset);WriteAt<std::uint32_t>(grid,8,2);WriteAt<std::uint32_t>(grid,0x28,1);WriteWord(g_RoomBytes,kRoomGridEntityTableOffset+8,AddressOf(grid));WriteWord(g_ModuleBytes,kGridEntity_RockVtableOffset+0x20,engine_call::AddressOfFunction(&Grid));
struct Case{const char*script;std::uintptr_t target,owner;bool vector;};
const Case cases[]={
{"local n=Isaac.FindByType(20)[1]:ToNPC();assert(select('#',n:Render(Vector(3,4)))==0);assert(not pcall(function()n:Render({})end))",engine_call::AddressOfFunction(&Npc),AddressOf(g_Entities[kEnemyA]),true},
{"Isaac.GetPlayer(0):Render(Vector(5,6))",engine_call::AddressOfFunction(&Player),AddressOf(g_Entities[kPlayer]),true},
{"assert(select('#',Isaac.FindByType(20)[1]:PostRender())==0)",engine_call::AddressOfFunction(&Post),AddressOf(g_Entities[kEnemyA]),false},
{"local grid=Game():GetRoom():GetGridEntity(1);assert(grid);grid:Render(Vector(7,8));assert(not pcall(function()grid:Render({})end))",engine_call::AddressOfFunction(&Grid),AddressOf(grid),true}};
g_HostEngineCallTrampolineCalls=0;
for(unsigned i=0;i<4;++i){const auto&c=cases[i];if(LuaRuntime::InitializeFromBuffer(c.script,std::strlen(c.script),"@api700-render.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t j=0;j<n;++j)std::fprintf(stderr,"%s\n",e[j].text);return 1;}assert(g_HostEngineCallTrampolineCalls==i+1);assert(g_HostEngineCallTrampolineLastTarget==c.target);assert(g_HostEngineCallTrampolineLastIntegers[0]==c.owner);if(c.vector)assert(g_HostEngineCallTrampolineLastIntegers[1]!=0);}
return 0;}

'''
class VirtualRender(unittest.TestCase):
 def test_public_dynamic_render(self):
  r=run_world(main=MAIN);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
