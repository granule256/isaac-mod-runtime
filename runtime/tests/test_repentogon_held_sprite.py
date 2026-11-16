"""GetHeldSprite lends the native ANM2 for one player's lifetime."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_support
from .test_repentogon_in_game import PREFIX

SOURCE = Path(__file__).resolve().parents[1] / "source"
DRIVER = PREFIX + r'''
#include "interfaces/lua/entity_lifetime.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/repentogon_player_api.hpp"
#include "runtime_constants.hpp"
#include <thread>
#include <vector>

static std::vector<unsigned char> moduleBytes(kEntityPlayerVtableOffset+16);
static std::array<unsigned char,0x3000> player{};
static unsigned spriteDestructors;

static std::uintptr_t PlayerAddress(){
 return reinterpret_cast<std::uintptr_t>(player.data());
}
static void SetVtable(std::uintptr_t offset){
 const auto vtable=reinterpret_cast<std::uintptr_t>(moduleBytes.data())+offset;
 std::memcpy(player.data(),&vtable,sizeof(vtable));
}
static int Retire(lua_State*){
 RetireEntityLifetime(PlayerAddress());
 return 0;
}
static int SetHeldSpriteFilename(lua_State* state){
 std::size_t size{};
 const char* name=luaL_checklstring(state,1,&size);
 assert(size<=22);
 auto* held=player.data()+0x12d8;
 std::memset(held,0,24);
 held[0]=static_cast<unsigned char>(size*2);
 std::memcpy(held+1,name,size);
 return 0;
}
static int InstallHeldSpriteGuard(lua_State*){
 const unsigned char guard[]={0x08,0x5b,0x82,0x52,0x74,0x02,0x08,0x8b,
                             0xe1,0x03,0x00,0x91,0xe0,0x03,0x14,0xaa};
 std::memcpy(moduleBytes.data()+0x2f66cc,guard,sizeof(guard));
 return 0;
}
static int SetPlayerVtable(lua_State* state){
 SetVtable(lua_toboolean(state,1)?kEntityPlayerVtableOffset:kEntityBaseVtableOffset);
 return 0;
}
static int PushPlayer(lua_State* state){
 PushEntityCallbackArgument(state,PlayerAddress());
 return 1;
}
static void DestroySprite(void*){++spriteDestructors;}

static void Extensions(lua_State* state) noexcept{
 PushPlayer(state);lua_setglobal(state,"player");
 lua_pushcfunction(state,Retire);lua_setglobal(state,"_retire");
 lua_pushcfunction(state,SetHeldSpriteFilename);lua_setglobal(state,"_setHeldFilename");
 lua_pushcfunction(state,InstallHeldSpriteGuard);lua_setglobal(state,"_installHeldGuard");
 lua_pushcfunction(state,SetPlayerVtable);lua_setglobal(state,"_setPlayerVtable");
 lua_pushcfunction(state,PushPlayer);lua_setglobal(state,"_pushPlayer");
}

int main(){
 SetVtable(kEntityPlayerVtableOffset);
 const std::uint32_t playerType=kEntityTypePlayer;
 std::memcpy(player.data()+kEntityTypeOffset,&playerType,sizeof(playerType));
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(moduleBytes.data()));
 LuaRuntime::ObserveGameThread();
 LuaRuntime::LuaSpriteBindings spriteBindings{};
 spriteBindings.destructor_=DestroySprite;
 LuaRuntime::SetSpriteBindings(spriteBindings);
 Files files(true);SetSessionSaveFilePort(&files);
 const repentogon::NativePort port{Ready,Ready};repentogon::SetNativePort(&port);
 LuaRuntime::SetRuntimeExtensionInstaller(Extensions);

 const char* script=R"lua(
assert(type(player.GetHeldSprite)=='function','EntityPlayer:GetHeldSprite was not registered')
local getHeld=player.GetHeldSprite
local ok,err=pcall(getHeld,player)
assert(not ok and err:find('guard'),tostring(err))
_installHeldGuard()
assert(not pcall(getHeld,{}))
local held=player:GetHeldSprite()
assert(type(held)=='userdata' and held:GetFilename()=='')
assert(GetPtrHash(held)==GetPtrHash(player:GetHeldSprite()))
assert(GetPtrHash(held)~=GetPtrHash(player:GetSprite()))
_setHeldFilename('gfx/held.anm2')
assert(held:GetFilename()=='gfx/held.anm2' and player:GetSprite():GetFilename()=='')
collectgarbage('collect')
assert(held:GetFilename()=='gfx/held.anm2')
_setPlayerVtable(false)
assert(not pcall(function()held:GetFilename()end))
assert(not pcall(getHeld,player))
_retire()
_setPlayerVtable(true)
assert(not pcall(getHeld,player))
assert(not pcall(function()held:GetFilename()end))
assert(_pushPlayer():GetHeldSprite():GetFilename()=='gfx/held.anm2')
assert(not pcall(function()held:GetFilename()end))
)lua";
 if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@held-sprite.lua")!=LuaRuntime::LuaInitResult::Success){
  char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));
  std::fprintf(stderr,"%s\n",error);return 1;
 }
 std::thread worker([]{
  auto* isolated=luaL_newstate();
  lua_pushcfunction(isolated,RepentogonEntityPlayerGetHeldSprite);
  assert(lua_pcall(isolated,0,0,0)!=LUA_OK);
  assert(std::strstr(lua_tostring(isolated,-1),"game thread"));
  lua_close(isolated);
 });worker.join();
 assert(LuaRuntime::ShutdownForModReload());
 assert(spriteDestructors==0);
 LuaRuntime::SetSpriteBindings({});
 repentogon::SetNativePort(nullptr);SetSessionSaveFilePort(nullptr);
 LuaRuntime::SetRuntimeExtensionInstaller(nullptr);
}
'''


class RepentogonHeldSpriteTests(unittest.TestCase):
    def test_borrowed_native_sprite(self):
        with tempfile.TemporaryDirectory(prefix="repentogon-held-sprite-") as folder:
            binary = test_support.build_lua_harness(
                source_root=SOURCE, workdir=Path(folder), harness_source=DRIVER
            )
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
