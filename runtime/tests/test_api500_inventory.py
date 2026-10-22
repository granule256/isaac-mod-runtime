"""第五批方法须进入真实绑定清单，字段独立计数并与前四批去重。"""
import importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class Api500Inventory(unittest.TestCase):
 def test_public_methods_and_independent_field_ledger(self):
  spec=importlib.util.spec_from_file_location('api500_inventory_tool',ROOT/'tools/build_lua_api_inventory.py');tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
  runtime=tool.load_runtime_implemented();index={x['owner']+':'+x['name']:x for x in runtime['entries']}
  selected=json.loads((ROOT/'dist/apis500-20261016/selected-100.json').read_text())
  fields=json.loads((ROOT/'tools/api500_field_evidence.json').read_text())['rows']
  self.assertEqual(len(selected),100);self.assertEqual(len({x['key']for x in selected}),100)
  self.assertEqual(len(fields),98);self.assertEqual({x['key']for x in fields},{x['key']for x in selected if x['kind']=='field'})
  self.assertEqual(sum(x['kind']=='method'for x in selected),2)
  previous=[]
  for n,date in [(100,'20261014'),(200,'20261014'),(300,'20261014'),(400,'20261016')]:previous+=json.loads((ROOT/f'dist/apis{n}-{date}/selected-100.json').read_text())
  self.assertFalse({x['key']for x in previous}&{x['key']for x in selected})
  for x in selected:
   if x['kind']=='method':
    self.assertEqual(index[x['key']]['id'].lower(),x['id'].lower());self.assertNotIn(x['key'],runtime['entries_without_handler'])
