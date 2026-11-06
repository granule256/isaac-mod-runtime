"""StageAPI can retarget a descriptor without changing config ownership or flags."""
import unittest
from . import test_api500_world as world

class RoomDescriptorDataWriteTests(unittest.TestCase):
 def test_data_accepts_borrowed_room_config_or_nil_without_touching_override(self):
  main=world.MAIN.replace('roomConfig(0x80)','roomConfig(0x100)')
  marker='const char*script=R"lua(';start=main.index(marker)+len(marker);end=main.index(')lua";',start)
  script=r'''
local d=Game():GetLevel():GetCurrentRoomDesc()
local saved=d.Data;local other=d.OverrideData
assert(saved.Variant==70050 and other.Variant==70051)
local flags=d.Flags
d.Data=other
assert(d.Data.Variant==70051 and d.OverrideData.Variant==70051 and d.Flags==flags)
assert(saved.Variant==70050,'original config remains owned by its RoomSet')
d.Data=nil
assert(d.Data.Type==0,'nil must clear the native pointer')
collectgarbage('collect')
d.Data=other
assert(d.Data.Variant==70051 and d.OverrideData.Variant==70051 and d.Flags==flags)
assert(not pcall(function()d.Data={}end))
assert(not pcall(function()d.Data=37 end))
d.GridIndex=-7;d.SafeGridIndex=-7;d.ListIndex=21
d.DisplayFlags=5;d.VisitedCount=3;d.Flags=0x80000400
assert(d.GridIndex==-7 and d.SafeGridIndex==-7 and d.ListIndex==21)
assert(d.DisplayFlags==5 and d.VisitedCount==3)
d.Clear=0;assert(d.Clear==true and d.Flags==0x80000401)
d.Clear=nil;assert(d.Clear==false and d.Flags==0x80000400)
for _,key in ipairs({'GridIndex','SafeGridIndex','ListIndex','DisplayFlags','VisitedCount','Flags'})do
 assert(not pcall(function()d[key]=1.5 end))
end
local m=RegisterMod('descriptor setter',1);m:AddCallback(1,function()end)
'''
  main=main[:start]+script+main[end:]
  before='if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@api500-world.lua")'
  setup=r'''
constexpr std::size_t owner=0x21b78+0x100+0x68;
WriteAt<std::int32_t>(roomConfig,0,1);WriteAt<std::int32_t>(roomConfig,4,0);
WriteAt<std::uint32_t>(roomConfig,8,5);WriteAt<std::uint32_t>(roomConfig,0xc,70050);
WriteAt<std::int32_t>(roomConfig,0x80,1);WriteAt<std::int32_t>(roomConfig,0x84,0);
WriteAt<std::uint32_t>(roomConfig,0x88,2);WriteAt<std::uint32_t>(roomConfig,0x8c,70051);
WriteWord(g_GameBytes,owner+0x18,AddressOf(roomConfig));WriteAt<std::uint32_t>(g_GameBytes,owner+0x20,2);
WriteWord(g_GameBytes,0x18+0x18,AddressOf(roomConfig)+0x80);
const unsigned char overrideRead[]={0x97,0x0e,0x40,0xf9,0xd7,0x00,0x00,0xb4,0xe8,0x02,0x40,0xb9,0x88,0x00,0x00,0x35};
const unsigned char overrideWrite[]={0x97,0x0e,0x00,0xf9,0x21,0x57,0x40,0xb9,0xe0,0x03,0x1b,0xaa,0x22,0x5f,0x40,0xb9};
std::memcpy(g_ModuleBytes.data()+0x3d6edc,overrideRead,16);
std::memcpy(g_ModuleBytes.data()+0x3d707c,overrideWrite,16);
auto unchanged=g_GameBytes;WriteWord(unchanged,0x28,AddressOf(roomConfig)+0x80);
WriteAt<std::int32_t>(unchanged,0x18,-7);WriteAt<std::int32_t>(unchanged,0x1c,-7);
WriteAt<std::uint32_t>(unchanged,0x20,21);WriteAt<std::uint32_t>(unchanged,0x18+0x48,5);
WriteAt<std::uint32_t>(unchanged,0x18+0x4c,3);WriteAt<std::uint32_t>(unchanged,0x18+0x50,0x80000400U);
const auto originalConfigs=roomConfig;
'''
  assert before in main;main=main.replace(before,setup+before,1)
  where=main.rfind('return 0;}');assert where>=0
  main=main[:where]+'assert(g_GameBytes==unchanged);assert(roomConfig==originalConfigs);'+main[where:]
  result=world.run_world(('data',),main=main)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
