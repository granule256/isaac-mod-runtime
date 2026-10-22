"""所有内部近桩登记；不让后加起点裁掉原已声明空间以掩盖覆盖。"""
import unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import verify_cave_allocation as v

class VeneerAllocationTests(unittest.TestCase):
 def test_every_internal_veneer_has_exact_reserved_bytes(self):
  rows=v.merge_relays(v.collect_views(v.PATCH_SOURCE,v.EXTRA_SOURCES,v.RUNTIME_CONSTANTS))
  spans=v.assign_ranges(rows)
  for name,offset,size in [('RoomSpawnInternal',0x68cfd0,16),('TrinketFirst',0x68cfe0,16),('TrinketSelected',0x68cff0,16),('ClearAward',0x68cdb8,8)]:
   key='runtime:k'+name+'Veneer'
   self.assertIn(key,spans)
   self.assertEqual(spans[key],[(offset,offset+size,'cave')])
 def test_inner_allocation_is_rejected_without_truncating_original(self):
  rows={}
  for name,off,size in [('runtime:kFirstVeneer',0x68cfe0,16),('runtime:kBadVeneer',0x68cfe4,8)]:
   row=v.Relay(name);row.views.append(v.RelayView(name,caves=[off],cave_length=size));rows[name]=row
  problems,stale=v.evaluate(rows,groups=())
  self.assertTrue(problems,'后加起点不得裁掉原16B近桩，使真实覆盖被漏掉')
  self.assertEqual(stale,[])
 def test_clear_award_does_not_overlap_any_ips_record_or_old_slot(self):
  import build_patches as b
  begin,end=0x68cdb8,0x68cdc0
  for name,records in vars(b).items():
   if not name.endswith('_RECORDS') or not isinstance(records,(tuple,list)):continue
   for row in records:
    if isinstance(row,tuple) and len(row)==2 and isinstance(row[0],int) and isinstance(row[1],bytes):
     start,data=row;self.assertFalse(start<end and begin<start+len(data),name)
  rows=v.merge_relays(v.collect_views(v.PATCH_SOURCE,v.EXTRA_SOURCES,v.RUNTIME_CONSTANTS))
  for row in rows.values():
   slot=row.slot()
   if slot is not None:self.assertFalse(slot<end and begin<slot+8,row.name)
