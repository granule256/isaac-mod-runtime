"""生产回调已改写FireTear入口时，字段布局验证仍须使用未改写的语义指纹。"""
import re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_api400_production import MAIN as PRODUCTION_MAIN
from .test_support import build_lua_harness
MAIN=PRODUCTION_MAIN.replace('#include <cassert>','#include <cassert>\n#include "relay/entry_relay.hpp"')
MAIN=MAIN.replace(' Api400EntitiesNativeTestBindings bindings{};',' relay::BuildEntryPatch(g_ModuleBytes.data()+kEntityPlayerFireTearOffset,g_EngineBase+0x80000);\n Api400EntitiesNativeTestBindings bindings{};')
class HookedLayout(unittest.TestCase):
 def test_actual_public_methods_after_entry_relay_install(self):
  prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')].replace('kEntityBlockSize = 0xD00','kEntityBlockSize = 0x3000')
  prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
  with tempfile.TemporaryDirectory(prefix='api400-hooked-layout-')as d:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+MAIN)
   result=subprocess.run([str(binary),'normal'],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
