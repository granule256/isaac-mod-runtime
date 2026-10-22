"""真实作者主入口与回调：完成初始化、绘制概率、属性栏开关和下一层更新。

宿主只替代设备/绘图依赖；Vector、Options读写、JSON、Mod及回调表走生产实现。
不能把Font/Sprite替身通过当成真机图形验证。
"""
import subprocess,tempfile,unittest
from pathlib import Path
from . import test_lua_batch343_get_color_and_lists as fixture
from .test_support import build_lua_harness
ROOT=Path(__file__).resolve().parents[2]
PRELUDE=r'''
-- 宿主诊断档不装文件require；仅将内建json名字映射到生产JSON模块。
local require=function(name)assert(name=='json');return json end
local probability=.01
local data={}
local player={FrameCount=10,Parent=nil}
function player:GetData()return data end
function player:GetPlayerType()return PlayerType.PLAYER_ISAAC end
function player:GetBabySkin()return -1 end
function player:GetMainTwin()return self end
function player:HasCollectible()return false end
function player:GetCollectibleNum()return 0 end
local level={}
function level:GetPlanetariumChance()return probability end
function level:IsAscent()return false end
function level:GetAbsoluteStage()return LevelStage.STAGE1_1 end
function level:GetRooms()return {Size=1,Get=function()return {Data={Type=RoomType.ROOM_TREASURE}}end}end
local room={GetType=function()return RoomType.ROOM_DEFAULT end,GetRoomConfigStage=function()return 1 end}
local seeds={HasSeedEffect=function()return false end,CountSeedEffects=function()return 0 end}
local game={Difficulty=Difficulty.DIFFICULTY_HARD,ScreenShakeOffset=Vector.Zero}
function game:GetLevel()return level end
function game:GetRoom()return room end
function game:GetHUD()return {IsVisible=function()return true end}end
function game:GetSeeds()return seeds end
function game:GetNumPlayers()return 1 end
function game:IsGreedMode()return false end
function game:GetVictoryLap()return 0 end
Game=function()return game end
Isaac.GetPlayer=function()return player end
Isaac.GetItemConfig=function()return {GetTrinket=function()return {IsAvailable=function()return true end}end}end
Isaac.Spawn=function()return {Exists=function()return true end,Remove=function()end}end
local texts={};local renders=0;local loadedFonts={}
Font=function()return {Load=function(_,path)loadedFonts[#loadedFonts+1]=path end,DrawString=function(_,text,x,y)texts[#texts+1]={text=text,x=x,y=y}end}end
Sprite=function()return {Load=function()end,SetFrame=function()end,Render=function()renders=renders+1 end}end
'''
CHECKS=r'''
-- 真实缺失存档首次安装续局，保留作者默认值。
PlanetariumChance.HasData=function()return false end
local saved
PlanetariumChance.SaveData=function(_,data)saved=data end
Isaac.RunCallback(ModCallbacks.MC_POST_GAME_STARTED,true)
assert(PlanetariumChance.initialized==true,'real author init must finish')
assert(PlanetariumChance.font~=nil and PlanetariumChance.hudSprite~=nil)
assert(math.abs(PlanetariumChance.coords.X-6)<.0001 and math.abs(PlanetariumChance.coords.Y-187.6)<.0001)
Isaac.RunCallback(ModCallbacks.MC_POST_RENDER)
assert(texts[1].text=='1.0%' and renders==1)
assert(loadedFonts[1]=='font/luaminioutlined.fnt')
local count=#texts
Options.FoundHUD=false
Isaac.RunCallback(ModCallbacks.MC_POST_RENDER)
assert(#texts==count and renders==1,'native HUD switch must hide chance')
Options.FoundHUD=true
probability=.21
Isaac.RunCallback(ModCallbacks.MC_POST_NEW_LEVEL)
Isaac.RunCallback(ModCallbacks.MC_POST_RENDER)
assert(texts[count+1].text=='21.0%' and renders==2)
-- 新局仍调用作者正常保存流程，概率没有变成固定1%。
Isaac.RunCallback(ModCallbacks.MC_POST_GAME_STARTED,false)
assert(PlanetariumChance.initialized and type(saved)=='string')
local decoded=require('json').decode(saved)
assert(decoded.Available==1 and decoded.CanSpawn==1)
local harness=RegisterMod('full-init-harness',1);harness:AddCallback(1,function()end)
'''
class PlanetariumFullInitTests(unittest.TestCase):
 def test_whole_author_module_init_render_visibility_and_floor_update(self):
  mod=(ROOT/'runtime/mod-patches/PlanetariumChance/main.lua').read_text()
  script=PRELUDE+'\n'+mod+'\n'+CHECKS
  main=r'''
int main(){PublishFakeMemory();LuaRuntime::SetGameBindings(AddressOf(g_OwnerSlotBytes),0x2222);
 WriteAt<float>(g_ManagerBytes,0x36514,0.3F);WriteAt<std::uint8_t>(g_ManagerBytes,0x3650a,1);
 const char* script=R"planet('''+script+r''')planet";
 auto r=LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@planetarium-full.lua");char error[2048]{};static_cast<void>(LuaRuntime::CopyLastLuaErrorText(error,sizeof(error)));std::puts(error);
 return r==LuaRuntime::LuaInitResult::Success?0:1;}
'''
  source=fixture.HARNESS[:fixture.HARNESS.index('int main(')]+main
  for name in ('CURRENT_TINT','CURRENT_SHIFT','DEFAULT_TINT','SPLAT_TINT'):
   for i,v in enumerate(getattr(fixture,name)):source=source.replace(f'{name}_{i}',repr(v))
  for name in ('COLLECTIBLE_COUNT','TRINKET_COUNT','ENTITY_DEFAULT_COLOR_OFFSET','ENTITY_SPLAT_COLOR_OFFSET'):source=source.replace(name,str(getattr(fixture,name)))
  with tempfile.TemporaryDirectory(prefix='planet-full-')as tmp:
   binary=build_lua_harness(source_root=fixture.SOURCE,workdir=Path(tmp),harness_source=source)
   r=subprocess.run([str(binary)],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
