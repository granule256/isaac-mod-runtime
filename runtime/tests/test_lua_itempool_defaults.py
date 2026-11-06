"""ItemPool:GetCollectible uses PC defaults and forwards them to the native pool."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_support import build_lua_harness

SOURCE = Path(__file__).resolve().parents[1] / "source"
HARNESS = r'''
#include "lua_runtime.hpp"
#include "game_observer.hpp"
#include "interfaces/lua/remaining_api.hpp"
#include "runtime_constants.hpp"
#include <cstdio>
#include <cstring>
#include <vector>
static unsigned calls=0,randomCalls=0;
static unsigned char pool[16]{};
static std::uint32_t Random(){return 100U+randomCalls++;}
GameItemPoolObservation ReadCurrentGameItemPool(uintptr_t,void** out) {
    *out=pool;return GameItemPoolObservation::Success;
}
static std::uint32_t Collect(void* object,std::uint32_t type,std::uint32_t seed,
                             std::uint32_t noDecrease,std::uint32_t fallback) {
    const std::uint32_t expected[][4]={
        {7,100,1,0},{7,101,1,0},{8,102,0,0},{9,103,1,13},
        {7,0,1,0},{8,12,0,13},{7,13,1,0},
        {7,0xffffffffU,1,0},{7,0,1,0},{7,3,1,0},
    };
    if(object!=pool||calls>=10)return 0;
    const auto& row=expected[calls++];
    return type==row[0]&&seed==row[1]&&noDecrease==row[2]&&fallback==row[3]?701:0;
}
int main() {
    std::vector<unsigned char> image(kRandomU32Offset+8);
    std::memcpy(image.data()+kRandomU32Offset,&kRandomU32EntryWord,4);
    LuaRuntime::SetEngineModuleBase(reinterpret_cast<std::uintptr_t>(image.data()));
    isaac::runtime::SetRandomU32HostImplementation(Random);
    LuaRuntime::SetItemPoolGetCollectibleBinding(reinterpret_cast<std::uintptr_t>(Collect));
    const char* script=R"lua(
        local p=Game():GetItemPool()
        assert(p:GetCollectible(7)==701)
        assert(p:GetCollectible(7,false)==701)
        assert(p:GetCollectible(8,true)==701)
        assert(p:GetCollectible(9,nil,nil,13)==701)
        assert(p:GetCollectible(7,false,0)==701)
        assert(p:GetCollectible(8,true,12,13)==701)
        assert(p:GetCollectible(7,false,13,nil)==701)
        -- PC's integer conversion preserves the low 32 seed bits, including
        -- signed Room:GetSpawnSeed() values used by revival and boss scripts.
        assert(p:GetCollectible(7,false,-1)==701)
        assert(p:GetCollectible(7,false,4294967296)==701)
        assert(p:GetCollectible(7,false,8589934595)==701)
        for _,args in ipairs({{}, {7,false,'bad'},
            {7,false,1,-1}, {7,false,1,0,0}}) do
            assert(not pcall(function()p:GetCollectible(table.unpack(args))end))
        end
        local mod=RegisterMod('PoolDefaults',1)
        mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function()end)
    )lua";
    const auto result=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@pool-defaults.lua");
    char error[1024]{};(void)LuaRuntime::CopyLastLuaErrorText(error,sizeof(error));
    std::printf("status=%u calls=%u random=%u error=%s\n",unsigned(result),calls,randomCalls,error);
    return result==LuaRuntime::LuaInitResult::Success&&calls==10&&randomCalls==4?0:1;
}
'''


class LuaItemPoolDefaultsTests(unittest.TestCase):
    def test_defaults_reach_native_pool_and_explicit_seed_does_not_consume_random(self):
        with tempfile.TemporaryDirectory(prefix="isaac-pool-defaults-") as temporary:
            binary = build_lua_harness(source_root=SOURCE, workdir=Path(temporary),
                                       harness_source=HARNESS)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
