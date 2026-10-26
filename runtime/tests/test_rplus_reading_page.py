"""执行作者真实阅读页关闭分支，覆盖手柄、键盘与原150帧阅读等待。"""
from pathlib import Path
import subprocess
import unittest
from . import test_dss_clip_reuse as dss_fixture
ROOT=Path(__file__).resolve().parents[2]
AUTHOR=ROOT/'dist/change-archive-20261024/001-rplus-reading-controller/main.before.lua'
PATCH=ROOT/'runtime/mod-patches/repentanceplus/main.lua'
class RPlusReadingPageTests(unittest.TestCase):
 setUpClass=classmethod(dss_fixture.DssClipReuseTests.setUpClass.__func__)
 tearDownClass=classmethod(dss_fixture.DssClipReuseTests.tearDownClass.__func__)
 def test_reading_page_accepts_current_player_confirm(self):
  source=(PATCH if PATCH.exists() else AUTHOR).read_text()
  start=source.index('\tif FLAG_DISPLAY_UNLOCKS_TIP\n\tand ')
  end=source.index('\n\t-- helper for reading double tap',start)
  branch=source[start:end]
  code=r'''
local source=[====[BRANCH]====]
local function run(frame,key,action,controller,control)
 local calls,unlocked=0,0
 local env=setmetatable({FLAG_DISPLAY_UNLOCKS_TIP=true,Player={ControllerIndex=controller},
 Keyboard={KEY_E=69,KEY_ENTER=257,KEY_SPACE=32,KEY_LEFT_CONTROL=341},ButtonAction={ACTION_MENUCONFIRM=14},
 game={GetFrameCount=function()return frame end},unlockAll=function()unlocked=unlocked+1 end,
 Input={IsButtonTriggered=function(k,i)assert(i==controller);return k==key end,
 IsButtonPressed=function(k,i)assert(i==controller);return control and k==341 end,
 IsActionTriggered=function(a,i)assert(a==14 and i==controller);calls=calls+1;return action end}}, {__index=_G})
 assert(load(source,'reading-page','t',env))()
 return env.FLAG_DISPLAY_UNLOCKS_TIP,unlocked,calls
end
for _,controller in ipairs({1,33}) do
 local shown,unlocked=run(150,nil,true,controller,false)
 assert(not shown and unlocked==0,'controller confirm must close after reading delay')
 assert(run(149,nil,true,controller,false),'controller must preserve reading delay')
 assert(run(150,nil,false,controller,false),'no input must keep page open')
 for _,key in ipairs({69,257,32}) do
  assert(not run(150,key,false,controller,false),'keyboard compatibility')
  assert(run(149,key,false,controller,false),'keyboard reading delay')
 end
 local shown,unlocked=run(149,69,false,controller,true)
 assert(not shown and unlocked==1,'original keyboard debug branch')
end
print('PASS reading-page: controller 1/33, frame149/150, no input, keyboard and original debug branch')
'''.replace('BRANCH',branch)
  path=Path(self.tmp.name)/'reading.lua';path.write_text(code)
  result=subprocess.run([str(self.host),str(path)],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr);print(result.stdout.strip())
