"""Native form counters are authoritative; item grants must preserve their input flag."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_lua_api_method_lookup_cost import function
from .test_support import lua_harness_objects

ROOT = Path(__file__).resolve().parents[2]

PREFIX = r'''
#include "runtime_constants.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
namespace engine_call {
template<class T>T AsFunction(std::uintptr_t address){return reinterpret_cast<T>(address);}
}
constexpr const char* kEntityPlayerMetatable="Player";
struct EntityHandle {};
std::array<unsigned char,0x1ca0> nativePlayer{};
unsigned expectedFirst=1,grants=0;
bool failed=false;
bool playerAvailable=true,counterReadable=true;
EntityHandle* CheckEntityHandle(lua_State*L,int index){return static_cast<EntityHandle*>(luaL_checkudata(L,index,kEntityPlayerMetatable));}
std::uintptr_t ValidatedEntityPlayer(EntityHandle*){return playerAvailable?reinterpret_cast<std::uintptr_t>(nativePlayer.data()):0;}
bool ReadIntegerArgument(lua_State*L,int index,lua_Integer*out){return isaac::runtime::IntegerArgumentAt(L,index,out);}
bool EntityPlayerProbeIdArgument(lua_State*L,const char*,bool,void*){CheckEntityHandle(L,1);luaL_checkinteger(L,2);return true;}
void PushZero(lua_State*L){lua_pushinteger(L,0);}
template<class T>bool ReadEngine(std::uintptr_t address,T*out){
 if(!counterReadable)return false;
 const auto start=reinterpret_cast<std::uintptr_t>(nativePlayer.data());
 if(address<start||address>start+nativePlayer.size()-sizeof(T))return false;
 std::memcpy(out,reinterpret_cast<void*>(address),sizeof(T));return true;
}
std::uint32_t NativeAdd(std::uintptr_t player,std::uint32_t item,std::uint32_t charge,
                        std::uint32_t first,std::uint32_t slot,std::uint32_t data){
 ++grants;
 if(player!=reinterpret_cast<std::uintptr_t>(nativePlayer.data())||item!=134||charge||slot||data||first!=expectedFirst){
  std::fprintf(stderr,"native grant FirstTimePickingUp: expected %u, received %u\n",expectedFirst,first);failed=true;
 }
 return 0;
}
std::uint32_t NativeHas(std::uintptr_t,std::uint32_t,std::uint32_t){return 1;}
std::uintptr_t AddCollectibleMethod(){return reinterpret_cast<std::uintptr_t>(&NativeAdd);}
std::uintptr_t HasCollectibleMethod(){return reinterpret_cast<std::uintptr_t>(&NativeHas);}
'''

MAIN = r'''
int main(int argc,char**argv){
 if(argc!=2)return 9;
 auto*L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 luaL_newmetatable(L,kEntityPlayerMetatable);lua_pushvalue(L,-1);lua_setfield(L,-2,"__index");
 lua_pushcfunction(L,EntityPlayerAddCollectible);lua_setfield(L,-2,"AddCollectible");
 lua_pushcfunction(L,EntityPlayerGetPlayerFormCounter);lua_setfield(L,-2,"GetPlayerFormCounter");lua_pop(L,1);
 lua_newuserdata(L,sizeof(EntityHandle));luaL_getmetatable(L,kEntityPlayerMetatable);lua_setmetatable(L,-2);lua_setglobal(L,"p");
 auto run=[&](const char*script){
  if(luaL_dostring(L,script)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));failed=true;lua_pop(L,1);}
 };
 if(!std::strcmp(argv[1],"grant")){
  expectedFirst=1;
  run("p:AddCollectible(134);p:AddCollectible(134,0);p:AddCollectible(134,0,nil);p:AddCollectible(134,0,true)");
  expectedFirst=0;run("p:AddCollectible(134,0,false);p:AddCollectible(134,0,false,0,0,nil)");
  if(grants!=6)failed=true;
 }else if(!std::strcmp(argv[1],"unavailable")){
  playerAvailable=false;
  run("assert(not pcall(p.GetPlayerFormCounter,p,0), 'an unavailable player is not a genuine zero counter')");
  playerAvailable=true;counterReadable=false;
  run("assert(not pcall(p.GetPlayerFormCounter,p,0), 'an unreadable native counter is not zero')");
  counterReadable=true;run("assert(p:GetPlayerFormCounter(0)==0, 'a readable native zero remains valid')");
 }else{
  // Native HasPlayerForm and increment_player_form_counter both access +0x1c54.
  // Neighboring completion-history bits and unrelated bytes must not supply progress.
  std::memset(nativePlayer.data(),0x7f,nativePlayer.size());
  for(unsigned form=0;form<15;++form){
   const std::int32_t count=static_cast<std::int32_t>(form%5);
   std::memcpy(nativePlayer.data()+0x1c54+form*4,&count,4);
  }
  run("for form=0,14 do assert(p:GetPlayerFormCounter(form)==form%5) end;assert(p:GetPlayerFormCounter(15)==0)");
  const std::int32_t changed=2;std::memcpy(nativePlayer.data()+0x1c54,&changed,4);
  run("assert(p:GetPlayerFormCounter(0)==2, 'read the current native counter without inventory reconstruction')");
 }
 lua_close(L);return failed?1:0;
}
'''


class NativePlayerFormStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='isaac-native-forms-')
        path = Path(cls.temporary.name)
        source = (ROOT/'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
        body = function(source, 'int EntityPlayerAddCollectible(lua_State* state) {') + '\n' + function(
            source, 'int EntityPlayerGetPlayerFormCounter(lua_State* state) {')
        (path/'test.cpp').write_text(PREFIX+body+MAIN)
        objects = lua_harness_objects(ROOT/'runtime/source', path)
        cls.binary = path/'test'
        result = subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'runtime/source'),'-I'+str(ROOT/'runtime/src'),
            '-I'+str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),str(path/'test.cpp'),
            *map(str,objects),'-o',str(cls.binary)],capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_default_and_explicit_first_pickup_flags_reach_native_grant(self):
        result = subprocess.run([str(self.binary),'grant'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_progress_reads_the_live_native_counter_array(self):
        result = subprocess.run([str(self.binary),'counter'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_unavailable_native_state_is_not_reported_as_zero_progress(self):
        result = subprocess.run([str(self.binary),'unavailable'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
