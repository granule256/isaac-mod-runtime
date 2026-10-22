"""Game.SpawnEntityDesc借用真实FriendBallEnemy原生描述符。"""
import unittest
from .test_api400_params import run_main
MAIN=r'''
#include "lua_object_handles.hpp"
#include "interfaces/lua/api700_world.hpp"
#include "interfaces/lua/api700_world.guards.hpp"
#include "interfaces/lua/api600_player.guards.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cstdio>
#include <cstring>
#include <cassert>
using namespace isaac::runtime;using Vec=LuaRuntime::VectorHandle;
static unsigned calls{};
static std::uintptr_t Spawn(void*self,const void*desc,const Vec&position,void*spawner){assert(self==g_GameBytes.data()&&desc==g_Entities[kPlayer].data()+0x1d88&&position.x==10&&position.y==20);assert(spawner==(calls==0?g_Entities[kPlayer].data():nullptr));++calls;return calls==1?AddressOf(g_Entities[kEnemyA]):0;}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
for(const auto&g:api700_world::kGuards)std::memcpy(g_ModuleBytes.data()+g.offset,g.bytes.data(),16);
namespace G=api600_player;std::memcpy(g_ModuleBytes.data()+G::kConstructorGuardOffset,G::kConstructorGuard.data(),16);std::memcpy(g_ModuleBytes.data()+G::kInitGuardOffset,G::kInitGuard.data(),16);std::memcpy(g_ModuleBytes.data()+G::kShootGuardOffset,G::kShootGuard.data(),16);
const std::uintptr_t native[]={0,0,0,0,0,0,0,engine_call::AddressOfFunction(&Spawn)};SetApi700WorldNativeTestBindings(native,8);
const char*script=R"lua(local p=Isaac.GetPlayer(0);local desc=p.FriendBallEnemy;assert(type(desc)=='userdata');local n=Game():SpawnEntityDesc(desc,Vector(10,20),p);assert(n and n:ToNPC() and n.Type==20);assert(Game():SpawnEntityDesc(desc,Vector(10,20),nil)==nil);assert(not pcall(function()Game():SpawnEntityDesc({},Vector(10,20),p)end));assert(not pcall(function()Game():SpawnEntityDesc(desc,{},p)end));assert(not pcall(function()Game():SpawnEntityDesc(desc,Vector(10,20),{})end)))lua";
if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api700-spawn-desc.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::fprintf(stderr,"%s\n",e[i].text);return 1;}assert(calls==2);return 0;}
'''
class SpawnDescConsumer(unittest.TestCase):
 def test_public_original_descriptor(self):
  r=run_main(MAIN);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
