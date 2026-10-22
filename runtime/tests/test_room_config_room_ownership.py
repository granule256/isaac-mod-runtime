"""真实Lua配置视图必须跟随RoomSet所有权，不能跟随可复用描述符槽。"""
import unittest
from . import test_api500_world as world

class RoomConfigRoomOwnershipTests(unittest.TestCase):
 def test_cached_config_survives_descriptor_retarget_but_not_room_set_unload(self):
  main=world.MAIN.replace('roomConfig(0x80)','roomConfig(0x100)')
  marker='const char*script=R"lua('
  start=main.index(marker)+len(marker);end=main.index(')lua";',start)
  script=r'''
local saved=Game():GetLevel():GetCurrentRoomDesc().Data
assert(saved.Variant==70050 and saved.Shape==1)
local mod=RegisterMod('room config cache owner',1)
local phase=0
mod:AddCallback(1,function()
 if phase==0 then
  assert(saved.Variant==70050 and saved.Shape==1,'cached config must survive debug descriptor retarget')
  local next=Game():GetLevel():GetCurrentRoomDesc().Data
  assert(next.Variant==70051 and next.Shape==2)
  phase=1;cached_config_pass=1
 else
  assert(not pcall(function()return saved.Variant end),'unloaded RoomSet must reject old config')
  cached_config_pass=2
 end
end)
'''
  main=main[:start]+script+main[end:]
  before='if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api500-world.lua")'
  setup=r'''
constexpr std::size_t owner=0x21b78+0x100+0x68;
WriteAt<std::int32_t>(roomConfig,0,1);WriteAt<std::int32_t>(roomConfig,4,0);
WriteAt<std::uint32_t>(roomConfig,0xc,70050);WriteAt<std::int32_t>(roomConfig,0x5c,1);
WriteAt<std::int32_t>(roomConfig,0x80,1);WriteAt<std::int32_t>(roomConfig,0x84,0);
WriteAt<std::uint32_t>(roomConfig,0x8c,70051);WriteAt<std::int32_t>(roomConfig,0xdc,2);
WriteWord(g_GameBytes,owner+0x18,AddressOf(roomConfig));WriteAt<std::uint32_t>(g_GameBytes,owner+0x20,2);
'''
  assert before in main;main=main.replace(before,setup+before,1)
  tail=r'''
WriteWord(g_GameBytes,0x28,AddressOf(roomConfig)+0x80);
LuaRuntime::DispatchPostUpdate();
if(LuaRuntime::TakeCallbackError()) {
 LuaRuntime::LuaErrorHistoryEntryView errors[8]{};auto count=LuaRuntime::CopyLuaErrorHistory(errors,8);
 for(std::size_t i=0;i<count;++i)std::fprintf(stderr,"%s\n",errors[i].text);
 return 2;
}
double passed=0;assert(LuaRuntime::ReadLuaGlobalNumber("cached_config_pass",&passed)&&passed==1);
WriteWord(g_GameBytes,owner+0x18,0);WriteAt<std::uint32_t>(g_GameBytes,owner+0x20,0);
LuaRuntime::DispatchPostUpdate();assert(!LuaRuntime::TakeCallbackError());
assert(LuaRuntime::ReadLuaGlobalNumber("cached_config_pass",&passed)&&passed==2);
'''
  where=main.rfind('return 0;}');assert where>=0;main=main[:where]+tail+main[where:]
  r=world.run_world(('borrowed',),main=main)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
