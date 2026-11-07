"""Native entity reinitialization replaces GetData without retiring live aliases."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import LUA_SOURCE_RELATIVE, lua_harness_objects

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'runtime/source'
BRIDGE = SOURCE / 'entity_init_hook.cpp'
DRIVER = r'''
#include "interfaces/lua/entity_lifetime.hpp"
#include "entity_init_hook.hpp"
#include "lua_object_handles.hpp"
extern "C" {
#include "lua.h"
#include "lauxlib.h"
}
#include <cassert>
#include <cstdlib>
#include <cstring>
using namespace isaac::runtime;
struct Allocator { bool fail{}; unsigned attempts{}; };
static void* Allocate(void* user,void* old,size_t,size_t size){
    auto& a=*static_cast<Allocator*>(user);
    if(!size){std::free(old);return nullptr;}
    ++a.attempts;if(a.fail)return nullptr;return std::realloc(old,size);
}
static lua_State* state{};
static const void* expectedData{};
static unsigned calls{};
static void NativeInit(void* entity,std::uint32_t type,std::uint32_t variant,
                       std::uint32_t subtype,std::uint32_t seed){
    assert(reinterpret_cast<std::uintptr_t>(entity)==0x1234);
    assert(type==5&&variant==10&&subtype==3&&seed==0xabcdef01);
    ++calls;
    if(state){
        const int top=lua_gettop(state);
        PushEntityLifetimeData(state,0x1234);
        assert(lua_topointer(state,-1)==expectedData);
        lua_settop(state,top);
    }
}
namespace LuaRuntime {
void DispatchNativeTearInit(std::uintptr_t) noexcept {}
void DispatchNativeEffectInit(std::uintptr_t) noexcept {}
void DispatchNativePickupInit(std::uintptr_t) noexcept {}
}
static EntityInitNativeBindings native{NativeInit};
int main(){
    // Native initialization also runs before any Lua state or entity data exists.
    RunNativeEntityInit(&native,NativeEntityInitKind::Base,reinterpret_cast<void*>(0x1234),5,10,3,0xabcdef01);
    Allocator allocator;state=lua_newstate(Allocate,&allocator);assert(state);
    assert(lua_checkstack(state,80));
    auto* token=PushEntityLifetimeToken(state,0x1234);
    PushEntityLifetimeData(state,0x1234);
    lua_pushliteral(state,"Coin");lua_setfield(state,-2,"MinimapAPIPickupID");
    expectedData=lua_topointer(state,-1);
    const int saved=luaL_ref(state,LUA_REGISTRYINDEX);
    PushEntityLifetimeData(state,0x5678);
    const void* otherData=lua_topointer(state,-1);lua_pop(state,1);
    for(unsigned repeat=0;repeat<2;++repeat){
        // A pooled/reinitialized object can retain its token without passing through D2.
        const int top=lua_gettop(state);
        const unsigned attempts=allocator.attempts;allocator.fail=true;
        RunNativeEntityInit(&native,NativeEntityInitKind::Base,reinterpret_cast<void*>(0x1234),5,10,3,0xabcdef01);
        assert(lua_gettop(state)==top&&allocator.attempts==attempts&&token->alive);
        allocator.fail=false;
        assert(PushEntityLifetimeToken(state,0x1234)==token);lua_pop(state,1);
        PushEntityLifetimeData(state,0x1234);
        assert(lua_topointer(state,-1)!=expectedData);
        lua_getfield(state,-1,"MinimapAPIPickupID");assert(lua_isnil(state,-1));lua_pop(state,1);
        expectedData=lua_topointer(state,-1);
        auto* coroutine=lua_newthread(state);
        PushEntityLifetimeData(coroutine,0x1234);
        assert(lua_topointer(coroutine,-1)==expectedData);lua_pop(coroutine,1);
        lua_pop(state,2);
        PushEntityLifetimeData(state,0x5678);assert(lua_topointer(state,-1)==otherData);lua_pop(state,1);
    }
    assert(calls==3);
    lua_rawgeti(state,LUA_REGISTRYINDEX,saved);
    lua_getfield(state,-1,"MinimapAPIPickupID");
    assert(lua_isstring(state,-1)&&std::strcmp(lua_tostring(state,-1),"Coin")==0);
    luaL_unref(state,LUA_REGISTRYINDEX,saved);
    ResetEntityLifetimeState();lua_close(state);state=nullptr;
    RunNativeEntityInit(&native,NativeEntityInitKind::Base,reinterpret_cast<void*>(0x1234),5,10,3,0xabcdef01);
    assert(calls==4);
}
'''

class EntityInitDataTests(unittest.TestCase):
    def test_native_initialization_bridge_exists(self):
        self.assertTrue(BRIDGE.is_file(), 'Native entity Init does not reset GetData')

    def test_native_init_resets_data_preserves_aliases_and_never_allocates(self):
        if not BRIDGE.is_file():
            self.skipTest('Native initialization bridge is not implemented')
        with tempfile.TemporaryDirectory(prefix='entity-init-data-') as directory:
            work = Path(directory)
            driver = work / 'driver.cpp'; driver.write_text(DRIVER)
            objects = lua_harness_objects(SOURCE, work)
            binary = work / 'driver'
            result = subprocess.run([
                'clang++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                '-I', str(SOURCE), '-I', str(ROOT / 'runtime/src'),
                '-I', str(SOURCE / LUA_SOURCE_RELATIVE), str(driver), str(BRIDGE),
                str(ROOT / 'runtime/src/interfaces/lua/entity_lifetime.cpp'),
                *map(str, objects), '-o', str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
