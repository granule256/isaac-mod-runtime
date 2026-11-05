"""Optional MiniMAPI Lua policy; the PC runtime does not own its private cache."""
import subprocess,tempfile,unittest
from pathlib import Path
from .test_support import LUA_SOURCE_RELATIVE,lua_harness_objects
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'runtime/source'
DRIVER=r'''
#include "interfaces/lua/compatibility_adapter_runtime.hpp"
#include "infrastructure/native/world_content_mutations.hpp"
#if __has_include("compatibility/minimapapi_pickups_adapter.hpp")
#include "compatibility/minimapapi_pickups_adapter.hpp"
#else
namespace isaac::runtime::compatibility {inline constexpr char kMinimapApiPickupAdapter[]="return function() end";}
#endif
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
#if __has_include("compatibility/builtin_adapters.hpp")
#include "compatibility/builtin_adapters.hpp"
#else
namespace isaac::runtime::compatibility {inline void InstallBuiltinCompatibilityAdapters(lua_State*)noexcept{}}
#endif
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
using namespace isaac::runtime;
static void Run(lua_State*L,const char*s){if(luaL_dostring(L,s)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));std::abort();}}
int main(){
 auto*L=luaL_newstate();assert(L);luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_TABLIBNAME,luaopen_table,1);lua_pop(L,1);BeginWorldContentRun();
 const auto*source=compatibility::kMinimapApiPickupAdapter;
 assert(luaL_loadbuffer(L,source,std::strlen(source),"@compatibility/minimapapi_pickups.lua")==LUA_OK);
 assert(lua_pcall(L,0,1,0)==LUA_OK);CompatibilityAdapterId id{};
 assert(RegisterCompatibilityAdapter(L,"minimapapi.pickups",-1,&id));lua_pop(L,1);
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
        MinimapAPI={MajorVersion=2,MinorVersion=59,PickupList=defs,GridEntityList={{IconID='Ladder'},{IconID='SharedGrid'}},
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
 RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);PumpCompatibilityAdapters(L);
 Run(L,R"lua(
 eq(normal.ItemIcons,{'Item','CustomItem','DadNote','EmptyItem','Ladder','Flag','Bed','MomChest','BombChest','Shared','SharedGrid','SharedKinds','Unknown'});intact();setup()
 )lua");
 RecordWorldContentMutation(WorldContentMutation::CollectiblesRerolled);PumpCompatibilityAdapters(L);
 Run(L,R"lua(
 eq(normal.ItemIcons,{'Coin','DadNote','EmptyItem','Ladder','Flag','Bed','MomChest','BombChest','Shared','SharedGrid','SharedKinds','Unknown'});intact();setup()
 )lua");
 RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);RecordWorldContentMutation(WorldContentMutation::CollectiblesRerolled);PumpCompatibilityAdapters(L);
 Run(L,R"lua(eq(normal.ItemIcons,{'DadNote','EmptyItem','Ladder','Flag','Bed','MomChest','BombChest','Shared','SharedGrid','Unknown'});intact();setup())lua");
 Run(L,"MinimapAPI.MinorVersion=63");RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);PumpCompatibilityAdapters(L);
 Run(L,"eq(normal.ItemIcons,icons)");auto d=GetCompatibilityAdapterDiagnostics(id);assert(d.lastResult==CompatibilityAdapterResult::NotApplicable&&d.reason[0]);
 Run(L,"MinimapAPI.MinorVersion=62");RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);PumpCompatibilityAdapters(L);
 Run(L,"assert(normal.ItemIcons[1]=='Item');setup()");
 // Policy uses captured primitive raw access, even if a mod adds metatables.
 Run(L,R"lua(
 local m={__index=function()error('metamethod')end,__newindex=function()error('metamethod')end,__pairs=function()error('pairs')end}
 setmetatable(MinimapAPI,m);setmetatable(normal,m);setmetatable(MinimapAPI.Levels,m)
 )lua");
 RecordWorldContentMutation(WorldContentMutation::PickupsRerolled);PumpCompatibilityAdapters(L);
 Run(L,"assert(normal.ItemIcons[1]=='Item');MinimapAPI=nil");
 RecordWorldContentMutation(WorldContentMutation::CollectiblesRerolled);PumpCompatibilityAdapters(L);
 d=GetCompatibilityAdapterDiagnostics(id);assert(d.failures==0&&d.lastResult==CompatibilityAdapterResult::NotApplicable);
 assert(!HasPendingCompatibilityAdapters());ResetCompatibilityAdapters(L);lua_close(L);
 L=luaL_newstate();assert(L);luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);luaL_requiref(L,LUA_TABLIBNAME,luaopen_table,1);lua_pop(L,1);
 compatibility::InstallBuiltinCompatibilityAdapters(L);
 assert(std::strcmp(GetCompatibilityAdapterDiagnostics(0).name,"minimapapi.pickups")==0);
 Run(L,"pcStillWorks=true;assert(pcStillWorks)");
 ResetCompatibilityAdapters(L);lua_close(L);
}
'''
class MinimapPickupAdapterTests(unittest.TestCase):
 def test_explicit_versioned_policy_preserves_unaffected_mod_state(self):
  with tempfile.TemporaryDirectory(prefix='minimap-adapter-')as directory:
   p=Path(directory);f=p/'main.cpp';f.write_text(DRIVER);objects=lua_harness_objects(SOURCE,p);out=p/'test'
   cpp=[ROOT/'runtime/src/interfaces/lua/compatibility_adapter_runtime.cpp',ROOT/'runtime/src/infrastructure/native/world_content_mutations.cpp']
   catalog=ROOT/'runtime/src/compatibility/builtin_adapters.cpp'
   if catalog.exists():cpp.append(catalog)
   build=subprocess.run(['clang++','-std=c++23','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime/src'),'-I',str(SOURCE/LUA_SOURCE_RELATIVE),str(f),*map(str,cpp),*map(str,objects),'-o',str(out)],capture_output=True,text=True)
   self.assertEqual(build.returncode,0,build.stdout+build.stderr)
   run=subprocess.run([str(out)],capture_output=True,text=True);self.assertEqual(run.returncode,0,run.stdout+run.stderr)
