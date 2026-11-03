"""GetStartSeed must preserve uint32 seeds consumed by EID crafting's Lua PRNG."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from .test_lua_api_method_lookup_cost import function
from .test_support import lua_harness_objects

ROOT=Path(__file__).resolve().parents[2]


class StartSeedUnsignedTests(unittest.TestCase):
    def test_full_uint32_range_and_lua_crafting_rng(self):
        source=(ROOT/'runtime/src/interfaces/lua/game_api.cpp').read_text()
        prefix=r'''
#include "runtime_constants.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
constexpr const char* kSeedsMetatable="Seeds";
std::vector<unsigned char> game(kGameSeedsObjectOffset+kSeedsStartSeedOffset+4);
bool available=true;
std::uintptr_t ResolveGame(){return available?reinterpret_cast<std::uintptr_t>(game.data()):0;}
template<class T>bool ReadEngine(std::uintptr_t address,T*value){
    auto begin=reinterpret_cast<std::uintptr_t>(game.data());
    if(address<begin||address>begin+game.size()-sizeof(T))return false;
    std::memcpy(value,reinterpret_cast<void*>(address),sizeof(T));return true;
}
'''
        main=r'''
int main(){
    auto*L=luaL_newstate();assert(L);
    luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
    luaL_newmetatable(L,kSeedsMetatable);lua_pop(L,1);
    lua_newuserdata(L,1);luaL_getmetatable(L,kSeedsMetatable);lua_setmetatable(L,-2);lua_setglobal(L,"seeds");
    lua_pushcfunction(L,SeedsGetStartSeed);lua_setglobal(L,"getStartSeed");
    const std::uint32_t values[]={0,1,0x7fffffffU,0x80000000U,0xf1234567U,0xffffffffU};
    for(auto raw:values){
        std::memcpy(game.data()+kGameSeedsObjectOffset+kSeedsStartSeedOffset,&raw,4);
        lua_pushinteger(L,static_cast<lua_Integer>(raw));lua_setglobal(L,"expected");
        const char*script=R"lua(
            local seed=getStartSeed(seeds)
            assert(seed==expected and seed>=0 and seed<=4294967295,'GetStartSeed must preserve the unsigned 32-bit value')
            if seed~=0 then
                -- EID performs its xorshift in Lua before multiplying by 2^-32.
                local n=seed
                n=n~((n>>1)&4294967295)
                n=n~((n<<5)&4294967295)
                n=n~((n>>16)&4294967295)
                local t=n*2.3283061589829401E-10
                assert(t>=0 and t<1,'negative RNG values select the first crafting item')
            end
        )lua";
        if(luaL_dostring(L,script)){
            std::fprintf(stderr,"seed=%u: %s\n",raw,lua_tostring(L,-1));return 1;
        }
    }
    available=false;
    if(luaL_dostring(L,"assert(getStartSeed(seeds)==0);assert(not pcall(getStartSeed,{}));assert(not pcall(getStartSeed,seeds,1))"))return 2;
    lua_close(L);return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='start-seed-unsigned-') as tmp:
            work=Path(tmp);driver=work/'seed.cpp'
            driver.write_text(prefix+function(source,'int SeedsGetStartSeed(lua_State* state) {')+'\n'+main)
            objects=lua_harness_objects(ROOT/'runtime/source',work)
            result=subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror',
                '-I'+str(ROOT/'runtime/source'),'-I'+str(ROOT/'runtime/source/third_party/lua-5.3.3/src'),
                str(driver),*map(str,objects),'-o',str(work/'seed')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(work/'seed')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
