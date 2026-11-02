"""Vanilla argument consumption through compatibility wrappers with trailing arguments."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include "interfaces/lua/field_api.hpp"
#include "interfaces/lua/lua_integer_argument.hpp"
#include "infrastructure/call/engine_call_access.hpp"
#include <cassert>
#include <limits>
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
namespace ForwardingProbe {
using namespace isaac::runtime;
static int handle;
static unsigned calls;
int* CheckEntityHandle(lua_State*,int) {return &handle;}
std::uintptr_t ValidatedEntityPlayer(int*) {return 0x1000;}
std::uint32_t Add(std::uintptr_t player,std::uint32_t type,std::uint32_t charge,
                  std::uint32_t first,std::uint32_t slot,std::uint32_t data) {
    assert(player==0x1000 && type==10 && charge==2 && first==0 && slot==3 && data==4);
    ++calls;return 0;
}
std::uint32_t Has(std::uintptr_t player,std::uint32_t type,std::uint32_t) {
    assert(player==0x1000 && type==10);return 1;
}
std::uintptr_t AddCollectibleMethod() {return engine_call::AddressOfFunction(&Add);}
std::uintptr_t HasCollectibleMethod() {return engine_call::AddressOfFunction(&Has);}
@BODY@
}
int main() {
    static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
    static_cast<void>(&CreateBlocks);static_cast<void>(&FillEntities);
    static_cast<void>(&PublishEntityList);static_cast<void>(&PublishLists);
    static_cast<void>(&PublishGame);
    auto* L=luaL_newstate();luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
    lua_pushcfunction(L,ForwardingProbe::EntityPlayerAddCollectible);lua_setglobal(L,"add");
    const char* script=R"lua(
        assert(add({},10,2,false,3,4))
        assert(add({},10,2,false,3,4,0))
        assert(add({},10,2,false,3,4,nil))
        assert(not pcall(function()add({},{},2,false,3,4,0)end))
    )lua";
    if(luaL_dostring(L,script)!=LUA_OK) {
        std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 1;
    }
    assert(ForwardingProbe::calls==3);lua_close(L);
}
'''


class AddCollectibleForwardingTests(unittest.TestCase):
    def test_trailing_arguments_preserve_native_argument_consumption(self):
        source = (ROOT / 'runtime/src/interfaces/lua/isaac_api.cpp').read_text()
        start = source.index('int EntityPlayerAddCollectible(lua_State* state) {')
        body = source[start:source.index('\n}', start) + 2]
        prefix = fixture.HARNESS[:fixture.HARNESS.index('int main(')]
        prefix = re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}',
                        '', prefix, count=1)
        with tempfile.TemporaryDirectory(prefix='collectible-forwarding-') as folder:
            binary = build_lua_harness(source_root=fixture.SOURCE, workdir=Path(folder),
                                       harness_source=prefix + DRIVER.replace('@BODY@', body))
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
