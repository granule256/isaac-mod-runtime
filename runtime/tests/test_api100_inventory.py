"""清单必须与真实Catalog/绑定ID一致，不能把未维护的域误写成Global。"""
import importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class Api100Inventory(unittest.TestCase):
 def test_inventory_ids_match_all_100_real_binding_ids(self):
  spec=importlib.util.spec_from_file_location('api100_inventory',ROOT/'tools/build_lua_api_inventory.py');tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
  runtime=tool.load_runtime_implemented();entries=runtime['entries'];indexed={(x['owner'],x['name']):x for x in entries}
  for x in json.loads((ROOT/'dist/apis100-20261014/selected-100.json').read_text()):
   row=indexed[x['owner'],x['name']];self.assertEqual(row['id'].lower(),x['id'].lower(),x['key']);self.assertNotIn(x['key'],runtime['entries_without_handler'])
