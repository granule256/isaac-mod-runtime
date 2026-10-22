"""完整作者HUD回调跟随原生奖杯偏移；不增加每次绘制的Vector分配。"""
import hashlib,subprocess,tempfile,unittest,sys
from pathlib import Path
from .test_support import lua_harness_objects
from .test_wmd_font_cache import HARNESS
ROOT=Path(__file__).resolve().parents[2]
AUTHOR=ROOT/'dist/boss-icon-challenge-20261018/author-challenge-goal.lua'
PATCH=ROOT/'runtime/mod-patches/ChallengeAPI/scripts/challengeapi/hud/challenge_goal.lua'
LUA=r'''
local callbacks,draws={},{}
local visible,nohud,allocations=true,false,0
local sprite={Render=function(_,p)draws[#draws+1]={p.X,p.Y}end}
local api={Enum={Callbacks={CALLBACK_POST_LOADED=100,CALLBACK_CHALLENGE_STARTED=101}},Log=function()end}
function api:AddCallback(id,fn)callbacks[id]=fn end
function api:AddPriorityCallback(id,priority,fn)assert(priority==10);callbacks[id]=fn end
function api:IsInChallenge()return true end
function api:GetCurrentChallenge()return {FetchGoal=function()return {goalIcon=sprite}end}end
local env=setmetatable({ChallengeAPI=api,Options={HUDOffset=1},CallbackPriority={LATE=10},
 ModCallbacks={MC_PRE_GAME_EXIT=17,MC_POST_RENDER=2},SeedEffect={SEED_NO_HUD=1},
 Vector=function(x,y)allocations=allocations+1;return {X=x,Y=y}end,
 Game=function()return {GetHUD=function()return {IsVisible=function()return visible end}end,
 GetSeeds=function()return {HasSeedEffect=function()return nohud end}end}end},{__index=_G})
assert(load(source,'challenge-goal','t',env))()
callbacks[2]();assert(#draws==0 and allocations==0)
callbacks[101](api,api:GetCurrentChallenge(),false)
for _,offset in ipairs({1,0,0.5,0.01,1})do
 env.Options.HUDOffset=offset
 local before=allocations;callbacks[2]();assert(allocations==before+1,'extra Vector allocation')
 local got=draws[#draws];local x,y=36+20*(offset-1),86+12*(offset-1)
 assert(math.abs(got[1]-x)<0.00001 and math.abs(got[2]-y)<0.00001,
  'offset '..offset..': expected '..x..','..y..', got '..got[1]..','..got[2])
end
local count=#draws
visible=false;callbacks[2]();visible=true;nohud=true;callbacks[2]();nohud=false
assert(#draws==count,'HUD visibility changed')
callbacks[17]();callbacks[2]();assert(#draws==count and api.GoalHUD.hudSprite==nil)
callbacks[100]();callbacks[2]();assert(#draws==count+1,'reload did not reinitialize goal')
'''
class ChallengeGoalHudOffset(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='challenge-goal-');p=Path(cls.tmp.name);src=ROOT/'runtime/source'
  objects=lua_harness_objects(src,p);(p/'host.cpp').write_text(HARNESS);cls.host=p/'host'
  r=subprocess.run(['c++','-std=c++17','-I'+str(src/'third_party/lua-5.3.3/src'),str(p/'host.cpp'),*[str(o)for o in objects],'-o',str(cls.host)],capture_output=True,text=True)
  if r.returncode:raise AssertionError(r.stdout+r.stderr)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_actual_author_callbacks_follow_trophy_and_keep_lifecycle(self):
  self.assertEqual(hashlib.sha256(AUTHOR.read_bytes()).hexdigest(),'620e1c909b91e6347684cfeb4245ff3edeac4130b44f59fec7f978f3826fee5e')
  candidate=PATCH.read_text()if PATCH.exists()else AUTHOR.read_text()
  p=Path(self.tmp.name)/'case.lua';p.write_text('local source=[====['+candidate+']====]\n'+LUA)
  r=subprocess.run([str(self.host),str(p)],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_packaging_changes_only_reviewed_author_file(self):
  sys.path.insert(0,str(ROOT/'tools'));import build_deploy_package as package
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);src=p/'src';f=src/'scripts/challengeapi/hud/challenge_goal.lua';f.parent.mkdir(parents=True);f.write_bytes(AUTHOR.read_bytes())
   package.copy_tree(src,p/'out');got=(p/'out'/f.relative_to(src)).read_bytes()
   self.assertNotEqual(got,AUTHOR.read_bytes(),'approved HUD patch was not packaged')
   self.assertEqual(got,PATCH.read_bytes())
   f.write_bytes(AUTHOR.read_bytes()+b'\n-- new author version\n');package.copy_tree(src,p/'unknown')
   self.assertEqual((p/'unknown'/f.relative_to(src)).read_bytes(),f.read_bytes())
if __name__=='__main__':unittest.main()
