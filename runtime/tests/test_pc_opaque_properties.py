"""PC枚举userdata为独立值：验证原生字节、赋回隔离和跨源对象寿命。"""
import unittest
from .test_api600_player import BASELINE_MAIN
from .test_api400_params import run_main
from .test_api500_world import MAIN as WORLD_MAIN, run_world

PLAYER_SCRIPT=r'''
local p=Isaac.GetPlayer();skin=p.BabySkin
assert(type(skin)=='userdata','BabySkin must return PC enum userdata')
assert(not pcall(function()return skin.Value end),'no invented enum member')
assert(not pcall(function()skin.Value=3 end),'enum userdata has no writable fields')
p.BabySkin=skin
local m=RegisterMod("Opaque skin snapshot",1);m:AddCallback(ModCallbacks.MC_POST_UPDATE,function()p.BabySkin=skin end)
for _,v in ipairs({0,true,{},'1'})do assert(not pcall(function()p.BabySkin=v end),'only same enum snapshot accepted')end
'''
PLAYER_MAIN=BASELINE_MAIN[:BASELINE_MAIN.index('std::vector<unsigned char>weapon')]+r'''
static_cast<void>(&Tear);static_cast<void>(&Multi);static_cast<void>(&Pos);static_cast<void>(&Bomb);
const unsigned char skinLayout[]={0x02,0xe8,0x60,0xb9,0x09,0xf1,0x8c,0x52,0x69,0x00,0xa0,0x72,0xf3,0x03,0x00,0xaa};
std::memcpy(g_ModuleBytes.data()+0x27b064,skinLayout,16);
WriteAt<std::uint64_t>(g_Entities[kPlayer],0x20e8,0x12345678fffffff9ULL);
const char*script=R"lua('''+PLAYER_SCRIPT+r''')lua";
if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@opaque-skin.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::fprintf(stderr,"%s\n",e[i].text);return 1;}

WriteAt<std::int32_t>(g_Entities[kPlayer],0x20e8,77);
LuaRuntime::DispatchPostUpdate();
assert(At<std::uint64_t>(g_Entities[kPlayer].data(),0x20e8)==0x12345678fffffff9ULL);
LuaRuntime::ObserveGameThread();assert(LuaRuntime::ShutdownForModReload());return 0;}
'''

WORLD_SCRIPT=r'''
local d=Game():GetLevel():GetCurrentRoomDesc();doors=d.AllowedDoors;mode=d.Data.Mode
assert(type(doors)=='userdata','AllowedDoors must return PC enum userdata')
assert(type(mode)=='userdata','RoomConfig.Mode must return PC enum userdata')
assert(not pcall(function()return doors.Value end));assert(not pcall(function()doors.Value=1 end))
assert(not pcall(function()return mode.Value end));assert(not pcall(function()mode.Value=1 end))
d.AllowedDoors=doors
local m=RegisterMod("Opaque doors snapshot",1);m:AddCallback(ModCallbacks.MC_POST_UPDATE,function()d.AllowedDoors=doors end)
assert(not pcall(function()d.AllowedDoors=mode end),'distinct enum families')
assert(not pcall(function()d.AllowedDoors=7 end));assert(not pcall(function()d.Data.Mode=mode end))
'''
# 复用原房间/描述符夹具与固定指令守卫，只替换本用例的Lua消费者和原生预期。
WORLD_PREFIX=WORLD_MAIN[:WORLD_MAIN.index('const char*script=R"lua(')]
WORLD_MAIN_OPAQUE=WORLD_PREFIX+r'''
static_cast<void>(argc);static_cast<void>(argv);
const unsigned char doorsLayout[]={0x88,0x0a,0x40,0xf9,0xa8,0x15,0x00,0xb4,0x08,0x21,0x40,0xf9,0x88,0x12,0x00,0xf9};
std::memcpy(g_ModuleBytes.data()+0x3d680c,doorsLayout,16);
WriteAt<std::uint64_t>(g_GameBytes,0x18+0x20,0xa1b2c3d400000055ULL);
const char*script=R"lua('''+WORLD_SCRIPT+r''')lua";
if(LuaRuntime::InitializeFromBuffer(script,std::strlen(script),"@opaque-world.lua")!=LuaRuntime::LuaInitResult::Success){LuaRuntime::LuaErrorHistoryEntryView e[8]{};auto n=LuaRuntime::CopyLuaErrorHistory(e,8);for(std::size_t i=0;i<n;++i)std::fprintf(stderr,"%s\n",e[i].text);return 1;}
WriteAt<std::uint64_t>(g_GameBytes,0x18+0x20,0xdeadbeef00000099ULL);
LuaRuntime::DispatchPostUpdate();
std::uint64_t doors{};std::memcpy(&doors,g_GameBytes.data()+0x18+0x20,8);assert(doors==0xa1b2c3d400000055ULL);
LuaRuntime::ObserveGameThread();assert(LuaRuntime::ShutdownForModReload());return 0;}
'''
class OpaqueProperties(unittest.TestCase):
 def test_player_enum_value(self):
  r=run_main(PLAYER_MAIN);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_room_enum_values(self):
  r=run_world(main=WORLD_MAIN_OPAQUE);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
