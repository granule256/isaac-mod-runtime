"""真实Lua5.3执行作者完整drawMenu及真实字宽/颜色上下文，比较绘制与分配。"""
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
AUTHOR=ROOT/'dist/dss-clip-reuse-20261017/author-dssmenucore.lua'
PATCH=ROOT/'runtime/mod-patches/repentanceplus/scripts/dssmenucore.lua'


def context(source):
 """按作者同级声明边界提取完整函数；不重写drawMenu或字宽算法。"""
 def part(start,end):
  return source[source.index(start):source.index(end,source.index(start))]
 return '\n'.join([
  part('    local mfdat = {}','    dssmod.menusounds ='),
  part('    local function getScreenBottomRight()','    local function approach('),
  part('    local function Lerp(','    local function KeysShareVals('),
  part('    local function hsvToRgb(','    local function bselToXY('),
  part('    local function getMenuStringLength(','    function dssmod.generateDynamicSet('),
  part('    function dssmod.drawMenu(','    function dssmod.handleInputs('),
 ])

LUA=r'''
local function serial(v)
 if type(v)~='table' then return type(v)..':'..tostring(v) end
 local out={};for i=1,#v do out[i]=serial(v[i]) end;return '{'..table.concat(out,',')..'}'
end
local function run(source,case)
 local events,groups,stack={}, {}, {}
 local constructs=0
 local mt={}
 local function make(x,y) return setmetatable({X=x,Y=y},mt) end
 local function vec(x,y) constructs=constructs+1;return make(x,y) end
 mt.__add=function(a,b)return make(a.X+b.X,a.Y+b.Y) end
 mt.__sub=function(a,b)return make(a.X-b.X,a.Y-b.Y) end
 mt.__mul=function(a,b)if type(b)=='number'then return make(a.X*b,a.Y*b)end;return make(a.X*b.X,a.Y*b.Y)end
 mt.__div=function(a,b)return make(a.X/b,a.Y/b)end
 function mt.__index(t,k)if k=='Rotated'then return function(a,degrees)local r=degrees*math.pi/180;return make(a.X*math.cos(r)-a.Y*math.sin(r),a.X*math.sin(r)+a.Y*math.cos(r))end end end
 local colors={}
 local function color(r,g,b,a,ro,go,bo)
  return setmetatable({R=r,G=g,B=b,A=a,RO=ro or 0,GO=go or 0,BO=bo or 0},{__index={SetColorize=function(self,...)self.colorize={...}end}})
 end
 local Color=setmetatable({}, {__call=function(_,...)return color(...)end})
 Color.Lerp=function(a,b,p)return color(a.R+(b.R-a.R)*p,a.G+(b.G-a.G)*p,a.B+(b.B-a.B)*p,a.A+(b.A-a.A)*p)end
 local function cv(c)if not c then return {}end;return {c.R,c.G,c.B,c.A,c.RO,c.GO,c.BO,c.colorize or {}}end
 local function vv(v)if not v then return {}end;return {v.X,v.Y}end
 local function sprite(name)
  local s={Color=color(1,1,1,1),Scale=make(1,1)}
  function s:SetFrame(...)events[#events+1]={'frame',name,{...},cv(self.Color),vv(self.Scale)}end
  function s:SetAnimation(...)events[#events+1]={'animation',name,{...}}end
  function s:Render(pos,top,bottom)
   events[#events+1]={'render',name,vv(pos),vv(top),vv(bottom),cv(self.Color),vv(self.Scale)}
   -- Native Sprite.Render consumes const Vector2&. Snapshot but never mutate inputs.
   if name=='font'then local g=stack[#stack];g.n=g.n+1;g.clips[top]=true;g.clips[bottom]=true end
  end
  return s
 end
 local sprites={Font=sprite('font'),Symbols=sprite('symbols')}
 local pal={color(.1,.2,.3,1),color(.8,.6,.4,1),color(.2,.9,.5,1)}
 local frame=case.frame or 17
 local env=setmetatable({Vector=vec,Color=Color,dssmod={},Isaac={ConsoleOutput=function(s)events[#events+1]={'console',s}end},game={GetFrameCount=function()return frame end,GetRoom=function()return {GetRenderSurfaceTopLeft=function()return make(3,5)end}end}}, {__index=_G})
 env.DeadSeaScrollsMenu={GetPalette=function()return pal end,GetDefaultMenuSprites=function()return sprites end}
 assert(load(source,'drawMenu-context','t',env))()
 local original=env.dssmod.drawMenu
 env.dssmod.drawMenu=function(tbl,tab)
  local g={n=0,clips={}};groups[#groups+1]=g;stack[#stack+1]=g
  local ret=original(tbl,tab);stack[#stack]=nil
  events[#events+1]={'return',tostring(ret)};return ret
 end
 local tab={type='str',str=case.str or 'abcde',size=case.size or 1,pos=vec(5,10),root=vec(120,90),scale=vec(case.sx or 1,case.sy or 1),halign=case.align or 0,alpha=.7}
 if case.bounds then tab.bounds={-100,case.bounds[1],100,case.bounds[2]}end
 if case.clip==false then tab.noclip=true end
 if case.empty then tab.str=''end
 if case.colored then tab.str={{str='abc',color=3},{str='d',color=color(.3,.4,.5,.6)},{str='e'}}end
 if case.effects then tab.glowcolor=3;tab.rainbow=true;tab.shine=.2;tab.usecolorize=true;tab.colorselect=true;tab.fontcolor=2 end
 if case.slider then tab.slider=true;tab.max=5;tab.increment=1;tab.setting=2;tab.hintletter='c';tab.underline=true end
 if case.arrows then tab.select=true;tab.settingscursor=true;tab.choices=4;tab.setting=2;tab.cursoroff=vec(-2,3);tab.inline=true end
 if case.dynamic then
  local children={tab,{type='str',str='xyz',size=2,pos=vec(2,1),halign=-1,height=12,select=true}, {type='str',str='12',size=3,pos=vec(-3,0),height=17,underline=true}}
  tab.root=nil;tab.pos=vec(0,0);tab.height=10
  tab={type='dynamicset',set=children,root=vec(120,90),pos=vec(3,5),bounds={-100,-20,100,90},width=90,halign=0}
  if case.grid then
   tab.gridx=2;tab.centeritems=true;tab.highest=20
   for i,v in ipairs(children)do v.widestinrow=70;v.highestinrow=20;v.width=50;v.height=14;v.gridxpos=(i-1)%2+1;v.gridypos=math.floor((i-1)/2)+1 end
  end
 end
 local tbl={};if case.customSprites then tbl.MenuSprites=sprites end
 local before=constructs
 env.dssmod.drawMenu(tbl,tab)
 if case.repeatClip then
  tab.bounds={-100,13,100,16};frame=43;env.dssmod.drawMenu(tbl,tab)
  tab.bounds={-100,-30,100,7};frame=62;env.dssmod.drawMenu(tbl,tab)
  tab.bounds={-100,-90,100,100};env.dssmod.drawMenu(tbl,tab)
 end
 local summary={};local saving=0
 for i,g in ipairs(groups)do local count=0;for _ in pairs(g.clips)do count=count+1 end
  summary[i]={g.n,count};if g.n>0 then saving=saving+2*(g.n-1)end
 end
 return {events=serial(events),groups=summary,allocations=constructs-before,saving=saving}
end
local function check(original,patch,case,label)
 local a=run(original,case);local b=run(patch,case)
 assert(a.events==b.events,'draw/frame/return mismatch: '..label)
 assert(#a.groups==#b.groups,'recursive call count changed: '..label)
 for i,g in ipairs(a.groups)do
  assert(g[2]==2*g[1],'author clip count unexpected: '..label)
  assert(b.groups[i][1]==g[1],'glyph render count changed: '..label)
  local expected=g[1]>0 and 2 or 0
  assert(b.groups[i][2]==expected,'clip vectors '..label..': expected '..expected..', got '..b.groups[i][2])
 end
 assert(a.allocations-b.allocations==a.saving,'Vector constructor delta mismatch: '..label)
end
'''

class DssClipReuseTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='dss-clip-reuse-');p=Path(cls.tmp.name)
  src=ROOT/'runtime/source';objects=lua_harness_objects(src,p)
  (p/'host.cpp').write_text(HARNESS);cls.host=p/'host'
  r=subprocess.run(['c++','-std=c++17','-I'+str(src/'third_party/lua-5.3.3/src'),str(p/'host.cpp'),*[str(o)for o in objects],'-o',str(cls.host)],capture_output=True,text=True)
  if r.returncode:raise AssertionError(r.stdout+r.stderr)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_full_draw_menu_parity_and_lazy_clip_vector_reuse(self):
  self.assertEqual(len(AUTHOR.read_bytes()),116028)
  self.assertEqual(hashlib.sha256(AUTHOR.read_bytes()).hexdigest(),'69d7a3a59a33c1e40f8dbc68e5cf83cec83bd1a8a5035f8cb23de7bf5e8f69d2')
  author=context(AUTHOR.read_text());candidate=context(PATCH.read_text()if PATCH.exists()else AUTHOR.read_text())
  code=LUA+'\nlocal author=[====['+author+']====]\nlocal patch=[====['+candidate+']====]\n'+r'''
 for size=1,3 do for _,align in ipairs({-2,-1,0,1})do
  check(author,patch,{size=size,align=align,sx=.8,sy=1.3,bounds={12,16}},'size-align-clip '..size..'/'..align)
 end end
 local cases={
 {},{empty=true},{str='a'},{str='ab'},{str='abcdefghij'},
 {bounds={40,90}},{bounds={-50,-40}},{bounds={40,90},clip=false},
 {colored=true,effects=true,frame=47},{slider=true,bounds={-10,80}},
 {arrows=true,bounds={-10,80},customSprites=true},
 {dynamic=true},{dynamic=true,grid=true},
 {repeatClip=true,colored=true,slider=true,effects=true},
 }
 for i,case in ipairs(cases)do check(author,patch,case,'scenario '..i)end
 print('PASS: 26 cases, full drawMenu traces, 2N-to-2 clip constructors, zero-render lazy, recursive groups and changing clips')
'''
  p=Path(self.tmp.name)/'case.lua';p.write_text(code)
  r=subprocess.run([str(self.host),str(p)],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout.strip())

if __name__=='__main__':unittest.main()
