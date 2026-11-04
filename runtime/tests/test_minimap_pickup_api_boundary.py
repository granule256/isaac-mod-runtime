"""Direct Lua Game rerolls finish native work before recording cache invalidation."""
import subprocess,tempfile,unittest,re
from pathlib import Path
from . import test_api200_game as api
from . import test_support
ROOT=Path(__file__).resolve().parents[2]
CHECKS=r'''
 auto run=[&](const char* code){if(luaL_dostring(L,code)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));std::abort();}};
 ResetMinimapPickupCache();checkRerollOrder=true;
 run(R"lua(
 g=Game();normal={Descriptor={},ItemIcons={'Coin','Item'}}
 MinimapAPI={PickupList={{Type=5,Variant=20,IconID='Coin'},{Type=5,Variant=100,SubType=-1,IconID='Item'}},GridEntityList={},Levels={[0]={normal}}}
 g:RerollLevelCollectibles()
 assert(#normal.ItemIcons==2,'wrapper entered Lua cache mutation')
 )lua");
 if(calls[15]!=1||!HasPendingMinimapPickupReroll()){std::puts("FAIL direct collectibles wrapper omitted post-native notification");return 30;}
 assert(FlushMinimapPickupCache(L));run("assert(#normal.ItemIcons==1 and normal.ItemIcons[1]=='Coin')");
 run("normal.ItemIcons={'Coin','Item'};g:RerollLevelPickups('4294967295');assert(#normal.ItemIcons==2)");
 if(calls[16]!=1||!HasPendingMinimapPickupReroll()){std::puts("FAIL direct pickups wrapper omitted post-native notification");return 31;}
 assert(FlushMinimapPickupCache(L));run("assert(#normal.ItemIcons==1 and normal.ItemIcons[1]=='Item')");
 run("assert(not pcall(function()g:RerollLevelPickups(nil)end))");
 assert(!HasPendingMinimapPickupReroll()&&calls[16]==1);
 lua_close(L);std::puts("PASS direct Lua rerolls: native first, pending only, original arguments and guards retained");return 0;
'''
class MinimapPickupApiBoundaryTests(unittest.TestCase):
 def test_direct_wrappers_record_the_matching_kind_after_native_return(self):
  main=api.MAIN.replace('#include "interfaces/lua/api200_game.hpp"','#include "interfaces/lua/api200_game.hpp"\n#include "interfaces/lua/minimap_pickup_cache.hpp"\nstatic bool checkRerollOrder=false;')
  main=main.replace('Touch(15,p);','if(checkRerollOrder)assert(!HasPendingMinimapPickupReroll());Touch(15,p);')
  main=main.replace('Touch(16,p);','if(checkRerollOrder)assert(!HasPendingMinimapPickupReroll());Touch(16,p);')
  main=main.replace(' const char*script=R"lua(',CHECKS+'\n const char*script=R"lua(',1)
  source=api.fixture.HARNESS.split('int main(',1)[0]+main
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  helper=ROOT/'runtime/src/interfaces/lua/minimap_pickup_cache.cpp'
  with tempfile.TemporaryDirectory(prefix='isaac-reroll-api-')as tmp:
   extra=()if helper in test_support.layered_lua_runtime_sources(api.fixture.SOURCE)else(helper,)
   binary=test_support.build_lua_harness(source_root=api.fixture.SOURCE,workdir=Path(tmp),harness_source=source,extra_sources=extra)
   result=subprocess.run([str(binary),'reroll_pending'],capture_output=True,text=True)
   print(result.stdout+result.stderr,flush=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
