"""EID HideInBattle consumes PC room counters, not broad NPC type counts."""
import subprocess
import tempfile
import unittest
from pathlib import Path
try:
    from .test_support import build_lua_harness
    from .test_lua_entity_query import HARNESS as ENTITY_HARNESS, SOURCE
except ImportError:
    from test_support import build_lua_harness
    from test_lua_entity_query import HARNESS as ENTITY_HARNESS, SOURCE

# Reuse the real entity-container fixture; retain shopkeeper/fireplace-shaped NPCs.
PREFIX = ENTITY_HARNESS[:ENTITY_HARNESS.index("int main(int argc, char** argv) {")]
MAIN = r'''int main(int argc, char** argv) {
    static_cast<void>(kScriptTemplate);static_cast<void>(&HarnessHasCollectible);
    static_cast<void>(&BuildPrelude);static_cast<void>(&ExpectNumber);
    if(argc!=2)return 90;
    const std::string scene=argv[1];
    CreateBlocks();FillEntities();PublishLists();PublishGame();PublishEntityList(g_RoomBytes,true);
    LuaRuntime::SetEngineModuleBase(g_EngineBase);
    WriteAt<std::uint32_t>(g_Entities[kEnemyA],kEntityTypeOffset,17);
    WriteAt<std::uint32_t>(g_Entities[kSizeOnly],kEntityTypeOffset,33);
    WriteAt<std::uint32_t>(g_Entities[kNoQuery],kEntityTypeOffset,17);
    std::int32_t e1=0,e2=0,b1=0,b2=0;
    if(scene=="combat"){e1=2;e2=3;b1=1;b2=1;}
    else if(scene=="negative"){e1=-8;e2=3;b1=-3;b2=1;}
    else if(scene=="overflow"){e1=2147483647;e2=1;b1=-2147483647;b2=-2;}
    else if(scene!="shop")return 91;
    WriteAt<std::int32_t>(g_RoomBytes,0x1a58,e1);
    WriteAt<std::int32_t>(g_RoomBytes,0x1a5c,e2);
    WriteAt<std::int32_t>(g_RoomBytes,0x1a60,b1);
    WriteAt<std::int32_t>(g_RoomBytes,0x1a64,b2);
    const char*script=R"lua(
        local enemies,bosses=Isaac.CountEnemies(),Isaac.CountBosses()
        -- EID 5.21 main.lua:1358-1362, its actual visibility condition.
        local function visible(hideInBattle)
            if hideInBattle then
                if Isaac.CountBosses()>0 or Isaac.CountEnemies()>0 then return false end
            end
            return true
        end
        print('COUNTS '..enemies..','..bosses)
        print('EID '..tostring(visible(true))..','..tostring(visible(false)))
    )lua";
    (void)LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@eid-hide-counts.lua");
    return 0;
}
'''

class EIDHideInBattleCountsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="eid-hide-counts-")
        cls.binary=build_lua_harness(source_root=SOURCE,workdir=Path(cls.temp.name),
                                    harness_source=PREFIX+MAIN)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def run_scene(self,scene):
        r=subprocess.run([str(self.binary),scene],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        return r.stdout+r.stderr
    def test_shop_npcs_do_not_trigger_eid_battle_hiding(self):
        s=self.run_scene('shop')
        self.assertIn('COUNTS 0,0',s)
        self.assertIn('EID true,true',s)
    def test_real_combat_counters_hide_only_when_enabled(self):
        s=self.run_scene('combat')
        self.assertIn('COUNTS 5,2',s)
        self.assertIn('EID false,true',s)
    def test_negative_native_totals_are_zero(self):
        self.assertIn('COUNTS 0,0',self.run_scene('negative'))
    def test_native_32bit_add_wraps_before_signed_clamp(self):
        self.assertIn('COUNTS 0,2147483647',self.run_scene('overflow'))

if __name__=='__main__':unittest.main()
