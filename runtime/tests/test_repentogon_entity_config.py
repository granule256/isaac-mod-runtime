"""EntityConfig borrowed records follow native lookup and current owner membership."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_support

SOURCE = Path(__file__).resolve().parents[1] / 'source'
DRIVER = r'''
#include "interfaces/lua/repentogon_entity_config_api.hpp"
#include "interfaces/lua/repentogon_environment.hpp"
#include "lua_runtime.hpp"
#include "runtime_constants.hpp"
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>
using namespace isaac::runtime;
static std::vector<unsigned char> moduleBytes,manager,entity,player,other;
static std::uintptr_t managerPointer;
static void* currentEntity{};static void* currentPlayer{};
static int entityCalls{},playerCalls{};
template<class T>void Put(std::vector<unsigned char>& b,std::size_t o,T value){std::memcpy(b.data()+o,&value,sizeof(value));}
static void Text(std::vector<unsigned char>& b,std::size_t o,const char* text){
 std::memset(b.data()+o,0,24);b[o]=static_cast<unsigned char>(std::strlen(text)*2);
 std::memcpy(b.data()+o+1,text,std::strlen(text));
}
static void* Entity(void* self,std::int32_t type,std::uint32_t variant,std::uint32_t subtype){
 assert(self==manager.data()+kManagerEntityConfigOffset);++entityCalls;
 assert(type==20||type==999);
 if(type==999)return nullptr;
 assert((variant==1&&subtype==2)||(variant==UINT32_MAX&&subtype==UINT32_MAX));return currentEntity;
}
static void* Player(void* self,std::int32_t type){
 assert(self==manager.data()+kManagerEntityConfigOffset);++playerCalls;
 if(type<0||type>1)return nullptr;return currentPlayer;
}
static int Change(lua_State* L){
 switch(luaL_checkinteger(L,1)){
 case 1:Put(entity,0x58,7.25F);Text(player,0x80,"extra-new.png");break;
 case 2:currentEntity=other.data();currentPlayer=other.data();break;
 case 3:currentEntity=entity.data();currentPlayer=player.data();break;
 case 4:managerPointer=0;break;
 case 5:moduleBytes[0x68684]^=1;break;
 default:break;
 }
 return 0;
}
static const RepentogonApiBinding apis[]={
 {{0x0E023000,ApiDomain::Isaac,"EntityConfig","GetEntity",{},0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},RepentogonEntityConfigGetEntity},
 {{0x0E023001,ApiDomain::Isaac,"EntityConfig","GetPlayer",{},0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},RepentogonEntityConfigGetPlayer},
 {{0x0E023002,ApiDomain::Isaac,"EntityConfigEntity","CanBeChampion",{},0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},RepentogonEntityConfigEntityCanBeChampion},
 {{0x0E023003,ApiDomain::Isaac,"EntityConfigEntity","GetStageHP",{},0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},RepentogonEntityConfigEntityGetStageHP},
 {{0x0E023004,ApiDomain::Isaac,"EntityConfigEntity","GetCollisionRadius",{},0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},RepentogonEntityConfigEntityGetCollisionRadius},
 {{0x0E023005,ApiDomain::Isaac,"EntityConfigPlayer","GetPortraitPath",{},0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},RepentogonEntityConfigPlayerGetPortraitPath},
 {{0x0E023006,ApiDomain::Isaac,"EntityConfigPlayer","GetExtraPortraitPath",{},0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},RepentogonEntityConfigPlayerGetExtraPortraitPath},
 {{0x0E023007,ApiDomain::Isaac,"EntityConfigPlayer","GetNameImagePath",{},0,ThreadAffinity::ManagedCallback,ApiMaturity::Experimental},RepentogonEntityConfigPlayerGetNameImagePath},
};
static int Initialize(lua_State* L){RegisterRepentogonEntityConfigViews(L);return 0;}
static const RepentogonBatch batch{"entity-config",apis,8,nullptr,0,nullptr,0,Initialize};
static const RepentogonCatalog catalog{&batch,1,nullptr};
static void Run(lua_State* L,const char* text){if(luaL_dostring(L,text)){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));std::exit(1);}}
int main(){
 moduleBytes.assign(kGameManagerGlobalSlotOffset+0x100,0);manager.assign(kManagerEntityConfigOffset+0x100,0);
 entity.assign(0x1b0,0);player.assign(0x178,0);other.assign(0x1b0,0);
 managerPointer=reinterpret_cast<std::uintptr_t>(manager.data());
 Put(moduleBytes,kGameManagerGlobalSlotOffset,reinterpret_cast<std::uintptr_t>(&managerPointer));
 const unsigned char entityGuard[]={0x0a,0x8c,0x40,0xf8,0x29,0x2c,0x0c,0x53,0xca,0x02,0x00,0xb4,0x28,0x21,0x02,0x2a};
 const unsigned char playerGuard[]={0x81,0x01,0xf8,0x37,0x08,0xa4,0x41,0xa9,0x29,0x01,0x08,0xcb,0x29,0xfd,0x43,0xd3};
 std::memcpy(moduleBytes.data()+0x68684,entityGuard,16);std::memcpy(moduleBytes.data()+0x700cc,playerGuard,16);
 Put(entity,0x38,std::uint8_t{1});Put(entity,0x3c,12.5F);Put(entity,0x58,3.5F);
 Text(player,0x20,"name.png");Text(player,0x38,"portrait.png");Text(player,0x80,"extra.png");
 currentEntity=entity.data();currentPlayer=player.data();
 LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(moduleBytes.data()));LuaRuntime::ObserveGameThread();
 SetRepentogonEntityConfigNativeTestBindings({Entity,Player});
 auto* L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);BeginRepentogonEnvironment(L,true,catalog);
 RegisterRepentogonEntityConfigViews(L);CompleteRepentogonEnvironment(L);
 lua_pushcfunction(L,Change);lua_setglobal(L,"change");
 Run(L,R"lua(
assert(REPENTOGON==nil)
local e=EntityConfig.GetEntity(20,1,2);assert(type(e)=='userdata')
assert(e:CanBeChampion() and e:GetStageHP()==3.5 and e:GetCollisionRadius()==12.5)
assert(EntityConfig.GetEntity(999)==nil)
assert(EntityConfig.GetEntity(20):GetStageHP()==3.5)
local p=EntityConfig.GetPlayer(1);assert(type(p)=='userdata')
assert(p:GetPortraitPath()=='portrait.png' and p:GetExtraPortraitPath()=='extra.png')
assert(p:GetNameImagePath()=='name.png');assert(EntityConfig.GetPlayer(-1)==nil)
assert(not pcall(EntityConfig.GetEntity,{}));assert(not pcall(EntityConfig.GetPlayer,{}))
assert(not pcall(e.GetStageHP,p));assert(not pcall(p.GetPortraitPath,e))
change(1);assert(e:GetStageHP()==7.25 and p:GetExtraPortraitPath()=='extra-new.png')
change(2);assert(not pcall(e.GetStageHP,e));assert(not pcall(p.GetPortraitPath,p))
change(3);assert(e:GetStageHP()==7.25)
savedEntity=e;savedPlayer=p
)lua");
 const int callsBefore=entityCalls+playerCalls;
 std::thread worker([&]{auto* otherLua=luaL_newstate();
  for(auto fn:{RepentogonEntityConfigGetEntity,RepentogonEntityConfigGetPlayer}){
   lua_pushcfunction(otherLua,fn);lua_pushinteger(otherLua,20);assert(lua_pcall(otherLua,1,1,0)!=LUA_OK);
   assert(std::strstr(lua_tostring(otherLua,-1),"game thread"));lua_pop(otherLua,1);
  }lua_close(otherLua);
 });worker.join();assert(entityCalls+playerCalls==callsBefore);
 Run(L,"change(5);assert(not pcall(EntityConfig.GetEntity,20));change(4);assert(not pcall(savedPlayer.GetPortraitPath,savedPlayer))");
 SuspendRepentogonEnvironment(L);lua_close(L);EndRepentogonEnvironment(nullptr);
 SetRepentogonEntityConfigNativeTestBindings({});
}
'''


class EntityConfigTests(unittest.TestCase):
    def test_record_lookup_fields_strings_and_lifetime(self):
        with tempfile.TemporaryDirectory(prefix='rgon-entity-config-') as folder:
            extra = SOURCE.parent / 'src/interfaces/lua/repentogon_entity_config_api.cpp'
            sources = test_support.layered_lua_runtime_sources
            added = () if extra in sources(SOURCE) else (extra,)
            binary = test_support.build_lua_harness(source_root=SOURCE,workdir=Path(folder),
                                                    harness_source=DRIVER,extra_sources=added)
            result = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
