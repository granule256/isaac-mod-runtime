"""Dependency rules for PC core, native lifecycle and optional policies."""
import re,unittest
from pathlib import Path
from .test_support import layered_lua_runtime_sources
ROOT=Path(__file__).resolve().parents[2]

def code(path):
 text=path.read_text()
 return re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)

class ArchitectureBoundaryTests(unittest.TestCase):
 def test_pc_core_and_native_world_do_not_know_mod_private_tables(self):
  paths=[ROOT/'runtime/source/lua_runtime.cpp',ROOT/'runtime/src/interfaces/lua/api200_game.cpp',ROOT/'runtime/src/interfaces/lua/compatibility_adapter_runtime.cpp']
  paths+=list((ROOT/'runtime/src/domain/world').glob('*.hpp'))
  paths+=list((ROOT/'runtime/src/infrastructure/native').glob('*.*'))
  for path in paths:
   with self.subTest(path=path.name):
    text=code(path)
    self.assertNotRegex(text,r'MinimapAPI|ItemIcons|PickupList|GridEntityList|compatibility/builtin_adapters')
 def test_core_can_link_without_builtin_catalog_or_policy(self):
  paths=layered_lua_runtime_sources(ROOT/'runtime/source')
  self.assertFalse(any('/compatibility/'in str(p)for p in paths))
  self.assertFalse((ROOT/'runtime/src/interfaces/lua/minimap_pickup_cache.cpp').exists())
 def test_init_sources_are_not_synthesized_by_scene_scan_or_fire(self):
  text=code(ROOT/'runtime/source/lua_runtime.cpp')
  for begin,end,forbidden in [('void DispatchTearEntityEvents','void DispatchProjectileEntityEvents','kCallbackPostTearInit'),('void DispatchEffectEntityEvents','void DispatchBombEntityEvents','kCallbackPostEffectInit'),('void DispatchPostFireTear','// sentinel','DispatchNativeTearInit')]:
   start=text.index(begin)
   stop=text.find(end,start+len(begin))
   if stop<0:stop=text.find('\n}',start)+2
   self.assertNotIn(forbidden,text[start:stop])
  self.assertNotRegex(text,r'MarkEntity(Tear|Effect)Initialized')
