"""冻结六组真实消费者与专门模组的加载/语法，避免交付旁路脚本。"""
import ast,hashlib,json,re,subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_entity_query as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
MOD=ROOT/'dist/apis300-20261014/api_restore_verify_300'
class Api300VerificationMod(unittest.TestCase):
 def test_six_consumers_match_executed_native_harnesses(self):
  manifest=json.loads((MOD/'manifest.json').read_text());self.assertEqual(len(manifest),6)
  counts={'player31':31,'game21':21,'room13':13,'world16':16,'native_seed11':11,'flags8':8}
  self.assertEqual(sum(counts[x['group']]for x in manifest),100)
  for row in manifest:
   tree=ast.parse((ROOT/row['source']).read_text());main=next(n.value.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id==row['variable']for t in n.targets))
   text=re.search(r'const char\s*\*\s*(?:script|s)\s*=\s*R"(\w+)\((.*?)\)\1";',main,re.S)[2].encode();stored=(ROOT/row['script']).read_bytes()
   self.assertEqual(stored,text,row['group']);self.assertEqual(hashlib.sha256(stored).hexdigest(),row['sha256'])
 def test_verification_mod_entry_loads_and_all_scripts_compile(self):
  prefix=fixture.HARNESS[:fixture.HARNESS.index('int main(')]
  prefix=re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',prefix,count=1)
  main='''
extern "C" {
#include <lauxlib.h>
}
int main(){static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);static_cast<void>(&PublishEntityList);CreateBlocks();FillEntities();PublishLists();PublishGame();const char*entry=R"ENTRY('''+(MOD/'main.lua').read_text()+''')ENTRY";if(LuaRuntime::InitializeFromBuffer(entry,std::strlen(entry),"@api300/main.lua")!=LuaRuntime::LuaInitResult::Success)return 1;
 auto*L=luaL_newstate();
'''
  for file in sorted((MOD/'scripts').glob('*.lua')):
   text=file.read_text();main+='const char*'+file.stem+'=R"SCRIPT('+text+')SCRIPT";if(luaL_loadbuffer(L,'+file.stem+',std::strlen('+file.stem+'),"@'+file.name+'"))return 2;lua_pop(L,1);\n'
  main+='lua_close(L);return 0;}\n'
  with tempfile.TemporaryDirectory(prefix='api300-mod-load-')as d:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(d),harness_source=prefix+main)
   result=subprocess.run([str(binary)],text=True,capture_output=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
