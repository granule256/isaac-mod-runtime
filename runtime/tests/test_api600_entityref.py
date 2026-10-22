"""第六批EntityRef两字段；独立核真实引擎构造前缀和原生回调快照。"""
import unittest
from .test_api400_params import run_main
MAIN=r'''
#include "interfaces/lua/entity_ref_api.hpp"
#include "interfaces/lua/isaac_api.hpp"
#include "interfaces/lua/entity_lifetime.hpp"
#include "lua_object_handles.hpp"
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace isaac::runtime;
template<class T>T RefAt(const void*p,unsigned o){T v{};std::memcpy(&v,static_cast<const char*>(p)+o,sizeof(v));return v;}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);CreateBlocks();FillEntities();WriteWord(g_Entities[kEnemyA],0,g_EngineBase+kEntityNpcVtableOffset);WriteAt<std::uint32_t>(g_Entities[kEnemyA],kEntityVariantOffset,7);WriteAt<std::uint32_t>(g_Entities[kEnemyA],kEntitySpawnerTypeOffset,1);WriteAt<std::uint32_t>(g_Entities[kEnemyA],kEntitySpawnerVariantOffset,0xf1234567U);WriteAt<LuaRuntime::VectorHandle>(g_Entities[kEnemyA],0x310,LuaRuntime::VectorHandle{3,4});WriteAt<LuaRuntime::VectorHandle>(g_Entities[kEnemyA],0x334,LuaRuntime::VectorHandle{5,6});WriteAt<std::uint64_t>(g_Entities[kEnemyA],0x1b8,(1ULL<<8)|(1ULL<<29)|(1ULL<<54));PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);LuaRuntime::SetEngineModuleBase(g_EngineBase);LuaRuntime::SetGameBindings(g_EngineBase+kGameOwnerGlobalSlotOffset,0x2222);
const char*body="local r=EntityRef(Isaac.FindByType(20)[1]);assert(r.SpawnerType==1 and r.SpawnerVariant==0xf1234567,'missing EntityRef spawner snapshot')";
if(LuaRuntime::InitializeFromBuffer(body,std::strlen(body),"@api600-ref.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView es[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(es,8);for(std::size_t i=0;i<n;++i)std::fprintf(stderr,"%s\n",es[i].text);return 9;}
auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);static_cast<void>(RegisterIsaacApi(L));luaL_newmetatable(L,LuaRuntime::kEntityRefMetatable);lua_pushcfunction(L,EntityRefIndex);lua_setfield(L,-2,"__index");lua_pop(L,1);lua_pushcfunction(L,CreateEntityRefHandle);lua_setglobal(L,"EntityRef");PushEntityCallbackArgument(L,AddressOf(g_Entities[kEnemyA]));lua_setglobal(L,"e");
if(luaL_dostring(L,"r=EntityRef(e);assert(r.Type==20 and r.Variant==7);assert(r.SpawnerType==1 and r.SpawnerVariant==0xf1234567,'new spawner snapshot');assert(not pcall(function()r.SpawnerType=9 end))")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;}
lua_getglobal(L,"r");const auto*raw=EntityRefBufferAt(L,-1);assert(raw);assert(RefAt<std::uint32_t>(raw,0)==20);assert(RefAt<std::uint32_t>(raw,4)==7);assert(RefAt<std::uint32_t>(raw,8)==1);assert(RefAt<std::uint32_t>(raw,12)==0xf1234567U);assert(RefAt<float>(raw,0x10)==3&&RefAt<float>(raw,0x14)==4&&RefAt<float>(raw,0x18)==5&&RefAt<float>(raw,0x1c)==6);assert(RefAt<std::uint32_t>(raw,0x20)==7);assert(RefAt<std::uintptr_t>(raw,0x28)==AddressOf(g_Entities[kEnemyA]));lua_pop(L,1);
WriteAt<std::uint32_t>(g_Entities[kEnemyA],kEntitySpawnerTypeOffset,9);if(luaL_dostring(L,"assert(r.SpawnerType==1)")){return 2;}
std::array<unsigned char,kEntityRefStorageSize> native{};std::uint32_t type=99,variant=88;std::int32_t spawner=-7;std::uint32_t sv=0xf2345678U;std::memcpy(native.data(),&type,4);std::memcpy(native.data()+4,&variant,4);std::memcpy(native.data()+8,&spawner,4);std::memcpy(native.data()+12,&sv,4);PushEntityRefArgument(L,reinterpret_cast<std::uintptr_t>(native.data()));lua_setglobal(L,"callbackRef");if(luaL_dostring(L,"assert(callbackRef.Type==99 and callbackRef.Variant==88 and callbackRef.SpawnerType==-7 and callbackRef.SpawnerVariant==0xf2345678)")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 3;}lua_close(L);return 0;}
'''
class EntityRefSnapshots(unittest.TestCase):
 def test_actual_native_snapshot(self):
  r=run_main(MAIN);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
