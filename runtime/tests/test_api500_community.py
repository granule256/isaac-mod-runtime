"""逐字作者片段读取真实生产RoomConfigRoom，覆盖5个新字段。"""
import unittest
from pathlib import Path
from .test_api500_world import MAIN,run_world
EXCERPT=(Path(__file__).parents[2]/"dist/apis500-20261016/community/excerpt.lua").read_text()
class AuthorConsumer(unittest.TestCase):
 def test_stageapi_room_metadata_excerpt(self):
  snippet="do local data=RoomConfig;local layout={}\n"+EXCERPT+"\nassert(layout.Name=='Test' and layout.Variant==0xf1234567 and layout.SubType==0xf1234567 and layout.Difficulty==19 and layout.Weight==3.25);end;\n"
  main=MAIN
  marker='assert(Grid.State==19,'
  assert marker in main
  main=main.replace(marker,snippet+marker,1)
  r=run_world(main=main);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
