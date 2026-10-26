"""Lua Sprite使用ANM2；入口按原始动态符号独立验证，避免同名Sprite类混用。"""
import re,unittest
from pathlib import Path
from tools.nro_symbols import parse_dynamic_symbols
ROOT=Path(__file__).resolve().parents[2]
class SpriteNativeClassTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.nro=next(ROOT.glob('The Binding*/Program #0/1/.nro/Repentance.nro')).read_bytes()
  _,cls.symbols=parse_dynamic_symbols(cls.nro)
  cls.constants=(ROOT/'runtime/source/runtime_constants.hpp').read_text()
 def test_reset_entry_is_anm2_member(self):
  actual=int(re.search(r'kSpriteResetOffset\s*=\s*(0x[0-9a-fA-F]+)',self.constants).group(1),16)
  native=self.symbols['_ZN15IsaacRepentance4ANM25ResetEv'].file_offset
  self.assertEqual(actual,native,'Lua Sprite must call ANM2::Reset, not the distinct Sprite::Reset')
 def test_reset_guard_belongs_to_anm2_member(self):
  body=re.search(r'kSpriteResetExpectedBytes\s*=\s*\{([^}]+)\}',self.constants).group(1)
  actual=bytes(int(x,16)for x in re.findall(r'0x[0-9a-fA-F]+',body))
  native=self.symbols['_ZN15IsaacRepentance4ANM25ResetEv'].file_offset
  self.assertEqual(actual,self.nro[native:native+16])
class SpriteResetMissingBindingTests(unittest.TestCase):
 def test_missing_reset_binding_is_reported(self):
  import tempfile,subprocess
  from .test_lua_batch309_get_filename import HARNESS,SOURCE
  from .test_support import build_lua_harness
  source=HARNESS.replace("const char* kRead =", "const char* unusedRead =",1)
  needle='    static const char* kArgs ='
  script="local s=Sprite();local ok,e=pcall(function()s:Reset()end);assert(not ok and tostring(e):find('native binding'),'missing Reset binding must not succeed');print('MISSING_RESET_OK')"
  source=source.replace(needle,'    static const char* kRead = "'+script+'";\n    static_cast<void>(unusedRead);\n'+needle,1)
  with tempfile.TemporaryDirectory(prefix='reset-binding-')as tmp:
   binary=build_lua_harness(source_root=SOURCE,workdir=Path(tmp),harness_source=source)
   r=subprocess.run([str(binary),'short'],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('MISSING_RESET_OK',r.stdout)

if __name__=='__main__':unittest.main()
