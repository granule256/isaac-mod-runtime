"""OverrideData 是 PC 的 borrowed RoomConfigRoom 指针，必须沿真实描述符元方法读写。"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from . import test_lua_room_descriptor as fixture
from .test_support import build_lua_harness

GUARDS = r'''
constexpr unsigned char overrideRead[]={0x97,0x0e,0x40,0xf9,0xd7,0x00,0x00,0xb4,0xe8,0x02,0x40,0xb9,0x88,0x00,0x00,0x35};
constexpr unsigned char overrideWrite[]={0x97,0x0e,0x00,0xf9,0x21,0x57,0x40,0xb9,0xe0,0x03,0x1b,0xaa,0x22,0x5f,0x40,0xb9};
std::memcpy(g_ModuleBytes.data()+0x3d6edc,overrideRead,16);
std::memcpy(g_ModuleBytes.data()+0x3d707c,overrideWrite,16);
'''
SCRIPT = r'''
local mod=RegisterMod('Override',1)
local phase=0
local d,source,override,flags,moduleSource
mod:AddCallback(ModCallbacks.MC_PRE_GET_COLLECTIBLE,function()
 if phase==0 then
  d=Game():GetLevel():GetCurrentRoomDesc();source=d.Data;flags=d.Flags
  assert(d.OverrideData==nil)
  d.OverrideData=source
  assert(type(d.OverrideData)=='userdata' and d.OverrideData.Type==source.Type)
  assert(d.Data.Type==source.Type and d.Flags==flags)
  d.OverrideData=nil;assert(d.OverrideData==nil)
  for _,bad in ipairs({{},123,'RoomConfigRoom',false}) do
   assert(not pcall(function() d.OverrideData=bad end))
  end
  d.OverrideData=source;override=d.OverrideData
  assert(not pcall(function() override.Type=6 end),'config writable surface must not expand')
 elseif phase==1 then
  assert(source.Type==6 and override.Type==6 and d.OverrideData.Type==6,'borrowed alias must reflect native edits')
  assert(d.Flags==flags)
 elseif phase==2 then
  assert(not pcall(function() return source.Type end),'Data owner changed')
  assert(override.Type==6,'override must validate +0x18 rather than changed Data +0x10')
  assert(not pcall(function() d.OverrideData=source end),'stale source owner must be rejected')
  d.OverrideData=override
  assert(d.OverrideData.Type==6)
  d.OverrideData=nil
  assert(d.OverrideData==nil and not pcall(function() return override.Type end),'nil must invalidate descriptor-owned override view')
  d.OverrideData=d.Data;override=d.OverrideData
  assert(override.Type==4 and d.Flags==flags)
 elseif phase==3 then
  moduleSource=d.Data
  d.OverrideData=nil;assert(d.OverrideData==nil and d.Flags==flags)
 elseif phase==4 then
  assert(not pcall(function() return moduleSource.Type end),'old module source view must fail')
  assert(not pcall(function() return override.Type end),'old module view must fail')
  assert(not pcall(function() d.OverrideData=override end),'old module assignment must fail')
 end
 phase=phase+1
end)
'''

DISPATCH = r'''
auto dispatch=[&](){LuaRuntime::DispatchPreGetCollectible(nullptr,0,0,1,0);if(LuaRuntime::TakeCallbackError()){char buffer[1024]{};const auto n=LuaRuntime::CopyLastLuaErrorText(buffer,sizeof(buffer));std::fprintf(stderr,"%.*s\n",static_cast<int>(n),buffer);return false;}return true;};
const auto descriptor=std::size_t{0x18};
std::uintptr_t nativeOverride{},nativeData{};std::uint32_t nativeFlags{};
if(!dispatch())return 10;
std::memcpy(&nativeOverride,g_LevelBytes.data()+descriptor+0x18,8);
std::memcpy(&nativeData,g_LevelBytes.data()+descriptor+0x10,8);
std::memcpy(&nativeFlags,g_LevelBytes.data()+descriptor+0x50,4);
if(nativeOverride!=AddressOf(g_ConfigBytes)||nativeData!=AddressOf(g_ConfigBytes)||nativeFlags!=0x401)return 11;
WriteAt<std::uint32_t>(g_ConfigBytes,0x8,6);
if(!dispatch())return 12;
WriteWord(g_LevelBytes,descriptor+0x10,AddressOf(g_ConfigBytes)+0x60);
if(!dispatch())return 13;
std::memcpy(&nativeOverride,g_LevelBytes.data()+descriptor+0x18,8);
std::memcpy(&nativeData,g_LevelBytes.data()+descriptor+0x10,8);
std::memcpy(&nativeFlags,g_LevelBytes.data()+descriptor+0x50,4);
if(nativeOverride!=AddressOf(g_ConfigBytes)+0x60||nativeData!=AddressOf(g_ConfigBytes)+0x60||nativeFlags!=0x401)return 14;
if(!dispatch())return 15;
std::memcpy(&nativeOverride,g_LevelBytes.data()+descriptor+0x18,8);
std::memcpy(&nativeData,g_LevelBytes.data()+descriptor+0x10,8);
std::memcpy(&nativeFlags,g_LevelBytes.data()+descriptor+0x50,4);
if(nativeOverride!=0||nativeData!=AddressOf(g_ConfigBytes)+0x60||nativeFlags!=0x401)return 16;
LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes)+16);
if(!dispatch())return 17;
LuaRuntime::SetEngineModuleBase(AddressOf(g_ModuleBytes));
'''



class OverrideData(unittest.TestCase):
    def test_borrowed_pointer_via_real_descriptor_metatable(self):
        harness = fixture.HARNESS.replace('LuaRuntime::SetGameBindings(AddressOf(g_OwnerBytes), 0x2222);',
            GUARDS + '\nLuaRuntime::SetGameBindings(AddressOf(g_OwnerBytes), 0x2222);')
        harness = harness.replace('    const auto result = LuaRuntime::InitializeFromBuffer',
            '    script=R"override(' + SCRIPT + ')override";\n    const auto result = LuaRuntime::InitializeFromBuffer')
        harness = harness.replace('    LuaRuntime::DispatchPreGetCollectible(nullptr, 0, 0, 1, 0);', DISPATCH)
        with tempfile.TemporaryDirectory(prefix='room-override-') as directory:
            binary = build_lua_harness(source_root=fixture.SOURCE, workdir=Path(directory),
                                      harness_source=harness)
            result = subprocess.run([str(binary), 'fields'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
