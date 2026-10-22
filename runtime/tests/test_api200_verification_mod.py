"""冻结三组真实消费者与专门模组的加载/语法，避免交付旁路脚本。"""
import ast,hashlib,json,re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MOD=ROOT/'dist/apis200-20261014/api_restore_verify_200'
class Api200VerificationMod(unittest.TestCase):
 def test_three_consumers_match_executed_native_harnesses(self):
  manifest=json.loads((MOD/'manifest.json').read_text());self.assertEqual(len(manifest),3)
  counts={'player34':34,'game18':18,'main48':48}
  self.assertEqual(sum(counts[x['group']]for x in manifest),100)
  for row in manifest:
   tree=ast.parse((ROOT/row['source']).read_text());main=next(n.value.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='MAIN'for t in n.targets))
   text=re.search(r'const char\s*\*\s*(?:script|s)\s*=\s*R"(\w+)\((.*?)\)\1";',main,re.S)[2].encode();stored=(ROOT/row['script']).read_bytes()
   self.assertEqual(stored,text,row['group']);self.assertEqual(hashlib.sha256(stored).hexdigest(),row['sha256'])
 def test_verification_mod_entry_loads_and_all_scripts_compile(self):
  prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
  prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
  main='''
extern "C" {
#include <lauxlib.h>
}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);static_cast<void>(&PublishEntityList);CreateBlocks();FillEntities();PublishLists();PublishGame();const char*entry=R"ENTRY('''+(MOD/'main.lua').read_text()+''')ENTRY";if(LuaRuntime::InitializeFromBuffer(entry,std::strlen(entry),"@api200/main.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto*L=luaL_newstate();
'''
  for file in sorted((MOD/'scripts').glob('*.lua')):
   text=file.read_text();main+='const char*'+file.stem+'=R"SCRIPT('+text+')SCRIPT";if(luaL_loadbuffer(L,'+file.stem+',std::strlen('+file.stem+'),"@'+file.name+'"))return 2;lua_pop(L,1);\n'
  main+='lua_close(L);return 0;}\n'
  with tempfile.TemporaryDirectory(prefix='api200-mod-load-')as d:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+main)
   result=subprocess.run([str(binary)],text=True,capture_output=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
