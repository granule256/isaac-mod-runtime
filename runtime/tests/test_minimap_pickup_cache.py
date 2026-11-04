"""Level rerolls invalidate only MiniMAPI's affected saved pickup icons."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from .test_support import LUA_SOURCE_RELATIVE, lua_harness_objects


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'runtime/source'
HELPER = ROOT / 'runtime/src/interfaces/lua/minimap_pickup_cache.cpp'
BUILD = ROOT.parents[1] / 'data/build/minimap-pickup-test'

DRIVER = r'''
#include "interfaces/lua/minimap_pickup_cache.hpp"
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
#include <cassert>
#include <cstdio>
#include <cstdlib>
using namespace isaac::runtime;
struct Allocator { bool fail{}; unsigned calls{}; };
static void* Allocate(void* user,void* old,size_t,size_t size){
    if(!size){std::free(old);return nullptr;}
    auto& a=*static_cast<Allocator*>(user);++a.calls;
    if(a.fail)return nullptr;
    return std::realloc(old,size);
}
static void Run(lua_State* L,const char* script){
    if(luaL_dostring(L,script)!=LUA_OK){
        std::fprintf(stderr,"%s\n",lua_tostring(L,-1));std::abort();
    }
}
int main(){
    Allocator allocator;
    auto* L=lua_newstate(Allocate,&allocator);assert(L);
    luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
    luaL_requiref(L,LUA_TABLIBNAME,luaopen_table,1);lua_pop(L,1);
    assert(lua_checkstack(L,80));
    ResetMinimapPickupCache();
    assert(!HasPendingMinimapPickupReroll());
    Run(L,R"lua(
      function setup()
        local defs={
          Coin={Type=5,Variant=20,SubType=-1,IconID='Coin'},
          Item={Type=5,Variant=100,SubType=-1,IconID='Item'},
          CustomItem={Type=5,Variant=100,SubType=123,IconID='CustomItem'},
          DadNote={Type=5,Variant=100,SubType=668,IconID='DadNote'},
          EmptyItem={Type=5,Variant=100,SubType=0,IconID='EmptyItem'},
          BigChest={Type=5,Variant=340,SubType=-1,IconID='Flag'},
          Trophy={Type=5,Variant=370,SubType=-1,IconID='Flag'},
          Bed={Type=5,Variant=380,SubType=-1,IconID='Bed'},
          MomChest={Type=5,Variant=390,SubType=-1,IconID='MomChest'},
          BombChest={Type=5,Variant=41,SubType=-1,IconID='BombChest'},
          SharedPickup={Type=5,Variant=10,SubType=-1,IconID='Shared'},
          SharedNonPickup={Type=33,Variant=4,SubType=-1,IconID='Shared'},
          SharedGridPickup={Type=5,Variant=30,SubType=-1,IconID='SharedGrid'},
          SharedKindsPickup={Type=5,Variant=40,SubType=-1,IconID='SharedKinds'},
          SharedKindsItem={Type=5,Variant=100,SubType=-1,IconID='SharedKinds'},
        }
        icons={'Coin','Item','CustomItem','DadNote','EmptyItem','Ladder','Flag','Bed','MomChest',
               'BombChest','Shared','SharedGrid','SharedKinds','Unknown'}
        function room(extra)
          local r={ItemIcons={table.unpack(icons)},Descriptor={},Visited=true,
                   DisplayFlags=5,PermanentIcons={'Treasure'},VisitedIcons={'Mirror'}}
          for k,v in pairs(extra or {}) do r[k]=v end
          return r
        end
        normal=room(); otherDimension=room(); noUpdate=room{NoUpdate=true}
        custom=room();custom.Descriptor=nil
        MinimapAPI={PickupList=defs,GridEntityList={{IconID='Ladder'},{IconID='SharedGrid'}},
                    Levels={[0]={normal,noUpdate,custom},[2]={otherDimension}}}
        originalIcons=normal.ItemIcons
        rewind={ItemIcons={table.unpack(icons)}}
        otherMod={GetData={MinimapAPIPickupID='Coin',anything=3}}
      end
      function eq(a,b)
        assert(table.concat(a,',')==table.concat(b,','),table.concat(a,','))
      end
      function intact()
        assert(normal.ItemIcons==originalIcons,'changed icon table identity')
        assert(normal.Visited and normal.DisplayFlags==5)
        eq(normal.PermanentIcons,{'Treasure'});eq(normal.VisitedIcons,{'Mirror'})
        eq(noUpdate.ItemIcons,icons);eq(custom.ItemIcons,icons);eq(rewind.ItemIcons,icons)
        assert(otherMod.GetData.MinimapAPIPickupID=='Coin' and otherMod.GetData.anything==3)
      end
      setup()
    )lua");
    const int top=lua_gettop(L);
    auto Note=[&](MinimapPickupReroll kind){
        const unsigned calls=allocator.calls;allocator.fail=true;
        NoteMinimapPickupReroll(kind);
        assert(allocator.calls==calls);allocator.fail=false;
        assert(HasPendingMinimapPickupReroll());
    };
    Note(MinimapPickupReroll::Pickups);
    assert(!FlushMinimapPickupCache(nullptr)&&HasPendingMinimapPickupReroll());
    assert(FlushMinimapPickupCache(L)&&!HasPendingMinimapPickupReroll());
    assert(lua_gettop(L)==top);
    Run(L,R"lua(
      expected={'Item','CustomItem','DadNote','EmptyItem','Ladder','Flag','Bed','MomChest',
                'BombChest','Shared','SharedGrid','SharedKinds','Unknown'}
      eq(normal.ItemIcons,expected);eq(otherDimension.ItemIcons,expected);intact()
      setup()
    )lua");
    Note(MinimapPickupReroll::Collectibles);
    assert(FlushMinimapPickupCache(L));
    Run(L,R"lua(
      expected={'Coin','DadNote','EmptyItem','Ladder','Flag','Bed','MomChest',
                'BombChest','Shared','SharedGrid','SharedKinds','Unknown'}
      eq(normal.ItemIcons,expected);eq(otherDimension.ItemIcons,expected);intact()
      setup()
    )lua");
    Note(MinimapPickupReroll::Pickups);Note(MinimapPickupReroll::Collectibles);
    assert(FlushMinimapPickupCache(L));
    Run(L,R"lua(
      expected={'DadNote','EmptyItem','Ladder','Flag','Bed','MomChest','BombChest',
                'Shared','SharedGrid','Unknown'}
      eq(normal.ItemIcons,expected);eq(otherDimension.ItemIcons,expected);intact()
      normal.ItemIcons={'Coin'}
    )lua");
    const unsigned idleCalls=allocator.calls;allocator.fail=true;
    assert(FlushMinimapPickupCache(L)); // consumed: no Lua work, even without allocation
    assert(allocator.calls==idleCalls);allocator.fail=false;
    Run(L,"eq(normal.ItemIcons,{'Coin'});setup()");
    Note(MinimapPickupReroll::Pickups);
    allocator.fail=true;
    assert(!FlushMinimapPickupCache(L)&&HasPendingMinimapPickupReroll());
    assert(lua_gettop(L)==top);
    allocator.fail=false;
    Run(L,"eq(normal.ItemIcons,icons)");
    assert(FlushMinimapPickupCache(L)&&!HasPendingMinimapPickupReroll());
    Run(L,"assert(normal.ItemIcons[1]=='Item');setup()");
    // Raw accesses must neither invoke mod-defined metamethods nor error on malformed data.
    Run(L,R"lua(
      local mt={__index=function() error('unexpected __index') end,
                __newindex=function() error('unexpected __newindex') end}
      setmetatable(MinimapAPI,mt);setmetatable(normal,mt)
      MinimapAPI.Levels[9]={false,{Descriptor={},ItemIcons=false}}
      MinimapAPI.PickupList.bad=false
    )lua");
    Note(MinimapPickupReroll::Pickups);assert(FlushMinimapPickupCache(L));
    Run(L,"MinimapAPI=nil");
    Note(MinimapPickupReroll::Collectibles);assert(FlushMinimapPickupCache(L));
    assert(!HasPendingMinimapPickupReroll());
    Note(MinimapPickupReroll::Pickups);ResetMinimapPickupCache();
    assert(!HasPendingMinimapPickupReroll());
    lua_close(L);
}
'''


class MinimapPickupCacheTests(unittest.TestCase):
    def test_level_rerolls_invalidate_affected_icons_without_changing_map_state(self):
        self.assertTrue(HELPER.is_file(), 'level rerolls leave MiniMAPI pickup snapshots stale')
        BUILD.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='host-', dir=BUILD) as directory:
            work = Path(directory)
            driver = work / 'driver.cpp'
            driver.write_text(DRIVER)
            objects = lua_harness_objects(SOURCE, work)
            binary = work / 'driver'
            result = subprocess.run([
                'clang++', '-std=c++23', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'runtime/src'),
                '-I', str(SOURCE / LUA_SOURCE_RELATIVE),
                str(driver), str(HELPER), *map(str, objects), '-o', str(binary)
            ], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
