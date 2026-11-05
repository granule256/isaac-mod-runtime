"""Direct Lua Game rerolls share the native world mutation completion boundary."""
import subprocess,tempfile,unittest,re
from pathlib import Path
from . import test_api200_game as api
from . import test_support
ROOT=Path(__file__).resolve().parents[2]
CHECKS=r'''
 auto run=[&](const char* code){if(luaL_dostring(L,code)!=LUA_OK){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));std::abort();}};
 BeginWorldContentRun();cursor.snapshot=CaptureWorldContentSnapshot();checkRerollOrder=true;
 run("g=Game();g:RerollLevelCollectibles()");
 auto completed=CaptureWorldContentSnapshot();
 auto changes=ChangesSince(cursor,completed);
 assert(calls[15]==1&&changes.collectiblesChanged&&!changes.pickupsChanged);
 assert(completed.version==cursor.snapshot.version+1);cursor.snapshot=completed;
 run("g:RerollLevelPickups('4294967295')");
 completed=CaptureWorldContentSnapshot();changes=ChangesSince(cursor,completed);
 assert(calls[16]==1&&changes.pickupsChanged&&!changes.collectiblesChanged);
 assert(completed.version==cursor.snapshot.version+1);cursor.snapshot=completed;
 run("assert(not pcall(function()g:RerollLevelPickups(nil)end))");
 assert(!ChangesSince(cursor,CaptureWorldContentSnapshot()).Any()&&calls[16]==1);
 lua_close(L);std::puts("PASS direct Lua rerolls: native first, exactly one world event, original arguments and guards retained");return 0;
'''
class MinimapPickupApiBoundaryTests(unittest.TestCase):
 def test_direct_wrappers_record_the_matching_kind_after_native_return(self):
  main=api.MAIN.replace('#include "interfaces/lua/api200_game.hpp"','#include "interfaces/lua/api200_game.hpp"\n#include "infrastructure/native/world_content_mutations.hpp"\nstatic bool checkRerollOrder=false;\nstatic isaac::runtime::WorldContentCursor cursor{};')
  main=main.replace('Touch(15,p);','if(checkRerollOrder)assert(!ChangesSince(cursor,CaptureWorldContentSnapshot()).Any());Touch(15,p);')
  main=main.replace('Touch(16,p);','if(checkRerollOrder)assert(!ChangesSince(cursor,CaptureWorldContentSnapshot()).Any());Touch(16,p);')
  main=main.replace(' const char*script=R"lua(',CHECKS+'\n const char*script=R"lua(',1)
  source=api.fixture.HARNESS.split('int main(',1)[0]+main
  source=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
  helper=ROOT/'runtime/src/infrastructure/native/world_content_mutations.cpp'
  with tempfile.TemporaryDirectory(prefix='isaac-reroll-api-')as tmp:
   extra=()if helper in test_support.layered_lua_runtime_sources(api.fixture.SOURCE)else(helper,)
   binary=test_support.build_lua_harness(source_root=api.fixture.SOURCE,workdir=Path(tmp),harness_source=source,extra_sources=extra)
   result=subprocess.run([str(binary),'reroll_pending'],capture_output=True,text=True)
   print(result.stdout+result.stderr,flush=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
