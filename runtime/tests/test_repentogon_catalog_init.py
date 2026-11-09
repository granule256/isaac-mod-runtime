"""Batch descriptors and the default directory must use constant initialization."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class CatalogInitializationTests(unittest.TestCase):
 def test_default_catalog_has_no_dynamic_static_guard(self):
  with tempfile.TemporaryDirectory() as folder:
   obj=Path(folder)/'catalog.o'
   subprocess.run(['c++','-std=c++20','-O2','-I',str(ROOT/'src'),'-I',str(ROOT/'source'),
    '-I',str(ROOT/'source/third_party/lua-5.3.3/src'),'-c',
    str(ROOT/'src/interfaces/lua/repentogon_environment.cpp'),'-o',str(obj)],check=True)
   result=subprocess.run(['nm','-u',str(obj)],capture_output=True,text=True,check=True)
   self.assertNotIn('__cxa_guard_',result.stdout)
