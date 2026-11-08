"""Behavior checks for the optional entity-free environmental rain mod."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from runtime.tests.test_support import lua_harness_objects

PUBLIC = Path(__file__).resolve().parents[1]
MOD = PUBLIC / 'mods/isaac_visual_rain'
DRIVER = r'''
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
#include <cstdio>
int main(int argc,char**argv){
 auto*L=luaL_newstate();
 luaL_requiref(L,"_G",luaopen_base,1);lua_pop(L,1);
 luaL_requiref(L,"math",luaopen_math,1);lua_pop(L,1);
 luaL_requiref(L,"table",luaopen_table,1);lua_pop(L,1);
 int rc=argc!=2||luaL_dofile(L,argv[1]);
 if(rc)std::fprintf(stderr,"%s\n",lua_tostring(L,-1));
 lua_close(L);return rc;
}
'''
SETUP = r'''
local Rain=dofile(MODULE)
local stats={queries=0,stops=0,loads=0,updates=0,draws=0,removed=0}
local vectorMT={}
vectorMT.__add=function(a,b)return Vector(a.X+b.X,a.Y+b.Y)end
vectorMT.__sub=function(a,b)return Vector(a.X-b.X,a.Y-b.Y)end
function Vector(x,y)return setmetatable({X=x,Y=y},vectorMT)end
VectorZero=Vector(0,0)
BackdropType={DOWNPOUR=31,DROSS=45}
RoomShape={ROOMSHAPE_1x1=1,ROOMSHAPE_IH=2,ROOMSHAPE_IV=3,ROOMSHAPE_1x2=4,
 ROOMSHAPE_IIV=5,ROOMSHAPE_2x1=6,ROOMSHAPE_IIH=7,ROOMSHAPE_2x2=8}
local room={backdrop=31,shape=1,left=Vector(40,120),right=Vector(600,400)}
function room:GetBackdropType()return self.backdrop end
function room:GetRoomShape()return self.shape end
function room:GetTopLeftPos()return self.left end
function room:GetBottomRightPos()return self.right end
function room:StopRain()stats.stops=stats.stops+1 end
local game={paused=false}
function game:GetRoom()return room end
function game:IsPaused()return self.paused end
function Game()return game end
local effects={}
local function effect(t,v,sub,spawner)
 local e={Type=t or 1000,Variant=v or 135,SubType=sub or 0,
  SpawnerType=spawner and spawner.Type or 0,SpawnerEntity=spawner}
 function e:Remove()self.removed=true;stats.removed=stats.removed+1 end
 return e
end
Isaac={FindByType=function(t,v,s)
 stats.queries=stats.queries+1;local a={}
 for _,e in ipairs(effects)do
  if not e.removed and e.Type==t and e.Variant==v and (s==-1 or e.SubType==s)then a[#a+1]=e end
 end
 return a
end,WorldToScreen=function(v)return v+Vector(10,20)end}
local sprite={}
function sprite:Load(path,graphics)
 stats.loads=stats.loads+1;assert(path=='gfx/isaac_visual_rain.anm2'and graphics)
 if stats.failLoad then error('asset missing')end
end
function sprite:Play(name)assert(name=='Rain')end
function sprite:IsPlaying(name)return name=='Rain'and not stats.invalidAnimation end
function sprite:Update()stats.updates=stats.updates+1 end
function sprite:Render(p)stats.draws=stats.draws+1;stats.positions=stats.positions or {};stats.positions[#stats.positions+1]=p;assert(p.X==p.X and p.Y==p.Y)end
function Sprite()return sprite end
math.random=function()error('gameplay RNG must not be consumed')end
local rain=Rain.new()
'''


class VisualRainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='visual-rain-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        source = PUBLIC / 'runtime/source'
        cpp = cls.directory / 'runner.cpp'
        cpp.write_text(DRIVER)
        cls.runner = cls.directory / 'lua'
        result = subprocess.run([
            'c++', '-std=c++17', '-I'+str(source/'third_party/lua-5.3.3/src'),
            str(cpp), *map(str,lua_harness_objects(source,cls.directory)),
            '-o',str(cls.runner),
        ],capture_output=True,text=True)
        if result.returncode:
            raise AssertionError(result.stdout+result.stderr)

    def run_lua(self, checks, setup=SETUP):
        self.assertTrue((MOD/'scripts/rain.lua').is_file(), 'visual rain module is not implemented')
        script = self.directory/(self._testMethodName+'.lua')
        script.write_text('MODULE='+json.dumps(str(MOD/'scripts/rain.lua'))+'\n'
                          +'MOD_DIR='+json.dumps(str(MOD))+'\n'+setup+checks)
        result=subprocess.run([str(self.runner),str(script)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_dry_room_does_not_poll_entities_or_stop_rain(self):
        self.run_lua('''
rain:onNewRoom();local queries=stats.queries
for i=1,200 do rain:onUpdate();rain:onRender()end
assert(stats.queries==queries and stats.stops==0 and stats.loads==0 and stats.draws==0)
assert(not rain:getStatus().active)
''')

    def test_native_rain_takeover_only_removes_decorative_drops_once(self):
        self.run_lua('''
rain:onNewRoom()
effects={effect(),effect(),effect(9,4),effect(1000,135,1),effect(1000,135,0,{Type=10}),effect(1000,133)}
rain:onEffectInit(effects[1]);assert(stats.stops==0)
rain:onUpdate();assert(stats.stops==1 and stats.removed==2)
for i=3,#effects do assert(not effects[i].removed,'attack or unrelated effect removed')end
assert(rain:getStatus().active and rain:getStatus().enabled)
local queries=stats.queries
for i=1,100 do rain:onUpdate();rain:onRender()end
assert(stats.stops==1 and stats.queries==queries and stats.loads==1)
''')

    def test_unknown_rooms_and_scripted_rain_are_not_replaced(self):
        self.run_lua('''
for _,backdrop in ipairs({1,36,45,31})do
 room.backdrop=backdrop
 for _,shape in ipairs({1,8,9,10,13})do
  room.shape=shape;effects={};rain:onNewRoom()
  if (backdrop~=31 and backdrop~=45)or shape>8 then
   rain:onEffectInit(effect());rain:onUpdate();assert(not rain:getStatus().active)
  end
 end
end
room.shape=1;room.backdrop=31;rain:onNewRoom()
for _,e in ipairs({effect(9,135),effect(1000,136),effect(1000,135,1),effect(1000,135,0,{Type=1})})do
 rain:onEffectInit(e);rain:onUpdate()
end
assert(stats.stops==0)
''')

    def test_animation_is_shared_bounded_and_frozen_while_paused(self):
        self.run_lua('''
effects={effect()};rain:onNewRoom();rain:onUpdate()
assert(rain:getStatus().active)
local updates,queries=stats.updates,stats.queries
for i=1,60 do rain:onRender()end
assert(stats.updates==updates and stats.queries==queries)
assert(stats.draws>0 and stats.draws<=60*12,'unbounded per-drop rendering')
game.paused=true;rain:onUpdate();rain:onRender();assert(stats.updates==updates)
game.paused=false;rain:onUpdate();assert(stats.updates==updates+1)
''')

    def test_render_projects_world_bounds_instead_of_using_world_pixel_offsets(self):
        self.run_lua('''
Isaac.WorldToScreen=function(v)return Vector(v.X*.5+10,v.Y*.5+20)end
effects={effect()};rain:onNewRoom();rain:onUpdate();rain:onRender()
assert(sprite.Scale.X<.6 and sprite.Scale.Y<.6,'world scale was used for screen drawing')
for _,p in ipairs(stats.positions)do
 assert(p.X>=38 and p.X<302 and p.Y>=88 and p.Y<212,'tile escaped projected room bounds')
end
''')

    def test_disable_is_deferred_until_room_boundary_and_can_be_reenabled(self):
        self.run_lua('''
effects={effect()};rain:onNewRoom();rain:onUpdate();assert(rain:getStatus().active)
rain:setEnabled(false)
assert(not rain:getStatus().enabled and rain:getStatus().active and rain:getStatus().pendingRestore)
room.backdrop=1;effects={};rain:onNewRoom();rain:onUpdate()
assert(not rain:getStatus().active and not rain:getStatus().pendingRestore)
room.backdrop=31;effects={effect()};rain:onNewRoom();rain:onUpdate();assert(stats.stops==1)
rain:setEnabled(true);rain:onUpdate();assert(stats.stops==2 and rain:getStatus().active)
rain:reset();rain:onRender();assert(not rain:getStatus().active)
assert(not pcall(function()rain:setEnabled(1)end))
''')

    def test_loading_failure_keeps_original_rain_and_can_retry_next_room(self):
        self.run_lua('''
effects={effect()};stats.failLoad=true;rain:onNewRoom();rain:onUpdate()
assert(not rain:getStatus().active and stats.stops==0 and stats.removed==0)
local loads=stats.loads
for i=1,30 do rain:onEffectInit(effect());rain:onUpdate()end
assert(stats.loads==loads,'failed asset retried for each particle')
stats.failLoad=false;rain:onNewRoom();rain:onUpdate();assert(rain:getStatus().active)
''')

    def test_missing_animation_keeps_original_rain(self):
        self.run_lua('''
effects={effect()};stats.invalidAnimation=true;rain:onNewRoom();rain:onUpdate()
assert(stats.stops==0 and stats.removed==0 and not rain:getStatus().active)
''')

    def test_main_wires_filtered_callbacks_and_persists_user_choice(self):
        self.run_lua(r'''
local callbacks,saved={},nil
local mod={}
function mod:AddCallback(id,fn,param)callbacks[id]={fn=fn,param=param}end
function mod:HasData()return saved~=nil end
function mod:LoadData()return saved end
function mod:SaveData(s)saved=s end
function RegisterMod()return mod end
function include(path)return dofile(MOD_DIR..'/'..path..'.lua')end
ModCallbacks={MC_POST_NEW_ROOM=19,MC_POST_GAME_STARTED=15,MC_POST_EFFECT_INIT=54,
 MC_POST_UPDATE=1,MC_POST_RENDER=2,MC_PRE_GAME_EXIT=17,MC_PRE_MOD_UNLOAD=73}
dofile(MOD_DIR..'/main.lua')
assert(callbacks[54].param==135,'effect init callback must be filtered')
callbacks[15].fn(mod,false);assert(IsaacVisualRain:GetStatus().enabled)
IsaacVisualRain:SetEnabled(false);assert(saved and not IsaacVisualRain:GetStatus().enabled)
dofile(MOD_DIR..'/main.lua');callbacks[15].fn(mod,true)
assert(not IsaacVisualRain:GetStatus().enabled,'saved setting lost on continue')
IsaacVisualRain:SetEnabled(true);effects={effect()};callbacks[19].fn(mod);callbacks[1].fn(mod)
assert(IsaacVisualRain:GetStatus().active)
callbacks[17].fn(mod,true);assert(not IsaacVisualRain:GetStatus().active)
callbacks[73].fn(mod,{});assert(IsaacVisualRain~=nil)
callbacks[73].fn(mod,mod);assert(IsaacVisualRain==nil)
''')

    def test_animation_uses_local_texture_and_valid_looping_frames(self):
        path=MOD/'resources/gfx/isaac_visual_rain.anm2'
        self.assertTrue(path.is_file(),'visual rain animation is not implemented')
        actor=ET.parse(path).getroot()
        animation=actor.find("./Animations/Animation[@Name='Rain']")
        self.assertIsNotNone(animation)
        self.assertEqual(animation.get('Loop'),'true')
        frames=animation.findall('./LayerAnimations/LayerAnimation/Frame')
        self.assertGreater(len(frames),1)
        sheet=actor.find('./Content/Spritesheets/Spritesheet')
        texture=MOD/'resources/gfx'/sheet.get('Path')
        self.assertTrue(texture.is_file())
        import struct
        data=texture.read_bytes()
        self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
        w,h=struct.unpack('>II',data[16:24])
        for f in frames:
            self.assertLessEqual(int(f.get('XCrop'))+int(f.get('Width')),w)
            self.assertLessEqual(int(f.get('YCrop'))+int(f.get('Height')),h)
        self.assertEqual(sum(int(f.get('Delay'))for f in frames),int(animation.get('FrameNum')))


if __name__=='__main__':
    unittest.main()
