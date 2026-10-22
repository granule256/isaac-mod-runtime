"""偏离台账解析必须遵守C++字符串与注释边界，不能把历史注释当现存欠账。"""
import tempfile,unittest
from pathlib import Path
from tools.api_deviation_ledger import load_entries
class ApiDeviationParserTests(unittest.TestCase):
 def parse(self,body):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'rows.cpp';p.write_text(body);return load_entries(p)
 def test_comment_entries_are_not_current_entries(self):
  rows=self.parse('''// {0xDEAD, ApiDeviationKind::Placeholder, "已退役"},
/* {0xBEEF, ApiDeviationKind::Placeholder, "旧记录"}, */
{0x1, ApiDeviationKind::Partial, "PC 契约：真的"},''')
  self.assertEqual([(r.identifier,r.text) for r in rows],[(1,'PC 契约：真的')])
 def test_comments_between_literals_do_not_leak_words(self):
  rows=self.parse('''{0x1, ApiDeviationKind::Partial,
  // "恒返回假值能还" // 孤立 /* 散文
  "PC 契约：真的" /* "假的" */
  "偏离后果：明确"},''')
  self.assertEqual(rows[0].text,'PC 契约：真的偏离后果：明确')
 def test_braces_quotes_urls_and_adjacent_literals_remain_data(self):
  rows=self.parse(r'''{0x1, ApiDeviationKind::Partial,
  "PC 契约：https://example.test/a/*b*/" " }, 中括号不结束条目 "
  "引号\"中文\"与反斜杠\\"},
{0x2, ApiDeviationKind::Placeholder, "第二条"},''')
  self.assertEqual(len(rows),2)
  self.assertEqual(rows[0].text,'PC 契约：https://example.test/a/*b*/ }, 中括号不结束条目 引号"中文"与反斜杠\\')
  self.assertEqual(rows[1].text,'第二条')
 def test_escaped_backslash_n_is_not_a_newline(self):
  rows=self.parse(r'''{ 0x1, ApiDeviationKind::Partial, "行\n字面\\n"},''')
  self.assertEqual(rows[0].text,'行\n字面\\n')
if __name__=='__main__':unittest.main()
