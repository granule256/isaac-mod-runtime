"""内部指令读数：按游戏基址解码，缺失/原BL绝不冒称已装。"""
import sys,unittest,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class InternalReadoutTests(unittest.TestCase):
 def test_branch_and_both_veneer_forms(self):
  spec=importlib.util.spec_from_file_location('internal_reader',ROOT/'tools/read_device_state_via_gdb.py')
  tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
  base=0x7000000000
  for name,(site,veneer,size) in tool.INTERNAL_HOOK_SITES.items():
   word=0x14000000|(((veneer-site)//4)&0x3ffffff)
   self.assertEqual(tool.decode_internal_branch(word,base+site),base+veneer)
   self.assertIsNone(tool.decode_internal_branch(word|0x80000000,base+site))
  self.assertIsNone(tool.decode_internal_veneer(None,base,8))
  self.assertIsNone(tool.decode_internal_veneer([0],base,8))
  self.assertEqual(tool.decode_internal_veneer([0xd61f020058000050,0x7123400000],base,16),0x7123400000)
  # ADRP x16,+0x123000 / BR x16；base+8应向下取页地址。
  pages=0x123;w=0x90000010|((pages&3)<<29)|((pages>>2)<<5)
  self.assertEqual(tool.decode_internal_veneer([0xd61f020000000000|w],base+8,8),base+0x123000)
  pages=(-0x123)&0x1fffff;w=0x90000010|((pages&3)<<29)|((pages>>2)<<5)
  self.assertEqual(tool.decode_internal_veneer([0xd61f020000000000|w],base+8,8),base-0x123000)
  self.assertEqual(tool.HOOK_NAMES[tool.HOOK_NAMES.index('ItemPoolTrinketFirstRandom'):tool.HOOK_NAMES.index('ConsoleUnknownCompare')+1],['ItemPoolTrinketFirstRandom','ItemPoolTrinketSelected','RoomClearAward','EntityRemovePointers','EntityDestructorRemove','LevelCurseFirstRandom','LevelCurseEvaluation','PickupSelection','PickupSelectionSpecial','ItemPoolGetCard','ModManagerUnload','ConsoleUnknownLength','ConsoleUnknownCompare'])

 def test_literal_external_slot_requires_matching_address_and_pointer(self):
  spec=importlib.util.spec_from_file_location('literal_reader',ROOT/'tools/read_device_state_via_gdb.py')
  tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
  base=0x700068cdb8;slot=0x700068cd68;target=0x900000000
  word=0xd61f020000000000 | 0x58000010 | (((slot-base)//4 & 0x7ffff)<<5)
  self.assertIsNone(tool.decode_internal_veneer([word],base,8))
  self.assertEqual(tool.decode_internal_veneer([word],base,8,slot,target),target)
  self.assertIsNone(tool.decode_internal_veneer([word],base,8,slot+8,target))
  self.assertIsNone(tool.decode_internal_veneer([word],base,8,slot,0))

 def test_entity_remove_pointer_sites_cover_production_plan(self):
  import re
  spec=importlib.util.spec_from_file_location('pointer_reader',ROOT/'tools/read_device_state_via_gdb.py')
  tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
  header=(ROOT/'runtime/source/entity_remove_slots.hpp').read_text().split('kEntityRemovePointerOffsets={',1)[1].split('};',1)[0]
  self.assertEqual(tool.ENTITY_REMOVE_POINTER_SITES,tuple(int(x,16) for x in re.findall(r'0x[0-9A-Fa-f]+',header)))
  self.assertEqual(tool.SYM_ELF_NAMES['entity_remove_pointer_callback'],'IsaacModRuntime_EntityRemovePointerIntercept')
  self.assertIn('entity_remove_pointer_callback',tool.SYM_ONLY)
