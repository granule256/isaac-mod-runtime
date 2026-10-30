"""组合真实生产IPS及运行时近桩，禁止用填充长度或白名单掩盖有效代码重叠。"""
import unittest
from pathlib import Path
from tools import build_patches as p,cold_static_callbacks as c
from runtime.game_patches.catalog import PATCHES as GAME_PATCHES
ROOT=Path(__file__).resolve().parents[2]
class CallbackPatchCompositionTests(unittest.TestCase):
 def records(self,blob):
  i=5;out=[]
  while blob[i:i+3]!=b'EOF':
   off=int.from_bytes(blob[i:i+3],'big');n=int.from_bytes(blob[i+3:i+5],'big');i+=5;self.assertGreater(n,0);out.append((off,blob[i:i+n]));i+=n
  return out
 def test_all_production_records_and_runtime_veneers_are_disjoint(self):
  n=next(Path('/Users/kelinls/code/github/isaac mod').glob('The Binding of Isaac_ Afterbirth+*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  ranges=[('lifecycle',a,len(b))for a,b in self.records(p.build_game_start_lifecycle_relay_patch(n))]
  ranges += [(patch.id,a,len(b))for patch in GAME_PATCHES for a,b in patch.records]
  ranges += [('cold',a,len(b))for a,b in self.records(c.build_static_callback_patch(n))]
  import re
  constants=(ROOT/'runtime/source/runtime_constants.hpp').read_text()
  for name,size in [('kEntityDestructorVeneerOffset',8),('kClearAwardVeneerOffset',8),('kRoomSpawnInternalVeneerOffset',16),('kTrinketFirstVeneerOffset',16),('kTrinketSelectedVeneerOffset',16),('kLevelCurseFirstVeneerOffset',8)]:
   start=int(re.search(name+r'\s*=\s*(0x[0-9A-Fa-f]+)',constants)[1],16);ranges.append((name,start,size))
  for i,(name,a,size)in enumerate(ranges):
   for name2,b,size2 in ranges[i+1:]:
    self.assertFalse(a<b+size2 and b<a+size,f'{name}@{a:x}+{size}覆盖{name2}@{b:x}+{size2}')
 def test_runtime_and_ips_locations_match(self):
  import re
  text=(ROOT/'runtime/source/runtime_constants.hpp').read_text()
  for source,gate,word in c.SITES:
   name='kLevelCurseStaticRelayCodeOffset'if source==0x3e0c88 else 'kPickupSelectionStaticRelayCodeOffset'if source==0x269d50 else 'kPickupSelectionSpecialRelayCodeOffset'
   self.assertEqual(int(re.search(name+r'\s*=\s*(0x[0-9A-Fa-f]+)',text)[1],16),gate)

 def test_allocation_checker_keeps_declared_code_length(self):
  from tools.verify_cave_allocation import Relay,RelayView,evaluate
  relays={'A':Relay('A',[RelayView('A',[0x1000],cave_length=80)]),'B':Relay('B',[RelayView('B',[0x1020],cave_length=32)])}
  self.assertTrue(evaluate(relays,groups=())[0],'80字节代码不能因后一个中继从32字节处开始而被截短成32字节')
