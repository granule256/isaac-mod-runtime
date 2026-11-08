"""Spawn completion must publish NPC INIT before author state changes."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness

MAIN = r'''
#include "interfaces/lua/api500_entities.guards.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "native_room_events.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
}
namespace LuaRuntime {
// Missing production functions leave the previous deferred behavior observable.
__attribute__((weak,noinline)) void DispatchPostNpcSpawn(std::uintptr_t) {}
__attribute__((weak,noinline)) void ResetNpcInitialization(std::uintptr_t) noexcept {}
}
static lua_State* state{};
static auto Npc(){return AddressOf(g_Entities[kEnemyA]);}
static int Spawn(lua_State* L){
 // Actual native base Init begins a new lifetime, followed by derived Init.
 LuaRuntime::ResetNpcInitialization(Npc());
 WriteAt<std::uint8_t>(g_Entities[kEnemyA],kEntityExistsOffset,1);
 WriteAt<std::uint32_t>(g_Entities[kEnemyA],0xb70,1);
 WriteAt<std::uint32_t>(g_Entities[kEnemyA],0xbf0,640);
 // This represents the common SpawnEx completion, before its caller resumes.
 LuaRuntime::DispatchPostNpcSpawn(Npc());
 isaac::runtime::PushEntityCallbackArgument(L,Npc());return 1;
}
static int Reenter(lua_State*){LuaRuntime::DispatchPostNpcSpawn(Npc());return 0;}
static int Remove(lua_State*){
 WriteAt<std::uint8_t>(g_Entities[kEnemyA],kEntityExistsOffset,0);return 0;
}
static void Install(lua_State* L) noexcept {
 state=L;
 lua_pushcfunction(L,Spawn);lua_setglobal(L,"native_spawn");
 lua_pushcfunction(L,Reenter);lua_setglobal(L,"observe_again");
 lua_pushcfunction(L,Remove);lua_setglobal(L,"native_remove");
}
static void Run(const char* code){
 if(luaL_dostring(state,code)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(state,-1));std::abort();}
}
static void SpawnAndWrite(void*){Run("held=native_spawn();beforeReturn=inits;held.State=13");}
int main(int argc,char**argv){
 assert(argc==2);const std::string mode=argv[1];
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();FillEntities();g_Entities[kEnemyA].resize(0x1200);PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);
 namespace G=isaac::runtime::api500_entities;
 std::memcpy(g_ModuleBytes.data()+G::kNpcLayout,G::kNpcGuard.data(),G::kNpcGuard.size());
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 LuaRuntime::SetRuntimeExtensionInstaller(Install);
 const std::string script="mode='"+mode+R"lua('
inits=0;updates=0;wrong=0
local m=RegisterMod('spawn init ordering',1)
m:AddCallback(27,function(_,n)
 inits=inits+1;assert(n.I1==640,'native derived fields incomplete')
 assert(inits<3,'recursive duplicate init')
 n.State=9
 if mode=='reentrant' then observe_again() end
 if mode=='remove' then native_remove() end
end,20)
m:AddCallback(27,function()wrong=wrong+1 end,999)
m:AddCallback(0,function()updates=updates+1 end,20)
)lua";
 if(LuaRuntime::InitializeFromBuffer(script.data(),script.size(),"@npc-spawn-init.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 if(mode=="room"||mode=="nested_room"){
  std::uint32_t level[]={1,0};
  if(mode=="room")isaac::runtime::CompleteNativeRoomLoad(SpawnAndWrite,level);
  else isaac::runtime::CompleteNativeRoomLoad([](void*){
   std::uint32_t inner[]={1,0};isaac::runtime::CompleteNativeRoomLoad(SpawnAndWrite,inner);
  },level);
 }else SpawnAndWrite(nullptr);
 LuaRuntime::DispatchPostNpcUpdate(Npc());LuaRuntime::DispatchPostUpdate();
 Run("assert(held.State==13,'deferred NPC INIT overwrote author state');assert(beforeReturn==1,'NPC INIT arrived after Spawn returned');assert(inits==1 and wrong==0,'duplicate or cross-family init')");
 if(mode=="remove")Run("assert(not held:Exists(),'removed entity was revived')");
 if(mode=="reuse"){
  Run("held=native_spawn();assert(inits==2,'reused address lost fresh INIT');held.State=13");
  LuaRuntime::DispatchPostNpcUpdate(Npc());LuaRuntime::DispatchPostUpdate();
  Run("assert(held.State==13 and inits==2,'fresh lifetime initialized twice')");
 }
 LuaRuntime::DispatchPostNpcSpawn(AddressOf(g_Entities[kPlayer]));
 Run("assert(wrong==0,'NPC spawn crossed entity families')");
 if(LuaRuntime::TakeCallbackError())return 2;
 return 0;
}
'''


class NpcSpawnInitTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='npc-spawn-init-')
        prefix = fixture.HARNESS.split('int main(', 1)[0]
        prefix = re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}',
                        '', prefix, count=1)
        cls.binary = build_lua_harness(source_root=fixture.SOURCE,
                                      workdir=Path(cls.tmp.name), harness_source=prefix + MAIN)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_spawn_init_precedes_author_state_and_stays_deduplicated(self):
        for mode in ('ordering', 'reentrant', 'remove', 'reuse', 'room', 'nested_room'):
            with self.subTest(mode=mode):
                result = subprocess.run([str(self.binary), mode], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
