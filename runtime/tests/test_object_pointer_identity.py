"""公开GetPtrHash必须比较真实对象；不同Lua包装不得破坏别名和寿命。"""
from pathlib import Path
import re,subprocess,tempfile,unittest
from unittest import mock
from . import test_support
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness

MAIN=r'''
#include "lua_object_handles.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include <cassert>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
using namespace isaac::runtime;
extern "C" lua_State* HashTestLuaState();
bool rngAlive=true;
std::array<unsigned char,16> referenceRng{};
std::uintptr_t RngReference(const LuaRuntime::RngHandle*) noexcept {
 return rngAlive?reinterpret_cast<std::uintptr_t>(referenceRng.data()):0;
}
void Run(lua_State* L,const char* script){
 if(luaL_dostring(L,script)){std::fprintf(stderr,"%s\n%s\n",lua_tostring(L,-1),script);std::abort();}
}
void PushRng(lua_State* L,const char* name,bool reference){
 auto* h=static_cast<LuaRuntime::RngHandle*>(lua_newuserdata(L,sizeof(LuaRuntime::RngHandle)));
 new(h)LuaRuntime::RngHandle{};h->resolver=reference?RngReference:nullptr;
 const std::uint32_t seed=12345;std::memcpy(h->storage.data(),&seed,4);
 luaL_getmetatable(L,LuaRuntime::kRngMetatable);lua_setmetatable(L,-2);lua_setglobal(L,name);
}
int main(){
 static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);
 static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
 CreateBlocks();g_GameBytes.resize(0x350000);FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
 LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 assert(LuaRuntime::InitializeFromBuffer("return true",11,"@identity.lua")==LuaRuntime::LuaInitResult::Success);
 auto* L=HashTestLuaState();assert(L);
 LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
 PushEntityCallbackArgument(L,AddressOf(g_Entities[kPlayer]));lua_setglobal(L,"player");
 lua_pushinteger(L,static_cast<lua_Integer>(AddressOf(g_GameBytes)));lua_setglobal(L,"gameAddress");
 lua_pushinteger(L,static_cast<lua_Integer>(AddressOf(g_RoomBytes)));lua_setglobal(L,"roomAddress");
 PushRng(L,"rngA",false);PushRng(L,"rngB",false);PushRng(L,"refA",true);PushRng(L,"refB",true);
 Run(L,R"lua(
  local ga,gb=Game(),Game();assert(ga~=gb)
  assert(GetPtrHash(ga)==gameAddress and GetPtrHash(gb)==gameAddress,'Game real identity missing')
  assert(GetPtrHash(ga:GetLevel())==gameAddress,'embedded Level identity changed')
  local ra,rb=ga:GetRoom(),gb:GetRoom();assert(ra~=rb)
  assert(GetPtrHash(ra)==roomAddress and GetPtrHash(rb)==roomAddress,'Room alias identity missing')
  assert(GetPtrHash(rngA)~=0 and GetPtrHash(rngB)~=0 and GetPtrHash(rngA)~=GetPtrHash(rngB),'owned RNG states collide')
  assert(GetPtrHash(refA)~=0 and GetPtrHash(refA)==GetPtrHash(refB),'reference RNG aliases differ')
  local seed=rngA:GetSeed();for i=1,50 do assert(GetPtrHash(rngA)~=0)end;assert(rngA:GetSeed()==seed,'hash advanced RNG')
  spriteA=player:GetSprite();spriteB=player:GetSprite();assert(spriteA~=spriteB)
  assert(GetPtrHash(spriteA)~=0 and GetPtrHash(spriteA)==GetPtrHash(spriteB),'borrowed Sprite aliases differ')
  assert(not pcall(GetPtrHash,nil) and not pcall(GetPtrHash,{}) and not pcall(GetPtrHash,42),'PC rejects non-userdata')
  assert(not pcall(GetPtrHash));assert(GetPtrHash(ga,gb)==gameAddress,'PC ignores extra arguments')
 )lua");
 rngAlive=false;
 RetireEntityLifetime(AddressOf(g_Entities[kPlayer]));
 Run(L,"assert(GetPtrHash(refA)==0 and GetPtrHash(refB)==0);assert(GetPtrHash(spriteA)==0 and GetPtrHash(spriteB)==0);assert(GetPtrHash(player)==0)");
 WriteWord(g_OwnerSlotBytes,0,0);
 Run(L,"assert(GetPtrHash(Game())==0 and GetPtrHash(Game():GetRoom())==0)");
 return 0;
}
'''
class ObjectPointerIdentityTests(unittest.TestCase):
 def test_real_object_aliases_distinct_objects_and_lifetime(self):
  prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
  prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
  prefix=prefix.replace("GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}",r'''GameRoomObservation ReadCurrentGameRoom(uintptr_t slot,void** room) {
    std::uintptr_t variable{},game{},value{};
    if(!slot)return GameRoomObservation::OwnerNull;
    std::memcpy(&variable,reinterpret_cast<void*>(slot),sizeof(variable));
    if(!variable)return GameRoomObservation::GameNull;
    std::memcpy(&game,reinterpret_cast<void*>(variable),sizeof(game));
    if(!game)return GameRoomObservation::GameNull;
    std::memcpy(&value,reinterpret_cast<void*>(game+kGameRoomPointerOffset),sizeof(value));
    *room=reinterpret_cast<void*>(value);
    return value?GameRoomObservation::Success:GameRoomObservation::RoomNull;
}''')
  with tempfile.TemporaryDirectory(prefix='object-pointer-identity-')as d:
   actual=fixture.SOURCE/'lua_runtime.cpp';temporary=Path(d)/'identity_runtime.cpp'
   temporary.write_text(actual.read_text()+'\nextern "C" lua_State* HashTestLuaState(){return LuaRuntime::g_LuaState;}\n')
   sources=[temporary if x==actual else x for x in test_support.layered_lua_runtime_sources(fixture.SOURCE)]
   with mock.patch.object(test_support,'layered_lua_runtime_sources',return_value=sources):
    binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d)/'build',harness_source=prefix+MAIN)
   r=subprocess.run([str(binary)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
