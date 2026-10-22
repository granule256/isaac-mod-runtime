"""游戏与房间的真实生产接线边界；复用正常夹具但不覆盖原消费者。"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_api300_game_room as base
from .test_support import build_lua_harness

GAME = r'''
 Put<std::int32_t>(0x26fa38,-1);
 Put<std::int32_t>(0x2f0050,18);Put<std::int32_t>(0x2f0054,3);
 if(luaL_dostring(L,R"LUA(
 assert(not game:HasHallucination())
 game:AddPixelation(-9)
 assert(not pcall(function()game.GetDarknessModifier(Isaac.GetPlayer())end))
 assert(not pcall(function()game.AddPixelation(Isaac.GetPlayer(),4)end))
 )LUA"))return 30;
 assert(Read<std::int32_t>(0x2f0050)==18&&Read<std::int32_t>(0x2f0054)==18);
 Put<std::uintptr_t>(0x2f0040,reinterpret_cast<std::uintptr_t>(bosses)-8);
 if(luaL_dostring(L,"assert(not pcall(function()game:GetNumEncounteredBosses()end))"))return 31;
 Put<std::uintptr_t>(0x2f0040,reinterpret_cast<std::uintptr_t>(bosses)+7);
 if(luaL_dostring(L,"assert(not pcall(function()game:GetNumEncounteredBosses()end))"))return 32;
 WriteWord(g_OwnerSlotBytes,0,0);
 if(luaL_dostring(L,R"LUA(
 for _,name in ipairs({'SetLastDevilRoomStage','AddTreasureRoomsVisited','GetTreasureRoomVisitCount',
 'AddStageWithoutHeartsPicked','GetStagesWithoutHeartsPicked','AddStageWithoutDamage',
 'ClearStagesWithoutDamage','GetStagesWithoutDamage','GetDevilRoomDeals','GetDonationModGreed',
 'GetDonationModAngel','ClearDonationModGreed','ClearDonationModAngel','SetLastLevelWithDamage',
 'GetNumEncounteredBosses','SetLastLevelWithoutHalfHp','GetScreenShakeCountdown',
 'GetDarknessModifier','GetTargetDarkness','AddPixelation','HasHallucination'}) do
 assert(type(game[name])=='function',name)
 assert(not pcall(function()game[name](game,3)end),name)
 end
 )LUA"))return 33;
'''

ROOM = r'''
 rput(0xe98,std::int32_t{37});
 if(luaL_dostring(L,R"LUA(
 assert(room:GetGridPathFromPos(Vector(0,80))==37)
 assert(room:GetGridPathFromPos(Vector(-21,80))==0)
 assert(room:GetGridPathFromPos(Vector(1,81))==37)
 assert(room:GetGridPathFromPos(Vector(540,160))==0)
 assert(room:GetGridPathFromPos(Vector(80,380))==0)
 assert(room:GetGridPathFromPos(Vector(0/0,160))==0)
 assert(room:GetGridPathFromPos(Vector(math.huge,160))==0)
 assert(room:GetGridPathFromPos(Vector(-math.huge,160))==0)
 assert(room:GetGridPathFromPos(Vector(1e30,160))==0)
 local v=room:GetWaterCurrent();v.X=90
 assert(room:GetWaterCurrent().X==3)
 room:SetSacrificeDone(0);assert(room:IsSacrificeDone())
 room:SetAmbushDone(false);room:SetSacrificeDone(nil)
 assert(not room:IsSacrificeDone())
 assert(not pcall(function()room.GetWaterCurrent(Game())end))
 assert(not pcall(function()room.SetSacrificeDone(Game(),true)end))
 )LUA")){std::fprintf(stderr,"%s\n",lua_tostring(L,-1));return 40;}
 std::memcpy(&flags,descriptor.data()+0x50,4);assert(flags==0x80000001);
 WriteWord(g_RoomBytes,8,0);
 if(luaL_dostring(L,R"LUA(
 assert(not pcall(function()room:IsSacrificeDone()end))
 assert(not pcall(function()room:SetSacrificeDone(true)end))
 assert(not pcall(function()room:SetAmbushDone(true)end))
 )LUA"))return 41;
 api300Room=nullptr;WriteWord(g_OwnerSlotBytes,0,0);
 if(luaL_dostring(L,R"LUA(
 for _,name in ipairs({'IsInitialized','KeepDoorsClosed','GetSecondBossID','GetRedHeartDamage',
 'SetRedHeartDamage','HasTriggerPressurePlates','GetWaterCurrent','StopRain',
 'SetCardAgainstHumanity','SetAmbushDone','SetSacrificeDone','IsSacrificeDone','GetGridPathFromPos'}) do
 assert(type(room[name])=='function',name)
 assert(not pcall(function()room[name](room,true)end),name)
 end
 )LUA"))return 42;
'''


class GameRoomBoundaries(unittest.TestCase):
    def run_consumer(self, main, extra, room=False):
        if room:
            main = main.replace('lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pop(L,1);',
                'lua_pushcfunction(L,VectorIndex);lua_setfield(L,-2,"__index");lua_pushcfunction(L,VectorNewIndex);lua_setfield(L,-2,"__newindex");lua_pop(L,1);')
        main = main.replace('lua_close(L);return 0;}',extra+'\n lua_close(L);return 0;}')
        source = base.fixture.HARNESS[:base.fixture.HARNESS.index('int main(')] + main
        source = re.sub(r'namespace GameFileReader \{\nTextReadResult[\s\S]*?\n\}\n\}', '',source,count=1)
        if room:
            source = source.replace('GameRoomObservation ReadCurrentGameRoom(uintptr_t, void**) {\n    return GameRoomObservation::RoomUnreadable;\n}',
                'extern void*api300Room;\nGameRoomObservation ReadCurrentGameRoom(uintptr_t,void**out){*out=api300Room;return api300Room?GameRoomObservation::Success:GameRoomObservation::RoomUnreadable;}')
        with tempfile.TemporaryDirectory(prefix='api300-game-room-boundaries-') as directory:
            binary = build_lua_harness(source_root=base.fixture.SOURCE,workdir=Path(directory),harness_source=source)
            result = subprocess.run([str(binary),'normal'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_game_statistics_invalid_vector_wrong_receiver_and_all_retired_methods(self):
        self.run_consumer(base.MAIN,GAME)

    def test_room_grid_float_edges_value_copy_descriptor_and_all_retired_methods(self):
        self.run_consumer(base.ROOM_MAIN,ROOM,True)
