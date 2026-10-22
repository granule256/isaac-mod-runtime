"""在真实 Lua 5.3 中对完整作者脚本和私有字体缓存补丁做行为对照。"""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
try:
 from .test_support import lua_harness_objects
except ImportError:
 from test_support import lua_harness_objects

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / 'dist/mod-attribution-20261017/device-wmd.lua'
PATCH = ROOT / 'runtime/mod-patches/whatsmydps/main.lua'

HARNESS = r'''
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
#include <cstdio>
int main(int argc, char** argv) {
 lua_State* L=luaL_newstate();
 luaL_requiref(L,"_G",luaopen_base,1); lua_pop(L,1);
 luaL_requiref(L,"string",luaopen_string,1); lua_pop(L,1);
 luaL_requiref(L,"table",luaopen_table,1); lua_pop(L,1);
 luaL_requiref(L,"math",luaopen_math,1); lua_pop(L,1);
 int rc=luaL_loadfile(L,argv[1]); if(!rc) rc=lua_pcall(L,0,0,0);
 if(rc) std::fprintf(stderr,"%s\n",lua_tostring(L,-1));
 lua_close(L); return rc?1:0;
}
'''

LUA = r'''
local function serialize(v)
 if type(v) ~= 'table' then return type(v)..':'..tostring(v) end
 local out={}; for i=1,#v do out[i]=serialize(v[i]) end
 return '{'..table.concat(out,',')..'}'
end
local function run(source, failures, second)
 local trace, draws, callbacks, options, fonts = {}, {}, {}, {}, {}
 fonts=setmetatable(fonts,{__mode="v"})
 local count, loads, paused, saved = 0,0,false,initialSettings
 local function event(...) trace[#trace+1]=serialize({...}) end
 local vecmt={}
 local function vec(x,y) return setmetatable({X=x,Y=y},vecmt) end
 vecmt.__sub=function(a,b) return vec(a.X-b.X,a.Y-b.Y) end
 vecmt.__mul=function(a,b) return vec(a.X*b,a.Y*b) end
 local player={Position=vec(120,80),Damage=3.5,MaxFireDelay=9}
 local room={GetRenderScrollOffset=function() return vec(2,3) end,
 WorldToScreenPosition=function(_,p) return vec(p.X+4,p.Y+6) end}
 local game={ScreenShakeOffset=vec(1,2),GetRoom=function() return room end,
 IsPaused=function() return paused end}
 local mod={}
 function mod:AddCallback(id,fn) callbacks[#callbacks+1]={id,fn}; event('callback',id) end
 local env=setmetatable({}, {__index=_G})
 env.RegisterMod=function(name,version) event('register',name,version); return mod end
 env.Game=function() return game end
 env.Vector=vec; env.KColor=function(...) return {...} end
 env.DamageFlag={DAMAGE_LASER=1,DAMAGE_EXPLOSION=2}
 env.ModCallbacks={MC_ENTITY_TAKE_DMG=1,MC_POST_RENDER=2,MC_POST_PLAYER_INIT=3,MC_POST_NEW_ROOM=4}
 env.Isaac={LoadModData=function() event('load'); return saved end,
 SaveModData=function(_,s) saved=s; event('save',s) end,
 GetPlayer=function(i) assert(i==0); return player end,
 WorldToScreen=function(p) return vec(p.X+3,p.Y+5) end}
 env.ModConfigMenu={OptionType={BOOLEAN=1},AddSetting=function(name,category,opt)
 options[#options+1]=opt; event('setting',name,category or '',opt.Type,opt.Display(),opt.CurrentSetting()) end}
 local ctor=function()
 count=count+1; local f={id=count,loaded=false}; fonts[#fonts+1]=f
 function f:Load(path) assert(path=='font/pftempestasevencondensed.fnt'); loads=loads+1; self.loaded=loads>failures; return nil end
 function f:IsLoaded() return self.loaded end
 function f:DrawString(...) draws[#draws+1]=serialize({'normal',self.loaded,...}) end
 function f:DrawStringScaled(...) draws[#draws+1]=serialize({'scaled',self.loaded,...}) end
 return f
 end
 env.Font=ctor
 assert(load(source,'author','t',env))()
 assert(env.Font==ctor,'must not replace global Font')
 assert(count==0,'font must load lazily')
 local function render() for _,cb in ipairs(callbacks) do if cb[1]==2 then cb[2](mod) end end end
 local enemy={IsActiveEnemy=function() return true end,IsInvincible=function() return false end}
 for i=1,75 do
  paused=i>=10 and i<=20
  if i==3 then mod:OnDamageHit(enemy,25.56,0) end
  if i==24 then player.Position=vec(200,125); player.Damage=12; player.MaxFireDelay=3 end
  if i==30 then options[1].OnChange(false) end
  if i==32 then options[2].OnChange(false) end
  if i==34 then options[3].OnChange(false) end
  if i==36 then for _,o in ipairs(options) do o.OnChange(true) end end
  if i==74 then mod:Reset() end
  if i==46 then mod:OnDamageHit(enemy,233.44,1) end
  if i==60 then mod:OnDamageHit(enemy,12,2) end
  if i==61 then mod:OnDamageHit(enemy,900,4) end
  render()
 end
 -- Trigger both actual reset callbacks, then ensure cache survives a collection.
 for _,cb in ipairs(callbacks) do if cb[1]==3 or cb[1]==4 then cb[2](mod); render() end end
 collectgarbage('collect'); render()
 local before=count
 if second then
  -- A second copy in a separate mod environment must create its own font.
  local other=run(source,0,false)
  assert(other.count==1,'private mod font constructions: expected 1, got '..other.count)
 end
 return {trace=serialize(trace),draws=serialize(draws),count=count,loads=loads,before=before}
end
'''
# Recursive calls are resolved through the local binding, not the global table.
LUA = LUA.replace('local function run(source, failures, second)', 'local run\nrun = function(source, failures, second, initialSettings)')

class WmdFontCacheTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp = tempfile.TemporaryDirectory(prefix='wmd-font-cache-')
  work=Path(cls.tmp.name)
  src=ROOT/'runtime/source'
  objects=lua_harness_objects(src,work)
  (work/'host.cpp').write_text(HARNESS)
  cls.host=work/'host'
  result=subprocess.run(['c++','-std=c++17','-I'+str(src/'third_party/lua-5.3.3/src'),str(work/'host.cpp'),*[str(p) for p in objects],'-o',str(cls.host)],capture_output=True,text=True)
  if result.returncode: raise AssertionError(result.stdout+result.stderr)
 @classmethod
 def tearDownClass(cls): cls.tmp.cleanup()
 def test_complete_author_behavior_and_retry_cache(self):
  self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),'01bf6f70012f1c3ec25303a2eb058aae130a4614259cdea33b22c7cad445c3ec')
  # Before implementation, run the author as candidate: this produces the intended
  # behavioral red (78 constructions), rather than an absent-file exception.
  candidate=PATCH.read_text() if PATCH.exists() else ORIGINAL.read_text()
  script=LUA+'\nlocal original=[====['+ORIGINAL.read_text()+']====]\nlocal patch=[====['+candidate+']====]\n'+r'''
 for _,failures in ipairs({0,1,3,100}) do
  local a=run(original,failures,false)
  local b=run(patch,failures,failures==0)
  assert(a.trace==b.trace,'callback/menu/save behavior changed')
  assert(a.draws==b.draws,'drawing arguments changed')
  local expected=math.min(failures+1,78)
  assert(b.count==expected,'font constructions: expected '..expected..', got '..b.count)
  assert(b.loads==expected,'font load count mismatch')
 end
 for _,saved in ipairs({'000','101','010'}) do
  local a=run(original,0,false,saved)
  local b=run(patch,0,false,saved)
  assert(a.trace==b.trace and a.draws==b.draws,'saved settings behavior changed')
  assert(b.count==1 and b.loads==1,'saved settings rebuilt font')
 end
 print('PASS: full author parity; nil Load; failures 0/1/3/100; saved settings 000/101/010; reset/GC/private cache')
'''
  file=Path(self.tmp.name)/'case.lua'; file.write_text(script)
  result=subprocess.run([str(self.host),str(file)],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  print(result.stdout.strip())

if __name__=='__main__': unittest.main()
