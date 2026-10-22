"""真实StageAPI共享表及原作者生成回调在首次NEW_ROOM之前也须可用。"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LUA = ROOT / "runtime/source/third_party/lua-5.3.3/src"
SHARED = ROOT / "runtime/mod-patches/StageAPI/scripts/stageapi/shared.lua"
CONSUMER = ROOT / "runtime/tests/fixtures/stageapi_shared_init/altRockOverride.lua"

SETUP = r'''
local rooms, levels, grids = 0, 0, 0
local currentRoom = {GetGridIndex=function(_,position) grids=grids+1;return 7 end}
local currentLevel = {}
local game = {
 GetRoom=function() rooms=rooms+1;return currentRoom end,
 GetLevel=function() levels=levels+1;return currentLevel end,
}
Game=function() return game end
SFXManager=function() return {} end
MusicManager=function() return {} end
Isaac={GetItemConfig=function() return {} end,GetPlayer=function() return nil end}
StageAPI={GetPlayers=function() return {currentRoom} end}
local shared=assert(loadfile(arg[1]))()
'''

SCENARIOS = {
 "room": "assert(shared.Room==currentRoom, 'first Room lookup must use real Game getter');assert(rooms==1);assert(shared.Room==currentRoom and rooms==1)",
 "level": "assert(shared.Level==currentLevel, 'first Level lookup must use real Game getter');assert(levels==1);assert(shared.Level==currentLevel and levels==1)",
 "refresh": r'''
assert(shared.Room==currentRoom)
local nextRoom={};shared.Room=nextRoom
assert(shared.Room==nextRoom and rooms==1, 'normal NEW_ROOM assignment must win')
shared.Room=nil;currentRoom={};assert(shared.Room==currentRoom and rooms==2)
assert(shared.Level==currentLevel);shared.Level=nil;currentLevel={}
assert(shared.Level==currentLevel and levels==2)
''',
 "players": r'''
local first=shared.Players;currentRoom={};local second=shared.Players
assert(first[1]~=second[1] and second[1]==currentRoom)
assert(rawget(shared,'Players')==nil and shared.unknown==nil)
assert(rooms==0 and levels==0)
''',
 "unavailable": r'''
currentRoom=nil
assert(shared.Room==nil and rooms==1 and levels==0, 'missing Room must not return a Level')
currentRoom={};assert(shared.Room==currentRoom and rooms==2)
currentLevel=nil
assert(shared.Level==nil and levels==1)
currentLevel={};assert(shared.Level==currentLevel and levels==2)
''',
 "author_spawn": r'''
local preSpawn
local mod={AddCallback=function(_,id,fn) if id==24 then preSpawn=fn end end}
package.loaded['scripts.stageapi.shared']=shared
package.loaded['scripts.stageapi.mod']=mod
package.loaded['scripts.stageapi.enums.Callbacks']=setmetatable({}, {__index=function(_,k)return k end})
ModCallbacks=setmetatable({MC_PRE_ENTITY_SPAWN=24},{__index=function(_,k)return k end})
GridEntityType={GRID_ROCK_ALT=6};RNG=function()return {}end
StageAPI.LogMinor=function()end;StageAPI.CustomGrid=function()return {}end
StageAPI.AddCallback=function()end;StageAPI.DeleteEntity=function()end
StageAPI.E={DeleteMeNPC={T=1,V=1},DeleteMeEffect={V=1},DeleteMeProjectile={V=1},DeleteMePickup={V=1},RandomRune={V=1}}
StageAPI.GetCustomGrid=function()return nil end;StageAPI.GetCustomGrids=function()return {}end
assert(loadfile(arg[2]))()
assert(type(preSpawn)=='function')
assert(preSpawn(mod,1000,68,0,{X=1,Y=2},{X=0,Y=0},nil,123)==nil)
assert(grids==1 and rooms==1, 'original wall-bug consumer must reach actual Room method')
''',
}


class StageApiSharedInitializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="isaac-stageapi-shared-")
        cls.binary = Path(cls.temp.name) / "lua"
        sources = sorted(str(p) for p in LUA.glob("*.c") if p.name != "luac.c")
        subprocess.run(["cc", "-O0", "-std=gnu99", "-I", str(LUA), *sources,
                        "-lm", "-o", str(cls.binary)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check_scenario(self, name):
        script = Path(self.temp.name) / (name + ".lua")
        script.write_text(SETUP + SCENARIOS[name])
        result = subprocess.run([str(self.binary), str(script), str(SHARED), str(CONSUMER)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_room_before_player_initialization(self): self.check_scenario("room")
    def test_level_before_player_initialization(self): self.check_scenario("level")
    def test_normal_room_assignment_and_explicit_reset(self): self.check_scenario("refresh")
    def test_players_remain_dynamic_and_unknown_keys_stay_nil(self): self.check_scenario("players")
    def test_unavailable_objects_remain_nil_until_real_getter_succeeds(self): self.check_scenario("unavailable")
    def test_original_spawn_consumer_before_new_room(self): self.check_scenario("author_spawn")
