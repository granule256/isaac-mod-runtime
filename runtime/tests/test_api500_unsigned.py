"""PC整数包装的零扩展/符号扩展边界。"""
import json,unittest
from pathlib import Path
from .test_api500_entities import MAIN as ENTITY_MAIN
from .test_api400_params import run_main
from .test_api500_world import MAIN as WORLD_MAIN,run_world
ROWS=json.loads((Path(__file__).parents[2]/"dist/apis500-20261016/entity-selected.json").read_text())
class UnsignedConsumer(unittest.TestCase):
 def test_npc_state_and_tear_index_high_bit(self):
  main=ENTITY_MAIN
  for owner,name,slot in [('EntityNPC','State','kEnemyA'),('EntityTear','TearIndex','kTearNear')]:
   i=next(i for i,x in enumerate(ROWS)if x['owner']==owner and x['name']==name);o=ROWS[i]['offset'];v=i+10
   main=main.replace(f'WriteAt<std::int32_t>(g_Entities[{slot}],{o},{v});',f'WriteAt<std::uint32_t>(g_Entities[{slot}],{o},0xf1234567U);')
   main=main.replace(f'{owner}.{name}=={v},',f'{owner}.{name}==4045620583,')
  r=run_main(main);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_grid_state_preserves_unsigned_wrapper(self):
  main=WORLD_MAIN.replace('auto expectedGrids=grids;', 'WriteAt<std::uint32_t>(grids[0],0x10,0xf1234567U);auto expectedGrids=grids;')
  main=main.replace('Grid.State==19,','Grid.State==4045620583,').replace('GridDesc.State==19,','GridDesc.State==-249346713,')
  main=main.replace('GridDesc.State==Grid.State','(GridDesc.State&0xffffffff)==Grid.State')
  r=run_world(main=main);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
