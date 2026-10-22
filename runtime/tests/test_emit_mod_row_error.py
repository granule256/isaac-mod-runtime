"""菜单参考缺失必须返回原始诊断，不能因异常类型写错而再抛 NameError。"""
import contextlib
import io
import tempfile
import unittest
from unittest.mock import patch
from tools import emit_mod_row_art as tool

class ModRowErrorTests(unittest.TestCase):
 def test_missing_menu_reference_reports_art_error(self):
  with tempfile.TemporaryDirectory() as td, patch('sys.argv',['emit','--tree',td,'--languages','zh','--menu-row-layer','--dump-root',td]), patch.object(tool,'emit_menu_anm2',side_effect=tool.ArtError('missing PC reference')), contextlib.redirect_stderr(io.StringIO()) as out:
   self.assertEqual(tool.main(),1)
   self.assertIn('missing PC reference',out.getvalue())
if __name__=='__main__':unittest.main()
