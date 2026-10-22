"""实体继承写入口必须到达真实内存，NPC专属与玩家专属字段不能串到兄弟对象。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from .test_support import build_lua_harness
from .test_lua_batch285_receivers import HARNESS, SOURCE

SCRIPT = r'''
local p = Isaac.GetPlayer(0)
local raw = p.Parent
local typed = raw:ToNPC() or raw:ToPickup() or raw:ToPlayer()
local function writes(e)
  e.Position = Vector(11.5, 22.25)
  e.Velocity = Vector(-3.5, 4.25)
  e.HitPoints = 17.5
  e.MaxHitPoints = 30.25
  assert(e.Position.X == 11.5 and e.Velocity.Y == 4.25)
  assert(e.HitPoints == 17.5 and e.MaxHitPoints == 30.25)
  e.Size = 12.5
  e.Friction = 0.75
  e.Visible = false
  e.Variant = 7
  e.SubType = 8
  e.SpawnerType = 9
  e.SpawnerVariant = 10
  assert(e.Size == 12.5 and e.Friction == 0.75 and e.Visible == false)
  assert(e.Variant == 7 and e.SubType == 8 and e.SpawnerType == 9 and e.SpawnerVariant == 10)
  assert(not pcall(function() e.Type = 100 end))
  assert(not pcall(function() e.NotAField = 100 end))
end
writes(raw)
writes(typed)
if typed:ToNPC() then
  typed.Scale = 1.25
  assert(typed.Scale == 1.25)
  for _, name in ipairs({'Damage','ControlsEnabled','CanFly'}) do
    assert(not pcall(function() typed[name] = 1 end), name .. ' must remain player-only')
  end
elseif typed:ToPickup() then
  assert(not pcall(function() typed.Scale = 1 end))
end
p.CanFly = true
assert(p.CanFly == true)
print('ENTITY_WRITE_VIEWS_OK')
'''

class EntityWriteViewsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='isaac-write-views-')
        text = HARNESS
        a = text.index('    const char* script = nullptr;')
        b = text.index('    const auto result = LuaRuntime::InitializeFromBuffer', a)
        text = text[:a] + '    const char* script = R"lua(' + SCRIPT + ')lua";\n' + text[b:]
        text = text.replace('    return 0;\n}\n', r'''
    float hp = 0, size = 0;
    std::memcpy(&hp, g_TargetBytes.data() + kEntityHitPointsOffset, sizeof(hp));
    std::memcpy(&size, g_TargetBytes.data() + kEntitySizeOffset, sizeof(size));
    if (hp != 17.5f || size != 12.5f) return 93;
    return 0;
}
''', 1)
        cls.binary = build_lua_harness(source_root=SOURCE, workdir=Path(cls.tmp.name), harness_source=text)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def test_writes_through_base_and_derived_views_reach_engine(self):
        for scenario in ('npc', 'pickup', 'player'):
            with self.subTest(scenario=scenario):
                r = subprocess.run([str(self.binary), scenario], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
                self.assertIn('ENTITY_WRITE_VIEWS_OK', r.stdout)

if __name__ == '__main__': unittest.main()
