"""真实Lua5.3执行完整StageAPI网格POST_RENDER，比较原生读取和消费者轨迹。"""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
try:
 from .test_support import lua_harness_objects
 from .test_wmd_font_cache import HARNESS
except ImportError:
 from test_support import lua_harness_objects
 from test_wmd_font_cache import HARNESS
ROOT=Path(__file__).resolve().parents[2]
AUTHOR=ROOT/'dist/stageapi-grid-read-reuse-20261017/author-callbacks.lua'
PATCH=ROOT/'runtime/mod-patches/StageAPI/scripts/stageapi/core/callbacks.lua'

def consumer(source):
 start=source.index('local FramesTabPressed = 0')
 end=source.index('function StageAPI.SetCurrentBossRoomInPlace(',start)
 return source[start:end]

LUA=r'''
local function serial(v)
 if type(v)~='table'then return type(v)..':'..tostring(v)end
 local out={};for i=1,#v do out[i]=serial(v[i])end;return '{'..table.concat(out,',')..'}'
end
local function run(source,config)
 local trace,metrics,states,objects,doors,metadata,streaks={},{},{},{},{},{},{}
 local frame=0;local readings
 local function note(...)trace[#trace+1]={frame,...}end
 local function newGrid(i,t,v,anim,animframe)
  states[i]={t=t,v=v or 0,anim=anim or 'Idle',animframe=animframe or 0}
  local desc=setmetatable({}, {__index=function(_,key)
   local r=readings[i];if key=='Type'then r.types[#r.types+1]=states[i].t;return states[i].t end
   if key=='Variant'then r.variant=r.variant+1;return states[i].v end
   error('unexpected descriptor field '..key)
  end})
  objects[i]=setmetatable({}, {__index=function(_,key)
   if key=='Desc'then readings[i].desc=readings[i].desc+1;return desc end
   if key=='GetSprite'then return function()note('sprite',i);return {
    GetAnimation=function()note('animation',i,states[i].anim);return states[i].anim end,
    GetFrame=function()note('animation-frame',i,states[i].animframe);return states[i].animframe end}end end
   error('unexpected grid field '..key)
  end})
 end
 newGrid(1,1);newGrid(2,9);newGrid(3,2,10,'Switched',0);newGrid(4,2,11,'Switched',1);newGrid(5,2,99,'Switched',0);newGrid(6,2,10,'Idle',0)
 local function door(slot)return {GetGridIndex=function()return slot+100 end}end
 doors[0]=door(0)
 local room={
  GetGridSize=function()note('grid-size');return frame==4 and 6 or 7 end,
  GetGridEntity=function(_,i)note('grid',i,objects[i]~=nil);return objects[i]end,
  GetDoor=function(_,i)note('door',i,doors[i]~=nil);return doors[i]end,
  GetType=function()return 5 end,GetBackdropType=function()return frame>=4 and 2 or 1 end,
 }
 local current={Data={},Metadata={Search=function(_,query)
  note('event-search',query.Group,query.Tag)
  metadata[query.Group]=metadata[query.Group]or{{Triggered=false},{Triggered=false}}
  return metadata[query.Group]
 end},GetPlayingMusic=function()note('room-music');if config.music then return 17,true end end}
 local grids={Bridges='bridge-gfx'};if config.custom then current.Data.RoomGfx={Grids=grids}end
 local api={PreviousDoors={},RoomGrids={[41]={}},EventTriggerPlateVariants={[10]=true,[11]=true},S={BossIntro=42},RoomRendered=false}
 api.GetCurrentRoomID=function()note('room-id');return 41 end
 api.GetCurrentRoom=function()if config.noRoom then return nil end;return current end
 api.TriggerEventGroup=nil -- use the actual author consumer below
 api.CheckStageTrapdoor=function(grid,i)
  assert(grid==objects[i]);note('trapdoor',i,states[i].t,states[i].v)
  if config.mutate then
   if frame==1 and i==2 then states[4].t=1;newGrid(7,9);doors[1]=door(1)end
   if frame==2 and i==1 then states[2].t=2;states[2].v=11;states[2].anim='Switched';states[2].animframe=0 end
   if frame==3 and i==3 then states[3].t=1 end
   if frame==4 and i==1 then objects[5]=nil;doors[0]=nil end
  end
 end
 local callbacks=setmetatable({}, {__index=function(_,key)return key end})
 api.CallCallbacks=function(name,...)
  note('callback',name)
  if name=='PRE_UPDATE_GRID_GFX'then if config.override=='boolean'then return true elseif config.override=='table'then return grids end end
 end
 api.GetTableIndexedByDimension=function(t,create)note('dimension-table',create);return t end
 api.StoreRoomGrids=function()note('store-grids')end
 api.InOverriddenStage=function()return config.custom end
 api.GetDimension=function()return config.dimension or 0 end
 api.GetCurrentRoomType=function()return 5 end
 api.CheckBridge=function(grid,index,gfx)assert(grid==objects[index]);note('bridge',index,gfx)end
 api.ChangeGrids=function(gfx)assert(gfx==grids);note('change-grids')end
 api.ChangeSingleGrid=function(d,gfx,index)assert(gfx==grids);note('change-door',index)end
 api.GetScreenCenterPosition=function()return {X=160,Y=120}end
 api.GetScreenBottomRight=function()return {X=320,Y=240}end
 api.PlayTextStreak=function(args)
  note('streak',args.Text,args.AboveHud,args.Hold,args.HoldFrames,args.RenderPos.X,args.RenderPos.Y)
  streaks[#streaks+1]=args;return args
 end
 api.CanOverrideMusic=function(id)note('override-music',id);return true,true,false end
 api.GetCallbacks=function(name)note('get-callbacks',name);return config.custom and {{name='gfx'}}or{}end
 api.TryCallback=function(cb,cur,gfx,force,dimension)assert(cur==current);note('try-callback',cb.name,force,dimension);return true,{Grids=grids}end
 api.ChangeRoomGfx=function(gfx)note('change-room-gfx');return 27 end
 if config.custom then api.CurrentStage={RoomGfx={[5]={Grids=grids}},GetDisplayName=function()return 'test-stage'end,GetPlayingMusic=function()note('stage-music');return 19,false,20,false,false end}end
 local music={GetCurrentMusicID=function()return 1 end,GetQueuedMusicID=function()return 2 end,
  Queue=function(_,id)note('queue',id)end,Play=function(_,id,volume)note('music-play',id,volume)end,
  Crossfade=function(_,id,fade)note('crossfade',id,fade)end,UpdateVolume=function()note('volume')end,
  IsLayerEnabled=function()return frame%2==0 end,EnableLayer=function()note('layer-enable')end,DisableLayer=function()note('layer-disable')end}
 local shared={Room=room,Game={GetFrameCount=function()return frame end},Players={{ControllerIndex=0},{ControllerIndex=1}},Music=music,
  Sfx={IsPlaying=function()return frame==2 end,Stop=function(_,sound)note('sound-stop',sound)end,Play=function(_,...)note('sound-play',...)end}}
 local render
 local env=setmetatable({StageAPI=api,shared=shared,Callbacks=callbacks,DIMENSION_DEATH_CERTIFICATE=2,
  mod={AddCallback=function(_,id,fn)assert(id==1 and not render);render=fn;note('register',id)end},ModCallbacks={MC_POST_RENDER=1},
  GridEntityType={GRID_PIT=1,GRID_PRESSURE_PLATE=2},DoorSlot={NUM_DOOR_SLOTS=4},SoundEffect={SOUND_CASTLEPORTCULLIS=13},
  ButtonAction={ACTION_MAP=7},Input={IsActionPressed=function(action,index)assert(action==7);note('map-key',index);return config.map and frame<=23 end},
  Vector=function(x,y)return {X=x,Y=y}end},{__index=_G})
 assert(load(source,'whole-post-render','t',env))()
 for f=0,(config.map and 25 or 6)do
  frame=f;readings={};for i=0,7 do readings[i]={desc=0,variant=0,types={}}end
  if config.mutate and f==5 then newGrid(5,2,10,'Switched',0);doors[2]=door(2)end
  local ret=render();note('return',tostring(ret),api.PreviousGridCount or -1,not not api.RoomRendered,api.LastBackdropType or -1)
  for group,list in pairs(metadata)do note('event-state',group,list[1].Triggered,list[2].Triggered)end
  for i,s in ipairs(streaks)do note('streak-state',i,s.Hold)end
  metrics[#metrics+1]=readings
 end
 local seen={};for _,event in ipairs(trace)do seen[event[2]]=true end
 assert(seen['trapdoor'] and seen['callback'] and seen['sprite'],'scan consumer coverage missing')
 if config.noRoom then assert(not seen['event-search'],'no-room event must be ignored')else assert(seen['event-search'],'real TriggerEventGroup was not consumed')end
 if config.custom and config.dimension~=2 and config.override~='boolean'then assert(seen['bridge'] and seen['change-grids'],'custom grid gfx coverage missing')end
 if config.custom and config.map then assert(seen['streak'],'22-frame held map streak was not drawn')end
 if config.music then assert(seen['queue'] and seen['volume'] and seen['layer-enable'],'music branch coverage missing')end
 return {trace=serial(trace),metrics=metrics}
end
local function check(author,patch,config,label)
 local a,b=run(author,config),run(patch,config)
 assert(a.trace==b.trace,'consumer/event/render trace changed: '..label)
 for frame,grids in ipairs(a.metrics)do for index,orig in pairs(grids)do
  local opt=b.metrics[frame][index]
  assert(orig.variant==opt.variant,'Variant reads changed')
  assert(orig.desc==#orig.types+orig.variant and opt.desc==#opt.types+opt.variant,'descriptor allocation count inconsistent')
  if #orig.types>0 then
   assert(#orig.types==(orig.types[1]==1 and 1 or 2),'original Type read count unexpected')
   assert(#opt.types==1,'Type/Desc reads '..label..' frame '..frame..' grid '..index..': expected 1, got '..#opt.types)
   assert(orig.types[1]==opt.types[1],'grid type changed')
  else assert(#opt.types==0,'nil/early-return grid was read')end
 end end
end
'''

class StageapiGridReadReuseTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='stageapi-grid-read-');p=Path(cls.tmp.name);src=ROOT/'runtime/source'
  objects=lua_harness_objects(src,p);(p/'host.cpp').write_text(HARNESS);cls.host=p/'host'
  r=subprocess.run(['c++','-std=c++17','-I'+str(src/'third_party/lua-5.3.3/src'),str(p/'host.cpp'),*[str(o)for o in objects],'-o',str(cls.host)],capture_output=True,text=True)
  if r.returncode:raise AssertionError(r.stdout+r.stderr)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_complete_post_render_consumers_and_per_grid_type_read(self):
  self.assertEqual(len(AUTHOR.read_bytes()),79237)
  self.assertEqual(hashlib.sha256(AUTHOR.read_bytes()).hexdigest(),'b4d5bf2d661e917bb689e2444d61e2cde64bf754050d91d89707e18efe0ab4c6')
  candidate=PATCH.read_text()if PATCH.exists()else AUTHOR.read_text()
  code=LUA+'\nlocal author=[====['+consumer(AUTHOR.read_text())+']====]\nlocal patch=[====['+consumer(candidate)+']====]\n'+r'''
 local configs={{},{mutate=true},{custom=true,mutate=true},{custom=true,map=true,music=true,mutate=true},
 {custom=true,dimension=2,mutate=true},{custom=true,override='boolean'}, {custom=true,override='table',mutate=true}, {noRoom=true,mutate=true}}
 for i,config in ipairs(configs)do check(author,patch,config,'scenario '..i)end
 print('PASS: 8 full POST_RENDER scenarios; per-grid Type/Desc 2-to-1; Variant unchanged; event/trapdoor/door/grid/music/streak parity')
'''
  p=Path(self.tmp.name)/'case.lua';p.write_text(code);r=subprocess.run([str(self.host),str(p)],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout.strip())

if __name__=='__main__':unittest.main()
