"""真实 MinimapAPI 作者代码消费换房缓存，防止换层地图使用上一层房间。

冻结来源：analysis/mod-corpus/MinimapAPI/scripts/minimapapi/cache.lua 全文，
main.lua 的 updatePlayerPos、IsBadLoad、MC_POST_NEW_LEVEL 注册原文切片。
cache.lua SHA256: ff578f4d80e88de4ec1ba7beafc76bbbaf8f765f534e4f5c14f69bfc739febbd
main.lua 全文 SHA256: edbb6e0e8195598b014ad1510d988785769a161da964dba10f3b9d1b5073da9d
主目录作者代码只读取得；夹具不修改作者逻辑。本测试不验证设备/引擎内存读取。
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / 'fixtures/minimapapi_frame_events'

SCRIPT = r'''
local callbacks = {}
ModCallbacks = {MC_POST_NEW_ROOM=19, MC_POST_NEW_LEVEL=18}
package.preload['scripts.minimapapi.constants'] = function() return {CALLBACK_PRIORITY=-1000} end
local function register(_, id, fn) callbacks[id] = fn end
local function registerPriority(_, id, priority, fn)
  assert(priority == -1000, '作者缓存优先级应按原文注册')
  callbacks[id] = fn
end
function RegisterMod() return {AddCallback=register, AddPriorityCallback=registerPriority} end
local current = {stage=1, index=12, shape=1}
local descriptor = {GridIndex=current.index, Data={Shape=current.shape}}
local otherDimension = {}
local level = {}
function level:GetCurrentRoomDesc() return descriptor end
function level:GetRoomByIdx(index, dimension)
  assert(index == current.index)
  return dimension == 0 and descriptor or otherDimension
end
function GetPtrHash(value) return value end
function level:GetStage() return current.stage end
function level:GetAbsoluteStage() return current.stage end
function level:GetStageType() return 0 end
function level:GetCurrentRoomIndex() return current.index end
local room = {GetType=function() return 1 end}
local game = {GetLevel=function() return level end, GetRoom=function() return room end,
              GetSeeds=function() return {} end}
function Game() return game end
Isaac = {GetChallenge=function() return 0 end}
Challenge = {CHALLENGE_APRILS_FOOL=45}
local vector_mt = {__add=function(a,b) return setmetatable({X=a.X+b.X,Y=a.Y+b.Y},getmetatable(a)) end}
function Vector(x,y) return setmetatable({X=x,Y=y},vector_mt) end
local rebuiltStage
MinimapAPI = {isRepentance=true, RoomShapeGridPivots={[1]=Vector(0,0)}}
function MinimapAPI:AddCallbackFunc(id, _, fn) callbacks[id]=fn end
function MinimapAPI:ClearLevels() end
function MinimapAPI:LoadDefaultMap() rebuiltStage=self.Cache.Stage end
function MinimapAPI:GridIndexToVector(index) return Vector(index,0) end
function MinimapAPI:RunPlayerPosCallbacks() end
function MinimapAPI:UpdateExternalMap() end
local cache = dofile('@CACHE@')
MinimapAPI.Cache = cache
local playerMapPos
@MAIN@
local order = {@ORDER@}
local function dispatch()
  for _,id in ipairs(order) do callbacks[id](MinimapAPI) end
end
-- 新层房号改变：真实作者 updatePlayerPos 必须读取新层 RoomDescriptor。
current = {stage=2,index=37,shape=1}
descriptor = {GridIndex=current.index, Data={Shape=current.shape}}
dispatch()
assert(cache.Dimension == 0 and not cache.MirrorDimension, 'Repentance房间维度应由真实描述符身份判定')
assert(playerMapPos.X == 37, '地图玩家位置仍来自上一层房间')
assert(rebuiltStage == 2, '换层重建仍读取上一层 Stage')
-- 同房号跨层仍应更新 Stage；与生产451判定测试配合。
current = {stage=3,index=37,shape=1}
descriptor = {GridIndex=current.index, Data={Shape=current.shape}}
dispatch()
assert(cache.RoomDescriptor == descriptor and cache.Dimension == 0, '同房号跨层仍须更新描述符身份')
assert(rebuiltStage == 3, '同房号跨层重建仍读取上一层 Stage')
print('MINIMAP_AUTHOR_CACHE_PASSED')
'''

class MinimapFrameEventOrderTests(unittest.TestCase):
    def test_author_cache_is_fresh_when_new_level_consumes_it(self):
        cc = shutil.which('cc')
        self.assertIsNotNone(cc, '需要宿主 C 编译器')
        runtime = (ROOT/'runtime/source/lua_runtime.cpp').read_text()
        body = runtime.split('void DispatchFrameEvents(',1)[1].split('void DispatchPostUpdate()',1)[0]
        order = re.findall(r'dispatcher.Dispatch\(isaac::runtime::kCallbackPost(NewRoom|NewLevel)', body)
        self.assertEqual(sorted(order), ['NewLevel','NewRoom'])
        script = SCRIPT.replace('@CACHE@', str(FIXTURES/'cache.lua')).replace(
            '@MAIN@', (FIXTURES/'main_new_level.lua').read_text()).replace(
            '@ORDER@', ','.join('ModCallbacks.MC_POST_NEW_'+('ROOM' if x=='NewRoom' else 'LEVEL') for x in order))
        lua_root = ROOT/'runtime/source/third_party/lua-5.3.3/src'
        with tempfile.TemporaryDirectory(prefix='isaac-minimap-frame-') as directory:
            directory = Path(directory)
            binary = directory/'lua'
            build = subprocess.run([cc,'-std=c99','-w',*[str(p) for p in sorted(lua_root.glob('*.c')) if p.name!='luac.c'],
                                    '-lm','-o',str(binary)], capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            path = directory/'test.lua'
            path.write_text(script)
            run = subprocess.run([str(binary),str(path)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('MINIMAP_AUTHOR_CACHE_PASSED',run.stdout)

if __name__ == '__main__':
    unittest.main()
