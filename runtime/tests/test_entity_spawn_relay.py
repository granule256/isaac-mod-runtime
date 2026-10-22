"""编译实际生成中继体，验证九参数、最后栈参数和指针返回，以及中继身份守卫。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_collision_relay_behavior import function
from .test_support import LUA_SOURCE_RELATIVE
ROOT = Path(__file__).resolve().parents[2]

class EntitySpawnRelayTests(unittest.TestCase):
    def test_native_forwarding_and_original_or_registered_entry(self):
        code = (ROOT / 'runtime/source/hook_manager.cpp').read_text()
        constants = (ROOT / 'runtime/source/runtime_constants.hpp').read_text()
        entry = re.search(r'inline constexpr [^;]+\bkGameSpawnExExpectedBytes\b[^;]*;', constants).group(0)
        header = (ROOT / 'runtime/source/lua_runtime.hpp').read_text()
        outcome = re.search(r'struct EntitySpawnOverride \{.*?^\};', header, re.S | re.M).group(0)
        driver = r'''
#include <array>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <type_traits>
namespace LuaRuntime { OUTCOME }
#include "domain/runtime/hook_catalog.hpp"
#include "interfaces/lua/engine_method_lookup.hpp"
using u8 = unsigned char;
ENTRY
static const float pos[]={12,34},vel[]={-5,6};
static bool modify=false;
static int calls=0,pre=0;
static void* native(void* game,std::int32_t type,std::uint32_t variant,const void* p,const void* v,
                    void* spawner,std::uint32_t sub,std::uint32_t seed,std::uint32_t force) {
 assert(game==reinterpret_cast<void*>(0x1000)&&p==pos&&v==vel&&spawner==reinterpret_cast<void*>(0x2000));
 assert(type==(modify?9:5)&&variant==(modify?300U:100U)&&sub==(modify?10U:7U));
 assert(seed==(modify?77U:0xffffffffU)&&force==0x89abcdefU&&pre==calls+1);
 ++calls;return reinterpret_cast<void*>(0xabcdef0123456789ULL);
}
namespace isaac::runtime {
 template<class Fn> Fn Original(HookId id) { assert(id==HookId::GameSpawnEx);return native; }
}
namespace LuaRuntime {
 EntitySpawnOverride DispatchPreEntitySpawn(std::int32_t t,std::uint32_t v,std::uint32_t s,
     const void* p,const void* velPtr,std::uintptr_t owner,std::uint32_t seed) {
  assert(t==5&&v==100&&s==7&&p==pos&&velPtr==vel&&owner==0x2000&&seed==0xffffffffU);++pre;
  return modify?EntitySpawnOverride{true,9,300,10,77}:EntitySpawnOverride{false,t,v,s,seed};
 }
}
RELAY
static unsigned char* begin=nullptr;static unsigned char* end=nullptr;
static bool readable(std::uintptr_t p,std::size_t n){return p>=reinterpret_cast<std::uintptr_t>(begin)&&p<=reinterpret_cast<std::uintptr_t>(end)&&n<=reinterpret_cast<std::uintptr_t>(end)-p;}
int main() {
 using Fn=void*(*)(void*,std::int32_t,std::uint32_t,const void*,const void*,void*,std::uint32_t,std::uint32_t,std::uint32_t);
 static_assert(std::is_same_v<decltype(&EntryRelayGameSpawnExCallback),Fn>);
 for(bool m:{false,true}) {
  modify=m;
  assert(EntryRelayGameSpawnExCallback(reinterpret_cast<void*>(0x1000),5,100,pos,vel,reinterpret_cast<void*>(0x2000),7,0xffffffffU,0x89abcdefU)==reinterpret_cast<void*>(0xabcdef0123456789ULL));
 }
 alignas(8) unsigned char memory[128]{};begin=memory;end=memory+sizeof(memory);
 const auto address=reinterpret_cast<std::uintptr_t>(memory);
 const auto fallback=address+64;
 auto match=[&](std::uintptr_t f){return isaac::runtime::EngineEntryOrRelayMatches<readable>(address,kGameSpawnExExpectedBytes.data(),16,f);};
 std::memcpy(memory,kGameSpawnExExpectedBytes.data(),16);assert(match(0));
 memory[12]^=1;assert(!match(0));
 const std::uint32_t words[]={0x58000050U,0xD61F0200U};
 std::memcpy(memory,words,8);const auto slot=fallback-32;std::memcpy(memory+8,&slot,8);
 std::memcpy(memory+64,kGameSpawnExExpectedBytes.data(),16);assert(match(fallback)&&!match(0));
 memory[76]^=1;assert(!match(fallback));memory[76]^=1;
 memory[8]^=1;assert(!match(fallback));
 assert(calls==2&&pre==2);
}
'''.replace('OUTCOME', outcome).replace('ENTRY', entry).replace('RELAY', function(code, 'EntryRelayGameSpawnExCallback'))
        with tempfile.TemporaryDirectory() as temp:
            source, binary = Path(temp)/'main.cpp', Path(temp)/'probe'
            source.write_text(driver)
            result = subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',
                '-I'+str(ROOT/'runtime/source'),'-I'+str(ROOT/'runtime/src'),'-I'+str(ROOT/'runtime/source'/LUA_SOURCE_RELATIVE),str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__ == '__main__': unittest.main()
