"""Legacy innate counts stay separate from real inventory and other players."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from . import test_repentogon_player_api as fixture
from . import test_support

ROOT = Path(__file__).resolve().parents[1]

DRIVER = r'''
#include "application/player/innate_collectibles.hpp"
#include <cassert>
#include <climits>
using namespace isaac::runtime::innate_collectibles;
int main() {
    assert(Count(1, 20) == 0);
    Change(1, 20, 2);
    Change(1, 20, 1);
    assert(Count(1, 20) == 3);
    assert(Count(2, 20) == 0 && Count(1, 21) == 0);
    assert(EffectiveCount(1, 20, 4, false) == 7);
    assert(EffectiveCount(1, 20, 4, true) == 4);
    assert(EffectiveHas(1, 20, false, false));
    assert(!EffectiveHas(1, 20, false, true));
    Change(1, 20, -1);
    assert(Count(1, 20) == 2);
    Change(1, 20, INT_MIN);
    assert(Count(1, 20) == 0 && EffectiveCount(1, 20, 4, false) == 4);
    Change(1, 20, -1);
    assert(Count(1, 20) == 0);
    Change(1, 20, INT_MAX);
    Change(1, 20, 1);
    assert(EffectiveCount(1, 20, 1, false) == INT_MAX);
    Change(2, 20, 2);
    ResetPlayer(1);
    assert(Count(1, 20) == 0 && Count(2, 20) == 2);
    Reset();
    assert(Count(2, 20) == 0);
}
'''


class InnateCollectiblesTests(unittest.TestCase):
    def test_inventory_modifiers(self):
        with tempfile.TemporaryDirectory(prefix="innate-counts-") as temporary:
            source = Path(temporary) / "driver.cpp"
            binary = Path(temporary) / "test"
            source.write_text(DRIVER)
            subprocess.run(
                ["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror",
                 "-I", str(ROOT / "src"), str(source), "-o", str(binary)],
                check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_mgo_legacy_add_remove_and_continue(self):
        source = fixture.DRIVER.replace(
            "static int calls;", r'''
#include "interfaces/lua/repentogon_innate_collectible_api.hpp"
#include "application/player/innate_collectibles.hpp"
static int calls;
static unsigned char innateItem[0x100]{};
static unsigned evaluations, costumes;
static std::uintptr_t Item(std::int32_t id) {
 return id == 20 ? reinterpret_cast<std::uintptr_t>(innateItem) : 0;
}
static void Costume(void* p,const void* item,bool keep) {
 assert(p==player.data()&&item==innateItem&&!keep);++costumes;
 const std::uint32_t flags=3;
 std::memcpy(player.data()+kEntityPlayerCacheFlagsOffset,&flags,4);
}
static void EvaluateInnate(void* p) {
 assert(p==player.data());++evaluations;
 const auto extra=innate_collectibles::Count(reinterpret_cast<std::uintptr_t>(p),20);
 assert(extra>=0&&extra<=2);
 std::uint32_t flags{};
 std::memcpy(&flags,player.data()+kEntityPlayerCacheFlagsOffset,4);
 assert(flags==7);
}
static int ResetInnate(lua_State*) {innate_collectibles::Reset();return 0;}
''')
        source = source.replace(
            'lua_setglobal(state,"player");',
            '''lua_setglobal(state,"player");
 lua_pushcfunction(state,ResetInnate);lua_setglobal(state,"_resetInnate");''')
        source = source.replace(
            "LuaRuntime::SetRuntimeExtensionInstaller(Extensions);",
            '''const std::uint32_t flags=4, pending=1;
 std::memcpy(innateItem+kItemConfigItemCacheFlagsOffset,&flags,4);
 innateItem[kApi600ItemConfigShouldAddCostumeOnPickupFieldOffset]=1;
 std::memcpy(player.data()+kEntityPlayerCacheFlagsOffset,&pending,4);
 SetInnateCollectibleTestBindings({Item,Costume,EvaluateInnate});
 LuaRuntime::SetRuntimeExtensionInstaller(Extensions);''')
        begin = source.index('const char* script=R"lua(')
        end = source.index(')lua";', begin) + len(')lua";')
        source = source[:begin] + r'''
 const char* script=R"lua(
assert(type(player.AddInnateCollectible)=='function')
player:AddInnateCollectible(20)
assert(player:GetCollectibleNum(20)==1)
assert(player:GetCollectibleNum(20,true)==0)
assert(player:HasCollectible(20) and not player:HasCollectible(20,true))
player:AddInnateCollectible(20,1,false)
assert(player:GetCollectibleNum(20)==2)
player:AddInnateCollectible(20,-1)
assert(player:GetCollectibleNum(20)==1)
player:AddInnateCollectible(20,-100)
assert(player:GetCollectibleNum(20)==0)
assert(not player:HasCollectible(20))
assert(not pcall(function()player:AddInnateCollectible(21)end))
assert(not pcall(function()player:AddInnateCollectible(20,1,'group')end))
assert(not pcall(player.AddInnateCollectible,{},20))
player:AddInnateCollectible(20)
_resetInnate()
assert(player:GetCollectibleNum(20)==0)
-- MGO restores its saved ItemList in MC_POST_GAME_STARTED on continue.
player:AddInnateCollectible(20)
assert(player:GetCollectibleNum(20)==1)
_retire()
assert(not pcall(function()player:AddInnateCollectible(20)end))
)lua";''' + source[end:]
        source = source.replace(
            "assert(calls==4);",
            "assert(evaluations==6 && costumes==4);"
            "assert(innate_collectibles::Count("
            "reinterpret_cast<std::uintptr_t>(player.data()),20)==0);")
        with tempfile.TemporaryDirectory(prefix="innate-api-") as temporary:
            binary = test_support.build_lua_harness(
                source_root=fixture.SOURCE, workdir=Path(temporary),
                harness_source=source)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
